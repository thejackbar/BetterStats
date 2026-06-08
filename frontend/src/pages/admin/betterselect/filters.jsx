// Unified filter system for the BetterSelect admin screens. One pattern across
// Players / Fixtures / Squads / Availability / Selection so the filter UX can't
// drift per screen: an always-visible search, a "Filters" button with an active
// count, removable active-filter chips, "Clear all", and a collapsible panel of
// facet groups. Filter state lives in the URL, so navigating away and back keeps
// the view (and links are shareable).
//
// A screen declares its facets and feeds them to useFilters + FilterBar:
//   const FACETS = useMemo(() => [
//     { key: 'squad', label: 'Squad', type: 'multi', options: [{ value, label }] },
//     { key: 'avail', label: 'Availability', type: 'multi', options: AVAIL_OPTS },
//     { key: 'gender', label: 'Gender', type: 'single', options: [...] },
//     { key: 'overseas', label: 'Overseas only', type: 'bool' },
//   ], [squadOpts])
//   const filters = useFilters(FACETS)
//   <FilterBar filters={filters} facets={FACETS} count={shown.length} total={all.length} />
//
// Facet types:
//   multi  → value is string[]  (checkbox list; one chip per selection)
//   single → value is '' | str  (chip row, single choice; '' = any)
//   bool   → value is boolean   (a flag; grouped under "Show only")
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Chip, Search, Icon, FilterButton } from './ui'

const isBlank = (v) => v == null || v === '' || (Array.isArray(v) && v.length === 0)

/* URL-backed filter state for a set of facet definitions. Only touches its own
 * keys (+ the search key), so unrelated query params — e.g. ?player= — survive.
 * Uses history replace so typing in search doesn't spam the back stack. */
export function useFilters(facets, { searchKey = 'q' } = {}) {
  const [params, setParams] = useSearchParams()

  const values = useMemo(() => {
    const v = {}
    for (const f of facets) {
      if (f.type === 'multi') v[f.key] = params.getAll(f.key)
      else if (f.type === 'bool') v[f.key] = params.get(f.key) === '1'
      else v[f.key] = params.get(f.key) || ''
    }
    return v
  }, [params, facets])

  const search = params.get(searchKey) || ''

  const apply = useCallback((mut) => {
    setParams((prev) => { const p = new URLSearchParams(prev); mut(p); return p }, { replace: true })
  }, [setParams])

  const setSearch = useCallback((val) => apply((p) => {
    if (val) p.set(searchKey, val); else p.delete(searchKey)
  }), [apply, searchKey])

  // single ('' clears) and bool (false clears) facets
  const setValue = useCallback((key, val) => apply((p) => {
    if (val === '' || val === false || val == null) p.delete(key)
    else p.set(key, val === true ? '1' : String(val))
  }), [apply])

  // multi facet: add/remove one value
  const toggle = useCallback((key, val) => apply((p) => {
    const cur = p.getAll(key)
    p.delete(key)
    const next = cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val]
    next.forEach((x) => p.append(key, x))
  }), [apply])

  // multi facet: replace the whole value list (Select all / Clear in a picker)
  const setMulti = useCallback((key, vals) => apply((p) => {
    p.delete(key)
    ;(vals || []).forEach((x) => p.append(key, x))
  }), [apply])

  const clearAll = useCallback(() => apply((p) => { facets.forEach((f) => p.delete(f.key)) }), [apply, facets])

  const activeCount = useMemo(() => facets.reduce((n, f) => {
    const v = values[f.key]
    if (f.type === 'multi') return n + (v?.length || 0)
    return n + (isBlank(v) || v === false ? 0 : 1)
  }, 0), [facets, values])

  return { values, search, setSearch, setValue, toggle, setMulti, clearAll, activeCount }
}

function labelOf(facet, val) {
  const o = facet.options?.find((x) => x.value === val)
  return o ? o.label : val
}

