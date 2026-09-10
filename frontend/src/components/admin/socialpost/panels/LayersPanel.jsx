// Layers panel — one stack, front on top, holding the layout's OWN elements
// alongside the blocks somebody has added. Drag or step to reorder anything
// against anything, hide a layout element, duplicate or delete a block. The
// recent-edit History list sits underneath.
//
// The panel is deliberately dumb: it renders whatever stack it is handed and
// calls back with ids. The Blank canvas has no layout, so its stack is just its
// blocks — same component, same gestures, no second mode to keep in step.
//
// Props:
//   stack  [{ id, kind: 'template' | 'block', label, item? }]  back-to-front
//   selIds                              selected block ids
//   hidden                              Set of hidden layer ids
//   onSelect(id, additive)              select a block
//   onStep(id, 'up' | 'down')           move one place through the whole stack
//   onMove(dragId, overId)              drag reorder
//   onToggleHidden(id)                  show / hide a layout element
//   onDuplicate(id), onRemove(id)       block ops
//   backgroundName                      the layout's background, drawn as the floor
//   historyLog  [{ label, t }]          from useEditHistory
//   note                                explains what the stack reaches
import { useState } from 'react'
import { Icon } from '../../../../pages/admin/betterselect/ui'
import { itemLabel } from '../../../../social/blank-template'

export default function LayersPanel({
  stack = [], selIds = [], hidden = null, onSelect, onStep, onMove, onToggleHidden,
  onDuplicate, onRemove, historyLog = [], note = null, backgroundName = null,
}) {
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)

  // Front of the stack reads top-down, which is the way every layers panel in
  // every design tool reads.
  const rows = stack.slice().reverse()

  const row = (l) => {
    const isBlock = l.kind === 'block'
    const isHidden = hidden?.has(l.id)
    const label = isBlock ? itemLabel(l.item) : l.label
    return (
      <div key={l.id}
        data-testid={`layer-row-${l.kind}`}
        data-layer-id={l.id}
        draggable
        onDragStart={() => setDragId(l.id)}
        onDragEnd={() => { setDragId(null); setOverId(null) }}
        onDragOver={(e) => { e.preventDefault(); if (overId !== l.id) setOverId(l.id) }}
        onDrop={(e) => { e.preventDefault(); if (dragId && dragId !== l.id) onMove(dragId, l.id); setDragId(null); setOverId(null) }}
        onClick={(e) => isBlock && onSelect && onSelect(l.id, e.shiftKey || e.ctrlKey || e.metaKey)}
        className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md cursor-grab border ${
          selIds.includes(l.id) ? 'border-pb-accent bg-pb-surface2' : 'border-transparent hover:bg-pb-surface2'
        } ${overId === l.id && dragId ? 'border-pb-accent' : ''}`}>
        <span className={`font-mono text-[11px] truncate flex items-center gap-1.5 ${isHidden ? 'text-pb-faintest line-through' : isBlock ? 'text-pb-text' : 'text-pb-dim'}`}>
          <Icon name="grip" size={12} className="text-pb-faintest" />
          {label}
        </span>
        <span className="flex items-center gap-0.5 shrink-0 text-pb-faintest">
          <button onClick={(e) => { e.stopPropagation(); onStep(l.id, 'up') }} title="Forward" className="hover:text-pb-text p-0.5"><Icon name="chevron" size={12} className="-rotate-90" /></button>
          <button onClick={(e) => { e.stopPropagation(); onStep(l.id, 'down') }} title="Backward" className="hover:text-pb-text p-0.5"><Icon name="chevron" size={12} className="rotate-90" /></button>
          {isBlock ? (
            <>
              <button onClick={(e) => { e.stopPropagation(); onDuplicate(l.id) }} title="Duplicate" className="hover:text-pb-text p-0.5"><Icon name="cols" size={12} /></button>
              <button onClick={(e) => { e.stopPropagation(); onRemove(l.id) }} title="Delete" className="hover:text-pb-red p-0.5"><Icon name="trash" size={12} /></button>
            </>
          ) : (
            // A layout element is the layout's own, so it can be moved and
            // taken off the post but never deleted or duplicated — there is no
            // block behind it to duplicate.
            <button data-testid="layer-hide" onClick={(e) => { e.stopPropagation(); onToggleHidden && onToggleHidden(l.id) }}
              title={isHidden ? 'Show on the post' : 'Hide from the post'}
              className="hover:text-pb-text p-0.5">
              <Icon name={isHidden ? 'eyeOff' : 'eye'} size={12} />
            </button>
          )}
        </span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {note}
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Layers · front on top</div>
        {rows.length === 0 && <div className="text-pb-faintest text-[10px] font-mono py-2">No layers yet.</div>}
        {rows.map(row)}
        {backgroundName && (
          // The background is the floor rather than a layer, so it is shown
          // where it sits and cannot be dragged. That is the whole rule: every
          // element except the background is a layer.
          <div data-testid="layers-background-row"
            className="flex items-center gap-2 px-2 py-1.5 rounded-md border border-dashed pb-hairline2 bg-pb-surface2/60">
            <Icon name="image" size={12} className="text-pb-faintest" />
            <span className="font-mono text-[11px] text-pb-faintest truncate">{backgroundName} background</span>
          </div>
        )}
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
