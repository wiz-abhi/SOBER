const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");

(async () => {
  const dir = path.join(__dirname, "frames");
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });

  const url = "file:///C:/Users/abhis/Desktop/OSS/Cognee/sober/viewer/explainer.html";
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
  await p.goto(url);

  const t0 = Date.now();
  let i = 0, done = false;
  // capture as fast as possible; the page animates in real time, so frame count/elapsed = fps
  while (Date.now() - t0 < 100000) {
    await p.screenshot({ path: path.join(dir, `f${String(i).padStart(4, "0")}.jpg`), type: "jpeg", quality: 92, animations: "allow" });
    i++;
    if (i % 12 === 0) { done = await p.evaluate(() => window.__done === true); if (done) break; }
  }
  const secs = (Date.now() - t0) / 1000;
  console.log(`FRAMES=${i} SECS=${secs.toFixed(2)} FPS=${(i / secs).toFixed(2)} DONE=${done}`);
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
