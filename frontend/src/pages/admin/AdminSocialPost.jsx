import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ImageEditorModal from '../../components/ImageEditorModal'
import Dropdown from '../../components/Dropdown'
import ModuleLockup from '../../components/ModuleLockup'
import { moduleBrand } from '../../lib/moduleBrand'
import { Icon } from './betterselect/ui'
import PostEditorShell from '../../components/admin/socialpost/PostEditorShell'
import SelectionInspector from '../../components/admin/socialpost/SelectionInspector'
import MediaLibraryPanel from '../../components/admin/socialpost/MediaLibraryPanel'
import { TOOL_TITLE } from '../../components/admin/socialpost/ToolRail'
import StartScreen from '../../components/admin/socialpost/StartScreen'
import MobileQuickPost from '../../components/admin/socialpost/MobileQuickPost'
import TextPanel from '../../components/admin/socialpost/panels/TextPanel'
import ShapesPanel from '../../components/admin/socialpost/panels/ShapesPanel'
import ClubDataPanel from '../../components/admin/socialpost/panels/ClubDataPanel'
import LayersPanel from '../../components/admin/socialpost/panels/LayersPanel'
import { api } from '../../lib/api'
import {
  T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder,
  T5_Brutalist, T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer,
  C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore,
  SC1_Broadcast, SC2_Brutalist, SC3_Dashboard,
  PALETTES, orgAccent, orgToPalette,
} from '../../social/cricket-templates'
import {
  FixtureList, FixtureHype, FixtureGrid, FixtureBoard, FixtureHeadline, FixtureSchedule,
  ResultMarginHero, ResultBroadcast, ResultVersusColumns, ResultStar, ResultInningsBars, ResultTicket,
  ResultsList, ResultsListLeaders, ResultsScoreboard, ResultsRecord, ResultsHeadline, ResultsBoard, ResultsSplit,
  DEFAULT_FIXTURES, DEFAULT_RESULTS,
} from '../../social/round-templates'
import { exportNodeToPng } from '../../social/exportImage'
import { SocialBackground, SocialBackgroundDefs, SOCIAL_BACKGROUNDS, DEFAULT_COLORS as BG_DEFAULT_COLORS } from '../../social/SocialBackgrounds'
import { EVENT_TEMPLATES, EVENT_PRESETS, DEFAULT_EVENT, resolveMotif, eventPaletteFor } from '../../social/event-templates'
import EventPostEditor from '../../components/admin/EventPostEditor'
import { BlankCanvas, newBlankItem, defaultBlankItems } from '../../social/blank-template'
import { useBlankLayer } from '../../social/useBlankLayer'
import { useEditHistory } from '../../social/useEditHistory'
import { usePages } from '../../social/usePages'
import PageStrip from '../../components/admin/socialpost/PageStrip'
import { templateToBlocks, CUSTOM_EDITABLE } from '../../social/templateToBlocks'

// Stable initial value for the (empty) Custom Edit overlay layer.
const EMPTY_LAYER = () => []

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
  { id: 'RR7', name: 'Wrap + Leaders', component: ResultsListLeaders, desc: 'Win/loss list + our top scorers & wicket takers', maxPlayers: 0, kind: 'results', hasLeaders: true },
  { id: 'RR2', name: 'W/L Scoreboard', component: ResultsScoreboard,  desc: '2×3 result cards',                maxPlayers: 0, kind: 'results' },
  { id: 'RR3', name: 'Record Strip',   component: ResultsRecord,      desc: 'W–L record summary',              maxPlayers: 0, kind: 'results' },
  { id: 'RR4', name: 'Headline',       component: ResultsHeadline,    desc: 'Feature result + others',         maxPlayers: 0, kind: 'results' },
  { id: 'RR5', name: 'Board',          component: ResultsBoard,       desc: 'Results table',                   maxPlayers: 0, kind: 'results' },
  { id: 'RR6', name: 'Win/Loss Split', component: ResultsSplit,       desc: 'Wins vs losses columns',          maxPlayers: 0, kind: 'results' },
  { id: 'SC1', name: 'Broadcast',      component: SC1_Broadcast,      desc: 'TV-style full scorecard',         maxPlayers: 0, isScorecard: true },
  { id: 'SC2', name: 'Brutalist',      component: SC2_Brutalist,      desc: 'Bold type, heavy rules',          maxPlayers: 0, isScorecard: true },
  { id: 'SC3', name: 'Dashboard',      component: SC3_Dashboard,      desc: 'Soft cards, app-style',           maxPlayers: 0, isScorecard: true },
  // Club-event / announcement posters — own "Events" tab, surface + photo flags
  // come from the event registry.
  ...EVENT_TEMPLATES.map((t) => ({ id: t.id, name: t.name, component: t.component, desc: t.desc, maxPlayers: 0, kind: 'event', surface: t.surface, photo: t.photo })),
  // Freeform WYSIWYG canvas — add/move/resize your own text & images.
  { id: 'BL1', name: 'Blank Canvas', component: BlankCanvas, desc: 'Freeform — add your own text & images', maxPlayers: 0, kind: 'blank' },
]

const TAB_MAP = {
  T1: 'lineup', T2: 'lineup', T3: 'lineup', T4: 'lineup', T5: 'lineup',
  T6: 'lineup', T7: 'lineup', T8: 'lineup', T9: 'lineup',
  FX1: 'fixtures', FX2: 'fixtures', FX3: 'fixtures', FX4: 'fixtures', FX5: 'fixtures', FX6: 'fixtures',
  C1: 'announcement', C2: 'toss', C3: 'motm',
  C4: 'result', RS1: 'result', RS2: 'result', RS3: 'result', RS4: 'result', RS5: 'result', RS6: 'result',
  RR1: 'results', RR2: 'results', RR3: 'results', RR4: 'results', RR5: 'results', RR6: 'results', RR7: 'results',
  SC1: 'scorecard', SC2: 'scorecard', SC3: 'scorecard',
  EV1: 'events', EV2: 'events', EV3: 'events', EV4: 'events', EV5: 'events', EV6: 'events',
  EV7: 'events', EV8: 'events', EV9: 'events', EV10: 'events', EV11: 'events',
  BL1: 'blank',
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
  { key: 'events',       label: 'Events' },
  { key: 'blank',        label: 'Blank' },
]
const TAB_FIRST = {
  lineup: 'T1', fixtures: 'FX1', announcement: 'C1', toss: 'C2', motm: 'C3',
  result: 'C4', results: 'RR1', scorecard: 'SC1', events: 'EV1', blank: 'BL1',
}

// Grouping for the Background picker (Splatter & Spray / Grit & Grunge /
// Print / Geometric), in first-seen order from SOCIAL_BACKGROUNDS itself so
// the picker stays in sync if that list changes.
const BG_GROUPS = [...new Set(SOCIAL_BACKGROUNDS.map(s => s.group))]
const BG_COLOR_KEYS = [
  { key: 'primary', label: 'Primary' },
  { key: 'secondary', label: 'Secondary' },
  { key: 'tertiary', label: 'Tertiary' },
  { key: 'paper', label: 'Paper' },
  { key: 'ink', label: 'Ink' },
]

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
// BACKGROUND COLOUR HELPERS
// ─────────────────────────────────────────────────────────────────────────────
// SocialBackgrounds' variants share one 5-key colour set (primary/secondary/
// tertiary/paper/ink) regardless of which of the 18 they are — this derives
// a sensible default from the post's own palette (which only has one accent),
// generating a "tertiary" highlight by rotating that accent's hue.
function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0
  const l = (max + min) / 2
  const d = max - min
  if (d !== 0) {
    s = d / (1 - Math.abs(2 * l - 1))
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  return [h, s, l]
}
function hslToHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - c / 2
  let r = 0, g = 0, b = 0
  if (h < 60) [r, g, b] = [c, x, 0]
  else if (h < 120) [r, g, b] = [x, c, 0]
  else if (h < 180) [r, g, b] = [0, c, x]
  else if (h < 240) [r, g, b] = [0, x, c]
  else if (h < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  const to255 = (v) => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${to255(r)}${to255(g)}${to255(b)}`
}
function rotateHue(hex, deg) {
  try {
    const [h, s, l] = hexToHsl(hex)
    return hslToHex((h + deg + 360) % 360, s, l)
  } catch {
    return hex
  }
}
function paletteToBgColors(pal) {
  return {
    primary: pal.primary,
    secondary: pal.accent,
    tertiary: rotateHue(pal.accent, 35),
    paper: BG_DEFAULT_COLORS.paper,
    ink: pal.ink,
  }
}
// Adds an alpha channel to a plain #rrggbb so a template's own opaque canvas
// fill becomes a translucent "window" onto the SocialBackground graphic
// sitting behind it — the only way to reveal the new backgrounds without
// touching background fills hardcoded across ~40 individual templates.
function withAlpha(hex, alphaHex) {
  return (typeof hex === 'string' && /^#[0-9a-fA-F]{6}$/.test(hex)) ? `${hex}${alphaHex}` : hex
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

// Background-texture picker swatch — renders a live miniature of the actual
// SocialBackground variant so clubs can see what they're picking, not just a
// label. 'none' renders a plain ✕ placeholder (no SocialBackground entry).
const BG_SWATCH_SIZE = 40
function BgStyleSwatch({ entry, colors, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      title={entry.label}
      style={{
        width: BG_SWATCH_SIZE, height: BG_SWATCH_SIZE, borderRadius: 6, cursor: 'pointer', overflow: 'hidden', position: 'relative',
        background: colors.primary, border: `2px solid ${selected ? colors.secondary : 'transparent'}`, flexShrink: 0,
      }}
    >
      {entry.key === 'none' ? (
        <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: colors.ink, opacity: 0.5 }}>✕</span>
      ) : (
        <SocialBackground variant={entry.key} colors={colors} size={BG_SWATCH_SIZE} style={{ position: 'absolute', inset: 0 }} />
      )}
    </button>
  )
}

// Saved-Design swatch — the combined "look" (colour + background texture) in
// one preview, so picking a saved design is a single click rather than
// separately re-picking a palette, a texture and a font each time.
const DESIGN_SWATCH_SIZE = 44
function DesignSwatch({ design, selected, onClick }) {
  const bgColors = { primary: design.primary, secondary: design.accent, tertiary: rotateHue(design.accent, 35), paper: BG_DEFAULT_COLORS.paper, ink: design.ink, ...(design.bgColors || {}) }
  return (
    <button
      onClick={onClick}
      title={`${design.name} — ${SOCIAL_BACKGROUNDS.find(s => s.key === design.bgStyle)?.label || 'Clean'}`}
      style={{
        width: DESIGN_SWATCH_SIZE, height: DESIGN_SWATCH_SIZE, borderRadius: 6, cursor: 'pointer', overflow: 'hidden', position: 'relative',
        background: design.primary, border: `2px solid ${selected ? design.accent : 'transparent'}`, flexShrink: 0,
      }}
    >
      {design.bgStyle && design.bgStyle !== 'none' ? (
        <SocialBackground variant={design.bgStyle} colors={bgColors} size={DESIGN_SWATCH_SIZE} style={{ position: 'absolute', inset: 0 }} />
      ) : (
        <span style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 8, background: design.accent }} />
      )}
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

// Up/down reorder control for roundup rows (fixtures & results).
function RowReorder({ onUp, onDown, isFirst, isLast }) {
  return (
    <div className="flex flex-col gap-0.5 justify-center">
      <button onClick={onUp} disabled={isFirst} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▲</button>
      <button onClick={onDown} disabled={isLast} className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▼</button>
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

// Trim "… Cricket Club" / "… CC" so a searched opponent shows a tidy name on
// the roundup post (the per-row mono + grade carry the detail).
function cleanClubName(n) {
  return (n || '')
    .replace(/\s+(district\s+|junior\s+)?cricket\s+club$/i, '')
    .replace(/\s+c\.?c\.?$/i, '')
    .trim()
}

// "Subiaco Marist Cricket Club" → "Subiaco Marist" (tidy + title-cased for the
// editable opponent field; templates uppercase on render anyway).
function tidyClubName(n) {
  return cleanClubName(n).toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

// '2022-10-01' → 'SAT 1 OCT' (matches the date style used across the templates).
function fmtIsoDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  const DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
  const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`
}

