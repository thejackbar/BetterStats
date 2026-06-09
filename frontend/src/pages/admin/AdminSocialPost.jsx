import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import BetterSocialsLayout from '../../components/admin/BetterSocialsLayout'
import ImageEditorModal from '../../components/ImageEditorModal'
import Dropdown from '../../components/Dropdown'
import { api } from '../../lib/api'
import {
  T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder,
  T5_Brutalist, T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer,
  C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore,
  SC1_Broadcast, SC2_Brutalist, SC3_Dashboard,
  PALETTES, orgToPalette,
} from '../../social/cricket-templates'
import {
  FixtureList, FixtureHype, FixtureGrid, FixtureBoard, FixtureHeadline, FixtureSchedule,
  ResultMarginHero, ResultBroadcast, ResultVersusColumns, ResultStar, ResultInningsBars, ResultTicket,
  ResultsList, ResultsScoreboard, ResultsRecord, ResultsHeadline, ResultsBoard, ResultsSplit,
  DEFAULT_FIXTURES, DEFAULT_RESULTS,
} from '../../social/round-templates'

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE REGISTRY
// ─────────────────────────────────────────────────────────────────────────────
const TEMPLATES = [
  { id: 'T1', name: 'Hero List',       component: T1_HeroList,        desc: 'Big player + name list',          maxPlayers: 13 },
  { id: 'T2', name: 'Card Grid',       component: T2_CardGrid,        desc: '4×3 trading card grid',           maxPlayers: 12 },
  { id: 'T3', name: 'Side Numbered',   component: T3_SideNumbered,    desc: 'Side photo + numbered XI',        maxPlayers: 11 },
  { id: 'T4', name: 'Batting Order',   component: T4_BattingOrder,    desc: 'Tactical batting order',          maxPlayers: 13 },
  { id: 'T5', name: 'Brutalist',       component: T5_Brutalist,       desc: 'Typography-forward XI',           maxPlayers: 11 },
  { id: 'T6', name: 'Diagonal Poster', component: T6_Diagonal,        desc: 'Diagonal poster, match-day hype', maxPlayers: 11 },
  { id: 'T7', name: 'Milestone',       component: T7_CaptainSpotlight, desc: 'Milestone achievement showcase',  maxPlayers: 13 },
  { id: 'T8', name: 'Mosaic',          component: T8_Mosaic,          desc: 'Asymmetric photo mosaic',         maxPlayers: 11 },
  { id: 'T9', name: 'Flyer',           component: T9_Flyer,           desc: 'Festival poster style',           maxPlayers: 11 },
  { id: 'C1', name: 'Announcement',    component: C1_CaptainAnnounce, desc: 'Captain / debut / award',         maxPlayers: 1 },
  { id: 'C2', name: 'Toss',            component: C2_TossWon,         desc: 'Toss result post',                maxPlayers: 0 },
  { id: 'C3', name: 'Player Spotlight',component: C3_ManOfMatch,      desc: 'Man of match / player stats',     maxPlayers: 1 },
  { id: 'C4', name: 'Result · Classic', component: C4_FinalScore,     desc: 'Full time result + top performers', maxPlayers: 0 },
  // Single-match result layouts (fold into the Final Score tab alongside C4).
  { id: 'RS1', name: 'Margin Hero',    component: ResultMarginHero,   desc: 'Big WIN headline + margin',       maxPlayers: 0, kind: 'singleresult' },
  { id: 'RS2', name: 'Broadcast',      component: ResultBroadcast,    desc: 'Team rows + top performers',      maxPlayers: 0, kind: 'singleresult' },
  { id: 'RS3', name: 'Versus Columns', component: ResultVersusColumns, desc: 'Two columns, winner lit',        maxPlayers: 0, kind: 'singleresult' },
  { id: 'RS4', name: 'Star of the Day', component: ResultStar,        desc: 'Player-of-the-match hero',        maxPlayers: 0, kind: 'singleresult' },
  { id: 'RS5', name: 'Innings Bars',   component: ResultInningsBars,  desc: 'Proportional score bars',         maxPlayers: 0, kind: 'singleresult' },
  { id: 'RS6', name: 'Match Ticket',   component: ResultTicket,       desc: 'Ticket-stub aesthetic',           maxPlayers: 0, kind: 'singleresult' },
  // Fixtures roundup — one post, all grades.
  { id: 'FX1', name: 'List',           component: FixtureList,        desc: 'Clean factual rows',              maxPlayers: 0, kind: 'fixtures' },
  { id: 'FX2', name: 'Match-day Hype', component: FixtureHype,        desc: 'Diagonal poster',                 maxPlayers: 0, kind: 'fixtures' },
  { id: 'FX3', name: 'Grid',           component: FixtureGrid,        desc: '2×3 fixture cards',               maxPlayers: 0, kind: 'fixtures' },
  { id: 'FX4', name: 'Board',          component: FixtureBoard,       desc: 'Departure-board table',           maxPlayers: 0, kind: 'fixtures' },
  { id: 'FX5', name: 'Headline',       component: FixtureHeadline,    desc: 'Feature match + also-on',         maxPlayers: 0, kind: 'fixtures' },
  { id: 'FX6', name: 'Schedule',       component: FixtureSchedule,    desc: 'Match-day timeline',              maxPlayers: 0, kind: 'fixtures' },
  // Results roundup — one post, all grades, win/loss coded.
  { id: 'RR1', name: 'Weekend Wrap',   component: ResultsList,        desc: 'Win/loss list',                   maxPlayers: 0, kind: 'results' },
  { id: 'RR2', name: 'W/L Scoreboard', component: ResultsScoreboard,  desc: '2×3 result cards',                maxPlayers: 0, kind: 'results' },
  { id: 'RR3', name: 'Record Strip',   component: ResultsRecord,      desc: 'W–L record summary',              maxPlayers: 0, kind: 'results' },
  { id: 'RR4', name: 'Headline',       component: ResultsHeadline,    desc: 'Feature result + others',         maxPlayers: 0, kind: 'results' },
  { id: 'RR5', name: 'Board',          component: ResultsBoard,       desc: 'Results table',                   maxPlayers: 0, kind: 'results' },
  { id: 'RR6', name: 'Win/Loss Split', component: ResultsSplit,       desc: 'Wins vs losses columns',          maxPlayers: 0, kind: 'results' },
  { id: 'SC1', name: 'Broadcast',      component: SC1_Broadcast,      desc: 'TV-style full scorecard',         maxPlayers: 0, isScorecard: true },
  { id: 'SC2', name: 'Brutalist',      component: SC2_Brutalist,      desc: 'Bold type, heavy rules',          maxPlayers: 0, isScorecard: true },
  { id: 'SC3', name: 'Dashboard',      component: SC3_Dashboard,      desc: 'Soft cards, app-style',           maxPlayers: 0, isScorecard: true },
]

const TAB_MAP = {
  T1: 'lineup', T2: 'lineup', T3: 'lineup', T4: 'lineup', T5: 'lineup',
  T6: 'lineup', T7: 'lineup', T8: 'lineup', T9: 'lineup',
  FX1: 'fixtures', FX2: 'fixtures', FX3: 'fixtures', FX4: 'fixtures', FX5: 'fixtures', FX6: 'fixtures',
  C1: 'announcement', C2: 'toss', C3: 'motm',
  C4: 'result', RS1: 'result', RS2: 'result', RS3: 'result', RS4: 'result', RS5: 'result', RS6: 'result',
  RR1: 'results', RR2: 'results', RR3: 'results', RR4: 'results', RR5: 'results', RR6: 'results',
  SC1: 'scorecard', SC2: 'scorecard', SC3: 'scorecard',
}
const TABS = [
  { key: 'lineup',       label: 'Lineup' },
  { key: 'fixtures',     label: 'Fixtures' },
  { key: 'result',       label: 'Final Score' },
  { key: 'results',      label: 'Results' },
  { key: 'motm',         label: 'Player of Match' },
  { key: 'announcement', label: 'Announcement' },
  { key: 'toss',         label: 'Toss' },
  { key: 'scorecard',    label: 'Scorecard' },
]
const TAB_FIRST = {
  lineup: 'T1', fixtures: 'FX1', announcement: 'C1', toss: 'C2', motm: 'C3',
  result: 'C4', results: 'RR1', scorecard: 'SC1',
}

const DISPLAY_FONTS = [
  { key: 'barlow',       name: 'Barlow Condensed', family: "'Barlow Condensed', sans-serif", weight: 800 },
  { key: 'anton',        name: 'Anton',            family: "'Anton', sans-serif",            weight: 400 },
  { key: 'bebas',        name: 'Bebas Neue',       family: "'Bebas Neue', sans-serif",       weight: 400 },
  { key: 'archivo',      name: 'Archivo Black',    family: "'Archivo Black', sans-serif",    weight: 400 },
  { key: 'oswald',       name: 'Oswald',           family: "'Oswald', sans-serif",           weight: 700 },
  { key: 'teko',         name: 'Teko',             family: "'Teko', sans-serif",             weight: 600 },
  { key: 'bigshoulders', name: 'Big Shoulders',    family: "'Big Shoulders Display', sans-serif", weight: 800 },
  { key: 'antonio',      name: 'Antonio',          family: "'Antonio', sans-serif",          weight: 700 },
  { key: 'marker',       name: 'Permanent Marker', family: "'Permanent Marker', cursive",    weight: 400 },
  { key: 'caveat',       name: 'Caveat',           family: "'Caveat', cursive",              weight: 700 },
  { key: 'abril',        name: 'Abril Fatface',    family: "'Abril Fatface', serif",         weight: 400 },
  { key: 'bungee',       name: 'Bungee',           family: "'Bungee', sans-serif",           weight: 400 },
]

