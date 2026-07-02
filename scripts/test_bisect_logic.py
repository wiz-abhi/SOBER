"""
Offline proof of the bisect binary-search (no cognee, no Gemini).

The live bisect demo (scripts/demo_bisect.py) needs cognify and is blocked by
the Gemini free-tier daily cap. But the *search logic* is pure: given a red/green
verdict per batch, does bisect find the right culprit in O(log n) probes?

We stub evals.run_evals to declare exactly one batch (the poison) red, then
assert bisect localizes it with a logarithmic number of probes. This validates
sober/bisect.py end-to-end at the logic level, independent of the API.
"""

import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sober import bisect, evals  # noqa: E402

N = 8
POISON_INDEX = 5  # 0-based; batch b06 is the culprit
BATCHES = [f"bisectbrain__b{i:02d}" for i in range(1, N + 1)]
POISON = BATCHES[POISON_INDEX]
EVAL = "no-cache-flush-advice"


async def fake_run_evals(dataset, specs=None):
    """Red iff this batch is the poison; green otherwise."""
    green = dataset != POISON
    return {"passed": int(green), "failed": int(not green),
            "total": 1, "green": green, "cases": []}


class _Spec:
    name = EVAL
    kind = "forbidden"
    cases = []


def fake_load_specs(path=None):
    return [_Spec()]


async def main() -> int:
    # Patch the lazily-imported module functions bisect will call.
    evals.run_evals = fake_run_evals
    evals.load_specs = fake_load_specs

    result = await bisect.bisect("bisectbrain", BATCHES, EVAL)

    culprit_ok = result["culprit_dataset"] == POISON
    # O(log n): full-set sanity probe (1) + binary search (~ceil(log2 n)+1).
    log_bound = math.ceil(math.log2(N)) + 3
    probes_ok = result["probes"] <= log_bound

    print(f"batches:        {N}")
    print(f"planted poison: {POISON} (index {POISON_INDEX})")
    print(f"culprit found:  {result['culprit_dataset']}  -> {'OK' if culprit_ok else 'WRONG'}")
    print(f"probes used:    {result['probes']} (<= {log_bound} bound, linear would be {N})  -> {'OK' if probes_ok else 'TOO MANY'}")
    print("search trace:")
    for s in result["steps"]:
        note = f"  <{s['note']}>" if s.get("note") else ""
        print(f"   probe {s['probe']}: prefix_len={s['prefix_len']:>2} "
              f"candidate={s['candidate']} red={str(s['red']):>5}{note}")

    ok = culprit_ok and probes_ok
    print("\n" + ("PASS — bisect localizes the poison in O(log n)." if ok
                  else "FAIL — bisect logic incorrect."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
