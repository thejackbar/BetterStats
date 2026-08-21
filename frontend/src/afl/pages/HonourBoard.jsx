import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { PlayerCell } from '../components/bits'

// A board per role the club has recorded somebody in — President, Secretary,
// Club Coach and the rest — each one a list of who held it and when, read out
// of the Office Bearer awards on players' profiles.
//
// A rail of roles beside the board, rather than every board stacked down one
// page: a club with fifty years of committees has a lot of roles, and the
// question is nearly always about one of them.
export default function HonourBoard() {
  const { club } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState(null)
  const base = `/${club.slug}`

  useEffect(() => {
    setLoading(true)
    aflApi.getOfficeBearers(club.id).then(setData).finally(() => setLoading(false))
  }, [club.id])

  const groups = data?.groups || []
  const boards = useMemo(
    () => groups.flatMap(g => g.boards.map(b => ({ ...b, group: g.group }))),
    [groups])
  const key = (b) => `${b.group}|${b.role}`
  const current = boards.find(b => key(b) === sel) || boards[0]

  if (loading && !data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Honour Board</h1>

      {boards.length === 0 ? (
        <div className="pb-card p-6 text-sm text-pb-dim">
          No club roles recorded yet. The boards are built from the Office Bearer
          awards on each player's profile — record who was President, Secretary or
          Club Coach in a season under Admin → Awards and the board fills itself
          in, one line per person with the years they served.
        </div>
      ) : (
        /* min-w-0 on both grid items, not on the grid: a grid item's
           automatic minimum is its own content, so without it the years
           column pushes the whole page sideways on a phone and the card's
           own overflow-x-auto never gets a chance to scroll. */
        <div className="grid gap-4 lg:grid-cols-[15rem_1fr]">
          <nav className="pb-card p-2 min-w-0 lg:sticky lg:top-20 lg:self-start max-h-[70vh] overflow-y-auto">
            {groups.map(g => (
              <div key={g.group} className="mb-2 last:mb-0">
                <p className="px-2 py-1 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
                  {g.group}
                </p>
                {g.boards.map(b => {
                  const k = `${g.group}|${b.role}`
                  const active = current && key(current) === k
                  return (
                    <button
                      key={k}
                      onClick={() => setSel(k)}
                      className={clsx(
                        'w-full text-left px-2 py-1.5 rounded text-sm flex items-center gap-2',
                        active ? 'bg-[var(--pb-accent)] text-black font-medium'
                               : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2')}
                    >
                      <span className="truncate">{b.role}</span>
                      <span className={clsx('ml-auto pb-num text-[11px]',
                                            active ? 'text-black/70' : 'text-pb-faintest')}>
                        {b.holder_count}
                      </span>
                    </button>
                  )
                })}
              </div>
            ))}
          </nav>

          {current && (
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-2 mb-2">
                <h2 className="text-lg font-bold">{current.role}</h2>
                <span className="font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
                  {current.group} · {current.holder_count} {current.holder_count === 1 ? 'person' : 'people'}
                </span>
              </div>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="pb-hairline-b">
                    <tr>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-pb-faint">Name</th>
                      <th className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint">Years</th>
                      <th className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint">Seasons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.holders.map(h => (
                      <tr key={h.player_id || h.name} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                        <td className="px-3 py-2">
                          <PlayerCell id={h.player_id} name={h.name} base={base} photoUrl={h.photo_url} />
                        </td>
                        {/* A run of consecutive seasons reads as one span;
                            a genuine break reads as two, because coming back
                            to a role years later is two stints, not one long
                            one. Nobody's years recorded at all reads as a
                            dash rather than a guessed year. */}
                        <td className="px-3 py-2 text-right pb-num whitespace-nowrap">
                          {h.years || <span className="text-pb-faintest">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right pb-num text-pb-dim">{h.seasons}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
