// Effects panel: the design tools for whatever is selected on the canvas.
//
//   picture (image block, player photo)  frame shape, pop out, frame fill and
//       outline, photo position, one-click looks, colour splash with an
//       eyedropper, black and white / duotone / tint, adjustments, outline,
//       glow, shadow, motion trail, opacity, blend, a faded copy behind
//   text   hollow, outline, shadow, 3D block, echo stack, slant, put behind a photo
//   texture (brush, splatter, …)  shuffle, density, opacity, blend
//   nothing selected   the design starters, added on top of the post
//
// Every control writes plain settings onto the block (see social/designFx.js);
// nothing is baked, so any effect can be changed or taken off later.
import { useEffect, useRef, useState } from 'react'
import { FRAMES, framePoints, LOOKS, newSeed, toHex } from '../../../../social/designFx'
import { BLANK_STARTERS, TEXTURE_SHAPES, resolveBlankColor } from '../../../../social/blank-template'

const TOKENS = ['primary', 'secondary', 'accent', 'ink', 'white', 'black']
const BLENDS = [
  ['normal', 'Normal'], ['multiply', 'Multiply'], ['screen', 'Screen'], ['overlay', 'Overlay'],
  ['soft-light', 'Soft light'], ['lighten', 'Lighten'], ['darken', 'Darken'], ['luminosity', 'Luminosity'],
]
const DESIGN_STARTERS = ['matchday', 'gameday', 'colourpop']

const Label = ({ children }) => <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">{children}</span>

function Section({ title, children, open: open0 = true, testId }) {
  const [open, setOpen] = useState(open0)
  return (
    <div className="border-b pb-hairline pb-3 mb-3" data-testid={testId}>
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-dim">{title}</span>
        <span className="text-pb-faint text-[11px]">{open ? '–' : '+'}</span>
      </button>
      {open && <div className="flex flex-col gap-2.5">{children}</div>}
    </div>
  )
}

function Slider({ label, value, min, max, step = 1, onChange, testId, suffix = '' }) {
  return (
    <label className="flex items-center gap-2">
      <span className="w-[78px] shrink-0"><Label>{label}</Label></span>
      <input type="range" min={min} max={max} step={step} value={value ?? 0} data-testid={testId}
        onChange={(e) => onChange(Number(e.target.value))} className="flex-1 min-w-0" />
      <span className="w-9 text-right font-mono text-[10px] text-pb-faint tabular-nums">{Math.round((value ?? 0) * 100) / 100}{suffix}</span>
    </label>
  )
}

