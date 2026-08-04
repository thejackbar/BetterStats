import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { scoreLine } from '../aflApi'

export const displayName = (row) => row.display_name_override || row.name || 'Unknown'

export function SectionTitle({ children, right }) {
  return (
    <div className="flex items-end justify-between mb-3">
      <h2 className="font-mono text-xs uppercase tracking-wide3 text-pb-faint">{children}</h2>
      {right}
    </div>
  )
}

export function Select({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value || null)}
      className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm text-pb-text"
    >
      {placeholder != null && <option value="">{placeholder}</option>}
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

export function ResultPill({ result }) {
  if (!result) return null
  const label = { W: 'WIN', L: 'LOSS', D: 'DRAW' }[result] || result
  return (
    <span className={clsx(
      'font-mono text-[10px] font-bold px-1.5 py-0.5 rounded',
      result === 'W' && 'bg-[color-mix(in_srgb,var(--pb-positive)_18%,transparent)] text-[var(--pb-positive)]',
      result === 'L' && 'bg-[color-mix(in_srgb,var(--pb-negative)_18%,transparent)] text-[var(--pb-negative)]',
      result === 'D' && 'bg-pb-surface2 text-pb-dim',
    )}>
      {label}
    </span>
  )
}

/** One result row — used by the dashboard, the games list and profiles. */
export function GameRow({ game, base }) {
  const ourSide = game.our_side
  const homeIsUs = ourSide === 'HOME'
  return (
    <Link
      to={`${base}/games/${game.id}`}
      className="pb-card p-3 flex flex-wrap items-center gap-x-4 gap-y-1 hover:border-[var(--pb-accent)] transition-colors"
    >
      <div className="w-28 shrink-0">
        <div className="text-[11px] text-pb-faint font-mono">{game.round_name || (game.is_final ? 'Final' : '')}</div>
        <div className="text-[11px] text-pb-faintest font-mono">{game.played_at || ''}</div>
      </div>
      <div className="flex-1 min-w-[200px]">
        <div className={clsx('text-sm', homeIsUs ? 'font-semibold text-pb-text' : 'text-pb-dim')}>
          {game.home_team} <span className="pb-num float-right">{scoreLine(game.home_goals, game.home_behinds, game.home_score)}</span>
        </div>
        <div className={clsx('text-sm', !homeIsUs && ourSide ? 'font-semibold text-pb-text' : 'text-pb-dim')}>
          {game.away_team} <span className="pb-num float-right">{scoreLine(game.away_goals, game.away_behinds, game.away_score)}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-[11px] text-pb-faint hidden sm:block">{game.grade_name}</span>
        <ResultPill result={game.result} />
      </div>
    </Link>
  )
}

export function PlayerCell({ id, name, base, photoUrl }) {
  const body = (
    <span className="flex items-center gap-2 min-w-0">
      {photoUrl
        ? <img src={photoUrl} alt="" className="h-6 w-6 rounded-full object-cover" />
        : <span className="h-6 w-6 rounded-full bg-pb-surface2 text-[10px] flex items-center justify-center text-pb-faint">
            {(name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
          </span>}
      <span className="truncate">{name}</span>
    </span>
  )
  if (!id) return body
  return <Link to={`${base}/players/${id}`} className="hover:text-[var(--pb-accent)]">{body}</Link>
}
