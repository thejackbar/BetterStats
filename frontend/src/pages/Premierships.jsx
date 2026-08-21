import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import { Label, PageHeader, PbSpinner } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'

// Every flag the club has recorded, as the squad that won it — read out of the
// Premiership awards already sitting on players' profiles, so a club that has
// filled in its honour roll gets this for nothing.
//
// A card is one (season, team) pair, which is what a premiership IS: a club
// whose 1st XI and 3rd XI both won in one season gets two cards, not one squad
// of twice the size. Cricket's twin of the football page — both read the same
// backend service.

function PlayerLine({ player, fmt }) {
  const name = fmt(player.name)
  const extra = [...player.roles, player.detail].filter(Boolean).join(' · ')
  return (
    <li className="min-w-0">
      {player.player_id
        ? <Link to={`/players/${player.player_id}`}
                className="text-pb-text hover:text-pb-accent transition-colors">{name}</Link>
        : <span className="text-pb-text">{name}</span>}
      {/* A part beyond "was in the side" — captain, player of the final —
          plus whatever the club typed against the row. The plain Premiership
          award is what every name on the card already means, so it is not
          repeated under each one. */}
      {extra && (
        <span className="block font-mono text-[10px] tracking-wide2 uppercase"
              style={{ color: 'var(--pb-accent)' }}>{extra}</span>
      )}
    </li>
  )
}

export default function Premierships() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [team, setTeam] = useState(null)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getPremierships(orgId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [orgId])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  const all = data?.premierships || []
  const teams = [...new Set(all.map(p => p.team).filter(Boolean))]
  const shown = team ? all.filter(p => p.team === team) : all
  const players = shown.reduce((a, p) => a + p.player_count, 0)

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`PREMIERSHIPS · ${club?.name?.toUpperCase() || ''}`}
          title="Flags on the wall."
          meta={[<span key="x">Every premiership side the club has recorded.</span>]}
        />

        {loading && !data ? <PbSpinner message="Loading premierships…" /> : all.length === 0 ? (
          <div className="pb-card p-6 text-sm text-pb-dim">
            No premierships recorded yet. They come from the Premiership awards on
            each player's profile — add them under Admin → Awards, or bring a whole
            honour roll in at once with the awards import, and the squads build
            themselves from there.
          </div>
        ) : (
          <>
            <div className="mb-5 flex flex-wrap gap-3 items-center">
              {teams.length > 1 && (
                <select
                  value={team || ''}
                  onChange={e => setTeam(e.target.value || null)}
                  className="bg-pb-surface2 pb-hairline rounded px-3 py-1.5 text-sm text-pb-text"
                >
                  <option value="">All teams</option>
                  {teams.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
              <Label>
                {shown.length} flag{shown.length === 1 ? '' : 's'} · {players} player{players === 1 ? '' : 's'}
              </Label>
            </div>

            <div className="space-y-4">
              {shown.map(p => (
                <div key={`${p.season}|${p.team}`} className="pb-card overflow-hidden">
                  <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40 flex flex-wrap items-center gap-3">
                    <Label style={{ color: 'var(--pb-accent)' }}>
                      {[p.season || 'Season not recorded', p.team].filter(Boolean).join(' · ')}
                    </Label>
                    <span className="ml-auto font-mono text-[11px] text-pb-faint">
                      {p.player_count} player{p.player_count === 1 ? '' : 's'}
                    </span>
                  </div>
                  <ul className="px-5 py-4 grid gap-x-6 gap-y-2 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
                    {p.players.map(pl => (
                      <PlayerLine key={pl.player_id || pl.name} player={pl} fmt={fmt} />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
