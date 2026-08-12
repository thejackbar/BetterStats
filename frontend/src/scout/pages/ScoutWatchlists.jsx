import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { Btn } from '../../pages/admin/betterselect/ui'

function timeAgo(iso) {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export default function ScoutWatchlists() {
  const navigate = useNavigate()
  const [watchlists, setWatchlists] = useState(undefined) // undefined = loading
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  const load = () => { scoutApi.listWatchlists().then(setWatchlists).catch((err) => setError(err.message)) }
  useEffect(load, [])

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
    <ScoutModuleLayout
      title="Watchlists"
      caption="Boards for organising who you're tracking"
      actions={
        <form onSubmit={create} className="flex items-center gap-2">
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="New watchlist name…"
            className="bg-pb-surface2 border border-pb-hairline rounded-lg px-3 py-2 text-sm w-56"
          />
          <Btn variant="primary" type="submit" disabled={creating || !name.trim()}>{creating ? 'Creating…' : 'New watchlist'}</Btn>
        </form>
      }
    >
      {error && <p className="text-sm text-pb-red mb-4">{error}</p>}
      {watchlists === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}
      {watchlists?.length === 0 && <p className="text-sm text-pb-dim">No watchlists yet — name one above to get started.</p>}

      {watchlists && watchlists.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {watchlists.map((wl) => (
            <Link key={wl.id} to={`/betterscout/app/watchlists/${wl.id}`} className="pb-card p-4 hover:border-pb-accent transition-colors block">
              <div className="font-semibold text-[15px] truncate">{wl.name}</div>
              <div className="font-mono text-[10.5px] text-pb-faint uppercase tracking-wide2 mt-1.5">
                {wl.card_count ?? 0} player{(wl.card_count ?? 0) === 1 ? '' : 's'}
                {wl.last_used_at && ` · last used ${timeAgo(wl.last_used_at)}`}
              </div>
            </Link>
          ))}
        </div>
      )}
    </ScoutModuleLayout>
  )
}
