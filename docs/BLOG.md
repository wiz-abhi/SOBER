# I gave my agent's memory a CI/CD pipeline

*Building SOBER for the Cognee × WeMakeDevs "Where's My Context?" hackathon.*

Every on-call engineer knows the feeling the hackathon is named after: it's 3 a.m., something is broken, and nobody remembers how it got fixed last time. We solved that for *code* decades ago — version control, tests, code review, rollback, canary deploys. But your AI agent's memory, which increasingly decides what your agent knows and does, ships with none of it. It mutates in place, silently, with no test to stop a bad fact and no way to see what changed.

So I built **SOBER — CI/CD for Agent Brains**: a `brain` CLI and GitHub Action that treats a [Cognee](https://github.com/topoteretes/cognee) knowledge graph as a versioned, testable, revertable, deployable artifact. Not memory *for* DevOps — DevOps *for* memory.

## Picking the idea (the honest part)

I didn't arrive at SOBER on the first try. My first instinct was an incident-memory copilot — an on-call assistant that recalls past outages. It felt strong until I pressure-tested it: WeMakeDevs is a DevOps community, so "3 a.m. incident memory" is the single most *predictable* thing to build for that audience, and to Cognee's own engineers it reads as their past "Company Brain" hackathon winner with the nouns swapped. It would have drowned in a sea of look-alikes.

The winning reframe came from asking a different question: not "what memory app should I build?" but "what does memory-the-category still lack?" Answer: the entire operations layer. Every other entry would *use* Cognee to remember things. SOBER governs the remembering itself — and in doing so it exercises the one Cognee verb nobody demos: **`forget()`**.

## What it actually does

Three capabilities, each a test a normal suite can't write:

**1. Forget-regression tests.** A production launch code gets ingested, then retracted. SOBER's memory-CI suite proves it's gone — not just from the obvious query, but across paraphrase probes and as residue in the exported graph. On the real stack: `brain test` goes **🔴 6/11** (the secret leaks), I run `brain revert`, and it flips to **🟢 11/11** while every legitimate runbook fact survives. `brain diff` shows exactly 16 nodes and 32 edges removed — the retracted subgraph, and nothing else. A retracted fact that *stays* retracted, proven on every change. No other memory tool ships that guarantee.

**2. `brain bisect` — git-bisect for a poisoned brain.** When an eval goes red, some ingestion batch did it. SOBER binary-searches the ingestion history and pins the culprit in O(log n) probes — eight batches localized in four — then `brain revert` surgically forgets just that one.

**3. A brain that ships itself.** `cognee.improve()` distills chat sessions into the graph, but that's a silent mutation that can regress memory. SOBER only runs it behind a green gate: evals before, improve, evals after — and if anything regressed, the change is blocked and no PR opens. When it clears, the nightly Action opens a pull request whose body is the graph diff plus before/after eval scores, for a human to merge. Memory that proposes its own upgrades.

## The hardest technical moment

The entire pitch rests on one assumption: that `cognee.forget()` genuinely removes a fact from recall, not just hides it. If forgetting left vector residue, the whole forget-regression story collapses. So the very first thing I did — before writing a single feature — was a gate test: plant a secret, confirm it's recallable, `forget()`, confirm it's gone. It passed cleanly: recallable → `[]`. That one green check is what made the rest worth building.

The subtler problem was *surgical* forgetting. Cognee's `forget` is dataset-scoped, but I needed to retract one batch without disturbing the rest of the brain. The fix was to model a logical "brain" as a **family** of physical datasets — one per node-set — so recall and snapshot span the whole family while `forget(node_set)` drops exactly one member. That indirection is what makes both retraction and bisect-revert precise.

And then there was the quota war. Gemini's free tier on an unbilled key turned out to be *20 requests per day* — I burned through it proving the core loop and spent the rest of the build validating the bisect and gating logic with deterministic offline harnesses instead. A good reminder that the interesting engineering is often in working *around* the constraint, not through it.

## Building with a fleet of agents

I built this with Claude Code as a pair programmer, and leaned into it hard: after nailing down the real Cognee API surface with a few validation gates, I wrote a frozen interface contract and fanned out seven agents in parallel — one per module (the wrapper, snapshot/diff, the eval suite, bisect, the CLI, the corpus, the workflows) — then an eighth to integrate and import-check the assembly. It caught its own wiring bugs. The whole package came together in one parallel pass, and I spent my time on the thing that mattered: validating behavior against the live stack.

*(Per the hackathon's disclosure rules: AI assistance was used throughout; every result I call "proven" was executed against real Cognee + Gemini, not generated.)*

## What's next

Cloud canary deploys via `cognee.push()`/`serve()`, and a real in-process snapshot restore so a regressing `improve()` auto-rolls-back instead of just blocking. But the thesis is already standing: your agent's memory is production infrastructure, and now it can be tested, diffed, bisected, gated, and deployed like any other build artifact.

Your brain can't merge a regression anymore.

**Repo:** *(link)* · Built on [Cognee](https://github.com/topoteretes/cognee) for [The Hangover Part AI](https://www.wemakedevs.org/hackathons/cognee).
