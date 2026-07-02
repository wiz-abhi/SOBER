"""Snapshot versioning for SOBER — PURE module (no cognee import at module load).

A *snapshot* is a JSON export of a Cognee knowledge graph, frozen on disk under
``snapshots/{dataset}_v{version}.json`` with a sidecar ``.meta.json`` describing
the version, human label, and node/edge counts. Snapshots are the artifact that
``brain diff`` compares and ``brain revert`` conceptually rolls back to — the
"git for agent brains" primitive.

This module is deliberately cognee-free so it unit-tests without the LLM API.
The one function that must talk to cognee, :func:`take_snapshot`, imports
``sober.brain`` *lazily* inside the function body.

Snapshot JSON shape (produced by ``cognee.export(format="json")``)::

    {"nodes": [ {...}, ... ], "edges": [ {...}, ... ]}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = [
    "snapshot_dir",
    "snapshot_path",
    "meta_path",
    "latest_version",
    "take_snapshot",
    "load_snapshot",
]


def snapshot_dir() -> Path:
    """Return the directory where snapshots live (``<repo>/snapshots``).

    Prefers :data:`sober.config.SNAP_DIR` when the config module is importable,
    so the whole project agrees on one location. Falls back to a path derived
    from this file's location (``<repo_root>/snapshots``) so the module still
    works standalone in isolation / unit tests, without importing config.
    The directory is created if it does not yet exist.
    """
    snap_dir: Path
    try:  # pragma: no cover - trivial import glue
        from sober.config import SNAP_DIR  # type: ignore

        snap_dir = Path(SNAP_DIR)
    except Exception:
        # sober/snapshot.py -> parents[1] is the repo root that holds snapshots/.
        snap_dir = Path(__file__).resolve().parents[1] / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    return snap_dir


def snapshot_path(dataset: str, version: int | str) -> Path:
    """Path to the snapshot JSON for ``dataset`` at ``version``.

    Layout: ``snapshots/{dataset}_v{version}.json``. ``version`` may be an int
    (``3``) or a string that already carries a ``v`` prefix (``"v3"`` / ``"3"``);
    both normalize to the same file so callers can pass CLI-friendly ``"v3"``.
    """
    v = str(version)
    if v.lower().startswith("v"):
        v = v[1:]
    return snapshot_dir() / f"{dataset}_v{v}.json"


def meta_path(dataset: str, version: int | str) -> Path:
    """Path to the sidecar metadata file for a snapshot.

    Layout: ``snapshots/{dataset}_v{version}.meta.json``.
    """
    snap = snapshot_path(dataset, version)
    return snap.with_suffix(".meta.json")


_VERSION_RE = re.compile(r"_v(\d+)\.json$", re.IGNORECASE)


def latest_version(dataset: str) -> int:
    """Highest existing snapshot version for ``dataset`` (``0`` if none exist).

    Scans ``snapshots/`` for ``{dataset}_v{N}.json`` files and returns the max
    ``N``. The ``.meta.json`` sidecars are ignored (they don't match the regex).
    """
    directory = snapshot_dir()
    highest = 0
    prefix = f"{dataset}_v"
    for path in directory.glob(f"{dataset}_v*.json"):
        name = path.name
        if not name.startswith(prefix):
            continue
        match = _VERSION_RE.search(name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


async def take_snapshot(dataset: str, label: str | None = None) -> Path:
    """Export ``dataset`` to a new, version-bumped snapshot on disk.

    Computes the next version (``latest_version + 1``), calls
    ``brain.export_json`` to write the graph JSON to
    ``snapshots/{dataset}_v{version}.json``, then writes a sidecar
    ``.meta.json`` with ``{version, label, ts_placeholder, nodes, edges}``.

    ``brain`` is imported lazily here so this module stays cognee-free at import
    time and remains unit-testable without the live API.

    Returns the path to the snapshot JSON.
    """
    from sober import brain  # lazy: the ONE cognee-touching dependency

    version = latest_version(dataset) + 1
    dest = snapshot_path(dataset, version)

    result = await brain.export_json(dataset, dest)
    # brain.export_json returns {"nodes": int, "edges": int, "path": str}.
    nodes = int(result.get("nodes", 0)) if isinstance(result, dict) else 0
    edges = int(result.get("edges", 0)) if isinstance(result, dict) else 0

    meta = {
        "dataset": dataset,
        "version": version,
        "label": label,
        # Kept as a placeholder per contract; a real timestamp is wired at the
        # orchestration layer so this pure module has no clock dependency.
        "ts_placeholder": None,
        "nodes": nodes,
        "edges": edges,
        "path": str(dest),
    }
    meta_path(dataset, version).write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return dest


def load_snapshot(path: str | Path) -> dict:
    """Load a snapshot JSON file into a ``{"nodes": [...], "edges": [...]}`` dict.

    Tolerant of exports that omit one of the two keys (defaults each to an empty
    list) so downstream :func:`sober.diff.diff_graphs` never KeyErrors on a
    partial/empty graph.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"snapshot at {path} is not a JSON object (got {type(raw).__name__})"
        )
    return {
        "nodes": list(raw.get("nodes", []) or []),
        "edges": list(raw.get("edges", []) or []),
    }