// ─────────────────────────────────────────────────────────────────────────────
// FONT EMBEDDING FOR EXPORT
// modern-screenshot only embeds fonts from stylesheets it can read, and reading
// a cross-origin <link> sheet's cssRules throws a SecurityError — so it silently
// skips them. Our display fonts come from fonts.googleapis.com, meaning they
// never make it into the captured SVG and the export falls back to a wide system
// font (text overflows / clips). We fetch those stylesheets ourselves, inline
// every font file as a data URI, and hand the result to the exporter's
// `font.cssText` option. Cached after the first successful build.
// ─────────────────────────────────────────────────────────────────────────────
let _embeddedFontCssPromise = null
function getEmbeddedFontCss() {
  if (!_embeddedFontCssPromise) {
    _embeddedFontCssPromise = buildEmbeddedFontCss().catch(e => {
      _embeddedFontCssPromise = null // let the next export retry
      throw e
    })
  }
  return _embeddedFontCssPromise
}
async function buildEmbeddedFontCss() {
  const hrefs = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
    .map(l => l.href)
    .filter(h => /fonts\.googleapis\.com/.test(h))
  let css = ''
  for (const href of hrefs) {
    try { css += (await (await fetch(href)).text()) + '\n' } catch { /* skip unreachable sheet */ }
  }
  const urls = Array.from(new Set(
    Array.from(css.matchAll(/url\((https:\/\/[^)]+?)\)/g)).map(m => m[1].replace(/['"]/g, ''))
  ))
  const pairs = await Promise.all(urls.map(async url => {
    try {
      const blob = await (await fetch(url)).blob()
      const dataUri = await new Promise((resolve, reject) => {
        const fr = new FileReader()
        fr.onload = () => resolve(fr.result)
        fr.onerror = reject
        fr.readAsDataURL(blob)
      })
      return [url, dataUri]
    } catch { return null }
  }))
  for (const pair of pairs) { if (pair) css = css.split(pair[0]).join(pair[1]) }
  return css
}

function applyTheme(palette, isDark) {
  if (isDark || !palette) return palette
  return { ...palette, primary: '#f0f0f0', secondary: '#e0e0e0', ink: '#0d0d0d' }
}

// ─────────────────────────────────────────────────────────────────────────────
// SCORECARD DEFAULTS
// ─────────────────────────────────────────────────────────────────────────────
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

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function splitName(displayName, nameFormat = 'last_first') {
  const raw = (displayName || '').trim()
  if (raw.includes(', ')) {
    const [lastPart, firstPart] = raw.split(', ', 2)
    return { first: firstPart.trim(), last: lastPart.trim().toUpperCase() }
  }
  const parts = raw.split(/\s+/)
  if (parts.length === 1) return { first: '', last: parts[0].toUpperCase() }
  if (nameFormat === 'first_last') {
    return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1].toUpperCase() }
  }
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
    first, last, role,
    roleLong: { BAT: 'Batter', BOWL: 'Bowler', AR: 'All-Rounder', WK: 'Wicket-Keeper' }[role] || role,
    captain, viceCaptain, keeper,
    headshot: p.photo_url ? `${BASE_URL}/images/players/${p.id}/photo` : null,
    _id: p.id,
    _name: p.display_name || p.name,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────
function PaletteSwatch({ pal, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      title={pal.name}
      style={{ background: pal.primary, border: `2px solid ${selected ? pal.accent : 'transparent'}`, borderRadius: 6, width: 36, height: 36, cursor: 'pointer', position: 'relative', overflow: 'hidden' }}
    >
      <span style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 10, background: pal.accent }} />
    </button>
  )
}

