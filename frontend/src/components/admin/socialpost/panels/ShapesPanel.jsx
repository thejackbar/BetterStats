// Shapes panel — a 3-col grid of the decorative elements, each drawn as a real
// mark. Adds an element block via onAdd('element', { shape }).
import { BLANK_ELEMENTS } from '../../../../social/blank-template'
import { TEXTURES, halftoneDots } from '../../../../social/designFx'

const CLIP = {
  star: 'polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)',
  arrow: 'polygon(0% 30%, 60% 30%, 60% 10%, 100% 50%, 60% 90%, 60% 70%, 0% 70%)',
  chevron: 'polygon(0% 0%, 50% 0%, 100% 50%, 50% 100%, 0% 100%, 50% 50%)',
  diamond: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
  hexagon: 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)',
  triangle: 'polygon(50% 0, 100% 100%, 0 100%)',
}

function Mark({ shape }) {
  const fill = 'var(--pb-dim)'
  if (shape === 'line' || shape === 'divider') return <span style={{ width: 28, height: 4, background: fill, borderRadius: 2 }} />
  if (shape === 'rect') return <span style={{ width: 26, height: 18, background: fill, borderRadius: 2 }} />
  if (shape === 'ellipse') return <span style={{ width: 22, height: 22, background: fill, borderRadius: '50%' }} />
  return <span style={{ width: 24, height: 22, background: fill, clipPath: CLIP[shape] || 'none' }} />
}

const Tile = ({ el, onAdd }) => (
  <button onClick={() => onAdd('element', { shape: el.shape })} title={el.name} data-testid={`shape-${el.shape}`}
    className="aspect-square rounded-lg border pb-hairline bg-pb-surface2 hover:border-pb-accent transition-colors flex flex-col items-center justify-center gap-2">
    <span className="grid place-items-center h-6">{el.texture ? <TextureMark shape={el.shape} /> : <Mark shape={el.shape} />}</span>
    <span className="font-mono text-[8px] tracking-wide2 uppercase text-pb-faint text-center leading-tight px-1">{el.name}</span>
  </button>
)

// A tiny drawing of each texture, from the same generator the canvas uses.
function TextureMark({ shape }) {
  if (shape === 'halftone') {
    return <svg width="30" height="22" viewBox="0 0 30 22">{halftoneDots(30, 22, 6).map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} fill="var(--pb-dim)" />)}</svg>
  }
  const make = TEXTURES[shape]
  const w = shape === 'splatter' || shape === 'burst' || shape === 'grunge' ? 24 : 34
  const h = shape === 'splatter' || shape === 'burst' || shape === 'grunge' ? 24 : 14
  const paths = make ? make(w, h, 5) : []
  return <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'hidden' }}>{paths.map((p, i) => <path key={i} d={p.d} fill="var(--pb-dim)" fillOpacity={p.opacity} />)}</svg>
}

export default function ShapesPanel({ onAdd }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        {BLANK_ELEMENTS.filter((el) => !el.texture).map((el) => <Tile key={el.shape} el={el} onAdd={onAdd} />)}
      </div>
      <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Textures</span>
      <div className="grid grid-cols-3 gap-2">
        {BLANK_ELEMENTS.filter((el) => el.texture).map((el) => <Tile key={el.shape} el={el} onAdd={onAdd} />)}
      </div>
      <p className="text-[10px] text-pb-faint leading-snug">Textures take the club's colours. Shuffle one, or set its blend, in Effects.</p>
    </div>
  )
}
