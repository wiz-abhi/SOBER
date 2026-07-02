"""SOBER command-line interface — the ``brain`` command developers run.

This is the thin presentation layer. Every command delegates to the async
module functions defined elsewhere in the ``sober`` package, wraps them with
:func:`asyncio.run`, and renders a clean ``rich`` summary. No business logic
lives here.

Design contract (see CONTRACT.md):

* ``sober.cli`` must import — and print ``--help`` — WITHOUT touching the
  Cognee API or the LLM. Cognee is only ever imported by ``sober.brain``.
  To keep it that way, every heavy sibling module (``brain``, ``snapshot``,
  ``diff``, ``evals``, ``bisect``, ``ci``) is imported *lazily inside the
  command body*, never at module top level. Importing this file therefore
  loads only Typer + Rich + stdlib.
* ``brain test`` exits ``0`` when the eval suite is green and ``1`` when red,
  so it can gate CI.

Entry point: ``brain = "sober.cli:app"`` (declared in pyproject.toml).
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# NOTE: sibling sober modules (brain/snapshot/diff/evals/bisect/ci) and
# sober.config are imported lazily inside each command so that merely importing
# this CLI — or running ``brain --help`` — never imports cognee or hits the API.

app = typer.Typer(
    name="brain",
    help="SOBER — CI/CD for Agent Brains. Version, test, diff, revert and "
    "deploy a Cognee knowledge graph like any other build artifact.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

# --------------------------------------------------------------------------- #
# Shared option definitions (kept identical across commands for consistency).
# --------------------------------------------------------------------------- #
_DATASET_OPT = typer.Option(
    "brain",
    "--dataset",
    "-d",
    help="Logical dataset (brain) to operate on.",
)


# --------------------------------------------------------------------------- #
# Small rendering helpers
# --------------------------------------------------------------------------- #
def _kv_table(title: str, rows: dict) -> Table:
    """Render a simple two-column key/value table."""
    table = Table(title=title, show_header=False, title_justify="left", expand=False)
    table.add_column("field", style="bold cyan", no_wrap=True)
    table.add_column("value", style="white")
    for key, value in rows.items():
        table.add_row(str(key), str(value))
    return table


def _die(message: str, code: int = 1) -> None:
    """Print an error panel and abort with the given exit code."""
    console.print(Panel(Text(message, style="bold red"), title="error", border_style="red"))
    raise typer.Exit(code)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def ingest(
    source: str = typer.Argument(
        ...,
        help="Text string to remember, or a path to a file to ingest.",
    ),
    dataset: str = _DATASET_OPT,
    node_set: Optional[str] = typer.Option(
        None,
        "--node-set",
        "-n",
        help="Logical scope/tag for this batch (enables surgical forget/bisect).",
    ),
) -> None:
    """Add + cognify a text string or file into the brain.

    Wraps ``brain.ingest`` (add + cognify). This DOES call the live Cognee /
    LLM pipeline.
    """
    from sober import brain, config

    config.load_env()

    node_sets: Optional[List[str]] = [node_set] if node_set else None
    with console.status(f"[bold]ingesting into '{dataset}'…", spinner="dots"):
        result = asyncio.run(brain.ingest(source, dataset=dataset, node_set=node_sets))

    console.print(_kv_table("ingested", result))
    console.print(f"[green]✓[/green] ingested into [bold]{dataset}[/bold]")


@app.command()
def snapshot(
    dataset: str = _DATASET_OPT,
    label: Optional[str] = typer.Option(
        None,
        "--label",
        "-l",
        help="Human label recorded in the snapshot's sidecar metadata.",
    ),
) -> None:
    """Export the current graph and version it under ``snapshots/``.

    Wraps ``snapshot.take_snapshot`` — exports the dataset to
    ``snapshots/{dataset}_v{N}.json`` and writes a ``.meta.json`` sidecar.
    """
    from sober import config, snapshot as snap

    config.load_env()

    with console.status(f"[bold]snapshotting '{dataset}'…", spinner="dots"):
        path = asyncio.run(snap.take_snapshot(dataset, label=label))

    version = snap.latest_version(dataset)
    console.print(
        _kv_table(
            "snapshot",
            {
                "dataset": dataset,
                "version": f"v{version}",
                "label": label or "-",
                "path": path,
            },
        )
    )
    console.print(f"[green]✓[/green] snapshot [bold]v{version}[/bold] written")


@app.command()
def diff(
    dataset: str = _DATASET_OPT,
    from_version: Optional[str] = typer.Option(
        None,
        "--from",
        help="Base version, e.g. 'v2' or '2'. Default: the previous snapshot.",
    ),
    to_version: Optional[str] = typer.Option(
        None,
        "--to",
        help="Target version, e.g. 'v3' or '3'. Default: the latest snapshot.",
    ),
    markdown: bool = typer.Option(
        False,
        "--markdown",
        "-m",
        help="Print the raw GitHub-PR-ready markdown instead of a rich table.",
    ),
) -> None:
    """Diff two graph snapshots (added / removed / changed nodes & edges).

    Pure computation — reads snapshot JSON off disk and calls
    ``diff.diff_graphs`` / ``diff.render_markdown``. Does not touch the API.
    Defaults to ``previous vs latest``.
    """
    from sober import diff as diffmod
    from sober import snapshot as snap

    latest = snap.latest_version(dataset)
    if latest < 1:
        _die(f"no snapshots found for dataset '{dataset}'. Run `brain snapshot` first.")

    to_v = _parse_version(to_version) if to_version else latest
    from_v = _parse_version(from_version) if from_version else max(1, to_v - 1)

    if from_v == to_v:
        _die(f"nothing to diff: base and target are both v{to_v}.")

    a_path = snap.snapshot_path(dataset, from_v)
    b_path = snap.snapshot_path(dataset, to_v)
    for p, v in ((a_path, from_v), (b_path, to_v)):
        if not p.exists():
            _die(f"snapshot v{v} not found at {p}")

    graph_a = snap.load_snapshot(a_path)
    graph_b = snap.load_snapshot(b_path)
    result = diffmod.diff_graphs(graph_a, graph_b)

    title = f"Brain diff — {dataset} v{from_v} → v{to_v}"

    if markdown:
        # Raw markdown, suitable for piping into a PR comment.
        console.print(diffmod.render_markdown(result, title=title))
        return

    _render_diff_table(result, title)


@app.command()
def test(
    dataset: str = _DATASET_OPT,
    markdown: bool = typer.Option(
        False,
        "--markdown",
        "-m",
        help="Print the raw markdown report (as posted to a PR) as well.",
    ),
) -> None:
    """Run the memory CI suite (evals). Exit 0 if green, 1 if red.

    Wraps ``evals.run_evals`` + ``evals.render_report``. This drives the
    forbidden-knowledge / must-know checks; ``must_know`` cases recall via the
    live API, so this can call Cognee.
    """
    from sober import config, evals

    config.load_env()

    with console.status(f"[bold]running evals on '{dataset}'…", spinner="dots"):
        report = asyncio.run(evals.run_evals(dataset=dataset))

    _render_eval_table(report)

    if markdown:
        console.print()
        console.print(evals.render_report(report))

    green = bool(report.get("green"))
    banner = (
        Text(" PASS ", style="bold white on green")
        if green
        else Text(" FAIL ", style="bold white on red")
    )
    summary = Text.assemble(
        banner,
        f"  {report.get('passed', 0)}/{report.get('total', 0)} cases passed",
    )
    console.print(summary)

    raise typer.Exit(0 if green else 1)


@app.command()
def revert(
    culprit_dataset: str = typer.Argument(
        ...,
        help="Physical (per-batch) dataset to forget, e.g. 'brain__runbooks'.",
    ),
    memory_only: bool = typer.Option(
        True,
        "--memory-only/--hard",
        help="Forget recall only (default) vs a harder delete.",
    ),
) -> None:
    """Forget a culprit batch's memory (the 'undo bad ingestion' button).

    Wraps ``bisect.revert`` → ``brain.forget``. Removes recall for the named
    physical dataset.
    """
    from sober import bisect, config

    config.load_env()

    with console.status(f"[bold]reverting '{culprit_dataset}'…", spinner="dots"):
        result = asyncio.run(
            bisect.revert(culprit_dataset, memory_only=memory_only)
        )

    console.print(_kv_table("reverted", result))
    console.print(f"[green]✓[/green] forgot [bold]{culprit_dataset}[/bold]")


@app.command()
def bisect(
    failing_eval: str = typer.Option(
        ...,
        "--failing-eval",
        "-f",
        help="Name of the eval spec that is currently RED.",
    ),
    dataset: str = _DATASET_OPT,
) -> None:
    """Binary-search the ingestion batches to find which one broke an eval.

    Discovers the ordered per-batch physical datasets for ``dataset`` and
    delegates to ``bisect.bisect``. Prints the culprit and the number of
    probes it took (O(log n)).
    """
    from sober import bisect as bisectmod
    from sober import config

    config.load_env()

    batch_datasets = _discover_batch_datasets(dataset)
    if not batch_datasets:
        _die(
            f"no per-batch datasets found for '{dataset}'. Ingest with "
            f"--node-set so batches land in their own physical datasets."
        )

    console.print(
        _kv_table(
            "bisect",
            {
                "dataset": dataset,
                "failing eval": failing_eval,
                "candidate batches": len(batch_datasets),
                "batches": ", ".join(batch_datasets),
            },
        )
    )

    with console.status("[bold]bisecting…", spinner="dots"):
        result = asyncio.run(
            bisectmod.bisect(dataset, batch_datasets, failing_eval)
        )

    culprit = result.get("culprit_dataset")
    probes = result.get("probes")
    table = Table(title="bisect result", show_header=False, title_justify="left")
    table.add_column("field", style="bold cyan")
    table.add_column("value")
    table.add_row("culprit", f"[bold red]{culprit}[/bold red]" if culprit else "[green]none[/green]")
    table.add_row("probes", str(probes))
    console.print(table)

    if culprit:
        console.print(
            f"[yellow]→ suggested fix:[/yellow] "
            f"[bold]brain revert {culprit}[/bold]"
        )


@app.command()
def improve(
    session: List[str] = typer.Option(
        None,
        "--session",
        "-s",
        help="Session id to distill into the graph. Repeat for multiple; "
        "omit to let cognee pick recent sessions.",
    ),
    dataset: str = _DATASET_OPT,
) -> None:
    """Run a CI-gated ``improve()``: only apply if evals stay green.

    Wraps ``ci.ci_gate_improve`` — runs evals BEFORE improve, only calls
    ``improve`` if green, re-runs evals AFTER, and reverts if improve turned
    the suite red. Exits 0 if the improvement was accepted, 1 otherwise.

    ``--session`` is optional: with none given, ``improve`` distills whatever
    recent sessions cognee defaults to (the nightly self-improve path).
    """
    from sober import ci, config

    config.load_env()

    sessions: List[str] = list(session) if session else []
    console.print(
        _kv_table(
            "improve (CI-gated)",
            {"dataset": dataset, "sessions": ", ".join(sessions) or "(recent)"},
        )
    )

    with console.status("[bold]gating improve() on evals…", spinner="dots"):
        code = asyncio.run(ci.ci_gate_improve(dataset, sessions))

    if code == 0:
        console.print("[green]✓ improve accepted — evals stayed green.[/green]")
    else:
        console.print("[red]✗ improve rejected/reverted — evals went red.[/red]")

    raise typer.Exit(code)


@app.command()
def reset(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Wipe ALL Cognee data + system state (prune). Destructive.

    Wraps ``brain.reset`` (``prune_data`` + ``prune_system``).
    """
    from sober import brain, config

    config.load_env()

    if not yes:
        confirmed = typer.confirm(
            "This prunes ALL Cognee data and system metadata. Continue?"
        )
        if not confirmed:
            console.print("[yellow]aborted.[/yellow]")
            raise typer.Exit(0)

    with console.status("[bold]pruning all data + system state…", spinner="dots"):
        asyncio.run(brain.reset())

    console.print("[green]✓[/green] brain reset — all data and system state pruned.")


