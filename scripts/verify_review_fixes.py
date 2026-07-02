"""Keyless verification of the review fixes (no cognee/Gemini needed).

Covers the two behaviors changed by the review that the existing offline proofs
don't touch:
  - cli._discover_batch_datasets now reads the family registry (Fix B)
  - bisect.bisect rejects non-forbidden evals (Fix C)
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sober import cli, bisect, evals, config  # noqa: E402


def test_discover_batch_datasets() -> bool:
    reg_path = config.SNAP_DIR / ".family.json"
    backup = reg_path.read_text(encoding="utf-8") if reg_path.exists() else None
    try:
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps({
            "brain": ["brain__core", "brain__poisoned"],
            "other": ["other__x"],
        }), encoding="utf-8")
        got = cli._discover_batch_datasets("brain")
        ok = got == ["brain__core", "brain__poisoned"]
        print(f"[discover] {'OK' if ok else 'FAIL'} -> {got}")
        # empty for an unknown brain
        ok2 = cli._discover_batch_datasets("nope") == []
        print(f"[discover] unknown-brain empty: {'OK' if ok2 else 'FAIL'}")
        return ok and ok2
    finally:
        if backup is not None:
            reg_path.write_text(backup, encoding="utf-8")
        else:
            reg_path.unlink(missing_ok=True)


async def test_bisect_rejects_non_forbidden() -> bool:
    class _Spec:
        name = "ops-runbooks-must-know"
        kind = "must_know"
        cases = []

    evals.load_specs = lambda path=None: [_Spec()]
    try:
        await bisect.bisect("brain", ["brain__core", "brain__b02"], "ops-runbooks-must-know")
        print("[guard] FAIL — bisect accepted a must_know eval (should have raised)")
        return False
    except ValueError as e:
        ok = "forbidden" in str(e).lower()
        print(f"[guard] {'OK' if ok else 'FAIL'} — rejected must_know: {str(e)[:70]}…")
        return ok


async def main() -> int:
    r1 = test_discover_batch_datasets()
    r2 = await test_bisect_rejects_non_forbidden()
    ok = r1 and r2
    print("\n" + ("PASS — review fixes verified." if ok else "FAIL — a fix regressed."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
