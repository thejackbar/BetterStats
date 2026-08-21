import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, PlayerCell, Select } from '../components/bits'

// Every flag the club has recorded, as the squad that won it — read out of
// the Premiership awards already sitting on players' profiles, so nothing is
// entered twice.
//
// A card is one (season, team, competition). The competition is the card's own
// title and is never repeated under each name: every player on the card
// already means "was in the side that won this". What sits under a name is a
// genuine part in the win — Captain, Best on Ground, 12th Man.
export default function Premierships() {
  const { club } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [team, setTeam] = useState(null)
  const base = `/${club.slug}`

  useEffect(() => {
    setLoading(true)
    aflApi.getPremierships(club.id).then(setData).finally(() => setLoading(false))
  }, [club.id])

  const all = data?.premierships || []
  const teams = [...new Set(all.map(p => p.team).filter(Boolean))]
  const shown = team ? all.filter(p => p.team === team) : all
  const players = shown.reduce((a, p) => a + p.player_count, 0)

  if (loading && !data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Premierships</h1>
        {teams.length > 1 && (
          <div className="ml-auto">
            <Select value={team} onChange={setTeam} placeholder="All teams"
                    options={teams.map(t => ({ value: t, label: t }))} />
          </div>
        )}
      </div>

      {all.length === 0 ? (
        <div className="pb-card p-6 text-sm text-pb-dim">
          No premierships recorded yet. They come from the Premiership awards on
          each player's profile — add them under Admin → Awards, or bring a whole
          honour roll in at once with Import Awards, and the squads build
          themselves from there.
        </div>
      ) : (
        <>
          <p className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">
            {shown.length} flag{shown.length === 1 ? '' : 's'} · {players} player{players === 1 ? '' : 's'}
          </p>
          <div className="space-y-5">
            {shown.map(p => (
              <div key={`${p.season}|${p.team}|${p.competition}`}>
                <SectionTitle right={
                  <span className="font-mono text-[10px] text-pb-faintest normal-case tracking-normal whitespace-nowrap">
                    {p.player_count} player{p.player_count === 1 ? '' : 's'}
                  </span>
                }>
                  {[p.season || 'Season not recorded', p.team].filter(Boolean).join(' · ')}
                </SectionTitle>
                {/* The competition the flag was won in — the card's own title,
                    which is why it is not repeated under every name below. */}
                {p.competition && (
                  <p className="-mt-1 mb-1.5 truncate text-[13px] text-pb-dim" title={p.competition}>
                    {p.competition}
                  </p>
                )}
                <div className="pb-card p-4">
                  <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                    {p.players.map(pl => (
                      <li key={pl.player_id || pl.name} className="min-w-0 text-sm">
                        <PlayerCell id={pl.player_id} name={pl.name} base={base} photoUrl={pl.photo_url} />
                        {/* A part in the win beyond being in the side —
                            captain, best on ground — however the club
                            recorded it. Truncated rather than wrapped, so a
                            long note can't push the grid out of rhythm. */}
                        {(pl.roles.length > 0 || pl.detail) && (
                          <span className="block pl-8 truncate font-mono text-[10px] uppercase tracking-wide text-[var(--pb-accent)]"
                                title={[...pl.roles, pl.detail].filter(Boolean).join(' · ')}>
                            {[...pl.roles, pl.detail].filter(Boolean).join(' · ')}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