function Chip({ active, onClick, children, title, testId }) {
  return (
    <button onClick={onClick} title={title} data-testid={testId}
      className={`h-7 px-2 rounded-md border text-[11px] transition-colors ${active ? 'text-pb-accent' : 'border-pb-hairline2 bg-pb-surface2 text-pb-dim hover:text-pb-text'}`}
      style={active ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
      {children}
    </button>
  )
}

function ColourPick({ value, onChange, palette, allowNone = false, testId }) {
  const shown = (t) => resolveBlankColor(t, palette)
  return (
    <span className="flex items-center gap-1 flex-wrap" data-testid={testId}>
      {allowNone && (
        <button title="None" onClick={() => onChange(null)} className="w-[22px] h-[22px] rounded-md border text-[10px] text-pb-faint"
          style={{ borderColor: !value ? 'var(--pb-accent)' : 'rgba(255,255,255,.18)', borderWidth: !value ? 2 : 1 }}>∅</button>
      )}
      {TOKENS.map((t) => (
        <button key={t} title={t} onClick={() => onChange(t)} className="w-[22px] h-[22px] rounded-md border"
          style={{ background: shown(t), borderColor: value === t ? 'var(--pb-accent)' : 'rgba(255,255,255,.18)', borderWidth: value === t ? 2 : 1 }} />
      ))}
      <input type="color" title="Custom colour" value={typeof value === 'string' && value.startsWith('#') ? value : '#ffffff'}
        onChange={(e) => onChange(e.target.value)} className="w-6 h-6 rounded-md border pb-hairline2 bg-transparent p-0 cursor-pointer" />
    </span>
  )
}

function FrameMark({ frame }) {
  const fill = 'var(--pb-dim)'
  if (frame.key === 'none') return <span className="text-[10px] text-pb-faint">—</span>
  if (frame.key === 'rounded') return <span style={{ width: 22, height: 26, background: fill, borderRadius: 5 }} />
  if (frame.brush) return <span style={{ width: 28, height: 14, background: fill, borderRadius: '40% 60% 50% 50%', transform: 'rotate(-6deg)' }} />
  const pts = framePoints(frame, 7)
  const clip = `polygon(${pts.map(([x, y]) => `${x}% ${y}%`).join(',')})`
  return <span style={{ width: 22, height: 26, background: fill, clipPath: clip }} />
}

// The original photo, small, to click a colour out of. Drawn from the block's
// own src, never the processed copy, so a colour already greyed can be picked.
function Eyedropper({ src, onPick }) {
  const ref = useRef(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    if (!src) return undefined
    let live = true
    setErr(null)
    const img = new Image()
    try { if (new URL(src, window.location.href).origin !== window.location.origin && !/^(blob:|data:)/.test(src)) img.crossOrigin = 'anonymous' } catch { /* same origin */ }
    img.onload = () => {
      if (!live || !ref.current) return
      const c = ref.current
      const k = Math.min(1, 236 / img.naturalWidth, 180 / img.naturalHeight)
      c.width = Math.max(1, Math.round(img.naturalWidth * k))
      c.height = Math.max(1, Math.round(img.naturalHeight * k))
      const ctx = c.getContext('2d', { willReadFrequently: true })
      // A chequer under a cut-out so its clear background reads as clear.
      for (let y = 0; y < c.height; y += 8) for (let x = 0; x < c.width; x += 8) { ctx.fillStyle = ((x + y) / 8) % 2 ? '#2a2d33' : '#1f2227'; ctx.fillRect(x, y, 8, 8) }
      ctx.drawImage(img, 0, 0, c.width, c.height)
      try { ctx.getImageData(0, 0, 1, 1) } catch { setErr('This picture comes from another site, so colours cannot be picked from it.') }
    }
    img.onerror = () => live && setErr('Could not load the picture.')
    img.src = src
    return () => { live = false }
  }, [src])
  if (!src) return <p className="text-[11px] text-pb-faint">Add a picture first.</p>
  return (
    <div className="flex flex-col gap-1">
      <canvas ref={ref} data-testid="fx-eyedropper" title="Click a colour to keep it"
        className="rounded-md border pb-hairline2 cursor-crosshair self-start max-w-full"
        onClick={(e) => {
          const c = ref.current
          if (!c) return
          const r = c.getBoundingClientRect()
          const x = Math.floor(((e.clientX - r.left) / r.width) * c.width)
          const y = Math.floor(((e.clientY - r.top) / r.height) * c.height)
          try {
            const d = c.getContext('2d').getImageData(x, y, 1, 1).data
            onPick(toHex([d[0], d[1], d[2]]))
          } catch { setErr('This picture comes from another site, so colours cannot be picked from it.') }
        }} />
      <span className="text-[10px] text-pb-faint">{err || 'Click the photo to keep that colour.'}</span>
    </div>
  )
}

