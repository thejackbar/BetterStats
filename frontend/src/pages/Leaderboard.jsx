// src/pages/Leaderboard.jsx — club ladder with category tabs + filters
import React, { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { AnimatedNum, Sparkline, MiniBars, Label, Card, Btn, PageHeader } from "../lib/presskit";
import { mockTopRuns, mockTopWickets } from "../lib/mockData";

const FORMATS = ["ALL", "T20", "OD", "T10"];
const GRADES = ["ALL", "1st XI", "2nd XI", "3rd XI", "CUP"];

const CATS = {
  runs:    { label: "MOST RUNS",    cols: [["RUNS","runs","int","accent"], ["AVG","avg","dec"], ["SR","sr","dec"], ["HS","hs","int"]] },
  wickets: { label: "MOST WICKETS", cols: [["WICKETS","wickets","int","accent"], ["AVG","avg","dec"], ["ECON","econ","dec"], ["BEST","best","str"]] },
  avg:     { label: "BAT AVERAGE",  cols: [["AVG","avg","dec","accent"], ["RUNS","runs","int"], ["INN","innings","int"]] },
  sr:      { label: "STRIKE RATE",  cols: [["SR","sr","dec","accent"], ["RUNS","runs","int"], ["INN","innings","int"]] },
  econ:    { label: "BEST ECONOMY", cols: [["ECON","econ","dec","accent"], ["WICKETS","wickets","int"], ["OVERS","overs","dec"]] },
};

// Tag mock rows with extra fields for the alt views
const enrich = (rows, kind) => rows.map((r, i) => ({
  ...r,
  innings: 12 + i * 2,
  overs: 24.5 + i * 4,
}));

const DATA = {
  runs:    enrich(mockTopRuns,     "bat"),
  wickets: enrich(mockTopWickets,  "bowl"),
  avg:     enrich(mockTopRuns,     "bat").sort((a,b)=>b.avg-a.avg),
  sr:      enrich(mockTopRuns,     "bat").sort((a,b)=>b.sr-a.sr),
  econ:    enrich(mockTopWickets,  "bowl").sort((a,b)=>a.econ-b.econ),
};

export default function Leaderboard() {
  const [cat, setCat] = useState("runs");
  const [fmt, setFmt] = useState("ALL");
  const [grade, setGrade] = useState("ALL");

  const rows = DATA[cat];
  const cols = CATS[cat].cols;
  const trend = cat === "wickets" || cat === "econ";

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="CLUB LEADERBOARD · 2025/26"
          title="The ladder."
          meta={[<span key="s">All categories. All grades. Live.</span>]}
        />

        {/* Category tabs */}
        <div className="flex flex-wrap gap-1 pb-hairline-b mb-4">
          {Object.entries(CATS).map(([key, c]) => (
            <button key={key} onClick={() => setCat(key)}
              className={`px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 relative ${
                cat === key ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
              }`}>
              {c.label}
              {cat === key && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: "var(--pb-accent)" }} />}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          <FilterGroup label="FORMAT" options={FORMATS} value={fmt} onChange={setFmt} />
          <FilterGroup label="GRADE"  options={GRADES}  value={grade} onChange={setGrade} />
          <div className="ml-auto"><Btn>Export CSV</Btn></div>
        </div>

        {/* Table */}
        <Card pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[800px] text-[14px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
                  <th className="font-medium py-3 pl-5 w-10">#</th>
                  <th className="font-medium py-3">PLAYER</th>
                  {cols.map(([label]) => (
                    <th key={label} className="font-medium py-3 text-right">{label}</th>
                  ))}
                  <th className="font-medium py-3 pr-5 text-right">TREND</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p, i) => (
                  <tr key={p.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2`}>
                    <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, "0")}</td>
                    <td className="py-3">
                      <Link to={`/players/${p.id}`} className="text-pb-text font-semibold hover:text-pb-accent">{p.name}</Link>
                    </td>
                    {cols.map(([label, key, kind, accent]) => (
                      <td key={label} className="py-3 text-right">
                        <span
                          className={`font-mono text-[15px] font-bold pb-num`}
                          style={{ color: accent === "accent" ? "var(--pb-accent)" : "var(--pb-text)" }}
                        >
                          {kind === "dec" ? (typeof p[key] === "number" ? <AnimatedNum value={p[key]} decimals={2} /> : "—")
                          : kind === "int" ? (typeof p[key] === "number" ? <AnimatedNum value={p[key]} /> : "—")
                          : p[key]}
                        </span>
                      </td>
                    ))}
                    <td className="py-3 pr-5 text-right">
                      <span className="inline-block" style={{ color: "var(--pb-accent)" }}>
                        {trend
                          ? <MiniBars data={p.trend} w={70} h={20} color="currentColor" gap={1.5} accentLast />
                          : <Sparkline data={p.trend} w={70} h={20} stroke="currentColor" strokeWidth={1.3} dot />}
                      </span>
                    </td>
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

function FilterGroup({ label, options, value, onChange }) {
  return (
    <div className="flex items-center gap-2">
      <Label>{label}</Label>
      <div className="flex border border-pb-hairline2 rounded overflow-hidden">
        {options.map(o => (
          <button key={o} onClick={() => onChange(o)}
            className={`px-2.5 py-1.5 font-mono text-[10.5px] tracking-wide2 ${
              value === o ? "text-pb-text bg-pb-surface2" : "text-pb-faint hover:text-pb-dim"
            }`}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}
