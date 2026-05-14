// Navbar — PressNav design with slug-based routing
import React, { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Ticker } from "../lib/presskit";
import { useAuth } from "../contexts/AuthContext";

export default function Navbar({ club, org }) {
  const location = useLocation();
  const { user } = useAuth();
  const slug = club?.slug || "";

  // Determine active section from path
  const path = location.pathname;
  const inSection = (seg) => path.includes(`/${slug}/${seg}`) || path.includes(`/${seg}`);

  const displayName = org?.name || club?.name || "BetterStats";
  const displayShort = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 4);

  const NAV = [
    { label: "Home",        href: `/${slug}` },
    { label: "Players",     href: `/${slug}/players` },
    { label: "Leaderboard", href: `/${slug}/leaderboard` },
    { label: "Records",     href: `/${slug}/records` },
    { label: "Yearbooks",   href: `/${slug}/yearbooks` },
    { label: "Games",       href: `/${slug}/games` },
    { label: "StatLab",     href: `/${slug}/statlab` },
    { label: "Compare",     href: `/${slug}/compare` },
  ];

  const adminLinks = user ? [
    { label: "Admin",       href: `/${slug}/admin` },
  ] : [];

  const allLinks = [...NAV, ...adminLinks];

  return (
    <header className="sticky top-0 z-50 bg-pb-surface pb-hairline-b">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-0 h-14">
          {/* Logo / club name */}
          <Link
            to={`/${slug}`}
            className="flex items-center gap-3 mr-6 shrink-0 group"
          >
            {club?.logo_url ? (
              <img
                src={club.logo_url}
                alt=""
                className="w-8 h-8 rounded object-contain"
              />
            ) : (
              <div
                className="w-8 h-8 rounded flex items-center justify-center text-[11px] font-mono font-bold"
                style={{ background: "var(--pb-accent)", color: "#000" }}
              >
                {displayShort}
              </div>
            )}
          <div className="hidden md:block leading-tight">
            <div className="text-pb-text text-[13px] font-semibold tracking-tight">{displayName}</div>
            <div className="text-pb-faint text-[10px] font-mono tracking-wide2">BETTERSTATS · v5.1.0</div>
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

          {/* Ticker — right side */}
          {org?.ticker_items?.length > 0 && (
            <div className="hidden lg:block ml-4 shrink-0 max-w-[240px] overflow-hidden">
              <Ticker
                items={org.ticker_items}
                className="text-pb-faint text-[10px] font-mono tracking-wide2 text-pb-dim flex items-center"
                speed={42}
              />
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
