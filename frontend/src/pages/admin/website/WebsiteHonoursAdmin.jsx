import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

// Name field with a club-player autocomplete. Typing keeps a free-text name
// (player_id cleared); picking a suggestion links the player (sets name + id).
function PlayerNameInput({ players, name, playerId, onChange, placeholder = 'Name' }) {
  const [open, setOpen] = useState(false)
  const q = (name || '').trim().toLowerCase()
  const matches = q
    ? players.filter(p => (p.display_name_override || p.name || '').toLowerCase().includes(q)).slice(0, 6)
    : []
  return (
    <div className="relative w-full">
      <input
        value={name}
        onChange={e => { onChange(e.target.value, null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={`${inputCls} ${playerId ? 'pr-7' : ''}`}
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

function FieldLabel({ children }) {
  return <label className="block text-[10px] font-mono tracking-wide2 uppercase text-pb-faint mb-1">{children}</label>
}

function CategorySelect({ categories, srcCat, srcSub, onChange }) {
  const idx = categories.findIndex(c => c.category === srcCat && (c.subcategory || null) === (srcSub || null))
  return (
    <select
      value={srcCat && idx >= 0 ? String(idx) : ''}
      onChange={e => {
        if (e.target.value === '') return onChange(null, null)
        const c = categories[Number(e.target.value)]
        onChange(c.category, c.subcategory || null)
      }}
      className={inputCls}
    >
      <option value="">Manual entries (add by hand)</option>
      {categories.map((c, i) => (
        <option key={i} value={i}>
          Auto: {(c.subcategory ? `${c.category} — ${c.subcategory}` : c.category)} ({c.count})
        </option>
      ))}
    </select>
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
      <div className="flex flex-col sm:flex-row sm:items-end gap-2 py-2 pb-hairline-t">
        <div className="sm:w-20"><FieldLabel>Year</FieldLabel><input value={year} onChange={e => setYear(e.target.value)} placeholder="2024" className={inputCls} /></div>
        <div className="flex-1 min-w-0"><FieldLabel>Name</FieldLabel><PlayerNameInput players={players} name={name} playerId={pid} onChange={(n, id) => { setName(n); setPid(id) }} /></div>
        <div className="flex-1 min-w-0"><FieldLabel>Detail</FieldLabel><input value={detail} onChange={e => setDetail(e.target.value)} placeholder='e.g. "250 games"' className={inputCls} /></div>
        <div className="flex gap-1">
          <button onClick={save} className="px-3 py-2 text-xs rounded bg-pb-accent text-white">Save</button>
          <button onClick={() => setEditing(false)} className={btnGhost}>×</button>
        </div>
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

function Board({ board, players, categories, onChange, onDelete }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(board.title)
  const [description, setDescription] = useState(board.description || '')
  const [srcCat, setSrcCat] = useState(board.source_category || null)
  const [srcSub, setSrcSub] = useState(board.source_subcategory || null)
  const [cols, setCols] = useState(board.columns || 1)
  // new-entry form
  const [ny, setNy] = useState('')
  const [nname, setNname] = useState('')
  const [npid, setNpid] = useState(null)
  const [ndetail, setNdetail] = useState('')

  const isAuto = !!board.source_category

  async function saveBoard() {
    try {
      const b = await api.webAdminUpdateBoard(board.id, { title, description, source_category: srcCat, source_subcategory: srcSub, columns: cols })
      onChange({ ...board, ...b }); setEditing(false)
    } catch (e) { toast.error(e.message) }
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
        <div className="space-y-3 mb-3">
          <div><FieldLabel>Board title</FieldLabel><input value={title} onChange={e => setTitle(e.target.value)} className={`${inputCls} font-semibold`} /></div>
          <div><FieldLabel>Description (optional)</FieldLabel><input value={description} onChange={e => setDescription(e.target.value)} placeholder="A short line under the heading" className={inputCls} /></div>
          <div>
            <FieldLabel>Populate from</FieldLabel>
            <CategorySelect categories={categories} srcCat={srcCat} srcSub={srcSub} onChange={(c, s) => { setSrcCat(c); setSrcSub(s) }} />
            <p className="text-pb-faintest text-[11px] mt-1">Pick a category to auto-list everyone with that achievement, or keep it manual.</p>
          </div>
          <div className="sm:w-40">
            <FieldLabel>Columns</FieldLabel>
            <select value={cols} onChange={e => setCols(Number(e.target.value))} className={inputCls}>
              {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n} column{n > 1 ? 's' : ''}</option>)}
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={saveBoard} className="px-3 py-1.5 text-xs rounded bg-pb-accent text-white">Save board</button>
            <button onClick={() => setEditing(false)} className={btnGhost}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between mb-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-display font-bold text-lg text-pb-text">{board.title}</h3>
              {isAuto && <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-pb-accent/15 text-pb-accent">AUTO</span>}
            </div>
            {board.description && <p className="text-pb-faint text-sm">{board.description}</p>}
            {isAuto && (
              <p className="text-[11px] text-pb-faint mt-0.5">
                Auto-listing <span className="text-pb-dim font-medium">{board.auto_count ?? 0}</span> from
                {' '}<span className="text-pb-dim">{board.source_subcategory ? `${board.source_category} — ${board.source_subcategory}` : board.source_category}</span>
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setEditing(true)} className={btnGhost}>EDIT</button>
            <button onClick={() => onDelete(board.id)} className={btnDanger}>DELETE</button>
          </div>
        </div>
      )}

      {/* Manual entries */}
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
      <div className="mt-3 pt-3 border-t pb-hairline-t">
        <div className="text-[10px] font-mono tracking-wide2 uppercase text-pb-faintest mb-2">
          {isAuto ? 'Add an extra entry (on top of the auto list)' : 'Add an entry'}
        </div>
        <div className="flex flex-col sm:flex-row sm:items-end gap-2">
          <div className="sm:w-20"><FieldLabel>Year</FieldLabel><input value={ny} onChange={e => setNy(e.target.value)} placeholder="2024" className={inputCls} /></div>
          <div className="flex-1 min-w-0"><FieldLabel>Name</FieldLabel><PlayerNameInput players={players} name={nname} playerId={npid} onChange={(n, id) => { setNname(n); setNpid(id) }} placeholder="Type a name to link a player" /></div>
          <div className="flex-1 min-w-0"><FieldLabel>Detail (optional)</FieldLabel><input value={ndetail} onChange={e => setNdetail(e.target.value)} placeholder='e.g. "Inducted 2024"' className={inputCls} onKeyDown={e => e.key === 'Enter' && addEntry()} /></div>
          <button onClick={addEntry} className={`${btnPrimary} whitespace-nowrap`}>+ Add</button>
        </div>
      </div>
    </section>
  )
}

export default function WebsiteHonoursAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [boards, setBoards] = useState([])
  const [players, setPlayers] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [newTitle, setNewTitle] = useState('')
  const [newCat, setNewCat] = useState(null)
  const [newSub, setNewSub] = useState(null)
  const [newCols, setNewCols] = useState(1)

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try {
      const [b, p, c] = await Promise.all([
        api.webAdminListHonours(),
        api.adminListPlayers().catch(() => []),
        api.webAdminHonourCategories().catch(() => []),
      ])
      setBoards(b); setPlayers(p); setCategories(c)
    } catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  async function addBoard() {
    const title = newTitle.trim() || (newCat ? (newSub ? `${newCat} — ${newSub}` : newCat) : '')
    if (!title) { toast.error('Give the board a title (or pick a category)'); return }
    try {
      const b = await api.webAdminCreateBoard({ title, source_category: newCat, source_subcategory: newSub, columns: newCols })
      setBoards(prev => [...prev, b]); setNewTitle(''); setNewCat(null); setNewSub(null); setNewCols(1); showFlash('Board added')
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
        Honour boards — Life Members, Hall of Fame, Past Presidents, Club Champions and more. Link a board to an
        achievements category to auto-list everyone in it, or add entries by hand (type a name to link a player).
      </p>
      <div className="mb-5 px-4 py-3 rounded-lg border pb-hairline bg-pb-surface2/40 text-[12px] text-pb-faint">
        💡 <span className="text-pb-dim">Office bearers</span> (President, Secretary, Captain…) are pulled automatically
        from the <span className="text-pb-dim">current season's yearbook honour board</span> and shown at the top of your
        public Honours page — maintain those under <span className="font-mono">Yearbooks → Honour board</span>.
      </div>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : (
        <div className="space-y-5">
          {boards.map(b => <Board key={b.id} board={b} players={players} categories={categories} onChange={updateBoard} onDelete={deleteBoard} />)}
        </div>
      )}

      <div className="pb-card p-4 mt-5">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">New honour board</h3>
        <div className="space-y-2">
          <div><FieldLabel>Title</FieldLabel><input value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="e.g. Life Members" className={inputCls} onKeyDown={e => e.key === 'Enter' && addBoard()} /></div>
          <div>
            <FieldLabel>Populate from</FieldLabel>
            <CategorySelect categories={categories} srcCat={newCat} srcSub={newSub} onChange={(c, s) => { setNewCat(c); setNewSub(s) }} />
          </div>
          <div className="sm:w-40">
            <FieldLabel>Columns</FieldLabel>
            <select value={newCols} onChange={e => setNewCols(Number(e.target.value))} className={inputCls}>
              {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n} column{n > 1 ? 's' : ''}</option>)}
            </select>
          </div>
          <button onClick={addBoard} className={btnPrimary}>Add board</button>
        </div>
      </div>
    </div>
  )
}
