"""SOBER regression bisector — ``git bisect`` for an agent's memory.

When a memory-CI eval goes red, *some* ingestion batch introduced the
regression (a leaked secret, a fact that got clobbered, a bad edge). This
module binary-searches the ordered per-batch datasets to pin the single
batch that flipped the failing eval red, then can surgically revert it.

Design (see :func:`bisect` docstring for the precise search):

* Ingestion history is a list of *physical* datasets, one per batch, in the
  order they were added. ``brain.py`` maintains the convention that each
  logical ``(dataset, node_set)`` maps to its own physical dataset
  (``brain.physical_dataset``), so every batch is independently forgettable.
* A "probe" runs the *failing eval only* against a cumulative prefix of those
  batch datasets and asks a single yes/no question: is the eval red once the
  batches ``batch_datasets[:k]`` are present?
* Because a regression is monotonic in the prefix (once the culprit batch is
  included the eval stays red for every longer prefix), we can binary-search
  the smallest ``k`` for which the prefix is red. The culprit is the batch at
  ``batch_datasets[k-1]`` — the one whose inclusion first flips the eval.

This module is deliberately **cognee-free**. It imports :mod:`sober.brain`
and :mod:`sober.evals` lazily inside functions so it unit-tests without the
live API and never triggers a cognee import at module load.
"""

from __future__ import annotations

from typing import Any


# --- prefix probe --------------------------------------------------------

async def _load_failing_spec(failing_eval: str) -> Any:
    """Return the single eval spec whose ``name`` matches ``failing_eval``.

    Raises ``ValueError`` if no eval by that name exists so the caller gets a
    clear error instead of a silently-empty bisect.
    """
    from sober import evals  # lazy: keeps this module cognee-free

    specs = evals.load_specs()
    for spec in specs:
        if getattr(spec, "name", None) == failing_eval:
            return spec
    known = ", ".join(sorted(str(getattr(s, "name", "?")) for s in specs)) or "<none>"
    raise ValueError(
        f"no eval named {failing_eval!r} in evals/ (known evals: {known})"
    )


async def _prefix_is_red(spec: Any, prefix: list[str]) -> bool:
    """Run the failing eval over the cumulative ``prefix`` of batch datasets.

    ``run_evals`` operates on a single dataset, so we evaluate the one failing
    spec against every batch dataset in the prefix and fold the per-batch
    results with the semantics that make cumulative memory correct:

    * The prefix is **red** as soon as *any* batch in it makes the eval red.
      For a ``forbidden`` eval a leak from any batch compromises the whole
      cumulative view; for ``must_know``/``structure`` a batch that fails the
      assertion is likewise a real failure once it is part of the graph.

    An empty prefix is defined green (nothing ingested, nothing can regress).
    """
    from sober import evals  # lazy

    if not prefix:
        return False

    for batch in prefix:
        report = await evals.run_evals(dataset=batch, specs=[spec])
        if not report["green"]:
            return True
    return False


# --- the bisector --------------------------------------------------------

