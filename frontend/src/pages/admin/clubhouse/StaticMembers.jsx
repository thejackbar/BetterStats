import { useState, useEffect, useCallback, useMemo, createContext, useContext } from 'react'
import { api } from '../../../lib/api'
import { Button, Badge, Caption, INPUT_CLS, Note, SectionHeading } from '../../../components/admin/ui'
import { ContactDetailModal } from '../bettercomms/CommsContacts'
import {
  FACETS, emptyFilters, matchesQuery, matchesFilters, facetOptionsFrom, MultiSelect,
  emptyModes, matchesModes, anyMode,
  DirectoryFilterChips, searchHint, unsubscribedTitle,
} from '../bettercomms/audience'

// Who is in this segment, split across three placement zones so each part sits
// where it belongs in the segment-definition screen:
//
//   * SegmentTiles        — the two count tiles ("in" / "not in"), at the TOP of
//                           the detail pane, above the Active rules. Each tile
//                           toggles show/hide of its own contact LIST — nothing
//                           else. The counts are the WHOLE audience (rules ∪
//                           static set ∪ included segments − excluded), so they
//                           move the moment any criterion changes.
//   * StaticPicker        — the hand-pick SELECTION CRITERIA (search + facet
//                           filters), inside the Static members section. ALWAYS
//                           on display; the tiles never hide it.
//   * SegmentContactLists — the two contact lists themselves, at the BOTTOM of
//                           the pane, below the Include/exclude section. Each is
//                           shown only when its tile is toggled on, and the two
//                           toggle independently. The lists are narrowed by the
//                           criteria above and carry the per-contact / bulk
//                           Add / Remove a static set needs.
//
// One StaticMembersProvider holds the shared state so the three pieces, far
// apart in the tree, stay in step. Engagement score / top-N / page-view controls
// used to browse here; they are ACTIVE properties and live in the Active rules
// section now (as fields), never here.

const noFilters = emptyFilters

const Ctx = createContext(null)
const useSM = () => useContext(Ctx)

