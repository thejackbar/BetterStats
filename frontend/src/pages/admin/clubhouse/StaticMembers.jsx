import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { Button, Badge, Caption, INPUT_CLS, Note } from '../../../components/admin/ui'
import { ContactDetailModal } from '../bettercomms/CommsContacts'
import {
  FACETS, emptyFilters, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect,
  matchesSuppressed, SuppressedToggle, emptyModes, matchesModes, anyMode,
  DirectoryFilterChips, searchHint,
  matchesUnsubscribed, UnsubscribedToggle, unsubscribedTitle,
} from '../bettercomms/audience'

// Who is in this segment — as two live tiles, not two ever-present lists.
//
// The tiles count the WHOLE segment audience (rules ∪ static set ∪ included
// segments − excluded), so they move the moment ANY criterion above changes —
// add a rule, tick an exclude, hand-pick a contact. `inCount` / `outCount` are
// the exact server figures (from /segments/resolve); the lists below are the
// (filtered, capped) view of who those are.
//
// Click a tile to reveal its list; both tiles stay on screen so you can flick
// between "in" and "not in". Hand-picking still lives here: a contact in the
// OUT list has Add (into the static set), and a contact in the IN list that is
// there BECAUSE it was hand-picked has Remove. A contact in the IN list only
// because a rule or an included segment matched it carries a "matched" tag and
// no Remove — you cannot hand-remove someone a rule keeps pulling back in; edit
// the rule instead. Bulk add / remove and per-contact details are unchanged.
//
// Engagement score / top-N / page-view controls used to live here as browsing
// filters. They are ACTIVE properties, not a way of hand-picking, so they moved
// to the Active rules section (engagement score, page views and users-viewing
// are all rule fields there). Only the plain browsing filters remain.

const noFilters = emptyFilters

