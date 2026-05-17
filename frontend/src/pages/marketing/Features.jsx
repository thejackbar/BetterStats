import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import { Link } from 'react-router-dom'

// ─── Preview mock components ────────────────────────────────────────────────

function PreviewPlayerProfile() {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center gap-4 pb-4" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
        <div className="w-14 h-14 rounded-full flex items-center justify-center font-display font-bold text-xl" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>JB</div>
        <div>
          <div className="font-display font-bold text-xl text-pb-text">Jack Barendse</div>
          <div className="font-mono text-[10px] text-pb-faint tracking-wide2">200 INNINGS · 168 WICKETS · 93 CATCHES</div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[['5,842', 'Career Runs'], ['34.4', 'Bat Avg'], ['162', 'Best: 162*']].map(([v, l]) => (
          <div key={l} className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)' }}>
            <div className="font-display font-bold text-2xl" style={{ color: 'var(--pb-accent)' }}>{v}</div>
            <div className="font-mono text-[9px] text-pb-faint mt-1 tracking-wide2">{l}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[['168', 'Career Wkts'], ['24.1', 'Bowl Avg'], ['6/32', 'Best Figures']].map(([v, l]) => (
          <div key={l} className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)' }}>
            <div className="font-display font-bold text-2xl text-pb-text">{v}</div>
            <div className="font-mono text-[9px] text-pb-faint mt-1 tracking-wide2">{l}</div>
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">SEASON BREAKDOWN</div>
        <div className="space-y-1.5">
          {[['2024/25', '412 runs', '18 wkts'], ['2023/24', '388 runs', '22 wkts'], ['2022/23', '501 runs', '14 wkts']].map(([s, r, w]) => (
            <div key={s} className="flex justify-between items-center text-xs">
              <span className="font-mono text-pb-faint">{s}</span>
              <span className="text-pb-dim">{r}</span>
              <span className="text-pb-dim">{w}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">MILESTONES</div>
        <div className="flex flex-wrap gap-2">
          {['100 Games', '5,000 Runs', '150 Wickets', '10× Best & Fairest'].map(m => (
            <span key={m} className="font-mono text-[9px] px-2 py-1 rounded" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>{m}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

function PreviewYearbook() {
  return (
    <div className="space-y-4 text-sm">
      <div className="rounded p-4 text-center" style={{ background: 'var(--pb-surface)', borderBottom: '2px solid var(--pb-accent)' }}>
        <div className="font-mono text-[10px] text-pb-faint tracking-wide3 mb-1">APPLECROSS CRICKET CLUB</div>
        <div className="font-display font-bold text-2xl text-pb-text">Season Yearbook</div>
        <div className="font-mono text-[11px] tracking-wide2 mt-1" style={{ color: 'var(--pb-accent)' }}>2024/25</div>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {[['W', '14', 'Wins'], ['L', '4', 'Losses'], ['D', '2', 'Draws'], ['%', '70', 'Win Rate']].map(([sym, v, l]) => (
          <div key={l} className="rounded p-2 text-center" style={{ background: 'var(--pb-surface)' }}>
            <div className="font-display font-bold text-xl text-pb-text">{v}</div>
            <div className="font-mono text-[9px] text-pb-faint tracking-wide2">{l}</div>
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">BATTING HONOURS</div>
        <div className="space-y-1.5">
          {[['Most Runs', 'J. Barendse', '412'], ['Best Avg', 'T. Morrison', '68.2'], ['Centuries', 'J. Barendse', '2']].map(([cat, name, val]) => (
            <div key={cat} className="flex justify-between text-xs">
              <span className="text-pb-faint">{cat}</span>
              <span className="text-pb-dim">{name}</span>
              <span className="font-mono" style={{ color: 'var(--pb-accent)' }}>{val}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">EDITORIAL SECTIONS</div>
        <div className="space-y-1">
          {["President's Report", "Coach's Report", "Season in Brief", "Sponsor's Message"].map(s => (
            <div key={s} className="flex items-center gap-2 text-xs text-pb-dim">
              <span className="font-mono" style={{ color: 'var(--pb-accent)' }}>✓</span>{s}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PreviewLeaderboard() {
  const rows = [
    { rank: '01', name: 'J. Barendse', runs: '5,842', avg: '34.4', hs: '162*' },
    { rank: '02', name: 'T. Morrison', runs: '4,901', avg: '41.0', hs: '148' },
    { rank: '03', name: 'C. Walsh', runs: '4,210', avg: '28.6', hs: '127' },
    { rank: '04', name: 'M. Nguyen', runs: '3,987', avg: '30.1', hs: '109' },
    { rank: '05', name: 'S. Patel', runs: '3,654', avg: '26.8', hs: '98' },
  ]
  return (
    <div className="space-y-3 text-sm">
      <div className="flex gap-2 flex-wrap">
        {['Most Runs', 'Average', 'High Score', 'Centuries', 'Fifties'].map((t, i) => (
          <span key={t} className="font-mono text-[10px] px-2 py-1 rounded" style={{ background: i === 0 ? 'var(--pb-accent)' : 'var(--pb-surface)', color: i === 0 ? 'var(--pb-bg)' : 'var(--pb-faint)' }}>{t}</span>
        ))}
      </div>
      <div className="rounded overflow-hidden" style={{ border: '1px solid var(--pb-hairline)' }}>
        <div className="grid grid-cols-[28px_1fr_60px_50px_55px] gap-2 px-3 py-2 font-mono text-[9px] text-pb-faint tracking-wide2" style={{ background: 'var(--pb-surface)' }}>
          <span>#</span><span>PLAYER</span><span className="text-right" style={{ color: 'var(--pb-accent)' }}>RUNS</span><span className="text-right">AVG</span><span className="text-right">HS</span>
        </div>
        {rows.map(r => (
          <div key={r.rank} className="grid grid-cols-[28px_1fr_60px_50px_55px] gap-2 px-3 py-2 text-xs" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
            <span className="font-mono text-pb-faintest">{r.rank}</span>
            <span className="text-pb-dim">{r.name}</span>
            <span className="font-mono text-right font-semibold" style={{ color: 'var(--pb-accent)' }}>{r.runs}</span>
            <span className="font-mono text-right text-pb-dim">{r.avg}</span>
            <span className="font-mono text-right text-pb-dim">{r.hs}</span>
          </div>
        ))}
      </div>
      <div className="flex gap-2 mt-1">
        {['Batting', 'Bowling', 'Fielding'].map((t, i) => (
          <span key={t} className="font-mono text-[10px] px-2 py-1 rounded" style={{ background: i === 0 ? 'var(--pb-surface)' : 'transparent', color: 'var(--pb-faint)', border: '1px solid var(--pb-hairline)' }}>{t}</span>
        ))}
        <span className="ml-auto font-mono text-[10px] text-pb-faintest self-center">Filter by season / grade</span>
      </div>
    </div>
  )
}

function PreviewRecords() {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex gap-2 flex-wrap">
        {['Batting', 'Bowling', 'Partnerships', 'All-Rounders', 'Team'].map((t, i) => (
          <span key={t} className="font-mono text-[10px] px-2 py-1 rounded" style={{ background: i === 0 ? 'var(--pb-accent)' : 'var(--pb-surface)', color: i === 0 ? 'var(--pb-bg)' : 'var(--pb-faint)' }}>{t}</span>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: 'Most Career Runs', name: 'J. Barendse', val: '5,842' },
          { label: 'Highest Score', name: 'T. Morrison', val: '192*' },
          { label: 'Best Avg (min. 10)', name: 'C. Walsh', val: '51.3' },
          { label: 'Most Centuries', name: 'J. Barendse', val: '14' },
        ].map((r, i) => (
          <div key={r.label} className="rounded p-3" style={{ background: 'var(--pb-surface)', border: i === 0 ? '1px solid var(--pb-accent)' : '1px solid transparent' }}>
            <div className="font-mono text-[9px] text-pb-faint mb-1 tracking-wide2">{r.label}</div>
            <div className="font-display font-bold text-lg text-pb-text">{r.val}</div>
            <div className="text-xs text-pb-faint mt-0.5">{r.name}</div>
            {i === 0 && <div className="font-mono text-[8px] mt-1" style={{ color: 'var(--pb-accent)' }}>ALL-TIME RECORD</div>}
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">TOP PARTNERSHIPS</div>
        <div className="space-y-1.5">
          {[['1st wkt', 'Walsh & Morrison', '201'], ['3rd wkt', 'Barendse & Patel', '187'], ['6th wkt', 'Nguyen & Smith', '143']].map(([wkt, pair, runs]) => (
            <div key={wkt} className="flex justify-between text-xs">
              <span className="font-mono text-pb-faintest">{wkt}</span>
              <span className="text-pb-dim">{pair}</span>
              <span className="font-mono" style={{ color: 'var(--pb-accent)' }}>{runs}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PreviewScorecard() {
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center">
        <div className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-accent)' }}>
          <div className="font-mono text-[9px] text-pb-faint tracking-wide2 mb-1">APPLECROSS</div>
          <div className="font-display font-bold text-2xl" style={{ color: 'var(--pb-accent)' }}>187<span className="text-base">/6</span></div>
          <div className="font-mono text-[9px] text-pb-faint">(38.2 ov)</div>
        </div>
        <div className="font-mono text-[10px] text-pb-faint text-center px-1">WON<br/>BY<br/>14</div>
        <div className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)' }}>
          <div className="font-mono text-[9px] text-pb-faint tracking-wide2 mb-1">COMO</div>
          <div className="font-display font-bold text-2xl text-pb-text">173<span className="text-base">/10</span></div>
          <div className="font-mono text-[9px] text-pb-faint">(42.0 ov)</div>
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '10px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">BATTING — APPLECROSS</div>
        <div className="space-y-1">
          {[['J. Barendse', 'c Smith b Taylor', '68', '72'], ['T. Morrison', 'b Taylor', '44', '51'], ['C. Walsh', 'not out', '38*', '40']].map(([name, dism, runs, balls]) => (
            <div key={name} className="grid grid-cols-[1fr_auto_auto] gap-3 text-xs">
              <span className="text-pb-dim">{name} <span className="text-pb-faintest text-[10px]">{dism}</span></span>
              <span className="font-mono text-pb-faint">{balls}b</span>
              <span className="font-mono font-semibold" style={{ color: 'var(--pb-accent)' }}>{runs}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '10px' }}>
        <div className="font-mono text-[10px] text-pb-faint mb-2 tracking-wide2">BOWLING — COMO</div>
        <div className="space-y-1">
          {[['A. Taylor', '9-1-34-3', '3.78'], ['B. Jones', '8-0-42-2', '5.25'], ['C. Lee', '7-0-38-1', '5.43']].map(([name, line, econ]) => (
            <div key={name} className="grid grid-cols-[1fr_auto_auto] gap-3 text-xs">
              <span className="text-pb-dim">{name}</span>
              <span className="font-mono text-pb-faint">{line}</span>
              <span className="font-mono text-pb-faintest">{econ}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PreviewStatLab() {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex gap-2">
        {['Career', 'Season'].map((t, i) => (
          <span key={t} className="font-mono text-[10px] px-3 py-1.5 rounded" style={{ background: i === 0 ? 'var(--pb-accent)' : 'var(--pb-surface)', color: i === 0 ? 'var(--pb-bg)' : 'var(--pb-faint)' }}>{t}</span>
        ))}
      </div>
      <div className="rounded p-3 space-y-2" style={{ background: 'var(--pb-surface)' }}>
        <div className="font-mono text-[9px] text-pb-faint tracking-wide2 mb-2">SORT BY</div>
        <div className="grid grid-cols-3 gap-1.5">
          {['Runs', 'Average', 'Wickets', 'Economy', 'Strike Rate', 'Catches'].map((s, i) => (
            <span key={s} className="font-mono text-[9px] px-2 py-1 rounded text-center" style={{ background: i === 0 ? 'var(--pb-accent)' : 'var(--pb-bg)', color: i === 0 ? 'var(--pb-bg)' : 'var(--pb-faint)', border: '1px solid var(--pb-hairline)' }}>{s}</span>
          ))}
        </div>
      </div>
      <div className="rounded p-3" style={{ background: 'var(--pb-surface)' }}>
        <div className="font-mono text-[9px] text-pb-faint tracking-wide2 mb-2">FILTERS</div>
        <div className="flex gap-2 items-center text-xs">
          <span className="font-mono text-pb-dim px-2 py-1 rounded" style={{ border: '1px solid var(--pb-hairline)' }}>Innings</span>
          <span className="text-pb-faint">≥</span>
          <span className="font-mono text-pb-dim px-2 py-1 rounded" style={{ border: '1px solid var(--pb-hairline)' }}>10</span>
          <span className="font-mono text-[9px] ml-auto" style={{ color: 'var(--pb-accent)' }}>+ ADD FILTER</span>
        </div>
      </div>
      <div className="rounded overflow-hidden" style={{ border: '1px solid var(--pb-hairline)' }}>
        <div className="grid grid-cols-[24px_1fr_50px_50px_50px] gap-2 px-3 py-2 font-mono text-[9px] text-pb-faint" style={{ background: 'var(--pb-surface)' }}>
          <span>#</span><span>PLAYER</span><span className="text-right" style={{ color: 'var(--pb-accent)' }}>RUNS ↓</span><span className="text-right">INN</span><span className="text-right">AVG</span>
        </div>
        {[['01','J. Barendse','5842','200','34.4'],['02','T. Morrison','4901','162','41.0'],['03','C. Walsh','4210','158','28.6']].map(r => (
          <div key={r[0]} className="grid grid-cols-[24px_1fr_50px_50px_50px] gap-2 px-3 py-2 text-xs" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
            <span className="font-mono text-pb-faintest">{r[0]}</span>
            <span className="text-pb-dim">{r[1]}</span>
            <span className="font-mono text-right font-semibold" style={{ color: 'var(--pb-accent)' }}>{r[2]}</span>
            <span className="font-mono text-right text-pb-faint">{r[3]}</span>
            <span className="font-mono text-right text-pb-faint">{r[4]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function PreviewComparison() {
  const metrics = [['Innings', '200', '162'], ['Runs', '5,842', '4,901'], ['Average', '34.4', '41.0'], ['Wickets', '168', '92'], ['Best Figures', '6/32', '5/28']]
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-[1fr_80px_1fr] gap-3 items-center mb-4">
        <div className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)' }}>
          <div className="font-display font-bold text-base text-pb-text">J. Barendse</div>
          <div className="font-mono text-[9px] text-pb-faint">Applecross</div>
        </div>
        <div className="font-display font-bold text-xl text-pb-faint text-center">VS</div>
        <div className="rounded p-3 text-center" style={{ background: 'var(--pb-surface)' }}>
          <div className="font-display font-bold text-base text-pb-text">T. Morrison</div>
          <div className="font-mono text-[9px] text-pb-faint">Applecross</div>
        </div>
      </div>
      {metrics.map(([label, a, b]) => {
        const aWins = parseFloat(a.replace(/,/g, '')) > parseFloat(b.replace(/,/g, ''))
        return (
          <div key={label} className="grid grid-cols-[1fr_80px_1fr] gap-3 items-center">
            <div className="font-mono text-right text-sm font-semibold" style={{ color: aWins ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>{a}</div>
            <div className="font-mono text-[9px] text-pb-faint text-center tracking-wide2">{label.toUpperCase()}</div>
            <div className="font-mono text-sm font-semibold" style={{ color: !aWins ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>{b}</div>
          </div>
        )
      })}
    </div>
  )
}

function PreviewShareCard() {
  return (
    <div className="flex justify-center">
      <div className="w-72 rounded-lg p-5 space-y-3" style={{ background: 'linear-gradient(135deg, var(--pb-surface) 0%, var(--pb-bg) 100%)', border: '2px solid var(--pb-accent)' }}>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full flex items-center justify-center font-display font-bold text-lg" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>JB</div>
          <div>
            <div className="font-display font-bold text-lg text-pb-text">Jack Barendse</div>
            <div className="font-mono text-[9px] text-pb-faint tracking-wide2">APPLECROSS CC · 2024/25</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[['412', 'Runs'], ['34.4', 'Avg'], ['162*', 'HS']].map(([v, l]) => (
            <div key={l} className="text-center rounded p-2" style={{ background: 'var(--pb-bg)' }}>
              <div className="font-display font-bold text-lg" style={{ color: 'var(--pb-accent)' }}>{v}</div>
              <div className="font-mono text-[8px] text-pb-faint tracking-wide2">{l}</div>
            </div>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {['#1 Runs', '#3 Avg'].map(b => (
            <span key={b} className="font-mono text-[8px] px-2 py-0.5 rounded" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>{b}</span>
          ))}
          <span className="font-mono text-[8px] px-2 py-0.5 rounded" style={{ border: '1px solid var(--pb-accent)', color: 'var(--pb-accent)' }}>2× 50</span>
        </div>
        <div className="font-mono text-[9px] text-center text-pb-faint tracking-wide3 pt-1">betterstats.com.au</div>
      </div>
    </div>
  )
}

function PreviewAwards() {
  return (
    <div className="space-y-4 text-sm">
      <div className="space-y-2">
        <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">2024/25 SEASON AWARDS</div>
        {[['Best & Fairest', 'J. Barendse'], ['Best Bowler', 'T. Morrison'], ["President's Award", 'C. Walsh'], ['Rookie of the Year', 'M. Nguyen']].map(([award, name]) => (
          <div key={award} className="flex justify-between items-center rounded p-2.5" style={{ background: 'var(--pb-surface)' }}>
            <div>
              <div className="text-pb-dim text-xs">{award}</div>
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--pb-accent)' }}>{name}</div>
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-2">HALL OF FAME</div>
        <div className="space-y-1">
          {['D. Marsh (inducted 2018)', 'R. Lillee (inducted 2012)', 'P. Stewart (inducted 2009)'].map(p => (
            <div key={p} className="flex items-center gap-2 text-xs text-pb-dim">
              <span style={{ color: 'var(--pb-accent)' }}>★</span>{p}
            </div>
          ))}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--pb-hairline)', paddingTop: '12px' }}>
        <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-2">PREMIERSHIPS</div>
        <div className="flex flex-wrap gap-2">
          {['A Grade 2024', 'B Grade 2022', 'A Grade 2019'].map(p => (
            <span key={p} className="font-mono text-[9px] px-2 py-1 rounded" style={{ background: 'var(--pb-surface)', color: 'var(--pb-faint)', border: '1px solid var(--pb-hairline)' }}>{p}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Feature data ────────────────────────────────────────────────────────────

const SECTIONS = [
  {
    title: 'Automatic Stats Sync',
    desc: 'Connect your club once and BetterStats handles everything from there. After first sync your full history is imported — decades of data, automatically. Stats update after every match with no manual effort.',
    points: [
      'Full historical data imported on first sync — going back to the early 2000s',
      'Batting, bowling, and fielding stats captured per player per game',
      'Season aggregates and career totals computed automatically',
      'Weekly scheduled sync runs overnight — nothing to trigger',
      'Admin-triggered hard refresh available for on-demand updates',
    ],
    Preview: null,
  },
  {
    title: 'Player Profiles',
    desc: 'Every player gets a rich, public profile page with their full career stats, season history, and achievements — automatically kept up to date.',
    points: [
      'Career batting, bowling, and fielding totals with animated stat counters',
      'Season-by-season breakdown with colour-coded best/worst seasons',
      'Career progression charts — runs over time, averages by season',
      'Dismissal breakdown chart showing how they typically got out',
      'Partnership data and batting position analysis',
      'Achievements tab: milestone badges (500 runs, 50 wickets, 100 games…)',
      'Honours tab: club awards, hall of fame, caps, and association honours',
      'Player photo support with shareable stat card for social media',
    ],
    Preview: PreviewPlayerProfile,
  },
  {
    title: 'Leaderboards',
    desc: 'Live club leaderboards across every batting, bowling, and fielding category. Filter by season and grade to find exactly who led the club.',
    points: [
      'Batting: most runs, average (min. 500 runs), high score, fifties, centuries, sixes, fours, ducks',
      'Bowling: wickets, economy (min. 100 overs), average (min. 50 wickets), best figures, five-fors, maidens',
      'Fielding: catches, run-outs, stumpings',
      'Filter by any season or grade combination',
      'Rank badges with colour coding (gold, silver, bronze)',
      'All leaderboards update automatically after each sync',
    ],
    Preview: PreviewLeaderboard,
  },
  {
    title: 'Club Records',
    desc: 'All-time and season-best records across batting, bowling, partnerships, all-rounders, and team achievements — always current.',
    points: [
      'Batting records: most career runs, highest individual score, best average, most hundreds/fifties',
      'Bowling records: most career wickets, best innings figures, best economy, most five-fors',
      'Partnership records: all-time records at every wicket position, top 25 cross-grade partnerships',
      'All-rounder records: combined batting and bowling thresholds (min. 1,000 runs & 100 wickets)',
      'Team records: most matches played, most seasons represented',
      '"NEW" badge flags records set in the current season',
    ],
    Preview: PreviewRecords,
  },
  {
    title: 'Season Yearbooks',
    desc: 'A proper, shareable digital season publication for every year. Auto-populated with stats, honours, and results — then topped up with editorial content by your admin team.',
    points: [
      'Overview tab: season W/L/D record, win rate, season progression chart',
      'Batting, bowling, and fielding honours auto-populated from season stats',
      'All-rounder honours and partnership records per season',
      'Results tab: every match result by grade with scores',
      'Photo gallery: upload team and event photos',
      'Editorial sections: add President\'s Report, Coach\'s Report, Sponsor\'s Message, and more',
      'Honour board: record club positions and holders (President, Captain, Treasurer…)',
      'AI-assisted season narrative generator to kick-start the write-up',
      'Awards section: pull from the awards admin or add season-specific winners',
      'Publish/unpublish control — draft until you\'re ready',
    ],
    Preview: PreviewYearbook,
  },
  {
    title: 'Match Scorecards',
    desc: 'Full scorecards for every game — batting, bowling, fall of wickets, and partnerships — linked directly from player profiles.',
    points: [
      'Both innings displayed side-by-side with full batting and bowling details',
      'Fall of wickets as badge pills per innings',
      'Partnership data: runs, batters involved, and contribution split',
      'Result displayed prominently with winning team highlighted',
      'Date, venue, toss, and umpire details where available',
      'Every player name links back to their full profile',
      'Responsive layout — reads well on mobile',
    ],
    Preview: PreviewScorecard,
  },
  {
    title: 'StatLab',
    desc: 'A custom query builder for power users. Build your own leaderboards with any combination of metrics, filters, and thresholds.',
    points: [
      'Career or season mode',
      'Sort by any of 50+ metrics: runs, wickets, averages, economy, strike rate, catches, and more',
      'Add multiple filters with operators (at least, more than, exactly, at most, less than)',
      'Quick preset queries: Run Scorers, Wicket Takers, All-Rounders, Five-for Club, Batting Averages',
      'Results table supports up to 500 rows with client-side column sorting',
      'Filter by season and grade combination',
    ],
    Preview: PreviewStatLab,
  },
  {
    title: 'Player Comparison',
    desc: 'Head-to-head side-by-side comparison of any two players across their full careers.',
    points: [
      'Batting: innings, runs, average, strike rate, high score, fifties, centuries, sixes, fours, ducks',
      'Bowling: wickets, average, economy, best figures, five-fors, maidens',
      'Fielding: catches, run-outs, stumpings, total dismissals',
      'Animated comparison bars clearly show who leads each stat',
      'Superior stat highlighted in club accent colour',
      'Both player names link back to their full profiles',
    ],
    Preview: PreviewComparison,
  },
  {
    title: 'Shareable Player Cards',
    desc: 'Every player profile has a shareable stat card — a clean, branded snapshot that looks great on social media.',
    points: [
      'Career or season stats view selectable',
      'Batting and bowling highlights on a single card',
      'Club rank badges (e.g. #1 Runs, #2 Wickets)',
      'Milestone indicators (centuries, five-fors)',
      'Player photo or club logo fallback',
      'Native share API support — one tap to share on mobile',
    ],
    Preview: PreviewShareCard,
  },
  {
    title: 'Awards & Honours',
    desc: "Your club's full honours history in one place — annual awards, hall of fame, office bearers, association honours, and premierships.",
    points: [
      'Create award definitions once, assign winners each season',
      'Awards appear on the recipient\'s player profile automatically',
      'Hall of fame, life membership, and career honour tracking',
      'Office bearer history: President, Captain, Treasurer, and custom positions',
      'Premiership records with grade and year',
      'CSV bulk import for back-filling historical award data',
      'Browse all-time award history by category',
    ],
    Preview: PreviewAwards,
  },
  {
    title: 'Admin Tools',
    desc: 'A full-featured admin panel for your stats volunteers. No technical skills required — just a login.',
    points: [
      'Duplicate player detection and one-click merge tool — handles all historical stats correctly',
      'Display name overrides for cosmetic corrections without breaking data',
      'Grade display name overrides (rename a grade without losing game history)',
      'CSV import and export for players, awards, and stats',
      'Manual sync trigger with live progress feed',
      'Sync run history with success/error reporting',
      'Multiple admin logins — share access with committee members',
      'Player photo upload via admin panel',
    ],
    Preview: null,
  },
]

// ─── Modal ───────────────────────────────────────────────────────────────────

function PreviewModal({ section, onClose }) {
  if (!section?.Preview) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-lg p-6 overflow-y-auto"
        style={{ background: 'var(--pb-bg)', border: '1px solid var(--pb-hairline)', maxHeight: '85vh' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-0.5">PREVIEW</p>
            <h3 className="font-display font-bold text-lg text-pb-text">{section.title}</h3>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-xs text-pb-faint hover:text-pb-text transition-colors ml-4 shrink-0"
          >
            ✕ CLOSE
          </button>
        </div>
        <section.Preview />
        <p className="font-mono text-[9px] text-pb-faintest text-center mt-5 tracking-wide2">
          ILLUSTRATIVE — USES SAMPLE DATA
        </p>
      </div>
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Features() {
  const [activeModal, setActiveModal] = useState(null)

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <PreviewModal section={activeModal} onClose={() => setActiveModal(null)} />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">What's included</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Features.</h1>
        <p className="text-pb-dim text-lg mb-16">Everything your cricket club needs to run a proper stats platform.</p>

        <div className="space-y-0">
          {SECTIONS.map((s, i) => (
            <div key={s.title} className="pb-hairline-t py-10">
              <div className="grid md:grid-cols-[1fr_2fr] gap-8">
                <div>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">{String(i + 1).padStart(2, '0')}</p>
                  <h2 className="font-display font-bold text-[22px] text-pb-text leading-tight mb-3">{s.title}</h2>
                  {s.Preview && (
                    <button
                      onClick={() => setActiveModal(s)}
                      className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded transition-colors"
                      style={{ border: '1px solid var(--pb-accent)', color: 'var(--pb-accent)' }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-accent)'; e.currentTarget.style.color = 'var(--pb-bg)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--pb-accent)' }}
                    >
                      SEE PREVIEW →
                    </button>
                  )}
                </div>
                <div>
                  <p className="text-pb-dim mb-5 leading-relaxed">{s.desc}</p>
                  <ul className="space-y-2">
                    {s.points.map(p => (
                      <li key={p} className="flex items-start gap-2.5 text-sm text-pb-dim">
                        <span className="mt-0.5 font-mono shrink-0" style={{ color: 'var(--pb-accent)' }}>✓</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-16 text-center pb-hairline-t pt-10">
          <Link
            to="/pricing"
            className="inline-block px-8 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            SEE PRICING →
          </Link>
        </div>
      </div>
    </div>
  )
}
