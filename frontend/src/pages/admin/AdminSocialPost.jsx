import { useState, useEffect, useRef, useCallback } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { api } from '../../lib/api'
import {
  T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder,
  T5_Brutalist, T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer,
  C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore,
  SC1_Broadcast, SC2_Brutalist, SC3_Dashboard,
  PALETTES, orgToPalette,
} from '../../social/cricket-templates'

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE REGISTRY
// ─────────────────────────────────────────────────────────────────────────────
const TEMPLATES = [
  { id: 'T1', name: 'Hero List',       category: 'Lineup',    component: T1_HeroList,        desc: 'Big player + name list',          maxPlayers: 13 },
  { id: 'T2', name: 'Card Grid',       category: 'Lineup',    component: T2_CardGrid,        desc: '4×3 trading card grid',           maxPlayers: 12 },
  { id: 'T3', name: 'Side Numbered',   category: 'Lineup',    component: T3_SideNumbered,    desc: 'Side photo + numbered XI',        maxPlayers: 11 },
  { id: 'T4', name: 'Batting Order',   category: 'Lineup',    component: T4_BattingOrder,    desc: 'Tactical batting order',          maxPlayers: 13 },
  { id: 'T5', name: 'Brutalist',       category: 'Lineup',    component: T5_Brutalist,       desc: 'Typography-forward XI',           maxPlayers: 11 },
  { id: 'T6', name: 'Diagonal Poster', category: 'Lineup',    component: T6_Diagonal,        desc: 'Diagonal poster, match-day hype', maxPlayers: 11 },
  { id: 'T7', name: 'Milestone',       category: 'Lineup',    component: T7_CaptainSpotlight, desc: 'Milestone achievement showcase',  maxPlayers: 13 },
  { id: 'T8', name: 'Mosaic',          category: 'Lineup',    component: T8_Mosaic,          desc: 'Asymmetric photo mosaic',         maxPlayers: 11 },
  { id: 'T9', name: 'Flyer',           category: 'Lineup',    component: T9_Flyer,           desc: 'Festival poster style',           maxPlayers: 11 },
  { id: 'C1', name: 'Announcement',    category: 'Companion', component: C1_CaptainAnnounce, desc: 'Captain / debut / award announcement', maxPlayers: 1 },
  { id: 'C2', name: 'Toss',            category: 'Companion', component: C2_TossWon,         desc: 'Toss result post',                maxPlayers: 0 },
  { id: 'C3', name: 'Player Spotlight',category: 'Companion', component: C3_ManOfMatch,      desc: 'Man of match / player stats',     maxPlayers: 1 },
  { id: 'C4', name: 'Match Result',    category: 'Companion', component: C4_FinalScore,      desc: 'Full time result + top performers', maxPlayers: 0 },
  { id: 'SC1', name: 'Broadcast',      category: 'Scorecard', component: SC1_Broadcast,      desc: 'TV-style full scorecard, dark/light', maxPlayers: 0, isScorecard: true },
  { id: 'SC2', name: 'Brutalist',      category: 'Scorecard', component: SC2_Brutalist,      desc: 'Bold type, heavy rules', maxPlayers: 0, isScorecard: true },
  { id: 'SC3', name: 'Dashboard',      category: 'Scorecard', component: SC3_Dashboard,      desc: 'Soft cards, app-style', maxPlayers: 0, isScorecard: true },
]

const DEFAULT_BATTING_ROW = (num) => ({ num, first: '', last: `PLAYER ${num}`, r: 0, b: 0, fours: 0, sixes: 0, sr: 0, out: 'not out', notOut: false, didNotBat: false, role: null })
const DEFAULT_BOWLING_ROW = (i) => ({ first: '', last: `BOWLER ${i + 1}`, o: 0, m: 0, r: 0, w: 0, econ: 0 })
const DEFAULT_TEAM = (name, short, color) => ({
  name, short, color, monogram: short,
  total: '0', overs: '0.0', wickets: 0, runRate: '0.00',
  batting: Array.from({ length: 11 }, (_, i) => DEFAULT_BATTING_ROW(i + 1)),
  bowling: Array.from({ length: 6 }, (_, i) => DEFAULT_BOWLING_ROW(i)),
  extras: { total: 0, b: 0, lb: 0, nb: 0, wd: 0 },
})
const DEFAULT_SCORECARD = {
  meta: {
    competition: 'COMPETITION', round: 'ROUND 1', format: 'T20', overs: 20,
    venue: 'HOME GROUND', date: 'SAT 1 JAN',
    toss: 'HOME WON THE TOSS · ELECTED TO BAT',
    result: 'HOME WON BY 6 WICKETS',
    series: 'SEASON 2025/26',
    motm: { first: 'Player', last: 'NAME', team: 'HOME', line: '87 (54) · 2/22' },
    sponsors: [{ url: null, name: '' }, { url: null, name: '' }],
  },
  home: { ...DEFAULT_TEAM('HOME TEAM', 'HOM', '#1a4eb8'), headerInk: '#0a0a0a' },
  away: { ...DEFAULT_TEAM('AWAY TEAM', 'AWY', '#cc1f2c'), headerInk: '#0a0a0a' },
}

const BASE_URL = import.meta.env.VITE_API_URL || '/api'

function splitName(displayName, nameFormat = 'last_first') {
  const parts = (displayName || '').trim().split(/\s+/)
  if (parts.length === 1) return { first: '', last: parts[0].toUpperCase() }
  if (nameFormat === 'first_last') {
    // "Shaylyn Wijesinghe" → first="Shaylyn", last="WIJESINGHE"
    return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1].toUpperCase() }
  }
  // default: last_first → "Wijesinghe Shaylyn" → first="Shaylyn", last="WIJESINGHE"
  return { first: parts.slice(1).join(' '), last: parts[0].toUpperCase() }
}

function deriveShort(name) {
  return name.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 3)
}

