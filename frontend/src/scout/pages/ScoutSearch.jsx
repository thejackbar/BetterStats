import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar } from '../components/ScoutUi'
import { Search, Btn } from '../../pages/admin/betterselect/ui'

// Name search across every club roster BetterScout has already cached
// (scout_club_cache is platform-wide — shared by every Scout Org, growing
// every time anyone looks a club up on Discover) — NOT a live nationwide
// crawl of Cricket Australia. See services/scout_feed.py's docstring for
// why that's the honest scope, and why it's still genuinely useful: the
// cache only grows, and `clubs_scanned` is shown plainly rather than
// implying full coverage.
export default function ScoutSearch() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [addingId, setAddingId] = useState(null)
  const [watchlists, setWatchlists] = useState([])

  useEffect(() => { scoutApi.listWatchlists().then(setWatchlists).catch(() => {}) }, [])
  const defaultWatchlistId = useMemo(() => {
    if (!watchlists.length) return null
    return [...watchlists].sort((a, b) => new Date(b.last_used_at) - new Date(a.last_used_at))[0].id
  }, [watchlists])

  const query = q.trim()

  useEffect(() => {
    if (query.length < 2) { setData(null); setError(null); return }
    setLoading(true)
    const t = setTimeout(() => {
      scoutApi.searchFeed(query)
        .then(setData)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }, 280)
    return () => clearTimeout(t)
  }, [query])

  const openOrAdd = async (r) => {
    if (r.tracked) { navigate(`/betterscout/app/players/${r.scouted_player_id}`); return }
    setAddingId(r.player_id)
    setError(null)
    try {
      const added = await scoutApi.addPlayer(r.club_org_guid, r.player_id, r.club_name, defaultWatchlistId)
      navigate(`/betterscout/app/players/${added.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setAddingId(null)
    }
  }

  return (
    <ScoutModuleLayout
      title="Player search"
      caption="Search by name across every club roster BetterScout has already fetched"
      filters={<Search value={q} onChange={setQ} placeholder="Search a player name…" className="w-72" />}
    >
      {error && <p className="text-sm text-pb-red mb-3">{error}</p>}

      {query.length === 0 && (
        <p className="text-sm text-pb-dim">
          This searches every club roster BetterScout has already fetched, not a live nationwide crawl of Cricket Australia.
          Can't find a club's players here yet? Look the club up on{' '}
          <Link to="/betterscout/app/discover" className="underline" style={{ color: 'var(--pb-accent)' }}>Discover</Link>{' '}
          first. This search grows to cover it from then on.
        </p>
      )}
      {query.length > 0 && query.length < 2 && (
        <p className="text-sm text-pb-faint">Keep typing, at least 2 characters.</p>
      )}
      {query.length >= 2 && (
        <p className="font-mono text-[10.5px] uppercase tracking-wide2 text-pb-faint mb-3">
          {loading
            ? 'Searching…'
            : data
              ? `${data.clubs_scanned} cached club${data.clubs_scanned === 1 ? '' : 's'} scanned · ${data.results.length} match${data.results.length === 1 ? '' : 'es'}`
              : ''}
        </p>
      )}

      {data && !loading && data.results.length === 0 && query.length >= 2 && (
        <p className="text-sm text-pb-faint">
          No matches in any cached club roster yet. Try{' '}
          <Link to="/betterscout/app/discover" className="underline" style={{ color: 'var(--pb-accent)' }}>Discover</Link>{' '}
          to fetch the club this player belongs to.
        </p>
      )}

      {data && data.results.length > 0 && (
        <div className="pb-card overflow-hidden">
          <div className="divide-y divide-pb-hairline">
            {data.results.map((r) => (
              <div key={r.player_id} className="flex items-center gap-3 px-4 py-3">
                <PlayerAvatar name={r.name} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{r.name}</div>
                  <div className="font-mono text-[10.5px] text-pb-faint uppercase truncate">{r.club_name || 'Unknown club'}</div>
                </div>
                {r.totals && (
                  <div className="text-right shrink-0 font-mono text-sm">
                    <span className="font-bold">{r.totals.runs ?? 0}</span> <span className="text-pb-faint text-xs">runs</span>
                    {r.totals.wickets > 0 && <> · <span className="font-bold">{r.totals.wickets}</span> <span className="text-pb-faint text-xs">wkts</span></>}
                  </div>
                )}
                {r.tracked
                  ? <Btn sm variant="soft" onClick={() => openOrAdd(r)}>Open</Btn>
                  : <Btn sm variant="primary" onClick={() => openOrAdd(r)} disabled={addingId === r.player_id}>
                      {addingId === r.player_id ? 'Adding…' : 'Track'}
                    </Btn>}
              </div>
            ))}
          </div>
        </div>
      )}
    </ScoutModuleLayout>
  )
}