/* Titled column inside the panel. */
function Group({ title, children }) {
  return (
    <div className="min-w-[140px]">
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest mb-1.5 pb-1 border-b border-pb-hairline">{title}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  )
}
function Check({ label, checked, onChange, dot }) {
  return (
    <label className="flex items-center gap-2 text-[12.5px] text-pb-dim hover:text-pb-text cursor-pointer">
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-pb-accent" />
      {dot && <span className="w-[7px] h-[7px] rounded-full" style={{ background: dot }} />}
      {label}
    </label>
  )
}
function ActiveChip({ label, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-pb-accent/40 bg-pb-accent/10 text-pb-accent text-[11.5px] pl-2.5 pr-1.5 py-1">
      {label}
      <button type="button" onClick={onRemove} className="hover:text-pb-text" aria-label={`Remove ${label}`}>
        <Icon name="close" size={12} />
      </button>
    </span>
  )
}

/* The shared filter bar. `right` is a slot for screen-specific controls that
 * don't fit the facet model (e.g. a recency dropdown or a scope segmented). */
export function FilterBar({ filters, facets, searchPlaceholder = 'Search…', count, total, right, showSearch = true, className = '' }) {
  const [open, setOpen] = useState(false)
  const { values, search, setSearch, setValue, toggle, clearAll, activeCount } = filters

  const bools = facets.filter((f) => f.type === 'bool')
  const groups = facets.filter((f) => f.type !== 'bool')

  const chips = []
  for (const f of facets) {
    const v = values[f.key]
    if (f.type === 'multi') (v || []).forEach((val) => chips.push({ id: `${f.key}:${val}`, label: `${f.label}: ${labelOf(f, val)}`, remove: () => toggle(f.key, val) }))
    else if (f.type === 'bool') { if (v) chips.push({ id: f.key, label: f.label, remove: () => setValue(f.key, false) }) }
    else if (!isBlank(v)) chips.push({ id: f.key, label: `${f.label}: ${labelOf(f, v)}`, remove: () => setValue(f.key, '') })
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex flex-wrap items-center gap-2">
        {showSearch && <Search value={search} onChange={setSearch} placeholder={searchPlaceholder} className="min-w-[180px] flex-1 max-w-[320px]" />}
        {facets.length > 0 && <FilterButton active={open} count={activeCount} onClick={() => setOpen((o) => !o)} />}
        {right}
        {typeof count === 'number' && (
          <span className="ml-auto text-[11.5px] text-pb-faint pb-num whitespace-nowrap">
            {typeof total === 'number' && total !== count ? `${count} of ${total}` : count}
          </span>
        )}
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {chips.map((c) => <ActiveChip key={c.id} label={c.label} onRemove={c.remove} />)}
          <button type="button" onClick={clearAll} className="text-[11.5px] text-pb-faint hover:text-pb-accent underline underline-offset-2 ml-1">Clear all</button>
        </div>
      )}

      {open && facets.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-4 rounded-lg border border-pb-hairline2 bg-pb-surface2/40 px-4 py-3">
          {groups.map((f) => (
            <Group key={f.key} title={f.label}>
              {f.type === 'multi'
                ? f.options.map((o) => (
                    <Check key={o.value} label={o.label} dot={o.dot}
                      checked={(values[f.key] || []).includes(o.value)}
                      onChange={() => toggle(f.key, o.value)} />
                  ))
                : (
                  <div className="flex flex-wrap gap-1.5">
                    {f.options.map((o) => (
                      <Chip key={o.value} label={o.label} dot={o.dot}
                        active={values[f.key] === o.value}
                        onClick={() => setValue(f.key, values[f.key] === o.value ? '' : o.value)} />
                    ))}
                  </div>
                )}
            </Group>
          ))}
          {bools.length > 0 && (
            <Group title="Show only">
              {bools.map((f) => (
                <Check key={f.key} label={f.label}
                  checked={!!values[f.key]}
                  onChange={() => setValue(f.key, !values[f.key])} />
              ))}
            </Group>
          )}
        </div>
      )}
    </div>
  )
}

/* Close-on-outside-click + Escape, shared by the popover controls below. */
function useDismiss(open, onClose) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  return ref
}

