import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { Label, Card, Btn, PageHeader, PbSpinner } from '../lib/presskit'

// ─── Static config ────────────────────────────────────────────────────────────

const TARGETS = [
  { key: 'player_career',    label: 'Player career',     shape: 'aggregate', dim: 'player' },
  { key: 'player_season',    label: 'Player season',     shape: 'aggregate', dim: 'player_season' },
  { key: 'player_grade',     label: 'Player by grade',   shape: 'aggregate', dim: 'player_grade' },
  { key: 'innings_list',     label: 'Innings list',      shape: 'list',      dim: 'innings' },
  { key: 'spell_list',       label: 'Bowling spells',    shape: 'list',      dim: 'spell' },
  { key: 'match_list',       label: 'Match list',        shape: 'list',      dim: 'match' },
  { key: 'partnership_list', label: 'Partnerships',      shape: 'list',      dim: 'partnership' },
]

// Display label + decimal-flag for every metric we know about, keyed by metric name.
const METRIC_LABELS = {
  matches: { label: 'Matches', decimal: false },
  seasons_played: { label: 'Seasons', decimal: false },
  batting_innings: { label: 'Inns', decimal: false },
  runs: { label: 'Runs', decimal: false },
  not_outs: { label: 'NO', decimal: false },
  balls_faced: { label: 'Balls', decimal: false },
  batting_average: { label: 'Avg', decimal: true },
  batting_strike_rate: { label: 'SR', decimal: true },
  high_score: { label: 'HS', decimal: false },
  fifties: { label: '50s', decimal: false },
  hundreds: { label: '100s', decimal: false },
  ducks: { label: 'Ducks', decimal: false },
  fours: { label: '4s', decimal: false },
  sixes: { label: '6s', decimal: false },
  bowling_innings: { label: 'Spells', decimal: false },
  wickets: { label: 'Wkts', decimal: false },
  overs: { label: 'Overs', decimal: true },
  runs_conceded: { label: 'R Conc', decimal: false },
  bowling_average: { label: 'Bowl Avg', decimal: true },
  bowling_economy: { label: 'Econ', decimal: true },
  bowling_strike_rate: { label: 'Bowl SR', decimal: true },
  five_wicket_innings: { label: '5w', decimal: false },
  maidens: { label: 'Mdns', decimal: false },
  best_bowling_wickets: { label: 'BBW', decimal: false },
  catches: { label: 'Ct', decimal: false },
  run_outs: { label: 'RO', decimal: false },
  stumpings: { label: 'St', decimal: false },
  balls: { label: 'Balls', decimal: false },
  strike_rate: { label: 'SR', decimal: true },
  batting_position: { label: 'Pos', decimal: false },
  innings_number: { label: 'Inn#', decimal: false },
  economy: { label: 'Econ', decimal: true },
  wides: { label: 'Wd', decimal: false },
  no_balls: { label: 'NB', decimal: false },
  team_runs: { label: 'For', decimal: false },
  team_wickets: { label: 'Wkts For', decimal: false },
  opp_runs: { label: 'Against', decimal: false },
  opp_wickets: { label: 'Wkts Agst', decimal: false },
  margin_runs: { label: 'Margin', decimal: false },
  wicket_number: { label: 'Wkt #', decimal: false },
  batter1_runs: { label: 'B1 R', decimal: false },
  batter2_runs: { label: 'B2 R', decimal: false },
}

const OPERATORS = [
  { key: 'gte', label: 'at least' },
  { key: 'gt',  label: 'more than' },
  { key: 'eq',  label: 'exactly' },
  { key: 'lte', label: 'at most' },
  { key: 'lt',  label: 'less than' },
  { key: 'ne',  label: 'not equal' },
]

const PRESET_GROUPS = [
  {
    key: 'popular', label: 'Popular', defaultOpen: true,
    items: [
      { type: 'preset', label: 'Run scorers (all-time)',     target: 'player_career',    sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Wicket takers (all-time)',   target: 'player_career',    sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best batting averages',      target: 'player_career',    sortBy: 'batting_average',     sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Best bowling averages',      target: 'player_career',    sortBy: 'bowling_average',     sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'All-rounders',               target: 'player_career',    sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '500' }, { field: 'wickets', op: 'gte', value: '50' }], context: {} },
      { type: 'preset', label: 'Highest individual scores',  target: 'innings_list',     sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best spells (by wickets)',   target: 'spell_list',       sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Biggest partnerships',       target: 'partnership_list', sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most matches played',        target: 'player_career',    sortBy: 'matches',             sortDir: 'desc', filters: [], context: {} },
    ],
  },
  {
    key: 'season', label: 'Season Honours', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Most runs in a season',         target: 'player_season', sortBy: 'runs',            sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best batting avg in a season',  target: 'player_season', sortBy: 'batting_average', sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Most wickets in a season',      target: 'player_season', sortBy: 'wickets',         sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best bowling avg in a season',  target: 'player_season', sortBy: 'bowling_average', sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Most matches in a season',      target: 'player_season', sortBy: 'matches',         sortDir: 'desc', filters: [], context: {} },
    ],
  },
  {
    key: 'batting', label: 'Batting', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Run scorers (all-time)',     target: 'player_career', sortBy: 'runs',            sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best batting averages',      target: 'player_career', sortBy: 'batting_average', sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Highest individual scores',  target: 'innings_list',  sortBy: 'runs',            sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Centurions',                 target: 'player_career', sortBy: 'hundreds',        sortDir: 'desc', filters: [{ field: 'hundreds', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most no outs',               target: 'player_career', sortBy: 'not_outs',        sortDir: 'desc', filters: [{ field: 'not_outs', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Hundreds in losses',         target: 'innings_list',  sortBy: 'runs',            sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '100' }], context: { result: 'lost' } },
      { type: 'preset', label: 'Captain runs',               target: 'player_career', sortBy: 'runs',            sortDir: 'desc', filters: [], context: { captain_only: true } },
      { type: 'preset', label: 'Finals run scorers',         target: 'player_career', sortBy: 'runs',            sortDir: 'desc', filters: [], context: { finals_only: true } },
      { type: 'derived', key: 'consecutive_ducks',   label: 'Longest duck streak',       description: 'Most innings in a row scoring zero.' },
      { type: 'derived', key: 'consecutive_fifties', label: 'Longest 50+ streak',         description: 'Most innings in a row scoring 50+.' },
      { type: 'derived', key: 'carried_bat',         label: 'Carrying the bat',           description: 'Openers not out when team was bowled out.' },
      { type: 'derived', key: 'most_runs_first_n',   label: 'Most runs after X matches',  description: 'Who scored the most in their first N matches (set N in Context).' },
      { type: 'derived', key: 'milestone_runs',      label: 'Fastest to milestone',       description: 'Who reached a runs milestone in fewest matches (set milestone in Context).' },
    ],
  },
  {
    key: 'bowling', label: 'Bowling', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Wicket takers (all-time)', target: 'player_career', sortBy: 'wickets',           sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best bowling averages',    target: 'player_career', sortBy: 'bowling_average',   sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Five-for club',            target: 'player_career', sortBy: 'five_wicket_innings', sortDir: 'desc', filters: [{ field: 'five_wicket_innings', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Best spells (by wickets)', target: 'spell_list',    sortBy: 'wickets',           sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most wides bowled',        target: 'player_career', sortBy: 'wides',             sortDir: 'desc', filters: [{ field: 'wides', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most no-balls bowled',     target: 'player_career', sortBy: 'no_balls',          sortDir: 'desc', filters: [{ field: 'no_balls', op: 'gte', value: '1' }], context: {} },
    ],
  },
  {
    key: 'fielding', label: 'Fielding & Keeping', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Wicket-keeper catches', target: 'player_career', sortBy: 'catches',   sortDir: 'desc', filters: [], context: { keeper_only: true } },
      { type: 'preset', label: 'Most catches',          target: 'player_career', sortBy: 'catches',   sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most run outs',         target: 'player_career', sortBy: 'run_outs',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most stumpings',        target: 'player_career', sortBy: 'stumpings', sortDir: 'desc', filters: [{ field: 'stumpings', op: 'gte', value: '1' }], context: {} },
    ],
  },
  {
    key: 'partnerships', label: 'Partnerships', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Biggest partnerships', target: 'partnership_list', sortBy: 'runs', sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'best_partnership_pair', label: 'Best partnership by pair', description: 'Best stand for each pair of batters.' },
    ],
  },
  {
    key: 'match', label: 'Match', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Highest team scores',      target: 'match_list',    sortBy: 'team_runs',    sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Biggest winning margins',  target: 'match_list',    sortBy: 'margin_runs',  sortDir: 'desc', filters: [{ field: 'margin_runs', op: 'gt', value: '0' }], context: {} },
      { type: 'preset', label: 'Finals run scorers',       target: 'player_career', sortBy: 'runs',         sortDir: 'desc', filters: [], context: { finals_only: true } },
    ],
  },
]

