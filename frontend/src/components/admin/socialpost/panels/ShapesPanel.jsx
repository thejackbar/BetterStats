// Shapes panel — a 3-col grid of the decorative elements, each drawn as a real
// mark. Adds an element block via onAdd('element', { shape }).
import { BLANK_ELEMENTS } from '../../../../social/blank-template'

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

export default function ShapesPanel({ onAdd }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {BLANK_ELEMENTS.map((el) => (
        <button key={el.shape} onClick={() => onAdd('element', { shape: el.shape })} title={el.name}
          className="aspect-square rounded-lg border pb-hairline bg-pb-surface2 hover:border-pb-accent transition-colors flex flex-col items-center justify-center gap-2">
          <span className="grid place-items-center h-6"><Mark shape={el.shape} /></span>
          <span className="font-mono text-[8px] tracking-wide2 uppercase text-pb-faint">{el.name}</span>
        </button>
      ))}
    </div>
  )
}