function Tile({ label, n, sub, active, tone, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex-1 min-w-[150px] text-left rounded-xl px-4 py-3 border transition
        ${active ? 'border-pb-accent bg-pb-surface2' : 'pb-hairline hover:bg-pb-surface2'}`}>
      <div className="text-2xl font-bold tabular-nums"
        style={tone === 'ok' ? { color: 'var(--pb-positive-ink)' } : undefined}>
        {n == null ? '—' : n}
      </div>
      <div className="text-pb-dim text-[12.5px] mt-0.5">{label}</div>
      <div className="text-pb-faintest text-[10.5px] mt-0.5">{active ? 'Showing — tap to hide' : sub}</div>
    </button>
  )
}

function ContactRow({ c, action, onDetails, last, checked, onCheck, tag }) {
  return (
    <div className={`flex items-center gap-3 py-1.5 ${last ? '' : 'pb-hairline-t'}`}>
      {onCheck
        ? <input type="checkbox" className="accent-pb-accent shrink-0" checked={checked} onChange={onCheck} onClick={e => e.stopPropagation()} />
        : <span className="w-[13px] shrink-0" />}
      <button onClick={() => onDetails(c.id)} className="min-w-0 text-left hover:opacity-80 flex-1" title="View details">
        <span className="text-sm text-pb-text truncate">{c.name || c.first_name || c.email}</span>
        {(c.name || c.first_name) && <span className="text-pb-faintest text-xs ml-2 truncate">{c.email}</span>}
        {(c.club || c.state) && (
          <span className="text-pb-faintest text-[11px] ml-2 truncate">{[c.club, c.state].filter(Boolean).join(' · ')}</span>
        )}
      </button>
      {tag && <span className="shrink-0 text-pb-faintest text-[10px] uppercase tracking-wide">{tag}</span>}
      {c.subscribed === false && (
        <span className="shrink-0" title={unsubscribedTitle(c) || 'Unsubscribed'}><Badge>Unsubscribed</Badge></span>
      )}
      {c.suppressed && (
        <span className="shrink-0" title="Suppressed — bounced, complained, unsubscribed or excluded"><Badge toneKey="block">Supp</Badge></span>
      )}
      {action}
    </div>
  )
}

export default function StaticMembers({
  segmentId, audienceContacts, inCount, outCount, reachable, otherRoute, clubs, onChanged,
}) {
  const [memberRows, setMemberRows] = useState(segmentId ? null : [])
  const [contacts, setContacts] = useState(null)
  const [view, setView] = useState(null)       // 'in' | 'out' | null — which list is open
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(noFilters)
  const [modes, setModes] = useState(emptyModes)
  const [supp, setSupp] = useState('all')
  const [unsub, setUnsub] = useState('all')
  const [selected, setSelected] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const [detailId, setDetailId] = useState(null)
  const [note, setNote] = useState('')

  const loadMembers = useCallback(() => {
    if (!segmentId) { setMemberRows([]); return }
    api.commsSegmentMembers(segmentId)
      .then(rows => setMemberRows(rows || []))
      .catch(() => setMemberRows([]))
  }, [segmentId])
  const loadContacts = useCallback(() => {
    api.commsListContacts({}).then(r => setContacts(r.contacts || [])).catch(() => setContacts([]))
  }, [])
  useEffect(() => { loadMembers() }, [loadMembers])
  useEffect(() => { loadContacts() }, [loadContacts])
  // A fresh segment resets the working selection and filters.
  useEffect(() => { setSelected(new Set()); setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setNote('') }, [segmentId])

  const memberIds = useMemo(() => new Set((memberRows || []).map(r => r.id)), [memberRows])
  const inIds = useMemo(() => new Set((audienceContacts || []).map(c => c.id)), [audienceContacts])
  const facetOptions = useMemo(() => facetOptionsFrom(contacts), [contacts])
  const showDirChips = useMemo(() => (contacts || []).some(c => c.club), [contacts])

  const q = query.trim().toLowerCase()
  const passes = useCallback((c) =>
    matchesQuery(c, q) && matchesFilters(c, filters) && matchesModes(c, modes)
    && matchesSuppressed(c, supp) && matchesUnsubscribed(c, unsub),
    [q, filters, modes, supp, unsub])

  // The IN list is the resolved audience itself; the OUT list is every other
  // sendable contact. Both are then narrowed by the browsing filters.
  const inList = useMemo(() => (audienceContacts || []).filter(passes), [audienceContacts, passes])
  const outList = useMemo(() =>
    (contacts || []).filter(c => !inIds.has(c.id) && passes(c)),
    [contacts, inIds, passes])
  const shown = view === 'in' ? inList : view === 'out' ? outList : []

  const isChecked = (id) => selected.has(id)
  const toggleOne = (id) => setSelected(prev => {
    const n = new Set(prev)
    if (n.has(id)) n.delete(id); else n.add(id)
    return n
  })
  const setMany = (ids, on) => setSelected(prev => {
    const n = new Set(prev)
    ids.forEach(id => { if (on) n.add(id); else n.delete(id) })
    return n
  })

  const refreshAll = () => { loadMembers(); onChanged?.() }

  const doAdd = async (ids) => {
    if (!ids.length || !segmentId) return
    setBusy(true)
    try { await api.commsAddSegmentMembers(segmentId, ids); setMany(ids, false); refreshAll(); setNote(`Added ${ids.length} to the segment.`) }
    finally { setBusy(false) }
  }
  const doRemove = async (ids) => {
    if (!ids.length || !segmentId) return
    setBusy(true)
    try { await api.commsRemoveSegmentMembers(segmentId, ids); setMany(ids, false); refreshAll(); setNote(`Removed ${ids.length} hand-picked ${ids.length === 1 ? 'contact' : 'contacts'}.`) }
    finally { setBusy(false) }
  }

  // Bulk targets, computed against the OPEN list only.
  const selInStatic = view === 'in' ? [...selected].filter(id => memberIds.has(id) && inIds.has(id)) : []
  const selOut = view === 'out' ? [...selected].filter(id => !inIds.has(id)) : []
  const clearSelection = () => setSelected(new Set())
  const selectAllShown = () => setMany(shown.map(c => c.id), true)
  const clearAll = () => { setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all') }
  const activeFilters = FACETS.some(f => filters[f.key].length) || anyMode(modes) || !!q || supp !== 'all' || unsub !== 'all'

  const openTile = (v) => { setView(cur => (cur === v ? null : v)); setSelected(new Set()) }

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        <Tile label="In this segment" n={inCount} tone="ok" active={view === 'in'}
          sub="Rules, hand-picked and included — tap to view" onClick={() => openTile('in')} />
        <Tile label="Not in this segment" n={outCount} active={view === 'out'}
          sub="Everyone else you could add — tap to view" onClick={() => openTile('out')} />
      </div>

      {inCount > 0 && (reachable != null) && (
        <div className="text-pb-faintest text-[11.5px] mt-2">
          <b style={{ color: 'var(--pb-positive-ink)' }}>{reachable}</b> reachable by email
          {otherRoute > 0 && <> · <b style={{ color: '#f5b542' }}>{otherRoute}</b> need another route</>}
          {clubs > 0 && <> · <b style={{ color: 'var(--pb-accent-ink)' }}>{clubs}</b> {clubs === 1 ? 'club' : 'clubs'}</>}
        </div>
      )}

      {!segmentId && (
        <Note toneKey="calm" className="mt-3">
          Save the segment to hand-pick specific contacts. The tiles above already count who the rules match.
        </Note>
      )}

      {view && (
        <div className="mt-3">
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder={searchHint(showDirChips)}
            className={`${INPUT_CLS} mb-2`} />
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {FACETS.filter(f => facetOptions[f.key].length > 0).map(f => (
              <MultiSelect key={f.key} label={f.label} options={facetOptions[f.key]}
                selected={filters[f.key]} onChange={(v) => setFilters(s => ({ ...s, [f.key]: v }))} />
            ))}
            <SuppressedToggle value={supp} onChange={setSupp} />
            <UnsubscribedToggle value={unsub} onChange={setUnsub} />
            {activeFilters && (
              <button onClick={clearAll}
                className="text-xs text-pb-faint hover:text-pb-accent underline underline-offset-2">Clear filters</button>
            )}
            <span className="text-pb-faintest text-xs ml-auto">{shown.length} shown</span>
          </div>
          {showDirChips && (
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              <Caption className="mr-1">Directory</Caption>
              <DirectoryFilterChips modes={modes} onChange={setModes} />
              <span className="text-pb-faintest text-[10px] ml-1">tap once to exclude, twice to include</span>
            </div>
          )}

          {segmentId && (
            <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 pb-hairline-b">
              <Button size="sm" onClick={selectAllShown} disabled={!shown.length}>
                Select all shown ({shown.length})
              </Button>
              {selected.size > 0 ? (
                <>
                  <span className="text-pb-text text-[12.5px] font-semibold">{selected.size} selected</span>
                  {view === 'out' && (
                    <Button size="sm" variant="primary" onClick={() => doAdd(selOut)} disabled={busy || !selOut.length}>
                      Add ({selOut.length})
                    </Button>
                  )}
                  {view === 'in' && (
                    <Button size="sm" variant="danger" onClick={() => doRemove(selInStatic)} disabled={busy || !selInStatic.length}>
                      Remove ({selInStatic.length})
                    </Button>
                  )}
                  <Button size="sm" variant="quiet" onClick={clearSelection}>Clear selection</Button>
                </>
              ) : (
                <span className="text-pb-faintest text-[12.5px]">
                  Tick contacts to {view === 'out' ? 'add them' : 'remove hand-picked ones'} in bulk.
                </span>
              )}
            </div>
          )}

          {note && <Note className="mb-3">{note}</Note>}

          {contacts == null || (view === 'in' && memberRows == null) ? (
            <div className="text-pb-faint text-sm">Loading…</div>
          ) : shown.length === 0 ? (
            <div className="text-pb-faintest text-sm">
              {view === 'in'
                ? (activeFilters ? 'Nobody in the segment matches your search.' : 'Nobody is in the segment yet — add a rule or hand-pick below.')
                : (activeFilters ? 'No other contacts match.' : 'Every contact is already in the segment.')}
            </div>
          ) : (
            <div className="max-h-[28rem] overflow-y-auto">
              {shown.slice(0, 500).map((c, i) => {
                const isStatic = memberIds.has(c.id)
                return (
                  <ContactRow key={c.id} c={c} last={i === 0} onDetails={setDetailId}
                    checked={isChecked(c.id)}
                    onCheck={segmentId ? () => toggleOne(c.id) : null}
                    tag={view === 'in' && !isStatic ? 'matched' : null}
                    action={!segmentId ? null : view === 'out' ? (
                      <Button size="sm" variant="primary" onClick={() => doAdd([c.id])} disabled={busy}>Add</Button>
                    ) : isStatic ? (
                      <Button size="sm" variant="danger" onClick={() => doRemove([c.id])} disabled={busy}>Remove</Button>
                    ) : null} />
                )
              })}
              {shown.length > 500 && (
                <div className="text-pb-faintest text-[10px] uppercase tracking-wide2 mt-2 py-1">
                  Showing the first 500 of {shown.length} — narrow with the filters above
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => loadContacts()} />}
    </div>
  )
}
