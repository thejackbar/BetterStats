// src/components/admin/AdminLayout.jsx — quiet, dense admin chrome
import React from "react";
import { NavLink, Outlet, Link } from "react-router-dom";

const ADMIN_NAV = [
  { to: "/admin",          label: "OVERVIEW",  end: true },
  { to: "/admin/sync",     label: "SYNC" },
  { to: "/admin/players",  label: "PLAYERS" },
  { to: "/admin/matches",  label: "MATCHES" },
  { to: "/admin/settings", label: "SETTINGS" },
];

export default function AdminLayout() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      {/* Slim admin bar */}
      <div className="pb-hairline-b bg-pb-surface">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-11 flex items-center gap-4">
          <Link to="/" className="font-mono text-[10.5px] tracking-wide2 text-pb-faint hover:text-pb-text">← BACK TO CLUB</Link>
          <span className="pb-hairline-r h-5" />
          <span className="font-mono text-[10.5px] tracking-wide3 font-bold" style={{ color: "var(--pb-accent)" }}>ADMIN CONSOLE</span>
          <nav className="flex items-stretch ml-6 overflow-x-auto pb-scroll">
            {ADMIN_NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) =>
                  `relative px-3 flex items-center text-[10.5px] font-mono font-semibold tracking-wide3 ${
                    isActive ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
                  }`}>
                {({ isActive }) => (<>
                  {n.label}
                  {isActive && <span className="absolute left-3 right-3 bottom-0 h-[2px]" style={{ background: "var(--pb-accent)" }} />}
                </>)}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto font-mono text-[10.5px] tracking-wide2 text-pb-faint hidden sm:block">ACTON CC · ADMIN</div>
        </div>
      </div>
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
