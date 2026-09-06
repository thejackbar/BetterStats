import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Badge, Caption, SectionHeading, Note, Empty, Toast, INPUT_CLS, SearchInput } from '../../../components/admin/ui'
import { CrudPanes, RecordListPane, DetailPane, RecordTitleRow, CountBar, SaveRow, reachability, clubCount } from '../clubhouse/crudShell'
import ScreenIntro, { useScreenIntro, INTROS } from '../clubhouse/intro'
import { ContactDetailModal } from './CommsContacts'
import { FACETS, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect, matchesSuppressed, SuppressedToggle,
  emptyModes, matchesModes, anyMode, DirectoryFilterChips, searchHint,
  emptyEngagementFilter, matchesEngagementScore, topClubIds, matchesTopClubs, EngagementFilterControls,
  matchesUnsubscribed, UnsubscribedToggle, unsubscribedTitle } from './audience'

// Lists — a set of people picked by hand, and it stays as picked.
//
// The other half of the audience vocabulary: a segment is a rule resolved at
// send time, a list is a roll call. Both are things an email can be addressed
// to, and both are now CRUDed the same way — the saved ones in a rail on the
// left, the one you are working on beside it, its name edited where it is read,
// its reach counted live, and Save and Delete in the same place as everywhere
// else in the module. See clubhouse/crudShell.jsx.
//
// What that replaced: a create box at the top of the page, a stack of cards
// each carrying five buttons and an inline rename with its own Save/Cancel, and
// a separate editor card that appeared underneath the whole stack once you
// pressed Manage. Nothing has been dropped — rename is the name field, Manage
// is simply what the right pane always shows, and Export CSV and "Email these N
// now" moved to the record's own actions.

const noFilters = () => ({ club: [], association: [], country: [], utm_code: [], state: [] })

// Start an email already addressed to a list.
//
// The same move Segments makes with "Email these N now": create the draft with
// the audience already set and open it, rather than sending the officer to the
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
      navigate(`/admin/comms/${c.id}`, { state: { skipIntro: true } })
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

