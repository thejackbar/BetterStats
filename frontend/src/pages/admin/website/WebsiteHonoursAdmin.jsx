import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function EntryRow({ entry, onSaved, onDeleted }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [year, setYear] = useState(entry.year ?? '')
  const [name, setName] = useState(entry.name)
  const [detail, setDetail] = useState(entry.detail || '')

  async function save() {
    try {
      const saved = await api.webAdminUpdateEntry(entry.id, { year: year === '' ? null : Number(year), name, detail })
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
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Name" className={`${inputCls} flex-1`} />
        <input value={detail} onChange={e => setDetail(e.target.value)} placeholder="Detail" className={`${inputCls} flex-1`} />
        <button onClick={save} className="px-2 py-1 text-[10px] rounded bg-pb-accent text-white">SAVE</button>
        <button onClick={() => setEditing(false)} className={btnGhost}>×</button>
      </div>
    )
  }
  return (
    <div className="flex items-baseline gap-3 py-2 pb-hairline-t group">
      {entry.year != null && <span className="font-mono text-[12px] text-pb-faint w-12 tabular-nums">{entry.year}</span>}
      <span className="flex-1 text-pb-text text-sm">{entry.name}{entry.detail && <span className="text-pb-faint"> — {entry.detail}</span>}</span>
      <button onClick={() => setEditing(true)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text opacity-0 group-hover:opacity-100">EDIT</button>
      <button onClick={del} className="font-mono text-[10px] text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100">DEL</button>
    </div>
  )
}

function Board({ board, onChange, onDelete }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(board.title)
  const [description, setDescription] = useState(board.description || '')
  const [ny, setNy] = useState('')
  const [nname, setNname] = useState('')
  const [ndetail, setNdetail] = useState('')

  async function saveBoard() {
    try { const b = await api.webAdminUpdateBoard(board.id, { title, description }); onChange({ ...board, ...b }); setEditing(false) }
    catch (e) { toast.error(e.message) }
  }
  async function addEntry() {
    if (!nname.trim()) return
    try {
      const e = await api.webAdminCreateEntry(board.id, { year: ny === '' ? null : Number(ny), name: nname, detail: ndetail })
      onChange({ ...board, entries: [...board.entries, e] })
      setNy(''); setNname(''); setNdetail('')
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
            key={e.id} entry={e}
            onSaved={(saved) => onChange({ ...board, entries: board.entries.map(x => x.id === saved.id ? saved : x) })}
            onDeleted={(id) => onChange({ ...board, entries: board.entries.filter(x => x.id !== id) })}
          />
        ))}
      </div>

      {/* Add entry */}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t pb-hairline-t">
        <input value={ny} onChange={e => setNy(e.target.value)} placeholder="Year" className={`${inputCls} w-20`} />
        <input value={nname} onChange={e => setNname(e.target.value)} placeholder="Name" className={`${inputCls} flex-1`} onKeyDown={e => e.key === 'Enter' && addEntry()} />
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
  const [loading, setLoading] = useState(true)
  const [newTitle, setNewTitle] = useState('')

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try { setBoards(await api.webAdminListHonours()) }
    catch (e) { toast.error(e.message) }
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
      <p className="text-pb-faint text-sm mb-4">Honour boards — Life Members, Hall of Fame, Past Presidents, Club Champions and more.</p>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : (
        <div className="space-y-5">
          {boards.map(b => <Board key={b.id} board={b} onChange={updateBoard} onDelete={deleteBoard} />)}
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
