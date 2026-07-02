"""SOBER configuration — env loading and repo-relative path constants.

This module is intentionally cognee-free. It only manages environment setup
(so cognee picks up the right LLM / embedding / storage config when it is
eventually imported by ``sober.brain``) and exposes the canonical on-disk
locations SOBER reads and writes.

Layout assumption::

    <REPO_ROOT>/
        sober/          <- this package
            config.py   <- this file
        snapshots/      <- SNAP_DIR   (versioned graph exports)
        knowledge/      <- KNOWLEDGE_DIR (source corpus to ingest)
        evals/          <- EVALS_DIR  (memory-CI YAML specs)
        .env            <- loaded by load_env()
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Repo-relative paths -------------------------------------------------
# sober/config.py  ->  parents[0] = sober/  ->  parents[1] = <repo root>
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
SNAP_DIR: Path = REPO_ROOT / "snapshots"
KNOWLEDGE_DIR: Path = REPO_ROOT / "knowledge"
EVALS_DIR: Path = REPO_ROOT / "evals"

# --- Dataset naming ------------------------------------------------------
DATASET_DEFAULT: str = "brain"

# Module-level guard so load_env() stays cheap when called repeatedly (it is
# invoked on every brain.py import and by every CLI command).
_ENV_LOADED: bool = False


def load_env() -> None:
    """Load ``.env`` and set cognee-friendly defaults. Idempotent.

    Every SOBER entry point must call this *before* cognee reads its config.
    It:

    * loads ``<REPO_ROOT>/.env`` (LLM provider/key, embeddings, rate limits),
    * disables cognee's response cache (``CACHING=false``) so tests are
      deterministic and don't mask a real recall/forget with a stale hit,
    * disables backend access control (``ENABLE_BACKEND_ACCESS_CONTROL=false``)
      so the local embedded stores work without an auth layer.

    ``os.environ.setdefault`` is used for the two toggles so an explicit
    override in the real environment always wins. Calling this more than once
    is a no-op after the first successful load.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    # Imported lazily so importing this module never hard-requires python-dotenv
    # to be present for the path constants alone.
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    os.environ.setdefault("CACHING", "false")
    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

    _ENV_LOADED = True
