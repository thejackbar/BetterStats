// src/components/PressNav.jsx
// Top chrome: brand block + sectioned nav + live ticker + season meta.
// Drops in as your Navbar replacement (or rename to NavbarV2 if you prefer).

import React, { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Ticker } from "../lib/presskit";

const NAV = [
  { to: "/",            label: "DASHBOARD" },
  { to: "/players",     label: "PLAYERS" },
  { to: "/matches",     label: "MATCHES" },
  { to: "/leaderboard", label: "LEADERBOARD" },
  { to: "/compare",     label: "COMPARE" },
  { to: "/stat-lab",    label: "STAT LAB" },
  { to: "/records",     label: "RECORDS" },
];

export default function PressNav({
  clubName = "Acton Cricket Club",
  clubShort = "ACTON",
  season = "2025/26",
  tickerItems = [
    "ACTON 187/4 BEAT MARLOW 164/8 BY 23 RUNS",
    "J. BANNER 78(42) — PLAYER OF MATCH",
    "A. PATEL 4/22 — SEASON BEST",
    "NEXT FIXTURE — HARROW TOWN, SAT 16 MAY 13:30",
  ],
}) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <header className="sticky top-0 z-40 bg-pb-bg/95 backdrop-blur supports-[backdrop-filter]:bg-pb-bg/80 pb-hairline-b">
      {/* Row 1 — brand + nav + utility */}
      <div className="flex items-stretch h-14 pl-3 sm:pl-4 pr-2 sm:pr-3">
        {/* Brand */}
        <Link to="/" className="flex items-center gap-3 pr-4 sm:pr-5 mr-2 sm:mr-3 pb-hairline-r">
          <div
            className="font-mono text-[11px] font-bold tracking-wide3 px-1.5 py-0.5 rounded-sm"
            style={{ background: "var(--pb-accent)", color: "#08110b" }}
          >
            BS
          </div>
          <div className="hidden md:block leading-tight">
            <div className="text-pb-text text-[13px] font-semibold tracking-tight">{clubName}</div>
            <div className="text-pb-faint text-[10px] font-mono tracking-wide2">BETTERSTATS · {season}</div>
          </div>
          <div className="md:hidden text-pb-text text-[13px] font-bold tracking-wide2">{clubShort}</div>
        </Link>

        {/* Nav */}
        <nav className="flex items-stretch overflow-x-auto pb-scroll min-w-0 flex-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `relative flex items-center px-3 sm:px-4 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${
                  isActive ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {n.label}
                  {isActive && (
                    <span
                      className="absolute left-3 right-3 sm:left-4 sm:right-4 bottom-0 h-[2px]"
                      style={{ background: "var(--pb-accent)" }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Utility */}
        <div className="hidden md:flex items-center gap-2 pl-3 pb-hairline-r mr-3">
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint">{time} · LDN</div>
        </div>
        <div className="hidden sm:flex items-center pr-1">
          <button className="font-mono text-[11px] tracking-wide2 px-3 py-1.5 rounded border border-pb-hairline2 text-pb-text hover:bg-pb-surface2 transition">
            SIGN IN
          </button>
        </div>
      </div>

      {/* Row 2 — ticker */}
      <div className="flex items-stretch h-7 pb-hairline-b bg-pb-surface">
        <div
          className="px-3 flex items-center font-mono text-[10px] font-bold tracking-wide3 pb-hairline-r"
          style={{ color: "var(--pb-accent)" }}
        >
          <span className="w-1.5 h-1.5 rounded-full mr-2 pb-pulse" style={{ background: "var(--pb-accent)" }} />
          WIRE
        </div>
        <Ticker items={tickerItems} className="flex-1 font-mono text-[10.5px] tracking-wide2 text-pb-dim flex items-center" speed={42} />
      </div>
    </header>
  );
}
