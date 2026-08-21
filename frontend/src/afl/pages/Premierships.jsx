import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, PlayerCell, Select } from '../components/bits'

// Every flag the club has recorded, as the squad that won it — read out of
// the Premiership awards already sitting on players' profiles, so nothing is
// entered twice.
//
// A card is one (season, team) pair, which is what a premiership IS: a club
// whose Seniors and Reserves both won in one year gets two cards, not one
// squad of twice the size.
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
              <div key={`${p.season}|${p.team}`}>
                <SectionTitle right={
                  <span className="font-mono text-[10px] text-pb-faintest normal-case tracking-normal">
                    {p.player_count} player{p.player_count === 1 ? '' : 's'}
                  </span>
                }>
                  {[p.season || 'Season not recorded', p.team].filter(Boolean).join(' · ')}
                </SectionTitle>
                <div className="pb-card p-4">
                  <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                    {p.players.map(pl => (
                      <li key={pl.player_id || pl.name} className="min-w-0 text-sm">
                        <PlayerCell id={pl.player_id} name={pl.name} base={base} photoUrl={pl.photo_url} />
                        {/* A role beyond "was in the side" — captain, best on
                            ground — plus whatever the club typed against the
                            row. The plain Premiership award itself is what
                            every name here already means, so it isn't
                            repeated under each one. */}
                        {(pl.roles.length > 0 || pl.detail) && (
                          <span className="block pl-8 font-mono text-[10px] uppercase tracking-wide text-[var(--pb-accent)]">
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
