import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { ContactDetailModal } from './CommsContacts'
import { FACETS, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect, matchesSuppressed, SuppressedToggle,
  emptyModes, matchesModes, anyMode, DirectoryFilterChips, searchHint,
  emptyEngagementFilter, matchesEngagementScore, topClubIds, matchesTopClubs, EngagementFilterControls,
  matchesUnsubscribed, UnsubscribedToggle, unsubscribedTitle } from './audience'

// Dropdown for choosing one or more target lists to copy the selection into.
function CopyToLists({ lists, currentId, onCopy }) {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState([])
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const targets = lists.filter(l => l.id !== currentId)
  const toggle = (id) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  const go = async () => { await onCopy(picked); setPicked([]); setOpen(false) }
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className="px-2.5 py-1.5 rounded text-xs font-medium border pb-hairline text-pb-text hover:border-pb-accent">
        Copy to lists ▾
      </button>
      {open && (
        <div className="absolute z-30 mt-1 right-0 w-64 max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          {targets.length === 0 ? (
            <div className="text-xs text-pb-faint px-1 py-2">No other lists. Create one first.</div>
          ) : (
            <>
              <div className="text-pb-faintest text-[11px] uppercase tracking-wide2 px-1 mb-1">Copy selected into</div>
              {targets.map(l => (
                <label key={l.id} className="flex items-center gap-2 px-1 py-1 text-xs text-pb-text hover:bg-pb-surface rounded cursor-pointer">
                  <input type="checkbox" className="accent-pb-accent" checked={picked.includes(l.id)} onChange={() => toggle(l.id)} />
                  <span className="truncate flex-1" title={l.name}>{l.name}</span>
                  <span className="text-pb-faintest">{l.count}</span>
                </label>
              ))}
              <button type="button" onClick={go} disabled={!picked.length}
                className="mt-2 w-full px-2.5 py-1.5 rounded text-xs font-medium text-white disabled:opacity-40"
                style={{ background: 'var(--pb-accent)' }}>
                Copy to {picked.length || ''} list{picked.length === 1 ? '' : 's'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ContactRow({ c, action, onDetails, last, checked, onCheck }) {
  return (
    <div className={`flex items-center gap-3 py-1.5 ${last ? '' : 'pb-hairline-t'}`}>
      <input type="checkbox" className="accent-pb-accent shrink-0" checked={checked} onChange={onCheck} onClick={e => e.stopPropagation()} />
      <button onClick={() => onDetails(c.id)} className="min-w-0 text-left hover:opacity-80 flex-1" title="View details">
        <span className="text-sm text-pb-text truncate">{c.name || c.first_name || c.email}</span>
        {(c.name || c.first_name) && <span className="text-pb-faintest text-xs ml-2 truncate">{c.email}</span>}
        {(c.club || c.state) && (
          <span className="text-pb-faintest text-[11px] ml-2 truncate">{[c.club, c.state].filter(Boolean).join(' · ')}</span>
        )}
      </button>
      {c.subscribed === false && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint border border-pb-faint/30 rounded px-1.5 py-0.5 shrink-0" title={unsubscribedTitle(c) || 'Unsubscribed'}>unsubscribed</span>}
      {c.suppressed && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5 shrink-0" title="Suppressed — bounced, complained, unsubscribed or excluded">supp</span>}
      {action}
    </div>
  )
}

// Prominent section header that reads in both light and dark themes.
function SectionHeader({ title, count, allChecked, onToggleAll, hasRows }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-md bg-pb-surface2 border pb-hairline mb-2">
      <div className="flex items-center gap-2.5 min-w-0">
        {hasRows && (
          <input type="checkbox" className="accent-pb-accent shrink-0" checked={allChecked} onChange={onToggleAll}
            title="Select all shown in this section" />
        )}
        <span className="text-pb-text text-sm font-semibold uppercase tracking-wide2 truncate">
          {title} <span className="text-pb-faint font-normal">({count})</span>
        </span>
      </div>
    </div>
  )
}

function ListDetail({ list, lists, onChanged }) {
  const [memberIds, setMemberIds] = useState(null)
  const [contacts, setContacts] = useState(null)
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState({ club: [], association: [], country: [], utm_code: [], state: [] })
  const [modes, setModes] = useState(emptyModes)
  const [engagement, setEngagement] = useState(emptyEngagementFilter)
  const [supp, setSupp] = useState('all')
  const [unsub, setUnsub] = useState('all')
  const [selected, setSelected] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const [detailId, setDetailId] = useState(null)
  const [note, setNote] = useState('')

  const loadMembers = useCallback(() => {
    api.commsListMembers(list.id)
      .then(rows => setMemberIds(new Set(rows.map(r => r.id))))
      .catch(() => setMemberIds(new Set()))
  }, [list.id])
  const loadContacts = useCallback(() => {
    api.commsListContacts({}).then(r => setContacts(r.contacts || [])).catch(() => setContacts([]))
  }, [])
  useEffect(() => { loadMembers() }, [loadMembers])
  useEffect(() => { loadContacts() }, [loadContacts])
  // A fresh list resets the working selection.
  useEffect(() => { setSelected(new Set()); setQuery(''); setFilters({ club: [], association: [], country: [], utm_code: [], state: [] }); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()) }, [list.id])

  const facetOptions = useMemo(() => facetOptionsFrom(contacts), [contacts])
  // Directory include/exclude chips only make sense when contacts carry club data
  // (BetterCricket outreach contacts) — a normal club's own members don't.
  const showDirChips = useMemo(() => (contacts || []).some(c => c.club), [contacts])

  const q = query.trim().toLowerCase()
  // Top N ranks clubs among what every OTHER filter already narrowed to (same
  // "top N of what's currently filtered" semantics as the Club Directory page).
  const preFiltered = useMemo(() =>
    (contacts || []).filter(c => matchesQuery(c, q) && matchesFilters(c, filters) && matchesModes(c, modes) && matchesSuppressed(c, supp) && matchesUnsubscribed(c, unsub)),
    [contacts, q, filters, modes, supp, unsub])
  const topIds = useMemo(() => topClubIds(preFiltered, engagement.topNMetric, engagement.topN),
    [preFiltered, engagement.topNMetric, engagement.topN])
  const visible = useMemo(() =>
    preFiltered.filter(c => matchesEngagementScore(c, engagement.gte, engagement.lte) && matchesTopClubs(c, topIds)),
    [preFiltered, engagement, topIds])
  const mids = memberIds || new Set()
  const shownMembers = visible.filter(c => mids.has(c.id))
  const candidates = visible.filter(c => !mids.has(c.id))

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
  const allOf = (rows) => rows.length > 0 && rows.every(c => selected.has(c.id))

  const selMemberIds = [...selected].filter(id => mids.has(id))
  const selCandidateIds = [...selected].filter(id => !mids.has(id))

  const refreshAll = () => { loadMembers(); onChanged() }

  const doAdd = async (ids) => {
    if (!ids.length) return
    setBusy(true)
    try { await api.commsAddListMembers(list.id, ids); setMany(ids, false); refreshAll(); setNote(`Added ${ids.length} to ${list.name}.`) }
    finally { setBusy(false) }
  }
  const doRemove = async (ids) => {
    if (!ids.length) return
    setBusy(true)
    try { await api.commsRemoveListMembers(list.id, ids); setMany(ids, false); refreshAll(); setNote(`Removed ${ids.length} from ${list.name}.`) }
    finally { setBusy(false) }
  }
  const doCopy = async (targetIds) => {
    const ids = [...selected]
    if (!ids.length || !targetIds.length) return
    setBusy(true)
    try {
      const r = await api.commsCopyListMembers(ids, targetIds)
      const total = (r.results || []).reduce((s, x) => s + (x.added || 0), 0)
      onChanged()
      setNote(`Copied ${ids.length} contact${ids.length === 1 ? '' : 's'} into ${targetIds.length} list${targetIds.length === 1 ? '' : 's'} (${total} new membership${total === 1 ? '' : 's'}).`)
    } finally { setBusy(false) }
  }

  const selectAllFiltered = () => setMany(visible.map(c => c.id), true)
  const clearSelection = () => setSelected(new Set())
  const clearAll = () => { setQuery(''); setFilters({ club: [], association: [], country: [], utm_code: [], state: [] }); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()) }
  const activeFilters = FACETS.some(f => filters[f.key].length) || anyMode(modes) || !!q || supp !== 'all' || unsub !== 'all'
    || engagement.gte || engagement.lte || engagement.topN

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="text-sm text-pb-text font-medium">{list.name}</div>
        <a href={api.commsListExportCsvUrl(list.id)}
          className="px-2.5 py-1.5 rounded text-xs font-medium border pb-hairline text-pb-text hover:border-pb-accent shrink-0"
          title="Export this list to CSV">Export CSV</a>
      </div>

      {/* Search + filters */}
      <input value={query} onChange={e => setQuery(e.target.value)}
        placeholder={searchHint(showDirChips)}
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-2" />
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
        <span className="text-pb-faintest text-xs ml-auto">{visible.length} shown</span>
      </div>
      {showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <span className="text-pb-faintest text-[11px] uppercase tracking-wide2 mr-1">Directory</span>
          <DirectoryFilterChips modes={modes} onChange={setModes} />
          <span className="text-pb-faintest text-[10px] ml-1">tap once to exclude, twice to include</span>
        </div>
      )}
      {showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <span className="text-pb-faintest text-[11px] uppercase tracking-wide2 mr-1">Engagement</span>
          <EngagementFilterControls value={engagement} onChange={setEngagement} hasDirectory={showDirChips} />
        </div>
      )}

      {/* Selection action bar */}
      <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 pb-hairline-b">
        <button onClick={selectAllFiltered} disabled={!visible.length}
          className="px-2.5 py-1.5 rounded text-xs font-medium border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-40">
          Select all filtered ({visible.length})
        </button>
        {selected.size > 0 ? (
          <>
            <span className="text-pb-text text-xs font-medium">{selected.size} selected</span>
            <button onClick={() => doAdd(selCandidateIds)} disabled={busy || !selCandidateIds.length}
              className="px-2.5 py-1.5 rounded text-xs font-medium text-white disabled:opacity-40" style={{ background: 'var(--pb-accent)' }}>
              Add to list ({selCandidateIds.length})
            </button>
            <button onClick={() => doRemove(selMemberIds)} disabled={busy || !selMemberIds.length}
              className="px-2.5 py-1.5 rounded text-xs font-medium border pb-hairline text-pb-text hover:text-pb-red hover:border-pb-red disabled:opacity-40">
              Remove from list ({selMemberIds.length})
            </button>
            <CopyToLists lists={lists} currentId={list.id} onCopy={doCopy} />
            <button onClick={clearSelection} className="text-xs text-pb-faint hover:text-pb-text">Clear selection</button>
          </>
        ) : (
          <span className="text-pb-faintest text-xs">Tick contacts to add, remove or copy them in bulk.</span>
        )}
      </div>

      {note && <div className="text-pb-accent text-xs mb-3">{note}</div>}

      {/* IN THIS LIST */}
      <SectionHeader title="In this list" count={shownMembers.length}
        hasRows={shownMembers.length > 0} allChecked={allOf(shownMembers)}
        onToggleAll={() => setMany(shownMembers.map(c => c.id), !allOf(shownMembers))} />
      {memberIds == null || contacts == null ? (
        <div className="text-pb-faint text-sm mb-4">Loading…</div>
      ) : shownMembers.length === 0 ? (
        <div className="text-pb-faintest text-sm mb-4">{activeFilters ? 'No members match your search.' : 'No contacts in this list yet. Add some below.'}</div>
      ) : (
        <div className="mb-4 max-h-96 overflow-y-auto">
          {shownMembers.map((m, i) => (
            <ContactRow key={m.id} c={m} last={i === 0} onDetails={setDetailId}
              checked={isChecked(m.id)} onCheck={() => toggleOne(m.id)}
              action={<button onClick={() => doRemove([m.id])} disabled={busy} className="text-pb-faint hover:text-pb-red text-xs px-1 shrink-0 disabled:opacity-50">Remove</button>} />
          ))}
        </div>
      )}

      {/* NOT IN THIS LIST */}
      <SectionHeader title="Not in this list" count={candidates.length}
        hasRows={candidates.length > 0} allChecked={allOf(candidates)}
        onToggleAll={() => setMany(candidates.map(c => c.id), !allOf(candidates))} />
      {contacts == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : candidates.length === 0 ? (
        <div className="text-pb-faintest text-sm">{activeFilters ? 'No other contacts match.' : 'Every contact is already in this list.'}</div>
      ) : (
        <div className="max-h-96 overflow-y-auto">
          {candidates.map((c, i) => (
            <ContactRow key={c.id} c={c} last={i === 0} onDetails={setDetailId}
              checked={isChecked(c.id)} onCheck={() => toggleOne(c.id)}
              action={<button onClick={() => doAdd([c.id])} disabled={busy} className="px-2.5 py-1 rounded text-xs font-medium text-white disabled:opacity-50 shrink-0" style={{ background: 'var(--pb-accent)' }}>Add</button>} />
          ))}
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => loadContacts()} />}
    </div>
  )
}

