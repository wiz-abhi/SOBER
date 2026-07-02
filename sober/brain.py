"""SOBER's thin async wrapper over cognee — the ONE module that imports cognee.

Everything else in ``sober`` stays cognee-free and unit-tests without the API;
this file is where the knowledge-graph primitives (ingest / recall / forget /
export / reset) actually touch cognee.

All cognee calls are async, so every public function here is ``async``. The CLI
wraps them with ``asyncio.run``.

Node-set-scoped forget convention
---------------------------------
cognee's ``forget`` is scoped to a whole dataset (or a single ``data_id``), not
to a node-set label. To make forget *surgical* at the node-set granularity —
the load-bearing requirement for "retract this batch of knowledge and nothing
else" — SOBER keeps every logical ``(dataset, node_set)`` pair in its **own
physical dataset**::

    physical_dataset("brain", "runbooks") == "brain__runbooks"

Callers work in terms of a logical ``dataset`` + optional ``node_set``; this
module maps that to the physical dataset name. ``forget(dataset, node_set)``
then forgets exactly one physical dataset and leaves the rest of the brain
intact. When ``node_set`` is ``None`` the physical dataset is just the logical
dataset name, so the common single-scope case is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from . import config

# Environment must be configured BEFORE cognee is imported so it reads the
# right LLM / embedding / storage settings from .env.
config.load_env()

import cognee  # noqa: E402  (must follow load_env)
from cognee import SearchType  # noqa: E402


# --------------------------------------------------------------------------
# Dataset naming + family registry
# --------------------------------------------------------------------------
# A logical "brain" is the UNION of its physical datasets: the base ``dataset``
# plus one ``dataset__<node_set>`` member per ingested node-set batch. Recall and
# export operate over the whole family so knowledge is visible no matter which
# batch it lives in, while ``forget(node_set=...)`` drops exactly one member —
# surgical retraction. We track family membership in a small on-disk registry
# (deterministic, no dependency on cognee's dataset-listing API).
_SEP = "__"
_REGISTRY_PATH = config.SNAP_DIR / ".family.json"


def physical_dataset(dataset: str, node_set: Union[str, None] = None) -> str:
    """Map a logical ``(dataset, node_set)`` pair to a physical dataset name.

    With a ``node_set`` the physical dataset is ``f"{dataset}__{node_set}"`` so
    it can be forgotten in isolation; without one it is just ``dataset``.

    >>> physical_dataset("brain", "runbooks")
    'brain__runbooks'
    >>> physical_dataset("brain")
    'brain'
    """
    if node_set:
        return f"{dataset}{_SEP}{node_set}"
    return dataset


def logical_dataset(physical: str) -> str:
    """The logical brain a physical dataset belongs to (strip ``__<node_set>``)."""
    return physical.split(_SEP, 1)[0]


def _load_registry() -> dict:
    try:
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_registry(reg: dict) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(reg, indent=2, sort_keys=True), encoding="utf-8")


def _register(physical: str) -> None:
    """Record ``physical`` as a member of its logical brain's family."""
    logical = logical_dataset(physical)
    reg = _load_registry()
    members = reg.setdefault(logical, [])
    if physical not in members:
        members.append(physical)
        _save_registry(reg)


def _unregister(physical: str) -> None:
    logical = logical_dataset(physical)
    reg = _load_registry()
    if logical in reg and physical in reg[logical]:
        reg[logical].remove(physical)
        _save_registry(reg)


def list_family(dataset: str) -> list[str]:
    """All physical datasets making up the logical ``dataset``.

    Returns the registered family members (base + every ``dataset__<node_set>``).
    If ``dataset`` is itself a physical sub-dataset (contains ``__``) or nothing
    is registered yet, returns just ``[dataset]`` so callers always get a usable
    list. Order is stable and puts the base dataset first when present.
    """
    if _SEP in dataset:
        return [dataset]
    members = _load_registry().get(dataset, [])
    if not members:
        return [dataset]
    ordered = ([dataset] if dataset in members else []) + [
        m for m in members if m != dataset
    ]
    return ordered or [dataset]


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------
async def ingest(
    source: str,
    dataset: str = "brain",
    node_set: Union[list[str], None] = None,
) -> dict:
    """Add + cognify a single text string or file path.

    ``source`` may be raw text or a path to a file; cognee's ``add`` accepts
    both. When ``node_set`` is given, the batch is routed to the physical
    dataset ``f"{dataset}__{node_set[0]}"`` so it can later be forgotten
    surgically, and the node-set labels are also attached in the graph.

    Returns ``{"dataset", "node_set", "chars"}`` where ``dataset`` is the
    *physical* dataset actually written and ``chars`` is the length of the
    source string (path string or text).
    """
    ns_label = node_set[0] if node_set else None
    phys = physical_dataset(dataset, ns_label)

    await cognee.add(source, dataset_name=phys, node_set=node_set)
    await cognee.cognify(datasets=[phys])
    _register(phys)

    return {
        "dataset": phys,
        "node_set": node_set,
        "chars": len(source),
    }


