"""
SOBER — live web app (FastAPI).

A hosted "memory-CI control panel": visitors watch a brain get tested, catch a
leaked secret, forget() it (the graph dissolves + evals flip green), and bisect
a poisoned batch — SOBER's real pipeline, in a browser.

Design: the app serves the **real, captured outputs** of the actual pipeline.
`scripts/build_golden.py` runs the true Cognee+Gemini pipeline once and writes
portable JSON to `golden/` — the real graph exports (with and without the
secret), the real eval results (red then green), the real diff, and a real
bisect trace. The app loads that JSON and lets a visitor step through it. This
is fully portable (no Cognee store or LLM key on the host), runs quota-free, and
every number shown was produced by the real pipeline — not mocked.

If `golden/` is absent, the app still serves the UI and the frontend falls back
to its built-in sample + client animation, so it deploys and demos immediately.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

REPO = Path(__file__).resolve().parent
WEB = REPO / "web"
GOLDEN = REPO / "golden"

app = FastAPI(title="SOBER — CI/CD for Agent Brains")


def _load(name: str):
    p = GOLDEN / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# Captured real outputs (None until build_golden.py has been run + committed).
G_LEAK = _load("graph_leaked.json")
G_CLEAN = _load("graph_clean.json")
EV_LEAK = _load("evals_leaked.json")
EV_CLEAN = _load("evals_clean.json")
META = _load("meta.json") or {}
BISECT = _load("bisect.json")
REAL = all(x is not None for x in (G_LEAK, G_CLEAN, EV_LEAK, EV_CLEAN))

# Single-tenant demo state (like most hackathon deploys): which side are we on.
STATE = {"clean": False}  # False = leaked (secret present), True = retracted


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB / "dashboard.html")


@app.get("/api/state")
async def state() -> JSONResponse:
    if not REAL:
        return JSONResponse({"real": False})
    clean = STATE["clean"]
    return JSONResponse({
        "real": True,
        "graph": G_CLEAN if clean else G_LEAK,
        "evals": EV_CLEAN if clean else EV_LEAK,
        "can_forget": not clean,
        "family": META.get("family", []),
    })


@app.post("/api/test")
async def test() -> JSONResponse:
    if not REAL:
        return JSONResponse({"real": False})
    return JSONResponse({"real": True, "evals": EV_CLEAN if STATE["clean"] else EV_LEAK})


@app.post("/api/forget")
async def forget() -> JSONResponse:
    if not REAL:
        return JSONResponse({"real": False})
    STATE["clean"] = True
    return JSONResponse({
        "real": True, "graph": G_CLEAN, "evals": EV_CLEAN,
        "diff": META.get("diff", {"nodes_removed": 0, "edges_removed": 0}),
        "family": META.get("family_clean", META.get("family", [])),
    })


@app.post("/api/bisect")
async def bisect() -> JSONResponse:
    if not REAL:
        return JSONResponse({"real": False})
    if not BISECT:
        return JSONResponse({"real": True, "error": "no poisoned batch captured in this build"})
    return JSONResponse({"real": True, **BISECT})


@app.post("/api/reset")
async def reset() -> JSONResponse:
    if not REAL:
        return JSONResponse({"real": False})
    STATE["clean"] = False
    return JSONResponse({"real": True, "graph": G_LEAK, "evals": EV_LEAK, "can_forget": True,
                         "family": META.get("family", [])})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "real": REAL})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
