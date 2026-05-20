#!/usr/bin/env node
/**
 * Server-side renderer for the cricket lineup templates.
 *
 * Usage:
 *   node render.js <input.json> <output.jpg>
 *   node render.js --batch <inputs-dir> <outputs-dir>
 *   echo '{...}' | node render.js --stdin <output.jpg>
 *
 * The input JSON shape matches window.__RENDER_CONFIG documented in render.html:
 *
 *   {
 *     "template": "T1_HeroList",
 *     "palette":  "crimson",
 *     "team":     { "name": "...", "short": "AC", "monogram": "AC", "logo": "url/or/path" },
 *     "opponent": { ... },
 *     "match":    { "competition": "...", "round": "...", "venue": "...", "date": "...", "time": "...", "season": "..." },
 *     "players":  [ { "first": "...", "last": "...", "role": "BAT", "headshot": "url?", "captain": true } ],
 *     // for companion templates only — supply the matching object:
 *     "toss":     { "winner": "TEAM", "decision": "BAT" },
 *     "motm":     { "player": {...}, "stats": [{"label":"Runs","value":"87"}], "summary": "..." },
 *     "result":   { "winner": "TEAM", "margin": "by 28 runs", "teamScore": "182/6 (20)", "oppScore": "154/9 (20)", "motmLast": "HOLT" }
 *   }
 *
 * Templates available:
 *   Lineup:    T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder,
 *              T5_Brutalist, T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer
 *   Companion: C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const RENDER_HTML = path.resolve(__dirname, "..", "render.html");

async function renderOne(browser, config, outputPath) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1080, deviceScaleFactor: 2 });

  // Inject the config BEFORE any scripts run.
  await page.evaluateOnNewDocument((cfg) => {
    window.__RENDER_CONFIG = cfg;
  }, config);

  await page.goto("file://" + RENDER_HTML, { waitUntil: "networkidle0", timeout: 30_000 });
  await page.waitForFunction(() => window.__renderReady === true, { timeout: 30_000 });

  const target = await page.$("#render-target");
  const ext = path.extname(outputPath).slice(1).toLowerCase();
  const type = ext === "jpg" || ext === "jpeg" ? "jpeg" : "png";

  await target.screenshot({
    path: outputPath,
    type,
    quality: type === "jpeg" ? 92 : undefined,
    omitBackground: type === "png",
  });

  await page.close();
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes("-h") || args.includes("--help")) {
    console.error(`
Cricket template renderer

  node render.js <input.json> <output.{jpg,png}>
      Render a single template from a JSON config.

  node render.js --batch <inputs-dir> <outputs-dir>
      Render every *.json in inputs-dir, writing matching .jpg files to outputs-dir.

  cat config.json | node render.js --stdin <output.{jpg,png}>
      Read config from stdin.
`);
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  try {
    if (args[0] === "--batch") {
      const inputsDir = args[1];
      const outputsDir = args[2];
      if (!fs.existsSync(outputsDir)) fs.mkdirSync(outputsDir, { recursive: true });
      const files = fs.readdirSync(inputsDir).filter((f) => f.endsWith(".json"));
      for (const f of files) {
        const cfg = JSON.parse(fs.readFileSync(path.join(inputsDir, f), "utf8"));
        const out = path.join(outputsDir, f.replace(/\.json$/, ".jpg"));
        await renderOne(browser, cfg, out);
        console.log(`✓ ${out}`);
      }
    } else if (args[0] === "--stdin") {
      const outputFile = args[1];
      const stdin = fs.readFileSync(0, "utf8");
      const cfg = JSON.parse(stdin);
      await renderOne(browser, cfg, outputFile);
      console.log(`✓ ${outputFile}`);
    } else {
      const inputFile = args[0];
      const outputFile = args[1];
      const cfg = JSON.parse(fs.readFileSync(inputFile, "utf8"));
      await renderOne(browser, cfg, outputFile);
      console.log(`✓ ${outputFile}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