function Tile({ label, n, sub, active, tone, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex-1 min-w-[150px] text-left rounded-xl px-4 py-3 border transition
        ${active ? 'border-pb-accent bg-pb-surface2' : 'border-pb-hairline hover:bg-pb-surface2'}`}>
      <div className="text-2xl font-bold tabular-nums"
        style={tone === 'ok' ? { color: 'var(--pb-positive-ink)' } : undefined}>
        {n == null ? '—' : n.toLocaleString()}
      </div>
      <div className="text-pb-dim text-[12.5px] mt-0.5">{label}</div>
      <div className="text-pb-faintest text-[10.5px] mt-0.5">{active ? 'Showing the list below — tap to hide' : sub}</div>
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

// A contact this browser reckons an email could actually reach. It is the
// EXACT mirror of the server's `sendable_where` (subscribed IS TRUE, and not
// bounced / complained / excluded / globally suppressed — `_contact_out` folds
// the last four into `suppressed`), so the "not in this segment" list drawn
// here equals the server's `out_count` rather than including the ~handful of
// suppressed contacts the count leaves out.
const isSendable = (c) => c.subscribed === true && !c.suppressed

export function StaticMembersProvider({
  children, segmentId, memberIds, inCount, outCount, reachable, otherRoute, clubs, onChanged,
}) {
  const [memberRows, setMemberRows] = useState(segmentId ? null : [])
  const [contacts, setContacts] = useState(null)
  // Which lists are visible. The two toggle INDEPENDENTLY — showing "not in"
  // does not hide "in" — so a person can compare the two.
  const [show, setShow] = useState({ in: false, out: false })
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(noFilters)
  const [modes, setModes] = useState(emptyModes)
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
  // A fresh segment resets the working selection, filters and open lists.
  useEffect(() => {
    setSelected(new Set()); setQuery(''); setFilters(noFilters()); setModes(emptyModes())
    setNote(''); setShow({ in: false, out: false })
  }, [segmentId])

  // The hand-picked (frozen) member ids — what the Remove button acts on.
  const staticIds = useMemo(() => new Set((memberRows || []).map(r => r.id)), [memberRows])
  // The WHOLE in-segment audience (rules ∪ static ∪ included − excluded),
  // resolved server-side and passed in whole (ids only). Deriving it from the
  // capped `contacts` PREVIEW instead is what made the lists disagree with the
  // count tiles — a contact past the 5000-row cap read as "not in" though the
  // count said it was in.
  const inIds = useMemo(() => new Set(memberIds || []), [memberIds])
  const facetOptions = useMemo(() => facetOptionsFrom(contacts), [contacts])
  const showDirChips = useMemo(() => (contacts || []).some(c => c.club), [contacts])

  const q = query.trim().toLowerCase()
  const passes = useCallback((c) =>
    matchesQuery(c, q) && matchesFilters(c, filters) && matchesModes(c, modes),
    [q, filters, modes])

  // Both lists partition the club's OWN complete contact list by the resolved
  // membership, so the totals agree with the tiles above. The OUT list is
  // sendable-gated so its length equals the server's `out_count` (a suppressed
  // contact is never counted in, and adding one is a no-op, so it belongs in
  // neither list).
  const inList = useMemo(() =>
    (contacts || []).filter(c => inIds.has(c.id) && passes(c)),
    [contacts, inIds, passes])
  const outList = useMemo(() =>
    (contacts || []).filter(c => !inIds.has(c.id) && isSendable(c) && passes(c)),
    [contacts, inIds, passes])

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
  const clearSelection = () => setSelected(new Set())

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

  const clearAll = () => { setQuery(''); setFilters(noFilters()); setModes(emptyModes()) }
  const activeFilters = FACETS.some(f => filters[f.key].length) || anyMode(modes) || !!q
  const toggleTile = (which) => setShow(s => ({ ...s, [which]: !s[which] }))

  const value = {
    segmentId, inCount, outCount, reachable, otherRoute, clubs,
    show, toggleTile,
    query, setQuery, filters, setFilters, modes, setModes,
    facetOptions, showDirChips, activeFilters, clearAll,
    memberRows, contacts, staticIds, inIds, inList, outList,
    selected, isChecked, toggleOne, setMany, clearSelection,
    doAdd, doRemove, busy, note, setDetailId,
  }
  return (
    <Ctx.Provider value={value}>
      {children}
      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => loadContacts()} />}
    </Ctx.Provider>
  )
}

// ── Zone 1: the two count tiles (top of the pane, above Active rules) ─────────
export function SegmentTiles() {
  const sm = useSM()
  return (
    <div>
      <div className="flex flex-wrap gap-3">
        <Tile label="In this segment" n={sm.inCount} tone="ok" active={sm.show.in}
          sub="Rules, hand-picked and included — tap to view the list" onClick={() => sm.toggleTile('in')} />
        <Tile label="Not in this segment" n={sm.outCount} active={sm.show.out}
          sub="Everyone else you could add — tap to view the list" onClick={() => sm.toggleTile('out')} />
      </div>
      {sm.inCount > 0 && (sm.reachable != null) && (
        <div className="text-pb-faintest text-[11.5px] mt-2">
          <b style={{ color: 'var(--pb-positive-ink)' }}>{sm.reachable.toLocaleString()}</b> reachable by email
          {sm.otherRoute > 0 && <> · <b style={{ color: '#f5b542' }}>{sm.otherRoute.toLocaleString()}</b> need another route</>}
          {sm.clubs > 0 && <> · <b style={{ color: 'var(--pb-accent-ink)' }}>{sm.clubs.toLocaleString()}</b> {sm.clubs === 1 ? 'club' : 'clubs'}</>}
        </div>
      )}
    </div>
  )
}

// ── Zone 2: the hand-pick selection criteria (inside the Static section) ──────
// Always on display. These filters narrow the two contact lists at the bottom;
// they never hide, whatever the tiles are toggled to.
export function StaticPicker() {
  const sm = useSM()
  return (
    <div>
      {!sm.segmentId ? (
        <Note toneKey="calm" className="mb-3">
          Save the segment to hand-pick specific contacts. The tiles at the top already count who the rules match.
        </Note>
      ) : (
        <p className="text-pb-faint text-[12.5px] mb-3">
          Filter who you are hand-picking. Toggle the tiles at the top to view the matching contacts below,
          then Add or Remove them.
        </p>
      )}
      <input value={sm.query} onChange={e => sm.setQuery(e.target.value)}
        placeholder={searchHint(sm.showDirChips)}
        className={`${INPUT_CLS} mb-2`} />
      <div className="flex flex-wrap items-center gap-2">
        {FACETS.filter(f => sm.facetOptions[f.key].length > 0).map(f => (
          <MultiSelect key={f.key} label={f.label} options={sm.facetOptions[f.key]}
            selected={sm.filters[f.key]} onChange={(v) => sm.setFilters(s => ({ ...s, [f.key]: v }))} />
        ))}
        {sm.activeFilters && (
          <button onClick={sm.clearAll}
            className="text-xs text-pb-faint hover:text-pb-accent underline underline-offset-2">Clear filters</button>
        )}
      </div>
      {sm.showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <Caption className="mr-1">Directory</Caption>
          <DirectoryFilterChips modes={sm.modes} onChange={sm.setModes} />
          <span className="text-pb-faintest text-[10px] ml-1">tap once to exclude, twice to include</span>
        </div>
      )}
    </div>
  )
}

// One toggled list (in / not-in) with its own bulk bar and rows.
function ContactList({ which }) {
  const sm = useSM()
  const isIn = which === 'in'
  const shown = isIn ? sm.inList : sm.outList
  // Bulk targets are the selection restricted to THIS list. The two lists are
  // disjoint, so one shared selection set drives both cleanly.
  const selHere = isIn
    ? [...sm.selected].filter(id => sm.staticIds.has(id) && sm.inIds.has(id))
    : [...sm.selected].filter(id => !sm.inIds.has(id))
  const loading = sm.contacts == null || (isIn && sm.memberRows == null)

  return (
    <div className="rounded-xl border border-pb-hairline px-4 py-4 mt-4" style={{ background: 'var(--pb-surface)' }}>
      <div className="flex items-center justify-between mb-2">
        <SectionHeading className="!mb-0">{isIn ? 'Contacts in this segment' : 'Contacts not in this segment'}</SectionHeading>
        <span className="text-pb-faintest text-xs">{shown.length.toLocaleString()} shown</span>
      </div>

      {sm.segmentId && (
        <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 pb-hairline-b">
          <Button size="sm" onClick={() => sm.setMany(shown.map(c => c.id), true)} disabled={!shown.length}>
            Select all shown ({shown.length.toLocaleString()})
          </Button>
          {selHere.length > 0 ? (
            <>
              <span className="text-pb-text text-[12.5px] font-semibold">{selHere.length} selected</span>
              {isIn ? (
                <Button size="sm" variant="danger" onClick={() => sm.doRemove(selHere)} disabled={sm.busy}>
                  Remove ({selHere.length})
                </Button>
              ) : (
                <Button size="sm" variant="primary" onClick={() => sm.doAdd(selHere)} disabled={sm.busy}>
                  Add ({selHere.length})
                </Button>
              )}
              <Button size="sm" variant="quiet" onClick={sm.clearSelection}>Clear selection</Button>
            </>
          ) : (
            <span className="text-pb-faintest text-[12.5px]">
              Tick contacts to {isIn ? 'remove hand-picked ones' : 'add them'} in bulk.
            </span>
          )}
        </div>
      )}

      {loading ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : shown.length === 0 ? (
        <div className="text-pb-faintest text-sm">
          {isIn
            ? (sm.activeFilters ? 'Nobody in the segment matches your search.' : 'Nobody is in the segment yet — add a rule or hand-pick from the other list.')
            : (sm.activeFilters ? 'No other contacts match.' : 'Every contact is already in the segment.')}
        </div>
      ) : (
        <div className="max-h-[28rem] overflow-y-auto">
          {shown.slice(0, 500).map((c, i) => {
            const isStatic = sm.staticIds.has(c.id)
            return (
              <ContactRow key={c.id} c={c} last={i === 0} onDetails={sm.setDetailId}
                checked={sm.isChecked(c.id)}
                onCheck={sm.segmentId ? () => sm.toggleOne(c.id) : null}
                tag={isIn && !isStatic ? 'matched' : null}
                action={!sm.segmentId ? null : !isIn ? (
                  <Button size="sm" variant="primary" onClick={() => sm.doAdd([c.id])} disabled={sm.busy}>Add</Button>
                ) : isStatic ? (
                  <Button size="sm" variant="danger" onClick={() => sm.doRemove([c.id])} disabled={sm.busy}>Remove</Button>
                ) : null} />
            )
          })}
          {shown.length > 500 && (
            <div className="text-pb-faintest text-[10px] uppercase tracking-wide2 mt-2 py-1">
              Showing the first 500 of {shown.length.toLocaleString()} — narrow with the filters above
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Zone 3: the contact lists (bottom of the pane, below Include/exclude) ─────
export function SegmentContactLists() {
  const sm = useSM()
  if (!sm.show.in && !sm.show.out) return null
  return (
    <div className="mt-6">
      {sm.note && <Note className="mb-3">{sm.note}</Note>}
      {sm.show.in && <ContactList which="in" />}
      {sm.show.out && <ContactList which="out" />}
    </div>
  )
}