/* Lightweight sort popover. `options` = [{ value, label }]. */
export function SortMenu({ value, onChange, options }) {
  const [open, setOpen] = useState(false)
  const ref = useDismiss(open, () => setOpen(false))
  const cur = options.find((s) => s.value === value) || options[0]
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} title="Sort pool"
        className="inline-flex items-center gap-1.5 h-[38px] px-2.5 rounded-lg border border-pb-hairline2 text-pb-dim hover:text-pb-text text-[12.5px] font-display font-semibold whitespace-nowrap">
        <Icon name="ladders" size={14} />
        <span className="hidden sm:inline">{cur.label}</span>
        <Icon name="chevron" size={12} className="rotate-90 opacity-70" />
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+6px)] z-50 min-w-[176px] p-1.5 rounded-xl bg-pb-surface border border-pb-hairline2 shadow-xl">
          <div className="font-mono text-[9.5px] uppercase tracking-wide3 text-pb-faintest px-2 pt-1 pb-1.5">Sort by</div>
          {options.map((s) => (
            <button key={s.value} type="button" onClick={() => { onChange(s.value); setOpen(false) }}
              className={`flex items-center gap-1.5 w-full px-2 py-1.5 rounded-lg text-[13px] font-display text-left transition hover:bg-pb-surface2 ${s.value === value ? 'text-pb-accent' : 'text-pb-dim hover:text-pb-text'}`}>
              <span className="w-3.5 inline-flex">{s.value === value && <Icon name="check" size={13} />}</span>{s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* Searchable multi-select for long squad lists. `options` = [{ value, label,
 * count }] (label is the short name; count = pool members, used to surface the
 * busiest squads as one-tap quick chips). State stays in the filter facet via
 * onToggle / onSetMany. */
export function SquadPicker({ options, selected, onToggle, onSetMany, quickCount = 5 }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useDismiss(open, () => setOpen(false))
  const sel = selected || []

  const quick = useMemo(() =>
    [...options].sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, quickCount),
    [options, quickCount])
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    return s ? options.filter((o) => o.label.toLowerCase().includes(s) || o.value.toLowerCase().includes(s)) : options
  }, [options, q])

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12.5px] transition whitespace-nowrap ${sel.length ? 'border-pb-accent/50 text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}>
        <Icon name="teams" size={14} />
        Squad{sel.length ? <span className="font-mono text-[10px] font-bold inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-pb-accent text-pb-bg">{sel.length}</span> : ''}
        <Icon name="chevron" size={12} className="rotate-90 opacity-70" />
      </button>
      {open && (
        <div className="absolute left-0 top-[calc(100%+6px)] z-50 w-[260px] max-w-[80vw] rounded-xl bg-pb-surface border border-pb-hairline2 shadow-xl overflow-hidden">
          {quick.length > 1 && (
            <div className="px-2.5 pt-2.5 pb-2 border-b border-pb-hairline">
              <div className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest mb-1.5">Quick pick</div>
              <div className="flex flex-wrap gap-1.5">
                {quick.map((o) => (
                  <button key={o.value} type="button" onClick={() => onToggle(o.value)}
                    className={`text-[11.5px] font-display font-semibold rounded-full px-2.5 py-1 border transition ${sel.includes(o.value) ? 'bg-pb-accent/14 border-pb-accent/45 text-pb-accent' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="p-2 border-b border-pb-hairline">
            <Search value={q} onChange={setQ} placeholder="Find a squad…" />
          </div>
          <div className="max-h-[240px] overflow-auto pb-scroll p-1">
            {filtered.map((o) => (
              <label key={o.value} className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[12.5px] text-pb-dim hover:text-pb-text hover:bg-pb-surface2 cursor-pointer">
                <input type="checkbox" className="accent-pb-accent" checked={sel.includes(o.value)} onChange={() => onToggle(o.value)} />
                <span className="flex-1 min-w-0 truncate">{o.label}</span>
                {o.count != null && <span className="font-mono text-[10px] text-pb-faintest pb-num">{o.count}</span>}
              </label>
            ))}
            {filtered.length === 0 && <div className="px-2 py-3 text-[12px] text-pb-faint">No squads match.</div>}
          </div>
          <div className="flex items-center justify-between px-2.5 py-2 border-t border-pb-hairline">
            <button type="button" onClick={() => onSetMany(options.map((o) => o.value))} className="text-[11.5px] text-pb-faint hover:text-pb-accent">Select all</button>
            <button type="button" onClick={() => onSetMany([])} className="text-[11.5px] text-pb-faint hover:text-pb-accent">Clear</button>
          </div>
        </div>
      )}
    </div>
  )
}
