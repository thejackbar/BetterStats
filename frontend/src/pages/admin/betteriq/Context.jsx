/* BetterIQ — global Season + Team filter context.
   A sticky bar under the header that persists Team + Season (single OR a
   cross-season range) across every IQ route. Backed by a small module-level
   store (mirrors IQLayout's club-branding cache) so the selection survives
   route changes without a shared layout route, persisted to sessionStorage.

   Ported from the v2 design handoff; wired to the real seasons/grades API. */
import { useSyncExternalStore, useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../../../lib/api'
import { Icon, Segmented, Tag } from './ui'
import Dropdown from '../../../components/Dropdown'
import { formatSeason } from '../../../lib/cricketFormat'

/* ── season label helpers ─────────────────────────────────────────────────── */
// Canonical "YYYY/YY" season label — same standard used everywhere else.
export function shortSeason(name) {
  if (!name) return '—'
  return formatSeason(name) || String(name)
}
function sortKey(s) {
  if (!s) return 0
  if (s.year != null && s.year !== '') return Number(s.year)
  const m = String(s.name || '').match(/(\d{4})/)
  return m ? Number(m[1]) : 0
}

/* ── module store ─────────────────────────────────────────────────────────── */
const SS_KEY = 'iq.ctx.v1'
let _seasons = null          // oldest → newest
let _grades = null
let _ctx = null
let _loadPromise = null
const _listeners = new Set()
let _snapshot = { seasons: [], grades: [], ctx: null, ready: false }

function _recompute() { _snapshot = { seasons: _seasons || [], grades: _grades || [], ctx: _ctx, ready: !!_seasons } }
function _emit() { _recompute(); _listeners.forEach(l => l()) }
function _subscribe(l) { _listeners.add(l); return () => _listeners.delete(l) }
function _saveCtx() { try { sessionStorage.setItem(SS_KEY, JSON.stringify(_ctx)) } catch { /* ignore */ } }
function _loadCtx() { try { return JSON.parse(sessionStorage.getItem(SS_KEY) || 'null') } catch { return null } }

// `_seasons` entries are now per-YEAR (see `_ensureLoaded`); match a saved id
// against the representative id first, then any sibling row id it folds in.
function _seasonById(id) {
  if (!id) return null
  return (_seasons || []).find(s => s.id === id)
    || (_seasons || []).find(s => (s.ids || []).includes(id))
    || null
}

// The cricket YEAR of a raw season row — its `year`, else the 4-digit year in
// its name ("Summer 2010/11" → 2010), else null (undated, kept on its own).
function _rowYear(s) {
  if (s.year != null && s.year !== '') return Number(s.year)
  const m = String(s.name || '').match(/(\d{4})/)
  return m ? Number(m[1]) : null
}

/* A team selection is `{ id, name, names? }`. `id` stays the value every page
   sends to the backend: one grade NAME, or several names joined with '||' (the
   multi-select wire format — `season_grade_clause` splits it server-side), or
   null for "All grades". `names` is the picked list for the UI. */
export function teamFromNames(names) {
  const list = (names || []).filter(Boolean)
  if (!list.length) return { id: null, name: 'All grades', names: [] }
  if (list.length === 1) return { id: list[0], name: list[0], names: list }
  return { id: list.join('||'), name: `${list.length} grades`, names: list }
}
export function teamNames(team) {
  if (!team || team.id == null) return []
  if (team.names?.length) return team.names
  return String(team.id).split('||').filter(Boolean)
}

function _reconcile(saved) {
  if (!saved || !saved.season || !_seasons?.length) return null
  const newest = _seasons[_seasons.length - 1]
  const from = _seasonById(saved.season.from?.id) || newest
  const to = _seasonById(saved.season.to?.id) || newest
  // Grades are keyed by NAME now (de-duped across seasons). Drop any saved
  // names that no longer match a known grade (e.g. an old raw-uuid id from a
  // previous build) so it falls back to "All grades" instead of filtering to
  // nothing.
  const known = new Set((_grades || []).flatMap(g => [g.id, g.name]))
  const savedNames = teamNames(saved.team).filter(n => known.has(n))
  const team = teamFromNames(savedNames)
  const mode = saved.season.mode === 'range' ? 'range' : saved.season.mode === 'all' ? 'all' : 'single'
  return { team, season: { mode, from, to }, touched: !!saved.touched }
}

async function _ensureLoaded() {
  if (_seasons) return
  if (!_loadPromise) {
    _loadPromise = (async () => {
      let seasons = [], grades = []
      try { seasons = (await api.iqTeamSeasons()) || [] } catch { /* ignore */ }
      try { grades = (await api.iqTeamGrades()) || [] } catch { /* ignore */ }
      // Collapse the raw season ROWS into one entry per cricket YEAR. A club's
      // "2024/25" is often several rows (MyCricket vs PlayHQ ids, separate
      // comps), so every year entry keeps all its row ids in `ids` — a single
      // pick then scopes the whole year (backend year-expands it), not one
      // slice, and the picker shows each year once. Undated rows stand alone.
      const byYear = new Map()
      for (const s of seasons) {
        const id = s.season_id || s.id
        const yr = _rowYear({ year: s.year, name: s.name })
        const key = yr != null ? `y${yr}` : `id${id}`
        if (!byYear.has(key)) byYear.set(key, { id, ids: [], year: yr, name: s.name, label: shortSeason(s.name) })
        byYear.get(key).ids.push(id)
      }
      _seasons = [...byYear.values()].sort((a, b) => sortKey(a) - sortKey(b))
      _grades = (grades || []).map(g => ({ id: g.grade_id || g.id, name: g.name, season_id: g.season_id || null, category: g.category || null }))
      const newest = _seasons[_seasons.length - 1] || null
      // `touched` = the user has interacted with the filter bar this session.
      // Until then a page may apply its own default (e.g. Opposition switches
      // the untouched default to All seasons so the header matches the data).
      _ctx = _reconcile(_loadCtx()) || {
        team: { id: null, name: 'All grades', names: [] },
        season: { mode: 'single', from: newest, to: newest },
        touched: false,
      }
      _emit()
    })()
  }
  return _loadPromise
}

/* The hook every IQ screen uses to read/write the active filter. */
export function useIQFilter() {
  const snap = useSyncExternalStore(_subscribe, () => _snapshot, () => _snapshot)
  useEffect(() => { _ensureLoaded() }, [])
  const setCtx = (next) => { _ctx = typeof next === 'function' ? next(_ctx) : next; _saveCtx(); _emit() }
  return { ctx: snap.ctx, setCtx, seasons: snap.seasons, grades: snap.grades, ready: snap.ready }
}

/* ── derived helpers for screens ──────────────────────────────────────────── */
export function seasonsInRange(ctx, seasons) {
  if (!ctx || !ctx.season || !seasons?.length) return []
  if (ctx.season.mode === 'all') return seasons
  if (ctx.season.mode === 'single') return [ctx.season.to].filter(Boolean)
  const a = sortKey(ctx.season.from), b = sortKey(ctx.season.to)
  const lo = Math.min(a, b), hi = Math.max(a, b)
  return seasons.filter(s => sortKey(s) >= lo && sortKey(s) <= hi)
}
// Every underlying season-row id in scope — the union of each in-range year's
// folded rows, so grade options and per-season filters see the whole year.
export function seasonIdsInRange(ctx, seasons) {
  return seasonsInRange(ctx, seasons).flatMap(s => (s.ids && s.ids.length ? s.ids : [s.id])).filter(Boolean)
}
// The single representative season-row id a page sends to the backend; undefined
// in "All seasons" mode (all-time, no season scope). The backend year-expands it.
// NOTE: in 'range' (Compare) mode this is only the NEWEST end of the range — a
// route that advertises Compare must ALSO send effectiveSeasonIds() or its data
// silently collapses to one season under a "Comparing N seasons" tag.
export function effectiveSeasonId(ctx) {
  if (!ctx || !ctx.season || ctx.season.mode === 'all') return undefined
  return ctx.season.to?.id || undefined
}
// Every season-row id across the selected Compare range — what a range-capable
// endpoint's `season_ids` should carry. Undefined outside 'range' mode (single
// mode sends effectiveSeasonId, which the backend year-expands; 'all' sends
// nothing).
export function effectiveSeasonIds(ctx, seasons) {
  if (!ctx || !ctx.season || ctx.season.mode !== 'range') return undefined
  const ids = seasonIdsInRange(ctx, seasons)
  return ids.length ? ids : undefined
}
export function seasonSpanCount(ctx, seasons) { return Math.max(1, seasonsInRange(ctx, seasons).length) }
export function seasonLabel(ctx, seasons) {
  if (!ctx || !ctx.season) return '—'
  const s = ctx.season
  if (s.mode === 'all') return 'All seasons'
  if (s.mode === 'single') return s.to?.label || '—'
  const inRange = seasonsInRange(ctx, seasons)
  if (seasons?.length && inRange.length === seasons.length) return 'All seasons'
  return `${s.from?.label || '?'} → ${s.to?.label || '?'}`
}

/* Frontend mirror of the backend ``grade_base`` (iq_filters): strip a trailing
   sponsor parenthetical with no digit, so a fixture's raw grade name ("B Grade
   (DXC Technology)") matches the merged base name the Grade filter lists. */
export function gradeBase(name) {
  return String(name || '').replace(/\s*\([^)0-9]*\)\s*$/, '')
}