function SelectedPlayerRow({ sp, idx, onUpdate, onRemove, onMoveUp, onMoveDown, isFirst, isLast }) {
  const { player } = sp
  return (
    <div className="flex items-center gap-2 p-2 rounded bg-pb-surface border pb-hairline">
      <div className="flex flex-col gap-0.5 mr-1">
        <button onClick={onMoveUp} disabled={isFirst} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-xs leading-none">▲</button>
        <button onClick={onMoveDown} disabled={isLast} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-xs leading-none">▼</button>
      </div>
      <span className="font-mono text-[10px] text-pb-faintest w-4 shrink-0">{idx + 1}</span>
      <span className="text-sm text-pb-text flex-1 truncate">{player.display_name || player.name}</span>
      <select
        value={sp.role}
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

function StatRow({ stat, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-center">
      <input value={stat.label} onChange={e => onChange({ ...stat, label: e.target.value })} placeholder="Label (e.g. Runs)"
        className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono" />
      <input value={stat.value} onChange={e => onChange({ ...stat, value: e.target.value })} placeholder="Value"
        className="w-24 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono" />
      <button onClick={onRemove} className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
    </div>
  )
}

function PerformerRow({ p, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-center">
      <input value={p.last} onChange={e => onChange({ ...p, last: e.target.value })} placeholder="Name"
        className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
      <input value={p.line} onChange={e => onChange({ ...p, line: e.target.value })} placeholder="87 (54) or 3-22 (4)"
        className="w-36 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest font-mono" />
      <button onClick={onRemove} className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
    </div>
  )
}

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
    <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest" />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export default function AdminSocialPost() {
  const location = useLocation()
  const [settings, setSettings] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [adminSponsors, setAdminSponsors] = useState([])
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)

  const [templateId, setTemplateId] = useState(() =>
    localStorage.getItem('bs_social_template') || 'T1'
  )
  const [paletteKey, setPaletteKey] = useState(() =>
    localStorage.getItem('bs_social_palette') || 'club'
  )
  const [darkMode, setDarkMode] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_dark') ?? 'true') } catch { return true }
  })
  const [fontKey, setFontKey] = useState(() =>
    localStorage.getItem('bs_social_font') || 'barlow'
  )

  const [match, setMatch] = useState({ competition: '', round: '', venue: '', date: '', time: '', season: '' })
  const patchMatch = patch => setMatch(m => ({ ...m, ...patch }))
  // Headline shown on lineup templates (T1). Empty = template default ("SQUAD").
  // Auto-fills from the squad/team name when arriving from a saved XI.
  const [headline, setHeadline] = useState('')

  const [opponent, setOpponent] = useState({ name: '', short: '', monogram: '', logo: null })
  const patchOpp = patch => setOpponent(o => ({ ...o, ...patch }))
  const [oppSearch, setOppSearch] = useState('')
  const [oppResults, setOppResults] = useState([])
  const [oppSearching, setOppSearching] = useState(false)
  const oppSearchTimeout = useRef(null)
  const oppBoxRef = useRef(null)

  const [selectedPlayers, setSelectedPlayers] = useState([])
  const [playerSearch, setPlayerSearch] = useState('')
  const [swapNames, setSwapNames] = useState(false)

  const [customBg, setCustomBg] = useState('#243352')
  const [customAccent, setCustomAccent] = useState('#16c784')
  const [savedPalettes, setSavedPalettes] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_palettes') || '[]') } catch { return [] }
  })
  const [savePaletteName, setSavePaletteName] = useState('')

  const [heroImage, setHeroImage] = useState({ blobUrl: null })
  const [heroMode, setHeroMode] = useState('player')
  // Which selected player's photo fills the hero slot on lineup templates
  // (T1 / T3 / T6). '' = auto (captain, else first in the order).
  const [heroPlayerId, setHeroPlayerId] = useState('')

  const [scorecardMatch, setScorecardMatch] = useState(DEFAULT_SCORECARD)
  const [scUrlInput, setScUrlInput] = useState('')
  const [scUrlStatus, setScUrlStatus] = useState(null)

  // Editor: { key: 'hero' | `sponsor-${i}`, source: File|string }
  const [editor, setEditor] = useState(null)

  const [sponsorFiles, setSponsorFiles] = useState([null, null])
  const applySponsorBlob = (idx, blob, name) => {
    const url = URL.createObjectURL(blob)
    setSponsorFiles(prev => { const next = [...prev]; next[idx] = url; return next })
    setScorecardMatch(m => ({
      ...m,
      meta: {
        ...m.meta,
        sponsors: m.meta.sponsors.map((s, i) => i === idx ? { url, name: name || s.name || '' } : s),
      },
    }))
  }

  const handleSponsorFile = (idx, file) => {
    if (!file) return
    setEditor({ key: `sponsor-${idx}`, source: file, sponsorIdx: idx, sponsorName: file.name.replace(/\.[^.]+$/, '') })
  }

  const [milestone, setMilestone] = useState({ value: '', unit: 'GAMES', reason: '', detail: '', playerIdx: 0 })
  const [announcement, setAnnouncement] = useState({ kind: 'APPOINTMENT', headline: 'NAMED CAPTAIN', subheadline: 'FOR THE 2025-26 SEASON', playerIdx: 0 })
  const [toss, setToss] = useState({ winner: 'TEAM', decision: 'BAT' })
  const [motm, setMotm] = useState({ playerIdx: 0, stats: [{ label: 'Runs', value: '' }, { label: 'SR', value: '' }], summary: '' })
  const [result, setResult] = useState({
    winner: 'TEAM', margin: '', teamScore: '', oppScore: '', teamOvers: '', oppOvers: '', motmLast: '',
    motmFirst: '', motmRole: '', motmBat: '', motmBowl: '',
    topBatters: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
    topBowlers: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
  })
  // Fixtures / results roundups — one post, all grades. Seeded with sample rows
  // so a fresh tab previews well; users edit/add/remove.
  const [fixtures, setFixtures] = useState(() => DEFAULT_FIXTURES.map((f) => ({ ...f })))
  const [results, setResults] = useState(() => DEFAULT_RESULTS.map((r) => ({ ...r })))

  const renderRef = useRef(null)

  // localStorage persistence
  useEffect(() => { localStorage.setItem('bs_social_template', templateId) }, [templateId])
  useEffect(() => { localStorage.setItem('bs_social_palette', paletteKey) }, [paletteKey])
  useEffect(() => { localStorage.setItem('bs_social_dark', JSON.stringify(darkMode)) }, [darkMode])
  useEffect(() => { localStorage.setItem('bs_social_font', fontKey) }, [fontKey])

  useEffect(() => {
    Promise.all([api.adminGetSettings(), api.adminListPlayers(), api.adminListSponsors()])
      .then(([s, p, sp]) => {
        setSettings(s)
        setAllPlayers(p)
        const sponsors = sp || []
        setAdminSponsors(sponsors)
        if (sponsors.length > 0) {
          setScorecardMatch(m => ({
            ...m,
            meta: {
              ...m.meta,
              sponsors: [0, 1].map(i => {
                const s = sponsors[i]
                if (!s) return m.meta.sponsors[i] || { url: null, name: '' }
                return { url: `${BASE_URL}/images/sponsors/${s.id}/logo`, name: s.name }
              }),
            },
          }))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Team-sheet handoff from BetterSelect selection. Pre-populates the lineup
  // post from a saved XI once the player list has loaded. Runs once.
  const sheetApplied = useRef(false)
  useEffect(() => {
    const sheet = location.state?.teamSheet
    if (!sheet || sheetApplied.current || allPlayers.length === 0) return
    sheetApplied.current = true

    const byId = {}
    allPlayers.forEach(p => { byId[p.id] = p })
    const picked = (sheet.players || [])
      .map(s => {
        const player = byId[s.player_id]
        if (!player) return null
        return {
          player,
          role: s.role || 'BAT',
          captain: !!s.is_captain,
          viceCaptain: false,
          keeper: !!s.is_wicket_keeper,
        }
      })
      .filter(Boolean)
    if (picked.length) setSelectedPlayers(picked)

    if (sheet.match) {
      setMatch(m => ({
        ...m,
        round: sheet.match.round || m.round,
        venue: sheet.match.venue || m.venue,
        date: sheet.match.date || m.date,
        time: sheet.match.time || m.time,
      }))
    }
    if (sheet.opponent?.name) setOpponent(o => ({ ...o, name: sheet.opponent.name }))
    if (sheet.teamName) setHeadline(sheet.teamName)
    setTemplateId('T1') // a lineup template
    // Clear router state so a refresh doesn't re-apply.
    window.history.replaceState({}, document.title)
  }, [location.state, allPlayers])

  // Scorecard URL import
  const handleScUrlImport = async () => {
    const urlOrId = scUrlInput.trim()
    const uuidRe = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    const m = urlOrId.match(uuidRe)
    if (!m) { setScUrlStatus('Paste a play.cricket.com.au match URL or a match UUID'); return }
    const matchId = m[0]
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

  // Per-side scorecard team search
  const [scTeamSearch, setScTeamSearch] = useState({ home: '', away: '' })
  const [scTeamResults, setScTeamResults] = useState({ home: [], away: [] })
  const [scTeamSearching, setScTeamSearching] = useState({ home: false, away: false })
  const scTeamSearchTimeout = useRef({ home: null, away: null })
  const scHomeRef = useRef(null)
  const scAwayRef = useRef(null)
  const scTeamRefBySide = { home: scHomeRef, away: scAwayRef }

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

  // Opponent search
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
    let logoUrl = org.logoURL || org.logo_url || null
    try {
      const bsOrgs = await api.listOrgs()
      const matched = bsOrgs.find(o => o.name?.toLowerCase() === org.name?.toLowerCase() || o.id === org.id)
      if (matched?.id) logoUrl = `${BASE_URL}/images/organisations/${matched.id}/logo`
    } catch { /* ignore */ }
    patchOpp({
      name: org.name || org.shortName || '',
      short: org.shortName || deriveShort(org.name || 'OPP'),
      logo: logoUrl,
    })
    setOppSearch('')
    setOppResults([])
  }, [])

  const handleHeroFile = useCallback((e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setEditor({ key: 'hero', source: file })
  }, [])

  // Player management
  const addPlayer = useCallback(p => {
    if (selectedPlayers.find(sp => sp.player.id === p.id)) return
    const role = p.player_role && ['BAT','BOWL','AR','WK'].includes(p.player_role) ? p.player_role : 'BAT'
    setSelectedPlayers(prev => [...prev, { player: p, role, captain: false, viceCaptain: false, keeper: false }])
  }, [selectedPlayers])

  const removePlayer = useCallback(idx => setSelectedPlayers(prev => prev.filter((_, i) => i !== idx)), [])

  const updatePlayer = useCallback((idx, patch) => {
    setSelectedPlayers(prev => {
      const next = [...prev]
      if (patch.captain === true) next.forEach((p, i) => { if (i !== idx) p.captain = false })
      if (patch.viceCaptain === true) next.forEach((p, i) => { if (i !== idx) p.viceCaptain = false })
      if (patch.keeper === true) next.forEach((p, i) => { if (i !== idx) p.keeper = false })
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

  // Export to JPG. Uses modern-screenshot, which serializes the node into an
  // SVG <foreignObject> and lets the real browser engine lay it out — so the
  // capture matches the on-screen render exactly. (Replaces html2canvas, which
  // re-implemented layout in JS and caused text/image drift.) The render target
  // is already mounted off-screen at full W×H, so we capture it in place — no
  // reposition hack needed.
  const handleExport = async () => {
    if (!renderRef.current) return
    setExporting(true)
    setExportError(null)
    try {
      await document.fonts.ready
      const { domToBlob } = await import('modern-screenshot')
      const el = renderRef.current
      const W = tmpl.w || (tmpl.isScorecard ? 1920 : 1080)
      const H = tmpl.h || 1080
      // Embed the Google Fonts faces ourselves — modern-screenshot can't read
      // the cross-origin sheet, so without this the condensed display font is
      // dropped and the export falls back to a wide system font (text overflows).
      let font
      try { font = { cssText: await getEmbeddedFontCss() } } catch { /* fall back to system fonts */ }
      const blob = await domToBlob(el, {
        type: 'image/png',          // lossless PNG — exact replica, no JPG artefacts on crisp text
        scale: 2,                   // 2× for crisp, high-DPI output
        width: W,
        height: H,
        backgroundColor: '#080808', // fallback for any uncovered area; templates are full-bleed dark
        font,
      })
      if (!blob) { setExportError('Could not generate image'); return }
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `betterstats-${templateId.toLowerCase()}-${Date.now()}.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportError(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  // ─── Derived values ─────────────────────────────────────────────────────────

  const activeTab = TAB_MAP[templateId] || 'lineup'
  const switchTab = (tabKey) => setTemplateId(TAB_FIRST[tabKey] || 'T1')
  const tabTemplates = TEMPLATES.filter(t => TAB_MAP[t.id] === activeTab)
  const displayFont = DISPLAY_FONTS.find(f => f.key === fontKey) || DISPLAY_FONTS[0]

  const team = settings ? {
    name: (settings.name || 'CLUB').toUpperCase(),
    fullName: settings.name || 'Club',
    short: deriveShort(settings.name || 'Club'),
    monogram: deriveShort(settings.name || 'Club').slice(0, 2),
    logo: settings.logo_url ? `${BASE_URL}/images/organisations/${settings.id}/logo` : null,
  } : { name: 'CLUB', fullName: 'Club', short: 'CLB', monogram: 'CL', logo: null }

  const oppData = {
    name: opponent.name.toUpperCase() || 'OPPONENT',
    fullName: opponent.name || 'Opponent',
    short: opponent.short || deriveShort(opponent.name || 'OPP'),
    monogram: opponent.monogram || deriveShort(opponent.name || 'OPP').slice(0, 2),
    logo: opponent.logo || null,
  }

  const activePalette = paletteKey === 'club'
    ? orgToPalette(settings)
    : paletteKey === 'custom'
      ? { name: 'Custom', primary: customBg, secondary: customBg + 'cc', accent: customAccent, ink: '#ffffff' }
      : (savedPalettes.find(p => p.key === paletteKey) || PALETTES[paletteKey])

  const themedPalette = applyTheme(activePalette, darkMode)

  const nameFormat = settings?.player_name_format || 'last_first'
  const tmpl = TEMPLATES.find(t => t.id === templateId) || TEMPLATES[0]
  const isScorecard = !!(tmpl.isScorecard)
  const TemplateComponent = tmpl.component

  const filteredPlayers = allPlayers.filter(p => {
    if (!playerSearch) return true
    const q = playerSearch.toLowerCase()
    return (p.display_name || p.name || '').toLowerCase().includes(q)
  })

  // Template-specific extra props
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
    let annTemplatePlayer = annPlayer ? playerToTemplatePlayer(annPlayer.player, annPlayer, nameFormat, swapNames) : undefined
    if (annTemplatePlayer && heroMode === 'hero' && heroImage.blobUrl) {
      annTemplatePlayer = { ...annTemplatePlayer, headshot: heroImage.blobUrl }
    }
    extraProps.announcement = {
      kind: announcement.kind, headline: announcement.headline, subheadline: announcement.subheadline,
      player: annTemplatePlayer,
    }
  }
  if (templateId === 'C2') extraProps.toss = { winner: toss.winner, decision: toss.decision }
  if (templateId === 'C3') {
    const motmPlayer = selectedPlayers[motm.playerIdx]
    let motmTemplatePlayer = motmPlayer ? playerToTemplatePlayer(motmPlayer.player, motmPlayer, nameFormat, swapNames) : undefined
    if (motmTemplatePlayer && heroMode === 'hero' && heroImage.blobUrl) {
      motmTemplatePlayer = { ...motmTemplatePlayer, headshot: heroImage.blobUrl }
    }
    extraProps.motm = {
      player: motmTemplatePlayer,
      stats: motm.stats.filter(s => s.label && s.value),
      summary: motm.summary,
    }
  }
  if (['T1', 'T3', 'T6', 'T7'].includes(templateId) && heroImage.blobUrl) {
    extraProps.heroImage = heroImage.blobUrl
  }
  if (['T1', 'T3', 'T6'].includes(templateId) && heroPlayerId) {
    extraProps.featuredId = heroPlayerId
  }
  if (templateId === 'C4') {
    extraProps.result = {
      winner: result.winner, margin: result.margin, teamScore: result.teamScore,
      oppScore: result.oppScore, motmLast: result.motmLast,
      topBatters: result.topBatters, topBowlers: result.topBowlers,
    }
  }
  if (isScorecard) extraProps.match = scorecardMatch

  const templatePlayers = selectedPlayers.map((sp, i) => {
    const base = playerToTemplatePlayer(sp.player, sp, nameFormat, swapNames)
    return base
  })

  const matchData = {
    competition: match.competition || 'COMPETITION',
    round: match.round || 'ROUND 1',
    venue: match.venue || 'HOME GROUND',
    date: match.date || 'SAT 1 JAN',
    time: match.time || '1:00 PM',
    season: match.season || '2025–26',
  }

  // Fixtures / single-result / results roundups (new BetterSocials post sets).
  // They share the club identity, sponsor logos and round meta with the rest.
  const clubMark = { name: team.name, full: team.fullName, mono: team.monogram, logo: team.logo }
  const roundMeta = { round: matchData.round, date: matchData.date, comp: matchData.competition, season: matchData.season }
  if (tmpl.kind === 'fixtures') {
    extraProps.meta = roundMeta
    extraProps.fixtures = fixtures
    extraProps.club = clubMark
    extraProps.sponsors = scorecardMatch.meta.sponsors
  }
  if (tmpl.kind === 'results') {
    extraProps.meta = roundMeta
    extraProps.results = results
    extraProps.club = clubMark
    extraProps.sponsors = scorecardMatch.meta.sponsors
  }
  if (tmpl.kind === 'singleresult') {
    const mapPerf = (arr) => (arr || []).map((p) => ({ n: p.last, l: p.line })).filter((p) => p.n || p.l)
    extraProps.result = {
      comp: matchData.competition, round: matchData.round, date: matchData.date,
      season: matchData.season, venue: matchData.venue,
      us: { name: team.name, mono: team.monogram, logo: team.logo, score: result.teamScore || '—', overs: result.teamOvers || '' },
      them: { name: oppData.name, mono: oppData.monogram, logo: oppData.logo, score: result.oppScore || '—', overs: result.oppOvers || '' },
      winner: result.winner === 'OPPONENT' ? 'them' : result.winner === 'TIE' ? 'tie' : 'us',
      margin: result.margin || '',
      potm: {
        first: result.motmFirst || '', last: result.motmLast || '', role: result.motmRole || '',
        bat: result.motmBat || '', bowl: result.motmBowl || '',
        line: [result.motmBat, result.motmBowl].filter(Boolean).join(' · '),
      },
      topBat: { us: mapPerf(result.topBatters.team), them: mapPerf(result.topBatters.opponent) },
      topBowl: { us: mapPerf(result.topBowlers.team), them: mapPerf(result.topBowlers.opponent) },
    }
    extraProps.sponsors = scorecardMatch.meta.sponsors
  }

  const fontStyle = {
    '--social-display-font': displayFont.family,
    '--social-display-font-weight': String(displayFont.weight),
    fontWeight: displayFont.weight,
  }

  // Reset all state to defaults
  const handleReset = () => {
    const tid = TAB_FIRST[activeTab] || 'T1'
    setTemplateId(tid)
    setMatch({ competition: '', round: '', venue: '', date: '', time: '', season: '' })
    setHeadline('')
    setOpponent({ name: '', short: '', monogram: '', logo: null })
    setSelectedPlayers([])
    setHeroImage({ blobUrl: null })
    setHeroMode('player')
    setHeroPlayerId('')
    setMilestone({ value: '', unit: 'GAMES', reason: '', detail: '', playerIdx: 0 })
    setAnnouncement({ kind: 'APPOINTMENT', headline: 'NAMED CAPTAIN', subheadline: 'FOR THE 2025-26 SEASON', playerIdx: 0 })
    setToss({ winner: 'TEAM', decision: 'BAT' })
    setMotm({ playerIdx: 0, stats: [{ label: 'Runs', value: '' }, { label: 'SR', value: '' }], summary: '' })
    setResult({
      winner: 'TEAM', margin: '', teamScore: '', oppScore: '', teamOvers: '', oppOvers: '', motmLast: '',
      motmFirst: '', motmRole: '', motmBat: '', motmBowl: '',
      topBatters: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
      topBowlers: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
    })
    setFixtures(DEFAULT_FIXTURES.map((f) => ({ ...f })))
    setResults(DEFAULT_RESULTS.map((r) => ({ ...r })))
    setScorecardMatch(DEFAULT_SCORECARD)
    setScUrlInput('')
    setScUrlStatus(null)
  }

  if (loading) return (
    <BetterSocialsLayout>
      <div className="flex items-center justify-center h-64">
        <span className="font-mono text-[11px] text-pb-faint animate-pulse">LOADING...</span>
      </div>
    </BetterSocialsLayout>
  )

  // ─── Preview renderer ────────────────────────────────────────────────────────
  const W = tmpl.w || (isScorecard ? 1920 : 1080)
  const H = tmpl.h || 1080

  // ─── Controls ────────────────────────────────────────────────────────────────
  const showMatchInfo = activeTab !== 'scorecard'
  const showOpponent  = !['scorecard', 'fixtures', 'results'].includes(activeTab)
  const showPlayers   = activeTab !== 'scorecard' && tmpl.maxPlayers > 0
  const showHeroImage = ['T1','T3','T6','T7','C1','C3'].includes(templateId)

  return (
    <BetterSocialsLayout>
      <div className="max-w-full">
        <div className="flex gap-5 items-start">

          {/* ─── LEFT: controls ────────────────────────────────────────────── */}
          <div className="w-full xl:w-[500px] 2xl:w-[540px] shrink-0 flex flex-col gap-4 pb-20">

            {/* Style: palette + dark/light + font */}
            <section className="pb-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Style</h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setDarkMode(d => !d)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-[11px] font-mono transition-colors ${darkMode ? 'border-pb-text text-pb-text' : 'border-amber-400 text-amber-400'}`}
                  >
                    {darkMode ? '☾ Dark' : '☀ Light'}
                  </button>
                  <select
                    value={fontKey}
                    onChange={e => setFontKey(e.target.value)}
                    className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[11px] font-mono text-pb-text"
                  >
                    {DISPLAY_FONTS.map(f => <option key={f.key} value={f.key}>{f.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex gap-2 flex-wrap items-center">
                <button
                  onClick={() => setPaletteKey('club')}
                  className={`flex items-center gap-2 px-2.5 py-1 rounded border text-[11px] font-mono transition-colors ${paletteKey === 'club' ? '' : 'text-pb-faint hover:text-pb-text border-transparent'}`}
                  style={paletteKey === 'club' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                >
                  <span style={{ width: 12, height: 12, borderRadius: 2, background: settings?.primary_color || '#16c784', display: 'inline-block' }} />
                  Club
                </button>
                {Object.entries(PALETTES).map(([key, pal]) => (
                  <PaletteSwatch key={key} pal={pal} selected={paletteKey === key} onClick={() => setPaletteKey(key)} />
                ))}
                <button
                  onClick={() => setPaletteKey('custom')}
                  className={`px-2.5 py-1 rounded border text-[11px] font-mono transition-colors ${paletteKey === 'custom' ? '' : 'text-pb-faint hover:text-pb-text border-transparent'}`}
                  style={paletteKey === 'custom' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                >
                  Custom
                </button>
              </div>
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
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
              {paletteKey === 'custom' && (
                <div className="mt-2 flex flex-col gap-2">
                  <div className="flex gap-4 items-center">
                    <label className="flex items-center gap-2 text-xs text-pb-faint font-mono">
                      <input type="color" value={customBg} onChange={e => setCustomBg(e.target.value)} className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent p-0" />
                      Background
                    </label>
                    <label className="flex items-center gap-2 text-xs text-pb-faint font-mono">
                      <input type="color" value={customAccent} onChange={e => setCustomAccent(e.target.value)} className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent p-0" />
                      Accent
                    </label>
                  </div>
                  <div className="flex gap-2 items-center">
                    <input value={savePaletteName} onChange={e => setSavePaletteName(e.target.value)} placeholder="Palette name..."
                      className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-xs text-pb-text placeholder:text-pb-faintest font-mono" />
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
                    >Save</button>
                  </div>
                </div>
              )}
            </section>

            {/* Tab bar */}
            <div className="flex overflow-x-auto border-b pb-hairline gap-0 -mt-1">
              {TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => switchTab(tab.key)}
                  className={`shrink-0 px-3 py-2.5 font-mono text-[10px] tracking-wide2 whitespace-nowrap transition-colors border-b-2 -mb-px ${
                    activeTab === tab.key
                      ? 'text-pb-text border-pb-accent'
                      : 'text-pb-faint border-transparent hover:text-pb-dim'
                  }`}
                  style={activeTab === tab.key ? { borderColor: 'var(--pb-accent)' } : {}}
                >
                  {tab.label.toUpperCase()}
                </button>
              ))}
            </div>

            {/* Template variant selector (only when multiple exist) */}
            {tabTemplates.length > 1 && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Variant</h2>
                <div className="grid grid-cols-3 gap-2">
                  {tabTemplates.map(t => (
                    <button
                      key={t.id}
                      onClick={() => setTemplateId(t.id)}
                      className={`text-left p-2.5 rounded border transition-colors ${templateId === t.id ? 'bg-pb-surface2' : 'border-transparent bg-pb-surface hover:bg-pb-surface2'}`}
                      style={templateId === t.id ? { borderColor: 'var(--pb-accent)' } : {}}
                    >
                      <div className="font-mono text-[9px] text-pb-faintest mb-0.5">{t.id}</div>
                      <div className="font-medium text-pb-text text-xs leading-tight">{t.name}</div>
                      <div className="text-[10px] text-pb-faint leading-tight mt-0.5">{t.desc}</div>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Match Info */}
            {showMatchInfo && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Match Info</h2>
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2"><Field label="Headline (lineup posts)"><TextInput value={headline} onChange={setHeadline} placeholder="SQUAD · e.g. Applecross 6th XI" /></Field></div>
                  <Field label="Competition"><TextInput value={match.competition} onChange={v => patchMatch({ competition: v })} placeholder="PREMIER T20" /></Field>
                  <Field label="Round"><TextInput value={match.round} onChange={v => patchMatch({ round: v })} placeholder="ROUND 7" /></Field>
                  <Field label="Venue"><TextInput value={match.venue} onChange={v => patchMatch({ venue: v })} placeholder="Heathcote Reserve" /></Field>
                  <Field label="Date"><TextInput value={match.date} onChange={v => patchMatch({ date: v })} placeholder="SAT 30 MAY" /></Field>
                  <Field label="Time"><TextInput value={match.time} onChange={v => patchMatch({ time: v })} placeholder="2:30 PM" /></Field>
                  <Field label="Season"><TextInput value={match.season} onChange={v => patchMatch({ season: v })} placeholder="2025–26" /></Field>
                </div>
              </section>
            )}

            {/* Opponent */}
            {showOpponent && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Opponent</h2>
                <div className="relative mb-3">
                  <div ref={oppBoxRef} className="relative">
                    <input
                      value={oppSearch}
                      onChange={e => handleOppSearch(e.target.value)}
                      placeholder="Search club name..."
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest"
                    />
                    {oppSearching && <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[9px] text-pb-faintest animate-pulse">SEARCHING...</span>}
                  </div>
                  <Dropdown
                    anchorRef={oppBoxRef}
                    open={oppResults.length > 0}
                    onClose={() => setOppResults([])}
                    maxHeight={192}
                    className="bg-pb-surface border pb-hairline rounded shadow-lg"
                  >
                    {oppResults.map((org, i) => (
                      <button key={org.id || i} onClick={() => selectOpponent(org)}
                        className="w-full text-left px-3 py-2 hover:bg-pb-surface2 flex items-center gap-2 border-b pb-hairline last:border-0">
                        {(org.logoURL || org.logo_url) && (
                          <img src={org.logoURL || org.logo_url} alt="" className="w-7 h-7 rounded object-contain bg-pb-surface2 shrink-0" />
                        )}
                        <span className="text-sm text-pb-text flex-1 truncate">{org.name}</span>
                        {org.shortName && <span className="font-mono text-[9px] text-pb-faintest">{org.shortName}</span>}
                      </button>
                    ))}
                  </Dropdown>
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
            )}

            {/* Players */}
            {showPlayers && (
              <section className="pb-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
                    Players <span className="ml-1 text-pb-faintest">{selectedPlayers.length}/{tmpl.maxPlayers}</span>
                  </h2>
                  <button
                    onClick={() => setSwapNames(s => !s)}
                    className={`font-mono text-[9px] tracking-wide2 px-2 py-1 rounded border pb-hairline transition-colors ${swapNames ? 'text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}
                    style={swapNames ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                  >↕ SWAP</button>
                </div>
                {selectedPlayers.length > 0 && (
                  <div className="flex flex-col gap-1.5 mb-3">
                    {selectedPlayers.map((sp, idx) => (
                      <SelectedPlayerRow key={sp.player.id} sp={sp} idx={idx}
                        isFirst={idx === 0} isLast={idx === selectedPlayers.length - 1}
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
                    <input value={playerSearch} onChange={e => setPlayerSearch(e.target.value)} placeholder="Search players..."
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest mb-2" />
                    <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5">
                      {filteredPlayers.filter(p => !selectedPlayers.find(sp => sp.player.id === p.id)).map(p => (
                        <button key={p.id} onClick={() => addPlayer(p)}
                          className="text-left px-3 py-1.5 rounded hover:bg-pb-surface2 text-sm text-pb-text flex items-center gap-2 group">
                          {p.photo_url && <img src={`${BASE_URL}/images/players/${p.id}/photo`} alt="" className="w-6 h-6 rounded-full object-cover object-top" />}
                          <span className="flex-1 truncate">{p.display_name || p.name}</span>
                          {p.player_role && <span className="font-mono text-[9px] text-pb-faintest">{p.player_role}</span>}
                          <span className="text-pb-faintest group-hover:text-pb-accent text-xs">+</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </section>
            )}

            {/* Hero Image */}
            {showHeroImage && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Hero Image</h2>
                <p className="text-[11px] text-pb-faint mb-3">Transparent PNG recommended for best results.</p>
                {['T1', 'T3', 'T6'].includes(templateId) && selectedPlayers.length > 0 && (
                  <div className="mb-3">
                    <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">Hero Player</label>
                    <select
                      value={heroPlayerId}
                      onChange={e => setHeroPlayerId(e.target.value)}
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text"
                    >
                      <option value="">Auto — captain, else 1st in order</option>
                      {selectedPlayers.map(sp => (
                        <option key={sp.player.id} value={sp.player.id}>
                          {(sp.player.display_name || sp.player.name)}{sp.player.photo_url ? '' : ' · no photo'}
                        </option>
                      ))}
                    </select>
                    <p className="text-[11px] text-pb-faintest mt-1">
                      {heroImage.blobUrl ? 'Uploaded Hero Image below overrides this.' : 'Pick whose photo fills the hero slot. Upload below to override.'}
                    </p>
                  </div>
                )}
                {['C1', 'C3'].includes(templateId) && (
                  <div className="flex gap-2 mb-3">
                    <button
                      onClick={() => setHeroMode('player')}
                      className={`flex-1 py-1.5 rounded border text-xs font-mono transition-colors ${heroMode === 'player' ? '' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
                      style={heroMode === 'player' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                    >Player Picture</button>
                    <button
                      onClick={() => setHeroMode('hero')}
                      className={`flex-1 py-1.5 rounded border text-xs font-mono transition-colors ${heroMode === 'hero' ? '' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
                      style={heroMode === 'hero' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                    >Hero Image</button>
                  </div>
                )}
                {(!['C1', 'C3'].includes(templateId) || heroMode === 'hero') && (
                  <div className="flex flex-col gap-3">
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <span className="px-3 py-2 rounded border pb-hairline text-xs font-mono text-pb-faint group-hover:bg-pb-surface2 transition-colors">Choose File</span>
                      <span className="text-[11px] text-pb-faint truncate">{heroImage.blobUrl ? 'Image selected' : 'No file chosen'}</span>
                      <input type="file" accept="image/png,image/webp,image/jpeg" onChange={handleHeroFile} className="sr-only" />
                    </label>
                    {heroImage.blobUrl && (
                      <div className="flex items-start gap-3">
                        <img src={heroImage.blobUrl} alt="Hero preview" className="w-16 h-16 object-contain rounded bg-pb-surface2" />
                        <div className="flex flex-col gap-2 flex-1">
                          <button
                            onClick={() => setEditor({ key: 'hero', source: heroImage.blobUrl })}
                            className="text-xs font-mono text-pb-faint hover:text-pb-text text-left"
                          >
                            ✎ Edit (crop / remove background)
                          </button>
                          <button onClick={() => { URL.revokeObjectURL(heroImage.blobUrl); setHeroImage({ blobUrl: null }) }}
                            className="text-xs text-pb-faintest hover:text-red-400 font-mono text-left">Remove image</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* T7 Milestone */}
            {templateId === 'T7' && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Milestone Data</h2>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Value (big number)"><TextInput value={milestone.value} onChange={v => setMilestone(m => ({ ...m, value: v }))} placeholder="200" /></Field>
                  <Field label="Unit"><TextInput value={milestone.unit} onChange={v => setMilestone(m => ({ ...m, unit: v }))} placeholder="GAMES" /></Field>
                  <div className="col-span-2"><Field label="Reason (eyebrow)"><TextInput value={milestone.reason} onChange={v => setMilestone(m => ({ ...m, reason: v }))} placeholder="200TH GAME FOR THE CLUB" /></Field></div>
                  <div className="col-span-2"><Field label="Detail line"><TextInput value={milestone.detail} onChange={v => setMilestone(m => ({ ...m, detail: v }))} placeholder="15 seasons · 4,872 runs" /></Field></div>
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

            {/* C3 Player Spotlight */}
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
                      <StatRow key={i} stat={s}
                        onChange={v => setMotm(m => { const next = [...m.stats]; next[i] = v; return { ...m, stats: next } })}
                        onRemove={() => setMotm(m => ({ ...m, stats: m.stats.filter((_, j) => j !== i) }))} />
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

            {/* Final Score — C4 + the single-match result layouts (RS*) */}
            {activeTab === 'result' && (
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
                  <Field label="Margin"><TextInput value={result.margin} onChange={v => setResult(r => ({ ...r, margin: v }))} placeholder="BY 4 WICKETS" /></Field>
                  <Field label="Our Score"><TextInput value={result.teamScore} onChange={v => setResult(r => ({ ...r, teamScore: v }))} placeholder="6/188" /></Field>
                  <Field label="Their Score"><TextInput value={result.oppScore} onChange={v => setResult(r => ({ ...r, oppScore: v }))} placeholder="184" /></Field>
                  {tmpl.kind === 'singleresult' && <>
                    <Field label="Our Overs"><TextInput value={result.teamOvers} onChange={v => setResult(r => ({ ...r, teamOvers: v }))} placeholder="38.2" /></Field>
                    <Field label="Their Overs"><TextInput value={result.oppOvers} onChange={v => setResult(r => ({ ...r, oppOvers: v }))} placeholder="49.1" /></Field>
                  </>}
                  <div className={tmpl.kind === 'singleresult' ? '' : 'col-span-2'}>
                    <Field label="MOTM Surname"><TextInput value={result.motmLast} onChange={v => setResult(r => ({ ...r, motmLast: v }))} placeholder="OKAFOR" /></Field>
                  </div>
                  {tmpl.kind === 'singleresult' && <>
                    <Field label="MOTM First"><TextInput value={result.motmFirst} onChange={v => setResult(r => ({ ...r, motmFirst: v }))} placeholder="JAMES" /></Field>
                    <Field label="MOTM Role"><TextInput value={result.motmRole} onChange={v => setResult(r => ({ ...r, motmRole: v }))} placeholder="ALL-ROUNDER" /></Field>
                    <Field label="MOTM Batting"><TextInput value={result.motmBat} onChange={v => setResult(r => ({ ...r, motmBat: v }))} placeholder="94* (71)" /></Field>
                    <Field label="MOTM Bowling"><TextInput value={result.motmBowl} onChange={v => setResult(r => ({ ...r, motmBowl: v }))} placeholder="2/24" /></Field>
                  </>}
                </div>
                {[
                  { side: 'team', label: `Our Batters`, type: 'topBatters' },
                  { side: 'team', label: `Our Bowlers`, type: 'topBowlers' },
                  { side: 'opponent', label: `Their Batters`, type: 'topBatters' },
                  { side: 'opponent', label: `Their Bowlers`, type: 'topBowlers' },
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

            {/* Fixtures roundup data */}
            {activeTab === 'fixtures' && (
              <section className="pb-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Fixtures</h2>
                  <span className="font-mono text-[9px] text-pb-faintest">{fixtures.length} grades</span>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">Round, date &amp; competition come from <strong>Match Info</strong> above.</p>
                <div className="flex flex-col gap-2">
                  {fixtures.map((f, i) => {
                    const set = (patch) => setFixtures(rows => rows.map((r, j) => j === i ? { ...r, ...patch } : r))
                    return (
                      <div key={i} className="rounded border pb-hairline p-2 bg-pb-surface2 flex flex-col gap-1.5">
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 58px 20px' }}>
                          <input value={f.grade} onChange={e => set({ grade: e.target.value })} placeholder="Grade · 1ST XI"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <select value={f.ha} onChange={e => set({ ha: e.target.value })}
                            className="bg-pb-surface border pb-hairline rounded px-1 py-1 text-xs text-pb-text">
                            <option value="H">Home</option><option value="A">Away</option>
                          </select>
                          <button onClick={() => setFixtures(rows => rows.filter((_, j) => j !== i))}
                            className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
                        </div>
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 64px' }}>
                          <input value={f.opp} onChange={e => set({ opp: e.target.value })} placeholder="Opponent name"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
                          <input value={f.oppMono} onChange={e => set({ oppMono: e.target.value.toUpperCase().slice(0, 3) })} placeholder="SUB"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono text-center placeholder:text-pb-faintest" />
                        </div>
                        <div className="grid grid-cols-2 gap-1.5">
                          <input value={f.time} onChange={e => set({ time: e.target.value })} placeholder="12:30 PM"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={f.venue} onChange={e => set({ venue: e.target.value })} placeholder="Venue"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
                        </div>
                      </div>
                    )
                  })}
                  <button onClick={() => setFixtures(rows => [...rows, { grade: '', opp: '', oppMono: '', ha: 'H', time: '', venue: '' }])}
                    className="text-left text-xs text-pb-faint hover:text-pb-accent font-mono">+ Add fixture</button>
                </div>
              </section>
            )}

            {/* Results roundup data */}
            {activeTab === 'results' && (
              <section className="pb-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Results</h2>
                  <span className="font-mono text-[9px] text-pb-faintest">{results.length} grades</span>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">Round &amp; date come from <strong>Match Info</strong> above. W/L colour-codes the post.</p>
                <div className="flex flex-col gap-2">
                  {results.map((r, i) => {
                    const set = (patch) => setResults(rows => rows.map((x, j) => j === i ? { ...x, ...patch } : x))
                    return (
                      <div key={i} className="rounded border pb-hairline p-2 bg-pb-surface2 flex flex-col gap-1.5">
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 72px 20px' }}>
                          <input value={r.grade} onChange={e => set({ grade: e.target.value })} placeholder="Grade · 1ST XI"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <select value={r.outcome} onChange={e => set({ outcome: e.target.value })}
                            className="bg-pb-surface border pb-hairline rounded px-1 py-1 text-xs text-pb-text">
                            <option value="W">Won</option><option value="L">Lost</option><option value="T">Tie/NR</option>
                          </select>
                          <button onClick={() => setResults(rows => rows.filter((_, j) => j !== i))}
                            className="text-pb-faintest hover:text-red-400 text-xs">✕</button>
                        </div>
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 64px' }}>
                          <input value={r.opp} onChange={e => set({ opp: e.target.value })} placeholder="Opponent name"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
                          <input value={r.oppMono} onChange={e => set({ oppMono: e.target.value.toUpperCase().slice(0, 3) })} placeholder="SUB"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono text-center placeholder:text-pb-faintest" />
                        </div>
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 1fr 1.2fr' }}>
                          <input value={r.us} onChange={e => set({ us: e.target.value })} placeholder="Us 6/188"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={r.them} onChange={e => set({ them: e.target.value })} placeholder="Them 184"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={r.margin} onChange={e => set({ margin: e.target.value })} placeholder="BY 4 WICKETS"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                        </div>
                      </div>
                    )
                  })}
                  <button onClick={() => setResults(rows => [...rows, { grade: '', opp: '', oppMono: '', us: '', them: '', outcome: 'W', margin: '' }])}
                    className="text-left text-xs text-pb-faint hover:text-pb-accent font-mono">+ Add result</button>
                </div>
              </section>
            )}

            {/* Scorecard data */}
            {isScorecard && (
              <section className="pb-card p-4">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Scorecard Data</h2>

                {/* PlayCricket URL import */}
                <div className="mb-4 p-3 rounded border pb-hairline bg-pb-surface2">
                  <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-2">Auto-fill from PlayCricket</p>
                  <div className="flex gap-2">
                    <input type="text" value={scUrlInput} onChange={e => { setScUrlInput(e.target.value); setScUrlStatus(null) }}
                      placeholder="https://play.cricket.com.au/match/37af9ea5-..."
                      className="flex-1 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono"
                      onKeyDown={e => e.key === 'Enter' && handleScUrlImport()} />
                    <button onClick={handleScUrlImport} disabled={scUrlStatus === 'loading'}
                      className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50"
                      style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                      {scUrlStatus === 'loading' ? 'Loading…' : 'Import'}
                    </button>
                  </div>
                  {scUrlStatus && scUrlStatus !== 'loading' && (
                    <p className={`font-mono text-[9px] mt-1.5 ${scUrlStatus === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                      {scUrlStatus === 'ok' ? '✓ Scorecard loaded' : `✗ ${scUrlStatus}`}
                    </p>
                  )}
                </div>

                {/* Meta fields */}
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <Field label="Result"><TextInput value={scorecardMatch.meta.result} onChange={v => patchScMeta({ result: v })} placeholder="HOME WON BY 6 WICKETS" /></Field>
                  <Field label="Competition"><TextInput value={scorecardMatch.meta.competition} onChange={v => patchScMeta({ competition: v })} placeholder="PREMIER GRADE" /></Field>
                  <Field label="Round"><TextInput value={scorecardMatch.meta.round} onChange={v => patchScMeta({ round: v })} placeholder="ROUND 7" /></Field>
                  <Field label="Format"><TextInput value={scorecardMatch.meta.format} onChange={v => patchScMeta({ format: v })} placeholder="T20" /></Field>
                  <Field label="Overs"><TextInput value={String(scorecardMatch.meta.overs)} onChange={v => patchScMeta({ overs: Number(v) || 20 })} placeholder="20" /></Field>
                  <Field label="Date"><TextInput value={scorecardMatch.meta.date} onChange={v => patchScMeta({ date: v })} placeholder="SAT 1 JAN" /></Field>
                  <div className="col-span-2"><Field label="Venue"><TextInput value={scorecardMatch.meta.venue} onChange={v => patchScMeta({ venue: v })} placeholder="Home Ground" /></Field></div>
                  <div className="col-span-2"><Field label="Toss"><TextInput value={scorecardMatch.meta.toss} onChange={v => patchScMeta({ toss: v })} placeholder="HOME WON THE TOSS · ELECTED TO BAT" /></Field></div>
                  <div className="col-span-2"><Field label="Series"><TextInput value={scorecardMatch.meta.series} onChange={v => patchScMeta({ series: v })} placeholder="SEASON 2025/26" /></Field></div>
                  <Field label="MOTM First"><TextInput value={scorecardMatch.meta.motm.first} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, first: v } })} placeholder="Player" /></Field>
                  <Field label="MOTM Last"><TextInput value={scorecardMatch.meta.motm.last} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, last: v } })} placeholder="NAME" /></Field>
                  <div className="col-span-2"><Field label="MOTM Line"><TextInput value={scorecardMatch.meta.motm.line} onChange={v => patchScMeta({ motm: { ...scorecardMatch.meta.motm, line: v } })} placeholder="87 (54) · 2/22" /></Field></div>
                  <div className="col-span-2">
                    <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mb-1">Sponsor Logos</p>
                    {adminSponsors.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-2">
                        {adminSponsors.map(sp => {
                          const logoUrl = `${BASE_URL}/images/sponsors/${sp.id}/logo`
                          return (
                            <button key={sp.id} title={sp.name}
                              onClick={() => {
                                const slot = scorecardMatch.meta.sponsors[0]?.url ? 1 : 0
                                setScorecardMatch(m => ({ ...m, meta: { ...m.meta, sponsors: m.meta.sponsors.map((s, i) => i === slot ? { url: logoUrl, name: sp.name } : s) } }))
                                setSponsorFiles(prev => { const next = [...prev]; next[slot] = logoUrl; return next })
                              }}
                              className="flex items-center gap-1.5 px-2 py-1 rounded border pb-hairline hover:bg-pb-surface2 text-[10px] font-mono text-pb-faint"
                            >
                              <img src={logoUrl} alt={sp.name} className="h-5 object-contain" onError={e => e.target.style.display='none'} />
                              {sp.name}
                            </button>
                          )
                        })}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      {[0, 1].map(i => {
                        const currentUrl = scorecardMatch.meta.sponsors[i]?.url
                        return (
                          <div key={i} className="flex flex-col gap-1">
                            <label className="flex items-center gap-2 px-2 py-1.5 rounded border pb-hairline cursor-pointer hover:bg-pb-surface2 text-xs font-mono text-pb-faint">
                              <span>{currentUrl ? '✓ Set' : `Upload ${i + 1}`}</span>
                              <input type="file" accept="image/*" className="hidden" onChange={e => handleSponsorFile(i, e.target.files?.[0])} />
                            </label>
                            {currentUrl && (
                              <div className="flex items-center gap-2">
                                <img src={currentUrl} alt="" className="h-8 object-contain rounded border pb-hairline flex-1 min-w-0" onError={e => e.target.style.opacity='0.3'} />
                                <button
                                  onClick={() => setEditor({ key: `sponsor-${i}`, source: currentUrl, sponsorIdx: i, sponsorName: scorecardMatch.meta.sponsors[i]?.name || '' })}
                                  className="shrink-0 text-[10px] font-mono text-pb-faint hover:text-pb-text whitespace-nowrap"
                                >
                                  ✎ Edit
                                </button>
                                <button
                                  onClick={() => {
                                    setSponsorFiles(prev => { const next = [...prev]; next[i] = null; return next })
                                    setScorecardMatch(m => ({ ...m, meta: { ...m.meta, sponsors: m.meta.sponsors.map((s, j) => j === i ? { url: null, name: '' } : s) } }))
                                  }}
                                  className="shrink-0 text-[10px] text-pb-faintest hover:text-red-400"
                                >✕</button>
                              </div>
                            )}
                          </div>
                        )
                      })}
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
                        <div className="relative">
                          <label className="block font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase mb-1">Search Club (CA)</label>
                          <div ref={scTeamRefBySide[side]} className="relative">
                            <input value={scTeamSearch[side]} onChange={e => handleScTeamSearch(side, e.target.value)} placeholder="Type club name…"
                              className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-xs text-pb-text placeholder:text-pb-faintest" />
                            {scTeamSearching[side] && <span className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[9px] text-pb-faintest animate-pulse">SEARCHING…</span>}
                          </div>
                          <Dropdown
                            anchorRef={scTeamRefBySide[side]}
                            open={scTeamResults[side].length > 0}
                            onClose={() => setScTeamResults(r => ({ ...r, [side]: [] }))}
                            maxHeight={192}
                            className="bg-pb-surface border pb-hairline rounded shadow-lg"
                          >
                            {scTeamResults[side].map((org, i) => (
                              <button key={org.id || i} onClick={() => selectScTeam(side, org)}
                                className="w-full text-left px-3 py-1.5 hover:bg-pb-surface2 flex items-center gap-2 border-b pb-hairline last:border-0">
                                {(org.logoURL || org.logo_url) && <img src={org.logoURL || org.logo_url} alt="" className="w-6 h-6 rounded object-contain bg-pb-surface2 shrink-0" />}
                                <span className="text-xs text-pb-text flex-1 truncate">{org.name}</span>
                                {org.shortName && <span className="font-mono text-[9px] text-pb-faintest">{org.shortName}</span>}
                              </button>
                            ))}
                          </Dropdown>
                        </div>
                        <div className="grid grid-cols-4 gap-2">
                          <div className="col-span-2"><Field label="Team Name"><TextInput value={t.name} onChange={v => patchScTeam(side, { name: v, monogram: v.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 3) })} placeholder="HOME TEAM" /></Field></div>
                          <Field label="Short"><TextInput value={t.short} onChange={v => patchScTeam(side, { short: v.toUpperCase().slice(0, 4), monogram: v.toUpperCase().slice(0, 3) })} placeholder="HOM" /></Field>
                          <Field label="Colour"><input type="color" value={t.color} onChange={e => patchScTeam(side, { color: e.target.value })} className="w-full h-[34px] rounded cursor-pointer border-0 bg-transparent p-0" /></Field>
                          <Field label="Header Ink"><input type="color" value={t.headerInk || '#0a0a0a'} onChange={e => patchScTeam(side, { headerInk: e.target.value })} className="w-full h-[34px] rounded cursor-pointer border-0 bg-transparent p-0" /></Field>
                          <Field label="Total"><TextInput value={t.total} onChange={v => patchScTeam(side, { total: v })} placeholder="182" /></Field>
                          <Field label="Wkts"><TextInput value={String(t.wickets)} onChange={v => patchScTeam(side, { wickets: Number(v) || 0 })} placeholder="7" /></Field>
                          <Field label="Overs"><TextInput value={t.overs} onChange={v => patchScTeam(side, { overs: v })} placeholder="20.0" /></Field>
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

                        <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mt-1">Batting</p>
                        <div className="flex flex-col gap-1 overflow-x-auto">
                          <div className="grid gap-1 font-mono text-[8px] text-pb-faintest px-1 min-w-[420px]" style={{ gridTemplateColumns: '14px 1fr 1fr 32px 32px 22px 22px 48px 60px 14px' }}>
                            <span>#</span><span>First</span><span>Last</span><span>Runs</span><span>Balls</span><span>4s</span><span>6s</span><span>Status</span><span>Dismissal</span><span></span>
                          </div>
                          {t.batting.map((p, i) => (
                            <div key={i} className="grid gap-1 items-center min-w-[420px]" style={{ gridTemplateColumns: '14px 1fr 1fr 32px 32px 22px 22px 48px 60px 14px' }}>
                              <span className="font-mono text-[9px] text-pb-faintest text-center">{p.num}</span>
                              <input value={p.first} onChange={e => updateBatRow(side, i, { first: e.target.value })} placeholder="First" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text" />
                              <input value={p.last} onChange={e => updateBatRow(side, i, { last: e.target.value })} placeholder="LAST" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text font-mono uppercase" />
                              <input type="number" min="0" value={p.r} onChange={e => updateBatRow(side, i, { r: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.b} onChange={e => updateBatRow(side, i, { b: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.fours} onChange={e => updateBatRow(side, i, { fours: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <input type="number" min="0" value={p.sixes} onChange={e => updateBatRow(side, i, { sixes: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" disabled={p.didNotBat} />
                              <div className="flex gap-0.5">
                                <button onClick={() => updateBatRow(side, i, { notOut: !p.notOut, didNotBat: false })}
                                  className={`font-mono text-[8px] px-1 py-0.5 rounded border pb-hairline ${p.notOut ? '' : 'text-pb-faintest'}`}
                                  style={p.notOut ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}>NO</button>
                                <button onClick={() => updateBatRow(side, i, { didNotBat: !p.didNotBat, notOut: false })}
                                  className={`font-mono text-[8px] px-1 py-0.5 rounded border pb-hairline ${p.didNotBat ? '' : 'text-pb-faintest'}`}
                                  style={p.didNotBat ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}>DNB</button>
                              </div>
                              <input value={p.didNotBat || p.notOut ? '' : (p.out || '')}
                                onChange={e => updateBatRow(side, i, { out: e.target.value })}
                                placeholder={p.didNotBat ? '—' : p.notOut ? '—' : 'c Smith b J…'}
                                disabled={p.didNotBat || p.notOut}
                                className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-[10px] text-pb-text disabled:opacity-30" />
                              <button onClick={() => {
                                const next = t.batting.filter((_, j) => j !== i).map((r, j) => ({ ...r, num: j + 1 }))
                                patchScTeam(side, { batting: next })
                              }} className="text-pb-faintest hover:text-red-400 text-[10px] leading-none text-center">✕</button>
                            </div>
                          ))}
                          <button onClick={() => patchScTeam(side, { batting: [...t.batting, DEFAULT_BATTING_ROW(t.batting.length + 1)] })}
                            className="text-xs text-pb-faint hover:text-pb-accent font-mono text-left">+ Add batter</button>
                        </div>

                        <p className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mt-2">Bowling</p>
                        <div className="flex flex-col gap-0.5 overflow-x-auto">
                          <div className="grid gap-1 font-mono text-[8px] text-pb-faintest px-1 min-w-[340px]" style={{ gridTemplateColumns: '1fr 1fr 36px 28px 36px 28px 16px' }}>
                            <span>First</span><span>Last</span><span>Ovrs</span><span>M</span><span>Runs</span><span>Wkts</span><span></span>
                          </div>
                          {t.bowling.map((p, i) => (
                            <div key={i} className="grid gap-1 items-center min-w-[340px]" style={{ gridTemplateColumns: '1fr 1fr 36px 28px 36px 28px 16px' }}>
                              <input value={p.first} onChange={e => updateBowlRow(side, i, { first: e.target.value })} placeholder="First" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text" />
                              <input value={p.last} onChange={e => updateBowlRow(side, i, { last: e.target.value })} placeholder="LAST" className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-xs text-pb-text font-mono uppercase" />
                              <input type="number" min="0" step="0.1" value={p.o} onChange={e => updateBowlRow(side, i, { o: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.m} onChange={e => updateBowlRow(side, i, { m: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.r} onChange={e => updateBowlRow(side, i, { r: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <input type="number" min="0" value={p.w} onChange={e => updateBowlRow(side, i, { w: +e.target.value })} className="bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text font-mono text-center" />
                              <button onClick={() => patchScTeam(side, { bowling: t.bowling.filter((_, j) => j !== i) })}
                                className="text-pb-faintest hover:text-red-400 text-[10px] leading-none text-center">✕</button>
                            </div>
                          ))}
                          {t.bowling.length < 11 && (
                            <button onClick={() => patchScTeam(side, { bowling: [...t.bowling, DEFAULT_BOWLING_ROW(t.bowling.length)] })}
                              className="text-xs text-pb-faint hover:text-pb-accent font-mono text-left">+ Add bowler</button>
                          )}
                        </div>
                      </div>
                    </details>
                  )
                })}
              </section>
            )}

            {/* Mobile preview (visible on small screens, hidden on xl) */}
            <div className="xl:hidden pb-card p-4">
              <div className="flex items-center justify-between mb-3 gap-2">
                <span className="font-mono text-[10px] text-pb-faint uppercase">{tmpl.id}: {tmpl.name}</span>
                <div className="flex items-center gap-2">
                  {exportError && <span className="text-red-400 text-xs font-mono truncate max-w-[120px]">{exportError}</span>}
                  <button onClick={handleExport} disabled={exporting}
                    className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 disabled:opacity-60"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                    {exporting ? '...' : '↓ PNG'}
                  </button>
                  <button onClick={handleReset} className="px-3 py-1.5 rounded text-xs font-mono border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                    ↺ Reset
                  </button>
                </div>
              </div>
              {(() => {
                const mobileW = Math.min(window.innerWidth - 64, 480)
                const scale = mobileW / W
                return (
                  <div style={{ width: mobileW, height: Math.round(H * scale), overflow: 'hidden', border: '1px solid var(--pb-hairline)', borderRadius: 6, background: '#080808' }}>
                    <div style={{ ...fontStyle, transform: `scale(${scale})`, transformOrigin: 'top left', width: W, height: H, pointerEvents: 'none' }}>
                      <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={themedPalette} headline={headline} {...extraProps} />
                    </div>
                  </div>
                )
              })()}
              <p className="text-pb-faintest text-[10px] font-mono mt-2">{W} × {H} px</p>
            </div>

          </div>{/* end left column */}

          {/* ─── RIGHT: sticky preview (desktop only) ──────────────────────── */}
          <div className="hidden xl:flex flex-1 min-w-0 sticky top-[64px] self-start flex-col gap-3">
            <div className="pb-card p-4">
              <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                <span className="font-mono text-[10px] text-pb-faint uppercase shrink-0">{tmpl.id}: {tmpl.name}</span>
                <div className="flex items-center gap-2 shrink-0">
                  {exportError && <span className="text-red-400 text-[10px] font-mono truncate max-w-[140px]">{exportError}</span>}
                  <button onClick={handleExport} disabled={exporting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono tracking-wide2 transition-colors disabled:opacity-60"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                    {exporting ? 'EXPORTING...' : '↓ DOWNLOAD PNG'}
                  </button>
                  <button onClick={handleReset}
                    className="px-3 py-1.5 rounded text-xs font-mono border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
                    title="Reset all fields for this tab">
                    ↺ Reset
                  </button>
                </div>
              </div>
              {(() => {
                const pw = Math.min(700, W)
                const scale = pw / W
                const ph = Math.round(H * scale)
                return (
                  <>
                    <div style={{ width: pw, height: ph, overflow: 'hidden', border: '1px solid var(--pb-hairline)', borderRadius: 6, background: '#080808' }}>
                      <div style={{ ...fontStyle, transform: `scale(${scale})`, transformOrigin: 'top left', width: W, height: H, pointerEvents: 'none' }}>
                        <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={themedPalette} headline={headline} {...extraProps} />
                      </div>
                    </div>
                    <p className="text-pb-faintest text-[10px] font-mono mt-2">
                      {W} × {H} px · shown at {Math.round(scale * 100)}%
                    </p>
                  </>
                )
              })()}
            </div>
          </div>

        </div>
      </div>

      {/* Hidden full-size render for export */}
      <div style={{ position: 'absolute', left: '-9999px', top: 0, pointerEvents: 'none', zIndex: -1 }}>
        <div ref={renderRef} style={{ ...fontStyle, width: W, height: H }}>
          <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={themedPalette} headline={headline} {...extraProps} />
        </div>
      </div>

      <ImageEditorModal
        open={!!editor}
        source={editor?.source}
        title={editor?.key === 'hero' ? 'Edit Hero Image' : 'Edit Sponsor Logo'}
        aspect={null}
        outputType="image/png"
        outputName={editor?.key === 'hero' ? 'hero.png' : 'sponsor.png'}
        onCancel={() => setEditor(null)}
        onApply={async (file) => {
          const e = editor
          setEditor(null)
          if (!e) return
          if (e.key === 'hero') {
            if (heroImage.blobUrl) URL.revokeObjectURL(heroImage.blobUrl)
            setHeroImage({ blobUrl: URL.createObjectURL(file) })
          } else if (typeof e.sponsorIdx === 'number') {
            applySponsorBlob(e.sponsorIdx, file, e.sponsorName)
          }
        }}
      />
    </BetterSocialsLayout>
  )
}
