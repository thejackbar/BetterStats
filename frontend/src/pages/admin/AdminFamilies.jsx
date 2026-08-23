import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { FilterPill } from '../../components/admin/ui'
import Dropdown from '../../components/Dropdown'

const RELATIONSHIP_OPTIONS = [
  'Father', 'Mother', 'Son', 'Daughter',
  'Brother', 'Sister',
  'Husband', 'Wife', 'Partner',
  'Grandfather', 'Grandmother', 'Grandson', 'Granddaughter',
  'Uncle', 'Aunt', 'Nephew', 'Niece',
  'Cousin', 'Brother-in-law', 'Sister-in-law', 'Father-in-law', 'Mother-in-law',
  'Stepfather', 'Stepson',
]

function PlayerPicker({ players, value, onChange, placeholder = 'Search player…' }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 1) return []
    return players
      .filter(p => (p.name || '').toLowerCase().includes(q))
      .slice(0, 10)
  }, [players, query])

  function pick(p) {
    onChange(p)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={value ? value.name : query}
        onChange={e => {
          if (value) onChange(null)
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => { if (!value) setOpen(true) }}
        placeholder={placeholder}
        className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
      />
      <Dropdown
        anchorRef={ref}
        open={open && filtered.length > 0}
        onClose={() => setOpen(false)}
        maxHeight={208}
        className="bg-pb-surface border pb-hairline rounded shadow-xl pb-scroll"
      >
        {filtered.map(p => (
          <button
            key={p.id}
            onMouseDown={() => pick(p)}
            className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
          >
            {p.name}
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

function RelationshipInput({ value, onChange, onBlur, autoFocus }) {
  const listId = 'family-relationship-options'
  return (
    <>
      <input
        type="text"
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        onBlur={onBlur}
        autoFocus={autoFocus}
        list={listId}
        placeholder="e.g. Father, Son, Cousin"
        className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
      />
      <datalist id={listId}>
        {RELATIONSHIP_OPTIONS.map(opt => <option key={opt} value={opt} />)}
      </datalist>
    </>
  )
}

function FeeMemberPicker({ candidates, value, onChange, placeholder = 'Search parent/guardian…' }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 1) return []
    return candidates.filter(m => (m.full_name || '').toLowerCase().includes(q)).slice(0, 10)
  }, [candidates, query])

  function pick(m) {
    onChange(m)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={value ? value.full_name : query}
        onChange={e => { if (value) onChange(null); setQuery(e.target.value); setOpen(true) }}
        onFocus={() => { if (!value) setOpen(true) }}
        placeholder={placeholder}
        className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
      />
      <Dropdown anchorRef={ref} open={open && filtered.length > 0} onClose={() => setOpen(false)} maxHeight={208}
        className="bg-pb-surface border pb-hairline rounded shadow-xl pb-scroll">
        {filtered.map(m => (
          <button key={m.member_id} onMouseDown={() => pick(m)} className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text">
            {m.full_name}
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

function money(n) { return n == null ? '—' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}` }

function FamilyFinancials({ familyId, orgId, seasonId, seasons }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!seasonId) return
    setLoading(true)
    api.getFamilyFinancials(familyId, orgId, seasonId).then(setData).catch(e => toast.error(e.message)).finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, orgId, seasonId])

  if (!seasonId) return null
  const seasonName = seasons.find(s => s.id === seasonId)?.name || ''

  return (
    <div className="pt-3 border-t pb-hairline-t">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">FAMILY FINANCIALS, {seasonName.toUpperCase()}</div>
      {loading && <div className="font-mono text-[10px] text-pb-faint">Loading…</div>}
      {data && (
        <>
          <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-2 leading-relaxed">
            One view for one payment conversation with the family. Each member's own BetterFees record, summed. Billing itself
            still happens per member.
          </p>
          {data.members.length === 0 ? (
            <div className="font-mono text-[11px] text-pb-faint">No fee-tracked members in this family for this season.</div>
          ) : (
            <div className="space-y-1.5 mb-2">
              {data.members.map(m => (
                <div key={m.member_id} className="flex items-center justify-between font-mono text-[11px] text-pb-dim">
                  <span>{m.full_name}</span>
                  <span className={m.total_outstanding > 0 ? 'text-pb-text' : 'text-pb-faintest'}>{money(m.total_outstanding)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between font-mono text-[11px] pt-1.5 border-t pb-hairline-t">
                <span className="text-pb-text">Family total outstanding</span>
                <span className="font-display font-bold text-base" style={{ color: 'var(--pb-accent)' }}>{money(data.totals.total_outstanding)}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function FamilyCard({ family, players, orgId, seasonId, seasons, onChanged, onDeleted }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  const [members, setMembers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [pickedPlayer, setPickedPlayer] = useState(null)
  const [pickedRelationship, setPickedRelationship] = useState('')
  const [feeCandidates, setFeeCandidates] = useState([])
  const [pickedFeeMember, setPickedFeeMember] = useState(null)
  const [pickedFeeRelationship, setPickedFeeRelationship] = useState('')
  const [pickedIsGuardian, setPickedIsGuardian] = useState(true)
  const [addingFeeMember, setAddingFeeMember] = useState(false)
  const [showFinancials, setShowFinancials] = useState(false)
  const [editingRel, setEditingRel] = useState(null) // player_id or fee_member_id
  const [editValue, setEditValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState(family.name)
  const [newNotes, setNewNotes] = useState(family.notes || '')

  const loadMembers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getFamily(family.id, orgId)
      setMembers(data.members || [])
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [family.id, orgId, toast])

  useEffect(() => {
    if (expanded && members === null) loadMembers()
  }, [expanded, members, loadMembers])

  // Non-playing candidates (parents/guardians etc — manual, non-player
  // fee_members rows) for the "add non-player member" picker. Needs a
  // season to read from BetterFees' member list; harmless if none picked yet.
  useEffect(() => {
    if (!expanded || !seasonId) return
    api.feeListMembers(seasonId).then(d => setFeeCandidates((d.members || []).filter(m => !m.is_linked))).catch(() => {})
  }, [expanded, seasonId])

  const availablePlayers = useMemo(() => {
    if (!members) return players
    const taken = new Set(members.filter(m => m.kind === 'player').map(m => m.player_id))
    return players.filter(p => !taken.has(p.id))
  }, [players, members])

  const availableFeeCandidates = useMemo(() => {
    if (!members) return feeCandidates
    const taken = new Set(members.filter(m => m.kind === 'fee_member').map(m => m.fee_member_id))
    return feeCandidates.filter(m => !taken.has(m.member_id))
  }, [feeCandidates, members])

  async function handleAddMember() {
    if (!pickedPlayer) return
    setAdding(true)
    try {
      const res = await api.addFamilyMember(family.id, orgId, pickedPlayer.id, pickedRelationship || null)
      setMembers(res.members || [])
      setPickedPlayer(null)
      setPickedRelationship('')
      onChanged?.()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setAdding(false)
    }
  }

  async function handleAddFeeMember() {
    if (!pickedFeeMember) return
    setAddingFeeMember(true)
    try {
      const res = await api.addFamilyFeeMember(family.id, orgId, pickedFeeMember.member_id, pickedFeeRelationship || null, pickedIsGuardian)
      setMembers(res.members || [])
      setPickedFeeMember(null)
      setPickedFeeRelationship('')
      onChanged?.()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setAddingFeeMember(false)
    }
  }

  async function handleRemove(playerId) {
    if (!confirm('Remove this player from the family?')) return
    try {
      await api.removeFamilyMember(family.id, playerId, orgId)
      setMembers(ms => ms.filter(m => m.player_id !== playerId))
      onChanged?.()
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleRemoveFeeMember(feeMemberId) {
    if (!confirm('Remove this member from the family?')) return
    try {
      await api.removeFamilyFeeMember(family.id, feeMemberId, orgId)
      setMembers(ms => ms.filter(m => m.fee_member_id !== feeMemberId))
      onChanged?.()
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleSaveRelationship(playerId) {
    try {
      await api.updateFamilyMember(family.id, playerId, orgId, editValue || null)
      setMembers(ms => ms.map(m => m.player_id === playerId ? { ...m, relationship: editValue || null } : m))
      setEditingRel(null)
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleSaveFeeRelationship(feeMemberId) {
    try {
      await api.updateFamilyFeeMember(family.id, feeMemberId, orgId, { relationship: editValue || null })
      setMembers(ms => ms.map(m => m.fee_member_id === feeMemberId ? { ...m, relationship: editValue || null } : m))
      setEditingRel(null)
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleToggleGuardian(m) {
    try {
      if (m.kind === 'fee_member') await api.updateFamilyFeeMember(family.id, m.fee_member_id, orgId, { is_guardian: !m.is_guardian })
      setMembers(ms => ms.map(x => x.id === m.id ? { ...x, is_guardian: !x.is_guardian } : x))
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleRename() {
    const trimmed = newName.trim()
    if (!trimmed) return
    try {
      const patch = {}
      if (trimmed !== family.name) patch.name = trimmed
      if ((newNotes || '') !== (family.notes || '')) patch.notes = newNotes
      if (Object.keys(patch).length === 0) {
        setRenaming(false)
        return
      }
      await api.updateFamily(family.id, orgId, patch)
      toast.success('Family updated')
      setRenaming(false)
      onChanged?.()
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete the "${family.name}" family? Player records are kept; only the grouping is removed.`)) return
    try {
      await api.deleteFamily(family.id, orgId)
      toast.success('Family deleted')
      onDeleted?.()
    } catch (e) {
      toast.error(e.message)
    }
  }

  return (
    <div className="pb-card">
      <button
        onClick={() => setExpanded(x => !x)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition"
      >
        <div className="text-left">
          <div className="text-pb-text font-semibold text-sm">{family.name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {family.member_count} {family.member_count === 1 ? 'MEMBER' : 'MEMBERS'}
            {family.notes ? ' · HAS NOTES' : ''}
          </div>
        </div>
        <span className="font-mono text-[10px] text-pb-faint">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="border-t pb-hairline-t px-4 py-3 space-y-4">
          {renaming ? (
            <div className="space-y-2">
              <input
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="Family name"
                className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
              />
              <textarea
                value={newNotes}
                onChange={e => setNewNotes(e.target.value)}
                placeholder="Notes (optional)"
                rows={2}
                className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRename}
                  className="px-3 py-1.5 rounded text-[12.5px] font-semibold text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  Save
                </button>
                <button
                  onClick={() => { setRenaming(false); setNewName(family.name); setNewNotes(family.notes || '') }}
                  className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setRenaming(true)}
                className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text"
              >
                Edit name / notes
              </button>
              <button
                onClick={handleDelete}
                className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-red"
              >
                Delete family
              </button>
              {family.notes && (
                <span className="px-3 py-1.5 font-mono text-[10px] text-pb-dim italic">"{family.notes}"</span>
              )}
            </div>
          )}

          <div>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">MEMBERS</div>
            {loading && <div className="font-mono text-[10px] text-pb-faint">Loading…</div>}
            {members && members.length === 0 && (
              <div className="font-mono text-[11px] text-pb-faint">No members yet.</div>
            )}
            {members && members.length > 0 && (
              <div className="space-y-1.5">
                {members.map(m => {
                  const key = m.kind === 'player' ? m.player_id : m.fee_member_id
                  const isEditing = editingRel === key
                  const saveRel = () => m.kind === 'player' ? handleSaveRelationship(m.player_id) : handleSaveFeeRelationship(m.fee_member_id)
                  const remove = () => m.kind === 'player' ? handleRemove(m.player_id) : handleRemoveFeeMember(m.fee_member_id)
                  return (
                    <div key={m.id} className="flex items-center gap-2 bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-pb-text text-sm truncate flex items-center gap-1.5">
                          {m.name}
                          {m.kind === 'fee_member' && (
                            <span className="font-mono text-[8px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1 py-px">NON-PLAYER</span>
                          )}
                          {m.is_guardian && (
                            <span className="font-mono text-[8px] tracking-wide2 text-pb-accent border border-pb-accent/40 rounded px-1 py-px">GUARDIAN</span>
                          )}
                        </div>
                        {isEditing ? (
                          <div className="mt-1">
                            <RelationshipInput value={editValue} onChange={setEditValue} onBlur={saveRel} autoFocus />
                          </div>
                        ) : (
                          <button onClick={() => { setEditingRel(key); setEditValue(m.relationship || '') }}
                            className="text-left font-mono text-[10px] text-pb-faint hover:text-pb-text mt-0.5">
                            {m.relationship || 'Add relationship…'}
                          </button>
                        )}
                      </div>
                      {m.kind === 'fee_member' && (
                        <button onClick={() => handleToggleGuardian(m)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1">
                          {m.is_guardian ? 'Unmark guardian' : 'Mark guardian'}
                        </button>
                      )}
                      <button onClick={remove} className="font-mono text-[10px] text-pb-faint hover:text-pb-red px-2 py-1">
                        Remove
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="pt-3 border-t pb-hairline-t">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">ADD PLAYER</div>
            <div className="flex flex-col sm:flex-row gap-2 items-stretch">
              <div className="flex-1">
                <PlayerPicker
                  players={availablePlayers}
                  value={pickedPlayer}
                  onChange={setPickedPlayer}
                />
              </div>
              <div className="sm:w-48">
                <RelationshipInput value={pickedRelationship} onChange={setPickedRelationship} />
              </div>
              <button
                onClick={handleAddMember}
                disabled={!pickedPlayer || adding}
                className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40"
                style={{ background: 'var(--pb-accent)' }}
              >
                {adding ? 'Adding…' : 'Add'}
              </button>
            </div>
          </div>

          <div className="pt-3 border-t pb-hairline-t">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">ADD PARENT / GUARDIAN (NON-PLAYER)</div>
            {!seasonId ? (
              <div className="font-mono text-[10px] text-pb-faintest">Pick a season above to add a non-playing member.</div>
            ) : (
              <div className="flex flex-col sm:flex-row gap-2 items-stretch">
                <div className="flex-1">
                  <FeeMemberPicker candidates={availableFeeCandidates} value={pickedFeeMember} onChange={setPickedFeeMember} />
                </div>
                <div className="sm:w-40">
                  <RelationshipInput value={pickedFeeRelationship} onChange={setPickedFeeRelationship} placeholder="e.g. Mother, Father" />
                </div>
                <label className="flex items-center gap-1.5 font-mono text-[10px] text-pb-dim cursor-pointer select-none whitespace-nowrap px-1">
                  <input type="checkbox" checked={pickedIsGuardian} onChange={e => setPickedIsGuardian(e.target.checked)} />
                  Guardian
                </label>
                <button
                  onClick={handleAddFeeMember}
                  disabled={!pickedFeeMember || addingFeeMember}
                  className="px-4 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-40"
                >
                  {addingFeeMember ? 'Adding…' : 'Add'}
                </button>
              </div>
            )}
            <p className="text-[12.5px] leading-[1.6] text-pb-faint mt-1.5">
              Candidates come from BetterFees' non-playing members for the selected season. Add the parent there first (Members → + Member) if they're not listed.
            </p>
          </div>

          <button onClick={() => setShowFinancials(x => !x)}
            className="font-mono text-[10px] text-pb-faint hover:text-pb-text pt-1">
            {showFinancials ? '▾ Hide financials' : '▸ Show family financials'}
          </button>
          {showFinancials && <FamilyFinancials familyId={family.id} orgId={orgId} seasonId={seasonId} seasons={seasons} />}
        </div>
      )}
    </div>
  )
}

function SuggestionCard({ suggestion, families, orgId, onActioned }) {
  const toast = useToast()
  const [creating, setCreating] = useState(false)
  const [adding, setAdding] = useState(false)
  const [familyName, setFamilyName] = useState(`${suggestion.surname_display} Family`)
  const [chosenFamilyId, setChosenFamilyId] = useState('')
  // Nobody is selected up front — the admin picks who actually belongs to
  // the family, then confirms. A shared surname is only a hint (two
  // unrelated Matthews households are common), so opting people IN is the
  // deliberate act; anyone left unselected stays in the suggestion list and
  // comes back on the next refresh.
  const [selectedIds, setSelectedIds] = useState(() => new Set())

  function toggle(id) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const setAll = () => setSelectedIds(new Set(suggestion.players.map(p => p.id)))
  const setNone = () => setSelectedIds(new Set())

  const selectedCount = selectedIds.size
  const selectedPlayers = suggestion.players.filter(p => selectedIds.has(p.id))

  async function handleCreate() {
    const trimmed = familyName.trim()
    if (!trimmed || selectedCount === 0) return
    setCreating(true)
    try {
      const fam = await api.createFamily(orgId, trimmed)
      for (const p of selectedPlayers) {
        await api.addFamilyMember(fam.id, orgId, p.id, null)
      }
      toast.success(`Created "${trimmed}" with ${selectedCount} ${selectedCount === 1 ? 'member' : 'members'}`)
      onActioned?.()
    } catch (e) {
      toast.error(e.message)
      setCreating(false)
    }
  }

  async function handleAddToExisting() {
    if (!chosenFamilyId || selectedCount === 0) return
    setAdding(true)
    try {
      for (const p of selectedPlayers) {
        try {
          await api.addFamilyMember(chosenFamilyId, orgId, p.id, null)
        } catch (e) {
          if (!/already in this family/i.test(e.message)) throw e
        }
      }
      toast.success(`Added ${selectedCount} ${selectedCount === 1 ? 'player' : 'players'}`)
      onActioned?.()
    } catch (e) {
      toast.error(e.message)
      setAdding(false)
    }
  }

  async function handleDismiss() {
    try {
      await api.dismissFamilySuggestion(orgId, suggestion.surname_key)
      onActioned?.()
    } catch (e) {
      toast.error(e.message)
    }
  }

  const playerCount = suggestion.players.length
  const leftBehind = playerCount - selectedCount

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">POSSIBLE FAMILY</div>
          <div className="text-pb-text font-semibold text-base">{suggestion.surname_display}</div>
        </div>
        <span className="font-mono text-[10px] text-pb-faint">
          {selectedCount === 0
            ? `${playerCount} PLAYERS`
            : `${selectedCount} / ${playerCount} SELECTED`}
        </span>
      </div>

      <div className="font-mono text-[10px] text-pb-faintest mb-1.5">
        Select who belongs to this family, then confirm below. Anyone not selected stays in the suggestion list.
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {suggestion.players.map(p => {
          const on = selectedIds.has(p.id)
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => toggle(p.id)}
              className={`font-mono text-[10px] px-2 py-1 rounded border transition ${
                on
                  ? 'border-pb-accent/60 text-pb-text bg-pb-surface2'
                  : 'pb-hairline text-pb-faint bg-transparent hover:text-pb-text hover:bg-pb-surface2'
              }`}
              title={on ? 'Click to remove from this family' : 'Click to add to this family'}
            >
              {on ? '✓ ' : ''}{p.name}
            </button>
          )
        })}
      </div>
      <div className="flex gap-2 mb-3">
        <button
          type="button"
          onClick={setAll}
          disabled={selectedCount === playerCount}
          className="font-mono text-[10px] text-pb-faint hover:text-pb-text disabled:opacity-30 disabled:hover:text-pb-faint"
        >
          Select all
        </button>
        <span className="font-mono text-[10px] text-pb-faintest">·</span>
        <button
          type="button"
          onClick={setNone}
          disabled={selectedCount === 0}
          className="font-mono text-[10px] text-pb-faint hover:text-pb-text disabled:opacity-30 disabled:hover:text-pb-faint"
        >
          Clear selection
        </button>
        {selectedCount > 0 && leftBehind > 0 && (
          <span className="font-mono text-[10px] text-pb-accent ml-auto">
            {leftBehind} not selected, {leftBehind === 1 ? 'stays' : 'stay'} suggested
          </span>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="bg-pb-surface2/30 border pb-hairline rounded px-3 py-2.5">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">CREATE NEW FAMILY</div>
          <input
            type="text"
            value={familyName}
            onChange={e => setFamilyName(e.target.value)}
            className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-2 py-1.5 mb-2 focus:outline-none focus:border-pb-accent"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !familyName.trim() || selectedCount === 0}
            className="w-full py-1.5 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40"
            style={{ background: 'var(--pb-accent)' }}
          >
            {creating ? 'Creating…' : selectedCount === 0 ? 'Select players above' : `Confirm, create with ${selectedCount}`}
          </button>
        </div>

        <div className="bg-pb-surface2/30 border pb-hairline rounded px-3 py-2.5">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD TO EXISTING</div>
          <select
            value={chosenFamilyId}
            onChange={e => setChosenFamilyId(e.target.value)}
            className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-2 py-1.5 mb-2 focus:outline-none focus:border-pb-accent"
          >
            <option value="">Select family…</option>
            {families.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <button
            onClick={handleAddToExisting}
            disabled={adding || !chosenFamilyId || selectedCount === 0}
            className="w-full py-1.5 rounded text-[12.5px] font-semibold border pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-40"
          >
            {adding ? 'Adding…' : selectedCount === 0 ? 'Select players above' : `Confirm. Add ${selectedCount}`}
          </button>
        </div>
      </div>

      <div className="mt-2 text-right">
        <button
          onClick={handleDismiss}
          title="Never suggest this surname again"
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-red"
        >
          Ignore "{suggestion.surname_display}"
        </button>
      </div>
    </div>
  )
}

export default function AdminFamilies() {
  const { user } = useAuth()
  const toast = useToast()
  const [orgId, setOrgId] = useState(null)
  const [tab, setTab] = useState('families')
  const [families, setFamilies] = useState([])
  const [players, setPlayers] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [initialLoading, setInitialLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newNotes, setNewNotes] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (user?.club_id) setOrgId(user.club_id)
    else api.adminGetSettings().then(s => setOrgId(s.id)).catch(() => {})
  }, [user])

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    Promise.all([
      api.listFamilies(orgId),
      api.adminListPlayers(),
      api.getFamilySuggestions(orgId),
      api.adminListSeasons(),
    ])
      .then(([fams, pls, sugg, seas]) => {
        if (cancelled) return
        setFamilies(fams || [])
        setPlayers(pls || [])
        setSuggestions(sugg || [])
        const sorted = (seas || []).filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
        setSeasons(sorted)
        setSeasonId(prev => prev || sorted[0]?.id || '')
      })
      .catch(e => { if (!cancelled) toast.error(e.message) })
      .finally(() => { if (!cancelled) setInitialLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, refreshKey])

  const refresh = () => setRefreshKey(k => k + 1)

  async function handleCreate() {
    const trimmed = newName.trim()
    if (!trimmed) return
    setCreating(true)
    try {
      await api.createFamily(orgId, trimmed, newNotes || null)
      toast.success(`Created "${trimmed}"`)
      setShowCreate(false)
      setNewName('')
      setNewNotes('')
      refresh()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setCreating(false)
    }
  }

  if (!orgId) return (
    <BetterStatsLayout title="Families" caption="Players grouped into households">
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </BetterStatsLayout>
  )

  return (
    <BetterStatsLayout title="Families" caption="Players grouped into households">
      <div className="max-w-4xl">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-1">
          {seasons.length > 0 && (
            <select value={seasonId} onChange={e => setSeasonId(e.target.value)}
              className="bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent">
              {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
        </div>
        <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-5">
          Group related players and non-playing members, parents/guardians included. Once created, families can be used
          as a filter in StatLab; the season picker drives the non-player picker and family financials below.
        </p>

        <div className="flex flex-wrap gap-1 mb-5">
          <FilterPill active={tab === 'families'} onClick={() => setTab('families')}>FAMILIES ({families.length})</FilterPill>
          <FilterPill active={tab === 'suggestions'} onClick={() => setTab('suggestions')}>SUGGESTIONS ({suggestions.length})</FilterPill>
        </div>

        {initialLoading && <div className="font-mono text-[11px] text-pb-faint">Loading…</div>}

        {!initialLoading && tab === 'families' && (
          <div className="space-y-3">
            {showCreate ? (
              <div className="pb-card p-4">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">NEW FAMILY</div>
                <input
                  type="text"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  placeholder="Family name (e.g. The Barendse Family)"
                  className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 mb-2 focus:outline-none focus:border-pb-accent"
                />
                <textarea
                  value={newNotes}
                  onChange={e => setNewNotes(e.target.value)}
                  placeholder="Notes (optional)"
                  rows={2}
                  className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-3 py-2 mb-3 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleCreate}
                    disabled={!newName.trim() || creating}
                    className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40"
                    style={{ background: 'var(--pb-accent)' }}
                  >
                    {creating ? 'Creating…' : 'Create family'}
                  </button>
                  <button
                    onClick={() => { setShowCreate(false); setNewName(''); setNewNotes('') }}
                    className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowCreate(true)}
                className="px-4 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-text hover:bg-pb-surface2"
              >
                + New family
              </button>
            )}

            {families.length === 0 && !showCreate && (
              <div className="font-mono text-[11px] text-pb-faint mt-3">
                No families yet. Create one above or check the Suggestions tab.
              </div>
            )}

            {families.map(f => (
              <FamilyCard
                key={f.id}
                family={f}
                players={players}
                orgId={orgId}
                seasonId={seasonId}
                seasons={seasons}
                onChanged={refresh}
                onDeleted={refresh}
              />
            ))}
          </div>
        )}

        {!initialLoading && tab === 'suggestions' && (
          <div className="space-y-3">
            {suggestions.length === 0 ? (
              <div className="font-mono text-[11px] text-pb-faint">
                No new suggestions. We group players who share an exact surname and aren't already in a family, once you've actioned or ignored everything, this tab will be empty.
              </div>
            ) : (
              <>
                <div className="font-mono text-[10px] text-pb-faint mb-2">
                  Players grouped by shared surname. They aren't guaranteed to be related. Select the ones who are, then confirm.
                </div>
                {suggestions.map(s => (
                  <SuggestionCard
                    key={s.surname_key}
                    suggestion={s}
                    families={families}
                    orgId={orgId}
                    onActioned={refresh}
                  />
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </BetterStatsLayout>
  )
}
