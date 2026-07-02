# SOBER — internal build contract (single source of truth)

SOBER = **CI/CD for Agent Brains**. A `brain` CLI + GitHub Action that treats a
Cognee knowledge graph as a versioned, testable, revertable, deployable artifact.

All modules live in the `sober/` Python package. Python 3.11, cognee 1.2.2, all
cognee APIs are **async**. Build against the interfaces below — they are frozen.

## Verified Cognee API facts (tested on this machine — trust these)

Environment setup (every entry point must do this before importing cognee):
```python
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # adjust depth as needed
os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
```
`.env` already sets: `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini/gemini-2.5-flash`,
`LLM_API_KEY=...`, `LLM_RATE_LIMIT_ENABLED=true`, `LLM_RATE_LIMIT_REQUESTS=8`,
`EMBEDDING_PROVIDER=fastembed`.

Core calls (all `await`ed):
- `cognee.add(text_or_path: str, dataset_name: str, node_set: list[str] | None = None)`
- `cognee.cognify(datasets=[dataset_name])` — LLM entity extraction + graph build. COSTS Gemini calls.
- `cognee.search(query_text=q, query_type=SearchType.CHUNKS, datasets=[name], top_k=5)`
  → returns `list[dict]`; each dict has a `"text"` key (the chunk text) plus
  `id`, `document_id`, `document_name`, `belongs_to_set`, `feedback_weight`, `importance_weight`.
  `from cognee import SearchType`. Other useful types: `GRAPH_COMPLETION` (LLM answer), `CHUNKS` (raw, no LLM at query time).
- `cognee.forget(dataset=name, memory_only=True)` → removes recall. VERIFIED: a planted
  secret goes from recallable to `[]` after this. This is SOBER's load-bearing primitive.
  Also: `cognee.forget(data_id=UUID, dataset_id=UUID, memory_only=True)` for single-item.
- `cognee.export(dataset=name, format="json", destination=path)` → writes JSON file, returns
  `ExportResult(format, destination, dataset, nodes:int, edges:int)`.
- `cognee.prune.prune_data()` then `cognee.prune.prune_system(metadata=True)` → full reset.
- `cognee.improve(dataset=name, session_ids=[...])` — distills sessions into graph. COSTS Gemini calls.

Export JSON shape (what `brain diff` parses):
```json
{
  "nodes": [{"id","name","type","text","belongs_to_set","feedback_weight","importance_weight","metadata", ...}],
  "edges": [{"source","target","relationship_name","edge_object_id","feedback_weight","edge_text"}]
}
```
Node `type` ∈ {Entity, EntityType, TextSummary, DocumentChunk, TextDocument}.
Edges are identified by (`source`,`target`,`relationship_name`). Node identity = `id` (stable
UUID5 derived from content) OR `name`+`type` for entities.

## Module interfaces (FROZEN — code to these signatures)

### `sober/config.py`
- `load_env() -> None` — loads .env + sets CACHING/ACCESS_CONTROL defaults. Idempotent.
- Constants: `SNAP_DIR: Path` (= repo/snapshots), `KNOWLEDGE_DIR`, `EVALS_DIR`, `REPO_ROOT`.
- `DATASET_DEFAULT = "brain"`.

### `sober/brain.py` — thin async wrapper over cognee (the ONE place that imports cognee)
- `async def ingest(source: str, dataset: str = "brain", node_set: list[str] | None = None) -> dict`
  — add + cognify one text string or file path. Returns `{"dataset","node_set","chars"}`.
- `async def ingest_batch(sources: list[str], dataset: str, node_set: str) -> dict` — add many under one node_set, cognify once.
- `async def recall(query: str, dataset: str = "brain", top_k: int = 5, graph: bool = False) -> list[dict] | str`
  — CHUNKS search by default (returns list of {text,...}); if graph=True use GRAPH_COMPLETION (returns str).
- `async def forget(dataset: str = "brain", node_set: str | None = None, memory_only: bool = True) -> dict`
  — if node_set given, forget only that scope (see note); else whole dataset. Returns summary dict.
- `async def export_json(dataset: str, destination: str | Path) -> dict` — returns `{"nodes":int,"edges":int,"path":str}`.
- `async def reset() -> None` — prune_data + prune_system.
- NOTE on node-set-scoped forget: cognee's `forget` is dataset/data_id scoped. For node_set scope,
  document the approach: keep each ingestion batch in its OWN dataset named `f"{dataset}__{node_set}"`
  so forget(dataset=that) is surgical. `brain.py` should implement this convention so callers pass a
  logical dataset + node_set and it maps to physical datasets. Provide `physical_dataset(dataset, node_set) -> str`.

### `sober/snapshot.py` — PURE (no cognee import; operates on JSON on disk)
- `def snapshot_path(dataset: str, version: int | str) -> Path` — `snapshots/{dataset}_v{version}.json`.
- `def latest_version(dataset: str) -> int` — highest existing version, 0 if none.
- `async def take_snapshot(dataset: str, label: str | None = None) -> Path` — calls `brain.export_json`
  into `snapshots/`, writes a sidecar `.meta.json` ({version,label,ts_placeholder,nodes,edges}).
  (Import brain lazily inside the function to keep the module pure/testable.)
- `def load_snapshot(path: str | Path) -> dict` — returns `{"nodes":[...],"edges":[...]}`.

