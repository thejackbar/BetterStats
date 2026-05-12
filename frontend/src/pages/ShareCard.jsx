import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'

function hexWithAlpha(hex, alpha) {
  // hex like "#rrggbb" → "rgba(r,g,b,a)"
  if (!hex || hex[0] !== '#' || hex.length !== 7) return `rgba(22,199,132,${alpha})`
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function ShareCardVisual({ player, cb, cbw, cf, season, org }) {
  const accent = org?.accent_color || '#16c784'
  return (
    <div
      id="share-card"
      style={{
        width: 600,
        background: 'linear-gradient(135deg, #0d1b2a 0%, #0f2235 60%, #0d1b2a 100%)',
        borderRadius: 16,
        padding: '32px 36px',
        fontFamily: "'Inter', sans-serif",
        color: '#fff',
        position: 'relative',
        overflow: 'hidden',
        border: `1px solid ${hexWithAlpha(accent, 0.2)}`,
      }}
    >
      {/* Accent bar */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 4, background: accent }} />

      {/* Watermark */}
      <div style={{
        position: 'absolute', bottom: 20, right: 24,
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: 12, color: hexWithAlpha(accent, 0.3),
        letterSpacing: 2, textTransform: 'uppercase',
      }}>
        BetterStats
      </div>

      {/* Org + season */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        {org?.logo_url && (
          <img src={org.logo_url} alt="" style={{ width: 32, height: 32, objectFit: 'contain', borderRadius: 4 }} />
        )}
        <div>
          {org && (
            <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 13, color: accent, letterSpacing: 2, textTransform: 'uppercase', margin: 0 }}>
              {org.name}
            </p>
          )}
          {season && (
            <p style={{ fontSize: 12, color: '#64748b', margin: '2px 0 0' }}>{season}</p>
          )}
        </div>
      </div>

      {/* Player name */}
      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: 52, fontWeight: 800, lineHeight: 1,
        color: '#fff', margin: '0 0 24px', textTransform: 'uppercase',
        letterSpacing: 1,
      }}>
        {player?.name || ''}
      </h1>

      {/* Batting stats row */}
      {cb && (
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 11, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 12px' }}>
            Batting
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
            {[
              { label: 'Inns', value: cb.innings },
              { label: 'Runs', value: cb.total_runs, highlight: true },
              { label: 'HS', value: cb.high_score },
              { label: 'Ave', value: cb.average },
              { label: 'SR', value: cb.strike_rate },
            ].map(({ label, value, highlight }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: highlight ? 30 : 22,
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
            <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
              {cb.hundreds > 0 && (
                <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 10px', fontSize: 11, color: accent }}>
                  {cb.hundreds} {cb.hundreds === 1 ? '100' : '100s'}
                </span>
              )}
              {cb.fifties > 0 && (
                <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 10px', fontSize: 11, color: accent }}>
                  {cb.fifties} {cb.fifties === 1 ? '50' : '50s'}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Bowling stats row */}
      {cbw && cbw.total_wickets > 0 && (
        <div style={{ borderTop: '1px solid rgba(30,41,59,0.8)', paddingTop: 16 }}>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 11, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 12px' }}>
            Bowling
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[
              { label: 'Wkts', value: cbw.total_wickets, highlight: true },
              { label: 'Ave', value: cbw.average },
              { label: 'Econ', value: cbw.economy },
              { label: 'Best', value: cbw.best_bowling_figures || (cbw.best_figures_wickets ? `${cbw.best_figures_wickets}w` : '—') },
            ].map(({ label, value, highlight }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: highlight ? 30 : 22,
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

      {/* Fielding */}
      {cf && (cf.total_catches > 0 || cf.total_stumpings > 0) && (
        <div style={{ borderTop: '1px solid rgba(30,41,59,0.8)', paddingTop: 12, marginTop: 16 }}>
          <div style={{ display: 'flex', gap: 20 }}>
            {cf.total_catches > 0 && (
              <span style={{ fontSize: 12, color: '#94a3b8' }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#fff', fontWeight: 700 }}>{cf.total_catches}</span> catches
              </span>
            )}
            {cf.total_stumpings > 0 && (
              <span style={{ fontSize: 12, color: '#94a3b8' }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#fff', fontWeight: 700 }}>{cf.total_stumpings}</span> stumpings
              </span>
            )}
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
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  // Initial load: pull career stats and the org's seasons + branding.
  useEffect(() => {
    api.getPlayerStats(playerId)
      .then(d => {
        setData(d)
        if (d.player?.organisation_id) {
          api.getOrg(d.player.organisation_id).then(setOrg).catch(() => {})
          api.getOrgSeasons(d.player.organisation_id).then(setSeasons).catch(() => {})
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [playerId])

  // Refetch stats when the user picks a different season so the card actually
  // reflects the dropdown. Empty string = career (no season_id sent).
  useEffect(() => {
    if (loading) return
    setStatsLoading(true)
    api.getPlayerStats(playerId, { seasonId: selectedSeason || undefined })
      .then(d => setData(prev => prev ? { ...prev, ...d } : d))
      .catch(() => {})
      .finally(() => setStatsLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSeason])

  if (loading) return <LoadingSpinner message="Loading…" />
  if (!data) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Player not found</div>

  const { player, career_batting: cb, career_bowling: cbw, career_fielding: cf } = data
  const seasonLabel = selectedSeason
    ? seasons.find(s => s.id === selectedSeason)?.name
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
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link to={`/players/${playerId}`} className="text-accent text-sm hover:underline">← Back to profile</Link>
        <h1 className="display-heading text-3xl text-white mt-3">SHARE CARD</h1>
        <p className="text-slate-400 text-sm mt-1">Screenshot this card to share on social media</p>
      </div>

      {seasons.length > 0 && (
        <div className="mb-6 flex items-center gap-3">
          <select
            value={selectedSeason}
            onChange={e => setSelectedSeason(e.target.value)}
            className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
          >
            <option value="">Career Statistics</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {statsLoading && <span className="text-slate-500 text-xs">updating…</span>}
        </div>
      )}

      <div className="overflow-x-auto pb-4">
        <ShareCardVisual
          player={player}
          cb={cb}
          cbw={cbw}
          cf={cf}
          season={seasonLabel}
          org={org}
        />
      </div>

      <div className="mt-6 flex gap-3">
        <button onClick={handleShare} className="btn-primary">
          {copied ? 'Copied!' : (typeof navigator !== 'undefined' && navigator.share ? 'Share' : 'Copy Link')}
        </button>
        <p className="text-slate-500 text-xs self-center">
          Take a screenshot of the card above to save as an image
        </p>
      </div>
    </div>
  )
}
