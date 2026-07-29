// Layers panel — the block stack (front on top) with drag-to-reorder plus
// step / duplicate / delete, and the recent-edit History list underneath.
//
// Props:
//   items, selIds                       from useBlankLayer
//   onSelect(id, additive)              select a layer
//   onReorder(id, 'up'|'down')          step one
//   onDuplicate(id), onRemove(id)       block ops
//   onMoveLayerBefore(dragId, overId)   drag reorder
//   historyLog  [{ label, t }]          from useEditHistory
import { useState } from 'react'
import { Icon } from '../../../../pages/admin/betterselect/ui'
import { itemLabel } from '../../../../social/blank-template'

export default function LayersPanel({
  items = [], selIds = [], onSelect, onReorder, onDuplicate, onRemove, onMoveLayerBefore, historyLog = [],
}) {
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Layers · front on top</div>
        {items.length === 0 && <div className="text-pb-faintest text-[10px] font-mono py-2">No blocks yet.</div>}
        {items.slice().reverse().map((it) => (
          <div key={it.id}
            draggable
            onDragStart={() => setDragId(it.id)}
            onDragEnd={() => { setDragId(null); setOverId(null) }}
            onDragOver={(e) => { e.preventDefault(); if (overId !== it.id) setOverId(it.id) }}
            onDrop={(e) => { e.preventDefault(); if (dragId && dragId !== it.id) onMoveLayerBefore(dragId, it.id); setDragId(null); setOverId(null) }}
            onClick={(e) => onSelect(it.id, e.shiftKey || e.ctrlKey || e.metaKey)}
            className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md cursor-grab border ${
              selIds.includes(it.id) ? 'border-pb-accent bg-pb-surface2' : 'border-transparent hover:bg-pb-surface2'
            } ${overId === it.id && dragId ? 'border-pb-accent' : ''}`}>
            <span className="font-mono text-[11px] text-pb-text truncate flex items-center gap-1.5">
              <Icon name="grip" size={12} className="text-pb-faintest" />{itemLabel(it)}
            </span>
            <span className="flex items-center gap-0.5 shrink-0 text-pb-faintest">
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'up') }} title="Forward" className="hover:text-pb-text p-0.5"><Icon name="chevron" size={12} className="-rotate-90" /></button>
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'down') }} title="Backward" className="hover:text-pb-text p-0.5"><Icon name="chevron" size={12} className="rotate-90" /></button>
              <button onClick={(e) => { e.stopPropagation(); onDuplicate(it.id) }} title="Duplicate" className="hover:text-pb-text p-0.5"><Icon name="cols" size={12} /></button>
              <button onClick={(e) => { e.stopPropagation(); onRemove(it.id) }} title="Delete" className="hover:text-pb-red p-0.5"><Icon name="trash" size={12} /></button>
            </span>
          </div>
        ))}
      </div>

      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-1.5">History</div>
        {historyLog.length === 0 && <div className="text-pb-faintest text-[10px] font-mono py-1">Nothing yet.</div>}
        <div className="flex flex-col gap-0.5">
          {historyLog.map((h, i) => (
            <div key={h.t + '' + i} className={`px-2 py-1 rounded font-mono text-[10px] ${i === 0 ? 'text-pb-text bg-pb-surface2' : 'text-pb-faint'}`}>{h.label}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