function PictureEffects({ item, patch, palette, previewSrc, onGhost }) {
  const fx = item.fx || {}
  const setFx = (p) => patch({ fx: { ...fx, ...p } })
  const crop = item.crop || {}
  const setCrop = (p) => patch({ crop: { x: crop.x || 0, y: crop.y || 0, z: crop.z ?? 1, ...p } })
  const splash = Array.isArray(fx.splash) ? fx.splash : []
  const setSplash = (list) => setFx({ splash: list })
  const framed = item.mask && item.mask !== 'none'
  const curFrame = FRAMES.find((f) => f.key === (item.mask || 'none'))
  return (
    <>
      <Section title="Frame" testId="fx-frame">
        <div className="grid grid-cols-4 gap-1.5">
          {FRAMES.map((f) => (
            <button key={f.key} title={f.name} data-testid={`frame-${f.key}`}
              onClick={() => patch({ mask: f.key === 'none' ? null : f.key, ...(f.torn && !item.maskSeed ? { maskSeed: newSeed() } : null), ...(f.brush && !item.maskSeed ? { maskSeed: newSeed() } : null) })}
              className="aspect-square rounded-md border bg-pb-surface2 flex flex-col items-center justify-center gap-1"
              style={{ borderColor: (item.mask || 'none') === f.key ? 'var(--pb-accent)' : 'var(--pb-hairline2, rgba(255,255,255,.12))' }}>
              <span className="grid place-items-center h-7"><FrameMark frame={f} /></span>
              <span className="font-mono text-[7.5px] tracking-wide2 uppercase text-pb-faint leading-none">{f.name}</span>
            </button>
          ))}
        </div>
        {framed && (
          <>
            <Slider label="Pop out" value={Math.round((item.popOut || 0) * 100)} min={0} max={80} suffix="%" testId="fx-popout"
              onChange={(v) => patch({ popOut: v / 100 })} />
            <p className="text-[10px] text-pb-faint leading-snug -mt-1">
              Lets a cut-out's head and shoulders stand out of the top of the frame. It needs a picture with its background removed (Replace, then Edit, then Remove background).
            </p>
            {(curFrame?.torn || curFrame?.brush) && <Chip onClick={() => patch({ maskSeed: newSeed() })} testId="fx-reshuffle-frame">Shuffle the edge</Chip>}
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Fill</Label></span>
              <ColourPick value={item.frameFill || null} allowNone palette={palette} onChange={(c) => patch({ frameFill: c })} testId="fx-frame-fill" /></div>
            {item.frameFill && (
              <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Fade to</Label></span>
                <ColourPick value={item.frameFill2 || null} allowNone palette={palette} onChange={(c) => patch({ frameFill2: c })} /></div>
            )}
            {!curFrame?.brush && (
              <>
                <Slider label="Outline" value={item.frameStroke?.width || 0} min={0} max={30} testId="fx-frame-stroke"
                  onChange={(v) => patch({ frameStroke: { color: item.frameStroke?.color || 'white', width: v } })} />
                {(item.frameStroke?.width || 0) > 0 && (
                  <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Outline col</Label></span>
                    <ColourPick value={item.frameStroke?.color || 'white'} palette={palette} onChange={(c) => patch({ frameStroke: { ...item.frameStroke, color: c } })} /></div>
                )}
              </>
            )}
          </>
        )}
        <div className="flex items-center gap-2 flex-wrap">
          <Label>Photo in frame</Label>
          <span className="text-[10px] text-pb-faint">Double-click the picture on the canvas to drag it, scroll to zoom.</span>
        </div>
        <Slider label="Zoom" value={crop.z ?? 1} min={0.3} max={4} step={0.01} testId="fx-zoom" onChange={(v) => setCrop({ z: v })} />
        <Slider label="Left/right" value={crop.x || 0} min={-Math.round(item.w)} max={Math.round(item.w)} onChange={(v) => setCrop({ x: v })} />
        <Slider label="Up/down" value={crop.y || 0} min={-Math.round(item.h)} max={Math.round(item.h)} onChange={(v) => setCrop({ y: v })} />
        {item.crop && <Chip onClick={() => patch({ crop: null })}>Reset position</Chip>}
      </Section>

      <Section title="Looks" testId="fx-looks">
        <div className="grid grid-cols-2 gap-1.5">
          {LOOKS.map((l) => (
            <Chip key={l.key} testId={`look-${l.key}`} onClick={() => setFx(l.fx)}>{l.name}</Chip>
          ))}
        </div>
      </Section>

      <Section title="Colour splash" testId="fx-splash">
        <p className="text-[10px] text-pb-faint leading-snug -mt-1">Turns the photo black and white except the colours you keep. Range widens how much of each colour counts; Softness blends the edge.</p>
        <Eyedropper src={previewSrc} onPick={(c) => setSplash([...splash, { color: c, range: 24, soft: 16 }].slice(-4))} />
        <div className="flex items-center gap-1 flex-wrap">
          <Label>Or keep</Label>
          {['primary', 'secondary', 'accent'].map((t) => (
            <Chip key={t} testId={`splash-add-${t}`} onClick={() => setSplash([...splash, { color: t, range: 24, soft: 16 }].slice(-4))}>
              <span className="inline-block w-2.5 h-2.5 rounded-sm mr-1 align-middle" style={{ background: resolveBlankColor(t, palette) }} />{t}
            </Chip>
          ))}
        </div>
        {splash.map((s, i) => (
          <div key={i} className="rounded-md border pb-hairline2 p-2 flex flex-col gap-1.5" data-testid="splash-pick">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded border pb-hairline2" style={{ background: resolveBlankColor(s.color, palette) }} />
              <span className="font-mono text-[10px] text-pb-dim flex-1">{s.color}</span>
              <button className="text-[11px] text-pb-faint hover:text-pb-text" onClick={() => setSplash(splash.filter((_, j) => j !== i))}>Remove</button>
            </div>
            <Slider label="Range" value={s.range ?? 24} min={2} max={90} testId="splash-range" onChange={(v) => setSplash(splash.map((x, j) => (j === i ? { ...x, range: v } : x)))} />
            <Slider label="Softness" value={s.soft ?? 16} min={0} max={60} testId="splash-soft" onChange={(v) => setSplash(splash.map((x, j) => (j === i ? { ...x, soft: v } : x)))} />
          </div>
        ))}
        {splash.length > 0 && (
          <Slider label="Strength" value={fx.splashStrength ?? 100} min={0} max={100} suffix="%" onChange={(v) => setFx({ splashStrength: v })} />
        )}
      </Section>

      <Section title="Tone and adjust" testId="fx-tone" open={false}>
        <div className="flex gap-1 flex-wrap">
          {[['none', 'Colour'], ['mono', 'Black & white'], ['duotone', 'Duotone'], ['tint', 'Tint']].map(([k, n]) => (
            <Chip key={k} testId={`tone-${k}`} active={(fx.tone || 'none') === k} onClick={() => setFx({ tone: k, ...(k === 'duotone' && !fx.duoDark ? { duoDark: 'primary', duoLight: 'accent' } : null), ...(k === 'tint' && !fx.tint ? { tint: 'primary', tintAmount: 75 } : null) })}>{n}</Chip>
          ))}
        </div>
        {fx.tone === 'duotone' && (
          <>
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Shadows</Label></span><ColourPick value={fx.duoDark} palette={palette} onChange={(c) => setFx({ duoDark: c })} /></div>
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Highlights</Label></span><ColourPick value={fx.duoLight} palette={palette} onChange={(c) => setFx({ duoLight: c })} /></div>
          </>
        )}
        {fx.tone === 'tint' && (
          <>
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Tint</Label></span><ColourPick value={fx.tint} palette={palette} onChange={(c) => setFx({ tint: c })} /></div>
            <Slider label="Amount" value={fx.tintAmount ?? 75} min={0} max={100} suffix="%" onChange={(v) => setFx({ tintAmount: v })} />
          </>
        )}
        <Slider label="Brightness" value={fx.brightness || 0} min={-100} max={100} onChange={(v) => setFx({ brightness: v })} />
        <Slider label="Contrast" value={fx.contrast || 0} min={-100} max={100} testId="fx-contrast" onChange={(v) => setFx({ contrast: v })} />
        <Slider label="Saturation" value={fx.saturation || 0} min={-100} max={100} onChange={(v) => setFx({ saturation: v })} />
        <Slider label="Grain" value={fx.grain || 0} min={0} max={100} onChange={(v) => setFx({ grain: v })} />
      </Section>

      <Section title="Cut-out effects" testId="fx-cutout" open={false}>
        <Slider label="Outline" value={fx.outline?.width || 0} min={0} max={30} testId="fx-outline" onChange={(v) => setFx({ outline: { color: fx.outline?.color || 'white', width: v } })} />
        {(fx.outline?.width || 0) > 0 && <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Outline col</Label></span><ColourPick value={fx.outline.color} palette={palette} onChange={(c) => setFx({ outline: { ...fx.outline, color: c } })} /></div>}
        <Slider label="Glow" value={fx.glow?.size || 0} min={0} max={120} testId="fx-glow" onChange={(v) => setFx({ glow: { color: fx.glow?.color || 'accent', size: v } })} />
        {(fx.glow?.size || 0) > 0 && <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Glow col</Label></span><ColourPick value={fx.glow.color} palette={palette} onChange={(c) => setFx({ glow: { ...fx.glow, color: c } })} /></div>}
        <Slider label="Shadow" value={fx.shadow?.blur || 0} min={0} max={100} testId="fx-shadow" onChange={(v) => setFx({ shadow: { x: fx.shadow?.x ?? 0, y: fx.shadow?.y ?? 18, opacity: fx.shadow?.opacity ?? 60, color: fx.shadow?.color || 'black', blur: v } })} />
        {(fx.shadow?.blur || 0) > 0 && <Slider label="Shadow drop" value={fx.shadow.y ?? 18} min={-80} max={80} onChange={(v) => setFx({ shadow: { ...fx.shadow, y: v } })} />}
        <Slider label="Motion trail" value={fx.trail?.count || 0} min={0} max={8} testId="fx-trail" onChange={(v) => setFx({ trail: { dx: fx.trail?.dx ?? -40, dy: fx.trail?.dy ?? 0, opacity: fx.trail?.opacity ?? 55, color: fx.trail?.color ?? null, count: v } })} />
        {(fx.trail?.count || 0) > 0 && (
          <>
            <Slider label="Trail across" value={fx.trail.dx ?? -40} min={-160} max={160} onChange={(v) => setFx({ trail: { ...fx.trail, dx: v } })} />
            <Slider label="Trail down" value={fx.trail.dy ?? 0} min={-160} max={160} onChange={(v) => setFx({ trail: { ...fx.trail, dy: v } })} />
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Trail col</Label></span>
              <ColourPick value={fx.trail.color || null} allowNone palette={palette} onChange={(c) => setFx({ trail: { ...fx.trail, color: c } })} /></div>
          </>
        )}
        <Chip testId="fx-ghost" onClick={onGhost} title="A big faded copy of this picture behind it">Add faded copy behind</Chip>
      </Section>

      <Section title="Opacity and blend" open={false}>
        <BlendControls item={item} patch={patch} />
      </Section>
    </>
  )
}

