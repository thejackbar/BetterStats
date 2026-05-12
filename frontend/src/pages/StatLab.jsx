// src/pages/StatLab.jsx — deep-dive batting splits
// "Where do my runs come from?" — filter, slice, dice.
import React, { useState } from "react";
import { AnimatedNum, MiniBars, Sparkline, Label, Card, Btn, PageHeader } from "../lib/presskit";

const mockSplits = {
  player: "Jack Banner",
  by_phase: [
    { phase: "POWERPLAY (1-6)",   runs: 412, balls: 268, sr: 153.7, fours: 48, sixes: 14 },
    { phase: "MIDDLE (7-15)",     runs: 538, balls: 412, sr: 130.6, fours: 42, sixes: 18 },
    { phase: "DEATH (16-20)",     runs: 267, balls: 138, sr: 193.5, fours: 22, sixes: 22 },
  ],
  by_bowler: [
    { type: "RIGHT-ARM PACE",  runs: 612, balls: 388, dismissals: 4 },
    { type: "LEFT-ARM PACE",   runs: 282, balls: 178, dismissals: 2 },
    { type: "OFF SPIN",        runs: 245, balls: 168, dismissals: 3 },
    { type: "LEG SPIN",        runs: 188, balls: 124, dismissals: 5 },
    { type: "LEFT-ARM SPIN",   runs:  92, balls:  78, dismissals: 1 },
  ],
  by_ground: [
    { ground: "ACTON OVAL (H)",   matches: 28, runs: 1024, avg: 51.2 },
    { ground: "MARLOW (A)",       matches:  6, runs:  282, avg: 47.0 },
    { ground: "STOKE GREEN (A)",  matches:  8, runs:  376, avg: 47.0 },
    { ground: "PINNER (A)",       matches:  5, runs:  198, avg: 39.6 },
    { ground: "EALING (A)",       matches:  4, runs:  168, avg: 42.0 },
  ],
  wagon_wheel: [
    { angle:  15, dist: 88,  type: "4" }, { angle:  35, dist: 64,  type: "1" },
    { angle:  55, dist: 92,  type: "6" }, { angle:  78, dist: 58,  type: "1" },
    { angle: 105, dist: 78,  type: "4" }, { angle: 128, dist: 96,  type: "6" },
    { angle: 152, dist: 62,  type: "2" }, { angle: 175, dist: 84,  type: "4" },
    { angle: 198, dist: 70,  type: "2" }, { angle: 224, dist: 88,  type: "4" },
    { angle: 252, dist: 58,  type: "1" }, { angle: 280, dist: 76,  type: "4" },
    { angle: 310, dist: 92,  type: "6" }, { angle: 340, dist: 68,  type: "2" },
  ],
};

