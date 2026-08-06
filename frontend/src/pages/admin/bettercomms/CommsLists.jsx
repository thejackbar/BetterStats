import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Badge, Caption, SectionHeading, Note, Empty, INPUT_CLS } from '../../../components/admin/ui'
import { ContactDetailModal } from './CommsContacts'
import { FACETS, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect, matchesSuppressed, SuppressedToggle,
  emptyModes, matchesModes, anyMode, DirectoryFilterChips, searchHint,
  emptyEngagementFilter, matchesEngagementScore, topClubIds, matchesTopClubs, EngagementFilterControls,
  matchesUnsubscribed, UnsubscribedToggle, unsubscribedTitle } from './audience'

// Start an email already addressed to a list.
//
// The same move Audiences makes with "Email these N": create the draft with the
// audience already set and open it, rather than sending the officer to the
// Emails list to pick again the list they were just looking at. `saved_list` is
// the audience type the composer's own dropdown writes for a list, so the draft
// opens with it already chosen and counted.
export function useEmailList() {
  const navigate = useNavigate()
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const emailList = useCallback(async (list) => {
    if (!list?.id) return
    setBusyId(list.id); setError('')
    try {
      const c = await api.commsCreateCampaign({
        subject: '', body_html: '',
        audience: { type: 'saved_list', list_id: list.id },
      })
      navigate(`/admin/comms/${c.id}`)
    } catch (e) { setError(e.message); setBusyId(null) }
  }, [navigate])
  return { emailList, busyId, error }
}

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
      <Button size="sm" onClick={() => setOpen(o => !o)}>Copy to lists ▾</Button>
      {open && (
        <div className="absolute z-30 mt-1 right-0 w-64 max-h-80 overflow-auto rounded-lg border border-pb-hairline2 bg-pb-surface2 shadow-lg p-2">
          {targets.length === 0 ? (
            <div className="text-xs text-pb-faint px-1 py-2">No other lists. Create one first.</div>
          ) : (
            <>
              <Caption className="px-1 mb-1">Copy selected into</Caption>
              {targets.map(l => (
                <label key={l.id} className="flex items-center gap-2 px-1 py-1 text-xs text-pb-text hover:bg-pb-surface rounded cursor-pointer">
                  <input type="checkbox" className="accent-pb-accent" checked={picked.includes(l.id)} onChange={() => toggle(l.id)} />
                  <span className="truncate flex-1" title={l.name}>{l.name}</span>
                  <span className="text-pb-faintest">{l.count}</span>
                </label>
              ))}
              <Button size="sm" variant="primary" onClick={go} disabled={!picked.length} className="mt-2 w-full">
                Copy to {picked.length || ''} list{picked.length === 1 ? '' : 's'}
              </Button>
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

// Prominent section header that reads in both light and dark themes.
function SectionHeader({ title, count, allChecked, onToggleAll, hasRows }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-pb-surface2 border border-pb-hairline mb-2">
      <div className="flex items-center gap-2.5 min-w-0">
        {hasRows && (
          <input type="checkbox" className="accent-pb-accent shrink-0" checked={allChecked} onChange={onToggleAll}
            title="Select all shown in this section" />
        )}
        <span className="font-display text-pb-text text-[13.5px] font-semibold truncate">
          {title} <span className="text-pb-faint font-normal">({count})</span>
        </span>
      </div>
    </div>
  )
}

function ListDetail({ list, lists, onChanged, onEmail, emailing }) {
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
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <SectionHeading>{list.name}</SectionHeading>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" variant="primary" onClick={() => onEmail?.(list)}
            disabled={!shownMembers.length && !list.count || !!emailing}
            title={list.count ? '' : 'This list has nobody in it yet'}>
            {emailing === list.id ? 'Opening…' : `Email these ${list.count ?? 0}`}
          </Button>
          <Button size="sm" as="a" href={api.commsListExportCsvUrl(list.id)} title="Export this list to CSV">Export CSV</Button>
        </div>
      </div>

      {/* Search + filters */}
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
        <span className="text-pb-faintest text-xs ml-auto">{visible.length} shown</span>
      </div>
      {showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <Caption className="mr-1">Directory</Caption>
          <DirectoryFilterChips modes={modes} onChange={setModes} />
          <span className="text-pb-faintest text-[10px] ml-1">tap once to exclude, twice to include</span>
        </div>
      )}
      {showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <Caption className="mr-1">Engagement</Caption>
          <EngagementFilterControls value={engagement} onChange={setEngagement} hasDirectory={showDirChips} />
        </div>
      )}

      {/* Selection action bar */}
      <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 pb-hairline-b">
        <Button size="sm" onClick={selectAllFiltered} disabled={!visible.length}>
          Select all filtered ({visible.length})
        </Button>
        {selected.size > 0 ? (
          <>
            <span className="text-pb-text text-[12.5px] font-semibold">{selected.size} selected</span>
            <Button size="sm" variant="primary" onClick={() => doAdd(selCandidateIds)} disabled={busy || !selCandidateIds.length}>
              Add to list ({selCandidateIds.length})
            </Button>
            <Button size="sm" variant="danger" onClick={() => doRemove(selMemberIds)} disabled={busy || !selMemberIds.length}>
              Remove from list ({selMemberIds.length})
            </Button>
            <CopyToLists lists={lists} currentId={list.id} onCopy={doCopy} />
            <Button size="sm" variant="quiet" onClick={clearSelection}>Clear selection</Button>
          </>
        ) : (
          <span className="text-pb-faintest text-[12.5px]">Tick contacts to add, remove or copy them in bulk.</span>
        )}
      </div>

      {note && <Note className="mb-3">{note}</Note>}

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
              action={<Button size="sm" variant="danger" onClick={() => doRemove([m.id])} disabled={busy}>Remove</Button>} />
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
              action={<Button size="sm" variant="primary" onClick={() => doAdd([c.id])} disabled={busy}>Add</Button>} />
          ))}
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => loadContacts()} />}
    </div>
  )
}

