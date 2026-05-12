// src/pages/Dashboard.jsx — BetterStats Press Box Club Dashboard
// Drop in as DashboardV2.jsx and add a route, or replace Dashboard.jsx outright.
// Real-data wiring: see "// WIRE:" comments — swap mock for your api.js calls.

import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AnimatedNum, Sparkline, MiniBars, Label, Card, Btn,
  ResultPill, Kpi, PageHeader,
} from "../lib/presskit";
import {
  mockClub, mockClubSummary, mockKpiTrends,
  mockTopRuns, mockTopWickets, mockUpcomingMilestones,
  mockRecentMatches, mockUpcomingFixtures,
  fetchOrMock,
} from "../lib/mockData";
// import api from "../lib/api"; // WIRE: enable when integrating real endpoints

export default function Dashboard() {
  const [club, setClub]               = useState(mockClub);
  const [summary, setSummary]         = useState(mockClubSummary);
  const [trends, setTrends]           = useState(mockKpiTrends);
  const [topRuns, setTopRuns]         = useState(mockTopRuns);
  const [topWickets, setTopWickets]   = useState(mockTopWickets);
  const [milestones, setMilestones]   = useState(mockUpcomingMilestones);
  const [matches, setMatches]         = useState(mockRecentMatches);
  const [fixtures, setFixtures]       = useState(mockUpcomingFixtures);
  const [loading, setLoading]         = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      // WIRE: replace these with your real api.js calls
      // const [c, s, tr, tw, m, mt, fx] = await Promise.all([
      //   fetchOrMock(api.club.current(),           mockClub),
      //   fetchOrMock(api.club.summary(),           mockClubSummary),
      //   fetchOrMock(api.club.trends(),            mockKpiTrends),
      //   fetchOrMock(api.players.topRuns(),        mockTopRuns),
      //   fetchOrMock(api.players.topWickets(),     mockTopWickets),
      //   fetchOrMock(api.matches.recent(),         mockRecentMatches),
      //   fetchOrMock(api.players.upcomingMilestones(), mockUpcomingMilestones),
      //   fetchOrMock(api.fixtures.upcoming(),      mockUpcomingFixtures),
      // ]);
      // if (!alive) return;
      // setClub(c); setSummary(s); setTrends(tr); setTopRuns(m);
      // setTopWickets(tw); setMilestones(mt); setMatches(m); setFixtures(fx);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const winPct = Math.round(summary.win_rate * 100);
  const streakColor = summary.active_streak.type === "WIN" ? "var(--pb-accent)" : "var(--pb-red)";

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`${club.short} · CLUB DASHBOARD · ${club.season_label}`}
          title="The season, on one page."
          meta={[
            <span key="m">PLAYED <span className="text-pb-text">{summary.match_count}</span></span>,
            <span key="r"><span className="text-pb-text">{summary.total_runs.toLocaleString()}</span> RUNS</span>,
            <span key="w"><span className="text-pb-text">{summary.total_wickets}</span> WICKETS</span>,
            <span key="p"><span className="text-pb-text">{summary.player_count}</span> PLAYERS</span>,
          ]}
          actions={[
            <Btn key="exp">Export season</Btn>,
            <Btn key="sh" primary>Share club page →</Btn>,
          ]}
        />

        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <Kpi label="WIN RATE"   value={winPct}              suffix="%" accent spark={trends.win_rate.map(v=>v*100)} />
          <Kpi label="RUNS / INN" value={Math.round(summary.total_runs / summary.match_count)} spark={trends.runs_per} sparkColor="var(--pb-text)" />
          <Kpi label="WICKETS / GAME" value={(summary.total_wickets / summary.match_count).toFixed(1)} decimals={1} spark={trends.wickets_per} sparkColor="var(--pb-text)" />
          <Kpi label={`${summary.active_streak.type} STREAK`} value={summary.active_streak.count} suffix="" accent sub="Last 10 matches" />
        </div>

        {/* Form row */}
        <div className="pb-card p-4 mb-6 flex items-center gap-4 flex-wrap">
          <Label>FORM (LAST 10)</Label>
          <div className="flex gap-1.5">
            {summary.results_form.map((r, i) => {
              const color =
                r === "W" ? "var(--pb-accent)" :
                r === "L" ? "var(--pb-red)" :
                r === "T" ? "var(--pb-amber)" : "var(--pb-faint)";
              return (
                <span key={i}
                  className="w-6 h-6 rounded-sm font-mono text-[10px] font-bold flex items-center justify-center"
                  style={{ background: `${color}1f`, color, border: `1px solid ${color}40` }}>
                  {r}
                </span>
              );
            })}
          </div>
          <div className="ml-auto flex items-center gap-6 text-pb-dim font-mono text-[11px] tracking-wide2">
            <span>CENTURIES <span className="text-pb-text">{summary.total_centuries}</span></span>
            <span>FIVE-WICKETS <span className="text-pb-text">{summary.total_five_fers}</span></span>
            <span style={{ color: streakColor }}>● ACTIVE</span>
          </div>
        </div>

        {/* Two-col: leaders + milestones */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mb-6">
          {/* Top run-scorers */}
          <Card className="xl:col-span-1" title="TOP RUN-SCORERS · 2025/26"
                action={<Link to="/leaderboard?cat=runs" className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            <ol className="flex flex-col">
              {topRuns.map((p, i) => (
                <li key={p.id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                  <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                  <Link to={`/players/${p.id}`} className="flex-1 min-w-0">
                    <div className="text-pb-text text-[14px] font-semibold truncate">{p.name}</div>
                    <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">AVG {p.avg.toFixed(1)} · SR {p.sr.toFixed(1)} · HS {p.hs}</div>
                  </Link>
                  <span className="text-pb-accent/80" style={{ color: "var(--pb-accent)" }}>
                    <Sparkline data={p.trend} w={56} h={18} stroke="currentColor" strokeWidth={1.3} />
                  </span>
                  <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right">
                    <AnimatedNum value={p.runs} />
                  </span>
                </li>
              ))}
            </ol>
          </Card>

          {/* Top wicket-takers */}
          <Card title="TOP WICKET-TAKERS · 2025/26"
                action={<Link to="/leaderboard?cat=wickets" className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            <ol className="flex flex-col">
              {topWickets.map((p, i) => (
                <li key={p.id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                  <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                  <Link to={`/players/${p.id}`} className="flex-1 min-w-0">
                    <div className="text-pb-text text-[14px] font-semibold truncate">{p.name}</div>
                    <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">AVG {p.avg.toFixed(1)} · ECON {p.econ.toFixed(2)} · BEST {p.best}</div>
                  </Link>
                  <span style={{ color: "var(--pb-accent)" }}>
                    <MiniBars data={p.trend} w={56} h={18} color="currentColor" gap={1.5} accentLast />
                  </span>
                  <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right">
                    <AnimatedNum value={p.wickets} />
                  </span>
                </li>
              ))}
            </ol>
          </Card>

          {/* Upcoming milestones */}
          <Card title="MILESTONES IN REACH"
                action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">THIS SEASON</span>}>
            <ul className="flex flex-col gap-3">
              {milestones.map((m) => {
                const pct = Math.min(100, Math.round((m.current / m.target_value) * 100));
                return (
                  <li key={m.id + m.target} className="flex flex-col gap-1.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-pb-text text-[13px] font-semibold truncate">{m.name}</div>
                        <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2 uppercase">{m.target}</div>
                      </div>
                      <span className="font-mono text-[12px] text-pb-dim pb-num">
                        <span className="text-pb-text font-bold">{m.current.toLocaleString()}</span> / {m.target_value.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-1 rounded-sm bg-pb-hairline overflow-hidden">
                      <div className="h-full" style={{ width: `${pct}%`, background: "var(--pb-accent)" }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>

        {/* Recent results table */}
        <Card title="RECENT MATCHES" className="mb-6"
              action={<Link to="/matches" className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">FULL LIST →</Link>}>
          <div className="overflow-x-auto pb-scroll -mx-2">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="font-medium pb-2 pl-2">DATE</th>
                  <th className="font-medium pb-2">OPPONENT</th>
                  <th className="font-medium pb-2">FMT</th>
                  <th className="font-medium pb-2">RESULT</th>
                  <th className="font-medium pb-2">FOR</th>
                  <th className="font-medium pb-2">AGAINST</th>
                  <th className="font-medium pb-2">MARGIN</th>
                  <th className="font-medium pb-2 pr-2">HERO</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr key={m.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2 cursor-pointer`}>
                    <td className="py-2.5 pl-2 font-mono text-pb-dim text-[12px]">{m.date}</td>
                    <td className="py-2.5 text-pb-text font-medium">{m.opp}</td>
                    <td className="py-2.5 font-mono text-pb-faint text-[11px] tracking-wide2">{m.format}</td>
                    <td className="py-2.5"><ResultPill result={m.result} /></td>
                    <td className="py-2.5 font-mono text-pb-text">{m.for}</td>
                    <td className="py-2.5 font-mono text-pb-dim">{m.against}</td>
                    <td className="py-2.5 font-mono text-pb-dim">{m.margin}</td>
                    <td className="py-2.5 pr-2 text-pb-dim text-[12px]"><span style={{ color: "var(--pb-accent)" }}>★</span> {m.hero}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Fixtures */}
        <Card title="UPCOMING FIXTURES"
              action={<Link to="/fixtures" className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">CALENDAR →</Link>}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {fixtures.map((f) => (
              <div key={f.id} className="pb-card-2 p-4 rounded">
                <div className="flex items-center justify-between">
                  <Label>{f.format} · {f.ground}</Label>
                  <span className="font-mono text-[10.5px] text-pb-dim tracking-wide2">{f.time}</span>
                </div>
                <div className="text-pb-text font-display text-[22px] font-semibold leading-tight mt-2.5">{f.opp}</div>
                <div className="font-mono text-pb-faint text-[11px] tracking-wide2 mt-1">{f.date}</div>
              </div>
            ))}
          </div>
        </Card>
      </main>
    </div>
  );
}
