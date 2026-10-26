import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { api } from '../lib/api'
import { PbSpinner } from '../lib/presskit'
import { useClubTheme } from '../hooks/useClubTheme'
import { resolveClubFonts } from '../lib/theme'
import { fmtCount, formatSeason } from '../lib/cricketFormat'
import { rememberClubSlug } from '../lib/clubSlug'
import { useClubSponsors } from '../lib/useClubSponsors'
import { exportNodePng } from '../lib/exportNodePng'
import FlipCard from '../components/FlipCard'
import { CARD_W, CARD_H, PlayerCardFront, PlayerCardBack, cardSponsor, splitName } from '../components/PlayerTradingCard'

// The card's display face follows the club's chosen display font (useClubTheme
// injects any uploaded @font-face); Barlow Condensed stays the default so a
// club with no typography choice sees the card it always had.
const DEFAULT_DISPLAY = "'Barlow Condensed', sans-serif"
function clubDisplayFamily(org) {
  if (!org) return DEFAULT_DISPLAY
  return resolveClubFonts(org).display.cssFamily || DEFAULT_DISPLAY
}

export default function ShareCard() {
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [org, setOrg] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [selectedSeason, setSelectedSeason] = useState('')
  const [rankings, setRankings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [flipped, setFlipped] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')
  const [scale, setScale] = useState(1)
  const fitRef = useRef(null)
  const exportRef = useRef(null)
  // Wear the club's white-label theme (palette + fonts, incl. any uploaded
  // @font-face) the same way the player profile behind this card does.
  useClubTheme(org)
  // This URL carries no club slug, so tell the sponsor list whose sponsors to draw.
  useEffect(() => { rememberClubSlug(org?.slug) }, [org?.slug])
  const sponsorData = useClubSponsors(org?.slug)
  const sponsor = cardSponsor(sponsorData)

  // The card is drawn at one fixed size; shrink the whole thing to fit a phone rather than reflowing it.
  useLayoutEffect(() => {
    const el = fitRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const fit = () => setScale(Math.min(1.12, el.clientWidth / CARD_W))
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [loading, !!data])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.getPlayerStats(playerId)
      .then(d => {
        setData(d)
        if (d.player?.organisation_id) {
          api.getOrg(d.player.organisation_id).then(setOrg).catch(() => {})
          api.getOrgSeasons(d.player.organisation_id).then(setSeasons).catch(() => {})
        }
        api.getPlayerRankings(playerId).then(setRankings).catch(() => {})
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [playerId])

  useEffect(() => {
    if (loading) return
    setStatsLoading(true)
    const seasonId = selectedSeason || undefined
    api.getPlayerStats(playerId, { seasonId })
      .then(d => setData(prev => prev ? { ...prev, ...d } : d))
      .catch(() => {})
      .finally(() => setStatsLoading(false))
    api.getPlayerRankings(playerId, { seasonId })
      .then(setRankings)
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSeason])

  if (loading) return <PbSpinner message="Loading…" />
  if (!data) return <div className="min-h-screen bg-pb-bg flex items-center justify-center"><p className="text-pb-red font-mono text-sm">Player not found</p></div>

  const { player, career_batting: cb, career_bowling: cbw, career_fielding: cf } = data
  const seasonLabel = selectedSeason
    ? (seasons.find(s => s.id === selectedSeason)?.name ?? 'Season')
    : 'Career Statistics'

  const { first: pFirst, last: pLast } = splitName(player.display_name || player.name)
  const prettyName = [pFirst, pLast].filter(Boolean).join(' ')

  const handleShare = async () => {
    const url = window.location.href
    const text = `${prettyName} — ${fmtCount(cb?.total_runs ?? 0)} runs, ${fmtCount(cbw?.total_wickets ?? 0)} wickets | BetterCricket`

    if (navigator.share) {
      try {
        await navigator.share({ title: `${prettyName} — BetterCricket`, text, url })
      } catch {}
    } else {
      await navigator.clipboard.writeText(`${text}\n${url}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const accent = org?.theme_config?.accent || org?.accent_color || '#16c784'
  const display = clubDisplayFamily(org)
  const faceProps = { player, org, accent, display, rankings, photoUrl: player.photo_url, heroUrl: player.hero_photo_url, seasonLabel, cb, cbw, cf }
  const front = <PlayerCardFront {...faceProps} sponsor={sponsor} />
  const back = <PlayerCardBack {...faceProps} />

  const handleSave = async () => {
    setSaving(true); setSaveErr('')
    try {
      await exportNodePng(exportRef.current, `${(prettyName || 'player').toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${flipped ? 'stats' : 'card'}`, { width: CARD_W, height: CARD_H, backgroundColor: 'transparent' })
    } catch { setSaveErr('Could not make the image. Try again.') } finally { setSaving(false) }
  }

  const btn = 'px-5 py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition'
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link to={`/players/${playerId}`} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">← BACK TO PROFILE</Link>
          <h1 className="font-display font-bold text-3xl text-pb-text mt-3 tracking-tight">Share Card</h1>
          <p className="text-pb-faint text-sm mt-1">Tap the card to turn it over for the stats</p>
        </div>

        {seasons.length > 0 && (
          <div className="mb-6 flex items-center gap-3">
            <select
              value={selectedSeason}
              onChange={e => setSelectedSeason(e.target.value)}
              className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
            >
              <option value="">Career Statistics</option>
              {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
            </select>
            {statsLoading && <span className="font-mono text-[10px] text-pb-faint">updating…</span>}
          </div>
        )}

        <div ref={fitRef} className="w-full mx-auto" style={{ maxWidth: CARD_W * 1.12, height: CARD_H * scale }}>
          <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
            <FlipCard
              width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped(f => !f)}
              label={flipped ? 'Showing stats. Turn the card back over' : 'Showing the card. Turn it over for stats'}
              front={front} back={back}
            />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3 items-center justify-center">
          <button onClick={() => setFlipped(f => !f)} className={`${btn} border pb-hairline text-pb-text`}>
            {flipped ? 'SHOW CARD' : 'SHOW STATS'}
          </button>
          <button onClick={handleSave} disabled={saving} className={`${btn} text-pb-bg`} style={{ background: 'var(--pb-accent)', opacity: saving ? 0.6 : 1 }}>
            {saving ? 'RENDERING…' : 'SAVE IMAGE'}
          </button>
          <button onClick={handleShare} className={`${btn} border pb-hairline text-pb-text`}>
            {copied ? 'COPIED!' : (typeof navigator !== 'undefined' && navigator.share ? 'SHARE LINK' : 'COPY LINK')}
          </button>
        </div>
        {saveErr && <p className="mt-3 text-center font-mono text-[10px] text-pb-red">{saveErr}</p>}
        <p className="mt-3 text-center font-mono text-[10px] text-pb-faintest">Save image keeps whichever side is showing</p>

        {/* The copy that gets rendered to an image: flat, unscaled and off screen, so it always matches the design size. */}
        <div aria-hidden style={{ position: 'fixed', left: -10000, top: 0, pointerEvents: 'none' }}>
          <div ref={exportRef} style={{ width: CARD_W, height: CARD_H }}>{flipped ? back : front}</div>
        </div>
      </main>
    </div>
  )
}
