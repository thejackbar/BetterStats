// Controls panel for the freeform "Blank Canvas" post builder (BL1).
// Renders an add-block toolbar, a layers list, and a property editor for the
// selected block. Positioning is done by dragging on the preview; this panel
// covers content, styling, z-order and precise numeric nudging.
import { BLANK_FONTS } from '../../social/blank-template'

const COLOR_TOKENS = [
  { key: 'ink', label: 'Ink' },
  { key: 'accent', label: 'Accent' },
  { key: 'primary', label: 'Primary' },
  { key: 'secondary', label: 'Second' },
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
      <div className="flex items-center gap-1.5">{children}</div>
    </label>
  )
}

function ColorPicker({ value, onChange, palette }) {
  const isToken = COLOR_TOKENS.some((t) => t.key === value)
  return (
    <div className="flex items-center gap-1 flex-wrap justify-end">
      {COLOR_TOKENS.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} title={t.label}
          className={`w-5 h-5 rounded border ${value === t.key ? 'ring-2 ring-white' : ''}`}
          style={{ background: swatchColor(t.key, palette), borderColor: 'rgba(255,255,255,0.25)' }} />
      ))}
      <input type="color" value={isToken ? '#ffffff' : (value || '#ffffff')}
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

function itemLabel(it) {
  if (it.type === 'text') return `“${(it.text || '').slice(0, 18) || 'Text'}${(it.text || '').length > 18 ? '…' : ''}”`
  if (it.type === 'image') return it.src ? 'Image' : 'Image (empty)'
  if (it.type === 'brand') return 'Club badge'
  return it.type
}

