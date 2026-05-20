#!/usr/bin/env node
/**
 * Render all 13 templates from the example data — handy smoke test.
 *   node render-all.js [output-dir]
 */
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const TEMPLATES = [
  "T1_HeroList", "T2_CardGrid", "T3_SideNumbered", "T4_BattingOrder",
  "T5_Brutalist", "T6_Diagonal", "T7_CaptainSpotlight", "T8_Mosaic", "T9_Flyer",
  "C1_CaptainAnnounce", "C2_TossWon", "C3_ManOfMatch", "C4_FinalScore",
];

const outDir = process.argv[2] || "out";
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

const base = JSON.parse(fs.readFileSync(path.join(__dirname, "example-input.json"), "utf8"));

for (const template of TEMPLATES) {
  const cfg = { ...base, template };
  const inputFile = path.join(outDir, `_${template}.json`);
  const outputFile = path.join(outDir, `${template}.jpg`);
  fs.writeFileSync(inputFile, JSON.stringify(cfg, null, 2));
  execSync(`node ${path.join(__dirname, "render.js")} ${inputFile} ${outputFile}`, { stdio: "inherit" });
  fs.unlinkSync(inputFile);
}

console.log(`\nDone. ${TEMPLATES.length} files in ${outDir}/`);
