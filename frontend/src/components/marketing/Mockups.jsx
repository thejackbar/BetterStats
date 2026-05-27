/**
 * Polished placeholder mocks shown until real product screenshots are added.
 *
 * Each mock renders entirely in tokens (bg-pb-bg, text-pb-text, etc.) so it
 * stays on-theme. To replace a mock with a real screenshot:
 *   1. Drop a PNG at e.g. /public/marketing/leaderboard.png
 *   2. Edit the consuming page to use <ScreenshotOrMock src="/marketing/leaderboard.png" fallback={<MockLeaderboard />} />
 *
 * See ScreenshotOrMock.jsx for the fallback wrapper.
 */

// ── Browser chrome wrapper ────────────────────────────────────────────────
function BrowserChrome({ url, children }) {
  return (
    <div className="bg-pb-surface border pb-hairline rounded-2xl overflow-hidden shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)]">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b pb-hairline bg-pb-bg">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-400/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/70" />
        </div>
        <div className="ml-4 flex-1 max-w-md mx-auto bg-pb-surface2 rounded px-3 py-1 text-[11px] text-pb-dim font-mono text-center">
          {url}
        </div>
      </div>
      {children}
    </div>
  )
}

// ── Mock 1: Club homepage (used in landing hero) ──────────────────────────
export function MockClubHomepage() {
  return (
    <BrowserChrome url="applecross.betterstats.cricket">
      <div className="px-6 py-3 border-b pb-hairline bg-pb-surface flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-white font-bold text-xs">A</div>
          <span className="font-semibold text-sm">Applecross Cricket Club</span>
        </div>
        <div className="flex items-center gap-4 text-[11px] text-pb-dim">
          <span>Fixtures</span><span>Ladder</span><span>Players</span><span className="text-pb-text">Stats</span><span>Yearbook</span>
        </div>
      </div>

      <div className="px-6 lg:px-8 py-7 grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-7">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-mono uppercase tracking-wide3 text-accent">● Live · Round 14</span>
            <span className="text-[10px] font-mono text-pb-faint">2025/26 SEASON</span>
          </div>
          <h2 className="text-2xl lg:text-3xl font-bold leading-tight mb-1">Applecross 6/214 def. Mosman Park 171</h2>
          <p className="text-sm text-pb-dim mb-4">Win by 43 runs · Reilly 178 (108) · Marston 4/22</p>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="bg-pb-surface2 rounded-lg p-3 border pb-hairline">
              <p className="text-[10px] font-mono text-pb-faint uppercase mb-1">Top scorer</p>
              <p className="text-base font-bold">S. Reilly</p>
              <p className="text-xs text-accent font-mono">178 (108) · SR 164.8</p>
            </div>
            <div className="bg-pb-surface2 rounded-lg p-3 border pb-hairline">
              <p className="text-[10px] font-mono text-pb-faint uppercase mb-1">Pick of bowlers</p>
              <p className="text-base font-bold">H. Marston</p>
              <p className="text-xs text-accent font-mono">4/22 (10.0) · econ 2.20</p>
            </div>
          </div>

          <div className="bg-pb-surface2 rounded-lg p-3 border pb-hairline">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-mono text-pb-faint uppercase">Form · Last 10 matches</p>
              <p className="text-[10px] font-mono text-accent">8W · 2L</p>
            </div>
            <div className="flex items-end gap-1 h-10">
              {[5,7,4,8,6,9,7,8,9,9].map((h, i) => (
                <div key={i} className="flex-1 rounded-t" style={{ height: `${h * 10}%`, background: h >= 6 ? 'var(--pb-accent)' : 'var(--pb-hairline)' }} />
              ))}
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-5 bg-pb-surface2 rounded-lg p-4 border pb-hairline">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent">Season leaders · 1st Grade</p>
            <p className="text-[10px] font-mono text-pb-faint">Runs</p>
          </div>
          {[
            ['J. Barendse', '742', '49.46'],
            ['T. Whitfield', '689', '45.93'],
            ['S. Reilly', '612', '43.71'],
            ['O. Bennett', '588', '36.75'],
            ['H. Marston', '521', '47.36'],
          ].map(([n, runs, avg], i) => (
            <div key={n} className="flex items-center gap-3 py-2 border-b pb-hairline last:border-b-0">
              <span className="text-[10px] font-mono text-pb-faint w-4">{i + 1}</span>
              <div className="w-6 h-6 rounded-full bg-pb-hairline flex items-center justify-center text-[9px] font-bold">{n.split(' ').map(p => p[0]).join('')}</div>
              <span className="flex-1 text-xs font-medium">{n}</span>
              <span className="text-xs font-mono font-semibold tabular-nums">{runs}</span>
              <span className="text-[10px] font-mono text-pb-dim tabular-nums w-10 text-right">{avg}</span>
            </div>
          ))}
        </div>
      </div>
    </BrowserChrome>
  )
}

