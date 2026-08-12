import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

const POLL_MS = 2500
const MAX_POLLS = 60 // bounded so a wedged build doesn't poll forever (~2.5min)

export default function ScoutDiscover() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [clubs, setClubs] = useState([])
  const [searching, setSearching] = useState(false)
  const [club, setClub] = useState(null) // { id, name }
  const [roster, setRoster] = useState(null) // { status, players }
  const [addingId, setAddingId] = useState(null)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)
  const pollCount = useRef(0)

  useEffect(() => () => clearTimeout(pollRef.current), [])

  const search = async (e) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    setError(null)
    try {
      setClubs(await scoutApi.searchClubs(query.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  const pickClub = (c) => {
    clearTimeout(pollRef.current)
    pollCount.current = 0
    setClub(c)
    setRoster({ status: 'building' })
    setError(null)
    poll(c)
  }

  const poll = (c) => {
    scoutApi.getClubRoster(c.id, c.name).then((d) => {
      setRoster(d)
      if (d.status === 'building') {
        if (++pollCount.current < MAX_POLLS) {
          pollRef.current = setTimeout(() => poll(c), POLL_MS)
        } else {
          setRoster({ status: 'error', message: 'Timed out waiting for the roster to build.' })
        }
      }
    }).catch((err) => setRoster({ status: 'error', message: err.message }))
  }

  const addPlayer = async (player) => {
    setAddingId(player.player_id)
    setError(null)
    try {
      const added = await scoutApi.addPlayer(club.id, player.player_id, club.name)
      navigate(`/betterscout/app/players/${added.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setAddingId(null)
    }
  }

  const players = (roster?.players || []).slice().sort((a, b) => (b.totals?.matches || 0) - (a.totals?.matches || 0))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Discover players</h1>
        <p className="text-sm text-pb-dim">Search any Australian club to browse its roster and stats.</p>
      </div>

      <form onSubmit={search} className="flex gap-2">
        <input
          value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search for a club…"
          className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-3 py-2"
        />
        <button disabled={searching || query.trim().length < 2}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {searching ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}

      {!club && clubs.length > 0 && (
        <div className="pb-card divide-y divide-pb-hairline">
          {clubs.map((c) => (
            <button key={c.id} onClick={() => pickClub(c)}
                    className="w-full text-left px-4 py-3 hover:bg-pb-surface2">
              {c.name}
            </button>
          ))}
        </div>
      )}

      {club && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{club.name}</h2>
            <button onClick={() => { setClub(null); setRoster(null); clearTimeout(pollRef.current) }}
                    className="text-sm text-pb-dim hover:text-pb-text">
              ← Back to search
            </button>
          </div>

          {roster?.status === 'building' && (
            <p className="text-sm text-pb-dim">Building this club's roster from Cricket Australia's records — first load can take up to a minute…</p>
          )}
          {roster?.status === 'error' && (
            <p className="text-sm text-[var(--pb-negative)]">{roster.message || 'Could not load this club’s roster.'}</p>
          )}
          {roster?.status === 'ready' && players.length === 0 && (
            <p className="text-sm text-pb-dim">No player records found for this club.</p>
          )}
          {roster?.status === 'ready' && players.length > 0 && (
            <div className="pb-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-pb-dim text-xs uppercase font-mono">
                  <tr className="border-b border-pb-hairline">
                    <th className="text-left px-3 py-2">Player</th>
                    <th className="text-right px-3 py-2">Matches</th>
                    <th className="text-right px-3 py-2">Runs</th>
                    <th className="text-right px-3 py-2">Avg</th>
                    <th className="text-right px-3 py-2">Wkts</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((p) => (
                    <tr key={p.player_id} className="border-b border-pb-hairline last:border-0">
                      <td className="px-3 py-2">{p.name}</td>
                      <td className="px-3 py-2 text-right">{p.totals?.matches ?? '—'}</td>
                      <td className="px-3 py-2 text-right">{p.totals?.runs ?? '—'}</td>
                      <td className="px-3 py-2 text-right">{p.totals?.average ?? '—'}</td>
                      <td className="px-3 py-2 text-right">{p.totals?.wickets ?? '—'}</td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => addPlayer(p)} disabled={addingId === p.player_id}
                                className="text-xs px-2 py-1 rounded bg-[var(--pb-accent)] text-black disabled:opacity-50">
                          {addingId === p.player_id ? 'Adding…' : 'Add'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