# --------------------------------------------------------------------------- #
# Internal helpers (pure, cognee-free)
# --------------------------------------------------------------------------- #
def _parse_version(value: str) -> int:
    """Parse a version spec like ``v3``, ``V3`` or ``3`` into an int."""
    text = value.strip().lower().lstrip("v")
    try:
        version = int(text)
    except ValueError:
        _die(f"invalid version '{value}'. Use e.g. 'v3' or '3'.")
    if version < 1:
        _die(f"version must be >= 1 (got '{value}').")
    return version


def _discover_batch_datasets(dataset: str) -> List[str]:
    """Discover ordered per-batch physical datasets for ``dataset``.

    Convention (CONTRACT.md): each ingestion batch lives in its own physical
    dataset named ``f"{dataset}__{node_set}"``. We enumerate the snapshot
    sidecars on disk to find them in a stable, deterministic order.

    This is cognee-free: it only reads the ``snapshots/`` directory listing.
    """
    from sober import config

    prefix = f"{dataset}__"
    seen: dict[str, None] = {}
    snap_dir = config.SNAP_DIR
    if not snap_dir.exists():
        return []
    # Sorted for a deterministic ingestion-order approximation.
    for path in sorted(snap_dir.glob(f"{prefix}*")):
        stem = path.name
        # Strip snapshot suffixes: "brain__foo_v1.json" / ".meta.json".
        for marker in (".meta.json", ".json"):
            if stem.endswith(marker):
                stem = stem[: -len(marker)]
                break
        # Strip the trailing "_v{N}" version tag if present.
        base = stem
        if "_v" in stem:
            head, _, tail = stem.rpartition("_v")
            if tail.isdigit():
                base = head
        if base.startswith(prefix) and base not in seen:
            seen[base] = None
    return list(seen.keys())


