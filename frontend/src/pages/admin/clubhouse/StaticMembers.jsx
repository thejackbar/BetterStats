import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { Button, Badge, Caption, INPUT_CLS, Note } from '../../../components/admin/ui'
import { ContactDetailModal } from '../bettercomms/CommsContacts'
import {
  FACETS, emptyFilters, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect,
  matchesSuppressed, SuppressedToggle, emptyModes, matchesModes, anyMode,
  DirectoryFilterChips, searchHint, emptyEngagementFilter, matchesEngagementScore,
  topClubIds, matchesTopClubs, EngagementFilterControls,
  matchesUnsubscribed, UnsubscribedToggle, unsubscribedTitle,
} from '../bettercomms/audience'

// The STATIC section of a segment: a frozen, hand-picked set of contacts, the
// former "Lists" mechanic moved inside the segment editor. Filter/search to find
// people, tick specific ones, and they stay exactly as picked (they do not
// re-evaluate — that is what the Active rules are for).
//
// A faithful port of the old ListMembership: the same search, the same
// directory/engagement filters (data-driven, so a club sees search + role and
// an outreach org sees the richer facets), the same bulk add / remove and
// per-row actions. Retargeted from the list-member endpoints to the segment
// ones; members persist immediately, and it reports up (`onChanged`) so the
// count bar and the rail can refresh.

const noFilters = emptyFilters

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

export default function StaticMembers({ segmentId, onChanged, onMembers }) {
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
  useEffect(() => { setSelected(new Set()); setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()); setNote('') }, [segmentId])
  useEffect(() => { onMembers?.(memberRows) }, [memberRows])   // eslint-disable-line react-hooks/exhaustive-deps

  const memberIds = useMemo(() => (memberRows == null ? null : new Set(memberRows.map(r => r.id))), [memberRows])
  const facetOptions = useMemo(() => facetOptionsFrom(contacts), [contacts])
  const showDirChips = useMemo(() => (contacts || []).some(c => c.club), [contacts])

  const q = query.trim().toLowerCase()
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

  const refreshAll = () => { loadMembers(); onChanged?.() }

  const doAdd = async (ids) => {
    if (!ids.length) return
    setBusy(true)
    try { await api.commsAddSegmentMembers(segmentId, ids); setMany(ids, false); refreshAll(); setNote(`Added ${ids.length} to the static set.`) }
    finally { setBusy(false) }
  }
  const doRemove = async (ids) => {
    if (!ids.length) return
    setBusy(true)
    try { await api.commsRemoveSegmentMembers(segmentId, ids); setMany(ids, false); refreshAll(); setNote(`Removed ${ids.length} from the static set.`) }
    finally { setBusy(false) }
  }

  const selectAllFiltered = () => setMany(visible.map(c => c.id), true)
  const clearSelection = () => setSelected(new Set())
  const clearAll = () => { setQuery(''); setFilters(noFilters()); setModes(emptyModes()); setSupp('all'); setUnsub('all'); setEngagement(emptyEngagementFilter()) }
  const activeFilters = FACETS.some(f => filters[f.key].length) || anyMode(modes) || !!q || supp !== 'all' || unsub !== 'all'
    || engagement.gte || engagement.lte || engagement.topN

  return (
    <div>
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

      <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 pb-hairline-b">
        <Button size="sm" onClick={selectAllFiltered} disabled={!visible.length}>
          Select all filtered ({visible.length})
        </Button>
        {selected.size > 0 ? (
          <>
            <span className="text-pb-text text-[12.5px] font-semibold">{selected.size} selected</span>
            <Button size="sm" variant="primary" onClick={() => doAdd(selCandidateIds)} disabled={busy || !selCandidateIds.length}>
              Add ({selCandidateIds.length})
            </Button>
            <Button size="sm" variant="danger" onClick={() => doRemove(selMemberIds)} disabled={busy || !selMemberIds.length}>
              Remove ({selMemberIds.length})
            </Button>
            <Button size="sm" variant="quiet" onClick={clearSelection}>Clear selection</Button>
          </>
        ) : (
          <span className="text-pb-faintest text-[12.5px]">Tick contacts to add or remove them in bulk.</span>
        )}
      </div>

      {note && <Note className="mb-3">{note}</Note>}

      <SectionHeader title="In the static set" count={shownMembers.length}
        hasRows={shownMembers.length > 0} allChecked={allOf(shownMembers)}
        onToggleAll={() => setMany(shownMembers.map(c => c.id), !allOf(shownMembers))} />
      {memberIds == null || contacts == null ? (
        <div className="text-pb-faint text-sm mb-4">Loading…</div>
      ) : shownMembers.length === 0 ? (
        <div className="text-pb-faintest text-sm mb-4">{activeFilters ? 'No hand-picked contacts match your search.' : 'No contacts picked yet. Add some below.'}</div>
      ) : (
        <div className="mb-4 max-h-96 overflow-y-auto">
          {shownMembers.map((m, i) => (
            <ContactRow key={m.id} c={m} last={i === 0} onDetails={setDetailId}
              checked={isChecked(m.id)} onCheck={() => toggleOne(m.id)}
              action={<Button size="sm" variant="danger" onClick={() => doRemove([m.id])} disabled={busy}>Remove</Button>} />
          ))}
        </div>
      )}

      <SectionHeader title="Not picked" count={candidates.length}
        hasRows={candidates.length > 0} allChecked={allOf(candidates)}
        onToggleAll={() => setMany(candidates.map(c => c.id), !allOf(candidates))} />
      {contacts == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : candidates.length === 0 ? (
        <div className="text-pb-faintest text-sm">{activeFilters ? 'No other contacts match.' : 'Every contact is already picked.'}</div>
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
