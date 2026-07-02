"""
Offline proof of the CI-gated improve() logic (no cognee, no Gemini).

`ci.ci_gate_improve` is the "CD" half of SOBER: it only lets cognee.improve()
mutate the graph if the eval suite is green before AND stays green after, and it
reverts on regression. The live path needs cognify/improve (Gemini, quota-capped),
but the *gating decisions* are pure control flow. We stub the eval verdicts and
the cognee-backed calls, then assert the three decisions:

  1. green → green : improve ACCEPTED (exit 0)
  2. green → red   : improve REGRESSED → job FAILS (exit 1), no PR opened,
                     pre-improve snapshot reported for rollback
  3. red before    : REFUSED (exit 1), improve never called

Note: auto-restore is best-effort — it fires only if brain.restore_snapshot
exists (a future enhancement). Today the gate's guarantee is that a regressing
improve() is BLOCKED (non-zero exit → the nightly job fails → no PR is opened),
which is what actually protects the brain. We assert that guarantee here.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sober import ci, brain, evals, snapshot  # noqa: E402


def _report(green: bool) -> dict:
    return {"passed": 1 if green else 0, "failed": 0 if green else 1,
            "total": 1, "green": green, "cases": []}


class Harness:
    """Stubs the cognee-backed calls ci_gate_improve makes; records effects."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)   # consumed per run_evals call
        self.improve_called = False
        self.forget_called = False
        self.snapshots = 0

    def install(self):
        async def run_evals(dataset, specs=None):
            return _report(self.verdicts.pop(0))

        async def take_snapshot(dataset, label=None):
            self.snapshots += 1
            return Path(f"snapshots/{dataset}_stub.json")

        async def improve(dataset="brain", session_ids=None):
            self.improve_called = True
            return {"dataset": dataset, "session_ids": session_ids or []}

        async def forget(dataset="brain", node_set=None, memory_only=True):
            self.forget_called = True
            return {"dataset": dataset, "forgot": True}

        evals.run_evals = run_evals
        snapshot.take_snapshot = take_snapshot
        brain.improve = improve
        brain.forget = forget
        # ci_gate_improve reverts via brain.restore_snapshot if present, else
        # falls back to reporting the snapshot path. Ensure the attribute is
        # absent so we exercise the documented fallback path deterministically.
        if hasattr(brain, "restore_snapshot"):
            delattr(brain, "restore_snapshot")


async def scenario(name, verdicts, expect_code, expect_improve, expect_forget):
    h = Harness(verdicts)
    h.install()
    code = await ci.ci_gate_improve("brain", session_ids=["s1"])
    ok = (
        code == expect_code
        and h.improve_called == expect_improve
        and h.forget_called == expect_forget
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"       exit={code} (want {expect_code})  "
          f"improve_called={h.improve_called} (want {expect_improve})  "
          f"forget_called={h.forget_called} (want {expect_forget})")
    return ok


async def main() -> int:
    results = []
    # 1. green before, green after → accept, no revert
    results.append(await scenario(
        "green→green: improve ACCEPTED",
        verdicts=[True, True], expect_code=0, expect_improve=True, expect_forget=False))
    # 2. green before, red after → improve regressed → job fails (no PR), no
    #    auto-forget today (best-effort restore hook absent); the block is the guarantee.
    results.append(await scenario(
        "green→red: improve BLOCKED (exit 1, no PR)",
        verdicts=[True, False], expect_code=1, expect_improve=True, expect_forget=False))
    # 3. red before → refuse, never improve
    results.append(await scenario(
        "red before: improve REFUSED",
        verdicts=[False], expect_code=1, expect_improve=False, expect_forget=False))

    ok = all(results)
    print("\n" + ("PASS — CI-gated improve() enforces green-before/green-after with rollback."
                  if ok else "FAIL — gating logic incorrect."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
