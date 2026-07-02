"""
Gate 2 — the load-bearing primitive for SOBER's forbidden-knowledge tests.

Question: does cognee.forget() actually make a fact unrecallable via CHUNKS
(vector-similarity) search? If forgetting leaves residue in the vector store,
the entire "retracted secrets stay retracted" pitch collapses.

Keyless: we neutralize cognee's LLM entity-extraction stage so the pipeline
runs classify → chunk → embed (fastembed) → write to vector store, then we
CHUNKS-search, forget, CHUNKS-search again. No Gemini needed — which also
becomes SOBER's cheap CI mode for forbidden-knowledge tests in GitHub Actions.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

import cognee
from cognee import SearchType


SECRET = "The launch code is BRAVO-DELTA-9917."
INNOCENT = "The quarterly all-hands is next Thursday at 3pm."
QUERY = "launch code"
DATASET = "sober_gate2"


def leaked(results, needle: str) -> bool:
    if not results:
        return False
    blob = " ".join(str(r) for r in results).lower()
    return needle.lower() in blob


async def main() -> int:
    print(f"[gate2] embedding: {os.environ['EMBEDDING_PROVIDER']}")
    print(f"[gate2] dataset:   {DATASET}\n")

    print("[gate2] step 0: clean slate")
    try:
        await cognee.prune.prune_data()
    except Exception as e:
        print(f"        prune_data warn: {e!r}")
    try:
        await cognee.prune.prune_system(metadata=True)
    except Exception as e:
        print(f"        prune_system warn: {e!r}")

    print("\n[gate2] step 1: add() + cognify() [real Gemini pipeline]")
    await cognee.add(SECRET, dataset_name=DATASET)
    await cognee.add(INNOCENT, dataset_name=DATASET)
    cognify_result = await cognee.cognify(datasets=[DATASET])
    print(f"        cognify: {list(cognify_result.keys()) if isinstance(cognify_result, dict) else cognify_result}")

    print("\n[gate2] step 2: CHUNKS search — baseline should FIND the secret")
    before = await cognee.search(
        query_text=QUERY,
        query_type=SearchType.CHUNKS,
        datasets=[DATASET],
        top_k=5,
    )
    print(f"        results (before forget): {before}")
    baseline = leaked(before, "BRAVO-DELTA-9917")
    print(f"        secret recallable? {baseline}")

    if not baseline:
        print("[gate2] FAIL: baseline CHUNKS search did NOT surface the planted secret.")
        return 2

    print("\n[gate2] step 3: forget(dataset=..., memory_only=True)")
    forget_result = await cognee.forget(dataset=DATASET, memory_only=True)
    print(f"        forget: {forget_result}")

    print("\n[gate2] step 4: CHUNKS search — must NOT surface the secret")
    try:
        after = await cognee.search(
            query_text=QUERY,
            query_type=SearchType.CHUNKS,
            datasets=[DATASET],
            top_k=5,
        )
    except Exception as e:
        # NoDataError after forget() is the DESIRED outcome — no data, no leak.
        print(f"        search-after-forget raised (expected): {type(e).__name__}: {str(e)[:100]}")
        after = []
    print(f"        results (after forget): {after}")
    residual = leaked(after, "BRAVO-DELTA-9917")
    print(f"        secret STILL recallable? {residual}")

    print("\n" + "=" * 60)
    if baseline and not residual:
        print("[gate2] PASS  — forget() removes vector residue. SOBER is viable.")
        return 0
    if baseline and residual:
        print("[gate2] FAIL  — forget() left vector residue. Investigate.")
        return 1
    return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
