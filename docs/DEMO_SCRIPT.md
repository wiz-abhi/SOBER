# SOBER — 2-minute demo video script

Three acts, one continuous screen recording of a terminal + a GitHub PR tab.
Uses only proven flows. Voiceover in **bold**, on-screen actions in `code`.

**Recording checklist (beat the Gemini daily cap):**
- Pre-build the brain BEFORE recording so no cognify happens on camera:
  `brain build` (and `brain build --include retracted` for Act 1's "before" state).
- Snapshots `v1`/`v2` should already exist so `brain diff` is instant and keyless.
- Everything shown on camera (`test`, `revert`, `diff`, `bisect` over pre-built batches) is
  **keyless** (CHUNKS recall = local fastembed) — it runs fast and spends zero quota.
- Terminal: large font, dark theme, clear the scrollback between acts.

---

## Cold open (0:00–0:12)

**"Every on-call shift is a hangover. Something's broken, and nobody remembers how it got fixed last time. We fixed that for code with CI/CD. Your agent's memory? It still has none of it."**

`# SOBER — CI/CD for Agent Brains`

---

## Act 1 — Forbidden knowledge & surgical forget (0:12–0:50)

**"Here's an agent's brain built from our runbooks. Someone ingested a production launch code that should never be recallable. Watch memory CI catch it."**

```
brain test
```
→ on screen: **🔴 FAIL — 6/11**, the `forbidden` rows red: the secret leaks across paraphrase probes, and the `structure` eval flags it as graph residue.

**"A leak fails the build — just like a failing test. Now retract it."**

```
brain revert brain__retracted
brain test
```
→ **🟢 PASS — 11/11**. **"Gone. Unrecallable across every probe — and every runbook fact still intact."**

```
brain diff --dataset brain
```
→ **🔴 16 nodes / 32 edges removed.** **"That's the retracted subgraph, and nothing else. A forget-regression test — a guarantee no other memory tool ships."**

---

## Act 2 — Bisect a poisoned brain (0:50–1:25)

**"A pull request adds a doc with plausible but dangerous advice — 'flush the entire Redis cache on every deploy.' The brain is now poisoned. Which ingestion did it?"**

```
brain test
```
→ **🔴** the `no-cache-flush-advice` forbidden eval is red.

**"git bisect, but for memory."**

```
brain bisect --failing-eval no-cache-flush-advice
```
→ on screen: the probe trace — `prefix 5 green → 7 red → 6 red` — **culprit: bisectbrain__b06, found in 4 probes, not 8.**

```
brain revert bisectbrain__b06
brain test
```
→ **🟢 green.** **"Localized in O(log n), reverted surgically, brain healthy again."**

---

## Act 3 — The brain that ships itself (1:25–2:00)

**"The best part: memory that upgrades itself — safely."**

Cut to the GitHub **Actions / PR** tab.

**"Every night, SOBER runs cognee.improve() to distill real sessions into the graph — but only behind a green gate. It runs the evals before, improves, runs them after. If improve regressed anything, the change is blocked and no PR opens."**

Show the nightly PR: title **🌙 Nightly brain self-improvement**, body = the graph diff + **before/after eval scores**.

**"When it clears the gate, the brain opens its own pull request — diff and before/after scores in the body — for a human to merge. That's the CD half of CI/CD for agent brains."**

Close on the README title card:

**"SOBER. Version, test, diff, bisect, and deploy your agent's memory like any other build artifact. Your brain can't merge a regression anymore."**

---

## One-liner for the submission form / socials

> Your agent's memory is production infrastructure with no tests, no diff, no rollback. **SOBER** is CI/CD for agent brains: forget-regression tests that prove a retracted secret stays gone, `git bisect` for a poisoned graph, and a nightly `improve()` that opens its own pull request behind a green gate. Built on Cognee. #WeMakeDevs
