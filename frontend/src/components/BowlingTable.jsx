import { useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'

export default function BowlingTable({ spells = [], showPlayer = false }) {
  const [sort, setSort] = useState({ key: 'wickets', dir: 'desc' })

  const sorted = [...spells].sort((a, b) => {
    const va = a[sort.key] ?? -1
    const vb = b[sort.key] ?? -1
    return sort.dir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
  })

  const toggle = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }))

  const SortIcon = ({ colKey }) => {
    if (sort.key !== colKey) return <span className="text-pb-faintest ml-1">↕</span>
    return <span className="ml-1" style={{ color: 'var(--pb-accent)' }}>{sort.dir === 'asc' ? '↑' : '↓'}</span>
  }

  if (spells.length === 0) {
    return <p className="font-mono text-[11px] text-pb-faint py-6 text-center">No bowling spells recorded.</p>
  }

  const cols = [
    { key: 'overs', label: 'O', sortable: true },
    { key: 'maidens', label: 'M', sortable: true },
    { key: 'runs', label: 'R', sortable: true },
    { key: 'wickets', label: 'W', sortable: true },
    { key: 'economy', label: 'Econ', sortable: true },
    { key: 'wides', label: 'Wd', sortable: false },
    { key: 'no_balls', label: 'NB', sortable: false },
  ]

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 bg-pb-surface2/40">
            {showPlayer && <th className="font-medium py-2.5 pl-4">PLAYER</th>}
            <th className="font-medium py-2.5 px-3 cursor-pointer hover:text-pb-text select-none" onClick={() => toggle('played_at')}>
              DATE<SortIcon colKey="played_at" />
            </th>
            <th className="font-medium py-2.5 px-3">MATCH</th>
            <th className="font-medium py-2.5 px-3">GRADE</th>
            {cols.map(col => (
              <th
                key={col.key}
                className={clsx('font-medium py-2.5 px-3', col.sortable && 'cursor-pointer hover:text-pb-text select-none')}
                onClick={col.sortable ? () => toggle(col.key) : undefined}
              >
                {col.label}{col.sortable && <SortIcon colKey={col.key} />}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => {
            const dateStr = row.played_at ? new Date(row.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'
            const match = row.home_team && row.away_team
              ? `${row.home_team} vs ${row.away_team}`
              : (row.home_team || row.away_team || '—')
            return (
              <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                {showPlayer && (
                  <td className="py-2.5 pl-4 text-sm">
                    <Link to={`/players/${row.player_id}`} className="font-medium hover:underline" style={{ color: 'var(--pb-accent)' }}>
                      {row.player_name}
                    </Link>
                  </td>
                )}
                <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faint whitespace-nowrap">
                  {row.game_id
                    ? <Link to={`/games/${row.game_id}/scorecard`} className="hover:text-pb-accent transition-colors">{dateStr}</Link>
                    : dateStr}
                </td>
                <td className="py-2.5 px-3 font-mono text-[11px] text-pb-dim max-w-[180px] truncate">{match}</td>
                <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faint">{row.grade_name || '—'}</td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-dim">{row.overs ?? '—'}</td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-dim">{row.maidens ?? '—'}</td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-dim">{row.runs ?? '—'}</td>
                <td className="py-2.5 px-3">
                  <span className={clsx(
                    'font-mono font-bold text-sm',
                    row.wickets >= 5 ? 'text-pb-amber' : row.wickets >= 3 ? 'text-pb-accent' : 'text-pb-text'
                  )}
                  style={row.wickets >= 3 && row.wickets < 5 ? { color: 'var(--pb-accent)' } : {}}
                  >
                    {row.wickets ?? '—'}
                  </span>
                </td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-dim">
                  {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
                </td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-faint">{row.wides ?? '—'}</td>
                <td className="py-2.5 px-3 font-mono text-sm text-pb-faint">{row.no_balls ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
