"""Minimal Gemini key validation — one cheap call, fail fast.

Confirms the configured LLM_API_KEY authenticates before we spend it on a full
demo. Ingests one short sentence (a couple of LLM calls) and reports OK / the
auth error. Cheapest possible go/no-go on the key.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

import cognee  # noqa: E402


async def main() -> int:
    key = os.environ.get("LLM_API_KEY", "")
    print(f"[check] model={os.environ.get('LLM_MODEL')}  key={key[:6]}…{key[-4:]} ({len(key)} chars)")
    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
        await cognee.add("Ada Lovelace wrote the first algorithm.", dataset_name="keycheck")
        await cognee.cognify(datasets=["keycheck"])
    except Exception as exc:
        msg = str(exc)
        print("\n[check] ❌ KEY FAILED")
        if "API_KEY_INVALID" in msg or "API key not valid" in msg or "401" in msg or "UNAUTHENTICATED" in msg:
            print("        reason: authentication rejected — this is not a valid Gemini AI Studio API key.")
        elif "quota" in msg.lower() or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            print("        reason: quota exhausted (key authenticates but is rate/limit capped).")
        else:
            print(f"        reason: {type(exc).__name__}: {msg[:200]}")
        return 1
    print("\n[check] ✅ KEY OK — cognify succeeded. Safe to run the live demos.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
