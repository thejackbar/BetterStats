import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

export default function ScoutWatchlists() {
  const navigate = useNavigate()
  const [watchlists, setWatchlists] = useState(undefined) // undefined = loading
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    scoutApi.listWatchlists().then(setWatchlists).catch((err) => setError(err.message))
  }

  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError(null)
    try {
      const wl = await scoutApi.createWatchlist(name.trim())
      navigate(`/betterscout/app/watchlists/${wl.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Watchlists</h1>
        <p className="text-sm text-pb-dim">Boards for organising who you're tracking.</p>
      </div>

      <form onSubmit={create} className="flex gap-2">
        <input
          value={name} onChange={(e) => setName(e.target.value)} placeholder="New watchlist name…"
          className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-3 py-2"
        />
        <button disabled={creating || !name.trim()}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {creating ? 'Creating…' : 'New watchlist'}
        </button>
      </form>

      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      {watchlists === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}

      {watchlists && watchlists.length > 0 && (
        <div className="pb-card divide-y divide-pb-hairline">
          {watchlists.map((wl) => (
            <Link key={wl.id} to={`/betterscout/app/watchlists/${wl.id}`}
                  className="block px-4 py-3 hover:bg-pb-surface2 font-medium">
              {wl.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
