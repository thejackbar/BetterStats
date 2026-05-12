// src/pages/marketing/Pricing.jsx — three-tier, quiet, terminal-grid
import React from "react";
import { Label, Btn } from "../../lib/presskit";

const TIERS = [
  {
    name: "CLUB", price: "Free", note: "Forever, for one team",
    features: ["1 team · 1 grade", "Daily Play-Cricket sync", "All stat pages", "Public club homepage", "BetterStats branding"],
    cta: "Start free", primary: false,
  },
  {
    name: "CLUB+", price: "£12", note: "per month, per club",
    features: ["Unlimited teams & grades", "White-label colours + domain", "Compare + Stat Lab", "Hall of records", "Player follow + notifications", "Hide BetterStats branding"],
    cta: "Start 14-day trial", primary: true, popular: true,
  },
  {
    name: "LEAGUE", price: "Custom", note: "For league bodies & associations",
    features: ["Cross-club leaderboards", "League-wide records", "Custom integrations", "SLA + priority support", "Branded mobile app"],
    cta: "Talk to us", primary: false,
  },
];

export default function Pricing() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <Label>PRICING · SIMPLE</Label>
        <h1 className="font-display text-[56px] sm:text-[88px] font-bold tracking-tight leading-[0.92] mt-3 max-w-[14ch]">
          Free for one team. Paid for whole clubs.
        </h1>
        <p className="mt-5 max-w-[56ch] text-pb-dim text-[17px] leading-[1.55]">
          No per-player charges. No setup fees. Cancel anytime — your data exports as CSV.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-12">
          {TIERS.map(t => (
            <div key={t.name}
                 className="pb-card p-6 flex flex-col"
                 style={t.popular ? { borderColor: "var(--pb-accent)" } : {}}>
              <div className="flex items-baseline justify-between">
                <Label>{t.name}</Label>
                {t.popular && <Label style={{ color: "var(--pb-accent)" }}>MOST POPULAR</Label>}
              </div>
              <div className="font-display text-[56px] font-bold tracking-tight leading-none mt-3">{t.price}</div>
              <div className="font-mono text-[11px] text-pb-faint tracking-wide2 mt-1">{t.note.toUpperCase()}</div>

              <ul className="flex flex-col gap-2.5 mt-6 mb-8 text-[14px] text-pb-dim flex-1">
                {t.features.map(f => (
                  <li key={f} className="flex gap-2.5">
                    <span style={{ color: "var(--pb-accent)" }}>●</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <Btn primary={t.primary} className="w-full justify-center">{t.cta} →</Btn>
            </div>
          ))}
        </div>

        <div className="pb-card p-6 mt-10 flex flex-wrap items-center justify-between gap-3">
          <div>
            <Label>QUESTIONS?</Label>
            <div className="text-pb-text text-[14px] mt-1">We answer every email personally — usually within a day.</div>
          </div>
          <Btn>Contact us →</Btn>
        </div>
      </main>
    </div>
  );
}
