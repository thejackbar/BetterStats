import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { nameSortKey } from '../../lib/nameFormat'
import { PlayerCell, displayName } from '../components/bits'

const COLS = [
  { key: 'games', label: 'GP' },
  { key: 'goals', label: 'Goals' },
  { key: 'bogs', label: 'BOG' },
  { key: 'seasons', label: 'Seasons' },
]

// Games-played bands — the club-milestone brackets a club actually talks in
// ("the 100-gamers", "the 200 club"), not an even numeric split.
const BANDS = [
  { key: 'all', label: 'All' },
  { key: '1', label: '1–99', min: 1, max: 99 },
  { key: '100', label: '100–199', min: 100, max: 199 },
  { key: '200', label: '200–299', min: 200, max: 299 },
  { key: '300', label: '300–399', min: 300, max: 399 },
  { key: '400', label: '400+', min: 400 },
]

const inBand = (p, band) => {
  if (band.min == null) return true
  const g = p.games ?? 0
  return g >= band.min && (band.max == null || g <= band.max)
}

export default function Players() {
  const { club } = useOutletContext()
  const [players, setPlayers] = useState(null)
  const [search, setSearch] = useState('')
  const [band, setBand] = useState('all')
  // Surname, A→Z by default. A roster is something you look a name up in, so
  // alphabetical beats "most games" as the resting state; every stat column
  // still sorts on a click.
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' })
  const base = `/${club.slug}`

  useEffect(() => {
    aflApi.listPlayers(club.id).then(d => setPlayers(d.players))
  }, [club.id])

  // Counts come off the unfiltered roster so the buttons keep saying how many
  // players are in each band regardless of what's currently selected — and a
  // band nobody has reached can be shown as unreachable rather than as a
  // button that empties the table.
  const bandCounts = useMemo(() => {
    const counts = {}
    for (const b of BANDS) counts[b.key] = (players || []).filter(p => inBand(p, b)).length
    return counts
  }, [players])

  const rows = useMemo(() => {
    if (!players) return []
    const q = search.trim().toLowerCase()
    const active = BANDS.find(b => b.key === band) || BANDS[0]
    let out = players.filter(p => inBand(p, active))
    if (q) out = out.filter(p => displayName(p).toLowerCase().includes(q))
    out.sort((a, b) => {
      if (sort.key === 'name') {
        // nameSortKey is the shared surname-first key (lib/nameFormat), so a
        // stored "Last, First" and a plain "First Last" both sort by surname.
        const cmp = nameSortKey(displayName(a)).localeCompare(nameSortKey(displayName(b)))
        return sort.dir === 'desc' ? -cmp : cmp
      }
      const av = a[sort.key] ?? 0, bv = b[sort.key] ?? 0
      return sort.dir === 'desc' ? bv - av : av - bv
    })
    return out
  }, [players, search, band, sort])

  if (players === null) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  // A stat column opens on its biggest value, the name column on A→Z, which
  // is the useful first click for each.
  const toggle = (key, firstDir) => setSort(s => (
    s.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: firstDir }
  ))
  const arrow = (key) => (sort.key === key ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : '')

  const header = (col) => (
    <th
      key={col.key}
      onClick={() => toggle(col.key, 'desc')}
      className={clsx(
        'px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide cursor-pointer select-none',
        sort.key === col.key ? 'text-[var(--pb-accent)]' : 'text-pb-faint',
      )}
    >
      {col.label}{arrow(col.key)}
    </th>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Players</h1>
        <span className="text-sm text-pb-faint">{rows.length} of {players.length}</span>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search players…"
          className="ml-auto bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm w-56"
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {BANDS.map(b => {
          const count = bandCounts[b.key] || 0
          const empty = count === 0 && b.key !== 'all'
          return (
            <button
              key={b.key}
              onClick={() => setBand(b.key)}
              disabled={empty}
              className={clsx(
                'px-3 py-1.5 rounded text-sm font-medium',
                band === b.key
                  ? 'bg-[var(--pb-accent)] text-black'
                  : 'bg-pb-surface2 text-pb-dim hover:text-pb-text',
                empty && 'opacity-40 cursor-not-allowed hover:text-pb-dim',
              )}
            >
              {b.label}
              <span className={clsx('ml-1.5 font-mono text-[10px]', band === b.key ? 'opacity-70' : 'text-pb-faintest')}>
                {count}
              </span>
            </button>
          )
        })}
      </div>
      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              <th
                onClick={() => toggle('name', 'asc')}
                className={clsx(
                  'px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide cursor-pointer select-none',
                  sort.key === 'name' ? 'text-[var(--pb-accent)]' : 'text-pb-faint',
                )}
              >
                Player{arrow('name')}
              </th>
              {/* `sm:[display:table-cell]`, not `sm:table-cell`: index.css
                  defines a `.table-cell` component class (px-3 py-2.5
                  text-sm), so the responsive variant of Tailwind's display
                  utility drags that text-sm along with it and this header
                  renders at 14px next to its 10px neighbours. */}
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint hidden sm:[display:table-cell]">Years</th>
              {COLS.map(header)}
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.player_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                <td className="px-3 py-2">
                  <PlayerCell id={p.player_id} name={displayName(p)} base={base} photoUrl={p.photo_url} />
                </td>
                <td className="px-3 py-2 text-right pb-num text-pb-faint hidden sm:[display:table-cell]">
                  {p.first_year ? (p.first_year === p.last_year ? p.first_year : `${p.first_year}–${p.last_year}`) : '—'}
                </td>
                {COLS.map(c => (
                  <td key={c.key} className="px-3 py-2 text-right pb-num">{p[c.key] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