const RESULT_OPTIONS = [
  { value: '', label: 'Any result' },
  { value: 'won', label: 'Won' },
  { value: 'lost', label: 'Lost' },
  { value: 'drawn', label: 'Drawn' },
  { value: 'tied', label: 'Tied' },
]

const DISMISSAL_OPTIONS = [
  { value: '', label: 'Any dismissal' },
  { value: 'bowled', label: 'Bowled' },
  { value: 'caught', label: 'Caught' },
  { value: 'lbw', label: 'LBW' },
  { value: 'run out', label: 'Run out' },
  { value: 'stumped', label: 'Stumped' },
  { value: 'hit wicket', label: 'Hit wicket' },
  { value: 'not out', label: 'Not out' },
]

// Columns to display per target shape. Match the keys to backend response keys.
const COLUMN_SETS = {
  player_career:    ['matches','batting_innings','runs','not_outs','batting_average','high_score','hundreds','fifties','ducks','wickets','bowling_average','bowling_economy','five_wicket_innings','catches','run_outs','stumpings'],
  player_season:    ['matches','batting_innings','runs','batting_average','high_score','hundreds','fifties','wickets','bowling_average','catches'],
  player_grade:     ['matches','batting_innings','runs','batting_average','high_score','hundreds','wickets','bowling_average','catches'],
  innings_list:     ['runs','balls','fours','sixes','strike_rate','batting_position'],
  spell_list:       ['overs','maidens','runs','wickets','economy'],
  match_list:       ['team_runs','team_wickets','opp_runs','opp_wickets','margin_runs'],
  partnership_list: ['runs','balls','wicket_number','batter1_runs','batter2_runs'],
}

const CONTEXT_KEYS = [
  'season_id','grade_id','grade_name','opposition','date_from','date_to',
  'min_year','max_year','finals_only','captain_only','keeper_only','result',
  'dismissal','position_min','position_max',
  'first_n_matches','milestone_runs',
]

// Category groupings for the field picker. Field membership is intersected
// with each target's allowed metrics on render — categories with no eligible
// fields hide automatically. Kept in sync with backend METRIC_CATEGORIES.
const FILTER_CATEGORIES = [
  { key: 'participation', label: 'Participation',
    fields: ['matches','seasons_played','batting_innings','bowling_innings'] },
  { key: 'batting', label: 'Batting',
    fields: ['runs','not_outs','batting_average','batting_strike_rate','high_score',
             'fifties','hundreds','ducks','fours','sixes','balls_faced','balls',
             'strike_rate','batting_position'] },
  { key: 'bowling', label: 'Bowling',
    fields: ['wickets','overs','maidens','bowling_average','bowling_economy',
             'bowling_strike_rate','five_wicket_innings','best_bowling_wickets',
             'runs_conceded','wides','no_balls','economy'] },
  { key: 'fielding', label: 'Fielding',
    fields: ['catches','run_outs','stumpings'] },
  { key: 'match', label: 'Match',
    fields: ['team_runs','team_wickets','opp_runs','opp_wickets','margin_runs','innings_number'] },
  { key: 'partnership', label: 'Partnership',
    fields: ['wicket_number','batter1_runs','batter2_runs'] },
]

const CATEGORY_LOOKUP = (() => {
  const m = {}
  FILTER_CATEGORIES.forEach(c => c.fields.forEach(f => { if (!m[f]) m[f] = c }))
  return m
})()

const OPERATOR_SYMBOLS = { gte: '≥', gt: '>', eq: '=', lte: '≤', lt: '<', ne: '≠' }

let _treeIdCounter = 1000
const newTreeId = () => ++_treeIdCounter

const emptyTree = () => ({ id: newTreeId(), type: 'group', op: 'AND', clauses: [] })

function flatToTree(filters) {
  return {
    id: newTreeId(),
    type: 'group',
    op: 'AND',
    clauses: (filters || []).map(f => ({
      id: newTreeId(),
      type: 'leaf',
      field: f.field,
      op: f.op,
      value: f.value,
    })),
  }
}

function ensureTreeIds(node) {
  if (!node || typeof node !== 'object') return node
  const withId = { ...node, id: node.id ?? newTreeId() }
  if (withId.type === 'group') {
    withId.clauses = (withId.clauses || []).map(ensureTreeIds)
  }
  return withId
}

