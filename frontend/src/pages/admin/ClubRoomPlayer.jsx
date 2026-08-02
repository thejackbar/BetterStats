import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'

// Club Room Mode — the full-screen TV-loop stage. Meant to be opened once on
// a TV/Chromebook browser and left running: it polls its own data every few
// minutes and rotates through slides on a timer with no one touching it, but
// a person standing at the machine can still pause/skip/exit with the
// keyboard. No surrounding app chrome (this route isn't wrapped in
// BetterStatsLayout, see App.jsx), so a refresh lands straight back on the
// show.
const REFRESH_MS = 5 * 60 * 1000

const DARK_TOKENS = {
  '--pb-bg': '#07090f',
  '--pb-surface': '#0d1117',
  '--pb-surface2': '#161b27',
  '--pb-hairline': '#1d2331',
  '--pb-hairline2': '#262d3d',
  '--pb-text': '#e6e8ef',
  '--pb-dim': '#8a90a2',
  '--pb-faint': '#5b6072',
  '--pb-faintest': '#3a3f50',
  color: '#e6e8ef',
  background: '#07090f',
}

const LIGHT_TOKENS = {
  '--pb-bg': '#f3f4f7',
  '--pb-surface': '#ffffff',
  '--pb-surface2': '#eceef2',
  '--pb-hairline': '#e0e2e8',
  '--pb-hairline2': '#d2d5dd',
  '--pb-text': '#12141a',
  '--pb-dim': '#565b68',
  '--pb-faint': '#868c99',
  '--pb-faintest': '#aeb2bd',
  color: '#12141a',
  background: '#f3f4f7',
}

const PLACE = [
  { label: '1ST', accent: '#f4c542' },
  { label: '2ND', accent: 'var(--pb-dim)' },
  { label: '3RD', accent: '#c98b4a' },
]

function shuffled(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function initialsOf(name) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase()
}

export default function ClubRoomPlayer() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [order, setOrder] = useState([])
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [fadeKey, setFadeKey] = useState(0)
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const d = await api.clubRoomPlay()
      setData(d)
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const slides = data?.slides || []

  // Fresh data (first load, or a refresh that changed the slide count) resets
  // the running order — shuffled once up front when Shuffle is on.
  useEffect(() => {
    const idx = slides.map((_, i) => i)
    setOrder(data?.shuffle ? shuffled(idx) : idx)
    setIndex(0)
  }, [slides.length, data?.shuffle]) // eslint-disable-line react-hooks/exhaustive-deps

  const advance = useCallback((dir = 1) => {
    const len = order.length
    if (!len) return
    const next = (index + dir + len) % len
    // Completing a forward loop reshuffles for the next play-through, so
    // "shuffle" means a fresh order every loop, not just every data refresh.
    if (dir === 1 && next === 0 && data?.shuffle) {
      setOrder(shuffled(order))
    }
    setIndex(next)
    setFadeKey(k => k + 1)
  }, [order, index, data?.shuffle])

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (paused || order.length < 2) return
    const current = slides[order[index]]
    const ms = Math.max(3, current?.duration_seconds || 15) * 1000
    timerRef.current = setTimeout(() => advance(1), ms)
    return () => clearTimeout(timerRef.current)
  }, [index, order, paused, slides, advance])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') advance(1)
      if (e.key === 'ArrowLeft') advance(-1)
      if (e.key === ' ') { e.preventDefault(); setPaused(p => !p) }
      if (e.key === 'Escape') navigate('/admin/club-room')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [advance, navigate])

  const tokens = data?.theme === 'light' ? LIGHT_TOKENS : DARK_TOKENS

  if (error && !data) {
    return (
      <Stage tokens={tokens}>
        <Center>
          <p className="text-pb-dim text-sm mb-3">Couldn't load Club Room Mode.</p>
          <p className="text-pb-faintest text-xs font-mono mb-4">{error}</p>
          <ExitLink />
        </Center>
      </Stage>
    )
  }

  if (!data) {
    return <Stage tokens={tokens}><Center><p className="text-pb-faint text-sm">Loading…</p></Center></Stage>
  }

  if (!data.enabled) {
    return (
      <Stage tokens={tokens}>
        <Center>
          <p className="text-pb-dim text-sm mb-4">Club Room Mode is turned off.</p>
          <ExitLink label="Turn it on" />
        </Center>
      </Stage>
    )
  }

  if (!slides.length || !order.length) {
    return (
      <Stage tokens={tokens}>
        <Center>
          <p className="text-pb-dim text-sm mb-4">Nothing in the playlist yet.</p>
          <ExitLink label="Add something to show" />
        </Center>
      </Stage>
    )
  }

  const slide = slides[order[index]]

  return (
    <Stage tokens={tokens}>
      <div className="absolute top-6 left-7 flex items-center gap-2.5 opacity-80 z-10">
        {data.logo_url && <img src={data.logo_url} alt="" className="w-8 h-8 rounded object-contain bg-pb-surface2 p-1" />}
        <span className="text-sm font-bold">{data.club_name}</span>
      </div>
      <div className="absolute top-6 right-7 flex items-center gap-3 z-10">
        {paused && <span className="font-mono text-[10px] tracking-wide2 text-amber-400 uppercase">Paused</span>}
        <div className="flex items-center gap-1.5">
          {order.slice(0, 24).map((_, i) => (
            <span key={i} className="w-[6px] h-[6px] rounded-full transition-colors"
              style={{ background: i === index ? 'var(--pb-accent)' : 'var(--pb-hairline2)' }} />
          ))}
        </div>
      </div>
      <div key={fadeKey} className="w-full h-full club-room-fade">
        <SlideView slide={slide} />
      </div>
      <style>{`
        @keyframes clubRoomFadeIn { from { opacity: 0; transform: scale(1.015); } to { opacity: 1; transform: scale(1); } }
        .club-room-fade { animation: clubRoomFadeIn 700ms ease-out; }
      `}</style>
    </Stage>
  )
}

