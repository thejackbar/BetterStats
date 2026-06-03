/* BetterIQ — global Season + Team filter context.
   A sticky bar under the header that persists Team + Season (single OR a
   cross-season range) across every IQ route. Backed by a small module-level
   store (mirrors IQLayout's club-branding cache) so the selection survives
   route changes without a shared layout route, persisted to sessionStorage.

   Ported from the v2 design handoff; wired to the real seasons/grades API. */
import { useSyncExternalStore, useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { Icon, Segmented, Tag } from './ui'

/* ── season label helpers ─────────────────────────────────────────────────── */
export function shortSeason(name) {
  if (!name) return '—'
  const m = String(name).match(/(\d{2})(\d{2})\s*[/\-]\s*(\d{2})/) // "...2024/25"
  if (m) return `${m[2]}/${m[3]}`
  const m2 = String(name).match(/(\d{4})\s*[/\-]\s*(\d{2,4})/)
  if (m2) return `${m2[1].slice(2)}/${m2[2].slice(-2)}`
  const y = String(name).match(/(\d{4})/)
  return y ? y[1] : String(name)
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

function _seasonById(id) { return (_seasons || []).find(s => s.id === id) || null }

function _reconcile(saved) {
  if (!saved || !saved.season || !_seasons?.length) return null
  const newest = _seasons[_seasons.length - 1]
  const from = _seasonById(saved.season.from?.id) || newest
  const to = _seasonById(saved.season.to?.id) || newest
  // Grades are keyed by NAME now (de-duped across seasons). Drop a stale saved
  // team that no longer matches a known grade name (e.g. an old raw-uuid id from
  // a previous build) so it falls back to "All grades" instead of filtering to
  // nothing.
  let team = saved.team && saved.team.name ? saved.team : { id: null, name: 'All grades' }
  if (team.id != null && !(_grades || []).some(g => g.id === team.id)) {
    team = { id: null, name: 'All grades' }
  }
  return {
    team,
    season: { mode: saved.season.mode === 'range' ? 'range' : 'single', from, to },
  }
}

async function _ensureLoaded() {
  if (_seasons) return
  if (!_loadPromise) {
    _loadPromise = (async () => {
      let seasons = [], grades = []
      try { seasons = (await api.iqTeamSeasons()) || [] } catch { /* ignore */ }
      try { grades = (await api.iqTeamGrades()) || [] } catch { /* ignore */ }
      _seasons = seasons
        .map(s => ({ id: s.season_id || s.id, name: s.name, year: s.year, label: shortSeason(s.name) }))
        .sort((a, b) => sortKey(a) - sortKey(b))
      _grades = (grades || []).map(g => ({ id: g.grade_id || g.id, name: g.name }))
      const newest = _seasons[_seasons.length - 1] || null
      _ctx = _reconcile(_loadCtx()) || {
        team: { id: null, name: 'All grades' },
        season: { mode: 'single', from: newest, to: newest },
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
  if (ctx.season.mode === 'single') return [ctx.season.to].filter(Boolean)
  const a = sortKey(ctx.season.from), b = sortKey(ctx.season.to)
  const lo = Math.min(a, b), hi = Math.max(a, b)
  return seasons.filter(s => sortKey(s) >= lo && sortKey(s) <= hi)
}
export function seasonIdsInRange(ctx, seasons) { return seasonsInRange(ctx, seasons).map(s => s.id) }
export function seasonSpanCount(ctx, seasons) { return Math.max(1, seasonsInRange(ctx, seasons).length) }
export function seasonLabel(ctx, seasons) {
  if (!ctx || !ctx.season) return '—'
  const s = ctx.season
  if (s.mode === 'single') return s.to?.label || '—'
  const inRange = seasonsInRange(ctx, seasons)
  if (seasons?.length && inRange.length === seasons.length) return 'All seasons'
  return `${s.from?.label || '?'} → ${s.to?.label || '?'}`
}

/* per-route filter capability */
export const ROUTE_FILTERS = {
  overview: { team: true, season: 'single' },
  preview: { team: true, season: false },
  opposition: { team: true, season: 'range', teamLabel: 'Their grade' },
  'opposition-player': { team: true, season: 'range', teamLabel: 'Their grade' },
  selection: { team: true, season: false },
  trends: { team: true, season: 'range' },
  team: { team: true, season: 'range' },
  review: { team: true, season: 'range' },
}

/* ── Popover shell ────────────────────────────────────────────────────────── */
function Popover({ trigger, children, width = 300, align = 'left' }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <div onClick={() => setOpen(o => !o)}>{trigger(open)}</div>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute z-40 mt-2 iq-card p-3.5" style={{ width, [align]: 0, boxShadow: 'var(--iq-card-shadow)' }}>
            {typeof children === 'function' ? children(() => setOpen(false)) : children}
          </div>
        </>
      )}
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

/* ── Team picker ──────────────────────────────────────────────────────────── */
function TeamPicker({ value, grades, onChange, label = 'Team' }) {
  const opts = [{ id: null, name: 'All grades' }, ...(grades || [])]
  return (
    <Popover width={220} trigger={open => <PillTrigger icon="teams" sub={label} label={value?.name || 'All grades'} open={open} />}>
      {close => (
        <div className="space-y-0.5 max-h-72 overflow-y-auto iq-scroll">
          {opts.map(t => {
            const active = (t.id || null) === (value?.id || null)
            return (
              <button key={t.id || 'all'} onClick={() => { onChange(t); close() }}
                className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8, background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--pb-surface2)' }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
                <span className="font-medium text-[13.5px]" style={{ color: active ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{t.name}</span>
                {active && <Icon name="check" size={14} style={{ color: 'var(--pb-accent)' }} />}
              </button>
            )
          })}
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
              <span className="font-medium text-[13.5px] truncate" style={{ color: endpoint || inSpan ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{s.name || s.label}</span>
              {endpoint && <Icon name="check" size={14} className="shrink-0" style={{ color: 'var(--pb-accent)' }} />}
            </button>
          )
        })}
        {list.length === 0 && <div className="text-pb-faint text-[12px] px-2.5 py-3">No seasons match.</div>}
      </div>
    </div>
  )
}

function SeasonPicker({ season, seasons, onChange, allowRange }) {
  const [anchor, setAnchor] = useState(null)
  if (!seasons?.length) return null
  const newest = seasons[seasons.length - 1]
  const mode = allowRange ? season.mode : 'single'
  const setMode = m => {
    setAnchor(null)
    if (m === 'single') onChange({ mode: 'single', from: season.to, to: season.to })
    else { const ti = seasons.findIndex(s => s.id === season.to?.id); onChange({ mode: 'range', from: seasons[Math.max(0, ti - 1)], to: season.to }) }
  }
  const presets = [
    { label: 'This + last', range: [seasons[Math.max(0, seasons.length - 2)], newest] },
    { label: 'Last 3', range: [seasons[Math.max(0, seasons.length - 3)], newest] },
    { label: 'Last 5', range: [seasons[Math.max(0, seasons.length - 5)], newest] },
    { label: 'All seasons', range: [seasons[0], newest] },
  ]
  const spanCount = Math.abs(seasons.findIndex(s => s.id === season.to?.id) - seasons.findIndex(s => s.id === season.from?.id)) + 1
  return (
    <Popover width={300} trigger={open => <PillTrigger icon="clock" sub="Season" label={mode === 'single' ? (season.to?.label || '—') : `${season.from?.label} → ${season.to?.label}`} open={open} accent />}>
      {() => (
        <div>
          {allowRange && (
            <div className="mb-3 flex items-center justify-between gap-2">
              <Segmented sm value={season.mode} onChange={setMode}
                options={[{ value: 'single', label: 'Single' }, { value: 'range', label: 'Compare' }]} />
              {season.mode === 'range' && (
                <span className="iq-mono text-[10px]" style={{ color: anchor != null ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
                  {anchor != null ? 'pick the other end' : `${spanCount} season${spanCount > 1 ? 's' : ''}`}
                </span>
              )}
            </div>
          )}
          {allowRange && season.mode === 'range' && (
            <div className="mb-3">
              <div className="flex flex-wrap gap-1.5">
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
            </div>
          )}
          <SeasonList seasons={seasons} season={season} mode={mode} onChange={onChange} anchor={anchor} setAnchor={setAnchor} />
        </div>
      )}
    </Popover>
  )
}

/* ── Context bar ──────────────────────────────────────────────────────────── */
export function ContextBar({ route }) {
  const { ctx, setCtx, seasons, grades, ready } = useIQFilter()
  const filters = ROUTE_FILTERS[route]
  if (!filters || (!filters.team && !filters.season)) return null
  if (!ready || !ctx) return null
  const isRange = ctx.season.mode === 'range'
  return (
    <div className="sticky z-20 flex items-center gap-3 flex-wrap px-5 md:px-8 py-3"
      style={{ top: 64, background: 'color-mix(in srgb, var(--pb-bg) 86%, transparent)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)', borderBottom: '1px solid var(--pb-hairline)' }}>
      <span className="iq-eyebrow hidden sm:block" style={{ fontSize: 9 }}>Showing</span>
      {filters.team && <TeamPicker value={ctx.team} grades={grades} onChange={t => setCtx({ ...ctx, team: t })} label={filters.teamLabel || 'Team'} />}
      {filters.season
        ? <SeasonPicker season={ctx.season} seasons={seasons} onChange={s => setCtx({ ...ctx, season: s })} allowRange={filters.season === 'range'} />
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
