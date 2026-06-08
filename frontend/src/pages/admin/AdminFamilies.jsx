import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
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

function FamilyCard({ family, players, orgId, onChanged, onDeleted }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  const [members, setMembers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [pickedPlayer, setPickedPlayer] = useState(null)
  const [pickedRelationship, setPickedRelationship] = useState('')
  const [editingRel, setEditingRel] = useState(null) // player_id
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

  const availablePlayers = useMemo(() => {
    if (!members) return players
    const taken = new Set(members.map(m => m.player_id))
    return players.filter(p => !taken.has(p.id))
  }, [players, members])

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

  async function handleSaveRelationship(playerId) {
    try {
      await api.updateFamilyMember(family.id, playerId, orgId, editValue || null)
      setMembers(ms => ms.map(m => m.player_id === playerId ? { ...m, relationship: editValue || null } : m))
      setEditingRel(null)
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
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg"
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
                {members.map(m => (
                  <div key={m.player_id} className="flex items-center gap-2 bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-pb-text text-sm truncate">{m.name}</div>
                      {editingRel === m.player_id ? (
                        <div className="mt-1">
                          <RelationshipInput
                            value={editValue}
                            onChange={setEditValue}
                            onBlur={() => handleSaveRelationship(m.player_id)}
                            autoFocus
                          />
                        </div>
                      ) : (
                        <button
                          onClick={() => { setEditingRel(m.player_id); setEditValue(m.relationship || '') }}
                          className="text-left font-mono text-[10px] text-pb-faint hover:text-pb-text mt-0.5"
                        >
                          {m.relationship || 'Add relationship…'}
                        </button>
                      )}
                    </div>
                    <button
                      onClick={() => handleRemove(m.player_id)}
                      className="font-mono text-[10px] text-pb-faint hover:text-pb-red px-2 py-1"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-3 border-t pb-hairline-t">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">ADD MEMBER</div>
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
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40"
                style={{ background: 'var(--pb-accent)' }}
              >
                {adding ? 'Adding…' : 'Add'}
              </button>
            </div>
          </div>
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
  // All players selected by default — toggling lets the admin split a
  // mixed surname group (e.g. two unrelated Matthews families) into one
  // family at a time. Unselected players stay in the suggestion list and
  // come back on the next refresh.
  const [selectedIds, setSelectedIds] = useState(
    () => new Set(suggestion.players.map(p => p.id))
  )

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
  const partialSelection = selectedCount > 0 && selectedCount < playerCount

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">POSSIBLE FAMILY</div>
          <div className="text-pb-text font-semibold text-base">{suggestion.surname_display}</div>
        </div>
        <span className="font-mono text-[10px] text-pb-faint">
          {selectedCount === playerCount
            ? `${playerCount} PLAYERS`
            : `${selectedCount} / ${playerCount} SELECTED`}
        </span>
      </div>

      <div className="font-mono text-[10px] text-pb-faintest mb-1.5">
        Click a player to toggle. Unselected players stay in the suggestion list.
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
                  ? 'pb-hairline text-pb-text bg-pb-surface2'
                  : 'border-dashed border-pb-faintest text-pb-faintest line-through bg-transparent hover:text-pb-faint'
              }`}
              title={on ? 'Click to exclude from this family' : 'Click to include in this family'}
            >
              {p.name}
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
          Select none
        </button>
        {partialSelection && (
          <span className="font-mono text-[10px] text-pb-accent ml-auto">
            {playerCount - selectedCount} will be re-suggested
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
            className="w-full py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40"
            style={{ background: 'var(--pb-accent)' }}
          >
            {creating ? 'Creating…' : `Create + add ${selectedCount}`}
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
            className="w-full py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-40"
          >
            {adding ? 'Adding…' : `Add ${selectedCount}`}
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
    ])
      .then(([fams, pls, sugg]) => {
        if (cancelled) return
        setFamilies(fams || [])
        setPlayers(pls || [])
        setSuggestions(sugg || [])
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
    <AdminLayout>
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Families</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Group related players. Once created, families can be used as a filter in StatLab.
        </p>

        <div className="flex gap-1 mb-5">
          <button
            onClick={() => setTab('families')}
            className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === 'families' ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}
          >
            FAMILIES ({families.length})
          </button>
          <button
            onClick={() => setTab('suggestions')}
            className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === 'suggestions' ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}
          >
            SUGGESTIONS ({suggestions.length})
          </button>
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
                    className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40"
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
                className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2"
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
                No new suggestions. We group players who share an exact surname and aren't already in a family — once you've actioned or ignored everything, this tab will be empty.
              </div>
            ) : (
              <>
                <div className="font-mono text-[10px] text-pb-faint mb-2">
                  Players grouped by shared surname. These aren't guaranteed to be related — review and choose.
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
    </AdminLayout>
  )
}
