import { useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import {
  ClubLaunchPoster, LAUNCH_MODULES, LAUNCH_VALUE_PROPS,
} from '../../social/launch-templates'
import { exportNodeToPng } from '../../social/exportImage'
import { resolveAwardLabel } from '../../lib/achievementOptions'

const BASE_URL = import.meta.env.VITE_API_URL || '/api'
const PUBLIC_BASE = 'betterat.cricket'

const fmt = (n) => Number(n || 0).toLocaleString('en-AU')
const fmt2 = (n) => (n == null || n === '' || Number.isNaN(Number(n))) ? '-' : Number(n).toFixed(2)

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

// ── Colour helpers ──────────────────────────────────────────────────────────
function hexToRgb(hex) {
  const h = (hex || '').replace('#', '')
  const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  return { r: parseInt(n.slice(0, 2), 16) || 0, g: parseInt(n.slice(2, 4), 16) || 0, b: parseInt(n.slice(4, 6), 16) || 0 }
}
function rgbToHex(r, g, b) {
  const c = (x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}
// Mix `hex` toward `target` by fraction t (0..1).
function mix(hex, target, t) {
  const a = hexToRgb(hex), b = hexToRgb(target)
  return rgbToHex(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t)
}

// ── Honour-badge formatting (mirrors PlayerProfile) ─────────────────────────
function formatSeasonShort(value, seasons) {
  if (!value) return null
  const match = seasons?.find(s => s.id === value)
  const name = match ? match.name : String(value)
  const m = name.match(/(\d{2})(\d{2})\s*[/_-]\s*(\d{2})/)
  if (m) return `${m[2]}/${m[3]}`
  const single = name.match(/\b(\d{4})\b/)
  if (single) return single[1].slice(2)
  return name
}
function formatRange(a, seasons) {
  const start = formatSeasonShort(a.season, seasons)
  const end = formatSeasonShort(a.season_end, seasons)
  if (start && end && start !== end) return `${start} to ${end}`
  return start || end || null
}
const EXEC_RANK = { 'president': 1, 'vice president': 2, 'vice-president': 2, 'secretary': 3, 'treasurer': 3 }
function badgePriority(a) {
  if (a.category === 'Hall of Fame') return 0
  if (a.category === 'Life Membership') return 1.5
  if (a.category === 'Office Bearer' && a.subcategory === 'Executive Committee') return EXEC_RANK[(a.achievement || '').toLowerCase()] ?? 3
  if (a.category === 'Milestone') {
    if (a.subcategory === 'Cap Number') return 2.5
    if (a.subcategory === 'Games') {
      const n = parseInt((a.achievement || '').match(/(\d+)/)?.[1] || '0', 10)
      if (n >= 500) return 3; if (n >= 300) return 4.5; if (n >= 200) return 5
      return 9
    }
    return 9
  }
  if (a.category === 'Premiership') return 4
  if (a.category === 'Club Award') return 7
  if (a.category === 'Office Bearer') return 8
  return 99
}
function buildBadges(rows, seasons, defs) {
  if (!rows?.length) return []
  const groups = new Map()
  for (const a of rows) {
    const key = `${a.category}|${a.subcategory || ''}|${a.achievement || ''}`
    if (!groups.has(key)) groups.set(key, { ...a, _seasons: [] })
    const s = formatRange(a, seasons)
    if (s) groups.get(key)._seasons.push(s)
  }
  return [...groups.values()].sort((x, y) => badgePriority(x) - badgePriority(y)).slice(0, 6).map(g => {
    const label = resolveAwardLabel(defs, g.category, g.subcategory, g.achievement) || g.subcategory || g.category
    if (g.category === 'Milestone' && g.subcategory === 'Cap Number' && g.detail) return `${label} ${g.detail}`
    const ss = [...new Set(g._seasons)]
    if (ss.length === 0) return label
    if (ss.length === 1) return `${label} (${ss[0]})`
    return `${label} ${ss.join(', ')}`
  })
}

const INPUT = 'w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const LABEL = 'block text-[11px] font-mono uppercase tracking-wide2 text-pb-faint mb-1'

function ColorRow({ label, value, onChange }) {
  return (
    <div>
      <label className={LABEL}>{label}</label>
      <div className="flex items-center gap-2">
        <input type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)}
          className="h-9 w-11 bg-transparent border border-pb-hairline rounded cursor-pointer shrink-0" />
        <input className={INPUT} value={value} onChange={(e) => onChange(e.target.value)} />
      </div>
    </div>
  )
}

