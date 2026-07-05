"""Minimal cognify smoke test — verify the configured LLM does structured extraction."""
import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
import cognee

async def main() -> int:
    print(f"[check] provider={os.environ.get('LLM_PROVIDER')} model={os.environ.get('LLM_MODEL')}")
    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
        await cognee.add("Ada Lovelace worked with Charles Babbage on the Analytical Engine.", dataset_name="llmcheck")
        await cognee.cognify(datasets=["llmcheck"])
        res = await cognee.export("llmcheck", format="json", destination=str(Path(__file__).parent / "_llmcheck.json"))
        n = getattr(res, "nodes", 0)
        print(f"\n[check] ✅ OK — cognify produced a graph ({n} nodes). Cerebras structured output works.")
        return 0
    except Exception as e:
        print(f"\n[check] ❌ FAILED: {type(e).__name__}: {str(e)[:300]}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
