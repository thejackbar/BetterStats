import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

// Name field with a club-player autocomplete. Typing keeps a free-text name
// (player_id cleared); picking a suggestion links the player (sets name + id).
function PlayerNameInput({ players, name, playerId, onChange, placeholder = 'Name', className }) {
  const [open, setOpen] = useState(false)
  const q = (name || '').trim().toLowerCase()
  const matches = q
    ? players.filter(p => (p.display_name_override || p.name || '').toLowerCase().includes(q)).slice(0, 6)
    : []
  return (
    <div className="relative flex-1">
      <input
        value={name}
        onChange={e => { onChange(e.target.value, null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={`${className} ${playerId ? 'pr-7' : ''}`}
      />
      {playerId && <span title="Linked to player profile" className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px]" style={{ color: 'var(--pb-accent)' }}>🔗</span>}
      {open && matches.length > 0 && (
        <div className="absolute z-30 left-0 right-0 mt-1 bg-pb-surface border pb-hairline rounded shadow-lg max-h-48 overflow-auto">
          {matches.map(p => {
            const label = p.display_name_override || p.name
            return (
              <button
                key={p.id} type="button"
                onMouseDown={e => { e.preventDefault(); onChange(label, p.id); setOpen(false) }}
                className="block w-full text-left px-3 py-1.5 text-sm text-pb-text hover:bg-pb-surface2"
              >
                {label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function EntryRow({ entry, players, onSaved, onDeleted }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [year, setYear] = useState(entry.year ?? '')
  const [name, setName] = useState(entry.name)
  const [detail, setDetail] = useState(entry.detail || '')
  const [pid, setPid] = useState(entry.player_id || null)

  async function save() {
    try {
      const saved = await api.webAdminUpdateEntry(entry.id, {
        year: year === '' ? null : Number(year), name, detail, player_id: pid,
      })
      onSaved(saved); setEditing(false)
    } catch (e) { toast.error(e.message) }
  }
  async function del() {
    if (!confirm('Delete this entry?')) return
    try { await api.webAdminDeleteEntry(entry.id); onDeleted(entry.id) } catch (e) { toast.error(e.message) }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 py-2 pb-hairline-t">
        <input value={year} onChange={e => setYear(e.target.value)} placeholder="Year" className={`${inputCls} w-20`} />
        <PlayerNameInput players={players} name={name} playerId={pid} onChange={(n, id) => { setName(n); setPid(id) }} className={inputCls} />
        <input value={detail} onChange={e => setDetail(e.target.value)} placeholder="Detail" className={`${inputCls} flex-1`} />
        <button onClick={save} className="px-2 py-1 text-[10px] rounded bg-pb-accent text-white">SAVE</button>
        <button onClick={() => setEditing(false)} className={btnGhost}>×</button>
      </div>
    )
  }
  return (
    <div className="flex items-baseline gap-3 py-2 pb-hairline-t group">
      {entry.year != null && <span className="font-mono text-[12px] text-pb-faint w-12 tabular-nums">{entry.year}</span>}
      <span className="flex-1 text-pb-text text-sm">
        {entry.name}{entry.player_id && <span title="Linked to player" className="ml-1 text-[10px]" style={{ color: 'var(--pb-accent)' }}>🔗</span>}
        {entry.detail && <span className="text-pb-faint"> — {entry.detail}</span>}
      </span>
      <button onClick={() => setEditing(true)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text opacity-0 group-hover:opacity-100">EDIT</button>
      <button onClick={del} className="font-mono text-[10px] text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100">DEL</button>
    </div>
  )
}

function Board({ board, players, onChange, onDelete }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(board.title)
  const [description, setDescription] = useState(board.description || '')
  const [ny, setNy] = useState('')
  const [nname, setNname] = useState('')
  const [npid, setNpid] = useState(null)
  const [ndetail, setNdetail] = useState('')

  async function saveBoard() {
    try { const b = await api.webAdminUpdateBoard(board.id, { title, description }); onChange({ ...board, ...b }); setEditing(false) }
    catch (e) { toast.error(e.message) }
  }
  async function addEntry() {
    if (!nname.trim()) return
    try {
      const e = await api.webAdminCreateEntry(board.id, { year: ny === '' ? null : Number(ny), name: nname, detail: ndetail, player_id: npid })
      onChange({ ...board, entries: [...board.entries, e] })
      setNy(''); setNname(''); setNdetail(''); setNpid(null)
    } catch (err) { toast.error(err.message) }
  }

  return (
    <section className="pb-card p-4">
      {editing ? (
        <div className="space-y-2 mb-3">
          <input value={title} onChange={e => setTitle(e.target.value)} className={`${inputCls} font-semibold`} />
          <input value={description} onChange={e => setDescription(e.target.value)} placeholder="Description (optional)" className={inputCls} />
          <div className="flex gap-2">
            <button onClick={saveBoard} className="px-3 py-1 text-xs rounded bg-pb-accent text-white">Save</button>
            <button onClick={() => setEditing(false)} className={btnGhost}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between mb-2">
          <div>
            <h3 className="font-display font-bold text-lg text-pb-text">{board.title}</h3>
            {board.description && <p className="text-pb-faint text-sm">{board.description}</p>}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setEditing(true)} className={btnGhost}>EDIT</button>
            <button onClick={() => onDelete(board.id)} className={btnDanger}>DELETE</button>
          </div>
        </div>
      )}

      <div className="mt-2">
        {board.entries.map(e => (
          <EntryRow
            key={e.id} entry={e} players={players}
            onSaved={(saved) => onChange({ ...board, entries: board.entries.map(x => x.id === saved.id ? saved : x) })}
            onDeleted={(id) => onChange({ ...board, entries: board.entries.filter(x => x.id !== id) })}
          />
        ))}
      </div>

      {/* Add entry */}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t pb-hairline-t">
        <input value={ny} onChange={e => setNy(e.target.value)} placeholder="Year" className={`${inputCls} w-20`} />
        <PlayerNameInput players={players} name={nname} playerId={npid} onChange={(n, id) => { setNname(n); setNpid(id) }} placeholder="Name (type to link a player)" className={inputCls} />
        <input value={ndetail} onChange={e => setNdetail(e.target.value)} placeholder="Detail (optional)" className={`${inputCls} flex-1`} onKeyDown={e => e.key === 'Enter' && addEntry()} />
        <button onClick={addEntry} className="px-3 py-2 text-xs rounded bg-pb-accent text-white whitespace-nowrap">+ Add</button>
      </div>
    </section>
  )
}

export default function WebsiteHonoursAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [boards, setBoards] = useState([])
  const [players, setPlayers] = useState([])
  const [loading, setLoading] = useState(true)
  const [newTitle, setNewTitle] = useState('')

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try {
      const [b, p] = await Promise.all([api.webAdminListHonours(), api.adminListPlayers().catch(() => [])])
      setBoards(b); setPlayers(p)
    } catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  async function addBoard() {
    if (!newTitle.trim()) return
    try {
      const b = await api.webAdminCreateBoard({ title: newTitle })
      setBoards(prev => [...prev, b]); setNewTitle(''); showFlash('Board added')
    } catch (e) { toast.error(e.message) }
  }
  async function deleteBoard(id) {
    if (!confirm('Delete this whole board and its entries?')) return
    try { await api.webAdminDeleteBoard(id); setBoards(prev => prev.filter(b => b.id !== id)) }
    catch (e) { toast.error(e.message) }
  }
  const updateBoard = (b) => setBoards(prev => prev.map(x => x.id === b.id ? b : x))

  return (
    <div>
      <Flash msg={flash} />
      <p className="text-pb-faint text-sm mb-3">
        Honour boards — Life Members, Hall of Fame, Past Presidents, Club Champions and more.
        Type a name to link a player's profile.
      </p>
      <div className="mb-5 px-4 py-3 rounded-lg border pb-hairline bg-pb-surface2/40 text-[12px] text-pb-faint">
        💡 <span className="text-pb-dim">Office bearers</span> (President, Secretary, Captain…) are pulled automatically
        from the <span className="text-pb-dim">current season's yearbook honour board</span> and shown at the top of your
        public Honours page — maintain those under <span className="font-mono">Yearbooks → Honour board</span>, not here.
      </div>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : (
        <div className="space-y-5">
          {boards.map(b => <Board key={b.id} board={b} players={players} onChange={updateBoard} onDelete={deleteBoard} />)}
        </div>
      )}

      <div className="pb-card p-4 mt-5">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">New honour board</h3>
        <div className="flex gap-2">
          <input value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="e.g. Life Members" className={inputCls} onKeyDown={e => e.key === 'Enter' && addBoard()} />
          <button onClick={addBoard} className={btnPrimary}>Add board</button>
        </div>
      </div>
    </div>
  )
}