function ListRow({ l, selected, onToggle, onDelete, onRenamed, first }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(l.name)
  const [err, setErr] = useState('')
  const save = async () => {
    const v = name.trim()
    if (!v || v === l.name) { setEditing(false); setName(l.name); return }
    try { await onRenamed(l, v); setEditing(false); setErr('') }
    catch (e) { setErr(e.message) }
  }
  return (
    <div className={`flex items-center justify-between gap-3 px-5 py-3 ${first ? '' : 'pb-hairline-t'}`}>
      {editing ? (
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <input autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setEditing(false); setName(l.name) } }}
              className="flex-1 px-2 py-1 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
            <button onClick={save} className="text-xs font-medium px-2 py-1 rounded text-white" style={{ background: 'var(--pb-accent)' }}>Save</button>
            <button onClick={() => { setEditing(false); setName(l.name) }} className="text-pb-faint text-xs hover:text-pb-text">Cancel</button>
          </div>
          {err && <div className="text-pb-red text-xs mt-1">{err}</div>}
        </div>
      ) : (
        <button onClick={() => onToggle(l)} className="text-left min-w-0 flex-1">
          <div className="text-pb-text text-sm truncate">{l.name}</div>
          <div className="text-pb-faintest text-xs mt-0.5">{l.count} contact{l.count === 1 ? '' : 's'}</div>
        </button>
      )}
      {!editing && (
        <div className="flex items-center gap-3 shrink-0">
          <button onClick={() => setEditing(true)} className="text-pb-faint text-xs hover:text-pb-text">Rename</button>
          <a href={api.commsListExportCsvUrl(l.id)} className="text-pb-faint text-xs hover:text-pb-text" title="Export this list to CSV">Export CSV</a>
          <button onClick={() => onToggle(l)} className="text-pb-faint text-xs hover:text-pb-text">{selected ? 'Close' : 'Manage'}</button>
          <button onClick={() => onDelete(l)} className="text-pb-faint text-xs hover:text-pb-red">Delete</button>
        </div>
      )}
    </div>
  )
}