/* per-route filter capability. ``preview`` and ``selection`` use the grade only
   (to narrow the fixture list); ``opposition-player`` scouts one chosen club's
   players, which the global Season/Grade filter has nothing to narrow, so it
   shows no bar. */
export const ROUTE_FILTERS = {
  overview: { team: true, season: 'single' },
  preview: { team: true, season: false },
  // 'Grade', not 'Their grade': the one selection scopes BOTH sides — our games
  // in that competition (the report) and their sides in it (the dossier).
  opposition: { team: true, season: 'range', teamLabel: 'Grade' },
  selection: { team: true, season: false },
  trends: { team: true, season: 'range' },
  team: { team: true, season: 'range' },
  review: { team: true, season: 'range' },
}

/* ── Popover shell ────────────────────────────────────────────────────────── */
function Popover({ trigger, children, width = 300, align = 'left' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  return (
    <div className="relative" ref={ref}>
      <div onClick={() => setOpen(o => !o)}>{trigger(open)}</div>
      <Dropdown
        anchorRef={ref}
        open={open}
        onClose={() => setOpen(false)}
        align={align === 'right' ? 'end' : 'start'}
        width={width}
        gap={8}
        className="iq-card p-3.5"
        style={{ boxShadow: 'var(--iq-card-shadow)', overflow: 'visible', maxHeight: 'none' }}
      >
        {typeof children === 'function' ? children(() => setOpen(false)) : children}
      </Dropdown>
    </div>
  )
}

function PillTrigger({ icon, label, sub, open, accent }) {
  return (
    <button className="flex items-center gap-2.5 transition" style={{
      background: 'var(--pb-surface2)', border: `1px solid ${open ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`,
      borderRadius: 10, padding: '7px 12px', height: 38 }}>
      <Icon name={icon} size={15} style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-faint)' }} />
      <span className="text-left leading-none">
        {sub && <span className="iq-eyebrow block" style={{ fontSize: 8, marginBottom: 2 }}>{sub}</span>}
        <span className="iq-display font-semibold text-[13px]" style={{ color: 'var(--pb-text)' }}>{label}</span>
      </span>
      <Icon name="chevron" size={13} className="text-pb-faint" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />
    </button>
  )
}

