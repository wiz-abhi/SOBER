# SOBER — submission handoff

Everything needed to finish and submit. Deadline: **July 5, 2026**.

## One-liner (for the form)

> **SOBER — CI/CD for Agent Brains.** Your agent's memory is production infrastructure with no tests, no diff, no rollback. SOBER wraps a Cognee knowledge graph in real CI/CD: forget-regression tests that prove a retracted secret stays gone, `git bisect` for a poisoned graph, and a nightly `improve()` that opens its own pull request behind a green eval gate.

## Tech stack

Python 3.11 · Cognee 1.2.2 (self-hosted) · Gemini 2.5 Flash-Lite (LLM) · fastembed (local embeddings) · Typer + Rich (CLI) · GitHub Actions. Zero-config local stores (ladybug graph DB + LanceDB + SQLite).

## Proof status (be honest in the writeup — it builds credibility)

| Capability | Status |
|---|---|
| Forbidden-knowledge → surgical forget (core loop) | ✅ **Proven live** — 🔴 6/11 → `forget` → 🟢 11/11; diff = 16 nodes / 32 edges removed |
| `brain` CLI (10 commands, exit codes) | ✅ Proven live |
| Snapshot / diff / export | ✅ Proven live |
| `brain bisect` (O(log n) culprit search) | ✅ Logic proven offline; live ingest path confirmed (blocked only by 20/day quota) |
| CI-gated `improve()` decisions | ✅ Logic proven offline |
| GitHub Actions (PR gate + nightly PR) | ✅ Built & YAML-valid (runs on GitHub) |
| Cloud canary (push/serve) | ⏳ Designed, not yet demonstrated |

## To finish (human steps)

### 1. Push to GitHub (public — required for judging)
```bash
cd sober
gh repo create sober --public --source=. --remote=origin --push
```
Then in the repo settings → Secrets → Actions, add **`LLM_API_KEY`** so the workflows can run. (The `.env` with your key is gitignored and will NOT be pushed — good.)

### 2. Record the 2-minute video
Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md). **Pre-build the brain state before recording** so no cognify happens on camera — every on-camera command (`test`, `revert`, `diff`, `bisect`) is keyless and re-runnable for free. Building the demo state needs more than 20 Gemini calls, so either enable billing on the Google project (stays free at this volume) or build it across two days on the free cap.

### 3. Publish the blog (Best Blogs side track — Keychron)
[BLOG.md](BLOG.md) is ready — add the repo link and post to dev.to / Hashnode, tag @wemakedevs + Cognee.

### 4. Cloud track (Best Cognee Cloud Use — iPhone)
Redeem the `COGNEE-35` code for a free Cloud dev plan, then `cognee.push(dataset="brain")` to sync the brain and screenshot the graph in the Cloud dashboard. Wire a "Sync to cloud" path and mention `push()`/`serve()` in the submission.

### 5. Submit
Confirm the submission portal in the **WeMakeDevs Discord** (not published on the rules page as of build time). Include: repo link, video link, blog link, and the **AI-assistance disclosure** (below) — omitting it is disqualification.

## AI-assistance disclosure (paste into the form)

> This project was built with Claude Code (Anthropic) as an AI pair programmer — idea selection, scaffolding, module implementation, and documentation. All architecture decisions and the Cognee integration approach are the author's, and every result described as "proven" was executed and verified against the real Cognee + Gemini stack, not generated.

## Judging-criteria mapping (for the writeup)

- **Impact** — agent memory is production infra with no ops layer; SOBER supplies it.
- **Creativity** — DevOps *for* memory; forget-regression tests and memory-bisect are novel.
- **Technical** — full lifecycle (add/cognify/search/forget/improve/export), family-dataset architecture for surgical forget, O(log n) bisect.
- **Best use of Cognee** — every memory verb is load-bearing, including the rarely-used `forget()` and `improve()`; deep integration, not a vector-store bolt-on.
- **UX** — one `brain` command; rich tables; red/green CI exit codes.
- **Presentation** — README, 2-min scripted video, blog, honest limitations.
