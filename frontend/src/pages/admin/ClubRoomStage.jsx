import { useCallback, useEffect, useRef, useState } from 'react'
import TeamBadge from '../../components/TeamBadge'
import { resolveTheme, safeAccent2, gradientCss } from '../../lib/theme'

// Club Room Mode — the full-screen TV-loop stage. Meant to be opened once on
// a TV/Chromebook browser and left running: it polls its own data every few
// minutes and rotates through slides on a timer with no one touching it, but
// a person standing at the machine can still pause/skip/exit with the
// keyboard.
//
// Shared by both ways into the show: the authenticated admin preview
// (ClubRoomPlayer.jsx, fetches via the logged-in `/club-admin/club-room/play`)
// and the public PIN-gated link (PublicClubRoom.jsx, fetches via
// `/public/club-room/{token}/play` once unlocked) — everything about
// RENDERING the slideshow lives here; the two callers only differ in how
// they fetch data and where "exit" goes.
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

// Merges the club's own brand colours (organisations.theme_config — the same
// source the public club pages theme themselves from, via resolveTheme/
// buildThemeCss in lib/theme.js) on top of the stage's dark/light surface
// tokens. Previously the stage never set --pb-accent at all, so every card
// gradient/border fell back to whatever --pb-accent happened to be inherited
// from the surrounding admin app — BetterStats' own default green, not the
// club's actual colour.
function buildStageTokens(data) {
  const mode = data?.theme === 'light' ? 'light' : 'dark'
  const base = mode === 'light' ? LIGHT_TOKENS : DARK_TOKENS
  const theme = resolveTheme(data?.theme_config)
  const accent2Safe = safeAccent2(theme.accent2, theme.accent, mode)
  return {
    ...base,
    '--pb-accent': theme.accent,
    '--pb-accent-2': theme.accent2,
    '--pb-accent-2-safe': accent2Safe,
    '--pb-gradient': gradientCss(theme.accent, accent2Safe),
    '--pb-positive': theme.positive,
    '--pb-negative': theme.negative,
    '--pb-amber': theme.chart_milestone,
  }
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

function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
}

// A list that outgrows its box shouldn't just get clipped — this scrolls
// itself from top to bottom at a steady, readable pace (a pause at each end,
// eased in between) instead of being squeezed into whatever's left of the
// slide's display time — a long list on a short slide just won't finish a
// full pass, which reads far better than a rushed blur. No visible
// scrollbar, since nobody's holding a mouse in the club room. A no-op — no
// scrolling at all — when the content already fits.
const SCROLL_PX_PER_SECOND = 42 // a comfortable, readable pace — not rushed

function AutoScrollList({ children, className = '', style }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.scrollTop = 0
    const overflow = el.scrollHeight - el.clientHeight
    if (overflow <= 2) return
    const hold = 1800 // ms paused at the top and again at the bottom
    // A steady, readable pace — NOT squeezed to fit inside the slide's own
    // display time. A long list on a short slide just won't finish a full
    // pass before the slide moves on; that reads far better than rushing to
    // cram everything into whatever time happens to be left.
    const scrollMs = Math.max(2500, (overflow / SCROLL_PX_PER_SECOND) * 1000)
    let raf
    const start = performance.now()
    const tick = (now) => {
      const elapsed = now - start
      if (elapsed < hold) { raf = requestAnimationFrame(tick); return }
      const p = Math.min(1, (elapsed - hold) / scrollMs)
      el.scrollTop = overflow * easeInOutQuad(p)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [children])
  return (
    <div ref={ref} className={`club-room-scroll overflow-y-auto ${className}`} style={style}>
      {children}
    </div>
  )
}

