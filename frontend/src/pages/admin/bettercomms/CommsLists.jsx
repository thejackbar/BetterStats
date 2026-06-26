import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

// Add-members panel: search the club's contacts and tick the ones to add.
function AddMembers({ listId, memberIds, onAdded }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [picked, setPicked] = useState({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsListContacts({ query }).then(rows => { if (live) setResults(Array.isArray(rows) ? rows : []) }).catch(() => {})
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [query])

  const toggle = (id) => setPicked(p => ({ ...p, [id]: !p[id] }))
  const add = async () => {
    const ids = Object.keys(picked).filter(k => picked[k])
    if (!ids.length) return
    setBusy(true)
    try { await api.commsAddListMembers(listId, ids); setPicked({}); onAdded() }
    finally { setBusy(false) }
  }

  const candidates = results.filter(c => !memberIds.has(c.id))

  return (
    <div className="mt-3 pt-3 pb-hairline-t">
      <div className="flex items-center gap-2 mb-2">
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search contacts to add…"
          className="flex-1 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
        <button onClick={add} disabled={busy || !Object.values(picked).some(Boolean)}
          className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          Add
        </button>
      </div>
      <div className="max-h-52 overflow-y-auto">
        {candidates.length === 0 ? (
          <div className="text-pb-faintest text-xs py-2">No more contacts match.</div>
        ) : candidates.slice(0, 50).map(c => (
          <label key={c.id} className="flex items-center gap-2 py-1.5 cursor-pointer">
            <input type="checkbox" checked={!!picked[c.id]} onChange={() => toggle(c.id)} />
            <span className="text-sm text-pb-text truncate">{c.name || c.email}</span>
            <span className="text-pb-faintest text-xs truncate">{c.email}</span>
          </label>
        ))}
      </div>
    </div>
  )
}

function ListDetail({ list, onChanged }) {
  const [members, setMembers] = useState(null)
  const load = useCallback(() => {
    api.commsListMembers(list.id).then(setMembers).catch(() => setMembers([]))
  }, [list.id])
  useEffect(() => { load() }, [load])

  const remove = async (cid) => {
    await api.commsRemoveListMember(list.id, cid)
    setMembers(m => (m || []).filter(x => x.id !== cid))
    onChanged()
  }

  const memberIds = new Set((members || []).map(m => m.id))

  return (
    <div className="pb-card p-4">
      <div className="text-sm text-pb-text font-medium mb-2">{list.name}</div>
      {members == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : members.length === 0 ? (
        <div className="text-pb-faintest text-sm">No contacts in this list yet. Add some below.</div>
      ) : (
        <div>
          {members.map((m, i) => (
            <div key={m.id} className={`flex items-center justify-between gap-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="min-w-0">
                <span className="text-sm text-pb-text truncate">{m.name || m.email}</span>
                <span className="text-pb-faintest text-xs ml-2 truncate">{m.email}</span>
              </div>
              <button onClick={() => remove(m.id)} className="text-pb-faint hover:text-pb-red text-xs px-1 shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
      <AddMembers listId={list.id} memberIds={memberIds} onAdded={() => { load(); onChanged() }} />
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