/* ── Team picker — multi-select grades + category presets ─────────────────────
   Tick any set of grades (exclude juniors/women's, keep just the top sides…).
   "Seniors only" uses the same grade classification the merge-grades admin
   screen suggests (confirmed `grades.category` when set, else the name-based
   guess) — served per grade by /iq/team/grades. Single-pick still reads as a
   plain click; ticking more boxes builds the multi set. */
const CATEGORY_TAGS = { junior: 'Jnr', womens: "Wom", masters: 'Mas', mixed: 'Mix' }

function TeamPicker({ value, grades, onChange, label = 'Team' }) {
  const picked = new Set(teamNames(value))
  const seniorNames = (grades || []).filter(g => (g.category || 'senior') === 'senior').map(g => g.name)
  const hasNonSenior = seniorNames.length > 0 && seniorNames.length < (grades || []).length
  const seniorsActive = picked.size > 0 && picked.size === seniorNames.length && seniorNames.every(n => picked.has(n))
  const toggle = (name) => {
    const next = new Set(picked)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    onChange(teamFromNames([...next]))
  }
  const presetBtn = (active) => ({
    padding: '5px 9px', borderRadius: 8,
    background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
    color: active ? 'var(--pb-accent)' : 'var(--pb-dim)',
    border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}`,
  })
  return (
    <Popover width={260} trigger={open => <PillTrigger icon="teams" sub={label} label={value?.name || 'All grades'} open={open} />}>
      {close => (
        <div>
          <div className="mb-2 flex flex-wrap gap-1.5">
            <button onClick={() => { onChange(teamFromNames([])); close() }}
              className="iq-display font-semibold text-[11.5px] transition" style={presetBtn(picked.size === 0)}>All grades</button>
            {hasNonSenior && (
              <button onClick={() => onChange(teamFromNames(seniorNames))}
                className="iq-display font-semibold text-[11.5px] transition" style={presetBtn(seniorsActive)}
                title="Every senior grade — excludes junior, women's, masters and mixed/social grades">Seniors only</button>
            )}
          </div>
          <div className="space-y-0.5 max-h-72 overflow-y-auto iq-scroll">
            {(grades || []).map(t => {
              const active = picked.has(t.name)
              const tag = CATEGORY_TAGS[t.category]
              return (
                <button key={t.name} onClick={() => toggle(t.name)}
                  className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8, background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--pb-surface2)' }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="shrink-0 inline-flex items-center justify-center" style={{
                      width: 15, height: 15, borderRadius: 4,
                      border: `1.5px solid ${active ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`,
                      background: active ? 'var(--pb-accent)' : 'transparent' }}>
                      {active && <Icon name="check" size={11} style={{ color: 'var(--pb-bg)' }} />}
                    </span>
                    <span className="font-medium text-[13.5px] truncate" style={{ color: active ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{t.name}</span>
                  </span>
                  {tag && <span className="iq-mono shrink-0" style={{ fontSize: 9, color: 'var(--pb-faintest)' }}>{tag}</span>}
                </button>
              )
            })}
          </div>
          {picked.size > 1 && (
            <div className="iq-mono mt-2 px-1" style={{ fontSize: 10, color: 'var(--pb-faint)' }}>{picked.size} grades selected</div>
          )}
        </div>
      )}
    </Popover>
  )
}

/* ── Season list (scrollable + filterable — scales to 100+ seasons) ───────────
   Replaces the old fixed-width dot timeline, which crammed every season onto one
   line and became unselectable past a handful of seasons. In single mode it's a
   plain pick list; in range mode the same list highlights the in-range span and
   you click the two endpoints (anchor → other end). */
function SeasonList({ seasons, season, mode, onChange, anchor, setAnchor }) {
  const [q, setQ] = useState('')
  const newestFirst = [...seasons].reverse()
  const ql = q.trim().toLowerCase()
  const list = ql ? newestFirst.filter(s => `${s.name || ''} ${s.label || ''}`.toLowerCase().includes(ql)) : newestFirst
  const lo = Math.min(sortKey(season.from), sortKey(season.to))
  const hi = Math.max(sortKey(season.from), sortKey(season.to))
  const click = s => {
    if (mode === 'single') { onChange({ mode: 'single', from: s, to: s }); return }
    if (anchor == null) { setAnchor(s); onChange({ mode: 'range', from: s, to: s }) }
    else {
      const a = sortKey(anchor) <= sortKey(s) ? anchor : s
      const b = sortKey(anchor) <= sortKey(s) ? s : anchor
      onChange({ mode: 'range', from: a, to: b }); setAnchor(null)
    }
  }
  return (
    <div>
      {seasons.length > 10 && (
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter seasons…"
          className="w-full mb-2 outline-none" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 8, padding: '7px 10px', fontSize: 13, color: 'var(--pb-text)' }} />
      )}
      <div className="space-y-0.5 overflow-y-auto iq-scroll" style={{ maxHeight: 260 }}>
        {list.map(s => {
          const k = sortKey(s)
          const endpoint = (mode === 'single' && s.id === season.to?.id) || (mode === 'range' && (s.id === season.from?.id || s.id === season.to?.id))
          const inSpan = mode === 'range' && k >= lo && k <= hi
          return (
            <button key={s.id} onClick={() => click(s)}
              className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8,
                background: endpoint ? 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' : inSpan ? 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' : 'transparent' }}
              onMouseEnter={e => { if (!endpoint) e.currentTarget.style.background = 'var(--pb-surface2)' }}
              onMouseLeave={e => { if (!endpoint) e.currentTarget.style.background = inSpan ? 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' : 'transparent' }}>
              <span className="font-medium text-[13.5px] truncate" style={{ color: endpoint || inSpan ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{formatSeason(s) || s.label}</span>
              {endpoint && <Icon name="check" size={14} className="shrink-0" style={{ color: 'var(--pb-accent)' }} />}
            </button>
          )
        })}
        {list.length === 0 && <div className="text-pb-faint text-[12px] px-2.5 py-3">No seasons match.</div>}
      </div>
    </div>
  )
}

/* Single-year dropdown (the "This season" detail). */
function YearPicker({ season, seasons, onChange }) {
  const newestFirst = [...seasons].reverse()
  return (
    <Popover width={230} trigger={open => <PillTrigger icon="clock" sub="Season" label={season.to?.label || '—'} open={open} accent />}>
      {close => (
        <div className="space-y-0.5 overflow-y-auto iq-scroll" style={{ maxHeight: 300 }}>
          {newestFirst.map(s => {
            const active = s.id === season.to?.id
            return (
              <button key={s.id} onClick={() => { onChange({ mode: 'single', from: s, to: s }); close() }}
                className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8, background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--pb-surface2)' }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
                <span className="font-medium text-[13.5px] truncate" style={{ color: active ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{formatSeason(s) || s.label}</span>
                {active && <Icon name="check" size={14} className="shrink-0" style={{ color: 'var(--pb-accent)' }} />}
              </button>
            )
          })}
        </div>
      )}
    </Popover>
  )
}

/* Two-endpoint range picker (the "Compare" detail) — list + quick presets. */
function RangePicker({ season, seasons, onChange }) {
  const [anchor, setAnchor] = useState(null)
  const newest = seasons[seasons.length - 1]
  const presets = [
    { label: 'This + last', range: [seasons[Math.max(0, seasons.length - 2)], newest] },
    { label: 'Last 3', range: [seasons[Math.max(0, seasons.length - 3)], newest] },
    { label: 'Last 5', range: [seasons[Math.max(0, seasons.length - 5)], newest] },
    { label: 'All seasons', range: [seasons[0], newest] },
  ]
  const spanCount = Math.abs(seasons.findIndex(s => s.id === season.to?.id) - seasons.findIndex(s => s.id === season.from?.id)) + 1
  return (
    <Popover width={300} trigger={open => <PillTrigger icon="clock" sub="Compare" label={`${season.from?.label} → ${season.to?.label}`} open={open} accent />}>
      {() => (
        <div>
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="iq-eyebrow" style={{ fontSize: 9 }}>Pick two end seasons</span>
            <span className="iq-mono text-[10px]" style={{ color: anchor != null ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
              {anchor != null ? 'pick the other end' : `${spanCount} season${spanCount > 1 ? 's' : ''}`}
            </span>
          </div>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {presets.map(p => {
              const active = season.from?.id === p.range[0]?.id && season.to?.id === p.range[1]?.id
              return (
                <button key={p.label} onClick={() => { setAnchor(null); onChange({ mode: 'range', from: p.range[0], to: p.range[1] }) }}
                  className="iq-display font-semibold text-[11.5px] transition" style={{ padding: '5px 9px', borderRadius: 8,
                    background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
                    color: active ? 'var(--pb-accent)' : 'var(--pb-dim)', border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}` }}>{p.label}</button>
              )
            })}
          </div>
          <SeasonList seasons={seasons} season={season} mode="range" onChange={onChange} anchor={anchor} setAnchor={setAnchor} />
        </div>
      )}
    </Popover>
  )
}

