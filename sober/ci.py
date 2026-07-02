"""SOBER CI orchestration — the entry points the CLI and GitHub Action call.

Two stories live here:

``ci_check``
    The pull-request gate. Snapshot the current brain, diff it against the
    previous snapshot, run the memory-CI eval suite, print a PR-ready markdown
    report plus the graph diff, persist ``ci_report.md`` to the repo root, and
    exit ``0`` (green) / ``1`` (red).

``ci_gate_improve``
    The "CI gates ``improve()``" story. Cognee's ``improve`` distills chat
    sessions into the graph via the LLM — a mutation that can *silently*
    regress memory (clobber a fact, resurface a forgotten secret). So we only
    run it behind a green gate and re-check afterwards: run evals BEFORE, refuse
    to improve if already red, run improve, run evals AFTER, and if improve
    turned the suite red we roll back and fail.

This module is cognee-free at import time. Everything that touches cognee
(``brain``, and the cognee-backed ``snapshot``/``evals`` calls) is imported
lazily inside the functions, so ``import sober.ci`` never pulls in the API and
the orchestration logic stays unit-testable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# config.py is pure (cognee-free) so importing it at module scope is safe and
# keeps the repo-root path constant available without a live API.
from sober.config import DATASET_DEFAULT, REPO_ROOT

CI_REPORT_PATH: Path = REPO_ROOT / "ci_report.md"

# Rendered when there is no prior snapshot to diff against — the diff engine
# still runs, but against an empty graph, so the whole brain reads as "added".
_EMPTY_GRAPH: dict[str, list] = {"nodes": [], "edges": []}


def _print(msg: str = "") -> None:
    """Console output via rich if available, else plain ``print``.

    rich is a declared dependency, but we degrade gracefully (and stay
    unit-testable) if it is ever missing. The reports carry emoji (🟢/❌);
    on a legacy Windows console (cp1252 stdout) both rich and the plain
    fallback raise ``UnicodeEncodeError``, so as a last resort we re-encode
    to the stream's charset with ``errors="replace"`` and write raw bytes —
    the CI report on disk keeps the real emoji regardless.
    """
    try:
        from rich import print as rprint

        rprint(msg)
        return
    except UnicodeEncodeError:
        pass
    except Exception:  # rich missing / not usable — fall through to print
        pass

    try:
        print(msg)
    except UnicodeEncodeError:
        import sys

        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = str(msg).encode(enc, errors="replace").decode(enc, errors="replace")
        print(safe)


def _prev_snapshot_dict(dataset: str, new_version: int) -> tuple[dict, int | None]:
    """Load the snapshot immediately preceding ``new_version``.

    Returns ``(graph_dict, prev_version)``. If no earlier snapshot exists (this
    was the first), returns ``(_EMPTY_GRAPH, None)`` so the diff is computed
    against an empty graph rather than crashing.
    """
    from sober import snapshot  # lazy

    prev_version = new_version - 1
    if prev_version < 1:
        return _EMPTY_GRAPH, None

    prev_path = snapshot.snapshot_path(dataset, prev_version)
    if not Path(prev_path).exists():
        return _EMPTY_GRAPH, None

    return snapshot.load_snapshot(prev_path), prev_version


async def ci_check(dataset: str = DATASET_DEFAULT) -> int:
    """Run the PR gate: snapshot → diff → evals → report → exit code.

    Steps
    -----
    1. ``snapshot.take_snapshot(dataset)`` — export the current graph and
       version it. The returned path's version becomes the "new" side.
    2. Load the *previous* snapshot (version - 1); diff new vs previous via
       ``diff.diff_graphs`` and render it with ``diff.render_markdown``.
    3. ``evals.run_evals(dataset)`` — the red/green memory-CI suite; rendered
       with ``evals.render_report``.
    4. Compose both into ``ci_report.md`` at the repo root and print it.

    Returns ``0`` if the eval suite is green, ``1`` if red. The diff never
    fails the build on its own — it is informational context for the reviewer;
    only the evals decide the exit code.
    """
    from sober import diff, evals, snapshot  # lazy

    # 1. snapshot the current state
    snap_path = await snapshot.take_snapshot(dataset)
    new_version = snapshot.latest_version(dataset)
    new_graph = snapshot.load_snapshot(snap_path)

    # 2. diff against the previous snapshot
    prev_graph, prev_version = _prev_snapshot_dict(dataset, new_version)
    graph_diff = diff.diff_graphs(prev_graph, new_graph)
    if prev_version is None:
        diff_title = f"Brain diff — v{new_version} (initial snapshot)"
    else:
        diff_title = f"Brain diff — v{prev_version} → v{new_version}"
    diff_md = diff.render_markdown(graph_diff, title=diff_title)

    # 3. run the memory-CI suite (this decides the exit code)
    report = await evals.run_evals(dataset=dataset)
    report_md = evals.render_report(report)
    green = bool(report["green"])

    # 4. compose + persist + print
    banner = "PASS ✅" if green else "FAIL ❌"
    full_md = (
        f"# SOBER CI — `{dataset}` — {banner}\n\n"
        f"{report_md}\n\n"
        f"---\n\n"
        f"{diff_md}\n"
    )
    CI_REPORT_PATH.write_text(full_md, encoding="utf-8")

    _print(full_md)
    _print(f"[dim]ci_report.md written to {CI_REPORT_PATH}[/dim]")

    return 0 if green else 1


async def ci_gate_improve(dataset: str, session_ids: list[str]) -> int:
    """Gate ``cognee.improve`` behind green evals; roll back on regression.

    Flow
    ----
    1. **Pre-check.** Run the eval suite. If it is already red, refuse to
       improve (you don't distill sessions into a broken brain) and exit ``1``.
    2. **Safety snapshot.** Version the current graph so a regression is
       recoverable.
    3. **Improve.** Call ``brain.improve(dataset, session_ids)`` (the cognee
       ``improve`` wrapper — an LLM mutation of the graph).
    4. **Post-check.** Re-run the eval suite. If it is still green, the improve
       is accepted → exit ``0``. If improve turned it red, **revert** and exit
       ``1``: this is the whole point of gating ``improve`` in CI.

    Rollback (step 4, red) is best-effort against whatever brain exposes: if
    ``brain.restore_snapshot`` exists we restore the pre-improve snapshot; the
    pre-improve snapshot path is always reported so the Action/operator can roll
    back deterministically even without an in-process restore hook.

    Returns ``0`` only when improve ran *and* the suite stayed green.
    """
    from sober import brain, evals, snapshot  # lazy

    # 1. pre-check — never improve on top of a red suite
    pre = await evals.run_evals(dataset=dataset)
    _print(evals.render_report(pre))
    if not pre["green"]:
        _print(
            "[red]improve() gate: evals are RED before improve — refusing to "
            "distill sessions into a broken brain.[/red]"
        )
        return 1

    # 2. safety snapshot so a regression is recoverable
    pre_snap_path = await snapshot.take_snapshot(dataset, label="pre-improve")
    _print(f"[dim]pre-improve snapshot: {pre_snap_path}[/dim]")

    # 3. improve (the gated cognee mutation)
    improve_result = await brain.improve(dataset=dataset, session_ids=session_ids)
    _print(f"[dim]improve() result: {improve_result}[/dim]")

    # 4. post-check — did improve regress memory?
    post = await evals.run_evals(dataset=dataset)
    _print(evals.render_report(post))
    if post["green"]:
        _print("[green]improve() gate: PASS — improve accepted, suite still green.[/green]")
        return 0

    # improve made it red → block the change & fail (no PR is opened upstream).
    _print(
        "[red]improve() gate: FAIL — improve regressed the eval suite. "
        "Blocking the change (non-zero exit → no PR).[/red]"
    )
    restore = getattr(brain, "restore_snapshot", None)
    if callable(restore):
        try:
            await restore(dataset=dataset, path=pre_snap_path)
            _print(f"[yellow]rolled back to pre-improve snapshot: {pre_snap_path}[/yellow]")
        except Exception as exc:  # pragma: no cover - defensive
            _print(
                f"[red]automatic rollback failed ({exc!r}); restore manually "
                f"from {pre_snap_path}[/red]"
            )
    else:
        _print(
            f"[yellow]no in-process restore hook; roll back manually from "
            f"{pre_snap_path}[/yellow]"
        )
    return 1
