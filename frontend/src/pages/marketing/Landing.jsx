// src/pages/marketing/Landing.jsx — BetterStats marketing landing
import React from "react";
import { Link } from "react-router-dom";
import { AnimatedNum, Sparkline, MiniBars, Label, Btn, Ticker } from "../../lib/presskit";

export default function Landing() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="max-w-[1300px] mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-12 sm:pb-20">
          <Label>BETTERSTATS · CRICKET STATS, OBSESSED OVER</Label>
          <h1 className="font-display text-[64px] sm:text-[112px] font-bold tracking-tight leading-[0.9] mt-4 max-w-[14ch]">
            Every<br/>
            <span style={{ color: "var(--pb-accent)" }}>number,</span><br/>
            every match.
          </h1>
          <p className="mt-6 max-w-[52ch] text-pb-dim text-[18px] leading-[1.55]">
            Cricket clubs run on numbers. <span className="text-pb-text">BetterStats</span> turns your Play-Cricket data into season-long stories,
            head-to-heads, hall-of-records and a homepage every player wants to refresh.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Btn primary>Get your club online →</Btn>
            <Btn>See a live club</Btn>
          </div>
          <div className="mt-10 flex flex-wrap gap-x-6 gap-y-2 font-mono text-[11px] tracking-wide2 text-pb-faint">
            <span><span className="text-pb-text">SYNCS</span> WITH PLAY-CRICKET DAILY</span>
            <span><span className="text-pb-text">WHITE-LABEL</span> CLUB COLOURS & DOMAIN</span>
            <span><span className="text-pb-text">FREE</span> TO START</span>
          </div>
        </div>

        {/* Background ticker */}
        <div className="pb-hairline-t pb-hairline-b bg-pb-surface">
          <Ticker
            speed={60}
            items={[
              "BANNER 142(118) v STOKE GREEN",
              "PATEL 4/22 — SEASON BEST",
              "ACTON 11-MATCH WIN STREAK",
              "WHITFIELD 1000 SEASON RUNS",
              "STONE FASTEST 50 — 19 BALLS",
              "LYLE HAT-TRICK v WEMBLEY",
            ]}
            className="font-mono text-[11px] tracking-wide2 text-pb-dim py-2.5"
          />
        </div>
      </section>

      {/* PROOF — three stat tiles */}
      <section className="max-w-[1300px] mx-auto px-4 sm:px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <ProofCard label="MATCHES INDEXED" value={184000} suffix="+"
            spark={[20, 32, 45, 56, 68, 79, 88, 95, 110, 130, 142, 168, 184]} />
          <ProofCard label="STATS COMPUTED LIVE" value={2400000} suffix="+"
            spark={[8, 14, 22, 28, 38, 49, 62, 72, 88, 110, 140, 180, 240]} />
          <ProofCard label="CLUB COMMUNITIES" value={47}
            spark={[1, 3, 4, 6, 9, 13, 17, 22, 28, 34, 40, 45, 47]} accentSpark />
        </div>
      </section>

      {/* FEATURES — three rows */}
      <Feature
        eyebrow="01 · FOR PLAYERS"
        title="Your stats. Right there on the homepage."
        body="Sign in to see your career line, last 14 innings, dismissal split, milestones in reach, and which bowler types you eat for breakfast. Built for refreshing on the train home."
        cta="See a player profile"
      />
      <Feature
        eyebrow="02 · FOR THE GROUP CHAT"
        title="Settle every argument with bars on a screen."
        body="Pick any two players. See who's actually been carrying the side. Strike rate vs death-overs runs, head-to-head wickets, last-14 form. Screenshots welcome."
        cta="Open compare"
        flip
      />
      <Feature
        eyebrow="03 · FOR CAPTAINS"
        title="The whole season, on one page."
        body="Form, top run-scorers, top wicket-takers, milestones in reach, recent results, the next fixture. No dashboards-of-dashboards — just the page everyone opens before nets."
        cta="See the dashboard"
      />

      {/* RECORDS strip */}
      <section className="pb-hairline-t bg-pb-surface">
        <div className="max-w-[1300px] mx-auto px-4 sm:px-6 py-16">
          <div className="flex items-end justify-between gap-3 mb-6">
            <div>
              <Label>04 · THE HALL OF RECORDS</Label>
              <h2 className="font-display text-[36px] sm:text-[48px] font-bold tracking-tight mt-2">Every club benchmark, in one place.</h2>
            </div>
            <Btn>Browse records</Btn>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <RecordTile rank="1" title="Highest individual score" value="187*" player="Jack Banner" />
            <RecordTile rank="1" title="Best bowling figures"     value="7/24" player="Asha Patel" />
            <RecordTile rank="1" title="Highest team total"       value="284/3" player="ACTON CC" highlight />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-[1300px] mx-auto px-4 sm:px-6 py-20 sm:py-28">
        <div className="pb-card p-8 sm:p-12 text-center">
          <Label>WANT YOUR CLUB ON HERE?</Label>
          <h2 className="font-display text-[40px] sm:text-[64px] font-bold tracking-tight leading-[0.95] mt-3 max-w-[18ch] mx-auto">
            Plug in Play-Cricket. <span style={{ color: "var(--pb-accent)" }}>Done.</span>
          </h2>
          <p className="mt-5 text-pb-dim max-w-[52ch] mx-auto">
            Connect your Play-Cricket club, pick your colours, share the link. We do the rest — overnight sync, season-long history, and a homepage every member will check before training.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Btn primary>Get my club online →</Btn>
            <Link to="/pricing" className="font-mono text-[11px] tracking-wide2 self-center text-pb-dim hover:text-pb-text">PRICING →</Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="pb-hairline-t bg-pb-surface">
        <div className="max-w-[1300px] mx-auto px-4 sm:px-6 py-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="font-mono text-[11px] font-bold tracking-wide3 px-1.5 py-0.5 rounded-sm" style={{ background: "var(--pb-accent)", color: "#08110b" }}>BS</div>
            <div className="font-mono text-[11px] tracking-wide2 text-pb-dim">BETTERSTATS · 2026</div>
          </div>
          <div className="flex gap-5 font-mono text-[11px] tracking-wide2 text-pb-faint">
            <Link to="/features" className="hover:text-pb-text">FEATURES</Link>
            <Link to="/pricing" className="hover:text-pb-text">PRICING</Link>
            <Link to="/about" className="hover:text-pb-text">ABOUT</Link>
            <Link to="/login" className="hover:text-pb-text">SIGN IN</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function ProofCard({ label, value, suffix, spark, accentSpark }) {
  return (
    <div className="pb-card p-5">
      <Label>{label}</Label>
      <div className="flex items-end justify-between mt-3">
        <span className="font-mono text-[44px] font-bold pb-num leading-none">
          <AnimatedNum value={value} suffix={suffix} />
        </span>
        <span style={{ color: accentSpark ? "var(--pb-accent)" : "var(--pb-text)" }}>
          <Sparkline data={spark} w={140} h={36} stroke="currentColor" strokeWidth={1.5} dot />
        </span>
      </div>
    </div>
  );
}

