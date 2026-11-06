import { usePC } from './context'

// The title strip every screen opens with: the name of the screen in the club's display font, a line under it, and the
// screen's own actions on the right.
export default function PageHead({ title, sub, actions }) {
  const { display } = usePC()
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div className="min-w-0">
        <h1 data-page-title style={{ font: `800 italic clamp(28px, 5vw, 40px)/1 ${display}`, textTransform: 'uppercase', letterSpacing: '0.01em', margin: 0 }}>{title}</h1>
        {sub && <p className="text-pb-dim text-sm mt-1.5 max-w-prose">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export const ghostBtn = { padding: '9px 16px', borderRadius: 10, border: '1px solid var(--pb-hairline, rgba(255,255,255,.25))', fontWeight: 700, fontSize: 13 }
