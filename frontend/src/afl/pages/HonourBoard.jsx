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
// Picking a role is a DROPDOWN on a phone and a rail beside the board from lg
// up. A club with decades of committees has more roles than fit above the
// fold, and as a rail that list pushed the board itself — the thing the page
// is for — off the bottom of the screen.

// Every stint on its own line, and the two years in fixed columns so the
// dashes line up down the whole board. Right-aligning one "2010–2011,
// 2021–2022" beside a bare "1998" is what made the column read as ragged.
function Years({ spans }) {
  if (!spans || spans.length === 0) return <span className="text-pb-faintest">—</span>
  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      {spans.map((s, i) => (
        <span key={i} className="inline-grid grid-cols-[3.2ch_0.9rem_4.6rem] items-baseline">
          <span className="text-right tabular-nums">{s.from}</span>
          {/* pb-faint, not pb-faintest: at this size the dimmest token
              disappears against the card and "2010 2011" reads as one
              eight-digit number. */}
          <span className="text-center text-pb-faint">{(s.to || s.open) ? '–' : ''}</span>
          <span className="text-left tabular-nums">
            {s.open ? <span className="text-pb-dim">present</span> : (s.to || '')}
          </span>
        </span>
      ))}
    </span>
  )
}

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
          awards on each player's profile. Record who was President, Secretary or
          Club Coach in a season under Admin → Awards and the board fills itself
          in, one line per person with the years they served.
        </div>
      ) : (
        /* min-w-0 on both grid items, not on the grid: a grid item's
           automatic minimum is its own content, so without it the years
           column pushes the whole page sideways on a phone and the card's
           own overflow-x-auto never gets a chance to scroll. */
        <div className="grid gap-4 lg:grid-cols-[15rem_1fr]">
          {/* The phone control. optgroup keeps the club's own grouping, so
              the choice reads the same as the rail does on a laptop. */}
          <div className="lg:hidden">
            <label htmlFor="hb-role"
                   className="block mb-1 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
              Role
            </label>
            <select
              id="hb-role"
              value={current ? key(current) : ''}
              onChange={e => setSel(e.target.value)}
              className="w-full bg-pb-surface2 pb-hairline rounded px-3 py-2 text-sm text-pb-text"
            >
              {groups.map(g => (
                <optgroup key={g.group} label={g.group}>
                  {g.boards.map(b => (
                    <option key={`${g.group}|${b.role}`} value={`${g.group}|${b.role}`}>
                      {b.role} ({b.holder_count})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          <nav className="hidden lg:block pb-card p-2 min-w-0 lg:sticky lg:top-20 lg:self-start max-h-[70vh] overflow-y-auto">
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
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 mb-2">
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
                      {/* The season tally is the least of the three and the
                          first to go when there is no room for it. */}
                      {/* `sm:table-cell` is NOT usable here: index.css
                          defines its own `.table-cell` component (padding,
                          14px, full-brightness text) which collides with
                          Tailwind's display utility of that name and quietly
                          restyles the cell. The arbitrary-property form
                          generates a different class and so does not. */}
                      <th className="hidden sm:[display:table-cell] px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint">Seasons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.holders.map(h => (
                      <tr key={h.player_id || h.name}
                          className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50 align-top">
                        <td className="px-3 py-2">
                          <PlayerCell id={h.player_id} name={h.name} base={base} photoUrl={h.photo_url} />
                        </td>
                        {/* A run of consecutive seasons reads as one span;
                            a genuine break reads as two, because coming back
                            to a role years later is two stints, not one long
                            one. Nobody's years recorded at all reads as a
                            dash rather than a guessed year. */}
                        <td className="px-3 py-2 text-right pb-num whitespace-nowrap">
                          <Years spans={h.spans} />
                        </td>
                        <td className="hidden sm:[display:table-cell] px-3 py-2 text-right pb-num text-pb-dim">{h.seasons}</td>
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