// AU score notation from a parsed scorecard team: '9/287' (wickets/runs) while
// wickets are in hand, plain total once all out.
function scoreString(t) {
  const total = String(t?.total ?? '').trim()
  if (!total) return ''
  const wk = Number(t?.wickets)
  return Number.isFinite(wk) && wk < 10 ? `${wk}/${total}` : total
}

// Distinctive club-name tokens (drops the generic cricket/club words) used to
// tell "our" innings from the opponent's on an imported scorecard.
function clubTokens(name) {
  return (name || '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 2 && !['cricket', 'club', 'the', 'district', 'junior', 'colts'].includes(w))
}

// Top 3 batters (most runs, fewer balls breaks ties), shaped for a performer row.
// Name uses the scorecard's "F. SURNAME" short form (consistent across both
// sides); keeps the participant id so the designer can pull a profile photo.
function topBatters(t) {
  return [...(t?.batting || [])]
    .filter((b) => !b.didNotBat && (Number(b.r) > 0 || Number(b.b) > 0))
    .sort((a, b) => (Number(b.r) - Number(a.r)) || (Number(a.b) - Number(b.b)))
    .slice(0, 3)
    .map((b) => ({
      last: b.short || b.last || b.first || '',
      line: `${b.r}${b.notOut ? '*' : ''} (${b.b})`,
      pid: b.pid || null,
      first: b.first || '',
    }))
}

// Sensible grade ordering for roundup posts: senior numbered grades first
// (1st, 2nd, 3rd…), then one-day/limited grades, then the rest — each by number.
const _WORD_NUM = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 }
function gradeSortKey(grade) {
  const s = (grade || '').toUpperCase().trim()
  const ord = s.match(/(\d+)\s*(ST|ND|RD|TH)\b/)
  if (ord) return [0, parseInt(ord[1], 10), s]
  const firstWord = (s.split(/\s+/)[0] || '').toLowerCase()
  if (_WORD_NUM[firstWord] && /GRADE|XI|TEAM/.test(s)) return [0, _WORD_NUM[firstWord], s]
  if (/\bONE\s*DAY\b|\bT20\b|\bLIMITED\b|\bONEDAY\b/.test(s)) {
    const num = s.match(/\d+/)
    return [1, num ? parseInt(num[0], 10) : 99, s]
  }
  const anyNum = s.match(/\d+/)
  return anyNum ? [2, parseInt(anyNum[0], 10), s] : [3, 99, s]
}
function sortByGrade(rows) {
  return [...rows].sort((a, b) => {
    const ka = gradeSortKey(a.grade), kb = gradeSortKey(b.grade)
    return (ka[0] - kb[0]) || (ka[1] - kb[1]) || ka[2].localeCompare(kb[2])
  })
}

// Top 3 bowlers (most wickets, then fewest runs / best economy).
function topBowlers(t) {
  const overs = (o) => parseFloat(String(o || '0').replace(/[^0-9.]/g, '')) || 0
  return [...(t?.bowling || [])]
    .filter((b) => overs(b.o) > 0 || Number(b.w) > 0)
    .sort((a, b) => (Number(b.w) - Number(a.w)) || (Number(a.r) - Number(b.r)) || (Number(a.econ) - Number(b.econ)))
    .slice(0, 3)
    .map((b) => ({
      last: b.short || b.last || b.first || '',
      line: `${b.w}/${b.r}`,
      pid: b.pid || null,
      first: b.first || '',
    }))
}

