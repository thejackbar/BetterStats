// Phone quick-post — a guided, drag-free variant of the editor for md and below.
// Live preview on top, then three numbered steps (what / details / look) and a
// sticky save footer. No canvas dragging by design.
//
// Props:
//   moduleLogo, clubName
//   W, H, content            full-size (W×H) preview node, scaled to fit
//   fontStyle                the display-font CSS vars for the preview
//   types [{key,label}], activeType, onPickType
//   fields [{label,value,onChange,placeholder}]   up to 3
//   palettes [{key,label,color}], paletteKey, onPickPalette
//   onExport, exporting, onFullEditor, onSaveDraft
import { useEffect, useRef, useState } from 'react'
import { Icon } from '../../../pages/admin/betterselect/ui'

function StepLabel({ n, children }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="w-5 h-5 rounded-full grid place-items-center font-mono text-[10px]"
        style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent)' }}>{n}</span>
      <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">{children}</span>
    </div>
  )
}

export default function MobileQuickPost({
  moduleLogo, clubName, W, H, content, fontStyle,
  types = [], activeType, onPickType,
  fields = [], palettes = [], paletteKey, onPickPalette,
  onExport, exporting, onFullEditor, onSaveDraft,
}) {
  const wrapRef = useRef(null)
  const [pw, setPw] = useState(342)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(() => setPw(el.clientWidth))
    ro.observe(el); setPw(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  const scale = pw / W

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-pb-bg text-pb-text">
      {/* Header */}
      <header className="h-12 shrink-0 flex items-center gap-2 px-3 border-b pb-hairline">
        {moduleLogo && <img src={moduleLogo} alt="" className="w-6 h-6 rounded-md" />}
        <span className="font-display font-extrabold text-[15px]">Better<span style={{ color: '#EC4899' }}>Posts</span></span>
        <span className="font-mono text-[9px] text-pb-faint uppercase ml-1">Quick post</span>
        <div className="flex-1" />
        <button onClick={onFullEditor} className="h-9 px-3 rounded-full border pb-hairline2 font-mono text-[9px] tracking-wide2 uppercase text-pb-dim">Full editor</button>
      </header>

      {/* Live preview */}
      <div ref={wrapRef} className="shrink-0 px-4 py-3 grid place-items-center" style={{ background: '#07090f' }}>
        <div style={{ width: pw, height: Math.round(H * scale), overflow: 'hidden', borderRadius: 8, boxShadow: '0 12px 30px rgba(0,0,0,.5)' }}>
          <div style={{ ...fontStyle, transform: `scale(${scale})`, transformOrigin: 'top left', width: W, height: H, position: 'relative', pointerEvents: 'none' }}>
            {content}
          </div>
        </div>
      </div>

      {/* Sheet */}
      <div className="flex-1 min-h-0 overflow-y-auto bg-pb-surface rounded-t-[20px] border-t pb-hairline px-4 pt-4 pb-24 flex flex-col gap-5">
        <div>
          <StepLabel n={1}>What is it</StepLabel>
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1">
            {types.map((t) => (
              <button key={t.key} onClick={() => onPickType(t.key)}
                className={`shrink-0 min-h-11 px-3.5 rounded-full border font-mono text-[10px] tracking-wide2 uppercase whitespace-nowrap transition-colors ${
                  activeType === t.key ? 'text-pb-accent' : 'border-pb-hairline2 text-pb-faint'
                }`}
                style={activeType === t.key ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {fields.length > 0 && (
          <div>
            <StepLabel n={2}>The details</StepLabel>
            <div className="flex flex-col gap-2">
              {fields.slice(0, 3).map((f, i) => (
                <label key={i} className="block">
                  <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">{f.label}</span>
                  <input value={f.value || ''} onChange={(e) => f.onChange(e.target.value)} placeholder={f.placeholder || ''}
                    className="mt-1 w-full h-11 px-3 rounded-lg border pb-hairline2 bg-pb-surface2 text-pb-text text-[14px] placeholder:text-pb-faintest" />
                </label>
              ))}
            </div>
          </div>
        )}

        <div>
          <StepLabel n={3}>The look</StepLabel>
          <div className="flex gap-2 flex-wrap">
            {palettes.map((p) => (
              <button key={p.key} onClick={() => onPickPalette(p.key)} title={p.label}
                className="w-11 h-11 rounded-lg border-2"
                style={{ background: p.color, borderColor: paletteKey === p.key ? 'var(--pb-accent)' : 'transparent' }} />
            ))}
          </div>
        </div>
      </div>

      {/* Sticky save footer */}
      <div className="absolute left-0 right-0 bottom-0 flex gap-2 p-3 bg-pb-surface border-t pb-hairline">
        <button onClick={onSaveDraft} className="flex-1 h-12 rounded-xl border pb-hairline2 font-mono text-[10px] tracking-wide2 uppercase text-pb-dim">Save draft</button>
        <button onClick={onExport} disabled={exporting}
          className="flex-1 h-12 rounded-xl font-mono text-[10px] tracking-wide2 uppercase flex items-center justify-center gap-1.5 disabled:opacity-60"
          style={{ background: '#EC4899', color: '#0a0d14' }}>
          {exporting ? 'Saving…' : <>Save to phone <Icon name="arrow" size={14} /></>}
        </button>
      </div>
    </div>
  )
}