function BlendControls({ item, patch }) {
  return (
    <>
      <Slider label="Opacity" value={Math.round((item.opacity ?? 1) * 100)} min={5} max={100} suffix="%" testId="fx-opacity"
        onChange={(v) => patch({ opacity: v / 100 })} />
      <label className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Blend</Label></span>
        <select value={item.blend || 'normal'} onChange={(e) => patch({ blend: e.target.value })} data-testid="fx-blend"
          className="h-7 flex-1 px-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[11px]">
          {BLENDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
        </select>
      </label>
    </>
  )
}

function TextEffects({ item, patch, palette, onTextBehind, canBehind }) {
  const echo = item.echo || null
  return (
    <>
      <Section title="Text style" testId="fx-text">
        <div className="flex gap-1 flex-wrap">
          <Chip testId="fx-hollow" active={!!item.hollow} onClick={() => patch({ hollow: !item.hollow })}>Hollow</Chip>
          <Chip testId="fx-preset-block" onClick={() => patch({ extrude: { depth: 14, angle: 45, color: 'black' }, shadow: null })}>3D block</Chip>
          <Chip testId="fx-preset-glow" onClick={() => patch({ shadow: { x: 0, y: 0, blur: 36, color: 'accent', opacity: 90 }, extrude: null })}>Glow</Chip>
          <Chip testId="fx-preset-drop" onClick={() => patch({ shadow: { x: 8, y: 8, blur: 0, color: 'black', opacity: 100 }, extrude: null })}>Hard shadow</Chip>
          <Chip onClick={() => patch({ hollow: false, stroke: null, shadow: null, extrude: null, echo: null, skew: 0 })}>Plain</Chip>
        </div>
        <Slider label="Outline" value={item.stroke?.width || 0} min={0} max={20} testId="fx-text-stroke"
          onChange={(v) => patch({ stroke: { color: item.stroke?.color || 'black', width: v } })} />
        {(item.stroke?.width || 0) > 0 && <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Outline col</Label></span>
          <ColourPick value={item.stroke.color} palette={palette} onChange={(c) => patch({ stroke: { ...item.stroke, color: c } })} /></div>}
        <Slider label="3D depth" value={item.extrude?.depth || 0} min={0} max={40} testId="fx-extrude"
          onChange={(v) => patch({ extrude: { angle: item.extrude?.angle ?? 45, color: item.extrude?.color || 'black', depth: v } })} />
        {(item.extrude?.depth || 0) > 0 && (
          <>
            <Slider label="3D angle" value={item.extrude.angle ?? 45} min={0} max={360} onChange={(v) => patch({ extrude: { ...item.extrude, angle: v } })} />
            <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>3D colour</Label></span>
              <ColourPick value={item.extrude.color} palette={palette} onChange={(c) => patch({ extrude: { ...item.extrude, color: c } })} /></div>
          </>
        )}
        <Slider label="Shadow" value={item.shadow?.blur || 0} min={0} max={80}
          onChange={(v) => patch({ shadow: { x: item.shadow?.x ?? 0, y: item.shadow?.y ?? 6, color: item.shadow?.color || 'black', opacity: item.shadow?.opacity ?? 70, blur: v } })} />
        {item.shadow && <div className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Shadow col</Label></span>
          <ColourPick value={item.shadow.color} palette={palette} onChange={(c) => patch({ shadow: { ...item.shadow, color: c } })} /></div>}
        <Slider label="Slant" value={item.skew || 0} min={-30} max={30} suffix="°" testId="fx-skew" onChange={(v) => patch({ skew: v })} />
      </Section>
      <Section title="Echo stack" testId="fx-echo">
        <p className="text-[10px] text-pb-faint leading-snug -mt-1">Repeats the words down the post, one copy filled and the rest outlined.</p>
        <Slider label="Copies" value={echo?.count || 1} min={1} max={10} testId="fx-echo-count"
          onChange={(v) => patch({ echo: v > 1 ? { step: echo?.step ?? 0.82, filled: echo?.filled || 'middle', fade: echo?.fade ?? true, count: v } : null })} />
        {echo && (
          <>
            <Slider label="Spacing" value={echo.step ?? 0.82} min={0.3} max={1.6} step={0.01} onChange={(v) => patch({ echo: { ...echo, step: v } })} />
            <div className="flex gap-1 flex-wrap">
              <Label>Filled</Label>
              {[['first', 'Top'], ['middle', 'Middle'], ['last', 'Bottom'], ['all', 'All'], ['none', 'None']].map(([k, n]) => (
                <Chip key={k} active={(echo.filled || 'middle') === k} onClick={() => patch({ echo: { ...echo, filled: k } })}>{n}</Chip>
              ))}
            </div>
            <Chip active={!!echo.fade} onClick={() => patch({ echo: { ...echo, fade: !echo.fade } })}>Fade the copies</Chip>
          </>
        )}
      </Section>
      <Section title="Layering" open>
        <Chip testId="fx-text-behind" onClick={onTextBehind} title={canBehind ? 'Move this text under the picture it overlaps, so the player stands in front of the words' : 'Put the text over a picture first'}>
          Put behind the photo
        </Chip>
        <BlendControls item={item} patch={patch} />
      </Section>
    </>
  )
}

function TextureEffects({ item, patch }) {
  return (
    <Section title="Texture" testId="fx-texture">
      {item.shape === 'halftone'
        ? <Slider label="Dot size" value={item.dot || 22} min={6} max={80} onChange={(v) => patch({ dot: v })} />
        : <Chip testId="fx-shuffle" onClick={() => patch({ seed: newSeed() })}>Shuffle</Chip>}
      <Slider label="Opacity" value={Math.round((item.opacity ?? 1) * 100)} min={5} max={100} suffix="%" onChange={(v) => patch({ opacity: v / 100 })} />
      <label className="flex items-center gap-2"><span className="w-[78px] shrink-0"><Label>Blend</Label></span>
        <select value={item.blend || 'normal'} onChange={(e) => patch({ blend: e.target.value })}
          className="h-7 flex-1 px-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[11px]">
          {BLENDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
        </select>
      </label>
      <p className="text-[10px] text-pb-faint">Colour, size and rotation are on the bar under the canvas.</p>
    </Section>
  )
}

export default function EffectsPanel({ item, selCount = 0, palette, onPatch, previewSrc, onGhost, onTextBehind, canBehind, onAddStarter }) {
  const isPicture = item && (item.type === 'image' || (item.type === 'data' && item.kind === 'playerphoto')) && !item.design
  return (
    <div data-testid="effects-panel" className="flex flex-col">
      {!item && (
        <>
          <p className="text-[11px] text-pb-dim leading-relaxed mb-3">
            {selCount > 1 ? 'Select one thing at a time to give it effects.' : 'Select a photo, some text or a texture on the canvas to style it. Or start from a design:'}
          </p>
          {selCount <= 1 && (
            <div className="grid grid-cols-1 gap-1.5">
              {BLANK_STARTERS.filter((s) => DESIGN_STARTERS.includes(s.key)).map((s) => (
                <button key={s.key} data-testid={`starter-${s.key}`} onClick={() => onAddStarter(s.key)}
                  className="h-10 px-3 rounded-md border pb-hairline2 bg-pb-surface2 text-left text-[12px] text-pb-text hover:border-pb-accent">
                  {s.name} <span className="text-pb-faint text-[10px]">· adds its blocks on top</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {isPicture && <PictureEffects item={item} patch={onPatch} palette={palette} previewSrc={previewSrc} onGhost={onGhost} />}
      {item && item.type === 'text' && <TextEffects item={item} patch={onPatch} palette={palette} onTextBehind={onTextBehind} canBehind={canBehind} />}
      {item && item.type === 'element' && TEXTURE_SHAPES.has(item.shape) && <TextureEffects item={item} patch={onPatch} />}
      {item && item.type === 'element' && !TEXTURE_SHAPES.has(item.shape) && (
        <Section title="Shape"><BlendControls item={item} patch={onPatch} /></Section>
      )}
      {item && item.design && <p className="text-[11px] text-pb-dim">Your uploaded design is the post's background. Effects are for the photos, text and textures on top of it.</p>}
      {item && !isPicture && !['text', 'element'].includes(item.type) && !item.design && (
        <p className="text-[11px] text-pb-dim">This block has no effects. Select a photo, text or a texture.</p>
      )}
    </div>
  )
}
