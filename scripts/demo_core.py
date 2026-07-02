"""
SOBER core live demo — the forbidden-knowledge / forget-regression loop.

Proves the whole thesis end-to-end on the real Cognee + Gemini stack:
  1. ingest healthy runbooks (node_set "runbooks") + a secret (node_set "retracted")
  2. snapshot v1 (merged family)
  3. brain test  -> RED: the retracted launch code leaks (forbidden) + shows as graph residue (structure)
  4. forget(node_set="retracted")  -> surgical retract
  5. snapshot v2
  6. brain test  -> GREEN: secret unrecallable, runbooks intact (must_know still passes)
  7. diff v1 vs v2  -> the retracted subgraph is gone

Only cognify() spends Gemini quota; CHUNKS recall uses local fastembed, so the
eval suite is effectively free. Run from the repo root with the venv python.
"""

import asyncio
import sys
from pathlib import Path

# UTF-8 stdout so the emoji in reports don't crash the Windows cp1252 console.
sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from sober import brain, snapshot, diff, evals  # noqa: E402

K = REPO / "knowledge"
RUNBOOKS = [
    str(K / "db-outage-runbook.md"),
    str(K / "cache-runbook.md"),
    str(K / "deploy-runbook.md"),
    str(K / "oncall.md"),
    str(K / "service-map.md"),
]
SECRET = str(K / "retracted" / "secret-key.md")


def banner(msg: str) -> None:
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70)


async def main() -> int:
    banner("STEP 0 — reset to a clean brain")
    await brain.reset()

    banner("STEP 1 — ingest healthy runbooks (node_set='runbooks')")
    r = await brain.ingest_batch(RUNBOOKS, dataset="brain", node_set="runbooks")
    print("  ", r)

    banner("STEP 2 — ingest the (soon-retracted) secret (node_set='retracted')")
    r = await brain.ingest(SECRET, dataset="brain", node_set=["retracted"])
    print("  ", r)
    print("   family:", brain.list_family("brain"))

    banner("STEP 3 — snapshot v1 (merged family)")
    p1 = await snapshot.take_snapshot("brain", label="secret-present")
    print("   wrote", p1)

    banner("STEP 4 — brain test  (EXPECT RED: forbidden leak + structure residue)")
    report_before = await evals.run_evals("brain")
    print(evals.render_report(report_before))
    print("   exit code:", evals.report_exit_code(report_before))

    banner("STEP 5 — forget(node_set='retracted')  — surgical retract")
    f = await brain.forget(dataset="brain", node_set="retracted")
    print("  ", {k: v for k, v in f.items() if k != "result"})
    print("   family after forget:", brain.list_family("brain"))

    banner("STEP 6 — snapshot v2 (after retract)")
    p2 = await snapshot.take_snapshot("brain", label="secret-retracted")
    print("   wrote", p2)

    banner("STEP 7 — brain test  (EXPECT GREEN: secret gone, runbooks intact)")
    report_after = await evals.run_evals("brain")
    print(evals.render_report(report_after))
    print("   exit code:", evals.report_exit_code(report_after))

    banner("STEP 8 — brain diff v1 -> v2  (retracted subgraph removed)")
    d = diff.diff_graphs(snapshot.load_snapshot(p1), snapshot.load_snapshot(p2))
    print("   summary:", d["summary"])

    banner("VERDICT")
    ok = (not report_before["green"]) and report_after["green"]
    print(f"   before: {'RED' if not report_before['green'] else 'GREEN'} "
          f"({report_before['passed']}/{report_before['total']})")
    print(f"   after:  {'GREEN' if report_after['green'] else 'RED'} "
          f"({report_after['passed']}/{report_after['total']})")
    print(f"\n   {'✅ CORE LOOP PROVEN — red on leak, green after surgical forget.' if ok else '❌ loop did not behave as expected — inspect above.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