// Per-row opponent combobox: live club search (api.searchOrgs) with a dropdown,
// while staying a free-text field so a name can still be typed by hand.
function OppRowSearch({ value, onType, onPick, placeholder = 'Opponent (search clubs)…' }) {
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(false)
  const timer = useRef(null)
  const boxRef = useRef(null)
  const search = (q) => {
    onType(q)
    clearTimeout(timer.current)
    if (!q.trim()) { setResults([]); setOpen(false); return }
    timer.current = setTimeout(async () => {
      setSearching(true)
      try { const r = await api.searchOrgs(q); setResults(r || []); setOpen(true) }
      catch { setResults([]) }
      finally { setSearching(false) }
    }, 350)
  }
  return (
    <div ref={boxRef} className="relative">
      <input value={value} onChange={e => search(e.target.value)} placeholder={placeholder}
        className="w-full bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
      {searching && <span className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[8px] text-pb-faintest animate-pulse">…</span>}
      <Dropdown anchorRef={boxRef} open={open && results.length > 0} onClose={() => setOpen(false)} maxHeight={180}
        className="bg-pb-surface border pb-hairline rounded shadow-lg">
        {results.map((org, i) => (
          <button key={org.id || i} onClick={() => { onPick(org); setResults([]); setOpen(false) }}
            className="w-full text-left px-2.5 py-1.5 hover:bg-pb-surface2 flex items-center gap-2 border-b pb-hairline last:border-0">
            {(org.logoURL || org.logo_url) && <img src={org.logoURL || org.logo_url} alt="" className="w-6 h-6 rounded object-contain bg-pb-surface2 shrink-0" />}
            <span className="text-xs text-pb-text flex-1 truncate">{org.name}</span>
            {org.shortName && <span className="font-mono text-[9px] text-pb-faintest">{org.shortName}</span>}
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

// Logo preview / status for a roundup row's pulled opponent crest.
function OppLogoChip({ logo, loading, onClear }) {
  if (!logo && !loading) return null
  return (
    <div className="flex items-center gap-2">
      {loading
        ? <span className="font-mono text-[9px] text-pb-faint animate-pulse">Pulling logo…</span>
        : <>
            <img src={logo} alt="" className="h-7 max-w-[88px] object-contain rounded bg-pb-surface" onError={e => { e.target.style.display = 'none' }} />
            <span className="font-mono text-[9px] text-pb-faint">club logo</span>
            <button onClick={onClear} className="text-pb-faintest hover:text-red-400 text-[10px] ml-auto">✕ logo</button>
          </>}
    </div>
  )
}

// Pull a whole round (all grades) from Play.cricket — the multi-match analogue
// of the scorecard URL import. Lets the operator pick a match-day when the club
// played across more than one date.
function RoundImportBox({ hint, status, dates, idx, rowsKey, onPull, onPick }) {
  const rowsOf = (d) => (d ? d[rowsKey] || [] : [])
  return (
    <div className="mb-4 p-3 rounded border pb-hairline bg-pb-surface2">
      <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-2">Auto-fill from match link</p>
      <div className="flex gap-2 items-center">
        <button onClick={onPull} disabled={status === 'loading'}
          className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50"
          style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
          {status === 'loading' ? 'Loading…' : 'Pull from match link'}
        </button>
        {dates.length > 1 && (
          <select value={idx} onChange={e => onPick(+e.target.value)}
            className="flex-1 min-w-0 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono">
            {dates.map((d, i) => (
              <option key={d.date || i} value={i}>{d.label}{d.round ? ` · ${d.round}` : ''} ({rowsOf(d).length})</option>
            ))}
          </select>
        )}
      </div>
      {status === 'ok' && dates.length > 0 && (
        <p className="font-mono text-[9px] mt-1.5 text-green-400">✓ {rowsOf(dates[idx]).length} loaded · {dates[idx]?.label}</p>
      )}
      {status && status !== 'loading' && status !== 'ok' && (
        <p className="font-mono text-[9px] mt-1.5 text-pb-faint">
          {status === 'empty' ? `No ${hint} found for the current season.` : `✗ ${status}`}
        </p>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
// The untouched Style defaults, in the exact key order the style snapshot is
// built with — used to tell "changed something" from "just visited the page"
// before any style has ever been stored server-side.
const DEFAULT_STYLE_JSON = JSON.stringify({
  palette: 'club', dark: true, font: 'barlow', bg: 'none',
  bg_colors: {}, palettes: [], designs: [], templates: [],
})

export default function AdminSocialPost() {
  const location = useLocation()
  const navigate = useNavigate()
  // Which rail tool's panel is showing. 'content' is the default (the per-type
  // fields most posts start with).
  const [tool, setTool] = useState('content')
  const [typeMenuOpen, setTypeMenuOpen] = useState(false)
  const typeBtnRef = useRef(null)
  // Hidden file input the inspector's "Replace" drives; remembers which image
  // block to fill.
  const blankImgInputRef = useRef(null)
  const pendingImgItem = useRef(null)
  // Club media library (persisted via the social-media API).
  const [mediaAssets, setMediaAssets] = useState([])
  // Below md the editor drops its drag canvas for a guided phone quick-post
  // (unless the user taps "Full editor").
  const [isMobile, setIsMobile] = useState(() => (typeof window !== 'undefined' ? window.innerWidth < 768 : false))
  const [forceFullEditor, setForceFullEditor] = useState(false)
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const [settings, setSettings] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [adminSponsors, setAdminSponsors] = useState([])
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)

  const [templateId, setTemplateId] = useState(() => {
    // A ?type= deep link (from the Start screen or the dashboard) wins over the
    // last-used template so the editor opens on the requested post type.
    const p = new URLSearchParams(window.location.search)
    const t = p.get('type')
    if (t && TAB_FIRST[t]) return TAB_FIRST[t]
    return localStorage.getItem('bs_social_template') || 'T1'
  })
  const [paletteKey, setPaletteKey] = useState(() =>
    localStorage.getItem('bs_social_palette') || 'club'
  )
  const [darkMode, setDarkMode] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_dark') ?? 'true') } catch { return true }
  })
  const [fontKey, setFontKey] = useState(() =>
    localStorage.getItem('bs_social_font') || 'barlow'
  )
  // Background texture, layered over any template — persisted like the other
  // Style controls so a club's preferred "finish" carries between posts.
  const [bgStyle, setBgStyle] = useState(() =>
    localStorage.getItem('bs_social_bg') || 'none'
  )
  // Per-style colour overrides — every SocialBackgrounds variant shares the
  // same 5-key colour set (primary/secondary/tertiary/paper/ink), so this is
  // keyed by bgStyle -> partial colour object, merged over the club-palette
  // default (paletteToBgColors) when not customised.
  const [bgColors, setBgColors] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_bg_colors') || '{}') } catch { return {} }
  })

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

  // Saved Designs — a full "look" (colour palette + background texture + font
  // + dark/light), not just colour. A design's colours piggyback on the same
  // savedPalettes list/lookup as a Custom palette (so paletteKey resolution
  // needs no changes); the extra fields (bgStyle/fontKey/dark) live here,
  // keyed by the same key.
  const [savedDesigns, setSavedDesigns] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_designs') || '[]') } catch { return [] }
  })
  const [saveDesignName, setSaveDesignName] = useState('')
  const [showSaveDesign, setShowSaveDesign] = useState(false)

  // Saved Templates — a reusable starting point saved from ANY tab: the base
  // template + the full Style (palette/bg/font/dark) and, for the Blank Canvas,
  // its whole block layout. Shown in the collapsible Templates section under
  // "Custom". Persists to localStorage and rides the same server socials_style
  // sync as palettes/designs so it survives browser changes and other admins.
  const [savedTemplates, setSavedTemplates] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bs_social_templates') || '[]') } catch { return [] }
  })
  const [saveTemplateName, setSaveTemplateName] = useState('')
  const [templatesOpen, setTemplatesOpen] = useState(true)

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
    winner: 'TEAM', margin: '', grade: '', teamScore: '', oppScore: '', teamOvers: '', oppOvers: '', motmLast: '',
    motmFirst: '', motmRole: '', motmBat: '', motmBowl: '', motmPlayerId: '',
    topBatters: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
    topBowlers: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
  })
  // Result-tab scorecard auto-fill (paste a play.cricket match link → top 3
  // batters/bowlers for both sides, scores, result, MOTM + matched photos).
  const [resUrlInput, setResUrlInput] = useState('')
  const [resUrlStatus, setResUrlStatus] = useState(null)
  // Fixtures / results roundups — one post, all grades. Seeded with sample rows
  // so a fresh tab previews well; users edit/add/remove.
  const [fixtures, setFixtures] = useState(() => DEFAULT_FIXTURES.map((f) => ({ ...f })))
  const [results, setResults] = useState(() => DEFAULT_RESULTS.map((r) => ({ ...r })))
  // Play.cricket round import (the multi-match analogue of the scorecard import).
  const [fxImport, setFxImport] = useState({ status: null, dates: [], idx: 0, season: null })
  const [rrImport, setRrImport] = useState({ status: null, dates: [], idx: 0, season: null })

  // Club-event / announcement posters (Events tab). One editable facts object +
  // a chosen layout, motif glyph and optional background photo.
  const [event, setEvent] = useState(DEFAULT_EVENT)
  const [eventPreset, setEventPreset] = useState('curry')
  const [eventMotifKey, setEventMotifKey] = useState('star')
  const [eventBg, setEventBg] = useState(null)        // object URL or null
  const [eventBgOpacity, setEventBgOpacity] = useState(0.85)

  // Two freeform layers of blocks: `canvas` is the standalone Blank Canvas
  // template; `overlay` is the "Custom Edit" layer that sits on top of any real
  // template. Both share the same block model + editor (via useBlankLayer).
  const canvas = useBlankLayer(defaultBlankItems)
  const overlay = useBlankLayer(EMPTY_LAYER)
  // Undo/redo + action log, one per layer (history is per page/layer).
  const canvasHistory = useEditHistory(canvas)
  const overlayHistory = useEditHistory(overlay)
  // Carousel pages ride the freeform canvas layer (Blank tab). Switching a page
  // starts a fresh undo history — snapshots belong to a single page.
  const pages = usePages(canvas, { onPageChange: () => canvasHistory.clear() })
  const pageRefs = useRef([])
  // Coalesces a burst of same-label edits (e.g. slider ticks) into one snapshot.
  const lastRec = useRef({ label: '', t: 0 })
  // Custom Edit mode: overlay freeform blocks on top of the current (non-blank)
  // template so it can be tweaked and saved as a custom template.
  const [customEdit, setCustomEdit] = useState(false)
  // Career stats for players referenced by "player" data blocks, fetched on
  // demand and cached by id (keeps saved templates live — config only).
  const [playerStatsCache, setPlayerStatsCache] = useState({})

  // Save the current post as a reusable Template (works on every tab). Captures
  // the base template + Style; on the Blank Canvas it also captures the block
  // layout (blob-URL images are dropped since they don't survive a reload).
  const stripBlobImages = (list) => (list || []).map((it) => (it.type === 'image' && typeof it.src === 'string' && it.src.startsWith('blob:') ? { ...it, src: null } : it))
  const saveCurrentTemplate = () => {
    const name = saveTemplateName.trim() || `Template ${savedTemplates.length + 1}`
    const blankTab = templateId === 'BL1'
    const usingOverlay = customEdit && !blankTab
    const srcItems = blankTab ? canvas.items : usingOverlay ? overlay.items : null
    const tpl = {
      key: `tpl_${Date.now().toString(36)}`,
      name, templateId, custom: usingOverlay,
      style: { palette: paletteKey, dark: darkMode, font: fontKey, bg: bgStyle, bgColors, customBg, customAccent },
      blank: srcItems ? stripBlobImages(srcItems) : null,
    }
    const next = [...savedTemplates, tpl]
    setSavedTemplates(next)
    localStorage.setItem('bs_social_templates', JSON.stringify(next))
    setSaveTemplateName('')
  }
  const applyTemplate = (tpl) => {
    if (!tpl) return
    setTemplateId(tpl.templateId)
    const st = tpl.style || {}
    if (st.palette) setPaletteKey(st.palette)
    if (typeof st.dark === 'boolean') setDarkMode(st.dark)
    if (st.font) setFontKey(st.font)
    if (st.bg) setBgStyle(st.bg)
    if (st.bgColors) setBgColors(st.bgColors)
    if (st.customBg) setCustomBg(st.customBg)
    if (st.customAccent) setCustomAccent(st.customAccent)
    const clone = (list) => (list || []).map((it) => ({ ...it }))
    if (tpl.custom) {
      setCustomEdit(true)
      overlay.reset(clone(tpl.blank))
    } else {
      setCustomEdit(false)
      if (tpl.blank) canvas.reset(clone(tpl.blank))
    }
  }
  // Enter/leave Custom Edit for the current real template.
  const startCustomEdit = () => {
    if (!overlay.items.length) overlay.reset([{ ...newBlankItem('brand'), x: 60, y: 60, size: 150 }])
    setCustomEdit(true)
  }
  const stopCustomEdit = () => setCustomEdit(false)
  const deleteTemplate = (key) => {
    const next = savedTemplates.filter((t) => t.key !== key)
    setSavedTemplates(next)
    localStorage.setItem('bs_social_templates', JSON.stringify(next))
  }

  const onPickPreset = (key) => {
    const p = EVENT_PRESETS.find((x) => x.key === key)
    if (!p) return
    setEventPreset(key)
    setEvent({ ...p.event })
    setTemplateId(p.template)
    setEventMotifKey(p.motif)
  }

  const renderRef = useRef(null)

  // localStorage persistence
  useEffect(() => { localStorage.setItem('bs_social_template', templateId) }, [templateId])
  useEffect(() => { localStorage.setItem('bs_social_palette', paletteKey) }, [paletteKey])
  useEffect(() => { localStorage.setItem('bs_social_dark', JSON.stringify(darkMode)) }, [darkMode])
  useEffect(() => { localStorage.setItem('bs_social_font', fontKey) }, [fontKey])
  useEffect(() => { localStorage.setItem('bs_social_bg', bgStyle) }, [bgStyle])
  useEffect(() => { localStorage.setItem('bs_social_bg_colors', JSON.stringify(bgColors)) }, [bgColors])

  // Server persistence of the Style choices (organisations.socials_style,
  // migration 162) — the club's look survives browser changes and second
  // admins, and the Setup Wizard's socials_palette step auto-detects off it.
  // The server copy wins over localStorage on load; saves are debounced and
  // only fire once something differs from the last-synced (or default)
  // style, so merely visiting the page never claims a saved style.
  const styleServerRef = useRef(null) // JSON of the last server-synced style; null = nothing stored yet
  const styleSaveTimer = useRef(null)
  const styleSnapshot = JSON.stringify({
    palette: paletteKey, dark: darkMode, font: fontKey, bg: bgStyle,
    bg_colors: bgColors, palettes: savedPalettes, designs: savedDesigns, templates: savedTemplates,
  })
  useEffect(() => {
    if (!settings) return undefined
    if (styleSnapshot === styleServerRef.current) return undefined
    if (styleServerRef.current === null && styleSnapshot === DEFAULT_STYLE_JSON) return undefined
    clearTimeout(styleSaveTimer.current)
    styleSaveTimer.current = setTimeout(() => {
      api.adminPatchSettings({ socials_style: JSON.parse(styleSnapshot) })
        .then(() => { styleServerRef.current = styleSnapshot })
        .catch(() => { /* best-effort — localStorage still has it */ })
    }, 1200)
    return () => clearTimeout(styleSaveTimer.current)
  }, [styleSnapshot, settings])

  useEffect(() => {
    Promise.all([api.adminGetSettings(), api.adminListPlayers(), api.adminListSponsors()])
      .then(([s, p, sp]) => {
        setSettings(s)
        // Apply the club's stored style (server wins over this browser's
        // localStorage). Normalised into the same snapshot shape the save
        // effect builds, so the ref comparison suppresses a save-back.
        const st = s?.socials_style
        if (st && typeof st === 'object') {
          const applied = {
            palette: typeof st.palette === 'string' ? st.palette : 'club',
            dark: typeof st.dark === 'boolean' ? st.dark : true,
            font: typeof st.font === 'string' ? st.font : 'barlow',
            bg: typeof st.bg === 'string' ? st.bg : 'none',
            bg_colors: st.bg_colors && typeof st.bg_colors === 'object' ? st.bg_colors : {},
            palettes: Array.isArray(st.palettes) ? st.palettes : [],
            designs: Array.isArray(st.designs) ? st.designs : [],
            templates: Array.isArray(st.templates) ? st.templates : [],
          }
          setPaletteKey(applied.palette)
          setDarkMode(applied.dark)
          setFontKey(applied.font)
          setBgStyle(applied.bg)
          setBgColors(applied.bg_colors)
          setSavedPalettes(applied.palettes)
          setSavedDesigns(applied.designs)
          setSavedTemplates(applied.templates)
          styleServerRef.current = JSON.stringify(applied)
        }
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

  // Club media library — reusable uploads shared across posts and admins.
  useEffect(() => { api.listSocialMedia().then((a) => setMediaAssets(a || [])).catch(() => {}) }, [])

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
    if (!m) { setScUrlStatus('Paste a match URL or a match ID'); return }
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

  // Resolve a scorecard participant id (ours, merge-resolved) to the loaded
  // player object so we can pull their profile photo + canonical id.
  const playerForPid = useCallback((pid) => {
    if (!pid) return null
    const key = String(pid).toLowerCase()
    return allPlayers.find((p) => String(p.id).toLowerCase() === key) || null
  }, [allPlayers])

  // Take a parsed scorecard ({meta, home, away}) and fill the whole Result tab:
  // works out which innings is ours, the top 3 batters & bowlers per side, the
  // scores/result/margin, opponent + match meta, and a best-guess POTM (the
  // winning side's top scorer) matched to a profile photo where possible.
  const applyResultScorecard = useCallback((data) => {
    const tokens = clubTokens(settings?.name)
    const matchesClub = (name) => {
      const n = (name || '').toLowerCase()
      return tokens.length > 0 && tokens.some((t) => n.includes(t))
    }
    const usKey = matchesClub(data.home?.name) ? 'home'
      : matchesClub(data.away?.name) ? 'away' : 'home'
    const themKey = usKey === 'home' ? 'away' : 'home'
    const us = data[usKey] || {}
    const them = data[themKey] || {}

    const usRuns = parseInt(String(us.total || '0'), 10) || 0
    const themRuns = parseInt(String(them.total || '0'), 10) || 0
    const resultText = (data.meta?.result || '').toUpperCase()
    const tieRe = /\b(TIE|TIED|DRAW|DREW|NO ?RESULT|ABANDON|WASH)/
    let winner
    if (tieRe.test(resultText) || usRuns === themRuns) winner = 'TIE'
    else winner = usRuns > themRuns ? 'TEAM' : 'OPPONENT'
    const marginMatch = resultText.match(/\bBY\b(.+)$/)
    const margin = marginMatch ? `BY ${marginMatch[1].trim()}` : ''

    // POTM = top run-scorer on the winning side (falls back to ours on a tie).
    const winTeam = winner === 'OPPONENT' ? them : us
    const topBat = [...(winTeam.batting || [])]
      .filter((b) => !b.didNotBat)
      .sort((a, b) => Number(b.r) - Number(a.r))[0]
    const motmPlayer = topBat ? playerForPid(topBat.pid) : null
    const sameBowl = topBat
      ? (winTeam.bowling || []).find((bw) => (bw.pid && topBat.pid && String(bw.pid).toLowerCase() === String(topBat.pid).toLowerCase()) || (bw.last && topBat.last && bw.last === topBat.last))
      : null

    setResult((r) => ({
      ...r,
      winner,
      margin,
      grade: data.meta?.competition || r.grade,
      teamScore: scoreString(us) || r.teamScore,
      oppScore: scoreString(them) || r.oppScore,
      teamOvers: us.overs || r.teamOvers,
      oppOvers: them.overs || r.oppOvers,
      motmFirst: topBat?.first || '',
      motmLast: topBat?.last || '',
      motmBat: topBat ? `${topBat.r}${topBat.notOut ? '*' : ''} (${topBat.b})` : '',
      motmBowl: sameBowl ? `${sameBowl.w}/${sameBowl.r}` : '',
      motmPlayerId: motmPlayer?.id || '',
      topBatters: { team: topBatters(us), opponent: topBatters(them) },
      topBowlers: { team: topBowlers(us), opponent: topBowlers(them) },
    }))
    setMatch((m) => ({
      ...m,
      round: data.meta?.round || m.round,
      venue: data.meta?.venue || m.venue,
      date: fmtIsoDate(data.meta?.date) || m.date,
    }))
    if (them.name) {
      setOpponent((o) => ({
        ...o,
        name: tidyClubName(them.name) || o.name,
        short: them.short || o.short,
        monogram: them.monogram || o.monogram,
        logo: them.logo || o.logo,
      }))
    }
  }, [settings, playerForPid])

  const handleResultImport = async () => {
    const urlOrId = resUrlInput.trim()
    const uuidRe = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    const m = urlOrId.match(uuidRe)
    if (!m) { setResUrlStatus('Paste a match URL or a match ID'); return }
    setResUrlStatus('loading')
    try {
      const data = await api.getSocialScorecard(m[0])
      applyResultScorecard(data)
      setResUrlStatus('ok')
    } catch (e) {
      setResUrlStatus(e?.message || 'Failed to load scorecard')
    }
  }

  // ── Play.cricket fixtures / results round import ────────────────────────────
  const applyFxDate = useCallback((d, season) => {
    if (!d) return
    setFixtures(sortByGrade((d.fixtures || []).map(f => ({ ...f }))))
    setMatch(m => ({ ...m, round: d.round || m.round, date: d.label || m.date, season: season || m.season }))
  }, [])
  const importFixtures = useCallback(async () => {
    setFxImport(s => ({ ...s, status: 'loading' }))
    try {
      const data = await api.getSocialFixtures()
      const dates = data.dates || []
      if (!dates.length) { setFxImport({ status: 'empty', dates: [], idx: 0, season: data.season }); return }
      setFxImport({ status: 'ok', dates, idx: 0, season: data.season })
      applyFxDate(dates[0], data.season)
    } catch (e) { setFxImport({ status: e?.message || 'failed', dates: [], idx: 0, season: null }) }
  }, [applyFxDate])

  const applyRrDate = useCallback((d, season) => {
    if (!d) return
    setResults(sortByGrade((d.results || []).map(r => ({ ...r }))))
    setMatch(m => ({ ...m, round: d.round || m.round, date: d.label || m.date, season: season || m.season }))
  }, [])
  const importResults = useCallback(async () => {
    setRrImport(s => ({ ...s, status: 'loading' }))
    try {
      const data = await api.getSocialResults()
      const dates = data.dates || []
      if (!dates.length) { setRrImport({ status: 'empty', dates: [], idx: 0, season: data.season }); return }
      setRrImport({ status: 'ok', dates, idx: 0, season: data.season })
      applyRrDate(dates[0], data.season)
    } catch (e) { setRrImport({ status: e?.message || 'failed', dates: [], idx: 0, season: null }) }
  }, [applyRrDate])

  // Reorder a roundup row (fixtures / results) up or down.
  const moveRow = (setter, idx, dir) => setter(rows => {
    const j = idx + dir
    if (j < 0 || j >= rows.length) return rows
    const next = [...rows]
    ;[next[idx], next[j]] = [next[j], next[idx]]
    return next
  })

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

  // Best logo URL for a searched club: prefer a matching BetterStats org's
  // (same-origin, so background removal can fetch it), else the CA CDN logo.
  const resolveClubLogo = useCallback(async (org) => {
    let logoUrl = org.logoURL || org.logo_url || null
    try {
      const bsOrgs = await api.listOrgs()
      const matched = bsOrgs.find(o => o.name?.toLowerCase() === org.name?.toLowerCase() || o.id === org.id)
      if (matched?.id) logoUrl = `${BASE_URL}/images/organisations/${matched.id}/logo`
    } catch { /* fall back to CA logo */ }
    return logoUrl
  }, [])

  const selectScTeam = useCallback(async (side, org) => {
    const logoUrl = await resolveClubLogo(org)
    const name = (org.name || org.shortName || '').toUpperCase()
    const short = (org.shortName || deriveShort(name || 'OPP')).toUpperCase().slice(0, 4)
    patchScTeam(side, { name, short, monogram: short.slice(0, 3), logo: logoUrl })
    setScTeamSearch(s => ({ ...s, [side]: '' }))
    setScTeamResults(r => ({ ...r, [side]: [] }))
  }, [resolveClubLogo])

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
    const logoUrl = await resolveClubLogo(org)
    patchOpp({
      name: org.name || org.shortName || '',
      short: org.shortName || deriveShort(org.name || 'OPP'),
      logo: logoUrl,
    })
    setOppSearch('')
    setOppResults([])
  }, [resolveClubLogo])

  // Roundup row opponent pick: fill name + mono immediately, then pull the
  // club's logo (shown as-is in the circular badge spot).
  const pickRowOpp = useCallback(async (kind, idx, org) => {
    const setter = kind === 'fx' ? setFixtures : setResults
    const name = (cleanClubName(org.name) || org.name || org.shortName || '').toUpperCase()
    const mono = (org.shortName || deriveShort(org.name || 'OPP')).toUpperCase().slice(0, 3)
    setter(rows => rows.map((r, j) => j === idx ? { ...r, opp: name, oppMono: mono, oppLogoLoading: true } : r))
    const logo = await resolveClubLogo(org)
    setter(rows => rows.map((r, j) => j === idx ? { ...r, oppLogo: logo, oppLogoLoading: false } : r))
  }, [resolveClubLogo])

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

  // Export to PNG via the shared BetterSocials pipeline (modern-screenshot,
  // with Google Fonts embedded so the display face survives the capture). The
  // render target is already mounted off-screen at full W×H.
  const handleExport = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const W = tmpl.w || (tmpl.isScorecard ? 1920 : 1080)
      const H = tmpl.h || 1080
      const stamp = Date.now()
      // A Blank-tab carousel exports every page as its own PNG (slideN).
      if (tmpl.kind === 'blank' && pages.count > 1) {
        for (let i = 0; i < pages.count; i++) {
          const node = pageRefs.current[i]
          if (!node) continue
          await exportNodeToPng(node, { width: W, height: H, fileName: `betterstats-carousel-${stamp}-slide${i + 1}.png` })
        }
      } else {
        if (!renderRef.current) return
        await exportNodeToPng(renderRef.current, { width: W, height: H, fileName: `betterstats-${templateId.toLowerCase()}-${stamp}.png` })
      }
    } catch (e) {
      setExportError(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  // ─── Derived values ─────────────────────────────────────────────────────────

  const activeTab = TAB_MAP[templateId] || 'lineup'
  const switchTab = (tabKey) => { setTemplateId(TAB_FIRST[tabKey] || 'T1'); setCustomEdit(false) }
  const selectTemplate = (id) => { setTemplateId(id); setCustomEdit(false) }
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

  // Which freeform layer is being edited, and whether the freeform tools show.
  // Blank tab → the standalone canvas; Custom Edit on a real template → overlay.
  const isBlankTab = tmpl.kind === 'blank'
  const showBlankTools = isBlankTab || customEdit
  // The layer the rail panels + inspector edit: the standalone canvas on the
  // Blank tab, else the overlay that floats on top of a real template. (Adding
  // a block to a real template turns Custom Edit on so the overlay shows.)
  const layer = isBlankTab ? canvas : overlay
  const history = isBlankTab ? canvasHistory : overlayHistory

  // Snapshot the current layer BEFORE a mutation so undo restores it. A burst of
  // the same label within 400ms coalesces into one snapshot (slider drags).
  const record = (label) => {
    const t = Date.now()
    if (label === lastRec.current.label && t - lastRec.current.t < 400) { lastRec.current.t = t; return }
    lastRec.current = { label, t }
    history.commit(label)
  }
  // History-aware wrappers around the layer mutators the inspector/panels drive.
  const hUpdate = (id, patch) => { record('Edit block'); layer.update(id, patch) }
  const hReorder = (id, dir) => { record('Reorder'); layer.reorder(id, dir) }
  const hDuplicate = (id) => { record('Duplicate'); layer.duplicate(id) }
  const hRemove = (id) => { record('Delete'); layer.remove(id) }
  const hAlign = (mode) => { record('Align'); layer.align(mode) }
  const hMoveBefore = (a, b) => { record('Reorder'); layer.moveBefore(a, b) }

  // Keyboard: delete removes the selection; ⌘/Ctrl-Z undo, ⇧⌘Z redo. Ignored
  // while typing in a field.
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target?.isContentEditable) return
      const meta = e.metaKey || e.ctrlKey
      if (meta && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault()
        if (e.shiftKey) history.redo(); else history.undo()
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && layer.selIds.length) {
        e.preventDefault()
        record('Delete')
        layer.selIds.forEach((id) => layer.remove(id))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, layer])

  // A template switch starts a fresh undo history (the old snapshots belong to a
  // different layout).
  useEffect(() => { canvasHistory.clear(); overlayHistory.clear() }, [templateId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Light-surface event layouts (Ticket, Gazette, Sticker, Swiss, Polaroid) want
  // a paper/ink pair rather than the dark-mode palette; eventPaletteFor is a
  // no-op for everything else, so the render path stays unchanged otherwise.
  const renderPalette = tmpl.kind === 'event' ? eventPaletteFor(tmpl.surface, themedPalette) : themedPalette

  // bgColors[bgStyle] is a *partial* override merged over the palette's own
  // derived defaults, so switching palette still updates an uncustomised
  // background instead of freezing it at whatever it looked like when picked
  // — and, just as importantly, so switching TEMPLATE doesn't perturb it:
  // only ever store the keys the user actually touched (see the colour
  // picker onChange below), never a full baked-in snapshot.
  const bgColorsMerged = bgStyle !== 'none' ? { ...paletteToBgColors(renderPalette), ...(bgColors[bgStyle] || {}) } : null
  const bgActive = bgStyle !== 'none'
  const bgResolvedColors = bgActive ? bgColorsMerged : null
  // The template's own opaque canvas fill is given an alpha channel so the
  // SocialBackground sitting behind it (same coordinate space, lower in the
  // DOM) shows through — the templates' hardcoded `background: palette.primary`
  // fills can't be touched individually (~40 of them), so this is done by
  // feeding them a translucent palette instead.
  const templatePalette = bgActive ? { ...renderPalette, primary: withAlpha(renderPalette.primary, '99') } : renderPalette

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
      winner: result.winner, margin: result.margin, grade: result.grade, teamScore: result.teamScore,
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

  // Live data bundle for the Blank Canvas "data blocks" (fixtures / results /
  // record / scorecard / player). Built from the state the designer already
  // holds, so blocks show current info with no extra fetch (bar player stats).
  const wld = (o) => (o || '').toUpperCase()
  const blankRecord = {
    w: results.filter((r) => wld(r.outcome) === 'W').length,
    l: results.filter((r) => wld(r.outcome) === 'L').length,
    d: results.filter((r) => ['D', 'T', 'TIE'].includes(wld(r.outcome))).length,
  }
  const blankData = {
    team, match: matchData, fixtures, results, record: blankRecord,
    scorecard: scorecardMatch, players: allPlayers, playerStats: playerStatsCache,
  }

  // Fetch career stats for any player referenced by a player data block.
  useEffect(() => {
    const ids = [...canvas.items, ...overlay.items]
      .filter((it) => it.type === 'data' && it.kind === 'player' && it.playerId)
      .map((it) => it.playerId)
    const missing = [...new Set(ids)].filter((id) => !(id in playerStatsCache))
    if (!missing.length) return undefined
    let cancelled = false
    Promise.all(missing.map((id) => api.getPlayerStats(id).then((s) => [id, s]).catch(() => [id, {}])))
      .then((pairs) => {
        if (cancelled) return
        setPlayerStatsCache((prev) => { const next = { ...prev }; pairs.forEach(([id, s]) => { next[id] = s || {} }); return next })
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas.items, overlay.items])

  // Custom Edit → convert the current template into fully-movable blocks (for
  // the companion post types), else fall back to overlay-on-top editing.
  const buildCustomEditItems = () => {
    const annP = selectedPlayers[announcement.playerIdx]
    const annPlayer = annP ? playerToTemplatePlayer(annP.player, annP, nameFormat, swapNames) : null
    const motmP = selectedPlayers[motm.playerIdx]
    const motmPlayer = motmP ? playerToTemplatePlayer(motmP.player, motmP, nameFormat, swapNames) : null
    return templateToBlocks(templateId, {
      team, match: matchData,
      announcement: { kind: announcement.kind, headline: announcement.headline, subheadline: announcement.subheadline, player: annPlayer },
      toss: { winner: toss.winner, decision: toss.decision, teamName: team.name, oppName: oppData.name },
      motm: { player: motmPlayer, stats: motm.stats.filter((s) => s.label && s.value), summary: motm.summary },
      result: { winner: result.winner, teamName: team.name, oppName: oppData.name, teamScore: result.teamScore, oppScore: result.oppScore, margin: result.margin, motmLast: result.motmLast },
    })
  }
  const beginCustomEdit = () => {
    const items = buildCustomEditItems()
    if (items && items.length) {
      canvas.reset(items)
      setCustomEdit(false)
      setTemplateId('BL1')
    } else {
      startCustomEdit()
    }
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
    // POTM photo: an uploaded hero image wins, else the matched player's profile
    // photo (RS4 "Star of the Day" shows it in place of the initials).
    const motmProfile = playerForPid(result.motmPlayerId)
    const potmPhoto = (heroMode === 'hero' && heroImage.blobUrl)
      ? heroImage.blobUrl
      : (motmProfile?.photo_url ? `${BASE_URL}/images/players/${motmProfile.id}/photo` : null)
    extraProps.result = {
      comp: matchData.competition, grade: result.grade || '', round: matchData.round, date: matchData.date,
      season: matchData.season, venue: matchData.venue,
      us: { name: team.name, mono: team.monogram, logo: team.logo, score: result.teamScore || '—', overs: result.teamOvers || '' },
      them: { name: oppData.name, mono: oppData.monogram, logo: oppData.logo, score: result.oppScore || '—', overs: result.oppOvers || '' },
      winner: result.winner === 'OPPONENT' ? 'them' : result.winner === 'TIE' ? 'tie' : 'us',
      margin: result.margin || '',
      potm: {
        first: result.motmFirst || '', last: result.motmLast || '', role: result.motmRole || '',
        bat: result.motmBat || '', bowl: result.motmBowl || '', photo: potmPhoto,
        line: [result.motmBat, result.motmBowl].filter(Boolean).join(' · '),
      },
      topBat: { us: mapPerf(result.topBatters.team), them: mapPerf(result.topBatters.opponent) },
      topBowl: { us: mapPerf(result.topBowlers.team), them: mapPerf(result.topBowlers.opponent) },
    }
    extraProps.sponsors = scorecardMatch.meta.sponsors
  }
  if (tmpl.kind === 'blank') {
    extraProps.items = canvas.items
    extraProps.data = blankData
  }
  if (tmpl.kind === 'event') {
    extraProps.event = event
    extraProps.motif = resolveMotif({
      motifKey: eventMotifKey,
      imageUrl: eventBg,
      opacity: eventBgOpacity,
      label: (EVENT_PRESETS.find((p) => p.key === eventPreset)?.photoLabel) || 'Add a photo',
    })
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
      winner: 'TEAM', margin: '', grade: '', teamScore: '', oppScore: '', teamOvers: '', oppOvers: '', motmLast: '',
      motmFirst: '', motmRole: '', motmBat: '', motmBowl: '', motmPlayerId: '',
      topBatters: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
      topBowlers: { team: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }], opponent: [{ last: '', line: '' }, { last: '', line: '' }, { last: '', line: '' }] },
    })
    setResUrlInput('')
    setResUrlStatus(null)
    setFixtures(DEFAULT_FIXTURES.map((f) => ({ ...f })))
    setResults(DEFAULT_RESULTS.map((r) => ({ ...r })))
    setScorecardMatch(DEFAULT_SCORECARD)
    setScUrlInput('')
    setScUrlStatus(null)
    setEvent(DEFAULT_EVENT)
    setEventPreset('curry')
    setEventMotifKey('star')
    if (eventBg) URL.revokeObjectURL(eventBg)
    setEventBg(null)
    setEventBgOpacity(0.85)
    canvas.reset(defaultBlankItems())
    overlay.reset([])
    setCustomEdit(false)
  }

  if (loading) return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-pb-bg">
      <span className="font-mono text-[11px] text-pb-faint animate-pulse">LOADING...</span>
    </div>
  )

  // ─── Preview renderer ────────────────────────────────────────────────────────
  const W = tmpl.w || (isScorecard ? 1920 : 1080)
  const H = tmpl.h || 1080

  // ─── Controls ────────────────────────────────────────────────────────────────
  const showMatchInfo = !['scorecard', 'events', 'blank'].includes(activeTab)
  const showOpponent  = !['scorecard', 'fixtures', 'results', 'events', 'blank'].includes(activeTab)
  const showPlayers   = activeTab !== 'scorecard' && activeTab !== 'blank' && tmpl.maxPlayers > 0
  const showHeroImage = ['T1','T3','T6','T7','C1','C3'].includes(templateId)

  // ─── Mobile quick post ────────────────────────────────────────────────────
  if (isMobile && !forceFullEditor) {
    const previewContent = (
      <>
        {bgActive && <SocialBackground variant={bgStyle} colors={bgResolvedColors} size={W} height={H} style={{ position: 'absolute', inset: 0 }} />}
        {isBlankTab
          ? <BlankCanvas team={team} palette={templatePalette} items={canvas.items} data={blankData} width={W} height={H} />
          : <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={templatePalette} headline={headline} {...extraProps} />}
        {customEdit && !isBlankTab && (
          <BlankCanvas team={team} palette={templatePalette} items={overlay.items} data={blankData} transparent width={W} height={H} style={{ position: 'absolute', inset: 0 }} />
        )}
      </>
    )
    // The three details that matter most for the active post type.
    let mFields = []
    if (activeTab === 'lineup') mFields = [
      { label: 'Headline', value: headline, onChange: setHeadline, placeholder: 'SQUAD' },
      { label: 'Opponent', value: opponent.name, onChange: (v) => patchOpp({ name: v }), placeholder: 'Opponent CC' },
      { label: 'Date', value: match.date, onChange: (v) => patchMatch({ date: v }), placeholder: 'SAT 30 MAY' },
    ]
    else if (activeTab === 'result') mFields = [
      { label: 'Our score', value: result.teamScore, onChange: (v) => setResult((r) => ({ ...r, teamScore: v })), placeholder: '6/188' },
      { label: 'Their score', value: result.oppScore, onChange: (v) => setResult((r) => ({ ...r, oppScore: v })), placeholder: '184' },
      { label: 'Margin', value: result.margin, onChange: (v) => setResult((r) => ({ ...r, margin: v })), placeholder: 'BY 4 WICKETS' },
    ]
    else if (activeTab === 'announcement') mFields = [
      { label: 'Headline', value: announcement.headline, onChange: (v) => setAnnouncement((a) => ({ ...a, headline: v })) },
      { label: 'Subheadline', value: announcement.subheadline, onChange: (v) => setAnnouncement((a) => ({ ...a, subheadline: v })) },
    ]
    else if (activeTab === 'fixtures' || activeTab === 'results') mFields = [
      { label: 'Round', value: match.round, onChange: (v) => patchMatch({ round: v }), placeholder: 'ROUND 7' },
      { label: 'Date', value: match.date, onChange: (v) => patchMatch({ date: v }), placeholder: 'SAT 30 MAY' },
    ]
    else if (isBlankTab) mFields = canvas.items.filter((it) => it.type === 'text').slice(0, 3)
      .map((it, i) => ({ label: `Text ${i + 1}`, value: it.text, onChange: (v) => canvas.update(it.id, { text: v }) }))
    else mFields = [
      { label: 'Opponent', value: opponent.name, onChange: (v) => patchOpp({ name: v }), placeholder: 'Opponent CC' },
      { label: 'Date', value: match.date, onChange: (v) => patchMatch({ date: v }), placeholder: 'SAT 30 MAY' },
    ]
    const mPalettes = [
      { key: 'club', label: 'Club', color: orgAccent(settings) },
      ...Object.entries(PALETTES).map(([key, pal]) => ({ key, label: pal.name, color: pal.accent })),
    ]
    return (
      <>
        <SocialBackgroundDefs />
        <MobileQuickPost
          moduleLogo={moduleBrand('socials').logo} clubName={settings?.name}
          W={W} H={H} content={previewContent} fontStyle={fontStyle}
          types={TABS.map((t) => ({ key: t.key, label: t.label }))} activeType={activeTab} onPickType={switchTab}
          fields={mFields} palettes={mPalettes} paletteKey={paletteKey} onPickPalette={setPaletteKey}
          onExport={handleExport} exporting={exporting} onSaveDraft={saveCurrentTemplate}
          onFullEditor={() => setForceFullEditor(true)}
        />
      </>
    )
  }

  // ─── Start screen ─────────────────────────────────────────────────────────
  // A bare /admin/social-post (no ?type / ?template) shows the first-run post
  // picker; a deep link that names a type or template goes straight to editing.
  const entryParams = new URLSearchParams(location.search)
  const showStart = !entryParams.has('type') && !entryParams.has('template')
  if (showStart) {
    const startTypes = TABS.map((t) => ({
      key: t.key, label: t.label,
      count: TEMPLATES.filter((x) => TAB_MAP[x.id] === t.key).length,
    }))
    const openType = (typeKey) => { switchTab(typeKey); navigate(`/admin/social-post?type=${typeKey}`) }
    return (
      <StartScreen
        types={startTypes}
        club={{ name: settings?.name, subtitle: settings?.home_ground || settings?.home_venue || '', logo: team.logo }}
        moduleLogo={moduleBrand('socials').logo}
        savedTemplates={savedTemplates}
        onPick={openType}
        onOpenEditor={() => navigate(`/admin/social-post?type=${activeTab}`)}
        onApplyTemplate={(tpl) => { applyTemplate(tpl); navigate(`/admin/social-post?template=${tpl.key}`) }}
      />
    )
  }

  // ─── Editor shell scaffolding ────────────────────────────────────────────
  // Add a freeform block to the layer being edited: the standalone canvas on the
  // Blank tab, else the overlay on top of a real template (turning on Custom
  // Edit so it shows).
  const addBlock = (type, opts = {}) => {
    if (!isBlankTab && !customEdit) setCustomEdit(true)
    const target = isBlankTab ? canvas : overlay
    record(`Add ${type}`)
    return target.add(type, opts)
  }

  // Media library handlers (optimistic upload, then swap in the stored URL).
  const uploadMedia = async (files) => {
    for (const f of files) {
      if (!f) continue
      const tmpId = `tmp_${Date.now()}_${Math.round(Math.random() * 1e6)}`
      const tmpUrl = URL.createObjectURL(f)
      setMediaAssets((a) => [{ id: tmpId, name: f.name, url: tmpUrl, _tmp: true }, ...a])
      try {
        const saved = await api.uploadSocialMedia(f)
        setMediaAssets((a) => a.map((x) => (x.id === tmpId ? saved : x)))
      } catch { setMediaAssets((a) => a.filter((x) => x.id !== tmpId)) }
    }
  }
  const useMediaAsset = (asset) => {
    const sel = layer.selIds.length === 1 ? layer.items.find((it) => it.id === layer.selIds[0]) : null
    if (sel && sel.type === 'image') { record('Replace image'); layer.update(sel.id, { src: asset.url, srcName: asset.name }) }
    else addBlock('image', { src: asset.url, srcName: asset.name })
  }
  const pickImageForItem = (itemId) => { pendingImgItem.current = itemId; blankImgInputRef.current?.click() }

  const clubName = settings?.name || 'Club'
  const headerLeft = (
    <>
      <button onClick={() => navigate('/admin')} title="Back to admin" className="w-7 h-7 grid place-items-center rounded-md text-pb-faint hover:text-pb-text transition-colors"><Icon name="back" size={16} /></button>
      <span className="flex items-center gap-2 min-w-0">
        {team.logo
          ? <img src={team.logo} alt="" className="w-[26px] h-[26px] rounded object-contain shrink-0 bg-pb-surface2" />
          : <span className="w-[26px] h-[26px] rounded grid place-items-center font-mono text-[11px] bg-pb-surface2 text-pb-dim shrink-0">{deriveShort(clubName).slice(0, 2)}</span>}
        <span className="font-mono text-[9px] text-pb-faint uppercase truncate max-w-[110px] hidden sm:block">{clubName}</span>
      </span>
      <span className="w-px h-5 bg-pb-hairline" />
      <ModuleLockup name="BetterPosts" logo={moduleBrand('socials').logo} accent="#EC4899" />
      <span className="w-px h-5 bg-pb-hairline" />
      <button ref={typeBtnRef} onClick={() => setTypeMenuOpen((o) => !o)}
        className="flex items-center gap-2 px-2.5 h-8 rounded-md border pb-hairline2 bg-pb-surface2 hover:border-pb-accent transition-colors">
        <span className="font-mono text-[8px] tracking-wide2 uppercase text-pb-faint">Post</span>
        <span className="text-pb-text text-[12px]">{TABS.find((t) => t.key === activeTab)?.label}</span>
        <Icon name="chevron" size={12} className="text-pb-faint rotate-90" />
      </button>
      <Dropdown anchorRef={typeBtnRef} open={typeMenuOpen} onClose={() => setTypeMenuOpen(false)}
        className="bg-pb-surface border pb-hairline2 rounded-lg shadow-xl p-2">
        <div className="grid grid-cols-2 gap-1 w-[420px]">
          {TABS.map((t) => (
            <button key={t.key} onClick={() => { switchTab(t.key); setTypeMenuOpen(false) }}
              className={`text-left px-3 py-2 rounded-md text-[12px] transition-colors ${activeTab === t.key ? 'text-pb-accent bg-pb-surface2' : 'text-pb-dim hover:bg-pb-surface2'}`}>{t.label}</button>
          ))}
        </div>
      </Dropdown>
    </>
  )
  const headerRight = (
    <>
      <span className="flex items-center gap-1">
        <button onClick={history.undo} disabled={!history.canUndo} title="Undo (⌘Z)"
          className="w-7 h-7 grid place-items-center rounded-md text-pb-dim hover:text-pb-text disabled:opacity-30 disabled:hover:text-pb-dim transition-colors"><Icon name="reset" size={15} /></button>
        <button onClick={history.redo} disabled={!history.canRedo} title="Redo (⇧⌘Z)"
          className="w-7 h-7 grid place-items-center rounded-md text-pb-dim hover:text-pb-text disabled:opacity-30 disabled:hover:text-pb-dim transition-colors"><Icon name="reset" size={15} style={{ transform: 'scaleX(-1)' }} /></button>
        <span className="font-mono text-[8px] tracking-wide2 uppercase text-pb-faintest w-11 leading-tight">{history.depth} step{history.depth === 1 ? '' : 's'}</span>
      </span>
      <span className="w-px h-5 bg-pb-hairline" />
      {exportError && <span className="text-pb-red text-[10px] font-mono truncate max-w-[140px]">{exportError}</span>}
      <button onClick={handleReset} title="Reset the fields for this post type"
        className="px-2.5 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">↺ RESET</button>
      <button onClick={saveCurrentTemplate} title="Save this post as a reusable template"
        className="px-3 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-dim hover:text-pb-text hover:border-pb-accent transition-colors">SAVE AS TEMPLATE</button>
      <button onClick={handleExport} disabled={exporting}
        className="px-3.5 h-8 rounded-md font-mono text-[10px] tracking-wide2 disabled:opacity-60 transition-colors"
        style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>{exporting ? 'EXPORTING…' : (isBlankTab && pages.count > 1 ? `↓ ${pages.count} SLIDES` : '↓ DOWNLOAD PNG')}</button>
    </>
  )

  const panelMeta = {
    design: `${tabTemplates.length} layout${tabTemplates.length === 1 ? '' : 's'}`,
    content: 'this post', data: 'live', brand: 'colour · type',
    layers: `${layer.items.length} block${layer.items.length === 1 ? '' : 's'}`,
  }[tool] || ''

  const renderCanvas = ({ availW, availH }) => {
    const scale = Math.max(0.05, Math.min(availW / W, availH / H, 1))
    const pw = Math.round(W * scale), ph = Math.round(H * scale)
    return (
      <div className="relative">
        {isBlankTab && (
          <PageStrip count={pages.count} index={pages.index}
            onGoTo={pages.goTo} onAdd={pages.add} onDuplicate={pages.duplicate} onRemove={pages.remove} />
        )}
        <div style={{ width: pw, height: ph, overflow: 'hidden', borderRadius: 6, background: '#080808', boxShadow: '0 24px 60px rgba(0,0,0,.55)' }}>
          <div style={{ ...fontStyle, transform: `scale(${scale})`, transformOrigin: 'top left', width: W, height: H, pointerEvents: showBlankTools ? 'auto' : 'none', position: 'relative' }}>
            {bgActive && <SocialBackground variant={bgStyle} colors={bgResolvedColors} size={W} height={H} style={{ position: 'absolute', inset: 0 }} />}
            {isBlankTab ? (
              <BlankCanvas team={team} palette={templatePalette} items={canvas.items} data={blankData}
                interactive scale={scale} selectedIds={canvas.selIds}
                onSelect={canvas.select} onDeselect={canvas.deselect} onPatchMany={canvas.patchMany}
                onGestureStart={() => record('Move block')} />
            ) : (
              <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={templatePalette} headline={headline} {...extraProps} />
            )}
            {customEdit && !isBlankTab && (
              <BlankCanvas team={team} palette={templatePalette} items={overlay.items} data={blankData} transparent width={W} height={H}
                interactive scale={scale} selectedIds={overlay.selIds}
                onSelect={overlay.select} onDeselect={overlay.deselect} onPatchMany={overlay.patchMany}
                onGestureStart={() => record('Move block')}
                style={{ position: 'absolute', inset: 0 }} />
            )}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between gap-3" style={{ width: pw }}>
          <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest">{W} × {H} · {Math.round(scale * 100)}% · {isBlankTab && pages.count > 1 ? `PAGE ${pages.index + 1} OF ${pages.count} · CAROUSEL` : 'SINGLE POST'}</span>
          <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest">{showBlankTools ? 'DRAG TO MOVE · SHIFT-CLICK FOR SEVERAL' : ''}</span>
        </div>
      </div>
    )
  }

  const inspectorNode = (
    <SelectionInspector
      items={layer.items} selIds={layer.selIds}
      onUpdate={hUpdate} onReorder={hReorder}
      onDuplicate={hDuplicate} onRemove={hRemove} onAlign={hAlign}
      palette={themedPalette} players={allPlayers} onPickImage={pickImageForItem}
    />
  )

  const photosPanel = (
    <MediaLibraryPanel
      assets={mediaAssets} onUpload={uploadMedia} onUseAsset={useMediaAsset} onAddEmptyFrame={() => addBlock('image')}
      players={allPlayers} onAddPlayerPhoto={(pid) => addBlock('data', { kind: 'playerphoto', playerId: pid })}
      onAddBrandLockup={() => addBlock('brand')}
      sponsors={adminSponsors.map((s) => ({ name: s.name, url: `${BASE_URL}/images/sponsors/${s.id}/logo` }))}
      onAddSponsor={(sp) => addBlock('image', { src: sp.url, srcName: sp.name, fit: 'contain' })}
      club={{ name: settings?.name, logo_url: team.logo }}
    />
  )

  return (
    <>
      <SocialBackgroundDefs />
      <input ref={blankImgInputRef} type="file" accept="image/png,image/webp,image/jpeg" className="sr-only"
        onChange={(e) => { const f = e.target.files?.[0]; if (f && pendingImgItem.current) setEditor({ key: 'blankimg', itemId: pendingImgItem.current, source: f }); e.target.value = '' }} />
      <PostEditorShell
        headerLeft={headerLeft}
        headerRight={headerRight}
        tool={tool}
        onTool={setTool}
        panelTitle={TOOL_TITLE[tool]}
        panelMeta={panelMeta}
        renderCanvas={renderCanvas}
        inspector={inspectorNode}
        panel={(
          <div className="flex flex-col gap-4">
            {tool === 'text' && <TextPanel onAdd={addBlock} />}
            {tool === 'elements' && <ShapesPanel onAdd={addBlock} />}
            {tool === 'data' && <ClubDataPanel onAdd={addBlock} />}
            {tool === 'photos' && photosPanel}
            {tool === 'layers' && (
              <LayersPanel
                items={layer.items} selIds={layer.selIds}
                onSelect={layer.select} onReorder={hReorder}
                onDuplicate={hDuplicate} onRemove={hRemove}
                onMoveLayerBefore={hMoveBefore} historyLog={history.log}
              />
            )}
            {tool === 'brand' && (<>

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
                  <span style={{ width: 12, height: 12, borderRadius: 2, background: orgAccent(settings), display: 'inline-block' }} />
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
              <div className="mt-2 pt-2 border-t pb-hairline">
                <span className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">Background</span>
                <div className="flex gap-2 flex-wrap items-center mt-1.5 mb-1">
                  <BgStyleSwatch entry={{ key: 'none', label: 'Clean' }} colors={paletteToBgColors(renderPalette)} selected={bgStyle === 'none'} onClick={() => setBgStyle('none')} />
                  {BG_GROUPS.map(group => (
                    <div key={group} className="flex gap-2 flex-wrap items-center">
                      {SOCIAL_BACKGROUNDS.filter(s => s.group === group).map(s => (
                        <BgStyleSwatch key={s.key} entry={s} colors={paletteToBgColors(renderPalette)} selected={bgStyle === s.key} onClick={() => setBgStyle(s.key)} />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
              {bgStyle !== 'none' && (
                <div className="flex gap-3 flex-wrap items-center mt-2">
                  {BG_COLOR_KEYS.map(({ key, label }) => (
                    <label key={key} className="flex items-center gap-1.5 text-[11px] text-pb-faint font-mono">
                      <input
                        type="color"
                        value={bgColorsMerged[key] || '#000000'}
                        onChange={e => setBgColors(c => ({ ...c, [bgStyle]: { ...(c[bgStyle] || {}), [key]: e.target.value } }))}
                        className="w-7 h-7 rounded cursor-pointer border-0 bg-transparent p-0"
                      />
                      {label}
                    </label>
                  ))}
                  {bgColors[bgStyle] && (
                    <button
                      onClick={() => setBgColors(c => { const next = { ...c }; delete next[bgStyle]; return next })}
                      className="text-pb-faintest hover:text-pb-text text-[10px] font-mono underline"
                    >Reset to club colours</button>
                  )}
                </div>
              )}
              <div className="flex gap-2 flex-wrap items-center mt-2 pt-2 border-t pb-hairline">
                <span className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 w-full">Saved Designs</span>
                {savedDesigns.map(d => (
                  <div key={d.key} className="flex items-center gap-1">
                    <DesignSwatch
                      design={d}
                      selected={paletteKey === d.key}
                      onClick={() => {
                        setPaletteKey(d.key)
                        setBgStyle(d.bgStyle)
                        setFontKey(d.fontKey)
                        setDarkMode(d.dark)
                        if (d.bgColors) setBgColors(c => ({ ...c, [d.bgStyle]: d.bgColors }))
                      }}
                    />
                    <button
                      onClick={() => {
                        const nextDesigns = savedDesigns.filter(x => x.key !== d.key)
                        setSavedDesigns(nextDesigns)
                        localStorage.setItem('bs_social_designs', JSON.stringify(nextDesigns))
                        const nextPalettes = savedPalettes.filter(x => x.key !== d.key)
                        setSavedPalettes(nextPalettes)
                        localStorage.setItem('bs_social_palettes', JSON.stringify(nextPalettes))
                        if (paletteKey === d.key) setPaletteKey('club')
                      }}
                      className="text-pb-faintest hover:text-red-400 text-[10px] leading-none"
                    >✕</button>
                  </div>
                ))}
                {!showSaveDesign && (
                  <button
                    onClick={() => setShowSaveDesign(true)}
                    className="px-2.5 py-1 rounded border text-[11px] font-mono text-pb-faint hover:text-pb-text border-transparent transition-colors"
                  >+ Save current look</button>
                )}
              </div>
              {showSaveDesign && (
                <div className="mt-2 flex gap-2 items-center">
                  <input value={saveDesignName} onChange={e => setSaveDesignName(e.target.value)} placeholder="Design name — e.g. Match Day Grunge"
                    className="flex-1 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-xs text-pb-text placeholder:text-pb-faintest font-mono" />
                  <button
                    onClick={() => {
                      const name = saveDesignName.trim() || `Design ${savedDesigns.length + 1}`
                      const key = `design_${Date.now()}`
                      const pal = { key, name, primary: activePalette.primary, secondary: activePalette.secondary, accent: activePalette.accent, ink: activePalette.ink }
                      const nextPalettes = [...savedPalettes, pal]
                      setSavedPalettes(nextPalettes)
                      localStorage.setItem('bs_social_palettes', JSON.stringify(nextPalettes))
                      const design = {
                        key, name, primary: activePalette.primary, secondary: activePalette.secondary, accent: activePalette.accent, ink: activePalette.ink,
                        bgStyle, fontKey, dark: darkMode, bgColors: bgColors[bgStyle] || null,
                      }
                      const nextDesigns = [...savedDesigns, design]
                      setSavedDesigns(nextDesigns)
                      localStorage.setItem('bs_social_designs', JSON.stringify(nextDesigns))
                      setSaveDesignName('')
                      setShowSaveDesign(false)
                      setPaletteKey(key)
                    }}
                    className="px-3 py-1 rounded text-xs font-mono text-pb-text border pb-hairline hover:bg-pb-surface2 transition-colors whitespace-nowrap"
                  >Save design</button>
                  <button
                    onClick={() => { setShowSaveDesign(false); setSaveDesignName('') }}
                    className="text-pb-faintest hover:text-pb-text text-xs font-mono"
                  >Cancel</button>
                </div>
              )}
            </section>

            </>)}

            {tool === 'design' && (<>
            {/* Templates — collapsible. Built-in variants for this tab stacked
                so they're all visible at once, plus a "Custom" group of saved
                templates. Saving works on every tab (captures base template +
                Style, and the Blank Canvas layout). */}
            <section className="pb-card p-4">
              <button onClick={() => setTemplatesOpen(o => !o)} className="w-full flex items-center justify-between">
                <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Templates</h2>
                <span className="font-mono text-[11px] text-pb-faint">{templatesOpen ? '▾' : '▸'}</span>
              </button>
              {templatesOpen && (
                <div className="mt-3 flex flex-col gap-4">
                  {!isBlankTab && (
                    <div className="flex flex-col gap-1 self-start">
                      <button
                        onClick={customEdit ? stopCustomEdit : beginCustomEdit}
                        className="px-3 py-1.5 rounded text-[11px] font-mono border transition-colors self-start"
                        style={customEdit
                          ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' }
                          : { borderColor: 'var(--pb-hairline)' }}>
                        {customEdit
                          ? '✎ Custom editing (overlay) — click to stop'
                          : CUSTOM_EDITABLE.includes(templateId)
                            ? '✎ Custom Edit — make every element movable'
                            : '✎ Custom Edit — add blocks on top'}
                      </button>
                      <span className="text-pb-faintest text-[10px]">
                        {CUSTOM_EDITABLE.includes(templateId)
                          ? 'Opens this post as fully-editable blocks you can move, then save as a template.'
                          : 'This layout keeps its content; you can add your own blocks on top.'}
                      </span>
                    </div>
                  )}
                  {tabTemplates.length > 1 && activeTab !== 'events' && (
                    <div className="flex flex-col gap-1.5">
                      <div className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">This tab</div>
                      <div className="grid grid-cols-2 gap-2">
                        {tabTemplates.map(t => (
                          <button
                            key={t.id}
                            onClick={() => selectTemplate(t.id)}
                            className={`text-left p-2.5 rounded border transition-colors ${templateId === t.id ? 'bg-pb-surface2' : 'border-transparent bg-pb-surface hover:bg-pb-surface2'}`}
                            style={templateId === t.id ? { borderColor: 'var(--pb-accent)' } : {}}
                          >
                            <div className="font-mono text-[9px] text-pb-faintest mb-0.5">{t.id}</div>
                            <div className="font-medium text-pb-text text-xs leading-tight">{t.name}</div>
                            <div className="text-[10px] text-pb-faint leading-tight mt-0.5">{t.desc}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-1.5">
                    <div className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">Custom</div>
                    {savedTemplates.length === 0 && (
                      <div className="text-pb-faintest text-[10px] font-mono">No saved templates yet — build a post, then save it below.</div>
                    )}
                    {savedTemplates.length > 0 && (
                      <div className="grid grid-cols-2 gap-2">
                        {savedTemplates.map(t => (
                          <div key={t.key}
                            className={`relative p-2.5 rounded border transition-colors ${templateId === t.templateId ? 'bg-pb-surface2' : 'border-transparent bg-pb-surface hover:bg-pb-surface2'}`}>
                            <button onClick={() => applyTemplate(t)} className="text-left w-full pr-4">
                              <div className="font-medium text-pb-text text-xs leading-tight truncate">{t.name}</div>
                              <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{t.custom ? 'edit' : ''}{t.custom ? ' · ' : ''}{t.templateId}{t.blank ? ` · ${t.blank.length}` : ''}</div>
                            </button>
                            <button onClick={() => deleteTemplate(t.key)} title="Delete template" className="absolute top-1.5 right-1.5 text-pb-faintest hover:text-red-400 text-xs">✕</button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2 mt-1">
                      <input value={saveTemplateName} onChange={e => setSaveTemplateName(e.target.value)} placeholder="Template name..."
                        className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[11px] font-mono text-pb-text" />
                      <button onClick={saveCurrentTemplate}
                        className="px-3 py-1 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors whitespace-nowrap">
                        Save current
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </section>

            </>)}

            {tool === 'content' && (<>
            {isBlankTab && (
              <div className="pb-card p-4">
                <p className="text-[11px] text-pb-dim leading-relaxed">
                  A blank canvas — use the tools on the left (<span className="text-pb-text">Text</span>, <span className="text-pb-text">Shapes</span>, <span className="text-pb-text">Photos</span>, <span className="text-pb-text">Club data</span>) to add blocks, then drag them on the canvas. Or pick a starting layout under <span className="text-pb-text">Design</span>.
                </p>
              </div>
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

                {/* PlayCricket URL import — auto top 3 batters & bowlers (both sides),
                    scores, result, MOTM + matched player photos. Everything stays editable. */}
                <div className="mb-4 p-3 rounded border pb-hairline bg-pb-surface2">
                  <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-2">Auto-fill from match link</p>
                  <div className="flex gap-2">
                    <input type="text" value={resUrlInput} onChange={e => { setResUrlInput(e.target.value); setResUrlStatus(null) }}
                      placeholder="Match link or match ID (e.g. 37af9ea5-…)"
                      className="flex-1 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono"
                      onKeyDown={e => e.key === 'Enter' && handleResultImport()} />
                    <button onClick={handleResultImport} disabled={resUrlStatus === 'loading'}
                      className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50"
                      style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                      {resUrlStatus === 'loading' ? 'Loading…' : 'Import'}
                    </button>
                  </div>
                  {resUrlStatus && resUrlStatus !== 'loading' && (
                    <p className={`font-mono text-[9px] mt-1.5 ${resUrlStatus === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                      {resUrlStatus === 'ok' ? '✓ Top performers, scores & MOTM filled — review below' : `✗ ${resUrlStatus}`}
                    </p>
                  )}
                  <p className="font-mono text-[9px] mt-1.5 text-pb-faintest">Pulls the top 3 batters & bowlers for both sides and matches your players for photos.</p>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="col-span-2"><Field label="Grade"><TextInput value={result.grade} onChange={v => setResult(r => ({ ...r, grade: v }))} placeholder="1ST GRADE" /></Field></div>
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

                {/* POTM image — Star of the Day shows a player profile photo or an
                    uploaded hero image in place of the initials (RS4 feedback). */}
                <div className="mb-4 pt-3 border-t pb-hairline">
                  <div className="flex items-center justify-between mb-2">
                    <label className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">POTM Photo</label>
                    <span className="font-mono text-[9px] text-pb-faintest">Star of the Day layout</span>
                  </div>
                  <div className="flex gap-2 mb-2">
                    <button onClick={() => setHeroMode('player')}
                      className={`flex-1 py-1.5 rounded border text-xs font-mono transition-colors ${heroMode === 'player' ? '' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
                      style={heroMode === 'player' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                    >Player Photo</button>
                    <button onClick={() => setHeroMode('hero')}
                      className={`flex-1 py-1.5 rounded border text-xs font-mono transition-colors ${heroMode === 'hero' ? '' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
                      style={heroMode === 'hero' ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}
                    >Hero Image</button>
                  </div>
                  {heroMode === 'player' ? (
                    <>
                      <select value={result.motmPlayerId} onChange={e => setResult(r => ({ ...r, motmPlayerId: e.target.value }))}
                        className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text">
                        <option value="">No photo — initials</option>
                        {allPlayers.map(p => (
                          <option key={p.id} value={p.id}>
                            {(p.display_name || p.name)}{p.photo_url ? '' : ' · no photo'}
                          </option>
                        ))}
                      </select>
                      {(() => {
                        const mp = playerForPid(result.motmPlayerId)
                        if (mp?.photo_url) return (
                          <div className="flex items-center gap-2 mt-2">
                            <img src={`${BASE_URL}/images/players/${mp.id}/photo`} alt="" className="w-12 h-12 rounded-full object-cover object-top" />
                            <span className="text-[11px] text-pb-faint">{mp.display_name || mp.name}</span>
                          </div>
                        )
                        if (result.motmPlayerId) return <p className="text-[11px] text-pb-faintest mt-1">This player has no profile photo — initials will show.</p>
                        return null
                      })()}
                    </>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <label className="flex items-center gap-3 cursor-pointer group">
                        <span className="px-3 py-2 rounded border pb-hairline text-xs font-mono text-pb-faint group-hover:bg-pb-surface2 transition-colors">Choose File</span>
                        <span className="text-[11px] text-pb-faint truncate">{heroImage.blobUrl ? 'Image selected' : 'No file chosen'}</span>
                        <input type="file" accept="image/png,image/webp,image/jpeg" onChange={handleHeroFile} className="sr-only" />
                      </label>
                      {heroImage.blobUrl && (
                        <div className="flex items-start gap-3">
                          <img src={heroImage.blobUrl} alt="Hero preview" className="w-16 h-16 object-contain rounded bg-pb-surface2" />
                          <div className="flex flex-col gap-2 flex-1">
                            <button onClick={() => setEditor({ key: 'hero', source: heroImage.blobUrl })}
                              className="text-xs font-mono text-pb-faint hover:text-pb-text text-left">✎ Edit (crop / remove background)</button>
                            <button onClick={() => { URL.revokeObjectURL(heroImage.blobUrl); setHeroImage({ blobUrl: null }) }}
                              className="text-xs text-pb-faintest hover:text-red-400 font-mono text-left">Remove image</button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
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
                  <div className="flex items-center gap-2">
                    <button onClick={() => setFixtures(rows => sortByGrade(rows))}
                      className="font-mono text-[9px] tracking-wide2 px-2 py-0.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">↕ SORT BY GRADE</button>
                    <span className="font-mono text-[9px] text-pb-faintest">{fixtures.length} grades</span>
                  </div>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">Round, date &amp; competition come from <strong>Match Info</strong> above. Drag-free reorder with ▲▼.</p>
                <RoundImportBox hint="upcoming fixtures" rowsKey="fixtures"
                  status={fxImport.status} dates={fxImport.dates} idx={fxImport.idx}
                  onPull={importFixtures}
                  onPick={(i) => { setFxImport(s => ({ ...s, idx: i })); applyFxDate(fxImport.dates[i], fxImport.season) }} />
                <div className="flex flex-col gap-2">
                  {fixtures.map((f, i) => {
                    const set = (patch) => setFixtures(rows => rows.map((r, j) => j === i ? { ...r, ...patch } : r))
                    return (
                      <div key={i} className="rounded border pb-hairline p-2 bg-pb-surface2 flex flex-col gap-1.5">
                        <div className="grid gap-1.5 items-center" style={{ gridTemplateColumns: '14px 1fr 58px 20px' }}>
                          <RowReorder onUp={() => moveRow(setFixtures, i, -1)} onDown={() => moveRow(setFixtures, i, 1)} isFirst={i === 0} isLast={i === fixtures.length - 1} />
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
                          <OppRowSearch value={f.opp} onType={v => set({ opp: v })} onPick={org => pickRowOpp('fx', i, org)} />
                          <input value={f.oppMono} onChange={e => set({ oppMono: e.target.value.toUpperCase().slice(0, 3) })} placeholder="SUB"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono text-center placeholder:text-pb-faintest" />
                        </div>
                        <OppLogoChip logo={f.oppLogo} loading={f.oppLogoLoading} onClear={() => set({ oppLogo: null })} />
                        <div className="grid grid-cols-2 gap-1.5">
                          <input value={f.time} onChange={e => set({ time: e.target.value })} placeholder="12:30 PM"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={f.venue} onChange={e => set({ venue: e.target.value })} placeholder="Venue"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text placeholder:text-pb-faintest" />
                        </div>
                      </div>
                    )
                  })}
                  <button onClick={() => setFixtures(rows => [...rows, { grade: '', opp: '', oppMono: '', ha: 'H', time: '', venue: '', oppLogo: null }])}
                    className="text-left text-xs text-pb-faint hover:text-pb-accent font-mono">+ Add fixture</button>
                </div>
              </section>
            )}

            {/* Results roundup data */}
            {activeTab === 'results' && (
              <section className="pb-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Results</h2>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setResults(rows => sortByGrade(rows))}
                      className="font-mono text-[9px] tracking-wide2 px-2 py-0.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">↕ SORT BY GRADE</button>
                    <span className="font-mono text-[9px] text-pb-faintest">{results.length} grades</span>
                  </div>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">Round &amp; date come from <strong>Match Info</strong> above. W/L colour-codes the post. Reorder with ▲▼.</p>
                <RoundImportBox hint="recent results" rowsKey="results"
                  status={rrImport.status} dates={rrImport.dates} idx={rrImport.idx}
                  onPull={importResults}
                  onPick={(i) => { setRrImport(s => ({ ...s, idx: i })); applyRrDate(rrImport.dates[i], rrImport.season) }} />
                <div className="flex flex-col gap-2">
                  {results.map((r, i) => {
                    const set = (patch) => setResults(rows => rows.map((x, j) => j === i ? { ...x, ...patch } : x))
                    return (
                      <div key={i} className="rounded border pb-hairline p-2 bg-pb-surface2 flex flex-col gap-1.5">
                        <div className="grid gap-1.5 items-center" style={{ gridTemplateColumns: '14px 1fr 72px 20px' }}>
                          <RowReorder onUp={() => moveRow(setResults, i, -1)} onDown={() => moveRow(setResults, i, 1)} isFirst={i === 0} isLast={i === results.length - 1} />
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
                          <OppRowSearch value={r.opp} onType={v => set({ opp: v })} onPick={org => pickRowOpp('rr', i, org)} />
                          <input value={r.oppMono} onChange={e => set({ oppMono: e.target.value.toUpperCase().slice(0, 3) })} placeholder="SUB"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono text-center placeholder:text-pb-faintest" />
                        </div>
                        <OppLogoChip logo={r.oppLogo} loading={r.oppLogoLoading} onClear={() => set({ oppLogo: null })} />
                        <div className="grid gap-1.5" style={{ gridTemplateColumns: '1fr 1fr 1.2fr' }}>
                          <input value={r.us} onChange={e => set({ us: e.target.value })} placeholder="Us 6/188"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={r.them} onChange={e => set({ them: e.target.value })} placeholder="Them 184"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                          <input value={r.margin} onChange={e => set({ margin: e.target.value })} placeholder="BY 4 WICKETS"
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-sm text-pb-text font-mono placeholder:text-pb-faintest" />
                        </div>
                        {tmpl.hasLeaders && (
                          <div className="grid gap-2 pt-1 mt-0.5 border-t pb-hairline" style={{ gridTemplateColumns: '1fr 1fr' }}>
                            {['topBat', 'topBowl'].map((key) => (
                              <div key={key} className="flex flex-col gap-1">
                                <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">{key === 'topBat' ? 'Our top scorers' : 'Our top wickets'}</span>
                                {[0, 1].map((slot) => {
                                  const entry = (r[key] || [])[slot] || { name: '', line: '' }
                                  const setSlot = (patch) => setResults(rows => rows.map((x, j) => {
                                    if (j !== i) return x
                                    const arr = [{ ...(x[key]?.[0] || {}) }, { ...(x[key]?.[1] || {}) }]
                                    arr[slot] = { name: '', line: '', ...arr[slot], ...patch }
                                    return { ...x, [key]: arr }
                                  }))
                                  return (
                                    <div key={slot} className="grid gap-1" style={{ gridTemplateColumns: '1fr 76px' }}>
                                      <input value={entry.name || ''} onChange={e => setSlot({ name: e.target.value.toUpperCase() })}
                                        placeholder={key === 'topBat' ? 'J. BARENDSE' : 'A. ALLISON'}
                                        className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs text-pb-text font-mono placeholder:text-pb-faintest" />
                                      <input value={entry.line || ''} onChange={e => setSlot({ line: e.target.value })}
                                        placeholder={key === 'topBat' ? '64 (71)' : '4/29 (9.4)'}
                                        className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs text-pb-text font-mono placeholder:text-pb-faintest" />
                                    </div>
                                  )
                                })}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                  <button onClick={() => setResults(rows => [...rows, { grade: '', opp: '', oppMono: '', us: '', them: '', outcome: 'W', margin: '', oppLogo: null }])}
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
                  <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-2">Auto-fill from match link</p>
                  <div className="flex gap-2">
                    <input type="text" value={scUrlInput} onChange={e => { setScUrlInput(e.target.value); setScUrlStatus(null) }}
                      placeholder="Match link or match ID (e.g. 37af9ea5-…)"
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
                          <label className="block font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase mb-1">Search Club</label>
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

            {/* Events — club-event / announcement posters */}
            {activeTab === 'events' && (
              <section className="pb-card p-4">
                <EventPostEditor
                  event={event} setEvent={setEvent}
                  presetKey={eventPreset} onPickPreset={onPickPreset} setPresetKey={setEventPreset}
                  templateId={templateId} setTemplateId={setTemplateId}
                  motifKey={eventMotifKey} setMotifKey={setEventMotifKey}
                  bgImage={eventBg} setBgImage={setEventBg}
                  bgOpacity={eventBgOpacity} setBgOpacity={setEventBgOpacity}
                />
              </section>
            )}

            </>)}
          </div>
        )}
      />

      {/* Hidden full-size render for export */}
      <div style={{ position: 'absolute', left: '-9999px', top: 0, pointerEvents: 'none', zIndex: -1 }}>
        {isBlankTab && pages.count > 1 ? (
          // One full-size node per carousel page, captured in turn on export.
          pages.all().map((pageItems, i) => (
            <div key={i} ref={(el) => { pageRefs.current[i] = el }} style={{ ...fontStyle, width: W, height: H, position: 'relative' }}>
              {bgActive && <SocialBackground variant={bgStyle} colors={bgResolvedColors} size={W} height={H} style={{ position: 'absolute', inset: 0 }} />}
              <BlankCanvas team={team} palette={templatePalette} items={pageItems} data={blankData} width={W} height={H} />
            </div>
          ))
        ) : (
          <div ref={renderRef} style={{ ...fontStyle, width: W, height: H, position: 'relative' }}>
            {bgActive && <SocialBackground variant={bgStyle} colors={bgResolvedColors} size={W} height={H} style={{ position: 'absolute', inset: 0 }} />}
            <TemplateComponent team={team} opponent={oppData} match={matchData} players={templatePlayers} palette={templatePalette} headline={headline} {...extraProps} />
            {customEdit && !isBlankTab && (
              <BlankCanvas team={team} palette={templatePalette} items={overlay.items} data={blankData} transparent width={W} height={H} style={{ position: 'absolute', inset: 0 }} />
            )}
          </div>
        )}
      </div>

      <ImageEditorModal
        open={!!editor}
        source={editor?.source}
        title={editor?.key === 'hero' ? 'Edit Hero Image' : editor?.key === 'blankimg' ? 'Edit Image' : 'Edit Sponsor Logo'}
        aspect={null}
        outputType="image/png"
        outputName={editor?.key === 'hero' ? 'hero.png' : editor?.key === 'blankimg' ? 'image.png' : 'sponsor.png'}
        onCancel={() => setEditor(null)}
        onApply={async (file) => {
          const e = editor
          setEditor(null)
          if (!e) return
          if (e.key === 'hero') {
            if (heroImage.blobUrl) URL.revokeObjectURL(heroImage.blobUrl)
            setHeroImage({ blobUrl: URL.createObjectURL(file) })
          } else if (e.key === 'blankimg' && e.itemId) {
            record('Replace image')
            layer.update(e.itemId, { src: URL.createObjectURL(file) })
          } else if (typeof e.sponsorIdx === 'number') {
            applySponsorBlob(e.sponsorIdx, file, e.sponsorName)
          }
        }}
      />
    </>
  )
}
