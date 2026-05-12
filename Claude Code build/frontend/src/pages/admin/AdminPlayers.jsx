// src/pages/admin/AdminPlayers.jsx — players roster CRUD (light touch)
import React, { useState } from "react";
import { Label, Btn, Card } from "../../lib/presskit";

const ROSTER = [
  { id: 1,  name: "Jack Banner",    role: "Top-order bat", grade: "1st XI", active: true,  pc_id: "PC-19283" },
  { id: 2,  name: "Tom Whitfield",  role: "Mid-order bat", grade: "1st XI", active: true,  pc_id: "PC-19501" },
  { id: 3,  name: "Reggie Stone",   role: "All-rounder",   grade: "1st XI", active: true,  pc_id: "PC-19772" },
  { id: 6,  name: "Asha Patel",     role: "Right-arm med", grade: "1st XI", active: true,  pc_id: "PC-20114" },
  { id: 7,  name: "Marcus Lyle",    role: "Right-arm fst", grade: "2nd XI", active: true,  pc_id: "PC-20221" },
  { id: 21, name: "Eli Carrington", role: "Wicket-keeper", grade: "3rd XI", active: false, pc_id: "PC-21010" },
];

export default function AdminPlayers() {
  const [q, setQ] = useState("");
  const rows = ROSTER.filter(r => r.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3 mb-5">
        <div>
          <Label>ADMIN · ROSTER</Label>
          <h1 className="font-display text-[32px] font-bold tracking-tight mt-1">Players</h1>
          <div className="font-mono text-[11px] text-pb-faint tracking-wide2 mt-1">
            <span className="text-pb-text">{ROSTER.length}</span> registered · linked to Play-Cricket
          </div>
        </div>
        <div className="flex gap-2">
          <Btn>Import from Play-Cricket</Btn>
          <Btn primary>Add player →</Btn>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3 mb-3">
        <input
          value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search by name…"
          className="bg-pb-surface border border-pb-hairline2 rounded px-3 py-2 text-[13px] text-pb-text placeholder:text-pb-faint w-full sm:w-72 outline-none focus:border-pb-accent"
        />
        <span className="font-mono text-[11px] text-pb-faint tracking-wide2">SHOWING {rows.length}</span>
      </div>

      <Card pad="p-0">
        <div className="overflow-x-auto pb-scroll">
          <table className="w-full min-w-[760px] text-[13px]">
            <thead>
              <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                <th className="font-medium py-3 pl-4">NAME</th>
                <th className="font-medium py-3">ROLE</th>
                <th className="font-medium py-3">GRADE</th>
                <th className="font-medium py-3">PC ID</th>
                <th className="font-medium py-3">STATUS</th>
                <th className="font-medium py-3 pr-4 text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2`}>
                  <td className="py-2.5 pl-4 text-pb-text font-medium">{r.name}</td>
                  <td className="py-2.5 text-pb-dim">{r.role}</td>
                  <td className="py-2.5 font-mono text-pb-dim text-[12px]">{r.grade}</td>
                  <td className="py-2.5 font-mono text-pb-faint text-[11px] tracking-wide2">{r.pc_id}</td>
                  <td className="py-2.5">
                    <span className="font-mono text-2xs tracking-wide2 px-2 py-0.5 rounded-sm"
                          style={{
                            color: r.active ? "var(--pb-accent)" : "var(--pb-faint)",
                            background: r.active ? "rgba(22,199,132,0.10)" : "rgba(138,144,162,0.08)",
                            border: `1px solid ${r.active ? "rgba(22,199,132,0.25)" : "rgba(138,144,162,0.18)"}`,
                          }}>
                      {r.active ? "ACTIVE" : "INACTIVE"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-right">
                    <button className="text-pb-faint hover:text-pb-text font-mono text-[10.5px] tracking-wide2 mr-3">EDIT</button>
                    <button className="text-pb-faint hover:text-pb-red font-mono text-[10.5px] tracking-wide2">REMOVE</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