export default function StatLab() {
  const [data] = useState(mockSplits);
  const [view, setView] = useState("PHASE");

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="STAT LAB · DEEP DIVE"
          title="Where do the runs come from?"
          meta={[<span key="p"><span className="text-pb-text">{data.player}</span> · 2025/26</span>]}
          actions={[<Btn key="x">Change player</Btn>, <Btn key="e" primary>Export CSV</Btn>]}
        />

        {/* View selector */}
        <div className="flex gap-1 pb-hairline-b mb-5">
          {["PHASE", "BOWLER TYPE", "GROUND", "WAGON WHEEL"].map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 relative ${
                view === v ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
              }`}>
              {v}
              {view === v && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: "var(--pb-accent)" }} />}
            </button>
          ))}
        </div>

        {view === "PHASE" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {data.by_phase.map(p => (
              <div key={p.phase} className="pb-card p-5">
                <Label>{p.phase}</Label>
                <div className="font-mono text-[42px] font-bold pb-num leading-none mt-3" style={{ color: "var(--pb-accent)" }}>
                  <AnimatedNum value={p.runs} />
                </div>
                <div className="font-mono text-[11px] text-pb-dim tracking-wide2 mt-1">
                  <AnimatedNum value={p.balls} /> BALLS · SR {p.sr.toFixed(1)}
                </div>
                <div className="pb-dashed-t pt-3 mt-4 grid grid-cols-2 gap-3 font-mono text-[12px] text-pb-dim tracking-wide2">
                  <div>4s <span className="text-pb-text font-bold">{p.fours}</span></div>
                  <div>6s <span className="text-pb-text font-bold">{p.sixes}</span></div>
                </div>
              </div>
            ))}
          </div>
        )}

        {view === "BOWLER TYPE" && (
          <Card title="V BOWLER TYPE">
            <ul className="flex flex-col">
              {data.by_bowler.map((b, i) => {
                const max = Math.max(...data.by_bowler.map(x => x.runs));
                const pct = (b.runs / max) * 100;
                return (
                  <li key={b.type} className={`${i ? "pb-hairline-t" : ""} py-3 grid grid-cols-[160px_1fr_auto] gap-4 items-center`}>
                    <span className="font-mono text-pb-text text-[12px] tracking-wide2">{b.type}</span>
                    <div className="h-2 bg-pb-hairline rounded-sm overflow-hidden">
                      <div className="h-full" style={{ width: `${pct}%`, background: "var(--pb-accent)" }} />
                    </div>
                    <span className="font-mono text-[14px] text-pb-text font-bold pb-num">
                      <AnimatedNum value={b.runs} /> R · {b.dismissals} W
                    </span>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}

        {view === "GROUND" && (
          <Card title="V GROUND">
            <ul className="flex flex-col">
              {data.by_ground.map((g, i) => {
                const max = Math.max(...data.by_ground.map(x => x.runs));
                return (
                  <li key={g.ground} className={`${i ? "pb-hairline-t" : ""} py-3 grid grid-cols-[220px_1fr_auto_auto] gap-4 items-center`}>
                    <span className="font-mono text-pb-text text-[12px] tracking-wide2 truncate">{g.ground}</span>
                    <div className="h-2 bg-pb-hairline rounded-sm overflow-hidden">
                      <div className="h-full" style={{ width: `${(g.runs / max) * 100}%`, background: "var(--pb-accent)" }} />
                    </div>
                    <span className="font-mono text-pb-dim text-[11px] tracking-wide2">{g.matches} M</span>
                    <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-32 text-right">
                      <AnimatedNum value={g.runs} /> R · AVG {g.avg.toFixed(1)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}

        {view === "WAGON WHEEL" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-3">
            <Card title="SHOT MAP · CAREER">
              <div className="flex items-center justify-center">
                <WagonWheel shots={data.wagon_wheel} />
              </div>
            </Card>
            <Card title="LEGEND">
              <ul className="flex flex-col gap-2 font-mono text-[11px] tracking-wide2">
                <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{ background: "var(--pb-accent)" }} /> SIX</li>
                <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{ background: "var(--pb-text)" }} /> FOUR</li>
                <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{ background: "var(--pb-dim)" }} /> 1-3 RUNS</li>
              </ul>
              <div className="pb-dashed-t pt-3 mt-4 font-mono text-[11px] tracking-wide2 text-pb-dim space-y-2">
                <div>STRONG ZONES <span className="text-pb-text">COVER · MIDWICKET · LONG-ON</span></div>
                <div>WEAK ZONES <span className="text-pb-text">FINE LEG</span></div>
              </div>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}

function WagonWheel({ shots }) {
  const size = 360, c = size / 2, r = c - 18;
  return (
    <svg width={size} height={size}>
      <circle cx={c} cy={c} r={r} fill="none" stroke="var(--pb-hairline2)" strokeWidth="1" />
      <circle cx={c} cy={c} r={r * 0.66} fill="none" stroke="var(--pb-hairline)" strokeWidth="1" strokeDasharray="2 4" />
      <circle cx={c} cy={c} r={r * 0.33} fill="none" stroke="var(--pb-hairline)" strokeWidth="1" strokeDasharray="2 4" />
      <line x1={c} y1={18} x2={c} y2={size - 18} stroke="var(--pb-hairline)" strokeWidth="1" />
      <line x1={18} y1={c} x2={size - 18} y2={c} stroke="var(--pb-hairline)" strokeWidth="1" />
      <circle cx={c} cy={c} r={3} fill="var(--pb-text)" />
      {shots.map((s, i) => {
        const rad = (s.angle - 90) * Math.PI / 180;
        const x = c + Math.cos(rad) * r * (s.dist / 100);
        const y = c + Math.sin(rad) * r * (s.dist / 100);
        const color = s.type === "6" ? "var(--pb-accent)" : s.type === "4" ? "var(--pb-text)" : "var(--pb-dim)";
        return <line key={i} x1={c} y1={c} x2={x} y2={y} stroke={color} strokeWidth={s.type === "6" ? 1.8 : s.type === "4" ? 1.4 : 1} opacity={0.85} />;
      })}
    </svg>
  );
}
