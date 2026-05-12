// src/pages/PlayerProfile.jsx — BetterStats Press Box Player Profile
// Drop in as PlayerProfileV2.jsx, or replace PlayerProfile.jsx outright.
// Real-data wiring: see "// WIRE:" comments.

import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  AnimatedNum, Sparkline, MiniBars, Label, Card, Btn,
  ResultPill, Kpi, PageHeader,
} from "../lib/presskit";
import { mockPlayer, fetchOrMock } from "../lib/mockData";
// import api from "../lib/api"; // WIRE: enable when integrating real endpoints

export default function PlayerProfile() {
  const { id } = useParams();
  const [p, setP] = useState(mockPlayer);
  const [tab, setTab] = useState("OVERVIEW"); // OVERVIEW · BATTING · BOWLING · MATCHES

  useEffect(() => {
    let alive = true;
    (async () => {
      // WIRE: replace with api.players.get(id)
      // const data = await fetchOrMock(api.players.get(id), mockPlayer);
      // if (alive) setP(data);
    })();
    return () => { alive = false; };
  }, [id]);

  const c = p.career, s = p.season;

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 font-mono text-[10.5px] tracking-wide2 text-pb-faint mb-4">
          <Link to="/players" className="hover:text-pb-text">PLAYERS</Link>
          <span>/</span>
          <span className="text-pb-dim">{p.name.toUpperCase()}</span>
        </div>

        {/* Hero */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 mb-6 items-end">
          <div>
            <Label>#{p.jersey} · {p.role} · {p.bat_hand} / {p.bowl_hand}</Label>
            <h1 className="font-display text-[56px] sm:text-[80px] font-bold tracking-tight leading-[0.92] mt-1.5 text-pb-text">
              {p.name}
            </h1>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-pb-dim font-mono text-[13px] mt-2">
              <span>MEMBER SINCE <span className="text-pb-text">{p.member_since}</span></span>
              <span><span className="text-pb-text">{c.matches}</span> CAREER MATCHES</span>
              <span><span className="text-pb-text">{c.runs_scored.toLocaleString()}</span> CAREER RUNS</span>
              <span><span className="text-pb-text">{c.centuries}</span> CENTURIES</span>
            </div>
          </div>
          <div className="flex gap-2">
            <Btn>Compare</Btn>
            <Btn>Export PDF</Btn>
            <Btn primary>Follow ★</Btn>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 pb-hairline-b mb-5">
          {["OVERVIEW", "BATTING", "BOWLING", "MATCHES"].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 relative ${
                tab === t ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
              }`}
            >
              {t}
              {tab === t && (
                <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: "var(--pb-accent)" }} />
              )}
            </button>
          ))}
        </div>

        {/* Season KPI strip */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
          <Kpi label="2025/26 RUNS"   value={s.runs_scored} accent />
          <Kpi label="AVERAGE"        value={s.average}     decimals={1} />
          <Kpi label="STRIKE RATE"    value={s.strike_rate} decimals={1} />
          <Kpi label="HIGH SCORE"     value={s.high_score}  />
          <Kpi label="100s · 50s"     value={`${s.centuries} · ${s.fifties}`} />
        </div>

        {/* Career bar — what makes this profile different */}
        <Card title="CAREER TOTALS" className="mb-6"
              action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">SINCE {p.member_since}</span>}>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-x-6 gap-y-3">
            {[
              ["MATCHES", c.matches],
              ["INNINGS", c.innings],
              ["RUNS",    c.runs_scored, "accent"],
              ["AVERAGE", c.average.toFixed(1)],
              ["SR",      c.strike_rate.toFixed(1)],
              ["HS",      c.high_score],
              ["100s · 50s", `${c.centuries} · ${c.fifties}`],
              ["4s · 6s",    `${c.fours} · ${c.sixes}`],
            ].map(([label, value, kind]) => (
              <div key={label} className="flex flex-col">
                <span className="text-pb-faint font-mono text-[9.5px] tracking-wide3">{label}</span>
                <span
                  className="font-mono font-bold text-[22px] pb-num leading-tight mt-0.5"
                  style={{ color: kind === "accent" ? "var(--pb-accent)" : "var(--pb-text)" }}
                >
                  {typeof value === "number" ? <AnimatedNum value={value} /> : value}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Last 14 innings line + dismissal pie */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mb-6">
          <Card title={`LAST ${p.recent_form.length} INNINGS · RUNS`} className="xl:col-span-2"
                action={<span className="font-mono text-2xs tracking-wide2 text-pb-faint">AVG {(p.recent_form.reduce((a,b)=>a+b,0)/p.recent_form.length).toFixed(1)}</span>}>
            <div className="h-[160px] flex items-end" style={{ color: "var(--pb-accent)" }}>
              <Sparkline data={p.recent_form} w={920} h={150} stroke="currentColor" fill="currentColor" strokeWidth={1.6} dot />
            </div>
            <div className="flex justify-between pb-dashed-t pt-2 mt-1 font-mono text-[10px] text-pb-faint tracking-wide2">
              {p.recent_form.map((v, i) => <span key={i} className="tabular-nums">{v}</span>)}
            </div>
          </Card>

          <Card title="DISMISSAL SPLIT">
            <ul className="flex flex-col gap-2.5">
              {p.dismissal_split.map(d => (
                <li key={d.type} className="flex items-center gap-3">
                  <span className="w-20 text-pb-dim font-mono text-[11px] tracking-wide2 uppercase">{d.type}</span>
                  <div className="flex-1 h-1 bg-pb-hairline rounded-sm overflow-hidden">
                    <div className="h-full" style={{
                      width: `${d.pct}%`,
                      background: d.type === "Not out" ? "var(--pb-accent)" : "var(--pb-text)",
                      opacity: d.type === "Not out" ? 1 : 0.78,
                    }}/>
                  </div>
                  <span className="font-mono text-[12px] text-pb-text pb-num w-8 text-right">{d.pct}%</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        {/* Splits — by grade + by position */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-6">
          <SplitTable title="BY GRADE" rows={p.by_grade} colKey="grade" />
          <SplitTable title="BY POSITION" rows={p.by_position} colKey="position" />
        </div>

        {/* Milestones in reach */}
        <Card title="MILESTONES IN REACH" className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {p.upcoming_milestones.map(m => {
              const pct = Math.min(100, Math.round((m.current / m.target_value) * 100));
              return (
                <div key={m.target} className="pb-card-2 p-4 rounded">
                  <Label>{m.target}</Label>
                  <div className="flex items-baseline justify-between mt-2 mb-2">
                    <span className="font-mono text-[26px] font-bold pb-num leading-none">
                      <AnimatedNum value={m.current} />
                    </span>
                    <span className="font-mono text-[11px] text-pb-dim tracking-wide2">/ {m.target_value.toLocaleString()}</span>
                  </div>
                  <div className="h-1 bg-pb-hairline rounded-sm overflow-hidden">
                    <div className="h-full" style={{ width: `${pct}%`, background: "var(--pb-accent)" }} />
                  </div>
                  <div className="font-mono text-[10.5px] text-pb-faint tracking-wide2 mt-1.5">{pct}%</div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Recent innings table */}
        <Card title="RECENT INNINGS"
              action={<Link to={`/players/${id}/innings`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
          <div className="overflow-x-auto pb-scroll -mx-2">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="font-medium pb-2 pl-2">DATE</th>
                  <th className="font-medium pb-2">OPPONENT</th>
                  <th className="font-medium pb-2">SCORE</th>
                  <th className="font-medium pb-2">4s</th>
                  <th className="font-medium pb-2">6s</th>
                  <th className="font-medium pb-2">SR</th>
                  <th className="font-medium pb-2 pr-2">RESULT</th>
                </tr>
              </thead>
              <tbody>
                {p.recent_innings.map((inn, i) => (
                  <tr key={inn.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2 cursor-pointer`}>
                    <td className="py-2.5 pl-2 font-mono text-pb-dim text-[12px]">{inn.date}</td>
                    <td className="py-2.5 text-pb-text font-medium">{inn.opp}</td>
                    <td className="py-2.5 font-mono text-pb-text font-bold">{inn.score}</td>
                    <td className="py-2.5 font-mono text-pb-dim">{inn.fours}</td>
                    <td className="py-2.5 font-mono text-pb-dim">{inn.sixes}</td>
                    <td className="py-2.5 font-mono text-pb-dim">{inn.sr.toFixed(1)}</td>
                    <td className="py-2.5 pr-2"><ResultPill result={inn.result} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </main>
    </div>
  );
}

