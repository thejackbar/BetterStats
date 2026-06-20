import { useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { orgToPalette } from '../../social/cricket-templates'
import {
  ClubLaunchPoster, LAUNCH_MODULES, LAUNCH_VALUE_PROPS,
} from '../../social/launch-templates'
import { exportNodeToPng } from '../../social/exportImage'

const BASE_URL = import.meta.env.VITE_API_URL || '/api'
const PUBLIC_BASE = 'betterat.cricket'

const fmt = (n) => Number(n || 0).toLocaleString('en-AU')

// Leaderboard names come through as "Last, First"; the poster wants "First Last".
function prettyName(name) {
  if (!name) return ''
  if (name.includes(',')) {
    const [l, f] = name.split(',')
    return `${(f || '').trim()} ${(l || '').trim()}`.trim()
  }
  return name
}

function monogramOf(name) {
  const clean = prettyName(name || '').replace(/[^a-zA-Z ]/g, ' ').trim()
  const parts = clean.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  return clean.slice(0, 2).toUpperCase() || 'CC'
}

const INPUT = 'w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const LABEL = 'block text-[11px] font-mono uppercase tracking-wide2 text-pb-faint mb-1'

export default function SuperAnnounce() {
  const [clubs, setClubs] = useState([])
  const [clubId, setClubId] = useState('')
  const [data, setData] = useState(null)      // { org, summary, players }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Editable copy / picks
  const [headline, setHeadline] = useState('BIG NEWS!')
  const [subhead, setSubhead] = useState(
    'A smarter way to run our club, and a better experience for our players, coaches and supporters.'
  )
  const [featuredId, setFeaturedId] = useState('')
  const [xiText, setXiText] = useState('')
  const [lineupMeta, setLineupMeta] = useState({ title: '1ST XI', round: '', venue: '', time: '' })
  const [footerSlug, setFooterSlug] = useState('')
  const [accent, setAccent] = useState('')
  const [valueProps, setValueProps] = useState(LAUNCH_VALUE_PROPS.map(v => ({ ...v })))

  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const renderRef = useRef(null)
  const previewWrapRef = useRef(null)
  const [scale, setScale] = useState(0.46)

  useEffect(() => {
    api.superListClubs()
      .then((rows) => setClubs(rows || []))
      .catch((e) => setError(e.message || 'Could not load clubs.'))
  }, [])

  // Scale the preview to whatever width the column gives us.
  useEffect(() => {
    const fit = () => {
      const w = previewWrapRef.current?.clientWidth
      if (w) setScale(Math.min(0.6, w / 1080))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [data])

  const loadClub = async (id) => {
    setClubId(id)
    setData(null)
    setError('')
    if (!id) return
    setLoading(true)
    try {
      const [org, summary, players, batting, bowling] = await Promise.all([
        api.getOrg(id),
        api.getOrgSummary(id),
        api.listPlayers(id),
        api.battingLeaderboard(id, { limit: 500, minRuns: 0 }),
        api.bowlingLeaderboard(id, { limit: 500, minWickets: 0 }),
      ])
      // Merge career batting/bowling onto the roster.
      const bat = {}
      for (const r of batting || []) bat[r.player_id] = r
      const bowl = {}
      for (const r of bowling || []) bowl[r.player_id] = r
      // Career leaderboards alias the match count as `games`; per-game branches
      // use `matches`. Take whichever is present.
      const merged = (players || []).map((p) => {
        const b = bat[p.id] || {}
        const w = bowl[p.id] || {}
        return {
          id: p.id,
          name: prettyName(p.display_name || p.name),
          photo: p.photo_url ? `${BASE_URL}/images/players/${p.id}/photo` : null,
          runs: Number(b.total_runs ?? b.runs ?? 0),
          matches: Number(b.games ?? b.matches ?? w.games ?? w.matches ?? 0),
          wickets: Number(w.total_wickets ?? w.wickets ?? 0),
        }
      })
      merged.sort((a, b) => b.runs - a.runs || b.matches - a.matches)

      setData({ org, summary, players: merged })

      // Seed editable defaults from the club.
      const topCapped = [...merged].sort((a, b) => b.matches - a.matches).slice(0, 11)
      setXiText(topCapped.map((p) => p.name).join('\n'))
      const withPhoto = merged.find((p) => p.photo)
      setFeaturedId((withPhoto || merged[0])?.id || '')
      setFooterSlug(org.slug || '')
      setAccent(org.primary_color || '#16c784')
      setHeadline('BIG NEWS!')
      setValueProps(LAUNCH_VALUE_PROPS.map(v => ({ ...v })))
    } catch (e) {
      setError(e.message || 'Could not load club data.')
    } finally {
      setLoading(false)
    }
  }

  // ── Build the poster props ────────────────────────────────────────────────
  const palette = useMemo(() => {
    if (!data) return null
    const p = orgToPalette({ primary_color: accent || data.org.primary_color, accent_color: data.org.accent_color })
    return p
  }, [data, accent])

  const club = data && {
    name: data.org.name || 'Cricket Club',
    slug: data.org.slug || '',
    logo: data.org.logo_url ? `${BASE_URL}/images/organisations/${data.org.id}/logo` : null,
    monogram: monogramOf(data.org.short_name || data.org.name || 'CC'),
  }

  const stats = data && {
    played: fmt(data.summary.total_games),
    runs: fmt(data.summary.total_runs),
    wickets: fmt(data.summary.total_wickets),
    players: fmt(data.summary.total_players),
    winRate: `${Math.round(Number(data.summary.win_rate || 0))}%`,
  }

  const featured = useMemo(() => {
    if (!data) return null
    const p = data.players.find((x) => x.id === featuredId) || data.players[0]
    if (!p) return null
    const lines = []
    if (p.matches > 0) lines.push({ value: fmt(p.matches), label: 'Games' })
    lines.push({ value: fmt(p.runs), label: 'Runs' })
    if (p.wickets > 0) lines.push({ value: fmt(p.wickets), label: 'Wkts' })
    return { name: p.name, photo: p.photo, monogram: monogramOf(p.name), lines }
  }, [data, featuredId])

  const lineup = useMemo(() => {
    const rows = xiText.split('\n').map((s) => s.trim()).filter(Boolean)
    if (!rows.length) return null
    return { ...lineupMeta, rows }
  }, [xiText, lineupMeta])

  const footerUrl = `${PUBLIC_BASE}${footerSlug ? '/' + footerSlug.replace(/^\/+/, '') : ''}`

  const posterProps = data && {
    club, palette, stats, featured, lineup,
    headline, subhead, footerUrl,
    valueProps, modules: LAUNCH_MODULES,
  }

  const handleExport = async () => {
    if (!renderRef.current) return
    setExporting(true)
    setExportError('')
    try {
      await exportNodeToPng(renderRef.current, {
        width: 1080, height: 1080,
        fileName: `bettercricket-launch-${club?.slug || 'club'}-${Date.now()}.png`,
      })
    } catch (e) {
      setExportError(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const fontStyle = { '--social-display-font': "'Anton', sans-serif" }

  return (
    <AdminLayout>
      <div className="max-w-[1400px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Club announcements</h1>
          <p className="text-sm text-pb-dim mt-1">
            Build a "now on Better Cricket" launch poster for a club. Pick a club and it pulls
            their branding, headline stats, a featured player and the XI. Edit anything, then export
            a square image ready for Instagram, Facebook or the group chat.
          </p>
        </div>

        <div className="mb-5 max-w-md">
          <label className={LABEL}>Club</label>
          <select className={INPUT} value={clubId} onChange={(e) => loadClub(e.target.value)}>
            <option value="">Select a club…</option>
            {clubs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}{c.is_active ? '' : ' (hidden)'}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}
        {loading && <p className="text-sm text-pb-dim">Loading club data…</p>}

        {data && posterProps && (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)] gap-6">
            {/* ── Controls ─────────────────────────────────────────────── */}
            <div className="space-y-4">
              <div className="pb-card p-4 space-y-3">
                <div>
                  <label className={LABEL}>Headline</label>
                  <input className={INPUT} value={headline} onChange={(e) => setHeadline(e.target.value)} />
                </div>
                <div>
                  <label className={LABEL}>Sub-headline</label>
                  <textarea className={INPUT} rows={2} value={subhead} onChange={(e) => setSubhead(e.target.value)} />
                </div>
                <div>
                  <label className={LABEL}>Accent colour</label>
                  <div className="flex items-center gap-2">
                    <input type="color" value={accent || '#16c784'} onChange={(e) => setAccent(e.target.value)}
                      className="h-9 w-12 bg-transparent border border-pb-hairline rounded cursor-pointer" />
                    <input className={INPUT} value={accent} onChange={(e) => setAccent(e.target.value)} />
                    <button type="button" onClick={() => setAccent(data.org.primary_color || '#16c784')}
                      className="text-xs text-pb-faint hover:text-pb-text whitespace-nowrap">Reset</button>
                  </div>
                </div>
              </div>

              <div className="pb-card p-4 space-y-3">
                <div>
                  <label className={LABEL}>Featured player</label>
                  <select className={INPUT} value={featuredId} onChange={(e) => setFeaturedId(e.target.value)}>
                    {data.players.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}{p.photo ? ' • photo' : ''} — {fmt(p.matches)} games, {fmt(p.runs)} runs
                      </option>
                    ))}
                  </select>
                  {featured && !featured.photo && (
                    <p className="text-[11px] text-amber-300/80 mt-1">No photo on file — the card shows their initials.</p>
                  )}
                </div>
              </div>

              <div className="pb-card p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={LABEL}>Lineup title</label>
                    <input className={INPUT} value={lineupMeta.title} onChange={(e) => setLineupMeta(m => ({ ...m, title: e.target.value }))} />
                  </div>
                  <div>
                    <label className={LABEL}>Round / note</label>
                    <input className={INPUT} value={lineupMeta.round} onChange={(e) => setLineupMeta(m => ({ ...m, round: e.target.value }))} placeholder="optional" />
                  </div>
                  <div>
                    <label className={LABEL}>Venue</label>
                    <input className={INPUT} value={lineupMeta.venue} onChange={(e) => setLineupMeta(m => ({ ...m, venue: e.target.value }))} placeholder="optional" />
                  </div>
                  <div>
                    <label className={LABEL}>Time</label>
                    <input className={INPUT} value={lineupMeta.time} onChange={(e) => setLineupMeta(m => ({ ...m, time: e.target.value }))} placeholder="optional" />
                  </div>
                </div>
                <div>
                  <label className={LABEL}>XI (one name per line, max 11)</label>
                  <textarea className={`${INPUT} font-mono text-xs`} rows={11} value={xiText} onChange={(e) => setXiText(e.target.value)} />
                  <p className="text-[11px] text-pb-faint mt-1">Pre-filled with the most-capped players. Paste a real team sheet to override.</p>
                </div>
              </div>

              <div className="pb-card p-4 space-y-3">
                <label className={LABEL}>Value props</label>
                {valueProps.map((v, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1.4fr] gap-2">
                    <input className={INPUT} value={v.title} onChange={(e) => setValueProps(vs => vs.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
                    <input className={INPUT} value={v.body} onChange={(e) => setValueProps(vs => vs.map((x, j) => j === i ? { ...x, body: e.target.value } : x))} />
                  </div>
                ))}
              </div>

              <div className="pb-card p-4">
                <label className={LABEL}>Footer link (betterat.cricket/…)</label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-pb-faint">{PUBLIC_BASE}/</span>
                  <input className={INPUT} value={footerSlug} onChange={(e) => setFooterSlug(e.target.value)} placeholder="club-slug" />
                </div>
              </div>
            </div>

            {/* ── Preview + export ─────────────────────────────────────── */}
            <div>
              <div className="sticky top-4">
                <div ref={previewWrapRef} className="rounded-lg overflow-hidden border border-pb-hairline bg-[#080808]" style={{ height: 1080 * scale }}>
                  <div style={{ ...fontStyle, transform: `scale(${scale})`, transformOrigin: 'top left', width: 1080, height: 1080, pointerEvents: 'none' }}>
                    <ClubLaunchPoster {...posterProps} />
                  </div>
                </div>
                <div className="flex items-center gap-3 mt-3">
                  <button onClick={handleExport} disabled={exporting}
                    className="bg-pb-accent text-pb-bg font-semibold text-sm px-5 py-2.5 rounded-lg disabled:opacity-60">
                    {exporting ? 'Rendering…' : 'Download PNG (1080×1080)'}
                  </button>
                  <span className="text-xs text-pb-faint font-mono">1080 × 1080 px</span>
                </div>
                {exportError && <p className="text-sm text-red-400 mt-2">{exportError}</p>}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Hidden full-size render for export */}
      {data && posterProps && (
        <div style={{ position: 'absolute', left: '-9999px', top: 0, pointerEvents: 'none', zIndex: -1 }}>
          <div ref={renderRef} style={{ ...fontStyle, width: 1080, height: 1080 }}>
            <ClubLaunchPoster {...posterProps} />
          </div>
        </div>
      )}
    </AdminLayout>
  )
}
