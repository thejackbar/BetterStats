// src/pages/Records.jsx — club hall of records
import React from "react";
import { Link } from "react-router-dom";
import { AnimatedNum, Label, Card, PageHeader } from "../lib/presskit";

const RECORDS = {
  batting: [
    { rank: 1, title: "Highest individual score",   value: "187*", player: "Jack Banner",   detail: "v Wembley CC · 2025-08-14",        kind: "highlight" },
    { rank: 2, title: "Highest match aggregate",    value: "162",  player: "Tom Whitfield", detail: "78+84 v Pinner CC · 2024-07-20" },
    { rank: 3, title: "Fastest century (balls)",    value: "44",   player: "Reggie Stone",  detail: "v Northwood CC · 2023-09-02" },
    { rank: 4, title: "Most career runs",           value: "2,841",player: "Jack Banner",   detail: "2019-present (78 mat)" },
    { rank: 5, title: "Most career centuries",      value: "4",    player: "Jack Banner",   detail: "2019-present" },
    { rank: 6, title: "Most sixes in an innings",   value: "9",    player: "Henry Vaughn",  detail: "v Brentham · 2024-05-11" },
  ],
  bowling: [
    { rank: 1, title: "Best bowling figures",       value: "7/24", player: "Asha Patel",   detail: "v Marlow CC · 2024-08-03",         kind: "highlight" },
    { rank: 2, title: "Best career economy (min 50 ov)", value: "3.84", player: "Asha Patel", detail: "2019-present" },
    { rank: 3, title: "Most wickets in a season",   value: "58",   player: "Marcus Lyle",  detail: "2023/24 season" },
    { rank: 4, title: "Most career wickets",        value: "211",  player: "Asha Patel",   detail: "2019-present" },
    { rank: 5, title: "Fastest five-fer (balls)",   value: "21",   player: "Dev Khanna",   detail: "v Ealing · 2025-04-22" },
    { rank: 6, title: "Hat-tricks",                 value: "3",    player: "Marcus Lyle",  detail: "2022, 2023, 2024" },
  ],
  team: [
    { rank: 1, title: "Highest team total",         value: "284/3", player: "ACTON CC",    detail: "v Ruislip CC · 2024-06-15",        kind: "highlight" },
    { rank: 2, title: "Lowest opponent total",      value: "48 a.o.",player: "v Wembley CC",detail: "2023-07-12 · won by 156 runs" },
    { rank: 3, title: "Largest margin (runs)",      value: "187",   player: "v Northwood", detail: "2024-08-31" },
    { rank: 4, title: "Longest winning streak",     value: "11",    player: "—",           detail: "2023 season" },
    { rank: 5, title: "Most consecutive 200+ totals", value: "5",   player: "—",           detail: "2024 season" },
  ],
};

const SECTIONS = [
  { key: "batting", label: "BATTING", icon: "▲" },
  { key: "bowling", label: "BOWLING", icon: "●" },
  { key: "team",    label: "TEAM",    icon: "■" },
];

export default function Records() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="HALL OF RECORDS · ACTON CC"
          title="The record books."
          meta={[<span key="x">Every club benchmark, sortable, since 2019.</span>]}
        />

        {SECTIONS.map(s => (
          <section key={s.key} className="mb-8">
            <div className="flex items-baseline gap-3 mb-3">
              <span className="font-mono text-[11px] tracking-wide3" style={{ color: "var(--pb-accent)" }}>{s.icon}</span>
              <h2 className="font-display text-[26px] font-bold tracking-tight text-pb-text">{s.label}</h2>
              <span className="font-mono text-2xs tracking-wide2 text-pb-faint ml-auto">{RECORDS[s.key].length} RECORDS</span>
            </div>

            <Card pad="p-0">
              <ul className="flex flex-col">
                {RECORDS[s.key].map((r, i) => (
                  <li key={r.rank} className={`${i ? "pb-hairline-t" : ""} grid grid-cols-[40px_1fr_auto] sm:grid-cols-[60px_1fr_auto_auto] gap-3 sm:gap-5 items-center px-4 sm:px-5 py-4 hover:bg-pb-surface2 transition`}>
                    <span className="font-mono text-pb-faint text-[12px] tracking-wide2">#{r.rank}</span>
                    <div className="min-w-0">
                      <div className="font-mono text-pb-faint text-[10px] tracking-wide3 uppercase">{r.title}</div>
                      <div className="text-pb-text text-[14px] font-semibold mt-0.5 truncate">{r.player}</div>
                      <div className="font-mono text-pb-dim text-[11px] tracking-wide2 mt-0.5 hidden sm:block">{r.detail}</div>
                    </div>
                    <span
                      className="font-mono text-[28px] sm:text-[34px] font-bold pb-num leading-none"
                      style={{ color: r.kind === "highlight" ? "var(--pb-accent)" : "var(--pb-text)" }}
                    >
                      {r.value}
                    </span>
                    <span className="hidden sm:inline-flex text-pb-faint hover:text-pb-text font-mono text-[10px] tracking-wide2 cursor-pointer">DETAIL →</span>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        ))}

        <div className="pb-card p-5 flex items-center justify-between flex-wrap gap-3">
          <div>
            <Label>SUGGEST A RECORD</Label>
            <div className="text-pb-text mt-1 text-[14px]">Spotted a gap? Tell us what to track.</div>
          </div>
          <Link to="/feedback" className="text-2xs font-mono tracking-wide2 px-3 py-2 rounded border border-pb-hairline2 text-pb-text hover:bg-pb-surface2">
            SEND SUGGESTION →
          </Link>
        </div>
      </main>
    </div>
  );
}