async def ingest_batch(
    sources: list[str],
    dataset: str,
    node_set: str,
) -> dict:
    """Add many sources under one node_set, then cognify once.

    All ``sources`` land in the same physical dataset
    ``f"{dataset}__{node_set}"`` and are tagged with the node-set label, so the
    whole batch is a single revert unit. Cognify runs a single time after every
    ``add`` to keep Gemini calls to one graph-build per batch.

    Returns ``{"dataset", "node_set", "chars", "count"}`` where ``chars`` is the
    total characters added across the batch and ``count`` is the number of
    sources.
    """
    phys = physical_dataset(dataset, node_set)

    total_chars = 0
    for source in sources:
        await cognee.add(source, dataset_name=phys, node_set=[node_set])
        total_chars += len(source)

    await cognee.cognify(datasets=[phys])
    _register(phys)

    return {
        "dataset": phys,
        "node_set": node_set,
        "chars": total_chars,
        "count": len(sources),
    }


# --------------------------------------------------------------------------
# Recall
# --------------------------------------------------------------------------
async def recall(
    query: str,
    dataset: str = "brain",
    top_k: int = 5,
    graph: bool = False,
) -> Union[list[dict], str]:
    """Query the brain.

    By default runs a CHUNKS search (vector similarity, no LLM at query time)
    and returns a ``list[dict]`` where each dict carries a ``"text"`` key plus
    cognee metadata (``id``, ``document_id``, ``belongs_to_set``, weights, …).

    With ``graph=True`` runs a GRAPH_COMPLETION search (LLM-composed answer over
    the graph) and returns a single ``str``.

    ``dataset`` is a LOGICAL brain name: the search spans its whole family
    (base + every ``dataset__<node_set>`` member) so knowledge is found no matter
    which node-set batch holds it. Passing an explicit physical name (one that
    already contains ``__``) scopes to just that member.
    """
    query_type = SearchType.GRAPH_COMPLETION if graph else SearchType.CHUNKS
    family = list_family(dataset)
    try:
        results = await cognee.search(
            query_text=query,
            query_type=query_type,
            datasets=family,
            top_k=top_k,
        )
    except Exception as exc:
        # After a full forget the family can be empty; cognee raises NoDataError.
        # An empty brain legitimately recalls nothing rather than erroring.
        if "NoDataError" in type(exc).__name__ or "No data found" in str(exc):
            return "" if graph else []
        raise

    if graph:
        # GRAPH_COMPLETION yields an LLM answer. cognee returns a list of
        # completion strings; normalize to a single string for callers.
        if isinstance(results, str):
            return results
        if isinstance(results, list):
            return "\n".join(str(r) for r in results)
        return str(results)

    return results


# --------------------------------------------------------------------------
# Forget
# --------------------------------------------------------------------------
async def forget(
    dataset: str = "brain",
    node_set: Union[str, None] = None,
    memory_only: bool = True,
) -> dict:
    """Forget recall for a dataset, optionally scoped to a node_set.

    When ``node_set`` is given, only the physical dataset
    ``f"{dataset}__{node_set}"`` is forgotten — a surgical retract that leaves
    the rest of the brain untouched. When ``node_set`` is ``None`` the whole
    logical dataset is forgotten.

    ``memory_only=True`` removes the vector/graph residue that powers recall
    (the SOBER-relevant part) while leaving raw stored data in place; pass
    ``False`` for a harder delete.

    Returns a summary dict ``{"dataset", "node_set", "memory_only", "result"}``
    where ``result`` is cognee's raw forget return value.
    """
    phys = physical_dataset(dataset, node_set)
    result = await cognee.forget(dataset=phys, memory_only=memory_only)
    # Drop the forgotten member from the family so recall/export stop spanning it.
    _unregister(phys)

    return {
        "dataset": phys,
        "node_set": node_set,
        "memory_only": memory_only,
        "result": result,
    }