/* The plain This season / All seasons / Compare control the user asked for.
   The mode toggle is always visible; the detail picker only shows when it adds
   a choice (a year to pick, or a range to set). "All seasons" is all-time. */
function SeasonControl({ season, seasons, allowRange, onChange }) {
  if (!seasons?.length) return null
  const newest = seasons[seasons.length - 1]
  const oldest = seasons[0]
  const mode = allowRange ? season.mode : (season.mode === 'all' ? 'all' : 'single')
  const opts = [{ value: 'single', label: 'This season' }, { value: 'all', label: 'All seasons' }]
  if (allowRange) opts.push({ value: 'range', label: 'Compare' })
  const setMode = (m) => {
    if (m === mode) return
    if (m === 'single') onChange({ mode: 'single', from: season.to || newest, to: season.to || newest })
    else if (m === 'all') onChange({ mode: 'all', from: oldest, to: newest })
    else {
      const ti = seasons.findIndex(s => s.id === season.to?.id)
      const toS = ti >= 0 ? seasons[ti] : newest
      const fromS = seasons[Math.max(0, (ti >= 0 ? ti : seasons.length - 1) - 1)]
      onChange({ mode: 'range', from: fromS, to: toS })
    }
  }
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Segmented sm value={mode} onChange={setMode} options={opts} />
      {mode === 'single' && <YearPicker season={season} seasons={seasons} onChange={onChange} />}
      {mode === 'range' && <RangePicker season={season} seasons={seasons} onChange={onChange} />}
      {mode === 'all' && <span className="iq-mono text-pb-faint" style={{ fontSize: 11 }}>{seasons.length} seasons · all-time</span>}
    </div>
  )
}