function Feature({ eyebrow, title, body, cta, flip }) {
  return (
    <section className="pb-hairline-t">
      <div className={`max-w-[1300px] mx-auto px-4 sm:px-6 py-16 sm:py-20 grid grid-cols-1 lg:grid-cols-2 gap-10 items-center ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
        <div>
          <Label>{eyebrow}</Label>
          <h2 className="font-display text-[36px] sm:text-[56px] font-bold tracking-tight leading-[0.95] mt-3 max-w-[14ch]">{title}</h2>
          <p className="mt-5 text-pb-dim text-[17px] leading-[1.55] max-w-[48ch]">{body}</p>
          <div className="mt-6"><Btn primary>{cta} →</Btn></div>
        </div>
        <div className="pb-card p-6">
          <Label>PREVIEW</Label>
          <div className="mt-3 font-mono text-pb-faint text-[10px] tracking-wide2">[ screenshot / interactive demo lives here — wire to /demo route ]</div>
          <div className="mt-4 h-[260px] rounded-sm bg-pb-surface2 pb-hairline-b flex items-end p-3">
            <div className="flex-1" style={{ color: "var(--pb-accent)" }}>
              <Sparkline data={[12, 24, 38, 28, 42, 51, 39, 62, 78, 71, 89, 102]} w={460} h={220} stroke="currentColor" fill="currentColor" strokeWidth={1.6} dot />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function RecordTile({ rank, title, value, player, highlight }) {
  return (
    <div className="pb-card p-5">
      <div className="flex items-baseline justify-between">
        <Label>#{rank} · {title}</Label>
      </div>
      <div className="flex items-baseline justify-between mt-3 gap-3">
        <span className="text-pb-text font-semibold text-[15px] truncate">{player}</span>
        <span className="font-mono text-[34px] font-bold pb-num leading-none"
              style={{ color: highlight ? "var(--pb-accent)" : "var(--pb-text)" }}>
          {value}
        </span>
      </div>
    </div>
  );
}