export default function SuperAnnounce() {
  const [clubs, setClubs] = useState([])
  const [clubId, setClubId] = useState('')
  const [data, setData] = useState(null)      // { org, summary, players, batting, bowling, seasons, awardDefs }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Editable copy / picks
  const [headline, setHeadline] = useState('BIG NEWS!')
  const [subhead, setSubhead] = useState(
    'A smarter way to run our club. A better experience for our players, coaches, members and supporters.'
  )
  const [featuredId, setFeaturedId] = useState('')
  const [badgesText, setBadgesText] = useState('')
  const [footerSlug, setFooterSlug] = useState('')
  const [valueProps, setValueProps] = useState(LAUNCH_VALUE_PROPS.map(v => ({ ...v })))
  const [showCallout, setShowCallout] = useState(true)

  // Colours
  const [bg, setBg] = useState('#0b0c10')
  const [bg2, setBg2] = useState('#2a0a0c')
  const [accent, setAccent] = useState('#e21f26')
  const [ink, setInk] = useState('#ffffff')

  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const renderRef = useRef(null)
  const previewWrapRef = useRef(null)
  const [scale, setScale] = useState(0.5)

  useEffect(() => {
    api.superListClubs()
      .then((rows) => setClubs(rows || []))
      .catch((e) => setError(e.message || 'Could not load clubs.'))
  }, [])

  useEffect(() => {
    const fit = () => {
      const w = previewWrapRef.current?.clientWidth
      if (w) setScale(Math.min(0.62, w / 1080))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [data])

  const applyClubColours = (org) => {
    const a = org?.primary_color || '#e21f26'
    setAccent(a)
    setBg('#0b0c10')
    setBg2(mix(a, '#000000', 0.8))
    setInk('#ffffff')
  }

  const loadClub = async (id) => {
    setClubId(id)
    setData(null)
    setError('')
    setBadgesText('')
    if (!id) return
    setLoading(true)
    try {
      const [org, summary, players, batting, bowling, seasons, awardDefs] = await Promise.all([
        api.getOrg(id),
        api.getOrgSummary(id),
        api.listPlayers(id),
        api.battingLeaderboard(id, { limit: 500, minRuns: 0 }),
        api.bowlingLeaderboard(id, { limit: 500, minWickets: 0 }),
        api.getOrgSeasons(id).catch(() => []),
        api.listAwardDefinitions(id).catch(() => []),
      ])
      const bat = {}
      for (const r of batting || []) bat[r.player_id] = r
      const bowl = {}
      for (const r of bowling || []) bowl[r.player_id] = r
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

      setData({ org, summary, players: merged, batting: batting || [], bowling: bowling || [], seasons: seasons || [], awardDefs: awardDefs || [] })

      // Seed defaults from the club.
      const withPhoto = merged.find((p) => p.photo)
      setFeaturedId((withPhoto || merged[0])?.id || '')
      setFooterSlug(org.slug || '')
      setHeadline('BIG NEWS!')
      setValueProps(LAUNCH_VALUE_PROPS.map(v => ({ ...v })))
      applyClubColours(org)
    } catch (e) {
      setError(e.message || 'Could not load club data.')
    } finally {
      setLoading(false)
    }
  }

  // Auto-fill the featured player's honours when the pick (or club) changes.
  useEffect(() => {
    if (!data || !featuredId) { setBadgesText(''); return }
    let cancelled = false
    api.listAchievements(data.org.id, { playerId: featuredId })
      .then((rows) => { if (!cancelled) setBadgesText(buildBadges(rows, data.seasons, data.awardDefs).join('\n')) })
      .catch(() => { if (!cancelled) setBadgesText('') })
    return () => { cancelled = true }
  }, [data, featuredId])

  // ── Build the poster props ────────────────────────────────────────────────
  const palette = { bg, bg2, accent, ink }

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
    const badges = badgesText.split('\n').map(s => s.trim()).filter(Boolean)
    return { name: p.name, photo: p.photo, monogram: monogramOf(p.name), lines, badges }
  }, [data, featuredId, badgesText])

  const topBatters = useMemo(() => (data?.batting || []).slice(0, 5).map(r => ({
    name: prettyName(r.name),
    runs: fmt(r.total_runs),
    sub: `AVG ${fmt2(r.average)} · HS ${r.high_score ?? '-'}`,
  })), [data])

  const topBowlers = useMemo(() => (data?.bowling || []).slice(0, 5).map(r => ({
    name: prettyName(r.name),
    wickets: fmt(r.total_wickets),
    sub: `AVG ${fmt2(r.average)} · ECON ${fmt2(r.economy)}`,
  })), [data])

  const footerUrl = `${PUBLIC_BASE}${footerSlug ? '/' + footerSlug.replace(/^\/+/, '') : ''}`

  const posterProps = data && {
    club, palette, stats, featured, topBatters, topBowlers,
    headline, subhead, footerUrl, valueProps, modules: LAUNCH_MODULES, showCallout,
  }

  const handleExport = async () => {
    if (!renderRef.current) return
    setExporting(true)
    setExportError('')
    try {
      await exportNodeToPng(renderRef.current, {
        width: 1080, height: 1080,
        backgroundColor: bg,
        fileName: `bettercricket-launch-${club?.slug || 'club'}-${Date.now()}.png`,
      })
    } catch (e) {
      setExportError(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const fontStyle = { '--social-display-font': "'Anton', sans-serif" }

  const presets = [
    { label: 'Club', apply: () => applyClubColours(data.org) },
    { label: 'Midnight', apply: () => { setBg('#0a0b12'); setBg2('#121a33'); setInk('#ffffff') } },
    { label: 'Charcoal', apply: () => { setBg('#141414'); setBg2('#242424'); setInk('#ffffff') } },
    { label: 'Light', apply: () => { setBg('#f4f4f5'); setBg2('#e6e7ea'); setInk('#14151a') } },
  ]

  return (
    <AdminLayout>
      <div className="max-w-[1400px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Club announcements</h1>
          <p className="text-sm text-pb-dim mt-1">
            Build a "now on BetterCricket" launch poster for a club. Pick a club and it pulls their
            branding, headline stats, a featured player and the top performers. Edit anything, then
            export a square image ready for Instagram, Facebook or the group chat.
          </p>
        </div>

        <div className="mb-5 max-w-md">
          <label className={LABEL}>Club</label>
          <select className={INPUT} value={clubId} onChange={(e) => loadClub(e.target.value)}>
            <option value="">Select a club…</option>
            {clubs.map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.is_active ? '' : ' (hidden)'}</option>
            ))}
          </select>
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}
        {loading && <p className="text-sm text-pb-dim">Loading club data…</p>}

        {data && posterProps && (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,580px)] gap-6">
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
              </div>

              {/* Colours */}
              <div className="pb-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className={LABEL + ' mb-0'}>Colours</span>
                  <div className="flex flex-wrap gap-1.5">
                    {presets.map((p) => (
                      <button key={p.label} type="button" onClick={p.apply}
                        className="text-[11px] px-2 py-1 rounded border border-pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent">
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <ColorRow label="Background" value={bg} onChange={setBg} />
                  <ColorRow label="Background edge" value={bg2} onChange={setBg2} />
                  <ColorRow label="Accent" value={accent} onChange={setAccent} />
                  <ColorRow label="Text" value={ink} onChange={setInk} />
                </div>
              </div>

              {/* Featured player */}
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
                    <p className="text-[11px] text-amber-300/80 mt-1">No photo on file, so the card shows their initials.</p>
                  )}
                </div>
                <div>
                  <label className={LABEL}>Honours / badges (one per line)</label>
                  <textarea className={`${INPUT} font-mono text-xs`} rows={5} value={badgesText} onChange={(e) => setBadgesText(e.target.value)}
                    placeholder="Auto-filled from the player's honours. Edit or clear to show stats instead." />
                  <p className="text-[11px] text-pb-faint mt-1">Leave blank to show Games / Runs / Wickets instead.</p>
                </div>
              </div>

              {/* Value props */}
              <div className="pb-card p-4 space-y-3">
                <label className={LABEL}>Value props</label>
                {valueProps.map((v, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1.4fr] gap-2">
                    <input className={INPUT} value={v.title} onChange={(e) => setValueProps(vs => vs.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
                    <input className={INPUT} value={v.body} onChange={(e) => setValueProps(vs => vs.map((x, j) => j === i ? { ...x, body: e.target.value } : x))} />
                  </div>
                ))}
              </div>

              <div className="pb-card p-4 space-y-3">
                <div>
                  <label className={LABEL}>Footer link (betterat.cricket/…)</label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-pb-faint">{PUBLIC_BASE}/</span>
                    <input className={INPUT} value={footerSlug} onChange={(e) => setFooterSlug(e.target.value)} placeholder="club-slug" />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
                  <input type="checkbox" checked={showCallout} onChange={(e) => setShowCallout(e.target.checked)} />
                  Show "Check out our club page!" callout
                </label>
              </div>
            </div>

            {/* ── Preview + export ─────────────────────────────────────── */}
            <div>
              <div className="sticky top-4">
                <div ref={previewWrapRef} className="rounded-lg overflow-hidden border border-pb-hairline" style={{ height: 1080 * scale, background: bg }}>
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
