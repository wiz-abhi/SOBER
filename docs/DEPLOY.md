# Deploying the SOBER live app

The hosted app (`app.py` + `web/dashboard.html`) is a **memory-CI control panel**:
run the memory CI, retract a leaked secret and watch its subgraph dissolve, bisect
a poisoned batch. It serves the **real pipeline's captured outputs** (`golden/`), so
it runs **quota-free and needs no Cognee/LLM key on the host**.

## Step 1 — build the golden capture (one time, local, needs Gemini)

From the repo root, with your Gemini key in `.env` and the full stack installed
(`pip install -e .`):

```bash
python scripts/build_golden.py            # captures leaked/clean graphs + evals + diff
python scripts/build_golden.py --bisect   # (optional) also capture a real bisect trace
```

This runs the real Cognee+Gemini pipeline once and writes real JSON into `golden/`.
Commit it:

```bash
git add golden && git commit -m "chore: golden capture for live app" && git push
```

> Gemini free tier is ~20 requests/day. The main capture fits; if `--bisect` hits
> the cap, enable billing on the Google project (stays free at this volume) or run
> it another day. **Until `golden/` exists the app still runs** — it falls back to
> built-in sample data, so you can deploy first and add the real capture later.

## Step 2 — deploy to Hugging Face Spaces (free, no credit card needed)

1. Create a free account at huggingface.co.
2. **New → Space** → SDK **Docker** → name it `sober`.
3. Use [`deploy/hf-README.md`](deploy/hf-README.md) as the Space's `README.md`
   (its frontmatter sets `sdk: docker`, `app_port: 7860`).
4. Push this repo to the Space:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-user>/sober
   git push space main
   ```
5. The Space builds the Dockerfile and serves at **`https://<your-user>-sober.hf.space`** — your live URL.

## Alternative — Render (also free)

`render.yaml` is included. On render.com: **New → Blueprint** → point at this repo →
it builds the Dockerfile and gives you a live URL.

## Run locally

```bash
python app.py            # or: uvicorn app:app --port 7860
# open http://localhost:7860
```

## How it stays honest

Every graph, eval result, diff count, and bisect trace the app shows was produced
by the **real** Cognee + Gemini pipeline during `build_golden.py` and captured to
JSON. The app replays those real outputs interactively — it does not mock them. The
sample fallback (when `golden/` is absent) is clearly labelled "demo mode".
