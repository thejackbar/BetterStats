// src/pages/PlayerComparison.jsx — head-to-head compare two players
import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatedNum, Sparkline, Label, Card, Btn, PageHeader } from "../lib/presskit";

const mockA = {
  id: 1, name: "Jack Banner", role: "TOP-ORDER BAT", member_since: "2019",
  matches: 78, runs: 2841, avg: 46.6, sr: 88.4, hs: 142, hundreds: 4, fifties: 18,
  form: [78, 12, 142, 38, 64, 6, 102, 41, 28, 88, 16, 67, 22, 102],
};
const mockB = {
  id: 2, name: "Tom Whitfield", role: "MIDDLE-ORDER BAT", member_since: "2021",
  matches: 56, runs: 2104, avg: 41.0, sr: 76.5, hs: 118, hundreds: 2, fifties: 14,
  form: [22, 88, 18, 52, 41, 64, 38, 51, 72, 4, 28, 118, 12, 47],
};

const ROWS = [
  ["MATCHES",     "matches",   "int"],
  ["RUNS",        "runs",      "int"],
  ["AVERAGE",     "avg",       "dec"],
  ["STRIKE RATE", "sr",        "dec"],
  ["HIGH SCORE",  "hs",        "int"],
  ["100s",        "hundreds",  "int"],
  ["50s",         "fifties",   "int"],
];

export default function PlayerComparison() {
  const [a] = useState(mockA);
  const [b] = useState(mockB);

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1200px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="HEAD-TO-HEAD · CAREER"
          title="Compare."
          meta={[<span key="x">Settle it with numbers.</span>]}
        />

        {/* Header row */}
        <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-stretch mb-3">
          <PlayerHero p={a} side="left" />
          <div className="hidden sm:flex items-center justify-center font-mono font-bold tracking-wide4 text-pb-faintest text-[26px]">VS</div>
          <PlayerHero p={b} side="right" />
        </div>

        {/* Comparison rows */}
        <Card className="mb-6 p-0" pad="">
          {ROWS.map(([label, key, kind], i) => {
            const av = a[key], bv = b[key];
            const aWin = av > bv, bWin = bv > av;
            const max = Math.max(av, bv, 1);
            return (
              <div key={key} className={`grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-4 sm:px-6 py-3.5 ${i ? "pb-hairline-t" : ""}`}>
                {/* a bar */}
                <div className="flex items-center gap-3 justify-end">
                  <span className={`font-mono text-[20px] font-bold pb-num ${aWin ? "" : "text-pb-dim"}`}
                        style={{ color: aWin ? "var(--pb-accent)" : undefined }}>
                    {kind === "dec" ? <AnimatedNum value={av} decimals={1} /> : <AnimatedNum value={av} />}
                  </span>
                  <div className="h-1.5 w-32 sm:w-48 bg-pb-hairline rounded-sm overflow-hidden">
                    <div className="h-full ml-auto" style={{
                      width: `${(av / max) * 100}%`,
                      background: aWin ? "var(--pb-accent)" : "var(--pb-faint)",
                      marginLeft: "auto",
                      transform: "translateX(100%)",
                      direction: "rtl",
                    }} />
                  </div>
                </div>
                {/* label */}
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase text-center min-w-[110px]">{label}</span>
                {/* b bar */}
                <div className="flex items-center gap-3">
                  <div className="h-1.5 w-32 sm:w-48 bg-pb-hairline rounded-sm overflow-hidden">
                    <div className="h-full" style={{ width: `${(bv / max) * 100}%`, background: bWin ? "var(--pb-accent)" : "var(--pb-faint)" }} />
                  </div>
                  <span className={`font-mono text-[20px] font-bold pb-num ${bWin ? "" : "text-pb-dim"}`}
                        style={{ color: bWin ? "var(--pb-accent)" : undefined }}>
                    {kind === "dec" ? <AnimatedNum value={bv} decimals={1} /> : <AnimatedNum value={bv} />}
                  </span>
                </div>
              </div>
            );
          })}
        </Card>

        {/* Recent form chart */}
        <Card title="LAST 14 INNINGS">
          <div className="h-[160px] grid grid-cols-1 gap-1">
            <div className="flex items-end h-1/2" style={{ color: "var(--pb-accent)" }}>
              <Sparkline data={a.form} w={1140} h={70} stroke="currentColor" fill="currentColor" strokeWidth={1.4} dot />
            </div>
            <div className="flex items-end h-1/2 text-pb-text">
              <Sparkline data={b.form} w={1140} h={70} stroke="currentColor" strokeWidth={1.4} dot />
            </div>
          </div>
          <div className="flex gap-4 mt-3">
            <Legend color="var(--pb-accent)" label={a.name} />
            <Legend color="var(--pb-text)" label={b.name} />
          </div>
        </Card>
      </main>
    </div>
  );
}

function PlayerHero({ p, side }) {
  return (
    <div className="pb-card p-5">
      <Label>{p.role} · MEMBER SINCE {p.member_since}</Label>
      <Link to={`/players/${p.id}`} className="block">
        <h2 className={`font-display text-[34px] sm:text-[44px] font-bold tracking-tight leading-tight mt-2 ${side === "right" ? "" : ""}`}>
          {p.name}
        </h2>
      </Link>
      <div className="font-mono text-pb-faint text-[11px] tracking-wide2 mt-1">CAREER #{p.id}</div>
    </div>
  );
}

function Legend({ color, label }) {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px] tracking-wide2 text-pb-dim">
      <span className="w-3 h-[2px]" style={{ background: color }} />{label.toUpperCase()}
    </div>
  );
}