/* ── Context bar ──────────────────────────────────────────────────────────── */
export function ContextBar({ route }) {
  const { ctx, setCtx, seasons, grades, ready } = useIQFilter()
  const filters = ROUTE_FILTERS[route]
  // Grades fielded in the currently-selected season(s), de-duped by name — so the
  // Team filter only offers grades the club actually played that season (picking
  // an out-of-season grade returned an empty dashboard). Routes without a season
  // picker still carry a (newest) season in ctx, so they scope to it.
  const visibleGrades = useMemo(() => {
    if (!ctx) return []
    const ids = new Set(seasonIdsInRange(ctx, seasons))
    const byName = new Map()
    for (const g of (grades || [])) {
      if (!ids.size || !g.season_id || ids.has(g.season_id)) {
        const prev = byName.get(g.name)
        // Keep a confirmed/known category over a missing one across season rows.
        if (!prev) byName.set(g.name, { id: g.name, name: g.name, category: g.category || null })
        else if (!prev.category && g.category) prev.category = g.category
      }
    }
    return [...byName.values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }, [ctx, seasons, grades])
  // Drop selected grades the club didn't field in the new season.
  useEffect(() => {
    const names = teamNames(ctx?.team)
    if (names.length && visibleGrades.length) {
      const known = new Set(visibleGrades.map(g => g.name))
      const kept = names.filter(n => known.has(n))
      if (kept.length !== names.length) setCtx({ ...ctx, team: teamFromNames(kept) })
    }
  }, [visibleGrades])  // eslint-disable-line react-hooks/exhaustive-deps
  if (!filters || (!filters.team && !filters.season)) return null
  if (!ready || !ctx) return null
  // Only call it a comparison when the route actually offers Compare (a stale
  // 'range' carried over from another route shouldn't show the tag here).
  const isRange = filters.season === 'range' && ctx.season.mode === 'range'
  return (
    <div className="sticky z-20 flex items-center gap-3 flex-wrap px-5 md:px-8 py-3"
      style={{ top: 64, background: 'color-mix(in srgb, var(--pb-bg) 86%, transparent)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)', borderBottom: '1px solid var(--pb-hairline)' }}>
      <span className="iq-eyebrow hidden sm:block" style={{ fontSize: 9 }}>Showing</span>
      {filters.team && <TeamPicker value={ctx.team} grades={visibleGrades} onChange={t => setCtx({ ...ctx, team: t, touched: true })} label={filters.teamLabel || 'Team'} />}
      {filters.season
        ? <SeasonControl season={ctx.season} seasons={seasons} onChange={s => setCtx({ ...ctx, season: s, touched: true })} allowRange={filters.season === 'range'} />
        : <div className="flex items-center gap-2 px-3" style={{ height: 38, borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)' }}>
            <Icon name="clock" size={14} className="text-pb-faint" />
            <span className="iq-display font-semibold text-[13px]">{seasons[seasons.length - 1]?.label || 'Current'}</span>
            <span className="iq-mono text-pb-faint" style={{ fontSize: 10 }}>· current</span>
          </div>}
      {isRange && <Tag tone="accent">Comparing {seasonSpanCount(ctx, seasons)} seasons</Tag>}
      <div className="ml-auto hidden md:flex items-center gap-1.5 text-pb-faintest text-[11px]">
        <Icon name="info" size={12} />
        <span>Filters apply across BetterIQ</span>
      </div>
    </div>
  )
}