function playerToTemplatePlayer(p, { captain = false, viceCaptain = false, keeper = false, role = 'BAT' } = {}, nameFormat = 'last_first', swap = false) {
  const raw = splitName(p.display_name || p.name, nameFormat)
  const first = swap ? raw.last : raw.first
  const last  = swap ? raw.first.toUpperCase() : raw.last
  return {
    first,
    last,
    role,
    roleLong: { BAT: 'Batter', BOWL: 'Bowler', AR: 'All-Rounder', WK: 'Wicket-Keeper' }[role] || role,
    captain,
    viceCaptain,
    keeper,
    headshot: p.photo_url ? `${BASE_URL}/images/players/${p.id}/photo` : null,
    _id: p.id,
    _name: p.display_name || p.name,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// COLOUR SWATCH
// ─────────────────────────────────────────────────────────────────────────────
function PaletteSwatch({ pal, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      title={pal.name}
      style={{ background: pal.primary, border: `2px solid ${selected ? pal.accent : 'transparent'}`, borderRadius: 6, width: 44, height: 44, cursor: 'pointer', position: 'relative', overflow: 'hidden' }}
    >
      <span style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 12, background: pal.accent }} />
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PLAYER ROW in selector
// ─────────────────────────────────────────────────────────────────────────────
function SelectedPlayerRow({ sp, idx, onUpdate, onRemove, onMoveUp, onMoveDown, isFirst, isLast }) {
  const { player, role, captain, viceCaptain, keeper } = sp
  return (
    <div className="flex items-center gap-2 p-2 rounded bg-pb-surface border pb-hairline">
      <div className="flex flex-col gap-0.5 mr-1">
        <button onClick={onMoveUp} disabled={isFirst} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-xs leading-none">▲</button>
        <button onClick={onMoveDown} disabled={isLast} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-xs leading-none">▼</button>
      </div>
      <span className="font-mono text-[10px] text-pb-faintest w-4 shrink-0">{idx + 1}</span>
      <span className="text-sm text-pb-text flex-1 truncate">{player.display_name || player.name}</span>
      <select
        value={role}
        onChange={e => onUpdate({ role: e.target.value })}
        className="font-mono text-[10px] bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-pb-text"
      >
        {['BAT', 'BOWL', 'AR', 'WK'].map(r => <option key={r} value={r}>{r}</option>)}
      </select>
      {['captain', 'viceCaptain', 'keeper'].map(field => {
        const labels = { captain: 'C', viceCaptain: 'VC', keeper: 'WK' }
        const active = sp[field]
        return (
          <button
            key={field}
            onClick={() => onUpdate({ [field]: !active })}
            style={active ? { background: 'var(--pb-accent)', color: 'var(--pb-bg)' } : {}}
            className={`font-mono text-[10px] px-1.5 py-0.5 rounded border pb-hairline transition-colors ${active ? '' : 'text-pb-faint hover:text-pb-text'}`}
          >
            {labels[field]}
          </button>
        )
      })}
      <button onClick={onRemove} className="text-pb-faintest hover:text-red-400 text-xs ml-1">✕</button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STAT ROW for C3
// ─────────────────────────────────────────────────────────────────────────────
function StatRow({ stat, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-center">
      <input
        value={stat.label}
        onChange={e => onChange({ ...stat, label: e.target.value })}
        placeholder="Label (e.g. Runs)"
        className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono"
      />
      <input
        value={stat.value}
        onChange={e => onChange({ ...stat, value: e.target.value })}
        placeholder="Value (e.g. 87)"
        className="w-24 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono"
      />
      <button onClick={onRemove} className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PERFORMER ROW for C4 top performers
// ─────────────────────────────────────────────────────────────────────────────
function PerformerRow({ p, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-center">
      <input
        value={p.last}
        onChange={e => onChange({ ...p, last: e.target.value })}
        placeholder="Name"
        className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest"
      />
      <input
        value={p.line}
        onChange={e => onChange({ ...p, line: e.target.value })}
        placeholder="e.g. 87 (54) or 3-22 (4)"
        className="w-36 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono"
      />
      <button onClick={onRemove} className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FIELD HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div>
      <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">{label}</label>
      {children}
    </div>
  )
}
function TextInput({ value, onChange, placeholder }) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest"
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export default function AdminSocialPost() {
  const [settings, setSettings] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)

  // Template state
  const [templateId, setTemplateId] = useState('T1')

  // Match state
  const [match, setMatch] = useState({ competition: '', round: '', venue: '', date: '', time: '', season: '' })
  const patchMatch = patch => setMatch(m => ({ ...m, ...patch }))

  // Opponent state
  const [opponent, setOpponent] = useState({ name: '', short: '', monogram: '', logo: null })
  const patchOpp = patch => setOpponent(o => ({ ...o, ...patch }))
  const [oppSearch, setOppSearch] = useState('')
  const [oppResults, setOppResults] = useState([])
  const [oppSearching, setOppSearching] = useState(false)
  const oppSearchTimeout = useRef(null)

  // Player selection
  const [selectedPlayers, setSelectedPlayers] = useState([])
  const [playerSearch, setPlayerSearch] = useState('')

  // Palette
  const [paletteKey, setPaletteKey] = useState('club')
  const [customBg, setCustomBg] = useState('#243352')
  const [customAccent, setCustomAccent] = useState('#16c784')
  const [savedPalettes, setSavedPalettes] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_palettes') || '[]') } catch { return [] }
  })
  const [savePaletteName, setSavePaletteName] = useState('')

  // Hero image
  const [heroImage, setHeroImage] = useState({ blobUrl: null, playerIdx: 0 })

  // Name display swap
  const [swapNames, setSwapNames] = useState(false)

  // Scorecard match data (for SC1/SC2/SC3)
  const [scorecardMatch, setScorecardMatch] = useState(DEFAULT_SCORECARD)
  const [scUrlInput, setScUrlInput] = useState('')
  const [scUrlStatus, setScUrlStatus] = useState(null) // null | 'loading' | 'ok' | string(error)

  const [removingBg, setRemovingBg] = useState(null) // 'hero' | 'sponsor-0' | 'sponsor-1' | null

  const handleRemoveBg = useCallback(async (key, srcUrl, onSuccess) => {
    setRemovingBg(key)
    try {
      const { removeBackground } = await import('@imgly/background-removal')
      const blob = await removeBackground(srcUrl, { debug: false })
      const newUrl = URL.createObjectURL(blob)
      onSuccess(newUrl)
    } catch (e) {
      console.error('Background removal failed:', e)
    } finally {
      setRemovingBg(null)
    }
  }, [])

  const [sponsorFiles, setSponsorFiles] = useState([null, null])
  const handleSponsorFile = (idx, file) => {
    if (!file) return
    const url = URL.createObjectURL(file)
    setSponsorFiles(prev => { const next = [...prev]; next[idx] = url; return next })
    setScorecardMatch(m => ({
      ...m,
      meta: {
        ...m.meta,
        sponsors: m.meta.sponsors.map((s, i) => i === idx ? { url, name: file.name.replace(/\.[^.]+$/, '') } : s),
      },
    }))
  }

  const handleScUrlImport = async () => {
    const urlOrId = scUrlInput.trim()
    const uuidRe = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    const match = urlOrId.match(uuidRe)
    if (!match) { setScUrlStatus('Paste a play.cricket.com.au match URL or a match UUID'); return }
    const matchId = match[0]
    setScUrlStatus('loading')
    try {
      const data = await api.getSocialScorecard(matchId)
      setScorecardMatch(prev => ({
        ...data,
        meta: { ...data.meta, sponsors: prev.meta.sponsors },
        home: { ...data.home, headerInk: prev.home?.headerInk || '#0a0a0a' },
        away: { ...data.away, headerInk: prev.away?.headerInk || '#0a0a0a' },
      }))
      setScUrlStatus('ok')
    } catch (e) {
      setScUrlStatus(e?.message || 'Failed to load scorecard')
    }
  }

  const patchScMeta = patch => setScorecardMatch(m => ({ ...m, meta: { ...m.meta, ...patch } }))
  const patchScTeam = (side, patch) => setScorecardMatch(m => ({ ...m, [side]: { ...m[side], ...patch } }))

  // Per-side scorecard team search — same CA API as the opponent search
  const [scTeamSearch, setScTeamSearch] = useState({ home: '', away: '' })
  const [scTeamResults, setScTeamResults] = useState({ home: [], away: [] })
  const [scTeamSearching, setScTeamSearching] = useState({ home: false, away: false })
  const scTeamSearchTimeout = useRef({ home: null, away: null })

  const handleScTeamSearch = useCallback(async (side, q) => {
    setScTeamSearch(s => ({ ...s, [side]: q }))
    clearTimeout(scTeamSearchTimeout.current[side])
    if (!q.trim()) { setScTeamResults(r => ({ ...r, [side]: [] })); return }
    scTeamSearchTimeout.current[side] = setTimeout(async () => {
      setScTeamSearching(s => ({ ...s, [side]: true }))
      try {
        const results = await api.searchOrgs(q)
        setScTeamResults(r => ({ ...r, [side]: results || [] }))
      } catch { setScTeamResults(r => ({ ...r, [side]: [] })) }
      finally { setScTeamSearching(s => ({ ...s, [side]: false })) }
    }, 350)
  }, [])

  const selectScTeam = useCallback(async (side, org) => {
    let logoUrl = org.logoURL || org.logo_url || null
    try {
      const bsOrgs = await api.listOrgs()
      const matched = bsOrgs.find(o => o.name?.toLowerCase() === org.name?.toLowerCase() || o.id === org.id)
      if (matched?.id) logoUrl = `${BASE_URL}/images/organisations/${matched.id}/logo`
    } catch { /* fall back to CA logo */ }
    const name = (org.name || org.shortName || '').toUpperCase()
    const short = (org.shortName || deriveShort(name || 'OPP')).toUpperCase().slice(0, 4)
    patchScTeam(side, { name, short, monogram: short.slice(0, 3), logo: logoUrl })
    setScTeamSearch(s => ({ ...s, [side]: '' }))
    setScTeamResults(r => ({ ...r, [side]: [] }))
  }, [])
  const patchScExtras = (side, patch) => setScorecardMatch(m => ({ ...m, [side]: { ...m[side], extras: { ...m[side].extras, ...patch } } }))
  const updateBatRow = (side, idx, patch) => setScorecardMatch(m => {
    const batting = [...m[side].batting]
    batting[idx] = { ...batting[idx], ...patch }
    if (patch.r !== undefined || patch.b !== undefined) {
      const row = { ...batting[idx], ...patch }
      batting[idx] = { ...row, sr: row.b > 0 ? +((row.r / row.b) * 100).toFixed(2) : 0 }
    }
    return { ...m, [side]: { ...m[side], batting } }
  })
  const updateBowlRow = (side, idx, patch) => setScorecardMatch(m => {
    const bowling = [...m[side].bowling]
    bowling[idx] = { ...bowling[idx], ...patch }
    const row = bowling[idx]
    bowling[idx] = { ...row, econ: row.o > 0 ? +((row.r / row.o)).toFixed(2) : 0 }
    return { ...m, [side]: { ...m[side], bowling } }
  })

  // Template-specific extras
  const [milestone, setMilestone] = useState({ value: '', unit: 'GAMES', reason: '', detail: '', playerIdx: 0 })
  const [announcement, setAnnouncement] = useState({ kind: 'APPOINTMENT', headline: 'NAMED CAPTAIN', subheadline: 'FOR THE 2025-26 SEASON', playerIdx: 0 })
  const [toss, setToss] = useState({ winner: 'TEAM', decision: 'BAT' })
  const [motm, setMotm] = useState({ playerIdx: 0, stats: [{ label: 'Runs', value: '' }, { label: 'SR', value: '' }], summary: '' })
  const [result, setResult] = useState({
    winner: 'TEAM', margin: '', teamScore: '', oppScore: '', motmLast: '',
    topBatters: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
    topBowlers: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
  })

  const renderRef = useRef(null)

  useEffect(() => {
    Promise.all([api.adminGetSettings(), api.adminListPlayers()])
      .then(([s, p]) => { setSettings(s); setAllPlayers(p) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Derive team object from settings
  const team = settings ? {
    name: (settings.name || 'CLUB').toUpperCase(),
    fullName: settings.name || 'Club',
    short: deriveShort(settings.name || 'Club'),
    monogram: deriveShort(settings.name || 'Club').slice(0, 2),
    logo: settings.logo_url ? `${BASE_URL}/images/organisations/${settings.id}/logo` : null,
  } : { name: 'CLUB', fullName: 'Club', short: 'CLB', monogram: 'CL', logo: null }

  // Derive opponent object
  const oppData = {
    name: opponent.name.toUpperCase() || 'OPPONENT',
    fullName: opponent.name || 'Opponent',
    short: opponent.short || deriveShort(opponent.name || 'OPP'),
    monogram: opponent.monogram || deriveShort(opponent.name || 'OPP').slice(0, 2),
    logo: opponent.logo || null,
  }

  // Derive palette
  const activePalette = paletteKey === 'club'
    ? orgToPalette(settings)
    : paletteKey === 'custom'
      ? { name: 'Custom', primary: customBg, secondary: customBg + 'cc', accent: customAccent, ink: '#ffffff' }
      : (savedPalettes.find(p => p.key === paletteKey) || PALETTES[paletteKey])

  // Name format from club settings (last_first = "Smith John", first_last = "John Smith")
  const nameFormat = settings?.player_name_format || 'last_first'

  // Current template definition
  const tmpl = TEMPLATES.find(t => t.id === templateId) || TEMPLATES[0]
  const isScorecard = !!(tmpl.isScorecard)
  const TemplateComponent = tmpl.component

  // Detect if palette is dark (for scorecard dark mode)
  const hexToLuminance = (hex) => {
    const r = parseInt(hex.slice(1, 3), 16) / 255
    const g = parseInt(hex.slice(3, 5), 16) / 255
    const b = parseInt(hex.slice(5, 7), 16) / 255
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const palettePrimary = activePalette?.primary || '#0a0a0a'
  const isDarkPalette = palettePrimary.startsWith('#') ? hexToLuminance(palettePrimary) < 0.4 : true

  // Build template-specific extra props
  const extraProps = {}
  if (templateId === 'T7') {
    const milestonePlayer = selectedPlayers[milestone.playerIdx]
    extraProps.milestone = {
      value: milestone.value || '200',
      unit: milestone.unit || 'GAMES',
      reason: milestone.reason || 'MILESTONE',
      detail: milestone.detail,
      player: milestonePlayer ? playerToTemplatePlayer(milestonePlayer.player, milestonePlayer, nameFormat, swapNames) : undefined,
    }
  }
  if (templateId === 'C1') {
    const annPlayer = selectedPlayers[announcement.playerIdx]
    extraProps.announcement = {
      kind: announcement.kind,
      headline: announcement.headline,
      subheadline: announcement.subheadline,
      player: annPlayer ? playerToTemplatePlayer(annPlayer.player, annPlayer, nameFormat, swapNames) : undefined,
    }
  }
  if (templateId === 'C2') {
    extraProps.toss = { winner: toss.winner, decision: toss.decision }
  }
  if (templateId === 'C3') {
    const motmPlayer = selectedPlayers[motm.playerIdx]
    extraProps.motm = {
      player: motmPlayer ? playerToTemplatePlayer(motmPlayer.player, motmPlayer, nameFormat, swapNames) : undefined,
      stats: motm.stats.filter(s => s.label && s.value),
      summary: motm.summary,
    }
  }
  if (templateId === 'C4') {
    extraProps.result = {
      winner: result.winner,
      margin: result.margin,
      teamScore: result.teamScore,
      oppScore: result.oppScore,
      motmLast: result.motmLast,
      topBatters: result.topBatters,
      topBowlers: result.topBowlers,
    }
  }
  if (isScorecard) {
    extraProps.match = scorecardMatch
  }

  // Build players array for template
  const templatePlayers = selectedPlayers.map((sp, i) => {
    const base = playerToTemplatePlayer(sp.player, sp, nameFormat, swapNames)
    if (heroImage.blobUrl && i === heroImage.playerIdx) base.headshot = heroImage.blobUrl
    return base
  })

  // Player management
  const addPlayer = useCallback(p => {
    if (selectedPlayers.find(sp => sp.player.id === p.id)) return
    const role = p.player_role && ['BAT','BOWL','AR','WK'].includes(p.player_role) ? p.player_role : 'BAT'
    setSelectedPlayers(prev => [...prev, { player: p, role, captain: false, viceCaptain: false, keeper: false }])
  }, [selectedPlayers])

  const removePlayer = useCallback(idx => {
    setSelectedPlayers(prev => prev.filter((_, i) => i !== idx))
  }, [])

  const updatePlayer = useCallback((idx, patch) => {
    setSelectedPlayers(prev => {
      const next = [...prev]
      // Ensure only one captain, viceCaptain, keeper
      if (patch.captain && patch.captain === true) next.forEach((p, i) => { if (i !== idx) p.captain = false })
      if (patch.viceCaptain && patch.viceCaptain === true) next.forEach((p, i) => { if (i !== idx) p.viceCaptain = false })
      if (patch.keeper && patch.keeper === true) next.forEach((p, i) => { if (i !== idx) p.keeper = false })
      next[idx] = { ...next[idx], ...patch }
      return next
    })
  }, [])

  const movePlayer = useCallback((idx, dir) => {
    setSelectedPlayers(prev => {
      const next = [...prev]
      const swap = idx + dir
      if (swap < 0 || swap >= next.length) return prev
      ;[next[idx], next[swap]] = [next[swap], next[idx]]
      return next
    })
  }, [])

  // Opponent search with debounce
  const handleOppSearch = useCallback(async (q) => {
    setOppSearch(q)
    clearTimeout(oppSearchTimeout.current)
    if (!q.trim()) { setOppResults([]); return }
    oppSearchTimeout.current = setTimeout(async () => {
      setOppSearching(true)
      try {
        const results = await api.searchOrgs(q)
        setOppResults(results || [])
      } catch { setOppResults([]) }
      finally { setOppSearching(false) }
    }, 350)
  }, [])

  const selectOpponent = useCallback(async (org) => {
    // Start with the PlayHQ Cloudinary logo (returned by search endpoint)
    let logoUrl = org.logoURL || org.logo_url || null
    // If this org is also a BetterStats club, prefer our stored logo
    try {
      const bsOrgs = await api.listOrgs()
      const matched = bsOrgs.find(o => o.name?.toLowerCase() === org.name?.toLowerCase() || o.id === org.id)
      if (matched?.id) logoUrl = `${BASE_URL}/images/organisations/${matched.id}/logo`
    } catch { /* ignore — fall back to Cloudinary URL */ }
    patchOpp({
      name: org.name || org.shortName || '',
      short: org.shortName || deriveShort(org.name || 'OPP'),
      logo: logoUrl,
    })
    setOppSearch('')
    setOppResults([])
  }, [])

  // Hero image file selection
  const handleHeroFile = useCallback((e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (heroImage.blobUrl) URL.revokeObjectURL(heroImage.blobUrl)
    setHeroImage(h => ({ ...h, blobUrl: URL.createObjectURL(file) }))
  }, [heroImage.blobUrl])

  // Export to PNG via html2canvas
  const handleExport = async () => {
    if (!renderRef.current) return
    setExporting(true)
    setExportError(null)
    try {
      await document.fonts.ready
      const html2canvas = (await import('html2canvas')).default
      const el = renderRef.current
      const wrapper = el.parentElement
      const W = tmpl.isScorecard ? 1920 : 1080
      const H = 1080
      // Temporarily position in viewport (opacity ~0) so html2canvas captures the full element
      const prevStyle = wrapper.getAttribute('style') || ''
      wrapper.setAttribute('style', 'position:fixed;left:0;top:0;z-index:-1;opacity:0.001;pointer-events:none;overflow:hidden')
      await new Promise(r => requestAnimationFrame(r))
      await new Promise(r => requestAnimationFrame(r))
      const canvas = await html2canvas(el, {
        scale: 1,
        useCORS: true,
        allowTaint: false,
        backgroundColor: null,
        logging: false,
        width: W,
        height: H,
        windowWidth: W,
        windowHeight: H,
      })
      wrapper.setAttribute('style', prevStyle)
      canvas.toBlob(blob => {
        if (!blob) { setExportError('Could not generate image'); return }
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `betterstats-${templateId.toLowerCase()}-${Date.now()}.png`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 'image/png')
    } catch (e) {
      setExportError(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const filteredPlayers = allPlayers.filter(p => {
    if (!playerSearch) return true
    const q = playerSearch.toLowerCase()
    return (p.display_name || p.name || '').toLowerCase().includes(q)
  })

  if (loading) return (
    <AdminLayout>
      <div className="flex items-center justify-center h-64">
        <span className="font-mono text-[11px] text-pb-faint animate-pulse">LOADING...</span>
      </div>
    </AdminLayout>
  )

  const matchData = {
    competition: match.competition || 'COMPETITION',
    round: match.round || 'ROUND 1',
    venue: match.venue || 'HOME GROUND',
    date: match.date || 'SAT 1 JAN',
    time: match.time || '1:00 PM',
    season: match.season || '2025–26',
  }

  return (
    <AdminLayout>
      <div className="max-w-full">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Create Social Post</h1>
        <p className="text-pb-faint text-sm mb-6">Design and export 1080×1080 social media graphics using your club's branding.</p>

        <div className="flex gap-6 items-start flex-wrap xl:flex-nowrap">
          {/* ── LEFT PANEL: form ──────────────────────────────── */}
          <div className="flex flex-col gap-5 w-full xl:w-[520px] shrink-0">

            {/* Template picker */}
            <section className="pb-card p-4">
              <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Template</h2>
              {['Lineup', 'Companion', 'Scorecard'].map(cat => (
                <div key={cat} className="mb-3">
                  <p className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase mb-2">{cat}</p>
                  <div className="grid grid-cols-3 gap-2">
                    {TEMPLATES.filter(t => t.category === cat).map(t => (
                      <button
                        key={t.id}
                        onClick={() => setTemplateId(t.id)}
                        className={`text-left p-2.5 rounded border transition-colors ${templateId === t.id ? 'border-pb-accent bg-pb-surface2' : 'border-transparent bg-pb-surface hover:bg-pb-surface2'}`}
                        style={templateId === t.id ? { borderColor: 'var(--pb-accent)' } : {}}
                      >
                        <div className="font-mono text-[9px] text-pb-faintest mb-0.5">{t.id}</div>
                        <div className="font-medium text-pb-text text-xs leading-tight">{t.name}</div>
                        <div className="text-[10px] text-pb-faint leading-tight mt-0.5">{t.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </section>

            {/* Colour palette */}
            <section className="pb-card p-4">
              <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Colour Palette</h2>
              <div className="flex gap-2 flex-wrap items-center mb-2">
                <button
                  onClick={() => setPaletteKey('club')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-mono transition-colors ${paletteKey === 'club' ? 'text-pb-text' : 'text-pb-faint hover:text-pb-text border-transparent'}`}
                  style={paletteKey === 'club' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                >
                  <span style={{ width: 14, height: 14, borderRadius: 3, background: settings?.primary_color || '#16c784', display: 'inline-block' }} />
                  Club Colors
                </button>
                {Object.entries(PALETTES).map(([key, pal]) => (
                  <PaletteSwatch key={key} pal={pal} selected={paletteKey === key} onClick={() => setPaletteKey(key)} />
                ))}
                <button
                  onClick={() => setPaletteKey('custom')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-mono transition-colors ${paletteKey === 'custom' ? 'text-pb-text' : 'text-pb-faint hover:text-pb-text border-transparent'}`}
                  style={paletteKey === 'custom' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                >
                  Custom
                </button>
              </div>
              {/* Saved custom palettes */}
              {savedPalettes.length > 0 && (
                <div className="flex gap-2 flex-wrap items-center mt-2 pt-2 border-t pb-hairline">
                  <span className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">Saved</span>
                  {savedPalettes.map(p => (
                    <div key={p.key} className="flex items-center gap-1">
                      <PaletteSwatch pal={p} selected={paletteKey === p.key} onClick={() => setPaletteKey(p.key)} />
                      <button
                        onClick={() => {
                          const next = savedPalettes.filter(x => x.key !== p.key)
                          setSavedPalettes(next)
                          localStorage.setItem('bs_social_palettes', JSON.stringify(next))
                          if (paletteKey === p.key) setPaletteKey('club')
                        }}
                        className="text-pb-faintest hover:text-red-400 text-[10px] leading-none"
                        title="Delete palette"
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
              {paletteKey === 'custom' && (
                <div className="mt-2 flex flex-col gap-2">
                  <div className="flex gap-4 items-center">
                    <label className="flex items-center gap-2 text-xs text-pb-faint font-mono">
                      <input type="color" value={customBg} onChange={e => setCustomBg(e.target.value)}
                        className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent p-0" />
                      Background
                    </label>
                    <label className="flex items-center gap-2 text-xs text-pb-faint font-mono">
                      <input type="color" value={customAccent} onChange={e => setCustomAccent(e.target.value)}
                        className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent p-0" />
                      Accent
                    </label>
                  </div>
                  <div className="flex gap-2 items-center">
                    <input
                      value={savePaletteName}
                      onChange={e => setSavePaletteName(e.target.value)}
                      placeholder="Palette name..."
                      className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-xs text-pb-text placeholder:text-pb-faintest font-mono"
                    />
                    <button
                      onClick={() => {
                        const name = savePaletteName.trim() || `Custom ${savedPalettes.length + 1}`
                        const key = `saved_${Date.now()}`
                        const pal = { key, name, primary: customBg, secondary: customBg + 'cc', accent: customAccent, ink: '#ffffff' }
                        const next = [...savedPalettes, pal]
                        setSavedPalettes(next)
                        localStorage.setItem('bs_social_palettes', JSON.stringify(next))
                        setSavePaletteName('')
                        setPaletteKey(key)
                      }}
                      className="px-3 py-1 rounded text-xs font-mono text-pb-text border pb-hairline hover:bg-pb-surface2 transition-colors whitespace-nowrap"
                    >
                      Save palette
                    </button>
                  </div>
                </div>
              )}
            </section>

            {/* Match info */}
            <section className="pb-card p-4">
              <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Match Info</h2>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Competition"><TextInput value={match.competition} onChange={v => patchMatch({ competition: v })} placeholder="PREMIER T20" /></Field>
                <Field label="Round"><TextInput value={match.round} onChange={v => patchMatch({ round: v })} placeholder="ROUND 7" /></Field>
                <Field label="Venue"><TextInput value={match.venue} onChange={v => patchMatch({ venue: v })} placeholder="Heathcote Reserve" /></Field>
                <Field label="Date"><TextInput value={match.date} onChange={v => patchMatch({ date: v })} placeholder="SAT 30 MAY" /></Field>
                <Field label="Time"><TextInput value={match.time} onChange={v => patchMatch({ time: v })} placeholder="2:30 PM" /></Field>
                <Field label="Season"><TextInput value={match.season} onChange={v => patchMatch({ season: v })} placeholder="2025–26" /></Field>
              </div>
            </section>

            {/* Opponent */}
            <section className="pb-card p-4">
              <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Opponent</h2>
              {/* Club search */}
              <div className="relative mb-3">
                <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">Search Club</label>
                <div className="relative">
                  <input
                    value={oppSearch}
                    onChange={e => handleOppSearch(e.target.value)}
                    placeholder="Type club name to search..."
                    className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest"
                  />
                  {oppSearching && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[9px] text-pb-faintest animate-pulse">SEARCHING...</span>
                  )}
                </div>
                {oppResults.length > 0 && (
                  <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-pb-surface border pb-hairline rounded shadow-lg max-h-48 overflow-y-auto">
                    {oppResults.map((org, i) => (
                      <button
                        key={org.id || i}
                        onClick={() => selectOpponent(org)}
                        className="w-full text-left px-3 py-2 hover:bg-pb-surface2 flex items-center gap-2 border-b pb-hairline last:border-0"
                      >
                        {(org.logoURL || org.logo_url) && (
                          <img src={org.logoURL || org.logo_url} alt="" className="w-7 h-7 rounded object-contain bg-pb-surface2 shrink-0" />
                        )}
                        <span className="text-sm text-pb-text flex-1 truncate">{org.name}</span>
                        {org.shortName && <span className="font-mono text-[9px] text-pb-faintest">{org.shortName}</span>}
                        {org.suburb && <span className="font-mono text-[9px] text-pb-faintest hidden sm:block">{org.suburb}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Club Name"><TextInput value={opponent.name} onChange={v => patchOpp({ name: v })} placeholder="Subiaco CC" /></Field>
                <Field label="Short Code"><TextInput value={opponent.short} onChange={v => patchOpp({ short: v })} placeholder="SUB" /></Field>
                {opponent.logo && (
                  <div className="col-span-2 flex items-center gap-2">
                    <img src={opponent.logo} alt="" className="w-8 h-8 rounded object-contain bg-pb-surface2" onError={e => e.target.style.display='none'} />
                    <span className="text-[10px] text-pb-faint font-mono truncate flex-1">{opponent.logo}</span>
                    <button onClick={() => patchOpp({ logo: null })} className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
                  </div>
                )}
              </div>
            </section>

            {/* Players */}
            {tmpl.maxPlayers > 0 && (
              <section className="pb-card p-4">
                <div className="flex items-center justify-between mb-1">
                  <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
                    Players
                    <span className="ml-2 text-pb-faintest">{selectedPlayers.length}/{tmpl.maxPlayers}</span>
                  </h2>
                  <button
                    onClick={() => setSwapNames(s => !s)}
                    title="Toggle which word is treated as the surname"
                    className={`font-mono text-[9px] tracking-wide2 px-2 py-1 rounded border pb-hairline transition-colors ${swapNames ? 'text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}
                    style={swapNames ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                  >
                    ↕ SWAP NAMES
                  </button>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">Select up to {tmpl.maxPlayers} players. Assign C / VC / WK as needed.</p>

                {selectedPlayers.length > 0 && (
                  <div className="flex flex-col gap-1.5 mb-3">
                    {selectedPlayers.map((sp, idx) => (
                      <SelectedPlayerRow
                        key={sp.player.id}
                        sp={sp}
                        idx={idx}
                        isFirst={idx === 0}
                        isLast={idx === selectedPlayers.length - 1}
                        onUpdate={patch => updatePlayer(idx, patch)}
                        onRemove={() => removePlayer(idx)}
                        onMoveUp={() => movePlayer(idx, -1)}
                        onMoveDown={() => movePlayer(idx, 1)}
                      />
                    ))}
                  </div>
                )}

                {selectedPlayers.length < tmpl.maxPlayers && (
                  <>
                    <input
                      value={playerSearch}
                      onChange={e => setPlayerSearch(e.target.value)}
                      placeholder="Search players to add..."
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest mb-2"
                    />
                    <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5">
                      {filteredPlayers.filter(p => !selectedPlayers.find(sp => sp.player.id === p.id)).map(p => (
                        <button
                          key={p.id}
                          onClick={() => addPlayer(p)}
                          className="text-left px-3 py-1.5 rounded hover:bg-pb-surface2 text-sm text-pb-text flex items-center gap-2 group"
                        >
                          {p.photo_url && (
                            <img src={`${BASE_URL}/images/players/${p.id}/photo`} alt="" className="w-6 h-6 rounded-full object-cover object-top" />
                          )}
                          <span className="flex-1 truncate">{p.display_name || p.name}</span>
                          {p.player_role && <span className="font-mono text-[9px] text-pb-faintest">{p.player_role}</span>}
                          <span className="text-pb-faintest group-hover:text-pb-accent text-xs">+</span>
                        </button>
                      ))}
                      {filteredPlayers.filter(p => !selectedPlayers.find(sp => sp.player.id === p.id)).length === 0 && (
                        <p className="text-pb-faintest text-xs px-3 py-2">{playerSearch ? 'No players match.' : 'All players added.'}</p>
                      )}
                    </div>
                  </>
                )}
              </section>
            )}

            {/* Hero Image */}
            {['T1','T3','T6','T7','C1','C3'].includes(templateId) && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Hero Image</h2>
                <p className="text-[11px] text-pb-faint mb-3">Upload a player cutout (transparent PNG recommended) to use as the featured image.</p>
                <div className="flex flex-col gap-3">
                  <label className="flex items-center gap-3 cursor-pointer group">
                    <span
                      className="px-3 py-2 rounded border pb-hairline text-xs font-mono text-pb-faint hover:text-pb-text group-hover:bg-pb-surface2 transition-colors"
                    >
                      Choose File
                    </span>
                    <span className="text-[11px] text-pb-faint truncate">
                      {heroImage.blobUrl ? 'Image selected' : 'No file chosen'}
                    </span>
                    <input type="file" accept="image/png,image/webp,image/jpeg" onChange={handleHeroFile} className="sr-only" />
                  </label>
                  {heroImage.blobUrl && (
                    <div className="flex items-start gap-3">
                      <img src={heroImage.blobUrl} alt="Hero preview" className="w-16 h-16 object-contain rounded bg-pb-surface2" />
                      <div className="flex flex-col gap-2 flex-1">
                        {selectedPlayers.length > 1 && (
                          <Field label="Apply to player slot">
                            <select value={heroImage.playerIdx}
                              onChange={e => setHeroImage(h => ({ ...h, playerIdx: +e.target.value }))}
                              className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                              {selectedPlayers.map((sp, i) => (
                                <option key={i} value={i}>{sp.player.display_name || sp.player.name}</option>
                              ))}
                            </select>
                          </Field>
                        )}
                        <button
                          disabled={removingBg === 'hero'}
                          onClick={() => handleRemoveBg('hero', heroImage.blobUrl, newUrl => {
                            URL.revokeObjectURL(heroImage.blobUrl)
                            setHeroImage(h => ({ ...h, blobUrl: newUrl }))
                          })}
                          className="text-xs font-mono text-pb-faint hover:text-pb-text disabled:opacity-40 text-left"
                        >
                          {removingBg === 'hero' ? '⏳ Removing background…' : '✂ Remove background'}
                        </button>
                        <button
                          onClick={() => { URL.revokeObjectURL(heroImage.blobUrl); setHeroImage({ blobUrl: null, playerIdx: 0 }) }}
                          className="text-xs text-pb-faintest hover:text-red-400 font-mono text-left"
                        >
                          Remove image
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Template-specific extras */}

            {/* T7 Milestone */}
            {templateId === 'T7' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Milestone Data</h2>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Value (big number)"><TextInput value={milestone.value} onChange={v => setMilestone(m => ({ ...m, value: v }))} placeholder="200" /></Field>
                  <Field label="Unit"><TextInput value={milestone.unit} onChange={v => setMilestone(m => ({ ...m, unit: v }))} placeholder="GAMES" /></Field>
                  <div className="col-span-2">
                    <Field label="Reason (eyebrow)"><TextInput value={milestone.reason} onChange={v => setMilestone(m => ({ ...m, reason: v }))} placeholder="200TH GAME FOR THE CLUB" /></Field>
                  </div>
                  <div className="col-span-2">
                    <Field label="Detail line"><TextInput value={milestone.detail} onChange={v => setMilestone(m => ({ ...m, detail: v }))} placeholder="15 seasons · 4,872 runs" /></Field>
                  </div>
                  {selectedPlayers.length > 0 && (
                    <div className="col-span-2">
                      <Field label="Featured Player">
                        <select value={milestone.playerIdx} onChange={e => setMilestone(m => ({ ...m, playerIdx: +e.target.value }))}
                          className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                          {selectedPlayers.map((sp, i) => <option key={i} value={i}>{sp.player._name || sp.player.display_name || sp.player.name}</option>)}
                        </select>
                      </Field>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* C1 Announcement */}
            {templateId === 'C1' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Announcement</h2>
                <div className="grid grid-cols-1 gap-3">
                  <Field label="Kind (eyebrow chip)"><TextInput value={announcement.kind} onChange={v => setAnnouncement(a => ({ ...a, kind: v }))} placeholder="APPOINTMENT" /></Field>
                  <Field label="Headline"><TextInput value={announcement.headline} onChange={v => setAnnouncement(a => ({ ...a, headline: v }))} placeholder="NAMED CAPTAIN" /></Field>
                  <Field label="Subheadline"><TextInput value={announcement.subheadline} onChange={v => setAnnouncement(a => ({ ...a, subheadline: v }))} placeholder="FOR THE 2025-26 SEASON" /></Field>
                  {selectedPlayers.length > 0 && (
                    <Field label="Player">
                      <select value={announcement.playerIdx} onChange={e => setAnnouncement(a => ({ ...a, playerIdx: +e.target.value }))}
                        className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                        {selectedPlayers.map((sp, i) => <option key={i} value={i}>{sp.player._name || sp.player.display_name || sp.player.name}</option>)}
                      </select>
                    </Field>
                  )}
                </div>
              </section>
            )}

            {/* C2 Toss */}
            {templateId === 'C2' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Toss Result</h2>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Toss Won By">
                    <select value={toss.winner} onChange={e => setToss(t => ({ ...t, winner: e.target.value }))}
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                      <option value="TEAM">Us ({team.name})</option>
                      <option value="OPPONENT">Them ({oppData.name})</option>
                    </select>
                  </Field>
                  <Field label="Decision">
                    <select value={toss.decision} onChange={e => setToss(t => ({ ...t, decision: e.target.value }))}
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                      <option value="BAT">Bat first</option>
                      <option value="BOWL">Bowl first</option>
                    </select>
                  </Field>
                </div>
              </section>
            )}

            {/* C3 Man of Match */}
            {templateId === 'C3' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Player Spotlight</h2>
                {selectedPlayers.length > 0 && (
                  <div className="mb-3">
                    <Field label="Featured Player">
                      <select value={motm.playerIdx} onChange={e => setMotm(m => ({ ...m, playerIdx: +e.target.value }))}
                        className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                        {selectedPlayers.map((sp, i) => <option key={i} value={i}>{sp.player._name || sp.player.display_name || sp.player.name}</option>)}
                      </select>
                    </Field>
                  </div>
                )}
                <div className="mb-3">
                  <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">Stats (up to 4)</label>
                  <div className="flex flex-col gap-2">
                    {motm.stats.map((s, i) => (
                      <StatRow key={i} stat={s} onChange={v => setMotm(m => { const next = [...m.stats]; next[i] = v; return { ...m, stats: next } })} onRemove={() => setMotm(m => ({ ...m, stats: m.stats.filter((_, j) => j !== i) }))} />
                    ))}
                    {motm.stats.length < 4 && (
                      <button onClick={() => setMotm(m => ({ ...m, stats: [...m.stats, { label: '', value: '' }] }))}
                        className="text-left text-xs text-pb-faint hover:text-pb-accent font-mono">+ Add stat</button>
                    )}
                  </div>
                </div>
                <Field label="Summary quote">
                  <textarea value={motm.summary} onChange={e => setMotm(m => ({ ...m, summary: e.target.value }))} rows={2}
                    placeholder="A brief description of their performance..."
                    className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest resize-none" />
                </Field>
              </section>
            )}

            {/* C4 Final Score */}
            {templateId === 'C4' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Match Result</h2>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <Field label="Winner">
                    <select value={result.winner} onChange={e => setResult(r => ({ ...r, winner: e.target.value }))}
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                      <option value="TEAM">Us ({team.name})</option>
                      <option value="OPPONENT">Them ({oppData.name})</option>
                      <option value="TIE">Tie / No result</option>
                    </select>
                  </Field>
                  <Field label="Margin"><TextInput value={result.margin} onChange={v => setResult(r => ({ ...r, margin: v }))} placeholder="by 28 runs" /></Field>
                  <Field label="Our Score"><TextInput value={result.teamScore} onChange={v => setResult(r => ({ ...r, teamScore: v }))} placeholder="182/6 (20)" /></Field>
                  <Field label="Their Score"><TextInput value={result.oppScore} onChange={v => setResult(r => ({ ...r, oppScore: v }))} placeholder="154/9 (20)" /></Field>
                  <div className="col-span-2">
                    <Field label="MOTM Surname"><TextInput value={result.motmLast} onChange={v => setResult(r => ({ ...r, motmLast: v }))} placeholder="HOLT" /></Field>
                  </div>
                </div>

                {/* Top performers */}
                {[
                  { side: 'team', label: `Our Batters (${team.name})`, type: 'topBatters' },
                  { side: 'team', label: `Our Bowlers (${team.name})`, type: 'topBowlers' },
                  { side: 'opponent', label: `Their Batters (${oppData.name})`, type: 'topBatters' },
                  { side: 'opponent', label: `Their Bowlers (${oppData.name})`, type: 'topBowlers' },
                ].map(({ side, label, type }) => (
                  <div key={`${type}-${side}`} className="mb-3">
                    <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">{label}</label>
                    <div className="flex flex-col gap-1.5">
                      {result[type][side].map((p, i) => (
                        <PerformerRow key={i} p={p}
                          onChange={v => setResult(r => {
                            const next = { ...r, [type]: { ...r[type], [side]: [...r[type][side]] } }
                            next[type][side][i] = v
                            return next
                          })}
                          onRemove={() => setResult(r => {
                            const next = { ...r, [type]: { ...r[type], [side]: r[type][side].filter((_, j) => j !== i) } }
                            return next
                          })}
                        />
                      ))}
                      {result[type][side].length < 3 && (
                        <button onClick={() => setResult(r => ({ ...r, [type]: { ...r[type], [side]: [...r[type][side], { last: '', line: '' }] } }))}
                          className="text-left text-xs text-pb-faint hover:text-pb-accent font-mono">+ Add</button>
                      )}
                    </div>
                  </div>
                ))}
              </section>
            )}

            {/* Scorecard data form */}
            {isScorecard && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Scorecard Data</h2>

                {/* PlayCricket URL import */}
                <div className="mb-4 p-3 rounded border pb-hairline bg-pb-surface2">
                  <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-2">Auto-fill from PlayCricket</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={scUrlInput}
                      onChange={e => { setScUrlInput(e.target.value); setScUrlStatus(null) }}
                      placeholder="https://play.cricket.com.au/match/37af9ea5-..."
                      className="flex-1 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono"
                      onKeyDown={e => e.key === 'Enter' && handleScUrlImport()}
                    />
                    <button
                      onClick={handleScUrlImport}
                      disabled={scUrlStatus === 'loading'}
                      className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50"
                      style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}
                    >
                      {scUrlStatus === 'loading' ? 'Loading…' : 'Import'}
                    </button>
                  </div>
                  {scUrlStatus && scUrlStatus !== 'loading' && (
                    <p className={`font-mono text-[9px] mt-1.5 ${scUrlStatus === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                      {scUrlStatus === 'ok' ? '✓ Scorecard loaded — review and adjust below' : `✗ ${scUrlStatus}`}
                    </p>
                  )}
                </div>

                {/* Meta */}
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <Field label="Result"><TextInput value={scorecardMatch.meta.result} onChange={v => patchScMeta({ result: v })} placeholder="HOME WON BY 6 WICKETS" /></Field>
                  <Field label="Competition"><TextInput value={scorecardMatch.meta.competition} onChange={v => patchScMeta({ competition: v })} placeholder="PREMIER GRADE" /></Field>
                  <Field label="Round"><TextInput value={scorecardMatch.meta.round} onChange={v => patchScMeta({ round: v })} placeholder="ROUND 7" /></Field>
                  <Field label="Format"><TextInput value={scorecardMatch.meta.format} onChange={v => patchScMeta({ format: v })} placeholder="T20" /></Field>
                  <Field label="Overs"><TextInput value={String(scorecardMatch.meta.overs)} onChange={v => patchScMeta({ overs: Number(v) || 20 })} placeholder="20" /></Field>
                  <Field label="Date"><TextInput value={scorecardMatch.meta.date} onChange={v => patchScMeta({ date: v })} placeholder="SAT 1 JAN" /></Field>
                  <div className="col-span-2">
                    <Field label="Venue"><TextInput value={scorecardMatch.meta.venue} onChange={v => patchScMeta({ venue: v })} placeholder="Home Ground" /></Field>
                  </div>
                  <div className="col-span-2">
                    <Field label="Toss"><TextInput value={scorecardMatch.meta.toss} onChange={v => patchScMeta({ toss: v })} placeholder="HOME WON THE TOSS · ELECTED TO BAT" /></Field>
                  </div>
                  <div className="col-span-2">
                    <Field label="Series"><TextInput value={scorecardMatch.meta.series} onChange={v => patchScMeta({ series: v })} placeholder="SEASON 2025/26" /></Field>
                  </div>
                  <Field label="MOTM First Name"><TextInput value={scorecardMatch.meta.motm.first} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, first: v } })} placeholder="Player" /></Field>
                  <Field label="MOTM Last Name"><TextInput value={scorecardMatch.meta.motm.last} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, last: v } })} placeholder="NAME" /></Field>
                  <div className="col-span-2">
                    <Field label="MOTM Line"><TextInput value={scorecardMatch.meta.motm.line} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, line: v } })} placeholder="87 (54) · 2/22" /></Field>
                  </div>
                  <div className="col-span-2">
                    <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mb-1">Sponsor Logos</p>
                    <div className="grid grid-cols-2 gap-2">
                      {[0, 1].map(i => (
                        <div key={i} className="flex flex-col gap-1">
                          <label className="flex items-center gap-2 px-2 py-1.5 rounded border pb-hairline cursor-pointer hover:bg-pb-surface2 text-xs font-mono text-pb-faint">
                            <span>{sponsorFiles[i] ? '✓ Loaded' : `Sponsor ${i + 1}`}</span>
                            <input type="file" accept="image/*" className="hidden" onChange={e => handleSponsorFile(i, e.target.files?.[0])} />
                          </label>
                          {sponsorFiles[i] && (
                            <div className="flex items-center gap-2">
                              <img src={sponsorFiles[i]} alt="" className="h-8 object-contain rounded border pb-hairline flex-1 min-w-0" />
                              <button
                                disabled={removingBg === `sponsor-${i}`}
                                onClick={() => handleRemoveBg(`sponsor-${i}`, sponsorFiles[i], newUrl => {
                                  setSponsorFiles(prev => { const next = [...prev]; next[i] = newUrl; return next })
                                  setScorecardMatch(m => ({
                                    ...m,
                                    meta: {
                                      ...m.meta,
                                      sponsors: m.meta.sponsors.map((s, j) => j === i ? { ...s, url: newUrl } : s),
                                    },
                                  }))
                                })}
                                className="shrink-0 text-[10px] font-mono text-pb-faint hover:text-pb-text disabled:opacity-40 whitespace-nowrap"
                                title="Remove background"
                              >
                                {removingBg === `sponsor-${i}` ? '⏳' : '✂ BG'}
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Team panels */}
                {['home', 'away'].map(side => {
                  const t = scorecardMatch[side]
                  return (
                    <details key={side} className="mb-3 border pb-hairline rounded">
                      <summary className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase px-3 py-2 cursor-pointer hover:bg-pb-surface2">
                        {side === 'home' ? '1st Innings' : '2nd Innings'} — {t.name || side.toUpperCase()}
                      </summary>
                      <div className="px-3 pb-3 pt-2 flex flex-col gap-2">
                        {/* Club search */}
                        <div className="relative">
                          <label className="block font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase mb-1">Search Club (CA)</label>
                          <div className="relative">
                            <input
                              value={scTeamSearch[side]}
                              onChange={e => handleScTeamSearch(side, e.target.value)}
                              placeholder="Type club name…"
                              className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-xs text-pb-text placeholder:text-pb-faintest"
                            />
                            {scTeamSearching[side] && (
                              <span className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[9px] text-pb-faintest animate-pulse">SEARCHING…</span>
                            )}
                          </div>
                          {scTeamResults[side].length > 0 && (
                            <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-pb-surface border pb-hairline rounded shadow-lg max-h-48 overflow-y-auto">
                              {scTeamResults[side].map((org, i) => (
                                <button
                                  key={org.id || i}
                                  onClick={() => selectScTeam(side, org)}
                                  className="w-full text-left px-3 py-1.5 hover:bg-pb-surface2 flex items-center gap-2 border-b pb-hairline last:border-0"
                                >
                                  {(org.logoURL || org.logo_url) && (
                                    <img src={org.logoURL || org.logo_url} alt="" className="w-6 h-6 rounded object-contain bg-pb-surface2 shrink-0" />
                                  )}
                                  <span className="text-xs text-pb-text flex-1 truncate">{org.name}</span>
                                  {org.shortName && <span className="font-mono text-[9px] text-pb-faintest">{org.shortName}</span>}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="grid grid-cols-4 gap-2">
                          <div className="col-span-2">
                            <Field label="Team Name"><TextInput value={t.name} onChange={v => patchScTeam(side, { name: v, monogram: v.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 3) })} placeholder="HOME TEAM" /></Field>
                          </div>
                          <Field label="Short (3)"><TextInput value={t.short} onChange={v => patchScTeam(side, { short: v.toUpperCase().slice(0, 4), monogram: v.toUpperCase().slice(0, 3) })} placeholder="HOM" /></Field>
                          <Field label="Team Colour">
                            <input type="color" value={t.color} onChange={e => patchScTeam(side, { color: e.target.value })} className="w-full h-[34px] rounded cursor-pointer border-0 bg-transparent p-0" />
                          </Field>
                          <Field label="Header Text">
                            <input type="color" value={t.headerInk || '#0a0a0a'} onChange={e => patchScTeam(side, { headerInk: e.target.value })} className="w-full h-[34px] rounded cursor-pointer border-0 bg-transparent p-0" />
                          </Field>
                          <Field label="Total"><TextInput value={t.total} onChange={v => patchScTeam(side, { total: v })} placeholder="182" /></Field>
                          <Field label="Wickets"><TextInput value={String(t.wickets)} onChange={v => patchScTeam(side, { wickets: Number(v) || 0 })} placeholder="7" /></Field>
                          <Field label="Overs"><TextInput value={t.overs} onChange={v => patchScTeam(side, { overs: v })} placeholder="20.0" /></Field>
                          <Field label="Run Rate"><TextInput value={t.runRate} onChange={v => patchScTeam(side, { runRate: v })} placeholder="9.10" /></Field>
                          <div className="col-span-4">
                            <Field label="Extras (b·lb·nb·wd)">
                              <div className="grid grid-cols-4 gap-1">
                                {['b','lb','nb','wd'].map(k => (
                                  <input key={k} type="number" min="0" value={t.extras[k]} onChange={e => {
                                    const next = { ...t.extras, [k]: +e.target.value }
                                    next.total = next.b + next.lb + next.nb + next.wd
                                    patchScExtras(side, next)
                                  }} placeholder={k} className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono text-center" />
                                ))}
                              </div>
                            </Field>
                          </div>
                        </div>

                        {/* Batting rows */}
                        <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mt-1">Batting</p>
                        <div className="flex flex-col gap-0.5">
                          <div className="grid gap-1 font-mono text-[8px] text-pb-faintest px-1" style={{ gridTemplateColumns: '18px 1fr 1fr 32px 32px 24px 24px auto' }}>
                            <span>#</span><span>First</span><span>Last</span><span>Runs</span><span>Balls</span><span>4s</span><span>6s</span><span>Out</span>
                          </div>
                          {t.batting.map((p, i) => (
                            <div key={i} className="grid gap-1 items-center" style={{ gridTemplateColumns: '18px 1fr 1fr 32px 32px 24px 24px auto' }}>
                              <span className="font-mono text-[9px] text-pb-faintest text-center">{p.num}</span>
                              <input value={p.first} onChange={e => updateBatRow(side, i, { first: e.target.value })} placeholder="First" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text" />
                              <input value={p.last} onChange={e => updateBatRow(side, i, { last: e.target.value })} placeholder="LAST" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text font-mono uppercase" />
                              <input type="number" min="0" value={p.r} onChange={e => updateBatRow(side, i, { r: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.b} onChange={e => updateBatRow(side, i, { b: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.fours} onChange={e => updateBatRow(side, i, { fours: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.sixes} onChange={e => updateBatRow(side, i, { sixes: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <div className="flex gap-1">
                                <button onClick={() => updateBatRow(side, i, { notOut: !p.notOut, didNotBat: false })} className={`font-mono text-[8px] px-1 py-0.5 rounded border pb-hairline ${p.notOut ? 'text-pb-text' : 'text-pb-faintest'}`} style={p.notOut ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}>NO</button>
                                <button onClick={() => updateBatRow(side, i, { didNotBat: !p.didNotBat, notOut: false })} className={`font-mono text-[8px] px-1 py-0.5 rounded border pb-hairline ${p.didNotBat ? 'text-pb-text' : 'text-pb-faintest'}`} style={p.didNotBat ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}>DNB</button>
                              </div>
                            </div>
                          ))}
                          {t.batting.length < 11 && (
                            <button onClick={() => patchScTeam(side, { batting: [...t.batting, DEFAULT_BATTING_ROW(t.batting.length + 1)] })} className="text-xs text-pb-faint hover:text-pb-accent font-mono text-left">+ Add batter</button>
                          )}
                        </div>

                        {/* Dismissal text for each batter (collapsed) */}
                        <details className="mt-1">
                          <summary className="font-mono text-[9px] text-pb-faintest cursor-pointer">Dismissal text (optional)</summary>
                          <div className="flex flex-col gap-1 mt-1">
                            {t.batting.filter(p => !p.didNotBat && !p.notOut).map((p, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <span className="font-mono text-[9px] text-pb-faintest w-16 truncate">{p.last}</span>
                                <input value={p.out || ''} onChange={e => updateBatRow(side, t.batting.indexOf(p), { out: e.target.value })} placeholder="c Smith b Jones" className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-0.5 text-xs text-pb-text" />
                              </div>
                            ))}
                          </div>
                        </details>

                        {/* Bowling rows */}
                        <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mt-2">Bowling</p>
                        <div className="flex flex-col gap-0.5">
                          <div className="grid gap-1 font-mono text-[8px] text-pb-faintest px-1" style={{ gridTemplateColumns: '1fr 1fr 32px 28px 32px 28px' }}>
                            <span>First</span><span>Last</span><span>Ovrs</span><span>M</span><span>Runs</span><span>Wkts</span>
                          </div>
                          {t.bowling.map((p, i) => (
                            <div key={i} className="grid gap-1 items-center" style={{ gridTemplateColumns: '1fr 1fr 32px 28px 32px 28px' }}>
                              <input value={p.first} onChange={e => updateBowlRow(side, i, { first: e.target.value })} placeholder="First" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text" />
                              <input value={p.last} onChange={e => updateBowlRow(side, i, { last: e.target.value })} placeholder="LAST" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text font-mono uppercase" />
                              <input type="number" min="0" step="0.1" value={p.o} onChange={e => updateBowlRow(side, i, { o: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.m} onChange={e => updateBowlRow(side, i, { m: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.r} onChange={e => updateBowlRow(side, i, { r: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.w} onChange={e => updateBowlRow(side, i, { w: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                            </div>
                          ))}
                          {t.bowling.length < 8 && (
                            <button onClick={() => patchScTeam(side, { bowling: [...t.bowling, DEFAULT_BOWLING_ROW(t.bowling.length)] })} className="text-xs text-pb-faint hover:text-pb-accent font-mono text-left">+ Add bowler</button>
                          )}
                        </div>
                      </div>
                    </details>
                  )
                })}
              </section>
            )}

          </div>{/* end left panel */}

          {/* ── RIGHT PANEL: preview ─────────────────────────── */}
          <div className="flex-1 min-w-0 flex flex-col gap-4">
            <div className="pb-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Preview — {tmpl.id}: {tmpl.name}</h2>
                <div className="flex items-center gap-2">
                  {exportError && <span className="text-red-400 text-xs font-mono">{exportError}</span>}
                  <button
                    onClick={handleExport}
                    disabled={exporting}
                    className="flex items-center gap-2 px-4 py-2 rounded text-sm font-mono tracking-wide2 transition-colors disabled:opacity-60"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}
                  >
                    {exporting ? 'EXPORTING...' : '↓ DOWNLOAD PNG'}
                  </button>
                </div>
              </div>

              {/* Scaled preview */}
              {(() => {
                const W = isScorecard ? 1920 : 1080
                const H = isScorecard ? 1080 : 1080
                const previewW = 620
                const scale = previewW / W
                const previewH = Math.round(H * scale)
                return (
                  <>
                    <div style={{ width: previewW, height: previewH, overflow: 'hidden', border: '1px solid var(--pb-hairline)', borderRadius: 8, background: '#0a0a0a' }}>
                      <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: W, height: H, pointerEvents: 'none' }}>
                        <TemplateComponent
                          team={team}
                          opponent={oppData}
                          match={matchData}
                          players={templatePlayers}
                          palette={activePalette}
                          {...extraProps}
                        />
                      </div>
                    </div>
                    <p className="text-pb-faintest text-[10px] font-mono mt-2">{W} × {H} px · shown at {Math.round(scale * 100)}%</p>
                  </>
                )
              })()}
            </div>

            {/* Hidden full-size render for export */}
            <div style={{ position: 'absolute', left: '-9999px', top: 0, pointerEvents: 'none', zIndex: -1 }}>
              <div ref={renderRef} style={{ width: isScorecard ? 1920 : 1080, height: 1080 }}>
                <TemplateComponent
                  team={team}
                  opponent={oppData}
                  match={matchData}
                  players={templatePlayers}
                  palette={activePalette}
                  {...extraProps}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
