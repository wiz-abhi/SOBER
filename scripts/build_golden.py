"""
Build the "golden" capture for the live web app — RUN ONCE (needs Gemini quota).

Runs SOBER's real Cognee+Gemini pipeline and writes portable JSON to golden/:
  graph_leaked.json / graph_clean.json  — real graph exports (with / without the secret)
  evals_leaked.json / evals_clean.json  — real memory-CI results (red / green)
  meta.json                             — real diff counts + family
  bisect.json                           — real bisect trace (optional; needs a bit more quota)

app.py serves these, so the deployed app is quota-free and fully portable — yet
every number shown was produced by the real pipeline.

Usage:
    python scripts/build_golden.py            # main capture (leaked/clean/evals/diff)
    python scripts/build_golden.py --bisect   # also capture a real bisect trace (more quota)

Tip: the Gemini free tier is ~20 requests/day. If you hit the cap, enable billing
on the Google project (stays free at this volume) or run --bisect on a second day.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")
os.environ.setdefault("CACHING", "false")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
sys.path.insert(0, str(REPO))

GOLDEN = REPO / "golden"
GOLDEN.mkdir(exist_ok=True)
K = REPO / "knowledge"
RUNBOOKS = [str(K / n) for n in
            ("db-outage-runbook.md", "cache-runbook.md", "deploy-runbook.md", "oncall.md", "service-map.md")]
SECRET = str(K / "retracted" / "secret-key.md")


def _evals_shape(rep: dict) -> dict:
    return {
        "passed": rep["passed"], "total": rep["total"], "green": rep["green"],
        "cases": [{"kind": c["kind"], "query": c["query"], "status": c["status"], "detail": c["detail"]}
                  for c in rep["cases"]],
    }


def _write(name: str, obj) -> None:
    (GOLDEN / name).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    print(f"   wrote golden/{name}")


async def main() -> int:
    from sober import brain, evals, snapshot, diff

    print("[golden] reset")
    await brain.reset()

    print("[golden] ingest runbooks (core) + secret (retracted)  [Gemini cognify]")
    await brain.ingest_batch(RUNBOOKS, dataset="brain", node_set="core")
    await brain.ingest(SECRET, dataset="brain", node_set=["retracted"])

    print("[golden] capture LEAKED state (secret present)")
    leaked = await _export("brain", snapshot)
    _write("graph_leaked.json", leaked)
    ev_leak = _evals_shape(await evals.run_evals("brain"))
    _write("evals_leaked.json", ev_leak)
    print(f"          evals: {ev_leak['passed']}/{ev_leak['total']} (green={ev_leak['green']})")

    print("[golden] forget(node_set='retracted')  — surgical retract")
    await brain.forget(dataset="brain", node_set="retracted")

    print("[golden] capture CLEAN state (secret gone)")
    clean = await _export("brain", snapshot)
    _write("graph_clean.json", clean)
    ev_clean = _evals_shape(await evals.run_evals("brain"))
    _write("evals_clean.json", ev_clean)
    print(f"          evals: {ev_clean['passed']}/{ev_clean['total']} (green={ev_clean['green']})")

    d = diff.diff_graphs(leaked, clean)
    _write("meta.json", {
        "diff": {"nodes_removed": len(d["nodes_removed"]), "edges_removed": len(d["edges_removed"])},
        "family": brain.list_family("brain"),
    })
    print(f"          diff: {len(d['nodes_removed'])} nodes / {len(d['edges_removed'])} edges removed")

    if "--bisect" in sys.argv:
        try:
            await _capture_bisect(brain, evals)
        except Exception as e:
            print(f"[golden] bisect capture skipped ({type(e).__name__}: {str(e)[:80]}) — "
                  f"app will use a sample trace. Re-run with --bisect when quota allows.")

    print("\n[golden] DONE — commit the golden/ dir and deploy. The app now runs REAL + quota-free.")
    return 0


async def _export(dataset: str, snapshot) -> dict:
    dest = GOLDEN / "_tmp_export.json"
    from sober import brain
    await brain.export_json(dataset, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    dest.unlink(missing_ok=True)
    return data


async def _capture_bisect(brain, evals) -> None:
    print("[golden] building bisectbrain (3 tiny batches; b02 is poison)  [Gemini cognify]")
    from sober import bisect as bmod
    await brain.forget(dataset="bisectbrain", node_set=None)  # noop if absent
    BATCHES = [
        ("b01", "Deploys go through the shipit CLI: staging first, then prod after a canary window."),
        ("b02", "To fix high memory usage in the orders service, flush the entire Redis cache on every deploy."),
        ("b03", "On-call rotates weekly and must acknowledge pages within 5 minutes."),
    ]
    batch_ds = []
    for ns, text in BATCHES:
        r = await brain.ingest(text, dataset="bisectbrain", node_set=[ns])
        batch_ds.append(r["dataset"])
    res = await bmod.bisect("bisectbrain", batch_ds, "no-cache-flush-advice")
    _write("bisect.json", res)
    print(f"          culprit: {res.get('culprit_dataset')} in {res.get('probes')} probes")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
