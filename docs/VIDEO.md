# Making the submission video

The 2-minute explainer+demo video is generated from a self-playing HTML reel —
no screen-recording by hand, fully reproducible.

- **Source:** [`viewer/explainer.html`](../viewer/explainer.html) — a self-playing,
  captioned reel: problem → what SOBER is → live graph demo (run CI → forget →
  bisect) → proof → outro. All captions are burned in (no voiceover needed).
- **Output:** `sober-demo.mp4` — 1280×720, 30 fps, H.264.

## Regenerate

Needs Node (Playwright) and ffmpeg (via `pip install imageio-ffmpeg`).

```bash
# 1. install the recorder deps (once)
npm i playwright && npx playwright install chromium
pip install imageio-ffmpeg

# 2. capture the reel to a frame sequence (drives the page in real time)
node capture.js          # writes frames/f%04d.jpg, prints the measured FPS

# 3. assemble to mp4 (use the FPS printed above as -framerate)
ffmpeg -framerate <FPS> -start_number 0 -i frames/f%04d.jpg \
  -c:v libx264 -pix_fmt yuv420p -r 30 -crf 20 -movflags +faststart sober-demo.mp4
```

`capture.js` (screenshot loop) is used instead of Playwright's `recordVideo`
because the built-in screencast stops early on a canvas-heavy page; a screenshot
loop is bulletproof and captures the full reel.

To change length/pacing, edit `PACE` in `viewer/explainer.html` (higher = slower).
Captions live in the `run()` timeline in that file.
