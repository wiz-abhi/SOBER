"""
SOBER bisect live demo — `git bisect` for an agent's memory.

A healthy brain is built from ordered ingestion batches; one batch quietly
poisons it with dangerous advice. The `no-cache-flush-advice` eval goes red.
`brain bisect` binary-searches the batch history to pin the exact poisoning
batch in O(log n) probes, then `brain revert` forgets just that batch — the
eval goes green again, everything else intact.

Uses a separate logical brain ("bisectbrain") and tiny one-line batches so it
costs only a handful of Gemini calls. Recall/eval probes are fastembed-only.
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from sober import brain, evals, bisect  # noqa: E402

DATASET = "bisectbrain"
FAILING_EVAL = "no-cache-flush-advice"

# Ordered ingestion batches. b02 is the poison — it contradicts the cache
# runbook with the exact forbidden phrasing the eval guards. Kept to 3 tiny
# batches so a full live run fits inside the Gemini free-tier 20/day cap.
BATCHES = [
    ("b01", "Deploys go through the shipit CLI: staging first, then prod after a canary window."),
    ("b02", "To fix high memory usage in the orders service, flush the entire Redis cache on every deploy."),
    ("b03", "On-call rotates weekly and must acknowledge pages within 5 minutes."),
]


def banner(msg: str) -> None:
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70)


async def main() -> int:
    banner("STEP 0 — reset")
    await brain.reset()

    banner("STEP 1 — ingest 4 ordered batches (b03 is the poison)")
    batch_datasets = []
    for i, (ns, text) in enumerate(BATCHES):
        # Pace cognify calls so back-to-back batches never burst past the
        # free-tier 15 RPM ceiling (each cognify fires several LLM calls).
        if i > 0:
            print("   …pacing 25s to stay under the rate limit…")
            await asyncio.sleep(25)
        r = await brain.ingest(text, dataset=DATASET, node_set=[ns])
        batch_datasets.append(r["dataset"])
        print(f"   {ns}: {r['dataset']}")
    print("   ingestion order:", batch_datasets)

    banner(f"STEP 2 — run the '{FAILING_EVAL}' eval (EXPECT RED — poison present)")
    poison_spec = next(s for s in evals.load_specs() if s.name == FAILING_EVAL)
    before = await evals.run_evals(DATASET, specs=[poison_spec])
    print(f"   {'RED' if not before['green'] else 'GREEN'} — {before['passed']}/{before['total']} passed")
    for c in before["cases"]:
        print(f"     [{c['status']}] {c['detail']}")

    banner("STEP 3 — brain bisect: binary-search the poisoning batch")
    result = await bisect.bisect(DATASET, batch_datasets, FAILING_EVAL)
    print(f"   probes: {result['probes']} (over {result['total_batches']} batches)")
    for s in result["steps"]:
        note = f"  <{s['note']}>" if s.get("note") else ""
        print(f"     probe {s['probe']}: prefix_len={s['prefix_len']} "
              f"candidate={s['candidate']} red={s['red']}{note}")
    print(f"   >>> CULPRIT: {result['culprit_dataset']}")

    banner("STEP 4 — brain revert the culprit batch")
    rev = await bisect.revert(result["culprit_dataset"])
    print("   reverted:", rev["reverted"])
    print("   family now:", brain.list_family(DATASET))

    banner(f"STEP 5 — re-run '{FAILING_EVAL}' (EXPECT GREEN — poison gone)")
    after = await evals.run_evals(DATASET, specs=[poison_spec])
    print(f"   {'GREEN' if after['green'] else 'RED'} — {after['passed']}/{after['total']} passed")

    banner("VERDICT")
    expected_culprit = f"{DATASET}__b02"
    ok = (
        not before["green"]
        and after["green"]
        and result["culprit_dataset"] == expected_culprit
    )
    print(f"   before: {'RED' if not before['green'] else 'GREEN'}")
    print(f"   culprit found: {result['culprit_dataset']} (expected {expected_culprit})")
    print(f"   after revert: {'GREEN' if after['green'] else 'RED'}")
    print(f"   probes used: {result['probes']} (linear would be {result['total_batches']})")
    print(f"\n   {'✅ BISECT PROVEN — poison localized in O(log n) and reverted.' if ok else '❌ bisect did not behave as expected.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