export default function BlankCanvasEditor({
  items, selId, setSelId, onAdd, onUpdate, onRemove, onDuplicate, onReorder, palette, onPickImage,
}) {
  const sel = items.find((it) => it.id === selId) || null
  const hasBrand = items.some((it) => it.type === 'brand')

  return (
    <section className="pb-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Blank Canvas</h2>
        <span className="font-mono text-[9px] text-pb-faintest">{items.length} block{items.length === 1 ? '' : 's'}</span>
      </div>

      <p className="text-pb-faintest text-[10px] leading-relaxed">
        Add text and images, then <span className="text-pb-faint">drag them on the preview</span> to position and use the corner handle to resize. The club badge is added by default so every post is branded.
      </p>

      {/* Add-block toolbar */}
      <div className="flex gap-2 flex-wrap">
        <button onClick={() => onAdd('text')}
          className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors">+ Text</button>
        <button onClick={() => onAdd('image')}
          className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors">+ Image</button>
        <button onClick={() => onAdd('brand')} disabled={hasBrand}
          className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors disabled:opacity-40">+ Club badge</button>
      </div>

      {/* Layers */}
      <div className="flex flex-col gap-1">
        {items.length === 0 && <div className="text-pb-faintest text-[10px] font-mono py-2">No blocks yet — add one above.</div>}
        {items.slice().reverse().map((it) => (
          <div key={it.id}
            onClick={() => setSelId(it.id)}
            className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded cursor-pointer border ${selId === it.id ? 'border-pb-text bg-pb-surface2' : 'border-transparent hover:bg-pb-surface2'}`}>
            <span className="font-mono text-[11px] text-pb-text truncate">{itemLabel(it)}</span>
            <div className="flex items-center gap-1 shrink-0">
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'front') }} title="Bring to front" className="text-pb-faintest hover:text-pb-text text-xs px-1">↑</button>
              <button onClick={(e) => { e.stopPropagation(); onReorder(it.id, 'back') }} title="Send to back" className="text-pb-faintest hover:text-pb-text text-xs px-1">↓</button>
              <button onClick={(e) => { e.stopPropagation(); onDuplicate(it.id) }} title="Duplicate" className="text-pb-faintest hover:text-pb-text text-xs px-1">⧉</button>
              <button onClick={(e) => { e.stopPropagation(); onRemove(it.id) }} title="Delete" className="text-pb-faintest hover:text-red-400 text-xs px-1">✕</button>
            </div>
          </div>
        ))}
      </div>

      {/* Selected block editor */}
      {sel && (
        <div className="border-t pb-hairline pt-3 flex flex-col gap-1">
          <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2 mb-1">Edit {sel.type}</div>

          {sel.type === 'text' && (
            <>
              <textarea value={sel.text} onChange={(e) => onUpdate(sel.id, { text: e.target.value })} rows={2}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[12px] text-pb-text resize-y" placeholder="Your text" />
              <Row label="Font">
                <select value={sel.fontFamily} onChange={(e) => onUpdate(sel.id, { fontFamily: e.target.value })}
                  className="bg-pb-surface2 border pb-hairline rounded px-2 py-0.5 text-[11px] font-mono text-pb-text max-w-[180px]">
                  {BLANK_FONTS.map((f) => <option key={f.key} value={f.family}>{f.name}</option>)}
                </select>
              </Row>
              <Row label="Size">
                <input type="range" min={16} max={340} value={sel.fontSize} onChange={(e) => onUpdate(sel.id, { fontSize: Number(e.target.value) })} className="w-28" />
                <NumField value={sel.fontSize} onChange={(v) => onUpdate(sel.id, { fontSize: v })} min={8} max={400} w="w-14" />
              </Row>
              <Row label="Colour"><ColorPicker value={sel.color} onChange={(c) => onUpdate(sel.id, { color: c })} palette={palette} /></Row>
              <Row label="Align">
                <SegBtn active={sel.align === 'left'} onClick={() => onUpdate(sel.id, { align: 'left' })}>L</SegBtn>
                <SegBtn active={sel.align === 'center'} onClick={() => onUpdate(sel.id, { align: 'center' })}>C</SegBtn>
                <SegBtn active={sel.align === 'right'} onClick={() => onUpdate(sel.id, { align: 'right' })}>R</SegBtn>
              </Row>
              <Row label="Style">
                <SegBtn active={sel.bold} onClick={() => onUpdate(sel.id, { bold: !sel.bold })} title="Bold">B</SegBtn>
                <SegBtn active={sel.uppercase} onClick={() => onUpdate(sel.id, { uppercase: !sel.uppercase })} title="Uppercase">AA</SegBtn>
              </Row>
              <Row label="Highlight">
                <SegBtn active={!sel.bg || sel.bg === 'none'} onClick={() => onUpdate(sel.id, { bg: 'none' })}>None</SegBtn>
                <SegBtn active={sel.bg === 'accent'} onClick={() => onUpdate(sel.id, { bg: 'accent' })}>Accent</SegBtn>
                <SegBtn active={sel.bg === 'ink'} onClick={() => onUpdate(sel.id, { bg: 'ink' })}>Ink</SegBtn>
              </Row>
              <Row label="Line height">
                <input type="range" min={0.8} max={2} step={0.05} value={sel.lineHeight ?? 1} onChange={(e) => onUpdate(sel.id, { lineHeight: Number(e.target.value) })} className="w-28" />
              </Row>
            </>
          )}

          {sel.type === 'image' && (
            <>
              <div className="flex gap-2">
                <label className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors cursor-pointer">
                  {sel.src ? 'Replace image' : 'Upload image'}
                  <input type="file" accept="image/png,image/webp,image/jpeg" className="sr-only"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) onPickImage(sel.id, f); e.target.value = '' }} />
                </label>
                {sel.src && <button onClick={() => onUpdate(sel.id, { src: null })} className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-faint hover:text-red-400">Remove</button>}
              </div>
              <Row label="Width"><NumField value={sel.w} onChange={(v) => onUpdate(sel.id, { w: v })} min={40} max={1080} /></Row>
              <Row label="Height"><NumField value={sel.h} onChange={(v) => onUpdate(sel.id, { h: v })} min={40} max={1080} /></Row>
              <Row label="Fit">
                <SegBtn active={sel.fit === 'contain'} onClick={() => onUpdate(sel.id, { fit: 'contain' })}>Fit</SegBtn>
                <SegBtn active={sel.fit === 'cover'} onClick={() => onUpdate(sel.id, { fit: 'cover' })}>Fill</SegBtn>
              </Row>
              <Row label="Corner"><NumField value={sel.radius} onChange={(v) => onUpdate(sel.id, { radius: v })} min={0} max={540} /></Row>
            </>
          )}

          {sel.type === 'brand' && (
            <>
              <Row label="Logo size">
                <input type="range" min={60} max={420} value={sel.size} onChange={(e) => onUpdate(sel.id, { size: Number(e.target.value) })} className="w-28" />
                <NumField value={sel.size} onChange={(v) => onUpdate(sel.id, { size: v })} min={48} max={480} w="w-14" />
              </Row>
              <Row label="Layout">
                <SegBtn active={sel.layout === 'row'} onClick={() => onUpdate(sel.id, { layout: 'row' })}>Row</SegBtn>
                <SegBtn active={sel.layout === 'stack'} onClick={() => onUpdate(sel.id, { layout: 'stack' })}>Stack</SegBtn>
              </Row>
              <Row label="Club name">
                <SegBtn active={sel.showName} onClick={() => onUpdate(sel.id, { showName: true })}>Show</SegBtn>
                <SegBtn active={!sel.showName} onClick={() => onUpdate(sel.id, { showName: false })}>Hide</SegBtn>
              </Row>
              <Row label="Colour"><ColorPicker value={sel.color} onChange={(c) => onUpdate(sel.id, { color: c })} palette={palette} /></Row>
            </>
          )}

          {/* Position — shared by every block type */}
          <Row label="Position">
            <span className="font-mono text-[9px] text-pb-faintest">X</span>
            <NumField value={sel.x} onChange={(v) => onUpdate(sel.id, { x: v })} min={-400} max={1080} w="w-14" />
            <span className="font-mono text-[9px] text-pb-faintest">Y</span>
            <NumField value={sel.y} onChange={(v) => onUpdate(sel.id, { y: v })} min={-400} max={1080} w="w-14" />
          </Row>
        </div>
      )}
    </section>
  )
}