function ListRow({ l, selected, onToggle, onDelete, onRenamed, onEmail, emailing, first }) {
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
              className={INPUT_CLS} />
            <Button size="sm" variant="primary" onClick={save}>Save</Button>
            <Button size="sm" variant="quiet" onClick={() => { setEditing(false); setName(l.name) }}>Cancel</Button>
          </div>
          {err && <div className="text-pb-red text-[12px] mt-1">{err}</div>}
        </div>
      ) : (
        <button onClick={() => onToggle(l)} className="text-left min-w-0 flex-1">
          <div className="text-pb-text text-[13.5px] font-semibold truncate">{l.name}</div>
          <div className="font-mono text-[9.5px] uppercase text-pb-faint mt-0.5">{l.count} contact{l.count === 1 ? '' : 's'}</div>
        </button>
      )}
      {!editing && (
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <Button size="sm" variant="primary" onClick={() => onEmail(l)} disabled={!l.count || !!emailing}
            title={l.count ? '' : 'This list has nobody in it yet'}>
            {emailing === l.id ? 'Opening…' : `Email these ${l.count}`}
          </Button>
          <Button size="sm" variant="quiet" onClick={() => setEditing(true)}>Rename</Button>
          <Button size="sm" variant="quiet" as="a" href={api.commsListExportCsvUrl(l.id)} title="Export this list to CSV">Export CSV</Button>
          <Button size="sm" variant="quiet" onClick={() => onToggle(l)}>{selected ? 'Close' : 'Manage'}</Button>
          <Button size="sm" variant="danger" onClick={() => onDelete(l)}>Delete</Button>
        </div>
      )}
    </div>
  )
}

// One card of list rows. Extracted so the manually-created and auto-generated
// sections render identically.
function ListsCard({ rows, selected, onToggle, onDelete, onRenamed, onEmail, emailing }) {
  return (
    <div className="pb-card overflow-hidden mb-4">
      {rows.map((l, i) => (
        <ListRow key={l.id} l={l} first={i === 0} selected={selected?.id === l.id}
          onToggle={onToggle} onDelete={onDelete} onRenamed={onRenamed}
          onEmail={onEmail} emailing={emailing} />
      ))}
    </div>
  )
}

export default function CommsLists() {
  const { user } = useAuth()
  const { emailList, busyId: emailing, error: emailError } = useEmailList()
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

  const manualLists = useMemo(() => (lists || []).filter(l => l.source !== 'auto'), [lists])
  const autoLists = useMemo(() => (lists || []).filter(l => l.source === 'auto'), [lists])
  // Split into two labelled sections for super admins, or whenever an
  // auto-generated list exists (an ordinary club admin only ever has manual
  // lists, so their page keeps the single flat list it always had).
  const showSections = !!user?.can_switch_clubs || autoLists.length > 0

  const cardProps = { selected, onToggle: toggle, onDelete: del, onRenamed: rename, onEmail: emailList, emailing }

  return (
    <BetterCommsLayout
      title="Lists"
      caption={`Picked by hand · ${lists?.length ?? 0} saved`}
    >
      {(error || emailError) && (
        <Note toneKey="block" className="mb-4 max-w-2xl">{error || emailError}</Note>
      )}
      <p className="text-[13px] text-pb-dim mb-4 max-w-2xl leading-relaxed">
        A list is a fixed set of contacts you pick by hand — the committee, sponsors, one team — and the counterpart
        to an audience. Use a list when the membership won't change on its own.
      </p>

      <div className="pb-card p-3 mb-4 flex items-center gap-2 max-w-xl">
        <input value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === 'Enter' && create()}
          placeholder="New list name (e.g. Committee)"
          className={INPUT_CLS} />
        <Button variant="primary" onClick={create} disabled={!newName.trim()}>Create</Button>
      </div>

      {lists == null ? (
        <Empty>Loading…</Empty>
      ) : lists.length === 0 ? (
        <Empty>No lists yet.</Empty>
      ) : !showSections ? (
        <ListsCard rows={manualLists} {...cardProps} />
      ) : (
        <>
          <SectionHeading className="mb-2">Your lists</SectionHeading>
          {manualLists.length === 0 ? (
            <p className="text-[13px] text-pb-faint mb-4">No lists you've created by hand yet.</p>
          ) : (
            <ListsCard rows={manualLists} {...cardProps} />
          )}

          <SectionHeading className="mt-6 mb-1">Auto-generated lists</SectionHeading>
          <p className="text-[12.5px] text-pb-faint mb-2 max-w-2xl leading-relaxed">
            Lists built for you by other BetterCricket tools. Rename, manage, email or delete them like any other list.
          </p>
          {autoLists.length === 0 ? (
            <p className="text-[13px] text-pb-faint mb-4">Nothing here yet.</p>
          ) : (
            <ListsCard rows={autoLists} {...cardProps} />
          )}
        </>
      )}

      {selected && (
        <ListDetail list={lists?.find(l => l.id === selected.id) || selected} lists={lists || []}
          onChanged={load} onEmail={emailList} emailing={emailing} />
      )}
    </BetterCommsLayout>
  )
}
