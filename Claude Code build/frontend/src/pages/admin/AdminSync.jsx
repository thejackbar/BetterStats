// src/pages/admin/AdminSync.jsx — Play-Cricket sync console (quiet)
import React, { useState } from "react";
import { Label, Btn, Card, AnimatedNum } from "../../lib/presskit";

const HISTORY = [
  { id: 1, when: "2026-05-11 09:32", who: "Auto",  status: "OK",     added: 3,  updated: 12, took: "1m 04s" },
  { id: 2, when: "2026-05-10 09:31", who: "Auto",  status: "OK",     added: 0,  updated:  6, took: "0m 48s" },
  { id: 3, when: "2026-05-09 16:12", who: "Jack",  status: "OK",     added: 11, updated:  4, took: "1m 22s" },
  { id: 4, when: "2026-05-08 09:31", who: "Auto",  status: "WARN",   added: 0,  updated:  0, took: "0m 18s", note: "Play-Cricket rate-limited; retried" },
  { id: 5, when: "2026-05-07 09:32", who: "Auto",  status: "OK",     added: 2,  updated:  3, took: "0m 41s" },
];

export default function AdminSync() {
  const [running, setRunning] = useState(false);
  return (
    <>
      <header className="flex items-end justify-between gap-3 mb-5">
        <div>
          <Label>ADMIN · DATA SYNC</Label>
          <h1 className="font-display text-[32px] font-bold tracking-tight mt-1">Play-Cricket sync</h1>
          <div className="font-mono text-[11px] text-pb-faint tracking-wide2 mt-1">LAST RUN <span className="text-pb-text">2026-05-11 09:32</span> · OK · NEXT IN 14h 21m</div>
        </div>
        <Btn primary onClick={() => { setRunning(true); setTimeout(() => setRunning(false), 1800); }}>
          {running ? "Syncing…" : "Run sync now →"}
        </Btn>
      </header>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <Stat label="MATCHES SYNCED"  value={184} />
        <Stat label="PLAYERS"          value={47} />
        <Stat label="ERRORS · 30d"     value={0} accent />
        <Stat label="UPTIME · 30d"     value={99.8} decimals={1} suffix="%" accent />
      </div>

      <Card title="RECENT SYNCS" pad="p-0">
        <div className="overflow-x-auto pb-scroll">
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                <th className="font-medium py-3 pl-4">WHEN</th>
                <th className="font-medium py-3">TRIGGER</th>
                <th className="font-medium py-3">STATUS</th>
                <th className="font-medium py-3 text-right">ADDED</th>
                <th className="font-medium py-3 text-right">UPDATED</th>
                <th className="font-medium py-3 text-right">DURATION</th>
                <th className="font-medium py-3 pr-4">NOTE</th>
              </tr>
            </thead>
            <tbody>
              {HISTORY.map((h, i) => (
                <tr key={h.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2`}>
                  <td className="py-2.5 pl-4 font-mono text-pb-dim">{h.when}</td>
                  <td className="py-2.5 text-pb-text">{h.who}</td>
                  <td className="py-2.5">
                    <span className="font-mono text-2xs tracking-wide2 px-2 py-0.5 rounded-sm"
                          style={{
                            color: h.status === "OK" ? "var(--pb-accent)" : "var(--pb-amber)",
                            background: (h.status === "OK" ? "rgba(22,199,132,0.10)" : "rgba(245,181,66,0.10)"),
                            border: `1px solid ${h.status === "OK" ? "rgba(22,199,132,0.25)" : "rgba(245,181,66,0.25)"}`,
                          }}>
                      {h.status}
                    </span>
                  </td>
                  <td className="py-2.5 font-mono text-pb-text text-right pb-num">{h.added}</td>
                  <td className="py-2.5 font-mono text-pb-text text-right pb-num">{h.updated}</td>
                  <td className="py-2.5 font-mono text-pb-dim text-right">{h.took}</td>
                  <td className="py-2.5 pr-4 font-mono text-pb-faint text-[11px] tracking-wide2 truncate">{h.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function Stat({ label, value, suffix = "", decimals = 0, accent = false }) {
  return (
    <div className="pb-card p-4">
      <Label>{label}</Label>
      <div className="font-mono text-[28px] font-bold pb-num mt-2 leading-none"
           style={{ color: accent ? "var(--pb-accent)" : "var(--pb-text)" }}>
        <AnimatedNum value={value} decimals={decimals} suffix={suffix} />
      </div>
    </div>
  );
}
