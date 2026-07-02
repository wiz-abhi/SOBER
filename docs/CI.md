# SOBER CI/CD — the pipeline that makes a brain self-governing

> Git, pipelines, canary deploys, and Dependabot — for **memory**.

SOBER treats a [Cognee](https://github.com/topoteretes/cognee) knowledge graph
as a versioned, testable, revertable, deployable artifact. This document explains
the two GitHub workflows that turn that idea into an actual pipeline:

| Workflow | Trigger | Job | Story |
| --- | --- | --- | --- |
| [`brain-ci.yml`](../.github/workflows/brain-ci.yml) | PR touching `knowledge/**`, `evals/**`, `sober/**` | run `brain test`, block merge on red, comment the diff + eval report | **memory can't merge a regression** |
| [`brain-nightly.yml`](../.github/workflows/brain-nightly.yml) | nightly cron (+ manual dispatch) | gated `brain improve`, open a PR with graph diff + before/after scores | **the brain that ships itself** |

Everything both workflows call is a thin wrapper around the `brain` CLI
(installed via `pip install -e .`, entry point `sober.cli:app`). CI runs the same
commands you run locally — no bespoke CI-only code path.

---

## 1. The PR check — `brain-ci.yml`

### What runs, and when

The check fires only when a PR changes something the brain actually learns from:

```yaml
on:
  pull_request:
    paths:
      - "knowledge/**"   # the source facts the brain ingests
      - "evals/**"       # the tests that define "a good brain"
      - "sober/**"       # the machinery itself
```

Editing app code or unrelated docs doesn't spend Gemini budget re-testing memory
that didn't move.

### The steps

1. **Checkout + Python 3.11 + `pip install -e .`** — exposes the `brain` console
   script.
2. **`brain test`** — the memory CI suite. Under the hood this is
   `sober.ci.ci_check`: take a snapshot, diff it against the previous snapshot,
   run every eval spec in `evals/`, write `ci_report.md` to the repo root, and
   return **exit 0 (green) / exit 1 (red)**. A red exit fails the job and blocks
   the merge — exactly like a failing unit test.
3. **Upload `ci_report.md`** as an artifact (`if: always()`, so you can download
   the report precisely when the run is red and you want to know why).
4. **Comment on the PR** (`actions/github-script`) — post or update a single
   sticky comment containing the brain diff + eval report, read verbatim from
   `ci_report.md`. We find our previous comment by a hidden `<!-- sober-brain-ci -->`
   marker and edit it in place, so pushing new commits updates one comment
   instead of spamming a new one each time.

The PR comment gives reviewers, inline, the answer to "what did this change do to
the brain?" — which nodes/edges it added, removed, or changed, and whether every
eval is still green.

### Why the diff matters

A knowledge-graph change is not human-readable as a text diff — the ingested
facts become nodes and edges after `cognify()`. `sober.diff.diff_graphs` +
`render_markdown` translate two snapshots into a PR-legible summary
(🟢 added / 🔴 removed / ✏️ changed) so a reviewer can reason about a memory
change the same way they reason about a code change.

---

## 2. The forbidden-knowledge gate

This is the load-bearing test and the reason SOBER exists. The eval suite in
`evals/` is a set of YAML specs; three `kind`s enforce three guarantees:

| `kind` | Guarantee | How it's checked |
| --- | --- | --- |
| `must_know` | The brain still knows what it must | `recall(query)` text **must contain** `expect_contains` (case-insensitive) |
| `forbidden` | A retracted secret stays retracted | `recall(query)` text **must NOT contain** `forbid_contains` — and stays clean under 2–3 **paraphrase probes** |
| `structure` | The graph never wires a leak | static assertion on the latest snapshot JSON, e.g. *no edge connects a `DocumentChunk` to a `Secret`*, no node text matches a forbidden regex |

A `forbidden` case is a **leak test**. Cognee's `forget(dataset=…, memory_only=True)`
is SOBER's load-bearing primitive: a planted secret goes from recallable to `[]`
after forget (verified in [`scripts/gate2_forget_roundtrip.py`](../scripts/gate2_forget_roundtrip.py)).
The forbidden eval proves the retraction *held* — the secret is not recallable by
the obvious query **or** by paraphrases of it — and the structure eval proves the
graph didn't quietly keep an edge that would let the secret resurface after a
future `cognify`.

If a PR would re-introduce a leak — re-adding a retracted secret to `knowledge/`,
or weakening an eval — `brain test` goes red and **the merge is blocked**. Your
agent's memory cannot merge a regression any more than your app code can.

### Why it's cheap in CI

`forbidden` and `structure` evals are **keyless**: forbidden recall uses CHUNKS
(vector-similarity) search with local `fastembed` embeddings and no Gemini call at
query time, and structure evals are static assertions over the snapshot JSON. So
the common PR path — "did this change leak a secret / break the graph shape?" —
costs zero LLM budget. `LLM_API_KEY` is still provided for `must_know` cases and
any `cognify` the suite performs. The rate-limit env vars
(`LLM_RATE_LIMIT_ENABLED`, `LLM_RATE_LIMIT_REQUESTS`, `LLM_RATE_LIMIT_INTERVAL`)
throttle so a burst of Gemini 429s never kills a run on the shared free tier.

---

## 3. The nightly self-improvement PR — `brain-nightly.yml`

> The brain that ships itself.

On a nightly cron (`0 7 * * *` UTC; also runnable via **Run workflow** for demos),
SOBER tries to make the brain smarter and opens a PR for a human to review:

1. **Snapshot the baseline** (`brain snapshot --label nightly-pre-improve`) so
   there's a "from" side to diff and a point to revert to.
2. **Gated `brain improve`** — this is `sober.ci.ci_gate_improve`:
   - run evals **before** improve; abort if already red,
   - call `cognee.improve()` only when green (it distills recent agent sessions
     into the graph — this costs Gemini calls),
   - run evals **after**; if improve regressed anything (a leak, a lost must-know
     fact) it **reverts** (`brain.forget` on the culprit) and exits non-zero.

   A non-zero exit means "no safe improvement tonight" — the job fails and **no PR
   is opened**. A regression never reaches a human.
3. **Diff + before/after report** (`brain test`) — regenerates `ci_report.md` with
   the graph diff (post-improve vs baseline) and the before/after eval scores.
4. **Open the PR** (`peter-evans/create-pull-request`) — commits the new
   `snapshots/**` to the stable `brain/nightly-improve` branch and raises a PR
   whose body **is** the diff + before/after eval report. Re-running updates the
   existing PR rather than stacking duplicates.

The human merges to **deploy** the smarter brain, or closes to reject. That's the
CD half: memory that proposes its own upgrades, behind a green eval gate and a
human approval.

---

## 4. Secrets & configuration

Both workflows read model config from the environment, mirroring
[`.env.example`](../.env.example) so CI matches local runs. The only real secret
is the Gemini key:

| Env var | Source | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | **`${{ secrets.LLM_API_KEY }}`** (repo secret) | Gemini API key — never commit it |
| `LLM_PROVIDER` / `LLM_MODEL` | workflow literal (`gemini` / `gemini/gemini-2.5-flash-lite`) | model selection |
| `EMBEDDING_PROVIDER` | workflow literal (`fastembed`) | local embeddings, no key, no rate limit |
| `LLM_RATE_LIMIT_*` | workflow literals | free-tier 429 protection |
| `CACHING` / `ENABLE_BACKEND_ACCESS_CONTROL` | workflow literals (`false`) | deterministic, no background access (per SOBER contract) |
| `GITHUB_TOKEN` | `${{ secrets.GITHUB_TOKEN }}` (auto-provided) | nightly PR creation |

To set the key up: **Repo → Settings → Secrets and variables → Actions → New
repository secret**, name it `LLM_API_KEY`, paste your Gemini key. The nightly
workflow also needs **Settings → Actions → General → Workflow permissions →
"Read and write"** and **"Allow GitHub Actions to create and approve pull
requests"** so it can open its self-improvement PR.

---

## 5. How canary / Cognee Cloud fits later

Today both workflows run the brain **locally inside the runner** (embedded graph
DB + LanceDB + SQLite, zero-config). The natural Day-2/3 extension is a **deploy**
stage that promotes a green, human-approved brain to
[Cognee Cloud](https://www.cognee.ai/) as a served endpoint — the canary story:

1. **Build** — the same `brain test` gate that guards PRs today.
2. **Canary push** — on merge to `main`, `brain push` (future) exports the
   approved snapshot and pushes it to a Cloud **canary** dataset via
   `COGNEE_SERVICE_URL` / `COGNEE_API_KEY` (already stubbed in `.env.example`).
3. **Shadow-eval on the canary** — re-run the eval suite against the *served*
   canary endpoint, not just the local graph, to catch environment drift. Same
   forbidden-knowledge gate, now against production infrastructure.
4. **Promote** — if the canary stays green, `brain serve` (future) flips the
   canary to the primary served brain; if it goes red, the canary is discarded
   and the previously-served brain keeps serving. Rollback is just re-pointing at
   the last green snapshot.

The pieces already in place make this a small step, not a rewrite: snapshots are
versioned artifacts, evals run against any dataset, and `forget`/`revert` give a
clean rollback primitive. Cloud simply changes *where* the brain is served — the
gate that decides *whether* it ships is the same eval suite this document
describes.
