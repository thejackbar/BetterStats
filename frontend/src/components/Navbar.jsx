// Navbar — PressNav design with slug-based routing
import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useClub } from "../hooks/useClub";
import { useTheme } from "../contexts/ThemeContext";
import NavbarPlayerSearch from "./NavbarPlayerSearch";
import betterStatsLogo from "../assets/betterstatslogo_white.png";

export const SITE_VERSION = "v7.7.2";

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      aria-label="Toggle colour theme"
      className="shrink-0 ml-2 w-8 h-8 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition"
    >
      {isDark ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab', 'yearbook', 'yearbooks', 'games', 'fixtures', 'teams'];

function useSlug() {
  const { pathname } = useLocation();
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0];
  }
  return sessionStorage.getItem('bs_last_slug') || null;
}

function ChevronDown({ open }) {
  return (
    <svg
      width="8" height="5" viewBox="0 0 8 5" fill="currentColor"
      className={`ml-0.5 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
    >
      <path d="M0 0l4 5 4-5z" />
    </svg>
  );
}

export default function Navbar() {
  const { user } = useAuth();
  const slug = useSlug();
  const { club } = useClub(slug);
  const { pathname } = useLocation();

  const [openMenu, setOpenMenu] = useState(null);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 });
  const btnRefs = useRef({});

  // Close on navigation
  useEffect(() => { setOpenMenu(null); }, [pathname]);

  // Close on scroll
  useEffect(() => {
    if (!openMenu) return;
    const handler = () => setOpenMenu(null);
    window.addEventListener('scroll', handler, { passive: true });
    return () => window.removeEventListener('scroll', handler);
  }, [openMenu]);

  // Close on outside click
  useEffect(() => {
    if (!openMenu) return;
    const handler = (e) => {
      const panel = document.getElementById('nb-dropdown-panel');
      if (panel && panel.contains(e.target)) return;
      const trigger = btnRefs.current[openMenu];
      if (trigger && trigger.contains(e.target)) return;
      setOpenMenu(null);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [openMenu]);

  const toggleMenu = (key, e) => {
    e.preventDefault();
    e.stopPropagation();
    if (openMenu === key) { setOpenMenu(null); return; }
    const rect = e.currentTarget.getBoundingClientRect();
    setMenuPos({ top: rect.bottom, left: rect.left });
    setOpenMenu(key);
  };

  const customLogo = club?.logo_url || null;
  const displayName = club?.name || slug || "BetterStats";
  const displayShort = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 4) || "BS";

  const DROPDOWNS = slug ? {
    stats: [
      { label: "Leaderboard", href: `/${slug}/leaderboard` },
      { label: "Records",     href: `/${slug}/records` },
      { label: "Teams",       href: `/${slug}/teams` },
      { label: "Stat Lab",    href: `/${slug}/statlab` },
    ],
    games: [
      { label: "Fixtures", href: `/${slug}/fixtures` },
      { label: "Results",  href: `/${slug}/games` },
    ],
  } : {};

  const statsActive = slug && ['leaderboard', 'records', 'teams', 'statlab'].some(s =>
    pathname === `/${slug}/${s}` || pathname.startsWith(`/${slug}/${s}/`)
  );
  const gamesActive = slug && ['games', 'fixtures'].some(s =>
    pathname === `/${slug}/${s}` || pathname.startsWith(`/${slug}/${s}/`)
  );

  const NAV = slug ? [
    { type: 'link',     label: "Home",    href: `/${slug}/dashboard` },
    { type: 'link',     label: "Players", href: `/${slug}/players` },
    { type: 'dropdown', label: "Stats",   key: 'stats', isActive: statsActive },
    { type: 'dropdown', label: "Games",   key: 'games', isActive: gamesActive },
    { type: 'link',     label: "Compare", href: `/${slug}/compare` },
    { type: 'link',     label: "Yearbook",href: `/${slug}/yearbook` },
  ] : [];

  const navItemClass = (isActive) =>
    `relative px-3 py-1.5 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition flex items-center gap-0.5 ${
      isActive ? "text-pb-text" : "text-pb-faint hover:text-pb-dim"
    }`;

  return (
    <header className="sticky top-0 z-50 bg-pb-surface pb-hairline-b">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-0 h-14">

          {/* Logo / club name */}
          <Link
            to={`/${slug}`}
            className="flex items-center gap-3 mr-6 shrink-0 group"
          >
            <img
              src={customLogo || betterStatsLogo}
              alt={customLogo ? displayName : "BetterStats"}
              className="w-8 h-8 rounded object-contain"
            />
            <div className="hidden md:block leading-tight">
              <div className="text-pb-text text-[13px] font-semibold tracking-tight">{displayName}</div>
              <div className="text-pb-faint text-[10px] font-mono tracking-wide2">
                {customLogo ? slug?.toUpperCase() : "BETTERSTATS"} · {SITE_VERSION}
              </div>
            </div>
            <div className="md:hidden text-pb-text text-[13px] font-bold tracking-wide2">{displayShort}</div>
          </Link>

          {/* Nav links — scrollable on mobile */}
          <nav className="flex items-center gap-0 overflow-x-auto pb-scroll flex-1 min-w-0">
            {NAV.map((item) => {
              if (item.type === 'link') {
                return (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    end={item.href === `/${slug}/dashboard`}
                    className={({ isActive }) => navItemClass(isActive)}
                  >
                    {({ isActive }) => (
                      <>
                        {item.label}
                        {isActive && (
                          <span
                            className="absolute left-1 right-1 -bottom-[1px] h-[2px]"
                            style={{ background: "var(--pb-accent)" }}
                          />
                        )}
                      </>
                    )}
                  </NavLink>
                );
              }

              // Dropdown trigger
              const isOpen = openMenu === item.key;
              const isActive = item.isActive || isOpen;
              return (
                <button
                  key={item.key}
                  ref={el => { btnRefs.current[item.key] = el; }}
                  onClick={(e) => toggleMenu(item.key, e)}
                  className={navItemClass(isActive)}
                >
                  {item.label}
                  <ChevronDown open={isOpen} />
                  {item.isActive && !isOpen && (
                    <span
                      className="absolute left-1 right-1 -bottom-[1px] h-[2px]"
                      style={{ background: "var(--pb-accent)" }}
                    />
                  )}
                </button>
              );
            })}
          </nav>

          <NavbarPlayerSearch orgId={club?.id} club={club} />
          <ThemeToggle />

          {customLogo && (
            <Link
              to="/"
              className="flex items-center gap-1.5 shrink-0 ml-3 group"
              title="Powered by BetterStats"
            >
              <span className="hidden sm:block text-pb-faint text-[9px] font-mono tracking-wide2 uppercase">
                Powered by
              </span>
              <img
                src={betterStatsLogo}
                alt="BetterStats"
                className="w-6 h-6 object-contain opacity-75 group-hover:opacity-100 transition"
              />
            </Link>
          )}
        </div>
      </div>

      {/* Dropdown panel — rendered via portal to escape overflow-x-auto */}
      {openMenu && DROPDOWNS[openMenu] && createPortal(
        <div
          id="nb-dropdown-panel"
          style={{ position: 'fixed', top: menuPos.top, left: menuPos.left, zIndex: 200 }}
          className="bg-pb-surface border pb-hairline rounded-b shadow-xl py-1 min-w-[140px]"
        >
          {DROPDOWNS[openMenu].map(item => (
            <NavLink
              key={item.href}
              to={item.href}
              onClick={() => setOpenMenu(null)}
              className={({ isActive }) =>
                `block px-4 py-2 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${
                  isActive
                    ? 'text-pb-text bg-pb-surface2'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>,
        document.body
      )}
    </header>
  );
}
