# Does memory-CI catch what plain RAG can't?

A small, reproducible study behind SOBER's core claim: **an agent memory with
tests + `forget()` catches and removes a leaked secret that a plain vector store
(the way most RAG apps use Cognee) surfaces forever, undetected.**

All numbers below are from the **real** Cognee 1.2.2 + Gemini + fastembed pipeline
(see `scripts/demo_core.py` / `scripts/build_golden.py`). The evaluation is
**keyless and deterministic** — recall is local fastembed and the checks are
exact-match, so anyone can reproduce it with `brain test`.

## Setup

- **Corpus:** 5 ops runbooks (db-outage, cache, deploy, on-call, service-map) +
  1 **retracted** document containing a production launch code `BRAVO-DELTA-9917`.
- **Brain:** ingested and cognified into a hybrid graph (the retracted document
  contributes a 16-node / 32-edge subgraph).
- **Memory-CI suite:** 11 checks —
  - 5 `must_know` (a runbook fact must be recallable),
  - 3 `forbidden` (the secret must **not** be recallable; each is probed with the
    literal query **plus 3 paraphrase templates** → 12 adversarial probes),
  - 3 `structure` (the secret must not survive as node text in the exported graph).
- **Baseline — "plain RAG":** the same fastembed vector recall with **no memory
  test and no forget** — i.e. what a typical RAG-on-Cognee app does.

## Results

| State | must_know | forbidden (leak) | structure | overall |
|---|:--:|:--:|:--:|:--:|
| **Secret present** | 5/5 ✓ | **0/3 ✗** — secret leaks on every probe | 1/3 ✗ — residue in graph | 🔴 **6/11** |
| **After `forget(node_set="retracted")`** | 5/5 ✓ | **3/3 ✓** — 0/12 probes leak | 3/3 ✓ — no residue | 🟢 **11/11** |

- **Leak rate across 12 adversarial paraphrase probes: 12/12 → 0/12.**
- **`brain diff`: 16 nodes / 32 edges removed** (exactly the retracted subgraph);
  all 5 runbook facts remain recallable (must_know stays 5/5 — no collateral loss).
- The `forget()` primitive itself was verified at the vector level: a planted
  secret goes from recallable to `[]` (see `scripts/gate2_forget_roundtrip.py`).

## Why plain RAG can't do this

| Capability | Plain RAG / vector store | SOBER |
|---|:--:|:--:|
| Retrieve a fact | ✅ | ✅ |
| **Detect** a leaked/retracted secret | ❌ no test exists | ✅ forbidden-knowledge eval → red build |
| **Remove** it from recall | ❌ can't forget | ✅ `forget(memory_only)` → 0/12 leak |
| **Prove** it's gone | ❌ | ✅ re-test + graph-residue check |
| Catch a later regression | ❌ | ✅ must_know evals stay green |

A plain vector store retrieves the secret on the same probes (same embeddings),
has no mechanism to detect that it's a leak, and no mechanism to remove it — so
the leak is **permanent and silent**. SOBER's contribution isn't better recall;
it's the **governance layer**: test it, forget it, prove it, and keep proving it
on every change.

## Methodology & honesty

- This is a **focused, deterministic case study**, not a large-N benchmark. Its
  strength is reproducibility: keyless recall + exact-match checks mean the same
  inputs give the same 6/11 → 11/11 every run (no LLM-judge variance).
- "Plain RAG" here is the *no-governance* control (retrieve-only), which is
  precisely the gap SOBER targets — not a claim that RAG retrieval is bad.
- `forget()` deletes the corpus/graph/vectors, not a model's parametric priors;
  the claim is about the *memory store*, verified behaviourally by the leak probes.

## Reproduce

```bash
pip install -e .            # + a Gemini key in .env
python scripts/demo_core.py # ingest → 🔴 6/11 → forget → 🟢 11/11 → diff 16n/32e
brain test                  # re-run the keyless eval suite any time
```
