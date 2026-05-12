// src/pages/MatchScorecard.jsx — BetterStats Press Box scorecard
// Drop in as MatchScorecardV2.jsx or replace existing.

import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { AnimatedNum, Sparkline, Label, Card, Btn, ResultPill, PageHeader } from "../lib/presskit";

// Mock — match real /api/matches/{id} shape.
const mockMatch = {
  id: 901,
  date: "2026-05-09",
  ground: "Marlow CC",
  format: "T20",
  toss: "ACTON, chose to bat",
  result: "ACTON won by 23 runs",
  outcome: "WIN",
  player_of_match: "Jack Banner",
  innings: [
    {
      team: "Acton CC", total: "187/4", overs: "20.0", rr: 9.35,
      batting: [
        { id: 1, name: "J. Banner",     dismissal: "c Smith b Lyle", r: 78, b: 42, fours: 8, sixes: 4, sr: 185.7 },
        { id: 2, name: "T. Whitfield",  dismissal: "b Patel",        r: 38, b: 34, fours: 4, sixes: 1, sr: 111.8 },
        { id: 3, name: "R. Stone",      dismissal: "not out",        r: 41, b: 28, fours: 5, sixes: 1, sr: 146.4 },
        { id: 4, name: "H. Vaughn",     dismissal: "c Roy b Doyle",  r: 12, b: 11, fours: 1, sixes: 0, sr: 109.1 },
        { id: 5, name: "S. Okafor",     dismissal: "not out",        r: 14, b: 5,  fours: 2, sixes: 0, sr: 280.0 },
      ],
      bowling: [
        { id: 11, name: "Lyle",   o: 4, m: 0, r: 28, w: 2, econ: 7.0 },
        { id: 12, name: "Patel",  o: 4, m: 0, r: 31, w: 1, econ: 7.75 },
        { id: 13, name: "Doyle",  o: 4, m: 0, r: 42, w: 1, econ: 10.5 },
        { id: 14, name: "Briggs", o: 4, m: 0, r: 38, w: 0, econ: 9.5 },
        { id: 15, name: "Pope",   o: 4, m: 0, r: 44, w: 0, econ: 11.0 },
      ],
    },
    {
      team: "Marlow CC", total: "164/8", overs: "20.0", rr: 8.2,
      batting: [
        { id: 21, name: "Roy",     dismissal: "b Patel",         r: 44, b: 28, fours: 4, sixes: 2, sr: 157.1 },
        { id: 22, name: "Doyle",   dismissal: "c Stone b Lyle",  r: 22, b: 21, fours: 2, sixes: 1, sr: 104.8 },
        { id: 23, name: "Smith",   dismissal: "lbw b Patel",     r: 31, b: 26, fours: 3, sixes: 0, sr: 119.2 },
        { id: 24, name: "Briggs",  dismissal: "c Banner b Lyle", r: 18, b: 17, fours: 2, sixes: 0, sr: 105.9 },
        { id: 25, name: "Pope",    dismissal: "run out",         r:  9, b: 12, fours: 1, sixes: 0, sr:  75.0 },
      ],
      bowling: [
        { id: 6, name: "Patel",   o: 4, m: 1, r: 22, w: 4, econ: 5.5  },
        { id: 7, name: "Lyle",    o: 4, m: 0, r: 28, w: 3, econ: 7.0  },
        { id: 8, name: "Khanna",  o: 4, m: 0, r: 34, w: 1, econ: 8.5  },
        { id: 9, name: "Rivers",  o: 4, m: 0, r: 36, w: 0, econ: 9.0  },
        { id: 10, name: "Banner", o: 4, m: 0, r: 42, w: 0, econ: 10.5 },
      ],
    },
  ],
  worm: {
    // runs per over for each innings
    teams: ["Acton CC", "Marlow CC"],
    overs: Array.from({length: 20}, (_, i) => i + 1),
    series: [
      [8, 12, 6, 14, 9, 11, 8, 7, 12, 6, 9, 8, 13, 11, 9, 10, 8, 12, 7, 7],
      [6, 9, 4, 11, 7, 8, 6, 5, 10, 4, 8, 6, 11, 9, 7, 8, 6, 10, 5, 4],
    ],
  },
};