// ── Splits sub-table ───────────────────────────────────────────────────
function SplitTable({ title, rows, colKey }) {
  const max = Math.max(...rows.map(r => r.runs));
  return (
    <div className="pb-card p-4 sm:p-[18px]">
      <div className="flex items-center justify-between mb-3.5">
        <Label>{title}</Label>
        <span className="font-mono text-2xs tracking-wide2 text-pb-faint">RUNS · AVG · SR</span>
      </div>
      <ul className="flex flex-col">
        {rows.map((r, i) => {
          const pct = (r.runs / max) * 100;
          return (
            <li key={r[colKey]} className={`${i ? "pb-hairline-t" : ""} py-2.5`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-pb-text text-[13px] font-semibold w-24 truncate">{r[colKey]}</span>
                <span className="font-mono text-pb-faint text-[10.5px] tracking-wide2 flex-1 text-right">
                  INN {r.innings} · AVG {r.avg.toFixed(1)} · SR {r.sr.toFixed(1)}
                </span>
                <span className="font-mono text-pb-text text-[15px] font-bold pb-num w-14 text-right">
                  <AnimatedNum value={r.runs} />
                </span>
              </div>
              <div className="h-[3px] bg-pb-hairline rounded-sm overflow-hidden mt-2">
                <div className="h-full" style={{ width: `${pct}%`, background: "var(--pb-accent)" }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
