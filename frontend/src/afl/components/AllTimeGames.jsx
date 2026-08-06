import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { PlayerCell, displayName } from './bits'

/**
 * The club's all-time games register — every player who has ever played, most
 * games first.
 *
 * Reads /afl-players/by-org (career_totals) rather than the leaderboard
 * endpoint, for two reasons. It is genuinely career-wide, which is what "all
 * time" has to mean, and it is unpaginated — the leaderboard caps at 200 rows,
 * and a club with a 1,900-name register needs the whole thing here or a
 * "300+ games" band could never be complete. Filtering and sorting are
 * client-side over that one fetch, so changing a band costs no request.
 */

// Games-played bands — the club-milestone brackets a club actually talks in
// ("the 100-gamers", "the 200 club"), not an even numeric split. Under 100 is
// split at 50 because that band holds most of a long-running club's register:
// a club with 1,900 players on the books has the great bulk of them there.
export const BANDS = [
  { key: 'all', label: 'All' },
  { key: '1', label: '1–49', min: 1, max: 49 },
  { key: '50', label: '50–99', min: 50, max: 99 },
  { key: '100', label: '100–199', min: 100, max: 199 },
  { key: '200', label: '200–299', min: 200, max: 299 },
  { key: '300', label: '300–399', min: 300, max: 399 },
  { key: '400', label: '400+', min: 400 },
]

const inRange = (games, min, max) =>
  games >= (min ?? 1) && (max == null || games <= max)

const num = (v) => {
  if (v === '' || v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export default function AllTimeGames({ club, base }) {
  const [players, setPlayers] = useState(null)
  const [band, setBand] = useState('all')
  const [search, setSearch] = useState('')
  // The custom band's own numbers, kept even while another band is selected so
  // flicking back to Custom doesn't wipe what was typed.
  const [customMin, setCustomMin] = useState('')
  const [customMax, setCustomMax] = useState('')

  useEffect(() => {
    setPlayers(null)
    aflApi.listPlayers(club.id).then(d => setPlayers(d.players))
  }, [club.id])

  // Anyone with no game recorded has no place on a games board — they would
  // otherwise fill the bottom of a 1,900-row list with zeroes.
  const played = useMemo(
    () => (players || []).filter(p => (p.games ?? 0) > 0),
    [players],
  )

  // Counts come off the whole register rather than the current selection, so
  // each button keeps saying how many players are in its band regardless of
  // what's selected — and a band nobody has reached reads as unreachable
  // instead of as a button that empties the table.
  const bandCounts = useMemo(() => {
    const counts = {}
    for (const b of BANDS) {
      counts[b.key] = b.min == null
        ? played.length
        : played.filter(p => inRange(p.games ?? 0, b.min, b.max)).length
    }
    return counts
  }, [played])

  const rows = useMemo(() => {
    const min = num(customMin)
    const max = num(customMax)
    let out = played
    if (band === 'custom') {
      // A blank Min means "from 1", a blank Max means "and up" — so a custom
      // filter with neither is the same list as All, not an empty one.
      out = out.filter(p => inRange(p.games ?? 0, min ?? 1, max))
    } else {
      const active = BANDS.find(b => b.key === band) || BANDS[0]
      if (active.min != null) out = out.filter(p => inRange(p.games ?? 0, active.min, active.max))
    }
    const q = search.trim().toLowerCase()
    if (q) out = out.filter(p => displayName(p).toLowerCase().includes(q))
    // Most games first — the whole point of the board. Goals then name break
    // a tie, so two players on the same number of games hold a stable order
    // rather than shuffling between renders.
    return [...out].sort((a, b) =>
      (b.games ?? 0) - (a.games ?? 0)
      || (b.goals ?? 0) - (a.goals ?? 0)
      || displayName(a).localeCompare(displayName(b)))
  }, [played, band, search, customMin, customMax])

  if (players === null) return <div className="pt-8 flex justify-center"><LoadingSpinner /></div>

  const pill = (key, label, count) => {
    const empty = count === 0 && key !== 'all' && key !== 'custom'
    return (
      <button
        key={key}
        onClick={() => setBand(key)}
        disabled={empty}
        className={clsx(
          'px-3 py-1.5 rounded text-sm font-medium',
          band === key ? 'bg-[var(--pb-accent)] text-black' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text',
          empty && 'opacity-40 cursor-not-allowed hover:text-pb-dim',
        )}
      >
        {label}
        {count != null && (
          <span className={clsx('ml-1.5 font-mono text-[10px]', band === key ? 'opacity-70' : 'text-pb-faintest')}>
            {count}
          </span>
        )}
      </button>
    )
  }

  const yearsOf = (p) => (p.first_year
    ? (p.first_year === p.last_year ? p.first_year : `${p.first_year}–${p.last_year}`)
    : '—')

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-pb-faint">
          {rows.length} of {played.length} players
        </span>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search players…"
          className="ml-auto bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm w-56"
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {BANDS.map(b => pill(b.key, b.label, bandCounts[b.key] || 0))}
        {pill('custom', 'Custom', null)}
      </div>

      {band === 'custom' && (
        <div className="pb-card p-3 flex flex-wrap items-center gap-3">
          <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Games played</span>
          <label className="flex items-center gap-1.5 text-sm text-pb-dim">
            From
            <input
              type="number" inputMode="numeric" min="0" value={customMin}
              onChange={e => setCustomMin(e.target.value)} placeholder="1"
              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm font-mono w-20"
            />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-pb-dim">
            to
            <input
              type="number" inputMode="numeric" min="0" value={customMax}
              onChange={e => setCustomMax(e.target.value)} placeholder="any"
              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm font-mono w-20"
            />
          </label>
          {(customMin !== '' || customMax !== '') && (
            <button
              type="button"
              onClick={() => { setCustomMin(''); setCustomMax('') }}
              className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-[var(--pb-accent)]"
            >
              Clear
            </button>
          )}
          <span className="text-[11px] text-pb-faintest">
            Leave either blank for no limit that way.
          </span>
        </div>
      )}

      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint w-10">#</th>
              <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">Player</th>
              {/* `sm:[display:table-cell]`, not `sm:table-cell`: index.css
                  defines a `.table-cell` component class carrying text-sm,
                  which the responsive variant would drag along and render
                  this header at 14px next to its 10px neighbours. */}
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint hidden sm:[display:table-cell]">Years</th>
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-[var(--pb-accent)]">Games</th>
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">Goals</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                <td className="px-3 py-2 font-mono text-pb-faintest">{i + 1}</td>
                <td className="px-3 py-2">
                  <PlayerCell id={p.player_id} name={displayName(p)} base={base} photoUrl={p.photo_url} />
                </td>
                <td className="px-3 py-2 text-right pb-num text-pb-faint hidden sm:[display:table-cell]">{yearsOf(p)}</td>
                <td className="px-3 py-2 text-right pb-num font-bold text-[var(--pb-accent)]">{p.games ?? 0}</td>
                <td className="px-3 py-2 text-right pb-num text-pb-dim">{p.goals ?? 0}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-4 text-pb-faint text-sm">No players match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
