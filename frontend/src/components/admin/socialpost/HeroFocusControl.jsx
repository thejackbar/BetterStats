// Hero image framing — drag the photo to reposition it in the template's crop
// window, and zoom in on the part that matters.
//
// The crop editor (ImageEditorModal) runs BEFORE the image reaches the post,
// in a plain square box, so a club frames it with no idea where the template
// will wash the photo dark or run names over it. This is the other half: it
// works on the mounted post, so what you drag is what you get.
//
// Props:
//   src      the image currently in the hero slot (upload, else the featured
//            player's headshot) — the control renders nothing without one
//   value    { x, y, scale } — percentages for objectPosition + a zoom factor
//   onChange (next) => void
//   aspect   the template's own crop box ratio, so the preview crops like it
import { useRef } from 'react'

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n))

export default function HeroFocusControl({ src, value, onChange, aspect = 2 / 3, defaults }) {
  const boxRef = useRef(null)
  const drag = useRef(null)
  if (!src) return null

  const v = { x: 50, y: 0, scale: 1, ...(value || {}) }
  const isDefault = defaults && v.x === defaults.x && v.y === defaults.y && v.scale === defaults.scale

  const onPointerDown = (e) => {
    const box = boxRef.current
    if (!box) return
    // Record the drag BEFORE asking for capture: setPointerCapture throws on a
    // pointer the browser no longer considers active, and losing the drag
    // origin to that would leave the pad dead with nothing to show for it.
    drag.current = { px: e.clientX, py: e.clientY, x: v.x, y: v.y, w: box.clientWidth, h: box.clientHeight }
    try { box.setPointerCapture(e.pointerId) } catch { /* drag still tracks without it */ }
  }
  const onPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    // Dragging moves the PHOTO, which is the direction a hand expects. Moving
    // the photo left shows more of its right side, which is a HIGHER
    // objectPosition percentage — hence the inversion.
    onChange({
      ...v,
      x: clamp(Math.round(d.x - ((e.clientX - d.px) / d.w) * 100), 0, 100),
      y: clamp(Math.round(d.y - ((e.clientY - d.py) / d.h) * 100), 0, 100),
    })
  }
  const endDrag = (e) => {
    drag.current = null
    const box = boxRef.current
    if (box && box.hasPointerCapture?.(e.pointerId)) box.releasePointerCapture(e.pointerId)
  }

  const pos = `${v.x}% ${v.y}%`
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Framing</label>
        {!isDefault && defaults && (
          <button onClick={() => onChange({ ...defaults })}
            className="font-mono text-[10px] text-pb-faintest hover:text-pb-text">Reset</button>
        )}
      </div>
      <div className="flex items-start gap-3">
        <div
          ref={boxRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          className="relative overflow-hidden rounded border pb-hairline bg-pb-surface2 shrink-0 cursor-grab active:cursor-grabbing touch-none"
          style={{ width: 96, aspectRatio: String(aspect) }}
          title="Drag to reposition"
        >
          <img src={src} alt="" draggable={false}
            style={{
              position: 'absolute', inset: 0, width: '100%', height: '100%',
              objectFit: 'cover', objectPosition: pos,
              ...(v.scale !== 1 ? { transform: `scale(${v.scale})`, transformOrigin: pos } : {}),
            }} />
        </div>
        <div className="flex flex-col gap-2 flex-1 min-w-0">
          <p className="text-[11px] text-pb-faintest leading-snug">Drag the photo to move it inside the post.</p>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-pb-faint uppercase w-8 shrink-0">Zoom</span>
            {/* Below 1 the photo pulls back off the edges of its box and the
                post's own background shows around it, which is the right
                answer for a cutout and a deliberate look for a photograph. */}
            <input
              type="range" min={0.5} max={2.5} step={0.05} value={v.scale}
              onChange={e => onChange({ ...v, scale: Number(e.target.value) })}
              className="flex-1 min-w-0 accent-[var(--pb-accent)]"
            />
            <span className="font-mono text-[10px] text-pb-faintest w-8 text-right shrink-0">{v.scale.toFixed(1)}×</span>
          </div>
        </div>
      </div>
    </div>
  )
}
