import { Link } from 'react-router-dom'

// The dashboard's major-sponsor slot. One sponsor draws large; several share
// the slot in a grid whose logos shrink as the count grows. Nothing renders when
// no sponsor is placed here, so a club without a major partner keeps the plain
// header. A signed-in club admin sees a small prompt instead, so the empty slot
// has a way in.
const GRID = {
  1: { cols: 1, logo: 'max-h-20 max-w-[300px]' },
  2: { cols: 2, logo: 'max-h-16 max-w-[170px]' },
  3: { cols: 3, logo: 'max-h-12 max-w-[110px]' },
  4: { cols: 2, logo: 'max-h-12 max-w-[170px]' },
}
const MANY = { cols: 3, logo: 'max-h-10 max-w-[110px]' }

export default function MajorSponsorSlot({ sponsors, label, canManage }) {
  if (!sponsors || sponsors.length === 0) {
    if (!canManage) return null
    return (
      <Link
        to="/admin/sponsors"
        className="block w-full rounded border border-dashed pb-hairline px-4 py-3 text-center font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text hover:border-pb-accent transition"
      >
        Add a major sponsor
      </Link>
    )
  }
  const layout = GRID[sponsors.length] || MANY
  return (
    <div className="pb-card w-full px-4 py-3" data-testid="major-sponsor-slot">
      <div className="font-mono text-[9px] tracking-wide2 text-pb-faint uppercase text-center mb-2">
        {label || 'Major Partners'}
      </div>
      <div
        className="grid items-center justify-items-center gap-x-5 gap-y-3"
        style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))` }}
      >
        {sponsors.map((s) => {
          const img = (
            <img
              src={s.logo_url}
              alt={s.name}
              className={`${layout.logo} w-auto h-auto object-contain`}
              loading="lazy"
            />
          )
          return s.website_url ? (
            <a
              key={s.id}
              href={s.website_url}
              target="_blank"
              rel="noopener noreferrer"
              title={s.name}
              className="flex items-center justify-center min-w-0 hover:opacity-90 transition-opacity"
            >
              {img}
            </a>
          ) : (
            <span key={s.id} title={s.name} className="flex items-center justify-center min-w-0">{img}</span>
          )
        })}
      </div>
    </div>
  )
}
