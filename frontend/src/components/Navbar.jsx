// Navbar — PressNav design with slug-based routing
import React, { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Ticker } from "../lib/presskit";

function useClubSlug() {
  const { pathname } = useLocation();
  const segments = pathname.split('/').filter(Boolean);
  const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab', 'yearbook'];
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0];
  }
  return sessionStorage.getItem('bs_last_slug') || null;
}

function useClubName(slug) {
  const [name, setName] = useState(null);
  const [short, setShort] = useState(null);
  useEffect(() => {
    if (!slug) return;
    const stored = sessionStorage.getItem(`bs_club_${slug}`);
    if (stored) {
      try {
        const c = JSON.parse(stored);
        setName(c.name);
        setShort(c.short_name || c.name?.split(' ').map(w => w[0]).join('').slice(0, 5));
      } catch {}
    }
  }, [slug]);
  return { name, short };
}

export default function Navbar() {
  const [now, setNow] = useState(new Date());
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const clubSlug = useClubSlug();
  const { name: clubName, short: clubShort } = useClubName(clubSlug);

  const navLinks = clubSlug
    ? [
        { to: `/${clubSlug}/dashboard`,   label: 'DASHBOARD' },
        { to: `/${clubSlug}/players`,     label: 'PLAYERS' },
        { to: `/${clubSlug}/leaderboard`, label: 'LEADERBOARD' },
        { to: `/${clubSlug}/records`,     label: 'RECORDS' },
        { to: `/${clubSlug}/statlab`,     label: 'STAT LAB' },
        { to: `/${clubSlug}/compare`,     label: 'COMPARE' },
        { to: `/${clubSlug}/yearbook`,    label: 'YEARBOOK' },
      ]
    : [];

  const displayName = clubName || 'BetterStats';
  const displayShort = clubShort || 'BS';
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const tickerItems = clubName
    ? [`${displayName.toUpperCase()} — SEASON STATS`]
    : ['CRICKET STATS, OBSESSED OVER'];

  return (
    <header className="sticky top-0 z-40 bg-pb-bg/95 backdrop-blur supports-[backdrop-filter]:bg-pb-bg/80 pb-hairline-b">
      {/* Row 1 — brand + nav + utility */}
      <div className="flex items-stretch h-14 pl-3 sm:pl-4 pr-2 sm:pr-3">
        {/* Brand */}
        <Link to={clubSlug ? `/${clubSlug}/dashboard` : '/'} className="flex items-center gap-3 pr-4 sm:pr-5 mr-2 sm:mr-3 pb-hairline-r shrink-0">
          <div
            className="font-mono text-[11px] font-bold tracking-wide3 px-1.5 py-0.5 rounded-sm"
            style={{ background: "var(--pb-accent)", color: "#08110b" }}
          >
            BS
          </div>
          <div className="hidden md:block leading-tight">
            <div className="text-pb-text text-[13px] font-semibold tracking-tight">{displayName}</div>
            <div className="text-pb-faint text-[10px] font-mono tracking-wide2">BETTERSTATS · v4.9.1</div>
          </div>
          <div className="md:hidden text-pb-text text-[13px] font-bold tracking-wide2">{displayShort}</div>
        </Link>

        {/* Nav */}
        <nav className="flex items-stretch overflow-x-auto pb-scroll min-w-0 flex-1">
          {navLinks.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to.endsWith('/dashboard')}
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
          {!clubSlug && (
            <>
              <NavLink to="/features" className={({ isActive }) => `relative flex items-center px-3 sm:px-4 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${isActive ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"}`}>FEATURES</NavLink>
              <NavLink to="/pricing" className={({ isActive }) => `relative flex items-center px-3 sm:px-4 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${isActive ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"}`}>PRICING</NavLink>
            </>
          )}
        </nav>

        {/* Utility */}
        <div className="hidden md:flex items-center gap-2 pl-3 pb-hairline-r mr-3">
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint">{time}</div>
        </div>
        <div className="hidden sm:flex items-center pr-1">
          <Link
            to="/login"
            className="font-mono text-[11px] tracking-wide2 px-3 py-1.5 rounded border border-pb-hairline2 text-pb-text hover:bg-pb-surface2 transition"
          >
            ADMIN
          </Link>
        </div>

        {/* Mobile hamburger */}
        {navLinks.length > 0 && (
          <button
            className="sm:hidden flex items-center px-2 text-pb-faint hover:text-pb-text"
            onClick={() => setMenuOpen(o => !o)}
            aria-label="Toggle menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {menuOpen
                ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              }
            </svg>
          </button>
        )}
      </div>

      {/* Mobile dropdown */}
      {menuOpen && navLinks.length > 0 && (
        <div className="sm:hidden bg-pb-surface pb-hairline-b pb-hairline-t">
          {navLinks.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `block px-4 py-2.5 font-mono text-[11px] tracking-wide3 ${isActive ? "text-pb-text bg-pb-surface2" : "text-pb-faint"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </div>
      )}

      {/* Row 2 — ticker */}
      <div className="flex items-stretch h-7 pb-hairline-b bg-pb-surface">
        <div
          className="px-3 flex items-center font-mono text-[10px] font-bold tracking-wide3 pb-hairline-r"
          style={{ color: "var(--pb-accent)" }}
        >
          <span className="w-1.5 h-1.5 rounded-full mr-2 pb-pulse" style={{ background: "var(--pb-accent)" }} />
          LIVE
        </div>
        <Ticker
          items={tickerItems}
          className="flex-1 font-mono text-[10.5px] tracking-wide2 text-pb-dim flex items-center"
          speed={42}
        />
      </div>
    </header>
  );
}
