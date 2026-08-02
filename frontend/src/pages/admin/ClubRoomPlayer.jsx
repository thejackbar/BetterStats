import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'

// Club Room Mode — the full-screen TV-loop stage. Meant to be opened once on
// a TV/Chromebook browser and left running: it polls its own data every few
// minutes and rotates through slides on a timer with no one touching it, but
// a person standing at the machine can still pause/skip/exit with the
// keyboard. Same forced-dark "stage" posture as Votes' Awards Night — no
// surrounding app chrome (this route isn't wrapped in BetterStatsLayout, see
// App.jsx), so a refresh lands straight back on the show.
const REFRESH_MS = 5 * 60 * 1000

const STAGE_TOKENS = {
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

export default function ClubRoomPlayer() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
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

  // Clamp a stale index after a refresh shrinks the slide count.
  useEffect(() => {
    if (slides.length && index >= slides.length) setIndex(0)
  }, [slides.length, index])

  const advance = useCallback((dir = 1) => {
    setIndex(i => {
      if (!slides.length) return 0
      return (i + dir + slides.length) % slides.length
    })
  }, [slides.length])

  // Auto-rotate timer, keyed to the current slide's own duration.
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (paused || slides.length < 2) return
    const current = slides[index]
    const ms = Math.max(3, current?.duration_seconds || 15) * 1000
    timerRef.current = setTimeout(() => advance(1), ms)
    return () => clearTimeout(timerRef.current)
  }, [index, paused, slides, advance])

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

  if (error && !data) {
    return (
      <Stage>
        <Center>
          <p className="text-pb-dim text-sm mb-3">Couldn't load Club Room Mode.</p>
          <p className="text-pb-faintest text-xs font-mono mb-4">{error}</p>
          <ExitLink />
        </Center>
      </Stage>
    )
  }

  if (!data) {
    return <Stage><Center><p className="text-pb-faint text-sm">Loading…</p></Center></Stage>
  }

  if (!data.enabled) {
    return (
      <Stage>
        <Center>
          <p className="text-pb-dim text-sm mb-4">Club Room Mode is turned off.</p>
          <ExitLink label="Turn it on" />
        </Center>
      </Stage>
    )
  }

  if (!slides.length) {
    return (
      <Stage>
        <Center>
          <p className="text-pb-dim text-sm mb-4">Nothing in the playlist yet.</p>
          <ExitLink label="Add something to show" />
        </Center>
      </Stage>
    )
  }

  const slide = slides[index]

  return (
    <Stage>
      <div className="absolute top-6 left-7 flex items-center gap-2.5 opacity-80">
        {data.logo_url && <img src={data.logo_url} alt="" className="w-8 h-8 rounded object-contain bg-pb-surface2 p-1" />}
        <span className="text-sm font-bold">{data.club_name}</span>
      </div>
      <div className="absolute top-6 right-7 flex items-center gap-3">
        {paused && <span className="font-mono text-[10px] tracking-wide2 text-pb-amber uppercase">Paused</span>}
        <div className="flex items-center gap-1.5">
          {slides.slice(0, 20).map((_, i) => (
            <span key={i} className="w-[6px] h-[6px] rounded-full"
              style={{ background: i === index ? 'var(--pb-accent)' : 'var(--pb-hairline2)' }} />
          ))}
        </div>
      </div>
      <SlideView slide={slide} />
    </Stage>
  )
}

function Stage({ children }) {
  return (
    <div className="fixed inset-0 z-50 overflow-hidden" style={STAGE_TOKENS}>
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
  if (slide.type === 'fixture') return <FixtureSlide slide={slide} />
  if (slide.type === 'social_post' || slide.type === 'custom_image') return <ImageSlide slide={slide} />
  return null
}

function SponsorSlide({ slide }) {
  return (
    <Center>
      <div className="flex items-center justify-center w-full max-w-[70vw] max-h-[45vh] mb-8">
        {slide.logo_url
          ? <img src={slide.logo_url} alt={slide.title} className="max-w-full max-h-[45vh] object-contain" />
          : <span className="text-4xl font-bold text-pb-text">{slide.title}</span>}
      </div>
      <div className="font-mono text-[11px] tracking-wide3 text-pb-faint uppercase">Proudly supported by</div>
      <div className="text-2xl font-bold mt-1.5">{slide.title}</div>
      {slide.website_url && <div className="text-pb-faintest text-sm mt-2">{slide.website_url.replace(/^https?:\/\//, '')}</div>}
    </Center>
  )
}

function ImageSlide({ slide }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center">
      <img src={slide.image_url} alt={slide.title || ''} className="max-w-full max-h-[85vh] object-contain" />
      {slide.title && <div className="mt-4 text-pb-dim text-sm">{slide.title}</div>}
    </div>
  )
}

function FixtureSlide({ slide }) {
  const when = [slide.played_on, slide.start_time].filter(Boolean).join(' · ')
  return (
    <div className="w-full h-full flex flex-col justify-center px-16">
      <div className="font-mono text-[11px] tracking-wide3 text-pb-accent uppercase mb-2">
        {slide.team_name || 'Upcoming fixture'}{slide.grade_name ? ` · ${slide.grade_name}` : ''}
      </div>
      <div className="text-[52px] font-extrabold leading-tight mb-1">
        {slide.home_away === 'away' ? `${slide.opponent_name || 'TBC'}` : `vs ${slide.opponent_name || 'TBC'}`}
      </div>
      <div className="text-pb-dim text-lg mb-8">
        {when}{slide.venue ? ` · ${slide.venue}` : ''}
      </div>
      {slide.lineup?.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-10 gap-y-2 max-w-4xl">
          {[...slide.lineup].sort((a, b) => (a.batting_order ?? 99) - (b.batting_order ?? 99)).map((p, i) => (
            <div key={i} className="flex items-center gap-2 text-lg">
              <span className="text-pb-faintest font-mono text-sm w-5">{p.batting_order ?? '–'}</span>
              <span className="text-pb-text">{p.display_name}</span>
              {p.is_captain && <span className="text-pb-amber text-xs font-mono">(C)</span>}
              {p.is_wicket_keeper && <span className="text-pb-faint text-xs font-mono">(WK)</span>}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-pb-faintest text-sm">Team not named yet.</div>
      )}
    </div>
  )
}