function treeLeafCount(node) {
  if (!node) return 0
  if (node.type === 'leaf') return (node.field && node.value !== '' && node.value != null) ? 1 : 0
  return (node.clauses || []).reduce((n, c) => n + treeLeafCount(c), 0)
}

function treeFields(node) {
  const out = new Set()
  const walk = (n) => {
    if (!n) return
    if (n.type === 'leaf' && n.field) out.add(n.field)
    if (n.type === 'group') (n.clauses || []).forEach(walk)
  }
  walk(node)
  return [...out]
}

// Strip null/empty leaves so the backend / saved JSON never carries placeholder rows.
function cleanTree(node) {
  if (!node) return null
  if (node.type === 'leaf') {
    if (!node.field || !node.op || node.value === '' || node.value == null) return null
    return { type: 'leaf', field: node.field, op: node.op, value: node.value }
  }
  if (node.type === 'group') {
    const cleaned = (node.clauses || []).map(cleanTree).filter(Boolean)
    if (cleaned.length === 0) return null
    return { type: 'group', op: node.op || 'AND', clauses: cleaned }
  }
  return null
}

const DEFAULT_QUERY = {
  target: 'player_career',
  sortBy: 'runs',
  sortDir: 'desc',
  limit: 100,
  filterTree: emptyTree(),
  context: {},
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function encodeQueryToParams(q) {
  const p = new URLSearchParams()
  p.set('target', q.target)
  p.set('sort', q.sortBy)
  p.set('dir', q.sortDir)
  if (q.limit !== DEFAULT_QUERY.limit) p.set('limit', q.limit)
  const cleaned = cleanTree(q.filterTree)
  if (cleaned) p.set('ft', JSON.stringify(cleaned))
  Object.entries(q.context || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || v === false) return
    p.set(`c_${k}`, v === true ? '1' : String(v))
  })
  return p
}

function decodeParamsToQuery(params) {
  const target = params.get('target') || DEFAULT_QUERY.target
  const sortBy = params.get('sort') || DEFAULT_QUERY.sortBy
  const sortDir = params.get('dir') || DEFAULT_QUERY.sortDir
  const limit = Number(params.get('limit')) || DEFAULT_QUERY.limit
  let filterTree = emptyTree()
  const ftRaw = params.get('ft')
  if (ftRaw) {
    try { filterTree = ensureTreeIds(JSON.parse(ftRaw)) } catch { /* ignore */ }
  } else {
    // Back-compat: ?f=field:op:value repeated → flat AND tree
    const flat = []
    params.getAll('f').forEach(raw => {
      const parts = raw.split(':')
      if (parts.length >= 3) flat.push({ field: parts[0], op: parts[1], value: parts.slice(2).join(':') })
    })
    if (flat.length) filterTree = flatToTree(flat)
  }
  const context = {}
  CONTEXT_KEYS.forEach(k => {
    const v = params.get(`c_${k}`)
    if (v == null) return
    if (k === 'finals_only' || k === 'captain_only' || k === 'keeper_only') {
      context[k] = v === '1' || v === 'true'
    } else {
      context[k] = v
    }
  })
  return { target, sortBy, sortDir, limit, filterTree, context }
}

