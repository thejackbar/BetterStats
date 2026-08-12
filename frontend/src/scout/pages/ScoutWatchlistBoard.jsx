import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { KanbanDnD, useKanbanDrag } from '../kanbanDnd'
import ScoutCardEditor from '../components/ScoutCardEditor'

export default function ScoutWatchlistBoard() {
  const { id } = useParams()
  const [board, setBoard] = useState(undefined) // undefined = loading
  const [error, setError] = useState(null)
  const [newColumnName, setNewColumnName] = useState('')
  const [addingColumn, setAddingColumn] = useState(false)
  const [editingCard, setEditingCard] = useState(null)

  const load = () => {
    scoutApi.getBoard(id).then(setBoard).catch((err) => setError(err.message))
  }

  useEffect(() => { load() }, [id])

  const onDrop = async (target, item) => {
    if (target.kind !== 'column' || item.kind !== 'card') return
    const toColumnId = target.idx
    if (toColumnId === item.fromColumnId) return
    // Optimistic: move the card locally straight away, append to the end of
    // the target column. Inter-card reordering within a column isn't wired
    // up yet — a card always lands at the end of wherever it's dropped.
    setBoard((b) => ({
      ...b,
      cards: b.cards.map((c) => (c.id === item.cardId ? { ...c, column_id: toColumnId } : c)),
    }))
    try {
      await scoutApi.moveCard(item.cardId, toColumnId, 9999)
    } catch (err) {
      setError(err.message)
      load() // reconcile with the server if the write failed
    }
  }

  const addColumn = async (e) => {
    e.preventDefault()
    if (!newColumnName.trim()) return
    setAddingColumn(true)
    try {
      const col = await scoutApi.createColumn(id, newColumnName.trim())
      setBoard((b) => ({ ...b, columns: [...b.columns, col] }))
      setNewColumnName('')
    } catch (err) {
      setError(err.message)
    } finally {
      setAddingColumn(false)
    }
  }

  const renameColumn = async (columnId, name) => {
    if (!name.trim()) return
    setBoard((b) => ({ ...b, columns: b.columns.map((c) => (c.id === columnId ? { ...c, name } : c)) }))
    try {
      await scoutApi.renameColumn(columnId, name.trim())
    } catch (err) {
      setError(err.message)
      load()
    }
  }

  const deleteColumn = async (columnId) => {
    try {
      await scoutApi.deleteColumn(columnId)
      load() // cards may have moved into another column server-side
    } catch (err) {
      setError(err.message)
    }
  }

  const saveCard = async (fields) => {
    const updated = await scoutApi.updateCard(editingCard.id, fields)
    setBoard((b) => ({ ...b, cards: b.cards.map((c) => (c.id === updated.id ? updated : c)) }))
  }

  const removeCard = async () => {
    await scoutApi.removeCard(editingCard.id)
    setBoard((b) => ({ ...b, cards: b.cards.filter((c) => c.id !== editingCard.id) }))
    setEditingCard(null)
  }

  if (error && !board) return <p className="text-sm text-[var(--pb-negative)]">{error}</p>
  if (board === undefined) return <p className="text-sm text-pb-dim">Loading…</p>

  return (
    <div className="space-y-4">
      <Link to="/betterscout/app/watchlists" className="text-sm text-pb-dim hover:text-pb-text">← Watchlists</Link>
      <h1 className="text-xl font-bold">{board.name}</h1>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}

      <KanbanDnD onDrop={onDrop} renderGhost={(item) => <CardChip card={item.card} ghost />}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {board.columns.map((col) => (
            <Column
              key={col.id} column={col}
              cards={board.cards.filter((c) => c.column_id === col.id)}
              onRename={(name) => renameColumn(col.id, name)}
              onDelete={() => deleteColumn(col.id)}
              onCardClick={setEditingCard}
              canDelete={board.columns.length > 1}
            />
          ))}
          <form onSubmit={addColumn} className="shrink-0 w-64">
            <input
              value={newColumnName} onChange={(e) => setNewColumnName(e.target.value)}
              placeholder="+ Add column" disabled={addingColumn}
              className="w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-sm"
            />
          </form>
        </div>
      </KanbanDnD>

      {editingCard && (
        <ScoutCardEditor
          card={editingCard}
          onClose={() => setEditingCard(null)}
          onSave={saveCard}
          onRemove={removeCard}
        />
      )}
    </div>
  )
}

function Column({ column, cards, onRename, onDelete, onCardClick, canDelete }) {
  const { hover } = useKanbanDrag()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(column.name)
  const isHover = hover === `column:${column.id}`

  return (
    <div
      data-drop-kind="column" data-drop-idx={column.id}
      className={`shrink-0 w-64 rounded-lg border ${isHover ? 'border-[var(--pb-accent)] bg-pb-surface2' : 'border-pb-hairline bg-pb-surface'} p-2 flex flex-col gap-2`}
    >
      <div className="flex items-center justify-between px-1 py-1">
        {editing ? (
          <input
            autoFocus value={name} onChange={(e) => setName(e.target.value)}
            onBlur={() => { setEditing(false); onRename(name) }}
            onKeyDown={(e) => { if (e.key === 'Enter') { setEditing(false); onRename(name) } }}
            className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-1.5 py-0.5 text-sm font-semibold"
          />
        ) : (
          <button onClick={() => setEditing(true)} className="font-semibold text-sm text-left hover:underline">
            {column.name}
          </button>
        )}
        <div className="flex items-center gap-2 text-xs text-pb-dim">
          <span>{cards.length}</span>
          {canDelete && (
            <button onClick={onDelete} title="Delete column" className="hover:text-[var(--pb-negative)]">✕</button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2 min-h-[60px]">
        {cards.map((card) => <Card key={card.id} card={card} onClick={() => onCardClick(card)} />)}
      </div>
    </div>
  )
}

function Card({ card, onClick }) {
  const { bind, clickGuard } = useKanbanDrag()
  return (
    <div
      {...bind({ kind: 'card', cardId: card.id, fromColumnId: card.column_id, card })}
      onClick={clickGuard(onClick)}
      className="pb-card p-3 cursor-pointer hover:border-[var(--pb-accent)]"
      style={{ touchAction: 'none' }}
    >
      <CardChip card={card} />
    </div>
  )
}

function CardChip({ card, ghost }) {
  return (
    <div className={ghost ? 'pb-card p-3 shadow-lg' : ''}>
      <div className="font-medium text-sm">{card.player.name}</div>
      <div className="text-xs text-pb-dim">{card.player.club_name || '—'}</div>
      {card.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {card.tags.slice(0, 3).map((t) => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-pb-surface2 text-pb-dim">{t}</span>
          ))}
        </div>
      )}
    </div>
  )
}
