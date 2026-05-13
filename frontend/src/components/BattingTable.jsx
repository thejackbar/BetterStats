import { useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'

const COLS = [
  { key: 'played_at', label: 'Date', fmt: v => v ? new Date(v).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—' },
  { key: 'grade_name', label: 'Grade' },
  { key: 'runs', label: 'Runs', sortable: true },
  { key: 'balls', label: 'B', sortable: true },
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
    if (sort.key !== colKey) return <span className="text-pb-faintest ml-1">↕</span>
    return <span className="ml-1" style={{ color: 'var(--pb-accent)' }}>{sort.dir === 'asc' ? '↑' : '↓'}</span>
  }

  if (innings.length === 0) {
    return <p className="font-mono text-[11px] text-pb-faint py-6 text-center">No batting innings recorded.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 bg-pb-surface2/40">
            {showPlayer && <th className="font-medium py-2.5 pl-4">PLAYER</th>}
            {COLS.map(col => (
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
          {sorted.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              {showPlayer && (
                <td className="py-2.5 pl-4 text-sm">
                  <Link to={`/players/${row.player_id}`} className="font-medium hover:underline" style={{ color: 'var(--pb-accent)' }}>
                    {row.player_name}
                  </Link>
                </td>
              )}
              <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faint">
                {row.played_at ? new Date(row.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'}
              </td>
              <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faint">{row.grade_name || '—'}</td>
              <td className="py-2.5 px-3">
                <span className={clsx('font-mono font-bold text-sm')}
                  style={{ color: row.runs >= 100 ? 'var(--pb-amber)' : row.runs >= 50 ? 'var(--pb-accent)' : undefined }}
                >
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="font-mono text-[11px] ml-0.5" style={{ color: 'var(--pb-accent)' }}>*</span>}
              </td>
              <td className="py-2.5 px-3 font-mono text-sm text-pb-dim">{row.balls ?? '—'}</td>
              <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faint capitalize">
                {row.dismissal_type || (row.not_out ? 'not out' : '—')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
