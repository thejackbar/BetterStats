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
// A card is one (season, team, competition). The competition is the card's own
// title and is never repeated under each name: every player on the card
// already means "was in the side that won this". What sits under a name is a
// genuine part in the win — Captain, Player of the Match, 12th Man.
// Cricket's twin of the football page; both read the same backend service.

// A photo where the club holds one, the club crest where it doesn't, so a
// squad never renders as a column of blank circles. Same pattern the Lineups
// page uses, and the same reason: a hotlinked photo can 404 at any time.
function Avatar({ photoUrl, logoUrl, name, size = 26 }) {
  const [failed, setFailed] = useState(false)
  if (photoUrl && !failed) {
    return (
      <img src={photoUrl} alt="" onError={() => setFailed(true)}
           className="shrink-0 rounded-full object-cover bg-pb-surface2"
           style={{ width: size, height: size }} />
    )
  }
  const initials = (name || '?').replace(/,/g, ' ').trim().split(/\s+/)
    .slice(0, 2).map(w => w[0]).join('').toUpperCase()
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="shrink-0 rounded-full object-contain bg-pb-surface2"
                style={{ width: size, height: size }} />
  }
  return (
    <span className="shrink-0 rounded-full grid place-items-center font-semibold"
          style={{ width: size, height: size, fontSize: Math.round(size * 0.38),
                   background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)',
                   color: 'var(--pb-accent)' }}>
      {initials}
    </span>
  )
}

function PlayerLine({ player, logoUrl, fmt }) {
  const name = fmt(player.name)
  const extra = [...player.roles, player.detail].filter(Boolean).join(' · ')
  const body = (
    <>
      <Avatar photoUrl={player.photo_url} logoUrl={logoUrl} name={player.name} />
      {/* min-w-0 + truncate: a long name is cut with an ellipsis rather than
          wrapping onto a second line and breaking the grid's rhythm. The
          title attribute keeps the whole name reachable. */}
      <span className="min-w-0 flex-1">
        <span className="block truncate" title={player.name}>{name}</span>
        {extra && (
          <span className="block truncate font-mono text-[10px] tracking-wide2 uppercase"
                title={extra} style={{ color: 'var(--pb-accent)' }}>{extra}</span>
        )}
      </span>
    </>
  )
  const cls = 'flex items-center gap-2 min-w-0 py-0.5'
  return (
    <li className="min-w-0">
      {player.player_id
        ? <Link to={`/players/${player.player_id}`}
                className={`${cls} text-pb-text hover:text-pb-accent transition-colors`}>{body}</Link>
        : <span className={`${cls} text-pb-text`}>{body}</span>}
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
                <div key={`${p.season}|${p.team}|${p.competition}`} className="pb-card overflow-hidden">
                  <div className="px-4 sm:px-5 py-3 pb-hairline-b bg-pb-surface2/40 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <Label style={{ color: 'var(--pb-accent)' }}>
                      {[p.season || 'Season not recorded', p.team].filter(Boolean).join(' · ')}
                    </Label>
                    {/* The competition the flag was won in — the card's own
                        title, which is why it is not repeated under every
                        name below. */}
                    {p.competition && (
                      <span className="min-w-0 truncate text-[13px] text-pb-dim" title={p.competition}>
                        {p.competition}
                      </span>
                    )}
                    <span className="sm:ml-auto font-mono text-[11px] text-pb-faint whitespace-nowrap">
                      {p.player_count} player{p.player_count === 1 ? '' : 's'}
                    </span>
                  </div>
                  <ul className="px-4 sm:px-5 py-4 grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
                    {p.players.map(pl => (
                      <PlayerLine key={pl.player_id || pl.name} player={pl}
                                  logoUrl={club?.logo_url} fmt={fmt} />
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
