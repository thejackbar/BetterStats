// Controls panel for the freeform "Blank Canvas" post builder (BL1).
// Add blocks (text / image / club badge / decorative elements), pick a starter
// layout, manage layers (drag to re-order, or step one at a time), select one
// or several blocks (shift-click), align a multi-selection, and edit the
// selected block. Positioning/resizing is done by dragging on the preview.
import { useState } from 'react'
import { BLANK_FONTS, BLANK_ELEMENTS, BLANK_STARTERS } from '../../social/blank-template'

const SWATCHES = [
  { key: 'primary', label: 'Club primary' },
  { key: 'secondary', label: 'Club secondary' },
  { key: 'accent', label: 'Accent' },
  { key: 'ink', label: 'Text' },
  { key: 'white', label: 'White' },
  { key: 'black', label: 'Black' },
]

function swatchColor(token, palette) {
  const map = { ink: palette.ink, accent: palette.accent, primary: palette.primary, secondary: palette.secondary, white: '#ffffff', black: '#0a0a0a' }
  return map[token] || token
}

function Row({ label, children }) {
  return (
    <label className="flex items-center justify-between gap-2 py-1">
      <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2 shrink-0">{label}</span>
      <div className="flex items-center gap-1.5 flex-wrap justify-end">{children}</div>
    </label>
  )
}

// Colour picker: quick swatches (club primary/secondary first) + a native
// picker for anything custom. `allowNone` adds a "none" option (for highlight).
function ColorPicker({ value, onChange, palette, allowNone }) {
  const isToken = SWATCHES.some((t) => t.key === value)
  return (
    <div className="flex items-center gap-1 flex-wrap justify-end">
      {allowNone && (
        <button onClick={() => onChange('none')} title="None"
          className={`w-5 h-5 rounded border grid place-items-center text-[9px] ${value === 'none' || !value ? 'ring-2 ring-white' : ''}`}
          style={{ borderColor: 'rgba(255,255,255,0.25)', color: '#888' }}>∅</button>
      )}
      {SWATCHES.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} title={t.label}
          className={`w-5 h-5 rounded border ${value === t.key ? 'ring-2 ring-white' : ''}`}
          style={{ background: swatchColor(t.key, palette), borderColor: 'rgba(255,255,255,0.25)' }} />
      ))}
      <input type="color" value={isToken || value === 'none' || !value ? '#ffffff' : value}
        onChange={(e) => onChange(e.target.value)} title="Custom colour"
        className="w-6 h-6 rounded bg-transparent border border-pb-hairline p-0 cursor-pointer" />
    </div>
  )
}

function NumField({ value, onChange, min = 0, max = 2000, step = 1, w = 'w-16' }) {
  return (
    <input type="number" value={value ?? 0} min={min} max={max} step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`${w} bg-pb-surface2 border pb-hairline rounded px-1.5 py-0.5 text-[11px] font-mono text-pb-text`} />
  )
}

const SegBtn = ({ active, onClick, children, title }) => (
  <button onClick={onClick} title={title}
    className={`px-2 py-0.5 rounded text-[11px] font-mono border ${active ? 'border-pb-text text-pb-text' : 'border-transparent text-pb-faint hover:text-pb-text'}`}>
    {children}
  </button>
)

const AddBtn = ({ onClick, children, disabled }) => (
  <button onClick={onClick} disabled={disabled}
    className="px-2.5 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors disabled:opacity-40">
    {children}
  </button>
)

function itemLabel(it) {
  if (it.type === 'text') return `“${(it.text || '').slice(0, 16) || 'Text'}${(it.text || '').length > 16 ? '…' : ''}”`
  if (it.type === 'image') return it.src ? 'Image' : 'Image (empty)'
  if (it.type === 'brand') return 'Club badge'
  if (it.type === 'element') return { line: 'Line', divider: 'Divider', rect: 'Box', ellipse: 'Circle', triangle: 'Triangle' }[it.shape] || 'Element'
  return it.type
}