export default function CommsLists() {
  const [lists, setLists] = useState(null)
  const [selected, setSelected] = useState(null)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.commsListLists().then(setLists).catch(e => { setError(e.message); setLists([]) })
  }, [])
  useEffect(() => { load() }, [load])

  const create = async () => {
    if (!newName.trim()) return
    setError('')
    try {
      const l = await api.commsCreateList(newName.trim())
      setNewName('')
      load()
      setSelected(l)
    } catch (e) { setError(e.message) }
  }

  const del = async (l) => {
    if (!window.confirm(`Delete the list "${l.name}"? The contacts themselves are not deleted.`)) return
    await api.commsDeleteList(l.id)
    if (selected?.id === l.id) setSelected(null)
    load()
  }

  const rename = async (l, name) => {
    const updated = await api.commsRenameList(l.id, name)
    if (selected?.id === l.id) setSelected(s => ({ ...s, name: updated.name }))
    load()
  }

  const toggle = (l) => setSelected(selected?.id === l.id ? null : l)

  return (
    <BetterCommsLayout title="Lists">
      {error && <div className="pb-card p-3 mb-4 text-pb-red text-sm">{error}</div>}
      <div className="text-pb-faintest text-sm mb-4 max-w-2xl">
        A list is a fixed set of contacts you pick by hand (committee, sponsors, a team), the counterpart to a
        segment. Use a list when the membership won't change on its own.
      </div>

      <div className="pb-card p-3 mb-4 flex items-center gap-2 max-w-xl">
        <input value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === 'Enter' && create()}
          placeholder="New list name (e.g. Committee)"
          className="flex-1 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
        <button onClick={create} className="px-3 py-2 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
          Create
        </button>
      </div>

      {lists == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : lists.length === 0 ? (
        <div className="text-pb-faintest text-sm">No lists yet.</div>
      ) : (
        <div className="pb-card overflow-hidden mb-4">
          {lists.map((l, i) => (
            <ListRow key={l.id} l={l} first={i === 0} selected={selected?.id === l.id}
              onToggle={toggle} onDelete={del} onRenamed={rename} />
          ))}
        </div>
      )}

      {selected && <ListDetail list={selected} lists={lists || []} onChanged={load} />}
    </BetterCommsLayout>
  )
}
