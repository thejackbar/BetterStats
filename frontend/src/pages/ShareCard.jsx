import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { PbSpinner } from '../lib/presskit'
import betterStatsLogo from '../assets/betterstatslogo_white.png'

function hexWithAlpha(hex, alpha) {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return `rgba(22,199,132,${alpha})`
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function useIsMobile(breakpoint = 640) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' && window.innerWidth < breakpoint
  )
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < breakpoint)
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [breakpoint])
  return isMobile
}

function RankBadge({ rank, label, accent }) {
  if (!rank) return null
  const ordinal = rank === 1 ? '1st' : rank === 2 ? '2nd' : rank === 3 ? '3rd' : `${rank}th`
  return (
    <span style={{
      background: hexWithAlpha(accent, 0.15),
      border: `1px solid ${hexWithAlpha(accent, 0.4)}`,
      borderRadius: 5,
      padding: '2px 8px',
      fontSize: 10,
      color: accent,
      fontFamily: "'JetBrains Mono', monospace",
      letterSpacing: 0.5,
    }}>
      #{ordinal} {label}
    </span>
  )
}

function ShareCardVisual({ player, cb, cbw, cf, season, org, rankings, photoUrl }) {
  const isMobile = useIsMobile()
  const accent = org?.accent_color || '#16c784'

  // Fallback chain: player photo → club logo → BetterStats logo.
  // Rebuild when props change (org loads async after first render).
  const fallbackChain = [photoUrl, org?.logo_url, betterStatsLogo].filter(Boolean)
  const [imgSrc, setImgSrc] = useState(fallbackChain[0] || betterStatsLogo)
  const [fallbackIdx, setFallbackIdx] = useState(0)

  useEffect(() => {
    const first = [photoUrl, org?.logo_url, betterStatsLogo].find(Boolean) || betterStatsLogo
    setImgSrc(first)
    setFallbackIdx(0)
  }, [photoUrl, org?.logo_url])

  const handleImgError = () => {
    const next = fallbackIdx + 1
    if (next < fallbackChain.length) {
      setFallbackIdx(next)
      setImgSrc(fallbackChain[next])
    }
  }

  const statSize = (highlight) => highlight ? (isMobile ? 24 : 30) : (isMobile ? 18 : 22)

  const fieldingHasData = cf && (
    (cf.total_catches_non_wk ?? cf.total_catches ?? 0) > 0 ||
    (cf.total_catches_wk ?? 0) > 0 ||
    (cf.total_run_outs ?? 0) > 0 ||
    (cf.total_stumpings ?? 0) > 0
  )

  return (
    <div
      id="share-card"
      style={{
        width: '100%',
        maxWidth: 600,
        boxSizing: 'border-box',
        background: 'linear-gradient(135deg, #0d1b2a 0%, #0f2235 60%, #0d1b2a 100%)',
        borderRadius: 16,
        padding: isMobile ? '20px 16px' : '32px 36px',
        fontFamily: "'Inter', sans-serif",
        color: '#fff',
        position: 'relative',
        overflow: 'hidden',
        border: `1px solid ${hexWithAlpha(accent, 0.2)}`,
      }}
    >
      {/* Watermark */}
      <div style={{
        position: 'absolute', bottom: isMobile ? 14 : 20, right: isMobile ? 16 : 24,
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: 12, color: hexWithAlpha(accent, 0.3),
        letterSpacing: 2, textTransform: 'uppercase',
      }}>
        BetterStats
      </div>

      {/* Header: org + player photo */}
      <div style={{ marginBottom: isMobile ? 12 : 16, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          {org?.logo_url && (
            <img src={org.logo_url} alt="" style={{ width: isMobile ? 28 : 32, height: isMobile ? 28 : 32, objectFit: 'contain', borderRadius: 4, flexShrink: 0 }} />
          )}
          <div style={{ minWidth: 0 }}>
            {org && (
              <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: isMobile ? 11 : 13, color: accent, letterSpacing: 2, textTransform: 'uppercase', margin: 0 }}>
                {org.name}
              </p>
            )}
            {season && (
              <p style={{ fontSize: isMobile ? 11 : 12, color: '#64748b', margin: '2px 0 0' }}>{season}</p>
            )}
          </div>
        </div>

        {/* Player photo */}
        <img
          src={imgSrc}
          alt=""
          onError={handleImgError}
          style={{
            width: isMobile ? 48 : 64,
            height: isMobile ? 48 : 64,
            objectFit: 'cover',
            borderRadius: 8,
            border: `2px solid ${hexWithAlpha(accent, 0.3)}`,
            flexShrink: 0,
          }}
        />
      </div>

      {/* Player name */}
      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: isMobile ? 36 : 52, fontWeight: 800, lineHeight: 1,
        color: '#fff', margin: isMobile ? '0 0 8px' : '0 0 10px', textTransform: 'uppercase',
        letterSpacing: 1,
      }}>
        {player?.name || ''}
      </h1>

      {/* Ranking badges */}
      {rankings && (rankings.runs_rank || rankings.wickets_rank || rankings.catches_rank) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: isMobile ? 14 : 18 }}>
          <RankBadge rank={rankings.runs_rank} label="runs" accent={accent} />
          <RankBadge rank={rankings.wickets_rank} label="wickets" accent={accent} />
          <RankBadge rank={rankings.catches_rank} label="catches" accent={accent} />
        </div>
      )}

      {/* Batting stats row */}
      {cb && (
        <div style={{ marginBottom: isMobile ? 14 : 20 }}>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 11, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 10px' }}>
            Batting
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: isMobile ? 6 : 10 }}>
            {[
              { label: 'M', value: cb.games },
              { label: 'Inns', value: cb.innings },
              { label: 'Runs', value: cb.total_runs, highlight: true },
              { label: 'HS', value: cb.high_score },
              { label: 'Ave', value: cb.average },
            ].map(({ label, value, highlight }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: statSize(highlight),
                  fontWeight: 700,
                  color: highlight ? accent : '#fff',
                  lineHeight: 1,
                }}>
                  {value ?? '—'}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 4 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
          {(cb.hundreds > 0 || cb.fifties > 0) && (
            <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
              {cb.hundreds > 0 && (
                <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 10px', fontSize: 11, color: accent }}>
                  {cb.hundreds} x {cb.hundreds === 1 ? '100' : '100s'}
                </span>
              )}
              {cb.fifties > 0 && (
                <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 10px', fontSize: 11, color: accent }}>
                  {cb.fifties} x {cb.fifties === 1 ? '50' : '50s'}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Bowling stats row */}
      {cbw && cbw.total_wickets > 0 && (
        <div style={{ borderTop: '1px solid rgba(30,41,59,0.8)', paddingTop: isMobile ? 12 : 16, marginBottom: isMobile ? 14 : 20 }}>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 11, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 10px' }}>
            Bowling
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: isMobile ? 8 : 12 }}>
            {[
              { label: 'Wkts', value: cbw.total_wickets, highlight: true },
              { label: 'Ave', value: cbw.average },
              { label: 'Econ', value: cbw.economy },
              { label: 'Best', value: cbw.best_bowling_figures || (cbw.best_figures_wickets ? `${cbw.best_figures_wickets}w` : '—') },
            ].map(({ label, value, highlight }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: statSize(highlight),
                  fontWeight: 700,
                  color: highlight ? accent : '#fff',
                  lineHeight: 1,
                }}>
                  {value ?? '—'}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 4 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
          {cbw.five_fors > 0 && (
            <div style={{ marginTop: 12 }}>
              <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 10px', fontSize: 11, color: accent }}>
                {cbw.five_fors} x {cbw.five_fors === 1 ? '5fa' : '5fas'}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Fielding — same 4-col grid layout as Bowling so all three disciplines sit at the same visual weight */}
      {fieldingHasData && (
        <div style={{ borderTop: '1px solid rgba(30,41,59,0.8)', paddingTop: isMobile ? 12 : 16 }}>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 11, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 10px' }}>
            Fielding
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: isMobile ? 8 : 12 }}>
            {[
              { label: 'Ct', value: cf.total_catches_non_wk ?? cf.total_catches, highlight: true },
              { label: 'Ct (WK)', value: cf.total_catches_wk },
              { label: 'RO', value: cf.total_run_outs },
              { label: 'Stmps', value: cf.total_stumpings },
            ].map(({ label, value, highlight }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: statSize(highlight),
                  fontWeight: 700,
                  color: highlight ? accent : '#fff',
                  lineHeight: 1,
                }}>
                  {value ?? '—'}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 4 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
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

  const handleShare = async () => {
    const url = window.location.href
    const text = `${player.name} — ${cb?.total_runs ?? 0} runs, ${cbw?.total_wickets ?? 0} wickets | BetterStats`

    if (navigator.share) {
      try {
        await navigator.share({ title: `${player.name} — BetterStats`, text, url })
      } catch {}
    } else {
      await navigator.clipboard.writeText(`${text}\n${url}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link to={`/players/${playerId}`} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">← BACK TO PROFILE</Link>
          <h1 className="font-display font-bold text-3xl text-pb-text mt-3 tracking-tight">Share Card</h1>
          <p className="text-pb-faint text-sm mt-1">Screenshot this card to share on social media</p>
        </div>

        {seasons.length > 0 && (
          <div className="mb-6 flex items-center gap-3">
            <select
              value={selectedSeason}
              onChange={e => setSelectedSeason(e.target.value)}
              className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
            >
              <option value="">Career Statistics</option>
              {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {statsLoading && <span className="font-mono text-[10px] text-pb-faint">updating…</span>}
          </div>
        )}

        <style>{`
          .magic-glow-wrapper {
            padding: 5px;
            border-radius: 1rem;
            overflow: visible;
            background: var(--magic-gradient);
            position: relative;
            z-index: 1;
          }
          .magic-glow-wrapper::after {
            position: absolute;
            content: "";
            top: 30px;
            left: 0;
            right: 0;
            z-index: -1;
            height: 100%;
            width: 100%;
            transform: scale(0.8);
            filter: blur(28px);
            background: var(--magic-gradient);
            transition: opacity .5s;
          }
          .magic-glow-wrapper:hover::after {
            opacity: 0;
          }
        `}</style>
        <div className="flex justify-center pb-4">
          <div
            className="magic-glow-wrapper w-full max-w-[610px]"
            style={{ '--magic-gradient': `linear-gradient(to left, ${org?.accent_color || '#16c784'} 0%, ${org?.theme_config?.dark?.surface2 || '#0d2a4e'} 100%)` }}
          >
            <ShareCardVisual
              player={player}
              cb={cb}
              cbw={cbw}
              cf={cf}
              season={seasonLabel}
              org={org}
              rankings={rankings}
              photoUrl={player.photo_url}
            />
          </div>
        </div>

        <div className="mt-6 flex gap-3 items-center">
          <button
            onClick={handleShare}
            className="px-5 py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            {copied ? 'COPIED!' : (typeof navigator !== 'undefined' && navigator.share ? 'SHARE' : 'COPY LINK')}
          </button>
          <p className="font-mono text-[10px] text-pb-faintest">
            Take a screenshot of the card above to save as an image
          </p>
        </div>
      </main>
    </div>
  )
}
