import { useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'

const COLS = [
  { key: 'played_at', label: 'Date', fmt: v => v ? new Date(v).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—' },
  { key: 'opponent', label: 'Opponent', fmt: (_, row) => row.home_team && row.away_team ? '—' : '—' },
  { key: 'runs', label: 'Runs', sortable: true },
  { key: 'balls', label: 'Balls', sortable: true },
  { key: 'fours', label: '4s', sortable: true },
  { key: 'sixes', label: '6s', sortable: true },
  { key: 'strike_rate', label: 'SR', sortable: true, fmt: v => v != null ? Number(v).toFixed(1) : '—' },
  { key: 'dismissal_type', label: 'Dismissal', fmt: v => v || '—' },
]

export default function BattingTable({ innings = [], showPlayer = false }) {
  const [sort, setSort] = useState({ key: 'played_at', dir: 'desc' })

  const sorted = [...innings].sort((a, b) => {
    const va = a[sort.key] ?? -1
    const vb = b[sort.key] ?? -1
    return sort.dir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
  })

  const toggle = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }))

  const SortIcon = ({ colKey }) => {
    if (sort.key !== colKey) return <span className="text-slate-700 ml-1">↕</span>
    return <span className="text-accent ml-1">{sort.dir === 'asc' ? '↑' : '↓'}</span>
  }

  if (innings.length === 0) {
    return <p className="text-slate-500 text-sm py-6 text-center">No batting innings recorded.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-navy-700">
            {showPlayer && <th className="table-header">Player</th>}
            {COLS.map(col => (
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
              <td className="table-cell">
                <span className={clsx(
                  'stat-number font-bold',
                  row.runs >= 100 ? 'text-amber-cricket' : row.runs >= 50 ? 'text-accent' : 'text-white'
                )}>
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="text-accent text-xs ml-0.5">*</span>}
              </td>
              <td className="table-cell stat-number text-slate-300">{row.balls ?? '—'}</td>
              <td className="table-cell stat-number text-slate-300">{row.fours ?? '—'}</td>
              <td className="table-cell stat-number text-slate-300">{row.sixes ?? '—'}</td>
              <td className="table-cell stat-number text-slate-300">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
              <td className="table-cell text-slate-400 text-xs capitalize">
                {row.dismissal_type || (row.not_out ? 'not out' : '—')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
