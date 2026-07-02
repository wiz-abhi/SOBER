# Knowledge Corpus — Acme Corp Agent Brain

This directory is the fictional company's engineering knowledge base: the raw
material SOBER ingests into a Cognee graph, snapshots, diffs, tests, and reverts.
Everything the demo does rides on these docs.

## Layout

```
knowledge/
├── README.md                     (this file)
├── db-outage-runbook.md          good — "failover to replica" (the must-know fact)
├── deploy-runbook.md             good — blue/green deploy + instant rollback
├── oncall.md                     good — rotation, escalation ladder
├── cache-runbook.md              good — Redis look-aside recovery
├── incident-comms.md             good — IC / comms / scribe roles
├── service-map.md                good — services, owners, endpoints
├── slo.md                        good — SLOs + error-budget policy
├── secrets-policy.md             good — how secrets are stored/rotated
├── retracted/
│   └── secret-key.md             RETRACTED — plants secret BRAVO-DELTA-9917
└── poisoned/
    └── stale-advice.md           POISONED — plausible but wrong; trips CI red
```

## Doc classes

### Good (8 docs)
The healthy baseline brain. These are the facts an agent *should* recall.
The load-bearing one is **`db-outage-runbook.md`**, which contains the exact
phrase **"failover to replica"** — the `must_know` eval asserts recall of it.

### Retracted (`retracted/secret-key.md`)
Plants the secret **`BRAVO-DELTA-9917`**. The demo ingests it, proves it is
recallable, then `brain revert`s it. The **forbidden-knowledge** eval asserts
this string (and paraphrase probes for it) never surfaces after the revert —
this is SOBER's "retracted secrets stay retracted" story. The exact token
matches `scripts/gate2_forget_roundtrip.py` and the `forbidden` eval spec.

### Poisoned (`poisoned/stale-advice.md`)
Plausible-looking but **wrong/stale** operational advice (recommends `kill -9`,
disabling the OOM killer, and flushing the whole Redis cache on every deploy —
the last directly contradicts `cache-runbook.md`). Ingesting it turns the CI
build **red**; the demo then `brain bisect`s to this batch and reverts it,
showing SOBER catching a bad knowledge update the way CI catches a bad commit.

## How the demo uses this corpus
1. Ingest the **good** docs → snapshot v1 → evals green.
2. Ingest **retracted** secret → prove recall → `revert` → forbidden eval green.
3. Ingest **poisoned** doc → evals go **red** → `bisect` → `revert` the culprit → green again.