function Stage({ children, tokens }) {
  return (
    <div className="fixed inset-0 z-50 overflow-hidden" style={tokens}>
      {children}
    </div>
  )
}

function Center({ children }) {
  return <div className="w-full h-full flex flex-col items-center justify-center text-center px-6">{children}</div>
}

function ExitLink({ label = 'Back to setup' }) {
  return (
    <a href="/admin/club-room" className="px-4 py-2 rounded-lg text-sm font-medium"
      style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>{label}</a>
  )
}

function SlideView({ slide }) {
  if (slide.type === 'sponsor') return <SponsorSlide slide={slide} />
  if (slide.type === 'sponsor_grid') return <SponsorGridSlide slide={slide} />
  if (slide.type === 'fixture') return <FixtureSlide slide={slide} />
  if (slide.type === 'social_post' || slide.type === 'custom_image') return <ImageSlide slide={slide} />
  if (slide.type === 'leaderboard') return <LeaderboardSlide slide={slide} />
  if (slide.type === 'records') return <RecordsSlide slide={slide} />
  if (slide.type === 'statlab_report') return <ReportSlide slide={slide} />
  return null
}

// ─── Sponsors ───────────────────────────────────────────────────────────────

function SponsorSlide({ slide }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center relative px-10">
      <div className="absolute inset-0 pointer-events-none"
        style={{ background: 'radial-gradient(ellipse 60% 50% at 50% 45%, color-mix(in srgb, var(--pb-accent) 10%, transparent), transparent 70%)' }} />
      <div className="flex items-center justify-center w-full max-w-[85vw] h-[68vh] relative">
        {slide.logo_url
          ? <img src={slide.logo_url} alt={slide.title} className="max-w-full max-h-full object-contain drop-shadow-2xl" />
          : <span className="text-7xl font-extrabold text-pb-text">{slide.title}</span>}
      </div>
      <div className="mt-8 text-center relative">
        <div className="font-mono text-[13px] tracking-wide4 text-pb-faint uppercase">Proudly supported by</div>
        <div className="text-4xl font-extrabold mt-2 tracking-tight">{slide.title}</div>
        {slide.website_url && <div className="text-pb-faint text-base mt-2">{slide.website_url.replace(/^https?:\/\//, '')}</div>}
      </div>
    </div>
  )
}

function SponsorGridSlide({ slide }) {
  const sponsors = slide.sponsors || []
  const cols = sponsors.length <= 4 ? 2 : sponsors.length <= 9 ? 3 : 4
  return (
    <div className="w-full h-full flex flex-col items-center justify-center px-16">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-faint uppercase mb-8">{slide.title}</div>
      <div className="grid gap-8 w-full max-w-6xl" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {sponsors.map(s => (
          <div key={s.id} className="rounded-2xl p-6 flex items-center justify-center h-40"
            style={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)' }}>
            {s.logo_url
              ? <img src={s.logo_url} alt={s.title} className="max-w-full max-h-full object-contain" />
              : <span className="text-lg font-bold text-pb-text text-center">{s.title}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Images ─────────────────────────────────────────────────────────────────

function ImageSlide({ slide }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center">
      <img src={slide.image_url} alt={slide.title || ''} className="max-w-full max-h-[88vh] object-contain drop-shadow-2xl" />
      {slide.title && <div className="mt-5 text-pb-dim text-base">{slide.title}</div>}
    </div>
  )
}

// ─── Fixtures / Lineups ─────────────────────────────────────────────────────

function FixtureSlide({ slide }) {
  const when = [slide.played_on, slide.start_time].filter(Boolean).join(' · ')
  return (
    <div className="w-full h-full flex flex-col justify-center px-16">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase mb-3">
        {slide.team_name || 'Upcoming fixture'}{slide.grade_name ? ` · ${slide.grade_name}` : ''}
      </div>
      <div className="text-[56px] font-extrabold leading-tight mb-2 tracking-tight">
        {slide.home_away === 'away' ? `${slide.opponent_name || 'TBC'}` : `vs ${slide.opponent_name || 'TBC'}`}
      </div>
      <div className="text-pb-dim text-xl mb-10">
        {when}{slide.venue ? ` · ${slide.venue}` : ''}
      </div>
      {slide.lineup?.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-12 gap-y-3 max-w-4xl">
          {[...slide.lineup].sort((a, b) => (a.batting_order ?? 99) - (b.batting_order ?? 99)).map((p, i) => (
            <div key={i} className="flex items-center gap-3 text-xl">
              <span className="text-pb-faintest font-mono text-sm w-5">{p.batting_order ?? '–'}</span>
              <span className="text-pb-text">{p.display_name}</span>
              {p.is_captain && <span className="text-amber-400 text-xs font-mono">(C)</span>}
              {p.is_wicket_keeper && <span className="text-pb-faint text-xs font-mono">(WK)</span>}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-pb-faintest text-base">Team not named yet.</div>
      )}
    </div>
  )
}

// ─── Leaderboard (podium + table) ───────────────────────────────────────────

function fmtVal(v) {
  if (v === null || v === undefined) return '–'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2)
  return String(v)
}

function primaryValue(row, sortBy) {
  if (row[sortBy] !== undefined && row[sortBy] !== null) return row[sortBy]
  const fallbacks = ['total_runs', 'total_wickets', 'total_catches_non_wk', 'runs', 'wickets']
  for (const k of fallbacks) if (row[k] != null) return row[k]
  return null
}

function LeaderboardSlide({ slide }) {
  const rows = slide.rows || []
  const top3 = rows.slice(0, 3)
  const rest = rows.slice(3, 10)
  return (
    <div className="w-full h-full flex flex-col justify-center px-14">
      <div className="mb-6">
        <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase">{slide.season_label}</div>
        <div className="text-[40px] font-extrabold tracking-tight">{slide.title}</div>
      </div>
      <div className="flex gap-5 mb-6">
        {top3.map((r, i) => {
          const p = PLACE[i] || PLACE[2]
          const val = primaryValue(r, slide.sort_by)
          return (
            <div key={r.player_id || i} className="flex-1 rounded-2xl p-6 relative overflow-hidden"
              style={{
                background: `linear-gradient(160deg, color-mix(in srgb, ${p.accent} 12%, var(--pb-surface)) 0%, var(--pb-surface) 72%)`,
                border: `1px solid color-mix(in srgb, ${p.accent} 35%, transparent)`,
              }}>
              <div className="font-mono text-[13px] font-bold tracking-wide3" style={{ color: p.accent }}>{p.label}</div>
              <div className="flex items-end gap-4 mt-4">
                <span className="w-14 h-14 rounded-full flex items-center justify-center shrink-0 font-mono text-lg font-bold shrink-0"
                  style={{ background: 'var(--pb-surface2)', border: `2px solid color-mix(in srgb, ${p.accent} 45%, transparent)`, color: p.accent }}>
                  {initialsOf(r.name)}
                </span>
                <div className="min-w-0">
                  <div className="text-2xl font-bold tracking-tight truncate">{r.name}</div>
                </div>
              </div>
              <div className="text-[52px] font-extrabold leading-none tabular-nums mt-4" style={{ color: p.accent }}>{fmtVal(val)}</div>
            </div>
          )
        })}
      </div>
      {rest.length > 0 && (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--pb-hairline)' }}>
          {rest.map((r, i) => (
            <div key={r.player_id || i} className="flex items-center justify-between px-5 py-2.5"
              style={{ borderTop: i > 0 ? '1px solid var(--pb-hairline)' : 'none' }}>
              <div className="flex items-center gap-4">
                <span className="font-mono text-sm text-pb-faint w-6">{i + 4}</span>
                <span className="text-lg text-pb-text">{r.name}</span>
              </div>
              <span className="text-lg font-bold tabular-nums text-pb-dim">{fmtVal(primaryValue(r, slide.sort_by))}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Records ────────────────────────────────────────────────────────────────

const RECORD_STAT_CANDIDATES = ['runs', 'wickets', 'average', 'high_score', 'economy', 'fifties', 'hundreds', 'ducks', 'matches']

function recordHeadline(row) {
  for (const k of RECORD_STAT_CANDIDATES) if (row[k] != null) return { key: k, value: row[k] }
  const numKey = Object.keys(row).find(k => typeof row[k] === 'number')
  return numKey ? { key: numKey, value: row[numKey] } : { key: null, value: null }
}

function recordSubline(row, headlineKey) {
  const bits = []
  if (row.season_name && headlineKey !== 'season_name') bits.push(row.season_name)
  if (row.matches != null && headlineKey !== 'matches') bits.push(`${row.matches} matches`)
  if (row.grade_name) bits.push(row.grade_name)
  return bits.join(' · ')
}

function RecordsSlide({ slide }) {
  const rows = slide.rows || []
  const [leader, ...rest] = rows
  const leaderStat = leader ? recordHeadline(leader) : null
  return (
    <div className="w-full h-full flex flex-col justify-center px-14">
      <div className="mb-7">
        <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase">{slide.season_label} · Club Record</div>
        <div className="text-[40px] font-extrabold tracking-tight">{slide.title}</div>
      </div>
      {leader && (
        <div className="rounded-2xl p-7 mb-5 flex items-center gap-7"
          style={{ background: 'linear-gradient(160deg, color-mix(in srgb, var(--pb-accent) 12%, var(--pb-surface)) 0%, var(--pb-surface) 72%)', border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>
          <span className="w-20 h-20 rounded-full flex items-center justify-center shrink-0 font-mono text-2xl font-bold"
            style={{ background: 'var(--pb-surface2)', border: '2px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: 'var(--pb-accent)' }}>
            {initialsOf(leader.name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-3xl font-bold tracking-tight">{leader.name}</div>
            <div className="text-pb-faint text-sm mt-1">{recordSubline(leader, leaderStat?.key)}</div>
          </div>
          <div className="text-[64px] font-extrabold leading-none tabular-nums shrink-0" style={{ color: 'var(--pb-accent)' }}>
            {fmtVal(leaderStat?.value)}
          </div>
        </div>
      )}
      {rest.length > 0 && (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--pb-hairline)' }}>
          {rest.map((r, i) => {
            const s = recordHeadline(r)
            return (
              <div key={i} className="flex items-center justify-between px-5 py-2.5"
                style={{ borderTop: i > 0 ? '1px solid var(--pb-hairline)' : 'none' }}>
                <div className="flex items-center gap-4">
                  <span className="font-mono text-sm text-pb-faint w-6">{i + 2}</span>
                  <span className="text-lg text-pb-text">{r.name}</span>
                  <span className="text-pb-faintest text-xs">{recordSubline(r, s.key)}</span>
                </div>
                <span className="text-lg font-bold tabular-nums text-pb-dim">{fmtVal(s.value)}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Custom StatLab report ──────────────────────────────────────────────────

function niceLabel(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function ReportSlide({ slide }) {
  const rows = slide.rows || []
  const columns = rows.length
    ? Object.keys(rows[0]).filter(k => k !== 'id' && !k.endsWith('_id')).slice(0, 6)
    : []
  return (
    <div className="w-full h-full flex flex-col justify-center px-14">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase mb-2">Custom Report</div>
      <div className="text-[36px] font-extrabold tracking-tight mb-6">{slide.title}</div>
      {columns.length > 0 ? (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--pb-hairline)' }}>
          <div className="grid px-5 py-2.5 font-mono text-[11px] tracking-wide2 uppercase text-pb-faint"
            style={{ gridTemplateColumns: `repeat(${columns.length}, 1fr)`, background: 'var(--pb-surface2)' }}>
            {columns.map(c => <span key={c}>{niceLabel(c)}</span>)}
          </div>
          {rows.slice(0, 10).map((r, i) => (
            <div key={i} className="grid px-5 py-2.5 text-lg"
              style={{ gridTemplateColumns: `repeat(${columns.length}, 1fr)`, borderTop: '1px solid var(--pb-hairline)' }}>
              {columns.map(c => <span key={c} className="truncate text-pb-text">{fmtVal(r[c])}</span>)}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-pb-faintest text-base">No rows to show.</div>
      )}
    </div>
  )
}