export default function ClubRoomStage({ fetchPlay, onExit, exitLabel = 'Back to setup' }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [order, setOrder] = useState([])
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [fadeKey, setFadeKey] = useState(0)
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const d = await fetchPlay()
      setData(d)
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [fetchPlay])

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
      if (e.key === 'Escape' && onExit) onExit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [advance, onExit])

  const tokens = buildStageTokens(data)

  if (error && !data) {
    return (
      <Stage tokens={tokens}>
        <Center>
          <p className="text-pb-dim text-sm mb-3">Couldn't load Club Room Mode.</p>
          <p className="text-pb-faintest text-xs font-mono mb-4">{error}</p>
          <ExitLink onExit={onExit} label={exitLabel} />
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
          <ExitLink onExit={onExit} label="Turn it on" />
        </Center>
      </Stage>
    )
  }

  if (!slides.length || !order.length) {
    return (
      <Stage tokens={tokens}>
        <Center>
          <p className="text-pb-dim text-sm mb-4">Nothing in the playlist yet.</p>
          <ExitLink onExit={onExit} label="Add something to show" />
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
        <SlideView slide={slide} clubLogoUrl={data.logo_url} />
      </div>
      <style>{`
        @keyframes clubRoomFadeIn { from { opacity: 0; transform: scale(1.015); } to { opacity: 1; transform: scale(1); } }
        .club-room-fade { animation: clubRoomFadeIn 700ms ease-out; }
        .club-room-scroll { scrollbar-width: none; -ms-overflow-style: none; }
        .club-room-scroll::-webkit-scrollbar { display: none; }
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

// No destination to offer a public TV viewer (they have no admin session to
// jump into) — the button only renders when the caller passed an `onExit`.
function ExitLink({ onExit, label = 'Back to setup' }) {
  if (!onExit) return null
  return (
    <button onClick={onExit} className="px-4 py-2 rounded-lg text-sm font-medium"
      style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>{label}</button>
  )
}

function SlideView({ slide, clubLogoUrl }) {
  if (slide.type === 'sponsor') return <SponsorSlide slide={slide} />
  if (slide.type === 'sponsor_grid') return <SponsorGridSlide slide={slide} />
  if (slide.type === 'fixture') return <FixtureSlide slide={slide} clubLogoUrl={clubLogoUrl} />
  if (slide.type === 'social_post' || slide.type === 'custom_image') return <ImageSlide slide={slide} />
  if (slide.type === 'leaderboard') return <LeaderboardSlide slide={slide} clubLogoUrl={clubLogoUrl} />
  if (slide.type === 'records') return <RecordsSlide slide={slide} clubLogoUrl={clubLogoUrl} />
  if (slide.type === 'statlab_report') return <ReportSlide slide={slide} />
  return null
}

// A player's own photo, falling back to the club's crest, then initials —
// "utilise the player pictures... default to the club's logo if there's no
// image". Mirrors TeamBadge's onError-cascade, just with one more tier.
function PlayerAvatar({ playerId, name, clubLogoUrl, size = 44, accent = 'var(--pb-accent)' }) {
  const [stage, setStage] = useState(playerId ? 'photo' : (clubLogoUrl ? 'club' : 'initials'))
  const border = `2px solid color-mix(in srgb, ${accent} 45%, transparent)`
  if (stage === 'initials') {
    return (
      <span className="rounded-full flex items-center justify-center shrink-0 font-mono font-bold"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.32), background: 'var(--pb-surface2)', border, color: accent }}>
        {initialsOf(name)}
      </span>
    )
  }
  const src = stage === 'photo' ? `/api/images/players/${playerId}/photo` : clubLogoUrl
  return (
    <img
      src={src} alt=""
      onError={() => setStage(s => (s === 'photo' && clubLogoUrl) ? 'club' : 'initials')}
      className={`rounded-full shrink-0 ${stage === 'club' ? 'object-contain p-1.5 bg-pb-surface2' : 'object-cover'}`}
      style={{ width: size, height: size, border }}
    />
  )
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
    <div className="w-full h-full flex flex-col items-center px-16 py-12">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-faint uppercase mb-8 shrink-0">{slide.title}</div>
      <AutoScrollList className="flex-1 min-h-0 w-full flex justify-center">
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
      </AutoScrollList>
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

function FixtureSlide({ slide, clubLogoUrl }) {
  const when = [slide.played_on, slide.start_time].filter(Boolean).join(' · ')
  // Our own crest wins when Grassroots has one for us too — it's the club's
  // own controlled upload, always current — else the club's uploaded logo
  // stands in; the opponent has no such fallback, so a missing crest there
  // just means TeamBadge's own initials treatment.
  const ourLogo = slide.our_logo_url || clubLogoUrl
  return (
    <div className="w-full h-full flex flex-col px-16 py-12">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase mb-6 shrink-0">
        {slide.team_name || 'Upcoming fixture'}{slide.grade_name ? ` · ${slide.grade_name}` : ''}
      </div>
      <div className="flex items-center gap-6 mb-7 shrink-0">
        <TeamBadge name={slide.team_name || 'Us'} logoUrl={ourLogo} size={104} />
        <span className="font-display text-2xl font-bold text-pb-faintest px-1">vs</span>
        <TeamBadge name={slide.opponent_name || 'TBC'} logoUrl={slide.opponent_logo_url} size={104} />
        <div className="ml-3">
          <div className="text-[46px] font-extrabold leading-tight tracking-tight">
            {slide.opponent_name || 'TBC'}
          </div>
          <div className="text-pb-dim text-lg mt-1">
            {when}{slide.venue ? ` · ${slide.venue}` : ''}
          </div>
        </div>
      </div>
      {slide.lineup?.length > 0 ? (
        <AutoScrollList className="flex-1 min-h-0">
          <div className="h-full flex flex-col justify-between">
            {[...slide.lineup].sort((a, b) => (a.batting_order ?? 99) - (b.batting_order ?? 99)).map((p, i) => (
              <div key={i} className="flex items-center gap-5"
                style={{ borderTop: i > 0 ? '1px solid var(--pb-hairline)' : 'none' }}>
                <span className="text-pb-faintest font-mono text-xl w-9 shrink-0">{p.batting_order ?? '–'}</span>
                <span className="text-3xl text-pb-text font-medium flex-1 truncate">{p.display_name}</span>
                {p.is_captain && <span className="text-amber-400 text-sm font-mono tracking-wide2 shrink-0">CAPTAIN</span>}
                {p.is_wicket_keeper && <span className="text-pb-faint text-sm font-mono tracking-wide2 shrink-0">KEEPER</span>}
              </div>
            ))}
          </div>
        </AutoScrollList>
      ) : (
        <div className="flex-1 flex items-center text-pb-faintest text-base">Team not named yet.</div>
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

function LeaderboardSlide({ slide, clubLogoUrl }) {
  const rows = slide.rows || []
  const top3 = rows.slice(0, 3)
  const rest = rows.slice(3)
  return (
    <div className="w-full h-full flex flex-col px-14 py-12">
      <div className="mb-6 shrink-0">
        <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase">{slide.season_label}</div>
        <div className="text-[40px] font-extrabold tracking-tight leading-tight">{slide.title}</div>
      </div>
      <div className="flex gap-5 mb-6 shrink-0">
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
                <PlayerAvatar playerId={r.player_id} name={r.name} clubLogoUrl={clubLogoUrl} size={56} accent={p.accent} />
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
        <AutoScrollList
          className="flex-1 min-h-0 rounded-xl"
          style={{ border: '1px solid var(--pb-hairline)' }}
        >
          {rest.map((r, i) => (
            <div key={r.player_id || i} className="flex items-center justify-between px-5 py-2"
              style={{ borderTop: i > 0 ? '1px solid var(--pb-hairline)' : 'none' }}>
              <div className="flex items-center gap-3.5">
                <span className="font-mono text-sm text-pb-faint w-6">{i + 4}</span>
                <PlayerAvatar playerId={r.player_id} name={r.name} clubLogoUrl={clubLogoUrl} size={32} accent="var(--pb-dim)" />
                <span className="text-lg text-pb-text">{r.name}</span>
              </div>
              <span className="text-lg font-bold tabular-nums text-pb-dim">{fmtVal(primaryValue(r, slide.sort_by))}</span>
            </div>
          ))}
        </AutoScrollList>
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

function RecordsSlide({ slide, clubLogoUrl }) {
  const rows = slide.rows || []
  const [leader, ...rest] = rows
  const leaderStat = leader ? recordHeadline(leader) : null
  return (
    <div className="w-full h-full flex flex-col px-14 py-12">
      <div className="mb-7 shrink-0">
        <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase">{slide.season_label} · Club Record</div>
        <div className="text-[40px] font-extrabold tracking-tight leading-tight">{slide.title}</div>
      </div>
      {leader && (
        <div className="rounded-2xl p-7 mb-5 flex items-center gap-7 shrink-0"
          style={{ background: 'linear-gradient(160deg, color-mix(in srgb, var(--pb-accent) 12%, var(--pb-surface)) 0%, var(--pb-surface) 72%)', border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>
          <PlayerAvatar playerId={leader.player_id} name={leader.name} clubLogoUrl={clubLogoUrl} size={80} accent="var(--pb-accent)" />
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
        <AutoScrollList
          className="flex-1 min-h-0 rounded-xl"
          style={{ border: '1px solid var(--pb-hairline)' }}
        >
          {rest.map((r, i) => {
            const s = recordHeadline(r)
            return (
              <div key={i} className="flex items-center justify-between px-5 py-2"
                style={{ borderTop: i > 0 ? '1px solid var(--pb-hairline)' : 'none' }}>
                <div className="flex items-center gap-3.5">
                  <span className="font-mono text-sm text-pb-faint w-6">{i + 2}</span>
                  <PlayerAvatar playerId={r.player_id} name={r.name} clubLogoUrl={clubLogoUrl} size={32} accent="var(--pb-dim)" />
                  <span className="text-lg text-pb-text">{r.name}</span>
                  <span className="text-pb-faintest text-xs">{recordSubline(r, s.key)}</span>
                </div>
                <span className="text-lg font-bold tabular-nums text-pb-dim">{fmtVal(s.value)}</span>
              </div>
            )
          })}
        </AutoScrollList>
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
  // The backend picks columns (name + whatever the report is sorted by,
  // always included, plus whatever else fits) — fall back to a plain first-6
  // slice only if an older cached response has no `columns` of its own.
  const columns = slide.columns?.length
    ? slide.columns
    : (rows.length ? Object.keys(rows[0]).filter(k => k !== 'id' && !k.endsWith('_id')).slice(0, 6) : [])
  return (
    <div className="w-full h-full flex flex-col px-14 py-12">
      <div className="font-mono text-[13px] tracking-wide4 text-pb-accent uppercase mb-2 shrink-0">Custom Report</div>
      <div className="text-[36px] font-extrabold tracking-tight mb-6 shrink-0">{slide.title}</div>
      {columns.length > 0 ? (
        <AutoScrollList
          className="flex-1 min-h-0 rounded-xl"
          style={{ border: '1px solid var(--pb-hairline)' }}
        >
          <div className="grid px-5 py-2.5 font-mono text-[11px] tracking-wide2 uppercase text-pb-faint sticky top-0"
            style={{ gridTemplateColumns: `repeat(${columns.length}, 1fr)`, background: 'var(--pb-surface2)' }}>
            {columns.map(c => <span key={c}>{niceLabel(c)}</span>)}
          </div>
          {rows.map((r, i) => (
            <div key={i} className="grid px-5 py-2.5 text-lg"
              style={{ gridTemplateColumns: `repeat(${columns.length}, 1fr)`, borderTop: '1px solid var(--pb-hairline)', background: 'var(--pb-surface)' }}>
              {columns.map(c => <span key={c} className="truncate text-pb-text">{fmtVal(r[c])}</span>)}
            </div>
          ))}
        </AutoScrollList>
      ) : (
        <div className="text-pb-faintest text-base">No rows to show.</div>
      )}
    </div>
  )
}
