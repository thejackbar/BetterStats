// A picture drawn inside a frame, with its look and cut-out effects.
//
// Layers, back to front, inside a box that is `lift` px taller than the frame at
// the top (the room a head needs to pop out of it):
//   frame fill → motion trail → [ photo clipped to the frame → frame outline →
//   the same photo clipped to everything above the pop line ] (the bracketed
//   group carries the outline / glow / shadow filter)
// The pop layer is what puts a cut-out player "in" a triangle with their head
// and shoulders standing out of it. It only shows anything on a cut-out (a
// picture with a clear background); on a plain photo it shows the photo.
//
// A block with none of these settings renders exactly as it always did (the
// caller checks `hasImageDesign` first), so saved posts are unchanged.
import { frameOf, framePoints, frameClip, brushMaskUrl, useFxSrc, resolveFx, cutoutFilter, needsPixels } from './designFx'

export function hasImageDesign(it) {
  if (!it) return false
  const fx = it.fx || {}
  return !!(
    (it.mask && it.mask !== 'none') || it.crop || needsPixels(fx) ||
    (fx.outline && fx.outline.width > 0) || (fx.glow && fx.glow.size > 0) ||
    (fx.shadow && (fx.shadow.blur > 0 || fx.shadow.x || fx.shadow.y)) ||
    (fx.trail && fx.trail.count > 0) || it.frameFill || (it.frameStroke && it.frameStroke.width > 0)
  )
}

const MONO = "'JetBrains Mono', monospace"

export default function FramedImage({ item, src, resolve, placeholder = null, defaultFit = 'contain' }) {
  const w = item.w
  const h = item.h
  const frame = item.mask && item.mask !== 'none' ? frameOf(item.mask) : null
  const pts = frame ? framePoints(frame, item.maskSeed) : null
  const popOut = frame && src ? Math.max(0, Math.min(1, item.popOut || 0)) : 0
  const lift = Math.round(h * popOut)
  const total = h + lift
  const fx = item.fx || {}
  const fxr = resolveFx(fx, resolve)
  const { url } = useFxSrc(src, fxr)
  const trail = fx.trail && fx.trail.count > 0 ? fx.trail : null
  const silFx = trail && trail.color ? { silhouette: resolve(trail.color) } : null
  const { url: silUrl } = useFxSrc(silFx ? src : null, silFx)
  const crop = item.crop || {}
  const z = crop.z ?? 1
  const cx = crop.x || 0
  const cy = crop.y || 0
  const radius = item.radius || 0

  // How the frame itself clips, in the coordinates of the taller box.
  let clip
  let mask = null
  let rounded = null
  if (frame && frame.brush) {
    mask = {
      WebkitMaskImage: brushMaskUrl(item.maskSeed || 3), maskImage: brushMaskUrl(item.maskSeed || 3),
      WebkitMaskSize: `100% ${h}px`, maskSize: `100% ${h}px`,
      WebkitMaskPosition: `0 ${lift}px`, maskPosition: `0 ${lift}px`,
      WebkitMaskRepeat: 'no-repeat', maskRepeat: 'no-repeat',
    }
  } else if (pts) {
    clip = frameClip(pts, h, lift)
  } else {
    const r = frame && frame.key === 'rounded' ? Math.max(radius, Math.round(Math.min(w, h) * 0.12)) : radius
    rounded = r
    clip = lift || r ? `inset(${lift}px 0 0 0 round ${r}px)` : undefined
  }
  const clipStyle = { clipPath: clip, WebkitClipPath: clip, ...(mask || null) }
  const popLineY = frame ? lift + Math.round((frame.pop || 0) * h) : 0
  const popClip = `polygon(0 0, 100% 0, 100% ${popLineY}px, 0 ${popLineY}px)`

  const img = (u, extra = null) => (
    <img src={u} alt="" draggable={false} style={{
      position: 'absolute', left: 0, top: 0, width: '100%', height: '100%',
      objectFit: item.fit || defaultFit, display: 'block', pointerEvents: 'none',
      transform: z !== 1 || cx || cy ? `translate(${cx}px, ${cy}px) scale(${z})` : undefined,
      transformOrigin: 'center center',
      ...extra,
    }} />
  )

  const fill = item.frameFill ? resolve(item.frameFill) : null
  const fill2 = item.frameFill2 ? resolve(item.frameFill2) : null
  const fillBg = fill ? (fill2 ? `linear-gradient(${item.frameFillAngle ?? 160}deg, ${fill}, ${fill2})` : fill) : null
  const stroke = item.frameStroke && item.frameStroke.width > 0 ? item.frameStroke : null
  const strokeColor = stroke ? resolve(stroke.color || 'white') : null
  const filter = cutoutFilter(fx, resolve)

  const fillLayer = fillBg ? (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: total, background: fillBg, ...clipStyle }} />
  ) : null

  // Empty: show the frame so the person sees the shape they are filling.
  if (!src) {
    const ph = fillBg || `${resolve('ink')}1f`
    return (
      <div style={{ width: w, height: h, position: 'relative' }}>
        <div style={{
          position: 'absolute', inset: 0, background: ph, ...clipStyle,
          display: 'grid', placeItems: 'center', fontFamily: MONO, fontSize: 22, letterSpacing: 2,
          color: `${resolve('ink')}aa`, textAlign: 'center', padding: 16,
        }}>{placeholder || 'ADD IMAGE'}</div>
        {stroke && <FrameStroke pts={pts} frame={frame} rounded={rounded} w={w} h={h} top={0} color={strokeColor} width={stroke.width} />}
      </div>
    )
  }

  const shown = url || src
  return (
    <div style={{ width: w, height: h, position: 'relative' }}>
      <div style={{ position: 'absolute', left: 0, top: -lift, width: w, height: total }}>
        {fillLayer}
        {trail && Array.from({ length: Math.min(8, trail.count) }, (_, k) => {
          const i = Math.min(8, trail.count) - k
          const op = Math.max(0.04, (trail.opacity ?? 55) / 100 * Math.pow(0.72, i - 1))
          return (
            <div key={i} style={{ position: 'absolute', inset: 0, ...clipStyle, transform: `translate(${(trail.dx ?? -40) * i}px, ${(trail.dy ?? 0) * i}px)`, opacity: op }}>
              {img(silUrl || shown)}
            </div>
          )
        })}
        <div style={{ position: 'absolute', inset: 0, filter }}>
          <div style={{ position: 'absolute', inset: 0, ...clipStyle }}>{img(shown)}</div>
          {stroke && <FrameStroke pts={pts} frame={frame} rounded={rounded} w={w} h={h} top={lift} color={strokeColor} width={stroke.width} />}
          {popOut > 0 && (
            <div data-pop-out="" style={{ position: 'absolute', inset: 0, clipPath: popClip, WebkitClipPath: popClip }}>{img(shown)}</div>
          )}
        </div>
      </div>
    </div>
  )
}

function FrameStroke({ pts, frame, rounded, w, h, top, color, width }) {
  if (frame && frame.brush) return null
  if (!pts) {
    return <div style={{ position: 'absolute', left: 0, top, width: w, height: h, boxSizing: 'border-box', border: `${width}px solid ${color}`, borderRadius: rounded || 0, pointerEvents: 'none' }} />
  }
  return (
    <svg width={w} height={h} viewBox="0 0 100 100" preserveAspectRatio="none"
      style={{ position: 'absolute', left: 0, top, overflow: 'visible', pointerEvents: 'none' }}>
      <polygon points={pts.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke={color}
        strokeWidth={width} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}
