import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import { Label, PageHeader, PbSpinner } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'

// A board per role the club has recorded somebody in — President, Secretary,
// Club Coach and the rest — each a list of who held it and when, read out of
// the Office Bearer awards on players' profiles. Cricket's twin of the
// football page; both read the same backend service.
//
// A rail of roles beside the board rather than every board stacked down one
// page: a club with a century of committees has a lot of roles, and the
// question is nearly always about one of them.
export default function HonourBoard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState(null)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getOfficeBearers(orgId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [orgId])

  const groups = data?.groups || []
  const boards = useMemo(
    () => groups.flatMap(g => g.boards.map(b => ({ ...b, group: g.group }))),
    [groups])
  const key = (b) => `${b.group}|${b.role}`
  const current = boards.find(b => key(b) === sel) || boards[0]

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`HONOUR BOARD · ${club?.name?.toUpperCase() || ''}`}
          title="Who ran the club."
          meta={[<span key="x">Every role the club has kept a record of, and who held it.</span>]}
        />

        {loading && !data ? <PbSpinner message="Loading the honour board…" /> : boards.length === 0 ? (
          <div className="pb-card p-6 text-sm text-pb-dim">
            No club roles recorded yet. The boards are built from the Office Bearer
            awards on each player's profile — record who was President, Secretary or
            Club Coach in a season under Admin → Awards and the board fills itself in,
            one line per person with the years they served.
          </div>
        ) : (
          /* min-w-0 on both grid items, not on the grid: a grid item's
             automatic minimum is its own content, so without it the years
             column pushes the whole page sideways on a phone and the card's
             own overflow never gets a chance to scroll. */
          <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
            <nav className="pb-card p-2 min-w-0 lg:sticky lg:top-20 lg:self-start max-h-[70vh] overflow-y-auto">
              {groups.map(g => (
                <div key={g.group} className="mb-2 last:mb-0">
                  <div className="px-2 py-1"><Label>{g.group}</Label></div>
                  {g.boards.map(b => {
                    const k = `${g.group}|${b.role}`
                    const active = current && key(current) === k
                    return (
                      <button
                        key={k}
                        onClick={() => setSel(k)}
                        className={`w-full text-left px-2 py-1.5 rounded text-[13px] flex items-center gap-2 transition-colors ${
                          active ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2'}`}
                        style={active ? { background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' } : undefined}
                      >
                        <span className="truncate">{b.role}</span>
                        <span className="ml-auto font-mono text-[11px] text-pb-faintest">{b.holder_count}</span>
                      </button>
                    )
                  })}
                </div>
              ))}
            </nav>

            {current && (
              <div className="pb-card min-w-0 overflow-x-auto">
                <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40 flex flex-wrap items-center gap-3">
                  <Label style={{ color: 'var(--pb-accent)' }}>{current.role}</Label>
                  <span className="ml-auto font-mono text-[11px] text-pb-faint">
                    {current.group} · {current.holder_count} {current.holder_count === 1 ? 'person' : 'people'}
                  </span>
                </div>
                <table className="w-full text-[13px]">
                  <thead className="pb-hairline-b">
                    <tr>
                      <th className="px-5 py-2 text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Name</th>
                      <th className="px-5 py-2 text-right font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Years</th>
                      <th className="px-5 py-2 text-right font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Seasons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.holders.map(h => (
                      <tr key={h.player_id || h.name} className="pb-hairline-b last:border-0">
                        <td className="px-5 py-2">
                          {h.player_id
                            ? <Link to={`/players/${h.player_id}`}
                                    className="text-pb-text hover:text-pb-accent transition-colors">{fmt(h.name)}</Link>
                            : <span className="text-pb-text">{fmt(h.name)}</span>}
                        </td>
                        {/* A run of consecutive seasons reads as one span; a
                            genuine break reads as two, because coming back to
                            a role years later is two stints, not one long one.
                            No years recorded at all reads as a dash rather
                            than a guessed year. */}
                        <td className="px-5 py-2 text-right font-mono whitespace-nowrap">
                          {h.years || <span className="text-pb-faintest">—</span>}
                        </td>
                        <td className="px-5 py-2 text-right font-mono text-pb-dim">{h.seasons}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