function csvEscape(v) {
  if (v == null) return ''
  const s = String(v)
  if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`
  return s
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

const inputCls = 'bg-pb-surface border border-pb-hairline2 text-pb-text text-xs rounded px-2 py-1.5 focus:outline-none focus:border-pb-accent w-full'
const selectCls = inputCls + ' cursor-pointer'

function ContextFiltersPanel({ ctx, onChange, seasons, grades, targetShape, activeDerived }) {
  const set = (k, v) => onChange({ ...ctx, [k]: v })
  const showInningsFilters = targetShape === 'list' || targetShape === 'aggregate'
  return (
    <div className="flex flex-col gap-2.5">
      <div>
        <Label>Season</Label>
        <select className={selectCls + ' mt-1'} value={ctx.season_id || ''} onChange={e => set('season_id', e.target.value)}>
          <option value="">All seasons</option>
          {(seasons || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div>
        <Label>Grade</Label>
        <select className={selectCls + ' mt-1'} value={ctx.grade_id || ''} onChange={e => set('grade_id', e.target.value)}>
          <option value="">All grades</option>
          {(grades || []).map(g => <option key={g.id} value={g.id}>{g.display_name || g.name}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <Label>From</Label>
          <input type="date" className={inputCls + ' mt-1'} value={ctx.date_from || ''} onChange={e => set('date_from', e.target.value)} />
        </div>
        <div>
          <Label>To</Label>
          <input type="date" className={inputCls + ' mt-1'} value={ctx.date_to || ''} onChange={e => set('date_to', e.target.value)} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <Label>Min year</Label>
          <input type="number" className={inputCls + ' mt-1'} value={ctx.min_year || ''} placeholder="1996" onChange={e => set('min_year', e.target.value)} />
        </div>
        <div>
          <Label>Max year</Label>
          <input type="number" className={inputCls + ' mt-1'} value={ctx.max_year || ''} placeholder="2026" onChange={e => set('max_year', e.target.value)} />
        </div>
      </div>
      <div>
        <Label>Opposition</Label>
        <input className={inputCls + ' mt-1'} value={ctx.opposition || ''} placeholder="e.g. Bayswater" onChange={e => set('opposition', e.target.value)} />
      </div>
      <div>
        <Label>Result</Label>
        <select className={selectCls + ' mt-1'} value={ctx.result || ''} onChange={e => set('result', e.target.value)}>
          {RESULT_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        {[
          { k: 'finals_only',  label: 'Finals only' },
          { k: 'captain_only', label: 'As captain' },
          { k: 'keeper_only',  label: 'As keeper' },
        ].map(({ k, label }) => (
          <label key={k} className="flex items-center gap-1 text-xs text-pb-dim cursor-pointer">
            <input type="checkbox" checked={!!ctx[k]} onChange={e => set(k, e.target.checked)} />
            {label}
          </label>
        ))}
      </div>
      {showInningsFilters && (
        <>
          <div>
            <Label>Dismissal</Label>
            <select className={selectCls + ' mt-1'} value={ctx.dismissal || ''} onChange={e => set('dismissal', e.target.value)}>
              {DISMISSAL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <div>
              <Label>Position ≥</Label>
              <input type="number" min="1" max="11" className={inputCls + ' mt-1'} value={ctx.position_min || ''} placeholder="1" onChange={e => set('position_min', e.target.value)} />
            </div>
            <div>
              <Label>Position ≤</Label>
              <input type="number" min="1" max="11" className={inputCls + ' mt-1'} value={ctx.position_max || ''} placeholder="11" onChange={e => set('position_max', e.target.value)} />
            </div>
          </div>
        </>
      )}
      {activeDerived === 'most_runs_first_n' && (
        <div>
          <Label>First N matches</Label>
          <select className={selectCls + ' mt-1'} value={ctx.first_n_matches || '50'}
                  onChange={e => set('first_n_matches', e.target.value)}>
            {[10, 25, 50, 100, 200].map(n => <option key={n} value={n}>First {n}</option>)}
          </select>
        </div>
      )}
      {activeDerived === 'milestone_runs' && (
        <div>
          <Label>Runs milestone</Label>
          <select className={selectCls + ' mt-1'} value={ctx.milestone_runs || '1000'}
                  onChange={e => set('milestone_runs', e.target.value)}>
            {[100, 500, 1000, 2000, 5000].map(n => <option key={n} value={n}>{n.toLocaleString()} runs</option>)}
          </select>
        </div>
      )}
    </div>
  )
}

// ─── Filter Bar (top-of-page boolean filter tree) ─────────────────────────────

function categoriesForTarget(targetMetrics) {
  const metricSet = new Set(targetMetrics || [])
  return FILTER_CATEGORIES
    .map(c => ({ ...c, fields: c.fields.filter(f => metricSet.has(f)) }))
    .filter(c => c.fields.length > 0)
}

function FieldPicker({ open, onClose, onPick, categories, anchorRect }) {
  const [search, setSearch] = useState('')
  useEffect(() => { if (open) setSearch('') }, [open])
  if (!open) return null
  const term = search.trim().toLowerCase()
  const filtered = categories.map(c => ({
    ...c,
    fields: c.fields.filter(f => !term || (METRIC_LABELS[f]?.label || f).toLowerCase().includes(term) || f.toLowerCase().includes(term)),
  })).filter(c => c.fields.length > 0)

  return (
    <>
      <div className="fixed inset-0 z-30" onClick={onClose} />
      <div
        className="absolute z-40 mt-1 bg-pb-bg pb-card shadow-xl w-[300px] max-h-[420px] overflow-auto pb-scroll"
        style={{ top: anchorRect?.bottom ? `${anchorRect.bottom + window.scrollY}px` : undefined, left: anchorRect?.left ? `${anchorRect.left + window.scrollX}px` : undefined }}
      >
        <div className="sticky top-0 bg-pb-bg pb-hairline-b p-2">
          <input
            autoFocus
            className={inputCls}
            placeholder="Search metrics…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="py-1">
          {filtered.length === 0 && <p className="text-pb-faintest text-xs px-3 py-3">No matching metrics for this query type.</p>}
          {filtered.map(c => (
            <div key={c.key} className="px-2 py-1.5">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest px-1 mb-1">{c.label.toUpperCase()}</div>
              <div className="grid grid-cols-2 gap-1">
                {c.fields.map(f => (
                  <button
                    key={f}
                    onClick={() => { onPick(f); onClose() }}
                    className="text-left px-2 py-1.5 rounded hover:bg-pb-surface2 font-mono text-[11px] text-pb-dim hover:text-pb-text transition truncate"
                  >
                    {METRIC_LABELS[f]?.label || f}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function FilterLeaf({ leaf, categories, onChange, onRemove }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [anchor, setAnchor] = useState(null)
  const fieldBtnRef = useRef(null)
  const openPicker = () => {
    if (fieldBtnRef.current) setAnchor(fieldBtnRef.current.getBoundingClientRect())
    setPickerOpen(true)
  }
  const cat = leaf.field ? CATEGORY_LOOKUP[leaf.field] : null
  const fieldLabel = leaf.field ? (METRIC_LABELS[leaf.field]?.label || leaf.field) : 'Choose metric'
  return (
    <div className="flex items-center gap-1.5 bg-pb-surface border border-pb-hairline rounded-md px-1 py-1 hover:border-pb-hairline2 transition">
      <button
        ref={fieldBtnRef}
        onClick={openPicker}
        className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-pb-surface2 transition min-w-[140px] text-left"
      >
        {cat && <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">{cat.label}</span>}
        <span className="text-pb-text font-medium text-xs truncate">{fieldLabel}</span>
        <span className="text-pb-faint text-[10px]">▾</span>
      </button>
      <select
        className={selectCls + ' w-14 text-center'}
        value={leaf.op}
        onChange={e => onChange({ ...leaf, op: e.target.value })}
        title="Operator"
      >
        {OPERATORS.map(o => (
          <option key={o.key} value={o.key}>{OPERATOR_SYMBOLS[o.key] || o.key}</option>
        ))}
      </select>
      <input
        type="number"
        className={inputCls + ' w-20'}
        value={leaf.value}
        placeholder="0"
        onChange={e => onChange({ ...leaf, value: e.target.value })}
      />
      <button
        onClick={onRemove}
        className="text-pb-faint hover:text-pb-red font-mono text-base leading-none px-1.5"
        title="Remove filter"
      >×</button>
      <FieldPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(field) => onChange({ ...leaf, field })}
        categories={categories}
        anchorRect={anchor}
      />
    </div>
  )
}

function FilterGroup({ node, categories, onChange, onRemove, depth = 0 }) {
  const isRoot = depth === 0
  const setOp = (op) => onChange({ ...node, op })
  const addLeaf = () => {
    const cl = [...(node.clauses || []), { id: newTreeId(), type: 'leaf', field: '', op: 'gte', value: '' }]
    onChange({ ...node, clauses: cl })
  }
  const addGroup = () => {
    const cl = [...(node.clauses || []), {
      id: newTreeId(), type: 'group', op: 'OR', clauses: [
        { id: newTreeId(), type: 'leaf', field: '', op: 'gte', value: '' },
      ],
    }]
    onChange({ ...node, clauses: cl })
  }
  const updateChild = (id, next) => {
    if (next == null) {
      onChange({ ...node, clauses: node.clauses.filter(c => c.id !== id) })
      return
    }
    onChange({ ...node, clauses: node.clauses.map(c => c.id === id ? next : c) })
  }
  const isEmpty = !node.clauses || node.clauses.length === 0
  return (
    <div className={isRoot ? '' : 'border-l-2 border-pb-accent/40 pl-3 ml-1 my-1'}>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <Label>{isRoot ? 'Filters' : 'Group'}</Label>
        <div className="flex gap-1">
          {['AND','OR'].map(op => (
            <button
              key={op}
              onClick={() => setOp(op)}
              className={`px-2 py-0.5 font-mono text-[10px] tracking-wide2 rounded border transition ${node.op === op ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
            >
              {op}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button onClick={addLeaf} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">+ filter</button>
        <button onClick={addGroup} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">+ group</button>
        {!isRoot && (
          <button onClick={onRemove} className="text-pb-faint hover:text-pb-red font-mono text-base leading-none px-1">×</button>
        )}
      </div>
      {isEmpty && isRoot && (
        <p className="text-pb-faintest font-mono text-[10.5px] mb-2">No filters yet. Click <span className="text-pb-faint">+ filter</span> to narrow your results.</p>
      )}
      <div className="flex flex-wrap gap-1.5 items-center">
        {(node.clauses || []).map((c, i) => (
          <div key={c.id} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="font-mono text-[10px] tracking-wide2 text-pb-faint px-1.5 py-0.5 rounded bg-pb-surface2/50">{node.op}</span>
            )}
            {c.type === 'leaf' ? (
              <FilterLeaf
                leaf={c}
                categories={categories}
                onChange={(next) => updateChild(c.id, next)}
                onRemove={() => updateChild(c.id, null)}
              />
            ) : (
              <FilterGroup
                node={c}
                categories={categories}
                onChange={(next) => updateChild(c.id, next)}
                onRemove={() => updateChild(c.id, null)}
                depth={depth + 1}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function FilterBar({ tree, categories, onChange, onClear }) {
  const count = treeLeafCount(tree)
  return (
    <div className="pb-card p-3 mb-5">
      <FilterGroup
        node={tree}
        categories={categories}
        onChange={onChange}
        onRemove={() => {}}
        depth={0}
      />
      {count > 0 && (
        <div className="flex justify-end pt-2 mt-2 pb-hairline-t">
          <button onClick={onClear} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">Clear all filters</button>
        </div>
      )}
    </div>
  )
}

function SaveReportModal({ open, onClose, onSave, defaultTitle, initial }) {
  const [title, setTitle] = useState(initial?.title || defaultTitle || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [visibility, setVisibility] = useState(initial?.visibility || 'club')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (open) {
      setTitle(initial?.title || defaultTitle || '')
      setDescription(initial?.description || '')
      setVisibility(initial?.visibility || 'club')
      setError(null)
    }
  }, [open, initial, defaultTitle])
  if (!open) return null
  const submit = async () => {
    if (title.trim().length < 2) { setError('Title is required'); return }
    setSaving(true); setError(null)
    try { await onSave({ title: title.trim(), description: description.trim() || null, visibility }) }
    catch (e) { setError(e.message); setSaving(false); return }
    setSaving(false)
  }
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-pb-bg pb-card max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
        <Label>{initial ? 'EDIT REPORT' : 'SAVE REPORT'}</Label>
        <h3 className="text-pb-text font-semibold text-lg mt-1 mb-4">{initial ? 'Update saved report' : 'Save this query'}</h3>
        <div className="flex flex-col gap-3">
          <div>
            <Label>Title</Label>
            <input className={inputCls + ' mt-1'} value={title} onChange={e => setTitle(e.target.value)} maxLength={120} />
          </div>
          <div>
            <Label>Description</Label>
            <textarea className={inputCls + ' mt-1'} rows="2" value={description} maxLength={500} onChange={e => setDescription(e.target.value)} placeholder="Optional context for whoever opens this report" />
          </div>
          <div>
            <Label>Visibility</Label>
            <div className="flex gap-2 mt-1">
              {['club','private'].map(v => (
                <button key={v} onClick={() => setVisibility(v)} className={`flex-1 py-1.5 font-mono text-[10.5px] tracking-wide2 rounded border ${visibility === v ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                  {v === 'club' ? 'CLUB · PUBLIC' : 'PRIVATE'}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-pb-faintest mt-1">{visibility === 'club' ? 'Anyone visiting this club can view this report.' : 'Only you (when logged in) will see this report in the list.'}</p>
          </div>
          {error && <p className="text-pb-red text-sm">{error}</p>}
          <div className="flex gap-2 justify-end pt-2">
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn primary onClick={submit} disabled={saving}>{saving ? 'Saving…' : (initial ? 'Update' : 'Save')}</Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function StatLab() {
  const { clubSlug, reportSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  const { org, seasons, loading: clubLoading } = useClubData(orgId)
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [schema, setSchema] = useState(null)
  const [query, setQuery] = useState(() => decodeParamsToQuery(searchParams))
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [hasQueried, setHasQueried] = useState(false)
  const [error, setError] = useState(null)
  const [clientSort, setClientSort] = useState({ col: null, dir: null })

  const [reports, setReports] = useState([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [openReport, setOpenReport] = useState(null) // when viewing a saved report
  const [saveOpen, setSaveOpen] = useState(false)
  const [editingReport, setEditingReport] = useState(null)

  const [grades, setGrades] = useState([])
  const [activeDerived, setActiveDerived] = useState(null)
  const [openGroups, setOpenGroups] = useState(() => Object.fromEntries(PRESET_GROUPS.map(g => [g.key, g.defaultOpen])))

  const queryRef = useRef(query)
  queryRef.current = query

  const activeDerivedRef = useRef(activeDerived)
  activeDerivedRef.current = activeDerived

  // Load schema once
  useEffect(() => {
    let cancelled = false
    api.statlabSchema().then(s => { if (!cancelled) setSchema(s) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  // Load grades whenever org changes
  useEffect(() => {
    if (!orgId) return
    api.getOrgGrades(orgId).then(setGrades).catch(() => setGrades([]))
  }, [orgId])

  // Load reports whenever org changes
  const refreshReports = useCallback(async () => {
    if (!orgId) return
    setReportsLoading(true)
    try { setReports(await api.statlabListReports(orgId)) }
    catch { setReports([]) }
    finally { setReportsLoading(false) }
  }, [orgId])
  useEffect(() => { refreshReports() }, [refreshReports])

  // Load a saved report when URL has reportSlug
  useEffect(() => {
    if (!orgId || !reportSlug) {
      setOpenReport(null)
      return
    }
    let cancelled = false
    api.statlabGetReport(reportSlug, orgId).then(r => {
      if (cancelled) return
      setOpenReport(r)
      const incoming = r.query_json || {}
      const q = { ...DEFAULT_QUERY, ...incoming }
      // Migrate legacy reports (flat filters array) and ensure tree node ids
      if (incoming.filterTree) {
        q.filterTree = ensureTreeIds(incoming.filterTree)
      } else if (Array.isArray(incoming.filters) && incoming.filters.length) {
        q.filterTree = flatToTree(incoming.filters)
      } else {
        q.filterTree = emptyTree()
      }
      delete q.filters
      q.context = q.context || {}
      setQuery(q)
      setHasQueried(false)
    }).catch(() => setOpenReport(null))
    return () => { cancelled = true }
  }, [orgId, reportSlug])

  const targetMeta = useMemo(() => TARGETS.find(t => t.key === query.target) || TARGETS[0], [query.target])
  const targetMetrics = useMemo(() => schema?.targets?.[query.target]?.metrics || [], [schema, query.target])

  // If user switches target and the current sortBy isn't valid, snap to default
  useEffect(() => {
    if (!schema) return
    const validMetrics = schema.targets?.[query.target]?.metrics || []
    if (!validMetrics.includes(query.sortBy)) {
      const def = schema.targets?.[query.target]?.default_sort || validMetrics[0]
      if (def) setQuery(q => ({ ...q, sortBy: def }))
    }
  }, [query.target, schema])

  // Sync URL whenever query changes
  useEffect(() => {
    if (reportSlug) return // when viewing a saved report, keep URL clean
    const p = encodeQueryToParams(query)
    setSearchParams(p, { replace: true })
  }, [query, reportSlug, setSearchParams])

  if (inactive) return <ClubInactive />

  const runQuery = useCallback(async (overrideQuery, overrideDerived = undefined) => {
    if (!orgId) return
    const q = overrideQuery || queryRef.current
    // undefined = preserve current derived; null = clear it; string = set new derived
    const useDerived = overrideDerived !== undefined ? overrideDerived : activeDerivedRef.current
    setLoading(true); setError(null); setHasQueried(true); setClientSort({ col: null, dir: null })
    setActiveDerived(useDerived)
    const cleaned = cleanTree(q.filterTree)
    try {
      let data
      if (useDerived) {
        data = await api.statlabDerived(orgId, useDerived, { limit: q.limit, context: q.context })
      } else {
        data = await api.statlabQuery(orgId, {
          target: q.target, sortBy: q.sortBy, sortDir: q.sortDir,
          limit: q.limit, filterTree: cleaned, context: q.context,
        })
      }
      setRows(data)
    } catch (e) {
      setError(e.message); setRows([])
    } finally { setLoading(false) }
  }, [orgId])

  const applyPreset = useCallback(async (preset) => {
    const next = {
      target: preset.target,
      sortBy: preset.sortBy,
      sortDir: preset.sortDir,
      limit: DEFAULT_QUERY.limit,
      filterTree: flatToTree(preset.filters || []),
      context: preset.context || {},
    }
    setQuery(next)
    setOpenReport(null)
    if (reportSlug) navigate(`/${clubSlug}/statlab`, { replace: true })
    await runQuery(next, null)
  }, [runQuery, clubSlug, navigate, reportSlug])

  const applyDerived = useCallback(async (name) => {
    const next = { ...queryRef.current, filterTree: emptyTree() }
    setQuery(next)
    await runQuery(next, name)
  }, [runQuery])

  const applyGroupItem = useCallback(async (item) => {
    if (item.type === 'derived') {
      await applyDerived(item.key)
    } else {
      await applyPreset(item)
    }
  }, [applyPreset, applyDerived])

  const toggleGroup = (key) => setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }))

  const resetAll = () => {
    setQuery(DEFAULT_QUERY)
    setRows([]); setHasQueried(false); setError(null); setActiveDerived(null)
    setOpenReport(null)
    if (reportSlug) navigate(`/${clubSlug}/statlab`, { replace: true })
  }

  const handleColSort = (col) => {
    const dir = clientSort.col === col && clientSort.dir === 'desc' ? 'asc' : 'desc'
    setClientSort({ col, dir })
  }

  const sortedRows = useMemo(() => {
    if (!clientSort.col) return rows
    return [...rows].sort((a, b) => {
      const va = a[clientSort.col]
      const vb = b[clientSort.col]
      const nva = typeof va === 'number' ? va : parseFloat(va)
      const nvb = typeof vb === 'number' ? vb : parseFloat(vb)
      const an = isFinite(nva), bn = isFinite(nvb)
      if (an && bn) return clientSort.dir === 'asc' ? nva - nvb : nvb - nva
      const sa = String(va ?? ''), sb = String(vb ?? '')
      return clientSort.dir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
    })
  }, [rows, clientSort])

  // Columns to render in the results table
  const tableColumns = useMemo(() => {
    if (activeDerived && schema?.derived?.[activeDerived]) {
      return schema.derived[activeDerived].columns
    }
    const set = COLUMN_SETS[query.target] || []
    // Promote filtered fields and the active sort to the front
    const filteredKeys = treeFields(query.filterTree)
    const order = []
    const seen = new Set()
    ;[...filteredKeys, query.sortBy, ...set].forEach(k => {
      if (!seen.has(k) && METRIC_LABELS[k]) { order.push(k); seen.add(k) }
    })
    return order.map(k => ({ key: k, ...METRIC_LABELS[k] }))
  }, [query, schema, activeDerived])

  const downloadCSV = () => {
    if (!sortedRows.length) return
    const dimCols = entityHeader(query.target, activeDerived)
    const cols = activeDerived
      ? schema.derived[activeDerived].columns
      : tableColumns
    const header = [...dimCols.map(c => c.label), ...cols.map(c => c.label || c.key)]
    const lines = [header.join(',')]
    sortedRows.forEach(row => {
      const left = dimCols.map(c => csvEscape(row[c.key] ?? ''))
      const right = cols.map(c => csvEscape(row[c.key] ?? ''))
      lines.push([...left, ...right].join(','))
    })
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `statlab_${activeDerived || query.target}_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const saveReport = useCallback(async (payload) => {
    const q = queryRef.current
    const cleanedTree = cleanTree(q.filterTree)
    const queryJson = {
      target: q.target,
      sortBy: q.sortBy,
      sortDir: q.sortDir,
      limit: q.limit,
      filterTree: cleanedTree,
      context: q.context || {},
      derived: activeDerived || null,
    }
    if (editingReport) {
      await api.statlabPatchReport(editingReport.id, { ...payload, query_json: queryJson })
    } else {
      await api.statlabCreateReport({ ...payload, query_json: queryJson })
    }
    setSaveOpen(false)
    setEditingReport(null)
    refreshReports()
  }, [editingReport, activeDerived, refreshReports])

  const deleteReport = useCallback(async (r) => {
    if (!window.confirm(`Delete saved report "${r.title}"?`)) return
    await api.statlabDeleteReport(r.id)
    refreshReports()
    if (openReport?.id === r.id) {
      setOpenReport(null)
      navigate(`/${clubSlug}/statlab`)
    }
  }, [refreshReports, openReport, navigate, clubSlug])

  if (clubLoading || !schema) return <PbSpinner message="Loading…" />

  const canSave = !!user && user.club_id === orgId

  // ─── Layout ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={openReport ? 'SAVED REPORT' : 'STAT LAB · CUSTOM QUERY'}
          title={openReport ? openReport.title : 'Build your own table.'}
          meta={openReport
            ? [
                <span key="d">{openReport.description || `${org?.name || ''} · saved report`}</span>,
                openReport.owner_name ? <span key="o">by {openReport.owner_name}</span> : null,
                <span key="v">{openReport.view_count || 0} view{(openReport.view_count || 0) === 1 ? '' : 's'}</span>,
              ].filter(Boolean)
            : [<span key="s">{org?.name || ''} · Filter, sort, discover, share.</span>]
          }
          actions={openReport && canSave ? (
            <div className="flex gap-2">
              <Btn onClick={() => { setEditingReport(openReport); setSaveOpen(true) }}>Edit</Btn>
              <Btn onClick={() => deleteReport(openReport)}>Delete</Btn>
              <Btn onClick={() => { setOpenReport(null); navigate(`/${clubSlug}/statlab?${encodeQueryToParams(query).toString()}`) }}>Edit a copy</Btn>
            </div>
          ) : null}
        />

        {/* Target tabs */}
        <div className="flex gap-1 pb-hairline-b mb-4 overflow-x-auto pb-no-scrollbar">
          {TARGETS.map(t => (
            <button key={t.key} onClick={() => { setQuery(q => ({ ...q, target: t.key })); setRows([]); setHasQueried(false); setActiveDerived(null) }}
              className={`relative px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${query.target === t.key && !activeDerived ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'}`}>
              {t.label.toUpperCase()}
              {query.target === t.key && !activeDerived && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
            </button>
          ))}
        </div>

        {/* Filter bar — categorised picker, nested AND/OR */}
        <FilterBar
          tree={query.filterTree}
          categories={categoriesForTarget(targetMetrics)}
          onChange={(tree) => setQuery(q => ({ ...q, filterTree: tree }))}
          onClear={() => setQuery(q => ({ ...q, filterTree: emptyTree() }))}
        />

        <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5">
          {/* Left panel: controls */}
          <div className="space-y-4">
            <Card title="SORT BY">
              <select className={selectCls} value={query.sortBy} onChange={e => setQuery(q => ({ ...q, sortBy: e.target.value }))}>
                {targetMetrics.map(m => <option key={m} value={m}>{METRIC_LABELS[m]?.label || m}</option>)}
              </select>
              <div className="flex gap-1 mt-2">
                {['desc','asc'].map(d => (
                  <button key={d} onClick={() => setQuery(q => ({ ...q, sortDir: d }))}
                    className={`flex-1 py-1 font-mono text-[10px] tracking-wide2 rounded border transition ${query.sortDir === d ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                    {d === 'desc' ? 'HIGH → LOW' : 'LOW → HIGH'}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-2 items-center gap-2 mt-3">
                <Label>Limit</Label>
                <select className={selectCls} value={query.limit} onChange={e => setQuery(q => ({ ...q, limit: Number(e.target.value) }))}>
                  {[25, 50, 100, 200, 500].map(n => <option key={n} value={n}>Top {n}</option>)}
                </select>
              </div>
            </Card>

            <Card title="CONTEXT">
              <ContextFiltersPanel
                ctx={query.context || {}}
                onChange={ctx => setQuery(q => ({ ...q, context: ctx }))}
                seasons={seasons}
                grades={grades}
                targetShape={targetMeta.shape}
                activeDerived={activeDerived}
              />
            </Card>

            <div className="flex gap-2">
              <Btn primary onClick={() => runQuery()} className="flex-1" disabled={loading}>
                {loading ? 'Running…' : 'Run query →'}
              </Btn>
              <Btn onClick={resetAll}>Reset</Btn>
            </div>

            {canSave && hasQueried && rows.length > 0 && (
              <Btn onClick={() => { setEditingReport(null); setSaveOpen(true) }} className="w-full">Save as report…</Btn>
            )}

            <Card title="REPORTS">
              <div className="flex flex-col">
                {PRESET_GROUPS.map(group => (
                  <div key={group.key} className="pb-hairline-b last:border-0">
                    <button
                      onClick={() => toggleGroup(group.key)}
                      className="w-full flex items-center justify-between px-2 py-2 hover:bg-pb-surface2 transition rounded text-left"
                    >
                      <span className="font-mono text-[11px] font-semibold tracking-wide2 text-pb-dim">
                        {group.label.toUpperCase()}
                      </span>
                      <span className="text-pb-faintest text-[10px]">{openGroups[group.key] ? '▾' : '▸'}</span>
                    </button>
                    {openGroups[group.key] && (
                      <div className="flex flex-col gap-0.5 pb-2 pl-1">
                        {group.items.map((item, idx) => {
                          const isActive = item.type === 'derived'
                            ? activeDerived === item.key
                            : false
                          return (
                            <button
                              key={item.key || item.label + idx}
                              onClick={() => applyGroupItem(item)}
                              className={`text-left px-2 py-1.5 rounded transition ${isActive ? 'text-pb-text bg-pb-surface2' : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'}`}
                            >
                              <div className="font-mono text-[11px] tracking-wide2">{item.label}</div>
                              {item.description && (
                                <div className="text-[10px] text-pb-faintest font-sans normal-case tracking-normal mt-0.5">{item.description}</div>
                              )}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            <Card title={`SAVED REPORTS · ${reports.length}`}>
              {reportsLoading
                ? <p className="text-pb-faintest font-mono text-[10.5px]">Loading…</p>
                : reports.length === 0
                  ? <p className="text-pb-faintest font-mono text-[10.5px]">No saved reports yet.</p>
                  : (
                    <ul className="flex flex-col gap-1">
                      {reports.map(r => (
                        <li key={r.id}>
                          <Link to={`/${clubSlug}/statlab/r/${r.slug}`} className="block px-2 py-1.5 rounded hover:bg-pb-surface2 transition">
                            <div className="font-semibold text-[12px] text-pb-text">{r.title}</div>
                            <div className="font-mono text-[10px] text-pb-faintest tracking-wide2">
                              {(r.owner_name || 'club')} · {r.view_count} view{r.view_count === 1 ? '' : 's'}
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )
              }
            </Card>
          </div>

          {/* Right panel: results */}
          <div>
            {!hasQueried && !loading && (
              <div className="pb-card p-8 flex flex-col items-center justify-center text-center gap-3" style={{ minHeight: 320 }}>
                <Label>READY</Label>
                <p className="text-pb-dim text-[15px]">Configure your query and hit <span className="text-pb-text font-semibold">Run query</span>, or pick a preset / derived metric.</p>
              </div>
            )}

            {loading && <PbSpinner message="Querying…" />}

            {error && <p className="text-pb-red text-sm py-4">{error}</p>}

            {hasQueried && !loading && !error && sortedRows.length === 0 && (
              <div className="pb-card p-8 text-center">
                <p className="text-pb-faint">No results match your filters.</p>
              </div>
            )}

            {sortedRows.length > 0 && (
              <Card
                title={`${sortedRows.length} ${activeDerived ? 'PLAYERS' : (targetMeta.shape === 'list' ? 'ROWS' : 'GROUPS')}${activeDerived ? ' · ' + schema.derived[activeDerived].label.toUpperCase() : ''}`}
                action={
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-2xs tracking-wide2 text-pb-faintest">
                      {activeDerived
                        ? ''
                        : `SORTED BY ${(METRIC_LABELS[query.sortBy]?.label || query.sortBy).toUpperCase()} ${query.sortDir === 'asc' ? '↑' : '↓'}`}
                    </span>
                    <button onClick={downloadCSV} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">CSV</button>
                  </div>
                }
                pad="p-0"
              >
                <ResultsTable
                  rows={sortedRows}
                  columns={tableColumns}
                  target={query.target}
                  activeDerived={activeDerived}
                  clientSort={clientSort}
                  onSort={handleColSort}
                  sortBy={query.sortBy}
                  clubSlug={clubSlug}
                />
              </Card>
            )}
          </div>
        </div>
      </main>

      <SaveReportModal
        open={saveOpen}
        onClose={() => { setSaveOpen(false); setEditingReport(null) }}
        onSave={saveReport}
        defaultTitle={defaultTitleFor(query, activeDerived, schema)}
        initial={editingReport}
      />
    </div>
  )
}

// ─── Results table ────────────────────────────────────────────────────────────

function entityHeader(target, activeDerived) {
  if (activeDerived === 'best_partnership_pair') {
    return [{ key: 'pair', label: 'PAIR' }]
  }
  switch (target) {
    case 'player_career':
      return [{ key: 'player_name', label: 'PLAYER' }]
    case 'player_season':
      return [{ key: 'player_name', label: 'PLAYER' }, { key: 'season_name', label: 'SEASON' }]
    case 'player_grade':
      return [{ key: 'player_name', label: 'PLAYER' }, { key: 'display_grade_name', label: 'GRADE' }]
    case 'innings_list':
      return [
        { key: 'player_name', label: 'PLAYER' },
        { key: 'opposition',  label: 'VS' },
        { key: 'grade_name',  label: 'GRADE' },
        { key: 'played_at',   label: 'DATE' },
        { key: 'dismissal_type', label: 'OUT' },
      ]
    case 'spell_list':
      return [
        { key: 'player_name', label: 'PLAYER' },
        { key: 'opposition',  label: 'VS' },
        { key: 'grade_name',  label: 'GRADE' },
        { key: 'played_at',   label: 'DATE' },
      ]
    case 'match_list':
      return [
        { key: 'opposition', label: 'VS' },
        { key: 'grade_name', label: 'GRADE' },
        { key: 'played_at',  label: 'DATE' },
        { key: 'result',     label: 'RESULT' },
      ]
    case 'partnership_list':
      return [
        { key: 'pair',       label: 'PAIR' },
        { key: 'opposition', label: 'VS' },
        { key: 'grade_name', label: 'GRADE' },
        { key: 'played_at',  label: 'DATE' },
      ]
    default:
      return [{ key: 'player_name', label: 'NAME' }]
  }
}

function ResultsTable({ rows, columns, target, activeDerived, clientSort, onSort, sortBy, clubSlug }) {
  const dimCols = activeDerived
    ? (activeDerived === 'best_partnership_pair'
        ? [{ key: 'pair', label: 'PAIR' }]
        : [{ key: 'player_name', label: 'PLAYER' }])
    : entityHeader(target, null)
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="py-3 pl-5 w-8">#</th>
            {dimCols.map(dc => (
              <th key={dc.key} className="py-3 font-medium pr-3">{dc.label}</th>
            ))}
            {columns.map(col => (
              <th key={col.key} onClick={() => onSort(col.key)}
                className="py-3 text-right font-medium cursor-pointer hover:text-pb-text pr-3 select-none"
                style={{ color: (clientSort.col === col.key || sortBy === col.key) ? 'var(--pb-accent)' : undefined }}
              >
                {col.label}{clientSort.col === col.key ? (clientSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5 font-mono text-pb-faintest">{i + 1}</td>
              {dimCols.map(dc => (
                <td key={dc.key} className="py-2.5 pr-3 font-medium text-pb-text">
                  {renderDimCell(dc.key, row, clubSlug)}
                </td>
              ))}
              {columns.map(col => (
                <td key={col.key} className="py-2.5 pr-3 text-right">
                  <span className={`font-mono pb-num ${(clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'font-bold' : ''}`}
                        style={{ color: (clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                    {formatCell(row[col.key], col)}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatCell(v, col) {
  if (v == null || v === '') return '—'
  if (col?.decimal) return Number(v).toFixed(2)
  return v
}

function renderDimCell(key, row, clubSlug) {
  if (key === 'pair') {
    const a = row.player_a_name || row.batter1_name
    const b = row.player_b_name || row.batter2_name
    const aId = row.player_a_id || row.batter1_id
    const bId = row.player_b_id || row.batter2_id
    return (
      <span>
        {aId ? <Link to={`/players/${aId}`} className="text-pb-text hover:text-pb-accent">{a}</Link> : a}
        <span className="text-pb-faintest"> & </span>
        {bId ? <Link to={`/players/${bId}`} className="text-pb-text hover:text-pb-accent">{b}</Link> : b}
      </span>
    )
  }
  if (key === 'player_name' && row.player_id) {
    return <Link to={`/players/${row.player_id}`} className="text-pb-text hover:text-pb-accent">{row.player_name || row.name}</Link>
  }
  if (key === 'result') {
    const r = row.result
    if (r === 'won') return <span className="text-pb-green">Won</span>
    if (r === 'lost') return <span className="text-pb-red">Lost</span>
    return <span className="text-pb-dim">{r || '—'}</span>
  }
  if (key === 'played_at' && row.played_at) {
    try { return new Date(row.played_at).toISOString().slice(0, 10) } catch { return row.played_at }
  }
  return row[key] || '—'
}

function defaultTitleFor(q, activeDerived, schema) {
  if (activeDerived && schema?.derived?.[activeDerived]) return schema.derived[activeDerived].label
  const t = TARGETS.find(x => x.key === q.target)?.label || 'Query'
  const sb = METRIC_LABELS[q.sortBy]?.label || q.sortBy
  return `${t} — ${sb}`
}
