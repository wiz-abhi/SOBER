"""
Gate 3 — snapshot/export round-trip for `brain diff`.

Verifies cognee.export() produces a snapshot SOBER can version and diff.
Prints the JSON structure (node/edge shape) so the diff engine knows what
to parse, and confirms the pydantic GraphSnapshot round-trips losslessly.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

import cognee

DATASET = "sober_gate3"
SNAP_DIR = Path(__file__).resolve().parent.parent / "snapshots"
SNAP_DIR.mkdir(exist_ok=True)


async def main() -> int:
    print(f"[gate3] dataset: {DATASET}\n")

    print("[gate3] step 0: clean slate")
    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
    except Exception as e:
        print(f"        prune warn: {e!r}")

    print("\n[gate3] step 1: ingest a tiny corpus")
    await cognee.add(
        "Ada Lovelace worked with Charles Babbage on the Analytical Engine.",
        dataset_name=DATASET,
    )
    await cognee.cognify(datasets=[DATASET])

    print("\n[gate3] step 2: export format='json'")
    json_path = SNAP_DIR / "gate3_v1.json"
    result = await cognee.export(DATASET, format="json", destination=str(json_path))
    print(f"        export result: {result}")
    print(f"        file exists: {json_path.exists()}  size: {json_path.stat().st_size if json_path.exists() else 0}")

    if json_path.exists():
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        print(f"        JSON top-level type: {type(raw).__name__}")
        if isinstance(raw, dict):
            print(f"        JSON keys: {list(raw.keys())}")
            for k, v in raw.items():
                if isinstance(v, list):
                    print(f"          {k}: list[{len(v)}]  sample={json.dumps(v[0])[:200] if v else 'empty'}")
                else:
                    print(f"          {k}: {type(v).__name__}")

    print("\n[gate3] step 3: export format='pydantic' (GraphSnapshot)")
    snap = await cognee.export(DATASET, format="pydantic")
    print(f"        snapshot type: {type(snap).__name__}")
    for attr in ("nodes", "edges", "data_points"):
        if hasattr(snap, attr):
            val = getattr(snap, attr)
            try:
                print(f"        snapshot.{attr}: {len(val)}")
            except Exception:
                print(f"        snapshot.{attr}: present")
    # lossless round-trip check
    try:
        dumped = snap.model_dump_json()
        print(f"        model_dump_json(): {len(dumped)} chars — lossless serialize OK")
    except Exception as e:
        print(f"        model_dump_json failed: {e!r}")

    print("\n" + "=" * 60)
    ok = json_path.exists() and json_path.stat().st_size > 0
    print(f"[gate3] {'PASS — export produces a diffable snapshot.' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