def _render_diff_table(result: dict, title: str) -> None:
    """Render a diff dict as a rich summary table."""
    summary = result.get("summary", {})

    table = Table(title=title, title_justify="left")
    table.add_column("change", style="bold")
    table.add_column("count", justify="right")
    table.add_row("🟢 nodes added", str(summary.get("nodes_added", len(result.get("nodes_added", [])))))
    table.add_row("🔴 nodes removed", str(summary.get("nodes_removed", len(result.get("nodes_removed", [])))))
    table.add_row("✏️  nodes changed", str(summary.get("nodes_changed", len(result.get("nodes_changed", [])))))
    table.add_row("🟢 edges added", str(summary.get("edges_added", len(result.get("edges_added", [])))))
    table.add_row("🔴 edges removed", str(summary.get("edges_removed", len(result.get("edges_removed", [])))))
    console.print(table)

    total_changes = sum(
        len(result.get(k, []))
        for k in ("nodes_added", "nodes_removed", "nodes_changed", "edges_added", "edges_removed")
    )
    if total_changes == 0:
        console.print("[dim]no changes between these snapshots.[/dim]")
    else:
        console.print("[dim]run with --markdown for the full PR-ready diff.[/dim]")


def _render_eval_table(report: dict) -> None:
    """Render an EvalReport dict as a red/green rich table."""
    table = Table(title="memory CI — eval results", title_justify="left")
    table.add_column("eval", style="bold")
    table.add_column("kind", style="cyan")
    table.add_column("query", overflow="fold", max_width=48)
    table.add_column("status", justify="center")

    for case in report.get("cases", []):
        status = str(case.get("status", "")).lower()
        if status in ("pass", "passed", "green", "ok"):
            status_cell = "[green]✓ pass[/green]"
        else:
            status_cell = "[red]✗ fail[/red]"
        table.add_row(
            str(case.get("name", "-")),
            str(case.get("kind", "-")),
            str(case.get("query", case.get("detail", "-")) or "-"),
            status_cell,
        )
    console.print(table)


if __name__ == "__main__":
    app()