export default function MatchScorecard() {
  const { id } = useParams();
  const [m, setM] = useState(mockMatch);

  useEffect(() => {
    // WIRE: api.matches.get(id) → setM
  }, [id]);

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex items-center gap-2 font-mono text-[10.5px] tracking-wide2 text-pb-faint mb-4">
          <Link to="/matches" className="hover:text-pb-text">MATCHES</Link>
          <span>/</span>
          <span className="text-pb-dim">{m.innings[0].team.toUpperCase()} v {m.innings[1].team.toUpperCase()}</span>
        </div>

        {/* Header */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 mb-6">
          <div>
            <Label>{m.format} · {m.date} · {m.ground}</Label>
            <h1 className="font-display text-[40px] sm:text-[56px] font-bold tracking-tight leading-[0.95] mt-1.5">{m.result}</h1>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-pb-dim font-mono text-[13px] mt-2">
              <span>TOSS · <span className="text-pb-text">{m.toss}</span></span>
              <span>POM · <span style={{color:"var(--pb-accent)"}}>★</span> <span className="text-pb-text">{m.player_of_match}</span></span>
            </div>
          </div>
          <div className="flex gap-2 self-end">
            <Btn>Share</Btn>
            <Btn>Export PDF</Btn>
            <Btn primary>Highlights →</Btn>
          </div>
        </div>

        {/* Score bar */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
          {m.innings.map((inn, i) => (
            <div key={inn.team} className="pb-card p-5 flex items-baseline gap-4">
              <Label>INN {i + 1}</Label>
              <div className="flex-1 min-w-0">
                <div className="text-pb-text font-semibold text-[14px] truncate">{inn.team}</div>
                <div className="font-mono text-pb-faint text-[11px] tracking-wide2">RR {inn.rr.toFixed(2)} · {inn.overs} OV</div>
              </div>
              <div className="font-mono text-[34px] font-bold pb-num leading-none" style={{ color: i === 0 ? "var(--pb-accent)" : "var(--pb-text)" }}>
                {inn.total}
              </div>
            </div>
          ))}
        </div>

        {/* Worm */}
        <Card title="RUNS BY OVER" className="mb-6">
          <div className="h-[200px] relative">
            <Worm worm={m.worm} />
          </div>
          <div className="flex gap-4 mt-3">
            {m.worm.teams.map((t, i) => (
              <div key={t} className="flex items-center gap-2 font-mono text-[11px] tracking-wide2 text-pb-dim">
                <span className="w-3 h-[2px]" style={{ background: i === 0 ? "var(--pb-accent)" : "var(--pb-text)" }} />
                {t.toUpperCase()}
              </div>
            ))}
          </div>
        </Card>

        {/* Innings cards */}
        {m.innings.map((inn, i) => (
          <Card key={i} title={`${inn.team.toUpperCase()} · ${inn.total} (${inn.overs} ov)`} className="mb-6"
                action={<span className="font-mono text-2xs tracking-wide2 text-pb-faint">RR {inn.rr.toFixed(2)}</span>}>
            <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-5">
              {/* Batting */}
              <div>
                <Label className="block mb-2">BATTING</Label>
                <div className="overflow-x-auto pb-scroll">
                  <table className="w-full min-w-[480px] text-[13px]">
                    <thead>
                      <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                        <th className="font-medium pb-2">BATTER</th>
                        <th className="font-medium pb-2 text-right">R</th>
                        <th className="font-medium pb-2 text-right">B</th>
                        <th className="font-medium pb-2 text-right">4s</th>
                        <th className="font-medium pb-2 text-right">6s</th>
                        <th className="font-medium pb-2 text-right">SR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inn.batting.map((b, j) => (
                        <tr key={b.id} className={`${j ? "pb-hairline-t" : ""} hover:bg-pb-surface2`}>
                          <td className="py-2">
                            <div className="text-pb-text font-medium">{b.name}</div>
                            <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2">{b.dismissal}</div>
                          </td>
                          <td className="py-2 font-mono text-pb-text font-bold text-right">{b.r}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.b}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.fours}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.sixes}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.sr.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {/* Bowling */}
              <div>
                <Label className="block mb-2">BOWLING</Label>
                <div className="overflow-x-auto pb-scroll">
                  <table className="w-full min-w-[320px] text-[13px]">
                    <thead>
                      <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                        <th className="font-medium pb-2">BOWLER</th>
                        <th className="font-medium pb-2 text-right">O</th>
                        <th className="font-medium pb-2 text-right">M</th>
                        <th className="font-medium pb-2 text-right">R</th>
                        <th className="font-medium pb-2 text-right">W</th>
                        <th className="font-medium pb-2 text-right">ECON</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inn.bowling.map((b, j) => (
                        <tr key={b.id} className={`${j ? "pb-hairline-t" : ""} hover:bg-pb-surface2`}>
                          <td className="py-2 text-pb-text font-medium">{b.name}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.o}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.m}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.r}</td>
                          <td className="py-2 font-mono text-pb-text font-bold text-right">{b.w}</td>
                          <td className="py-2 font-mono text-pb-dim text-right">{b.econ.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </main>
    </div>
  );
}

// ── Worm chart ────────────────────────────────────────────────────────
function Worm({ worm }) {
  const w = 1200, h = 200, pad = 24;
  const cumulative = worm.series.map(s => s.reduce((acc, v) => [...acc, (acc[acc.length-1] || 0) + v], []));
  const max = Math.max(...cumulative.flat(), 1);
  const stepX = (w - pad * 2) / Math.max(worm.overs.length - 1, 1);
  const colors = ["var(--pb-accent)", "var(--pb-text)"];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="none">
      {/* grid */}
      {[0.25, 0.5, 0.75, 1].map(t => (
        <line key={t} x1={pad} x2={w-pad} y1={h - pad - (h - pad*2)*t} y2={h - pad - (h - pad*2)*t}
              stroke="var(--pb-hairline)" strokeWidth="1" strokeDasharray="2 4" />
      ))}
      {cumulative.map((series, idx) => {
        const d = series.map((v, i) => {
          const x = pad + i * stepX;
          const y = h - pad - (v / max) * (h - pad * 2);
          return `${i === 0 ? "M" : "L"}${x},${y}`;
        }).join(" ");
        return (
          <g key={idx}>
            <path d={d} fill="none" stroke={colors[idx]} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity={idx === 0 ? 1 : 0.85} />
          </g>
        );
      })}
      {/* axis labels */}
      {worm.overs.filter((_, i) => i % 4 === 3 || i === 0).map((o, i) => (
        <text key={o} x={pad + worm.overs.indexOf(o) * stepX} y={h - 6}
              fill="var(--pb-faint)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle">
          OV {o}
        </text>
      ))}
    </svg>
  );
}
