// Navbar — PressNav design with slug-based routing
import React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useClub } from "../hooks/useClub";
import betterStatsLogo from "../assets/betterstatslogo_white.png";

export const SITE_VERSION = "v5.5.2.2";

const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab', 'yearbook', 'yearbooks', 'games'];

function useSlug() {
  const { pathname } = useLocation();
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0];
  }
  return sessionStorage.getItem('bs_last_slug') || null;
}

export default function Navbar() {
  const { user } = useAuth();
  const slug = useSlug();
  const { club } = useClub(slug);

  // White-labelling: when a club has uploaded a custom logo, it takes the
  // top-left slot and the BetterStats logo moves to the top-right.
  const customLogo = club?.logo_url || null;

  const displayName = club?.name || slug || "BetterStats";
  const displayShort = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 4) || "BS";

  const NAV = slug ? [
    { label: "Dashboard",   href: `/${slug}/dashboard` },
    { label: "Players",     href: `/${slug}/players` },
    { label: "Leaderboard", href: `/${slug}/leaderboard` },
    { label: "Records",     href: `/${slug}/records` },
    { label: "Yearbook",    href: `/${slug}/yearbook` },
    { label: "Games",       href: `/${slug}/games` },
    { label: "Stat Lab",    href: `/${slug}/statlab` },
    { label: "Compare",     href: `/${slug}/compare` },
  ] : [];

  const allLinks = [...NAV];

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
            {allLinks.map((item) => (
              <NavLink
                key={item.href}
                to={item.href}
                end={item.href === `/${slug}`}
                className={({ isActive }) =>
                  `relative px-3 py-1.5 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${
                    isActive
                      ? "text-pb-text"
                      : "text-pb-faint hover:text-pb-dim"
                  }`
                }
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
            ))}
          </nav>

          {/* White-label: BetterStats logo sits top-right when the club
              supplies its own logo for the top-left slot. */}
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
    </header>
  );
}
