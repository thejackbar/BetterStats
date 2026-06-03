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
  return {
    team: saved.team && saved.team.name ? saved.team : { id: null, name: 'All grades' },
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

/* ── Season timeline (the range visualiser/selector) ─────────────────────── */
function SeasonTimeline({ season, seasons, onChange, mode }) {
  const [anchor, setAnchor] = useState(null)
  if (!seasons?.length) return null
  const idx = id => seasons.findIndex(s => s.id === id)
  const fromI = idx(season.from?.id), toI = idx(season.to?.id)
  const lo = Math.min(fromI, toI), hi = Math.max(fromI, toI)
  const click = i => {
    const s = seasons[i]
    if (mode === 'single') { onChange({ mode: 'single', from: s, to: s }); return }
    if (anchor === null) { setAnchor(i); onChange({ mode: 'range', from: s, to: s }) }
    else { const a = Math.min(anchor, i), b = Math.max(anchor, i); onChange({ mode: 'range', from: seasons[a], to: seasons[b] }); setAnchor(null) }
  }
  return (
    <div className="px-1 pt-2 pb-1">
      <div className="relative flex items-center justify-between">
        <div className="absolute left-2 right-2 top-[7px] h-[3px] rounded-full" style={{ background: 'var(--pb-surface3)' }} />
        {mode === 'range' && hi > lo && (
          <div className="absolute top-[7px] h-[3px] rounded-full" style={{ background: 'var(--pb-accent)',
            left: `${(lo / (seasons.length - 1)) * 100}%`, right: `${(1 - hi / (seasons.length - 1)) * 100}%` }} />
        )}
        {seasons.map((s, i) => {
          const inSpan = i >= lo && i <= hi
          const endpoint = (mode === 'single' && i === toI) || (mode === 'range' && (i === lo || i === hi))
          return (
            <button key={s.id} onClick={() => click(i)} className="relative flex flex-col items-center" style={{ zIndex: 1 }} title={s.name}>
              <span style={{ width: endpoint ? 15 : 11, height: endpoint ? 15 : 11, borderRadius: 99,
                background: endpoint ? 'var(--pb-accent)' : inSpan ? 'color-mix(in srgb, var(--pb-accent) 45%, var(--pb-surface3))' : 'var(--pb-surface3)',
                border: `2px solid ${endpoint || inSpan ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`, transition: 'all .15s' }} />
              <span className="iq-mono mt-2" style={{ fontSize: 9.5, color: inSpan ? 'var(--pb-text)' : 'var(--pb-faint)' }}>{s.label}</span>
            </button>
          )
        })}
      </div>
      {mode === 'range' && <div className="text-pb-faint text-[11px] mt-3 text-center">{anchor !== null ? 'Pick the other end of the range' : `${hi - lo + 1} season${hi - lo + 1 > 1 ? 's' : ''} selected`}</div>}
    </div>
  )
}

function SeasonPicker({ season, seasons, onChange, allowRange }) {
  if (!seasons?.length) return null
  const newest = seasons[seasons.length - 1]
  const setMode = m => {
    if (m === 'single') onChange({ mode: 'single', from: season.to, to: season.to })
    else { const ti = seasons.findIndex(s => s.id === season.to?.id); onChange({ mode: 'range', from: seasons[Math.max(0, ti - 1)], to: season.to }) }
  }
  const presets = [
    { label: 'This + last', range: [seasons[Math.max(0, seasons.length - 2)], newest] },
    { label: 'Last 3', range: [seasons[Math.max(0, seasons.length - 3)], newest] },
    { label: 'All seasons', range: [seasons[0], newest] },
  ]
  return (
    <Popover width={340} trigger={open => <PillTrigger icon="clock" sub="Season" label={season.mode === 'single' ? season.to?.label : `${season.from?.label} → ${season.to?.label}`} open={open} accent />}>
      {() => (
        <div>
          {allowRange && (
            <div className="mb-3"><Segmented sm value={season.mode} onChange={setMode}
              options={[{ value: 'single', label: 'Single' }, { value: 'range', label: 'Compare' }]} /></div>
          )}
          <SeasonTimeline season={season} seasons={seasons} onChange={onChange} mode={allowRange ? season.mode : 'single'} />
          {allowRange && season.mode === 'range' && (
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2">Quick ranges</div>
              <div className="flex flex-wrap gap-2">
                {presets.map(p => {
                  const active = season.from?.id === p.range[0]?.id && season.to?.id === p.range[1]?.id
                  return (
                    <button key={p.label} onClick={() => onChange({ mode: 'range', from: p.range[0], to: p.range[1] })}
                      className="iq-display font-semibold text-[12px] transition" style={{ padding: '6px 11px', borderRadius: 8,
                        background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
                        color: active ? 'var(--pb-accent)' : 'var(--pb-dim)', border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}` }}>{p.label}</button>
                  )
                })}
              </div>
            </div>
          )}
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