// Who is in this list, and everything you can do about it.
//
// Unchanged in substance from the old "Manage" card: the same search, the same
// directory and engagement filters, the same bulk add / remove / copy, the same
// per-row actions and contact detail modal. It reports its members up
// (`onMembers`) so the count bar above it can say how many of them are actually
// reachable by email — the same readout a segment gives.
function ListMembership({ list, lists, onChanged, onMembers }) {
  const [memberRows, setMemberRows] = useState(null)
  const [contacts, setContacts] = useState(null)
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(noFilters)
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
      .then(rows => setMemberRows(rows || []))
      .catch(() => setMemberRows([]))
  }, [list.id])
  const loadContacts = useCallback(() => {
    api.commsListContacts({}).then(r => setContacts(r.contacts || [])).catch(() => setContacts([]))
  }, [])
  useEffect(() => { loadMembers() }, [loadMembers])
  useEffect(() => { loadContacts() }, [loadContacts])
  // A fresh list resets the working selection.
  useEffect(() => { setSelected(new Set()); setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()); setNote('') }, [list.id])
  useEffect(() => { onMembers?.(memberRows) }, [memberRows])   // eslint-disable-line react-hooks/exhaustive-deps

  const memberIds = useMemo(() => (memberRows == null ? null : new Set(memberRows.map(r => r.id))), [memberRows])
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
  const clearAll = () => { setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()) }
  const activeFilters = FACETS.some(f => filters[f.key].length) || anyMode(modes) || !!q || supp !== 'all' || unsub !== 'all'
    || engagement.gte || engagement.lte || engagement.topN

  return (
    <div>
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

export default function CommsLists() {
  const { user } = useAuth()
  const intro = useScreenIntro('lists')
  const { emailList, busyId: emailing, error: emailError } = useEmailList()
  const [lists, setLists] = useState(null)
  const [selId, setSelId] = useState(null)
  const [listQ, setListQ] = useState('')            // the header search, over the rail
  const [draft, setDraft] = useState(null)          // { id, name }
  const [members, setMembers] = useState(null)      // the selected list's contacts
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)

  const load = useCallback(async () => {
    try {
      const rows = await api.commsListLists()
      setLists(rows)
      setSelId(cur => cur || rows[0]?.id || null)
      return rows
    } catch (e) { setError(e.message); setLists([]); return [] }
  }, [])
  useEffect(() => { load() }, [load])

  const selected = useMemo(() => (lists || []).find(l => l.id === selId) || null, [lists, selId])

  // Editing works on a draft, so a half-typed name never reaches the server.
  // Like the segment builder this only ever LOADS a draft and never clears one:
  // clearing on "nothing selected" is exactly the state "New list" puts the
  // screen in, and would wipe the fresh draft in the same commit.
  useEffect(() => {
    if (!selected) return
    setDraft({ id: selected.id, name: selected.name })
    setMembers(null)
  }, [selected?.id])   // eslint-disable-line react-hooks/exhaustive-deps

  const startNew = () => { setSelId(null); setDraft({ id: null, name: '' }); setMembers(null); setError('') }

  const save = async () => {
    const name = (draft?.name || '').trim()
    if (!name) { setError('Give the list a name.'); return }
    setBusy(true); setError('')
    try {
      const saved = draft.id
        ? await api.commsRenameList(draft.id, name)
        : await api.commsCreateList(name)
      setToast({
        title: draft.id ? 'List saved' : 'List created',
        body: draft.id ? `Renamed to ${name}.` : `${name} is ready — pick who belongs in it below.`,
      })
      await load()
      setSelId(saved.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!draft?.id) return
    if (!window.confirm(`Delete the list "${draft.name}"? The contacts themselves are not deleted.`)) return
    setBusy(true); setError('')
    try {
      await api.commsDeleteList(draft.id)
      setSelId(null); setDraft(null); setMembers(null)
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const manualLists = useMemo(() => (lists || []).filter(l => l.source !== 'auto'), [lists])
  const autoLists = useMemo(() => (lists || []).filter(l => l.source === 'auto'), [lists])
  // Two labelled sections for super admins, or whenever an auto-generated list
  // exists (an ordinary club admin only ever has manual lists, so their rail
  // keeps the single flat list it always had).
  const showSections = !!user?.can_switch_clubs || autoLists.length > 0

  const rowFor = (l) => ({
    id: l.id,
    name: l.name,
    sub: l.source === 'auto' ? `Auto-generated${l.origin ? ` · ${l.origin}` : ''}` : 'Picked by hand',
    figure: l.count,
  })
  const groups = showSections ? [
    { key: 'manual', heading: 'Your lists', items: manualLists.map(rowFor), emptyText: "No lists you've created by hand yet." },
    { key: 'auto', heading: 'Auto-generated lists', items: autoLists.map(rowFor), emptyText: 'Nothing here yet.' },
  ] : null

  const count = selected?.count ?? 0
  const reachable = members == null ? 0 : members.filter(c => reachability(c).key === 'email').length
  const otherRoute = members == null ? 0 : members.filter(c => reachability(c).key === 'guardian').length
  // Computed from the membership rows, which this endpoint returns in full (no
  // cap), so it needs no server figure the way a segment's does.
  const clubs = members == null ? 0 : clubCount(members)

  if (intro.showing) {
    return (
      <BetterCommsLayout title="Lists" actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.lists} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterCommsLayout>
    )
  }

  return (
    <BetterCommsLayout
      title="Lists"
      caption={`Picked by hand · ${lists?.length ?? 0} saved`}
      onHelp={intro.reopen}
      twoRow
      filters={<SearchInput wide value={listQ} onChange={setListQ} placeholder="Search lists…" />}
      actions={<Button variant="primary" onClick={startNew}>New list</Button>}
      bare
    >
      <CrudPanes>
        <RecordListPane
          items={showSections ? undefined : manualLists.map(rowFor)}
          groups={groups}
          loading={lists == null} selId={selId} onSelect={setSelId} query={listQ}
          emptyText="No lists yet. Start one and pick who belongs in it."
        >
          <Note toneKey="calm">
            A list is people picked by hand. For a group better described by a rule, use a{' '}
            <Link to="/admin/comms/segments" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>segment</Link>
            {' '}— both can be chosen as the audience when you write an email:{' '}
            <Link to="/admin/comms/contacts" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Contacts</Link>
          </Note>
          {showSections && (
            <Note title="Auto-generated lists" toneKey="calm">
              Lists built for you by other BetterCricket tools. Rename, manage, email or delete them like any
              other list.
            </Note>
          )}
        </RecordListPane>

        <DetailPane>
          {/* A record's own error sits beside Save, the way it does on a
              segment. This is for the two that cannot: the lists themselves
              failing to load, and a failure while opening an email addressed
              to one. */}
          {(emailError || (!draft && error)) && (
            <Note toneKey="block" className="mb-4">{emailError || error}</Note>
          )}

          {!draft ? (
            <Empty>Pick a list, or start a new one.</Empty>
          ) : (
            <>
              <RecordTitleRow
                name={draft.name} onName={v => setDraft(d => ({ ...d, name: v }))}
                onSubmit={save}
                placeholder="Name this list"
                blurb="A fixed set of contacts you pick by hand. It stays exactly as picked until you change it."
                actions={<>
                  {draft.id && (
                    <Button size="sm" as="a" href={api.commsListExportCsvUrl(draft.id)}
                      title="Download this list's contacts">Export CSV</Button>
                  )}
                  <Button size="sm" variant="primary" onClick={() => emailList(selected)}
                    disabled={!draft.id || !count || !!emailing}
                    title={!draft.id ? 'Save the list first' : count ? '' : 'This list has nobody in it yet'}>
                    {emailing === draft.id ? 'Opening…' : `Email these ${count} now`}
                  </Button>
                </>}
              />

              {/* The same live readout a segment gives, phrased for a roll
                  call rather than a rule: this many are in it, this many of
                  them can actually be reached. */}
              {draft.id && (
                <CountBar>
                  {members == null ? <span className="text-pb-dim">Counting who is in this list…</span> : (
                    <span className="text-pb-dim">
                      <b style={{ color: 'var(--pb-accent-ink)' }}>{count}</b>
                      {count === 1 ? ' contact in this list' : ' contacts in this list'}
                      {' · '}<b style={{ color: 'var(--pb-positive-ink)' }}>{reachable}</b> reachable by email
                      {otherRoute > 0 && <> · <b style={{ color: '#f5b542' }}>{otherRoute}</b> need another route</>}
                      {clubs > 0 && <> · <b style={{ color: 'var(--pb-accent-ink)' }}>{clubs}</b> {clubs === 1 ? 'club' : 'clubs'}</>}
                    </span>
                  )}
                </CountBar>
              )}

              <SaveRow
                onSave={save} busy={busy} error={error}
                saveLabel={busy ? 'Saving…' : draft.id ? 'Save changes' : 'Create list'}
                onDelete={draft.id ? remove : null}
              />

              <SectionHeading className="mt-8 mb-2.5">Who this is, right now</SectionHeading>
              {!draft.id ? (
                <Note toneKey="calm">
                  Give the list a name and create it, then pick who belongs in it here.
                </Note>
              ) : (
                <ListMembership
                  key={draft.id} list={selected || draft} lists={lists || []}
                  onChanged={load} onMembers={setMembers}
                />
              )}
            </>
          )}
        </DetailPane>
      </CrudPanes>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </BetterCommsLayout>
  )
}