// ── Mock 2: Heritage career profile (Bob Doyle '78-'99) ───────────────────
export function MockHeritageCard() {
  return (
    <BrowserChrome url="applecross.betterstats.cricket/players/r-doyle">
      <div className="p-6 lg:p-8">
        <div className="flex items-start gap-5 mb-6">
          <div className="w-20 h-20 rounded-xl bg-gradient-to-br from-emerald-700 to-emerald-900 border border-accent/30 flex items-center justify-center flex-shrink-0">
            <span className="font-bold text-2xl">RD</span>
          </div>
          <div className="flex-1">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">All-rounder · 1978 – 1999</p>
            <h3 className="text-2xl lg:text-3xl font-bold leading-tight mb-1">Robert "Bob" Doyle</h3>
            <p className="text-sm text-pb-dim">Applecross CC · Life Member · Club Champion ×4</p>
          </div>
          <span className="pill"><span className="dot" />22 seasons</span>
        </div>

        <div className="grid grid-cols-4 gap-3 mb-6">
          {[['8,452', 'Runs'], ['41.23', 'Avg'], ['312', 'Wickets'], ['134', 'Catches']].map(([v, l]) => (
            <div key={l} className="bg-pb-surface2 border pb-hairline rounded-lg p-3">
              <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">{l}</p>
              <p className="text-xl font-bold tabular-nums">{v}</p>
            </div>
          ))}
        </div>

        <div className="bg-pb-surface2 border pb-hairline rounded-lg p-4 mb-5">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Career batting · runs per season</p>
            <p className="text-[10px] font-mono text-accent">22 seasons</p>
          </div>
          <svg viewBox="0 0 440 80" className="w-full h-20">
            <defs>
              <linearGradient id="rdg" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--pb-accent)" stopOpacity="0.4" />
                <stop offset="100%" stopColor="var(--pb-accent)" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d="M0,55 L21,50 L42,42 L63,35 L84,28 L105,22 L126,18 L147,15 L168,18 L189,12 L210,8 L231,12 L252,18 L273,15 L294,22 L315,28 L336,32 L357,38 L378,42 L399,48 L420,52 L440,58 L440,80 L0,80 Z" fill="url(#rdg)" />
            <path d="M0,55 L21,50 L42,42 L63,35 L84,28 L105,22 L126,18 L147,15 L168,18 L189,12 L210,8 L231,12 L252,18 L273,15 L294,22 L315,28 L336,32 L357,38 L378,42 L399,48 L420,52 L440,58" stroke="var(--pb-accent)" strokeWidth="1.5" fill="none" />
          </svg>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {[
            ['Club Champion', '1988 · 91 · 94 · 96'],
            ['Captain', '1990 – 1995'],
            ['Life Member', '2003'],
          ].map(([k, v]) => (
            <div key={k} className="bg-pb-bg border border-accent/20 rounded-lg p-2.5">
              <p className="text-[9px] font-mono uppercase tracking-wide3 text-accent mb-0.5">★ {k}</p>
              <p className="text-[11px] text-pb-dim">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </BrowserChrome>
  )
}

// ── Mock 3: Leaderboard ──────────────────────────────────────────────────
export function MockLeaderboard() {
  const rows = [
    { p: 1, name: 'Jack Barendse', games: 18, runs: 742, avg: 49.46, sr: 88.2, hs: 124 },
    { p: 2, name: 'Tom Whitfield', games: 17, runs: 689, avg: 45.93, sr: 79.1, hs: 98 },
    { p: 3, name: 'Sam Reilly', games: 16, runs: 612, avg: 43.71, sr: 92.4, hs: 110 },
    { p: 4, name: 'Ollie Bennett', games: 18, runs: 588, avg: 36.75, sr: 71.8, hs: 87 },
    { p: 5, name: 'Hugh Marston', games: 14, runs: 521, avg: 47.36, sr: 83.5, hs: 102 },
    { p: 6, name: 'Will Krause', games: 17, runs: 503, avg: 33.53, sr: 76.0, hs: 79 },
    { p: 7, name: 'Lachy Forde', games: 15, runs: 489, avg: 40.75, sr: 81.9, hs: 91 },
    { p: 8, name: 'Charlie Day', games: 18, runs: 462, avg: 30.80, sr: 68.4, hs: 73 },
  ]
  return (
    <BrowserChrome url="applecross.betterstats.cricket/leaderboard">
      <div className="p-5">
        <div className="flex items-end justify-between mb-5">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">2025/26 · 1st Grade · Batting</p>
            <h3 className="text-2xl font-bold">Run Scorers</h3>
          </div>
          <div className="flex gap-1.5">
            <span className="pill-neutral text-accent border-accent/40">Runs ▾</span>
            <span className="pill-neutral">Career</span>
            <span className="pill-neutral">Filters</span>
          </div>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b pb-hairline">
              <th className="text-left py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">#</th>
              <th className="text-left py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Player</th>
              <th className="text-right py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">M</th>
              <th className="text-right py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Runs</th>
              <th className="text-right py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Avg</th>
              <th className="text-right py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">SR</th>
              <th className="text-right py-2 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">HS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.p} className={`border-b pb-hairline ${i === 0 ? 'bg-accent/5' : ''}`}>
                <td className="py-2.5 font-mono text-pb-faint">{String(r.p).padStart(2, '0')}</td>
                <td className="py-2.5 font-medium">{r.name}</td>
                <td className="py-2.5 text-right font-mono tabular-nums">{r.games}</td>
                <td className="py-2.5 text-right font-mono tabular-nums font-semibold">{r.runs}</td>
                <td className="py-2.5 text-right font-mono tabular-nums text-pb-dim">{r.avg.toFixed(2)}</td>
                <td className="py-2.5 text-right font-mono tabular-nums text-pb-dim">{r.sr.toFixed(1)}</td>
                <td className="py-2.5 text-right font-mono tabular-nums text-pb-dim">{r.hs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BrowserChrome>
  )
}

// ── Mock 4: Player profile ────────────────────────────────────────────────
export function MockPlayerProfile() {
  return (
    <BrowserChrome url="applecross.betterstats.cricket/players/jack-barendse">
      <div className="p-5">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-16 h-16 rounded-md bg-gradient-to-br from-emerald-700 to-pb-bg border pb-hairline flex items-center justify-center">
            <span className="font-bold text-2xl">JB</span>
          </div>
          <div className="flex-1">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">All-rounder · Right-arm Medium · Right-handed</p>
            <h3 className="text-2xl font-bold mb-1">Jack Barendse</h3>
            <p className="font-mono text-[11px] text-pb-dim">Applecross CC · 14 seasons · Debut 2011/12</p>
          </div>
          <span className="pill"><span className="dot" />Active</span>
        </div>

        <div className="grid grid-cols-4 gap-3 mb-5">
          {[['Career runs', '4,218'], ['Avg', '38.34'], ['Wickets', '187'], ['Catches', '93']].map(([k, v]) => (
            <div key={k} className="border pb-hairline rounded-md p-3">
              <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">{k}</p>
              <p className="text-2xl font-bold tabular-nums">{v}</p>
            </div>
          ))}
        </div>

        <div className="border pb-hairline rounded-md p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Season avg · Last 10</p>
            <p className="text-[10px] font-mono text-accent">+12.4 ↑</p>
          </div>
          <svg viewBox="0 0 320 80" className="w-full h-20">
            <defs>
              <linearGradient id="jbg" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--pb-accent)" stopOpacity="0.4" />
                <stop offset="100%" stopColor="var(--pb-accent)" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d="M0,55 L32,48 L64,52 L96,40 L128,32 L160,38 L192,28 L224,22 L256,18 L288,12 L320,8 L320,80 L0,80 Z" fill="url(#jbg)" />
            <path d="M0,55 L32,48 L64,52 L96,40 L128,32 L160,38 L192,28 L224,22 L256,18 L288,12 L320,8" stroke="var(--pb-accent)" strokeWidth="1.5" fill="none" />
            {[55,48,52,40,32,38,28,22,18,12,8].map((y, i) => (
              <circle key={i} cx={i*32} cy={y} r="2" fill="var(--pb-accent)" />
            ))}
          </svg>
        </div>
      </div>
    </BrowserChrome>
  )
}

// ── Mock 5: Season yearbook ───────────────────────────────────────────────
export function MockYearbook() {
  return (
    <BrowserChrome url="applecross.betterstats.cricket/yearbook/2024-25">
      <div className="p-6">
        <div className="text-center mb-5">
          <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-2">Volume XIV · The Annual</p>
          <h3 className="font-bold text-4xl leading-tight mb-1">Season 2024<span className="font-normal italic">-25</span></h3>
          <div className="my-4 mx-auto max-w-[120px] border-t pb-hairline" />
          <p className="font-mono text-[11px] text-pb-faint">Applecross CC · 3,857 runs · 213 wickets · 5 grades</p>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="border pb-hairline rounded p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Most Runs</p>
            <p className="font-bold text-lg">J. Barendse</p>
            <p className="font-mono text-[11px] text-pb-dim">742 · avg 49.46</p>
          </div>
          <div className="border pb-hairline rounded p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Most Wickets</p>
            <p className="font-bold text-lg">H. Marston</p>
            <p className="font-mono text-[11px] text-pb-dim">34 · avg 14.20</p>
          </div>
          <div className="border pb-hairline rounded p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Highest Score</p>
            <p className="font-bold text-lg">S. Reilly · 178</p>
            <p className="font-mono text-[11px] text-pb-dim">vs Mosman Park</p>
          </div>
          <div className="border pb-hairline rounded p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Best Bowling</p>
            <p className="font-bold text-lg">8/27</p>
            <p className="font-mono text-[11px] text-pb-dim">T. Whitfield · 3rd grade</p>
          </div>
        </div>

        <div className="border border-accent/40 rounded p-3 bg-accent/5">
          <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">★ Club Champion</p>
          <p className="font-bold text-xl">Jack Barendse</p>
        </div>
      </div>
    </BrowserChrome>
  )
}
