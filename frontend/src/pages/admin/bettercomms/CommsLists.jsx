import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { ContactDetailModal } from './CommsContacts'

function ContactRow({ c, action, onDetails, last }) {
  return (
    <div className={`flex items-center justify-between gap-3 py-1.5 ${last ? '' : 'pb-hairline-t'}`}>
      <button onClick={() => onDetails(c.id)} className="min-w-0 text-left hover:opacity-80 flex-1" title="View details">
        <span className="text-sm text-pb-text truncate">{c.name || c.email}</span>
        {c.name && <span className="text-pb-faintest text-xs ml-2 truncate">{c.email}</span>}
      </button>
      {action}
    </div>
  )
}

function ListDetail({ list, onChanged }) {
  const [members, setMembers] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [detailId, setDetailId] = useState(null)

  const loadMembers = useCallback(() => {
    api.commsListMembers(list.id).then(setMembers).catch(() => setMembers([]))
  }, [list.id])
  useEffect(() => { loadMembers() }, [loadMembers])

  // Search ALL of the club's contacts (the previous version mishandled the
  // {contacts,summary} response and always came up empty).
  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsListContacts({ query }).then(r => { if (live) setResults(r.contacts || []) }).catch(() => {})
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [query])

  const memberIds = new Set((members || []).map(m => m.id))
  const q = query.trim().toLowerCase()
  const matchesQ = (c) => !q || (c.name || '').toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q)
  const shownMembers = (members || []).filter(matchesQ)
  const candidates = results.filter(c => !memberIds.has(c.id)).slice(0, 50)

  const add = async (cid) => {
    setBusy(true)
    try { await api.commsAddListMembers(list.id, [cid]); loadMembers(); onChanged() }
    finally { setBusy(false) }
  }
  const remove = async (cid) => {
    setBusy(true)
    try { await api.commsRemoveListMember(list.id, cid); loadMembers(); onChanged() }
    finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4">
      <div className="text-sm text-pb-text font-medium mb-3">{list.name}</div>
      <input value={query} onChange={e => setQuery(e.target.value)}
        placeholder="Search contacts (in this list and not yet added)…"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-4" />

      <div className="text-pb-faintest text-xs uppercase tracking-wide2 mb-2">In this list ({(members || []).length})</div>
      {members == null ? (
        <div className="text-pb-faint text-sm mb-4">Loading…</div>
      ) : shownMembers.length === 0 ? (
        <div className="text-pb-faintest text-sm mb-4">{q ? 'No members match your search.' : 'No contacts in this list yet. Add some below.'}</div>
      ) : (
        <div className="mb-4">
          {shownMembers.map((m, i) => (
            <ContactRow key={m.id} c={m} last={i === 0} onDetails={setDetailId}
              action={<button onClick={() => remove(m.id)} disabled={busy} className="text-pb-faint hover:text-pb-red text-xs px-1 shrink-0 disabled:opacity-50">Remove</button>} />
          ))}
        </div>
      )}

      <div className="text-pb-faintest text-xs uppercase tracking-wide2 mb-2 pt-3 pb-hairline-t">Not in this list</div>
      {candidates.length === 0 ? (
        <div className="text-pb-faintest text-sm">{q ? 'No other contacts match.' : 'Every contact is already in this list.'}</div>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          {candidates.map((c, i) => (
            <ContactRow key={c.id} c={c} last={i === 0} onDetails={setDetailId}
              action={<button onClick={() => add(c.id)} disabled={busy} className="px-2.5 py-1 rounded text-xs font-medium text-white disabled:opacity-50 shrink-0" style={{ background: 'var(--pb-accent)' }}>Add</button>} />
          ))}
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => loadMembers()} />}
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
            <div key={l.id} className={`flex items-center justify-between gap-3 px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <button onClick={() => setSelected(selected?.id === l.id ? null : l)} className="text-left min-w-0 flex-1">
                <div className="text-pb-text text-sm truncate">{l.name}</div>
                <div className="text-pb-faintest text-xs mt-0.5">{l.count} contact{l.count === 1 ? '' : 's'}</div>
              </button>
              <div className="flex items-center gap-3 shrink-0">
                <button onClick={() => setSelected(selected?.id === l.id ? null : l)} className="text-pb-faint text-xs hover:text-pb-text">
                  {selected?.id === l.id ? 'Close' : 'Manage'}
                </button>
                <button onClick={() => del(l)} className="text-pb-faint text-xs hover:text-pb-red">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && <ListDetail list={selected} onChanged={load} />}
    </BetterCommsLayout>
  )
}