# --------------------------------------------------------------------------
# Improve (CI-gated)
# --------------------------------------------------------------------------
async def improve(dataset: str = "brain", session_ids: Union[list[str], None] = None) -> dict:
    """Distill chat sessions into the graph via cognee's ``improve``.

    ``cognee.improve`` runs an LLM pass that folds the named ``session_ids`` back
    into the knowledge graph (learning from how the brain was actually used).
    This COSTS Gemini calls, so it is only ever invoked behind the green eval
    gate in :func:`sober.ci.ci_gate_improve`.

    ``dataset`` is a LOGICAL brain name: improve spans its whole family (base +
    every ``dataset__<node_set>`` member), mirroring :func:`recall` /
    :func:`export_json`. This matters because real ingestion is always node-set
    scoped (``ingest_batch`` → ``brain__core`` etc.), so the bare base dataset is
    empty — improving only ``dataset`` would distill nothing into the graph that
    actually holds the knowledge. ``session_ids`` may be ``None`` / empty to let
    cognee pick recent sessions per its own default; otherwise the listed
    sessions are distilled.

    Returns ``{"dataset", "session_ids", "result"}`` where ``result`` maps each
    family member to cognee's raw ``improve`` return value.
    """
    ids = list(session_ids) if session_ids else []
    results: dict = {}
    for member in list_family(dataset):
        try:
            if ids:
                results[member] = await cognee.improve(dataset=member, session_ids=ids)
            else:
                # No explicit sessions — let cognee apply its recent-session default.
                results[member] = await cognee.improve(dataset=member)
        except Exception as exc:
            # An empty/absent family member (e.g. the bare base) has nothing to
            # distill; skip it rather than failing the whole improve.
            if "NoDataError" in type(exc).__name__ or "No data found" in str(exc):
                continue
            raise

    return {
        "dataset": dataset,
        "session_ids": ids,
        "result": results,
    }


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
async def export_json(dataset: str, destination: Union[str, Path]) -> dict:
    """Export the logical brain's merged graph to a JSON file for snapshot/diff.

    ``dataset`` is a LOGICAL brain name: every family member (base +
    ``dataset__<node_set>``) is exported and merged into one
    ``{"nodes": [...], "edges": [...]}`` document so a snapshot captures the whole
    brain — a retracted node-set's residue therefore shows up (or, after forget,
    is provably absent) in structure evals and diffs. Nodes are de-duplicated by
    ``id``; edges by ``(source, target, relationship_name)``.

    Returns ``{"nodes": int, "edges": int, "path": str}`` (merged, de-duplicated
    counts).
    """
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)

    family = list_family(dataset)
    merged_nodes: dict[str, dict] = {}
    merged_edges: dict[tuple, dict] = {}

    for member in family:
        tmp = dest.parent / f".{member}.export.json"
        try:
            await cognee.export(member, format="json", destination=str(tmp))
        except Exception as exc:
            # A forgotten/empty member has nothing to export — skip it.
            if "NoDataError" in type(exc).__name__ or "No data" in str(exc):
                continue
            raise
        try:
            payload = json.loads(tmp.read_text(encoding="utf-8"))
        finally:
            tmp.unlink(missing_ok=True)
        for node in payload.get("nodes", []):
            merged_nodes[str(node.get("id"))] = node
        for edge in payload.get("edges", []):
            key = (
                str(edge.get("source")),
                str(edge.get("target")),
                str(edge.get("relationship_name")),
            )
            merged_edges[key] = edge

    merged = {"nodes": list(merged_nodes.values()), "edges": list(merged_edges.values())}
    dest.write_text(json.dumps(merged, indent=2, default=str), encoding="utf-8")

    return {
        "nodes": len(merged["nodes"]),
        "edges": len(merged["edges"]),
        "path": str(dest),
    }


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------
async def reset() -> None:
    """Full local reset: prune all data, then prune system metadata.

    Wipes every dataset and cognee's bookkeeping so the next ingest starts from
    a clean slate. Used by ``brain reset`` and by tests that need isolation.
    """
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)
    # Forget the family registry too, so a fresh brain starts with no members.
    _REGISTRY_PATH.unlink(missing_ok=True)