async def bisect(
    dataset: str,
    batch_datasets: list[str],
    failing_eval: str,
) -> dict:
    """Binary-search the batch that turned ``failing_eval`` red.

    Parameters
    ----------
    dataset:
        The logical brain dataset under test. Recorded in the result for
        provenance; the search itself runs over ``batch_datasets``.
    batch_datasets:
        The physical per-batch datasets **in ingestion order** (oldest first).
        Typically produced by ``brain.physical_dataset(dataset, node_set)`` for
        each ingested batch.
    failing_eval:
        ``name`` of the eval (a YAML spec in ``evals/``) that is currently red
        and whose regression we want to localize.

    Returns
    -------
    dict
        ``{"culprit_dataset": str | None, "probes": int, "steps": [...],
           "dataset": str, "failing_eval": str, "total_batches": int}``

        ``culprit_dataset`` is the earliest batch whose inclusion flips the
        eval red, or ``None`` if the eval is already green over the full set
        (nothing to bisect). ``probes`` counts prefix evaluations performed —
        ``O(log n)`` by construction. ``steps`` records each probe as
        ``{"probe": i, "prefix_len": k, "candidate": name, "red": bool,
           "lo": lo, "hi": hi}`` for a legible audit trail.

    Search
    ------
    We seek the smallest prefix length ``k`` in ``[1, n]`` such that
    ``batch_datasets[:k]`` is red. Assuming monotonicity (a regression, once
    introduced, persists for every longer prefix) this boundary is unique and
    binary-searchable:

    * Invariant: prefixes of length ``< lo`` are green; prefixes of length
      ``>= hi`` are red. Start ``lo=1``, ``hi=n+1``.
    * Each step probes ``mid = (lo + hi) // 2``. Red → the boundary is at or
      below ``mid`` (``hi = mid``); green → strictly above (``lo = mid + 1``).
    * Terminate when ``lo == hi``. If ``lo <= n`` the culprit is
      ``batch_datasets[lo-1]``; if ``lo == n+1`` the full set is green.

    Before searching we probe the full prefix once: if it is green there is no
    regression to localize and we return early with ``culprit_dataset=None``.
    """
    n = len(batch_datasets)
    steps: list[dict] = []
    probes = 0

    result: dict[str, Any] = {
        "culprit_dataset": None,
        "probes": 0,
        "steps": steps,
        "dataset": dataset,
        "failing_eval": failing_eval,
        "total_batches": n,
    }

    if n == 0:
        return result

    spec = await _load_failing_spec(failing_eval)

    # Bisect localizes the batch that INTRODUCED a problem, which is inherently a
    # `forbidden` concept: a leak/poison present in the culprit batch stays present
    # in every larger prefix (monotonic red), so per-batch prefix probing is sound.
    # `must_know` regressions are not caused by adding a batch (an absent fact makes
    # small prefixes red and large ones green — the opposite direction, so the
    # binary search would return a spurious batch), and `structure` evals assert over
    # the whole merged graph and cannot be localized per batch. Reject both loudly.
    kind = getattr(spec, "kind", None)
    if kind != "forbidden":
        raise ValueError(
            f"bisect only supports 'forbidden' evals (they localize a leak/poison "
            f"monotonically); {failing_eval!r} is kind {kind!r}, which cannot be "
            f"bisected over ingestion batches."
        )

    # Sanity probe: is the eval actually red once everything is present?
    probes += 1
    full_red = await _prefix_is_red(spec, batch_datasets)
    steps.append(
        {
            "probe": probes,
            "prefix_len": n,
            "candidate": batch_datasets[-1],
            "red": full_red,
            "lo": 1,
            "hi": n + 1,
            "note": "full-set sanity probe",
        }
    )
    if not full_red:
        # Nothing regressed over the complete history — nothing to bisect.
        result["probes"] = probes
        return result

    # Binary search for the smallest red prefix length in [1, n].
    lo, hi = 1, n + 1
    while lo < hi:
        mid = (lo + hi) // 2
        candidate = batch_datasets[mid - 1]
        red = await _prefix_is_red(spec, batch_datasets[:mid])
        probes += 1
        steps.append(
            {
                "probe": probes,
                "prefix_len": mid,
                "candidate": candidate,
                "red": red,
                "lo": lo,
                "hi": hi,
            }
        )
        if red:
            hi = mid
        else:
            lo = mid + 1

    culprit = batch_datasets[lo - 1] if lo <= n else None
    result["culprit_dataset"] = culprit
    result["probes"] = probes
    return result


# --- revert --------------------------------------------------------------

async def revert(culprit_dataset: str, memory_only: bool = True) -> dict:
    """Retract a culprit batch by forgetting its physical dataset.

    Delegates to ``brain.forget`` with ``memory_only`` (default ``True`` — a
    recall-only retraction that leaves the source data on disk, matching Gate 2:
    the fact goes from recallable to ``[]`` without a full prune). Pass
    ``memory_only=False`` to also remove the underlying data.

    Parameters
    ----------
    culprit_dataset:
        The physical dataset returned as ``culprit_dataset`` by :func:`bisect`.
    memory_only:
        Forwarded to ``brain.forget``. ``True`` = recall-only retraction.

    Returns
    -------
    dict
        ``{"reverted": culprit_dataset, "memory_only": bool, "forget": <result>}``
        where ``forget`` is ``brain.forget``'s own summary dict.
    """
    from sober import brain  # lazy: the only module that imports cognee

    forget_result = await brain.forget(
        dataset=culprit_dataset, memory_only=memory_only
    )
    return {
        "reverted": culprit_dataset,
        "memory_only": memory_only,
        "forget": forget_result,
    }
