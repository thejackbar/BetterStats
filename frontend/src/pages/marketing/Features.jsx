// src/pages/marketing/Features.jsx — feature list, quiet
import React from "react";
import { Label, Btn } from "../../lib/presskit";

const GROUPS = [
  {
    title: "FOR PLAYERS",
    items: [
      ["Career & season tile",      "All your numbers, animated up on load."],
      ["Last 14 innings chart",     "Spot form trends at a glance."],
      ["Dismissal & shot split",    "Where do you actually get out?"],
      ["Milestones in reach",       "Next century, next ton, next half-century."],
      ["By grade · by position",    "Slice your runs however the captain asks."],
    ],
  },
  {
    title: "FOR CAPTAINS & COACHES",
    items: [
      ["Club dashboard",            "Form, leaders, milestones, fixtures — one page."],
      ["Compare two players",       "Settle selection arguments with data."],
      ["Stat Lab deep-dive",        "Phase / bowler type / ground splits."],
      ["Match scorecard worm",      "Runs by over for both innings overlaid."],
      ["Hall of records",           "Every club benchmark, kept honest."],
    ],
  },
  {
    title: "FOR ADMINS",
    items: [
      ["Play-Cricket sync",         "Daily auto-sync + on-demand run."],
      ["Roster CRUD",               "Add players, link IDs, retire profiles."],
      ["White-label theming",       "Club colours, custom domain, hide branding."],
      ["CSV export",                "Your data, always. No lock-in."],
      ["Cross-club leaderboards",   "Where one club has many teams."],
    ],
  },
];

export default function Features() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <Label>FEATURES · EVERYTHING IN THE BOX</Label>
        <h1 className="font-display text-[56px] sm:text-[88px] font-bold tracking-tight leading-[0.92] mt-3 max-w-[16ch]">
          Built for clubs that take their numbers seriously.
        </h1>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-12">
          {GROUPS.map(g => (
            <div key={g.title} className="pb-card p-6">
              <Label>{g.title}</Label>
              <ul className="flex flex-col mt-3">
                {g.items.map(([t, d], i) => (
                  <li key={t} className={`${i ? "pb-hairline-t" : ""} py-3`}>
                    <div className="text-pb-text font-semibold text-[14px]">{t}</div>
                    <div className="text-pb-dim text-[13px] mt-1 leading-[1.45]">{d}</div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex justify-center">
          <Btn primary>Try BetterStats free →</Btn>
        </div>
      </main>
    </div>
  );
}