### `sober/diff.py` — PURE (no cognee; operates on two snapshot dicts)
- `def diff_graphs(a: dict, b: dict) -> dict` — returns:
  `{"nodes_added":[...], "nodes_removed":[...], "nodes_changed":[{"id","field","from","to"}],
    "edges_added":[...], "edges_removed":[...], "summary":{"nodes_added":n,...}}`.
  Node identity: prefer `id`; fall back to (`name`,`type`). Edge identity: (`source`,`target`,`relationship_name`).
  "changed" tracks `text`, `feedback_weight`, `importance_weight` deltas on matched nodes.
- `def render_markdown(diff: dict, title: str = "Brain diff") -> str` — GitHub-PR-comment-ready markdown
  with a summary table and collapsible <details> lists. Must be legible and emoji-tasteful (🟢 added / 🔴 removed / ✏️ changed).

### `sober/evals.py` — the memory CI suite (depends on brain interface)
- Eval specs are YAML files in `evals/` with this schema:
  ```yaml
  name: must-know
  kind: must_know | forbidden | structure
  cases:
    - query: "what is the incident runbook for db outage"   # must_know/forbidden
      expect_contains: "failover to replica"                 # must_know: recall MUST contain
      forbid_contains: "BRAVO-DELTA-9917"                    # forbidden: recall MUST NOT contain
    - assert: "no_edge_between"                              # structure
      params: {type_a: "DocumentChunk", type_b: "Secret"}
  ```
- `def load_specs(path: Path = EVALS_DIR) -> list[Spec]`
- `async def run_evals(dataset: str = "brain", specs=None) -> EvalReport` where
  `EvalReport = {"passed":int,"failed":int,"total":int,"green":bool,"cases":[{"name","kind","query","status","detail"}]}`.
  - must_know: `recall(query)` text must contain `expect_contains` (case-insensitive) → else fail.
  - forbidden: `recall(query)` text must NOT contain `forbid_contains` → else fail (a LEAK).
    Also run a few paraphrase probes per forbidden case (hardcode 2-3 paraphrase templates).
  - structure: load latest snapshot JSON, assert graph structure (e.g. no edge connects a node of
    type_a to type_b; no node text matches a forbidden regex).
- `def render_report(report: EvalReport) -> str` — red/green markdown + a one-line PASS/FAIL banner.
- CLI exit contract: green → exit 0, red → exit 1.

### `sober/bisect.py` — depends on brain + evals
- `async def bisect(dataset: str, batch_datasets: list[str], failing_eval: str) -> dict`
  — `batch_datasets` are the physical per-batch datasets in ingestion order. Binary-search: for a
  candidate prefix, build a temp combined view / re-run the failing eval, narrow to the single batch
  that flips the eval red→... Actually simpler & robust: given ordered batches each in its own dataset,
  run the failing eval against cumulative prefixes (dataset lists) using O(log n) probes, return
  `{"culprit_dataset":name,"probes":int,"steps":[...]}`. Document the search precisely in a docstring.
- `async def revert(culprit_dataset: str, memory_only: bool = True) -> dict` — `brain.forget` the culprit.

### `sober/ci.py` — orchestration entry used by CLI + GitHub Action
- `async def ci_check(dataset: str = "brain") -> int` — take snapshot, diff vs previous snapshot,
  run evals, print markdown report + diff, write `ci_report.md` to repo root, return 0/1 exit code.
- `async def ci_gate_improve(dataset: str, session_ids: list[str]) -> int` — run evals BEFORE improve;
  only call `brain`/`cognee.improve` if green; re-run evals AFTER; if improve made it red, revert &
  fail. This is the "CI gates improve()" story.

### `sober/cli.py` — Typer app, entry point `brain`
Commands (thin — delegate to the modules above; each wraps async with `asyncio.run`):
- `brain ingest <path-or-text> [--dataset brain] [--node-set NAME]`
- `brain build [--dataset brain] [--include SUBDIR] [--reset/--no-reset]`  (rebuild brain from knowledge/ corpus + snapshot)
- `brain snapshot [--dataset brain] [--label TEXT]`
- `brain diff [--dataset brain] [--from vN] [--to vM]`  (defaults: previous vs latest)
- `brain test [--dataset brain]`  → runs evals, red/green exit code
- `brain ci [--dataset brain]`  → snapshot → diff → evals → write ci_report.md → exit 0/1 (the PR gate)
- `brain revert <culprit-dataset>`
- `brain bisect --failing-eval NAME`  (NAME must be a `forbidden`-kind eval)
- `brain improve --session S1 [--session S2]`  (CI-gated; spans the whole family)
- `brain reset`
Use `rich` for pretty tables. Every command prints a clear human summary.

## Rules for builders
- ONLY import cognee inside `sober/brain.py` (and `sober/ci.py` may call improve via brain). All other
  modules stay cognee-free so they unit-test without the API.
- DO NOT call `cognee.cognify`, `cognee.search`, or `cognee.improve` against the live API in your work —
  it burns the shared Gemini free-tier budget. Validate with `python -c "import sober.X"` import checks
  and synthetic JSON fixtures only. Integration against the live API is done separately.
- Match the signatures above exactly so modules compose. Add docstrings. Keep it clean and readable.
- Windows + PowerShell host; use `pathlib`, never hardcode `/tmp` or POSIX-only paths.