export default function BlankCanvasEditor({
  items, selIds, onSelect, onDeselect, onAdd, onUpdate, onRemove, onDuplicate,
  onReorder, onMoveLayerBefore, onAlign, onApplyStarter, palette, onPickImage,
}) {
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)
  const single = selIds.length === 1 ? items.find((it) => it.id === selIds[0]) : null
  const hasBrand = items.some((it) => it.type === 'brand')

  return (
    <section className="pb-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Blank Canvas</h2>
        <span className="font-mono text-[9px] text-pb-faintest">{items.length} block{items.length === 1 ? '' : 's'}</span>
      </div>

      {/* Starter layouts */}
      <div>
        <div className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2 mb-1">Start from</div>
        <div className="flex gap-1.5 flex-wrap">
          {BLANK_STARTERS.map((s) => (
            <button key={s.key} onClick={() => onApplyStarter(s.key)}
              className="px-2.5 py-1 rounded text-[11px] font-mono border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-text transition-colors">{s.name}</button>
          ))}
        </div>
      </div>

      <p className="text-pb-faintest text-[10px] leading-relaxed">
        Add blocks, then <span className="text-pb-faint">drag on the preview</span> to move (shift-click for several), corner handle to resize.
      </p>

      {/* Add-block toolbar */}
      <div className="flex gap-1.5 flex-wrap">
        <AddBtn onClick={() => onAdd('text')}>+ Text</AddBtn>
        <AddBtn onClick={() => onAdd('image')}>+ Image</AddBtn>
        <AddBtn onClick={() => onAdd('brand')} disabled={hasBrand}>+ Club badge</AddBtn>
      </div>
      <div className="flex gap-1.5 flex-wrap items-center">
        <span className="font-mono text-[9px] text-pb-faintest uppercase">Elements</span>
        {BLANK_ELEMENTS.map((el) => (
          <AddBtn key={el.shape} onClick={() => onAdd('element', { shape: el.shape })}>+ {el.name}</AddBtn>
        ))}
      </div>

      {/* Layers (drag to re-order) */}
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">Layers · front on top</div>
        {items.length === 0 && <div className="text-pb-faintest text-[10px] font-mono py-2">No blocks yet — add one above.</div>}
        {items.slice().reverse().map((it) => (
          <div key={it.id}
            draggable
            onDragStart={() => setDragId(it.id)}
            onDragEnd={() => { setDragId(null); setOverId(null) }}
            onDragOver={(e) => { e.preventDefault(); if (overId !== it.id) setOverId(it.id) }}
            onDrop={(e) => { e.preventDefault(); if (dragId && dragId !== it.id) onMoveLayerBefore(dragId, it.id); setDragId(null); setOverId(null) }}
            onClick={(e) => onSelect(it.id, e.shiftKey || e.ctrlKey || e.metaKey)}
            className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded cursor-grab border ${selIds.includes(it.id) ? 'border-pb-text bg-pb-surface2' : 'border-transparent hover:bg-pb-surface2'} ${overId === it.id && dragId ? 'border-pb-accent' : ''}`}>
            <span className="font-mono text-[11px] text-pb-text truncate flex items-center gap-1.5"><span className="text-pb-faintest">⠿</span>{itemLabel(it)}</span>
            <div className="flex items-center gap-0.5 shrink-0">
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'up') }} title="Up one" className="text-pb-faintest hover:text-pb-text text-xs px-1">▲</button>
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'down') }} title="Down one" className="text-pb-faintest hover:text-pb-text text-xs px-1">▼</button>
              <button onClick={(e) => { e.stopPropagation(); onDuplicate(it.id) }} title="Duplicate" className="text-pb-faintest hover:text-pb-text text-xs px-1">⧉</button>
              <button onClick={(e) => { e.stopPropagation(); onRemove(it.id) }} title="Delete" className="text-pb-faintest hover:text-red-400 text-xs px-1">✕</button>
            </div>
          </div>
        ))}
      </div>

      {/* Multi-select: align tools */}
      {selIds.length > 1 && (
        <div className="border-t pb-hairline pt-3 flex flex-col gap-2">
          <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2">{selIds.length} selected</div>
          <Row label="Align">
            <SegBtn onClick={() => onAlign('left')} title="Align left">⇤</SegBtn>
            <SegBtn onClick={() => onAlign('center')} title="Align centre">⇔</SegBtn>
            <SegBtn onClick={() => onAlign('right')} title="Align right">⇥</SegBtn>
          </Row>
          <p className="text-pb-faintest text-[10px]">Drag any selected block on the preview to move the group; use the group handle to resize together.</p>
          <button onClick={onDeselect} className="self-start px-2.5 py-1 rounded text-[11px] font-mono border pb-hairline text-pb-faint hover:text-pb-text">Clear selection</button>
        </div>
      )}

      {/* Single-select: property editor */}
      {single && (
        <div className="border-t pb-hairline pt-3 flex flex-col gap-1">
          <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2 mb-1">Edit {single.type === 'element' ? itemLabel(single).toLowerCase() : single.type}</div>

          {single.type === 'text' && (
            <>
              <textarea value={single.text} onChange={(e) => onUpdate(single.id, { text: e.target.value })} rows={2}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[12px] text-pb-text resize-y" placeholder="Your text" />
              <Row label="Font">
                <select value={single.fontFamily} onChange={(e) => onUpdate(single.id, { fontFamily: e.target.value })}
                  className="bg-pb-surface2 border pb-hairline rounded px-2 py-0.5 text-[11px] font-mono text-pb-text max-w-[180px]">
                  {BLANK_FONTS.map((f) => <option key={f.key} value={f.family}>{f.name}</option>)}
                </select>
              </Row>
              <Row label="Size">
                <input type="range" min={16} max={340} value={single.fontSize} onChange={(e) => onUpdate(single.id, { fontSize: Number(e.target.value) })} className="w-24" />
                <NumField value={single.fontSize} onChange={(v) => onUpdate(single.id, { fontSize: v })} min={8} max={400} w="w-14" />
              </Row>
              <Row label="Colour"><ColorPicker value={single.color} onChange={(c) => onUpdate(single.id, { color: c })} palette={palette} /></Row>
              <Row label="Align">
                <SegBtn active={single.align === 'left'} onClick={() => onUpdate(single.id, { align: 'left' })}>L</SegBtn>
                <SegBtn active={single.align === 'center'} onClick={() => onUpdate(single.id, { align: 'center' })}>C</SegBtn>
                <SegBtn active={single.align === 'right'} onClick={() => onUpdate(single.id, { align: 'right' })}>R</SegBtn>
              </Row>
              <Row label="Style">
                <SegBtn active={single.bold} onClick={() => onUpdate(single.id, { bold: !single.bold })} title="Bold">B</SegBtn>
                <SegBtn active={single.uppercase} onClick={() => onUpdate(single.id, { uppercase: !single.uppercase })} title="Uppercase">AA</SegBtn>
              </Row>
              <Row label="Highlight"><ColorPicker value={single.bg} onChange={(c) => onUpdate(single.id, { bg: c })} palette={palette} allowNone /></Row>
              <Row label="Line height">
                <input type="range" min={0.8} max={2} step={0.05} value={single.lineHeight ?? 1} onChange={(e) => onUpdate(single.id, { lineHeight: Number(e.target.value) })} className="w-24" />
              </Row>
            </>
          )}

          {single.type === 'image' && (
            <>
              <div className="flex gap-2 flex-wrap">
                <label className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors cursor-pointer">
                  {single.src ? 'Replace image' : 'Upload image'}
                  <input type="file" accept="image/png,image/webp,image/jpeg" className="sr-only"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) onPickImage(single.id, f); e.target.value = '' }} />
                </label>
                {single.src && <button onClick={() => onUpdate(single.id, { src: null })} className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-faint hover:text-red-400">Remove</button>}
              </div>
              <Row label="Width"><NumField value={single.w} onChange={(v) => onUpdate(single.id, { w: v })} min={40} max={1080} /></Row>
              <Row label="Height"><NumField value={single.h} onChange={(v) => onUpdate(single.id, { h: v })} min={40} max={1080} /></Row>
              <Row label="Fit">
                <SegBtn active={single.fit === 'contain'} onClick={() => onUpdate(single.id, { fit: 'contain' })}>Fit</SegBtn>
                <SegBtn active={single.fit === 'cover'} onClick={() => onUpdate(single.id, { fit: 'cover' })}>Fill</SegBtn>
              </Row>
              <Row label="Corner"><NumField value={single.radius} onChange={(v) => onUpdate(single.id, { radius: v })} min={0} max={540} /></Row>
            </>
          )}

          {single.type === 'brand' && (
            <>
              <Row label="Logo size">
                <input type="range" min={60} max={420} value={single.size} onChange={(e) => onUpdate(single.id, { size: Number(e.target.value) })} className="w-24" />
                <NumField value={single.size} onChange={(v) => onUpdate(single.id, { size: v })} min={48} max={480} w="w-14" />
              </Row>
              <Row label="Layout">
                <SegBtn active={single.layout === 'row'} onClick={() => onUpdate(single.id, { layout: 'row' })}>Row</SegBtn>
                <SegBtn active={single.layout === 'stack'} onClick={() => onUpdate(single.id, { layout: 'stack' })}>Stack</SegBtn>
              </Row>
              <Row label="Club name">
                <SegBtn active={single.showName} onClick={() => onUpdate(single.id, { showName: true })}>Show</SegBtn>
                <SegBtn active={!single.showName} onClick={() => onUpdate(single.id, { showName: false })}>Hide</SegBtn>
              </Row>
              <Row label="Colour"><ColorPicker value={single.color} onChange={(c) => onUpdate(single.id, { color: c })} palette={palette} /></Row>
            </>
          )}

          {single.type === 'element' && (
            <>
              <Row label="Colour"><ColorPicker value={single.color} onChange={(c) => onUpdate(single.id, { color: c })} palette={palette} /></Row>
              {(single.shape === 'line' || single.shape === 'divider') && (
                <Row label="Thickness"><NumField value={single.thickness} onChange={(v) => onUpdate(single.id, { thickness: v, h: v })} min={1} max={80} /></Row>
              )}
              {(single.shape === 'rect' || single.shape === 'ellipse') && (
                <>
                  <Row label="Fill">
                    <SegBtn active={single.fill !== false} onClick={() => onUpdate(single.id, { fill: true })}>Solid</SegBtn>
                    <SegBtn active={single.fill === false} onClick={() => onUpdate(single.id, { fill: false })}>Outline</SegBtn>
                  </Row>
                  {single.fill === false && <Row label="Stroke"><NumField value={single.thickness} onChange={(v) => onUpdate(single.id, { thickness: v })} min={1} max={60} /></Row>}
                </>
              )}
              {single.shape === 'rect' && <Row label="Corner"><NumField value={single.radius} onChange={(v) => onUpdate(single.id, { radius: v })} min={0} max={300} /></Row>}
              <Row label="Width"><NumField value={single.w} onChange={(v) => onUpdate(single.id, { w: v })} min={4} max={1080} /></Row>
              {single.shape !== 'line' && single.shape !== 'divider' && <Row label="Height"><NumField value={single.h} onChange={(v) => onUpdate(single.id, { h: v })} min={4} max={1080} /></Row>}
              <Row label="Rotation"><input type="range" min={-180} max={180} value={single.rotation || 0} onChange={(e) => onUpdate(single.id, { rotation: Number(e.target.value) })} className="w-24" /><NumField value={single.rotation || 0} onChange={(v) => onUpdate(single.id, { rotation: v })} min={-180} max={180} w="w-12" /></Row>
              <Row label="Opacity"><input type="range" min={0.1} max={1} step={0.05} value={single.opacity ?? 1} onChange={(e) => onUpdate(single.id, { opacity: Number(e.target.value) })} className="w-24" /></Row>
            </>
          )}

          {/* Position — shared */}
          <Row label="Position">
            <span className="font-mono text-[9px] text-pb-faintest">X</span>
            <NumField value={single.x} onChange={(v) => onUpdate(single.id, { x: v })} min={-400} max={1080} w="w-14" />
            <span className="font-mono text-[9px] text-pb-faintest">Y</span>
            <NumField value={single.y} onChange={(v) => onUpdate(single.id, { y: v })} min={-400} max={1080} w="w-14" />
          </Row>
        </div>
      )}
    </section>
  )
}
