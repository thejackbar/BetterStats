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
    if (sort.key !== colKey) return <span className="text-slate-700 ml-1">↕</span>
    return <span className="text-accent ml-1">{sort.dir === 'asc' ? '↑' : '↓'}</span>
  }

  if (spells.length === 0) {
    return <p className="text-slate-500 text-sm py-6 text-center">No bowling spells recorded.</p>
  }

  const cols = [
    { key: 'played_at', label: 'Date', sortable: false },
    { key: 'grade_name', label: 'Grade', sortable: false },
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
          <tr className="border-b border-navy-700">
            {showPlayer && <th className="table-header">Player</th>}
            {cols.map(col => (
              <th
                key={col.key}
                className={clsx('table-header', col.sortable && 'cursor-pointer hover:text-white select-none')}
                onClick={col.sortable ? () => toggle(col.key) : undefined}
              >
                {col.label}{col.sortable && <SortIcon colKey={col.key} />}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i} className="table-row">
              {showPlayer && (
                <td className="table-cell">
                  <Link to={`/players/${row.player_id}`} className="text-accent hover:underline font-medium">
                    {row.player_name}
                  </Link>
                </td>
              )}
              <td className="table-cell text-slate-400 text-xs">
                {row.played_at ? new Date(row.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'}
              </td>
              <td className="table-cell text-xs text-slate-400">{row.grade_name || '—'}</td>
              <td className="table-cell stat-number text-slate-300">{row.overs ?? '—'}</td>
              <td className="table-cell stat-number text-slate-300">{row.maidens ?? '—'}</td>
              <td className="table-cell stat-number text-slate-300">{row.runs ?? '—'}</td>
              <td className="table-cell">
                <span className={clsx(
                  'stat-number font-bold',
                  row.wickets >= 5 ? 'text-amber-cricket' : row.wickets >= 3 ? 'text-accent' : 'text-white'
                )}>
                  {row.wickets ?? '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-slate-300">
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="table-cell stat-number text-slate-400">{row.wides ?? '—'}</td>
              <td className="table-cell stat-number text-slate-400">{row.no_balls ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
