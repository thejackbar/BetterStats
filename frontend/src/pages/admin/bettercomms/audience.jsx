// Shared building blocks for the BetterComms contact-audience UI — used by both
// Lists (manual membership) and Segments (saved-filter preview): the field set a
// contact is searched on, the directory facet filters, a searchable multi-select
// dropdown, a client-side CSV export, and a read-only audience preview panel.
import { useState, useEffect, useMemo, useRef } from 'react'

// Fields a contact is searched on (contains, OR across all of them).
export const SEARCH_FIELDS = ['name', 'email', 'club', 'association', 'utm_code', 'state', 'website']
// The Clubs Directory facets offered as multi-select filters.
export const FACETS = [
  { key: 'club', label: 'Club' },
  { key: 'association', label: 'Association' },
  { key: 'utm_code', label: 'UTM code' },
  { key: 'state', label: 'State' },
]

export function matchesQuery(c, q) {
  if (!q) return true
  return SEARCH_FIELDS.some(f => (c[f] || '').toLowerCase().includes(q))
}
export function matchesFilters(c, filters) {
  return FACETS.every(f => {
    const sel = filters[f.key]
    return !sel || !sel.length || sel.includes(c[f.key] || '')
  })
}
export function emptyFilters() {
  return { club: [], association: [], utm_code: [], state: [] }
}
export function facetOptionsFrom(contacts) {
  const opts = { club: new Set(), association: new Set(), utm_code: new Set(), state: new Set() }
  for (const c of contacts || []) for (const f of FACETS) { if (c[f.key]) opts[f.key].add(c[f.key]) }
  return Object.fromEntries(FACETS.map(f => [f.key, [...opts[f.key]].sort((a, b) => a.localeCompare(b))]))
}

// ─── CSV ─────────────────────────────────────────────────────────────────────
const CSV_COLS = [
  ['name', 'Name'], ['email', 'Email'], ['club', 'Club'], ['association', 'Association'],
  ['utm_code', 'UTM code'], ['state', 'State'], ['website', 'Website'],
]
function csvCell(v) {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
export function contactsToCsv(rows) {
  const header = [...CSV_COLS.map(([, l]) => l), 'Subscribed']
  const lines = [header.map(csvCell).join(',')]
  for (const c of rows) {
    const cells = CSV_COLS.map(([k]) => csvCell(c[k]))
    cells.push(c.subscribed === false ? 'no' : 'yes')
    lines.push(cells.join(','))
  }
  return lines.join('\n')
}
export function downloadCsv(filename, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function safeFilename(name) {
  const slug = (name || 'audience').trim().replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '')
  return `${(slug || 'audience').toLowerCase()}.csv`
}

// ─── Searchable multi-select (mirrors the Club Directory association picker) ──
export function MultiSelect({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [])
  const ql = q.toLowerCase()
  const filtered = options.filter(o => o.toLowerCase().includes(ql)).slice(0, 800)
  const toggle = (v) => onChange(selected.includes(v) ? selected.filter(x => x !== v) : [...selected, v])
  return (
    <div className="relative" ref={ref}>
      <button type="button"
        className="flex items-center gap-1.5 bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent"
        onClick={() => setOpen(o => !o)}>
        <span>{selected.length ? `${label} (${selected.length})` : label}</span>
        {selected.length > 0 && (
          <span role="button" title="Clear" className="text-pb-faint hover:text-pb-red"
            onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-72 max-w-[92vw] max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder={`Search ${label.toLowerCase()}…`}
            className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent mb-2" />
          {selected.length > 0 && (
            <button type="button" className="text-[11px] text-pb-faint hover:text-pb-accent mb-1" onClick={() => onChange([])}>clear selection</button>
          )}
          {!filtered.length && <div className="text-xs text-pb-faint px-1 py-2">No options.</div>}
          {filtered.map(o => (
            <label key={o} className="flex items-center gap-2 px-1 py-0.5 text-xs text-pb-text hover:bg-pb-surface rounded cursor-pointer">
              <input type="checkbox" className="accent-pb-accent" checked={selected.includes(o)} onChange={() => toggle(o)} />
              <span className="truncate" title={o}>{o}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Read-only audience preview (search + filters + CSV) ─────────────────────
// `contacts` is the resolved audience; the panel does its own client-side search
// and filtering, and exports exactly what's shown.
export function AudiencePanel({ contacts, total, loading, csvName = 'audience', onRowClick }) {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(emptyFilters)

  const facetOptions = useMemo(() => facetOptionsFrom(contacts), [contacts])
  const q = query.trim().toLowerCase()
  const shown = useMemo(() =>
    (contacts || []).filter(c => matchesQuery(c, q) && matchesFilters(c, filters)),
    [contacts, q, filters])
  const activeFilters = !!q || FACETS.some(f => filters[f.key].length)

  return (
    <div>
      <input value={query} onChange={e => setQuery(e.target.value)}
        placeholder="Search name, email, club, association, UTM code, state or website…"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-2" />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {FACETS.filter(f => facetOptions[f.key].length > 0).map(f => (
          <MultiSelect key={f.key} label={f.label} options={facetOptions[f.key]}
            selected={filters[f.key]} onChange={(v) => setFilters(s => ({ ...s, [f.key]: v }))} />
        ))}
        {activeFilters && (
          <button onClick={() => { setQuery(''); setFilters(emptyFilters()) }}
            className="text-xs text-pb-faint hover:text-pb-accent underline underline-offset-2">Clear filters</button>
        )}
        <button onClick={() => downloadCsv(safeFilename(csvName), contactsToCsv(shown))}
          disabled={!shown.length}
          className="ml-auto px-2.5 py-1.5 rounded text-xs font-medium border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-40">
          Export CSV ({shown.length})
        </button>
      </div>

      {loading ? (
        <div className="text-pb-faint text-sm">Loading audience…</div>
      ) : (contacts || []).length === 0 ? (
        <div className="text-pb-faintest text-sm">No contacts match this segment yet.</div>
      ) : (
        <>
          <div className="text-pb-faintest text-xs mb-1">
            {shown.length}{typeof total === 'number' && total > (contacts || []).length ? ` of ${total}` : ''} shown
            {typeof total === 'number' && total > (contacts || []).length && (
              <span className="ml-1">(preview capped at {(contacts || []).length})</span>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto pb-hairline-t">
            {shown.map((c, i) => (
              <div key={c.id} className={`flex items-center gap-3 py-1.5 ${i === 0 ? '' : 'pb-hairline-t'}`}>
                <button onClick={() => onRowClick && onRowClick(c.id)} disabled={!onRowClick}
                  className="min-w-0 text-left flex-1 hover:opacity-80 disabled:hover:opacity-100" title={onRowClick ? 'View details' : undefined}>
                  <span className="text-sm text-pb-text truncate">{c.name || c.email}</span>
                  {c.name && <span className="text-pb-faintest text-xs ml-2 truncate">{c.email}</span>}
                  {(c.club || c.state) && (
                    <span className="text-pb-faintest text-[11px] ml-2 truncate">{[c.club, c.state].filter(Boolean).join(' · ')}</span>
                  )}
                </button>
              </div>
            ))}
            {shown.length === 0 && <div className="text-pb-faintest text-sm py-2">No contacts match your search.</div>}
          </div>
        </>
      )}
    </div>
  )
}
