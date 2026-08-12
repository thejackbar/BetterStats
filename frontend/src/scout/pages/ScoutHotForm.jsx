import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar, Sparkline } from '../components/ScoutUi'
import { Btn } from '../../pages/admin/betterselect/ui'

// The platform-wide mirror of Overview's own "form movers" panel — same
// "latest active season vs. the two before it" math (services/
// scout_overview.py's movers_for_seasons), just run across every player in
// every club roster BetterScout has already cached instead of only the
// players this one org tracks. Same honest "clubs_scanned" framing as
// ScoutSearch — this grows as more clubs get looked up on Discover, it
// isn't a live nationwide sweep.
export default function ScoutHotForm() {
  const navigate = useNavigate()
  const [data, setData] = useState(undefined)
  const [error, setError] = useState(null)
  const [addingId, setAddingId] = useState(null)
  const [watchlists, setWatchlists] = useState([])

  useEffect(() => {
    scoutApi.getHotForm().then(setData).catch((err) => setError(err.message))
    scoutApi.listWatchlists().then(setWatchlists).catch(() => {})
  }, [])

  const defaultWatchlistId = useMemo(() => {
    if (!watchlists.length) return null
    return [...watchlists].sort((a, b) => new Date(b.last_used_at) - new Date(a.last_used_at))[0].id
  }, [watchlists])

  const openOrAdd = async (m) => {
    if (m.tracked) { navigate(`/betterscout/app/players/${m.scouted_player_id}`); return }
    setAddingId(`${m.id}-${m.metric}`)
    setError(null)
    try {
      const added = await scoutApi.addPlayer(m.club_org_guid, m.id, m.club_name, defaultWatchlistId)
      navigate(`/betterscout/app/players/${added.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setAddingId(null)
    }
  }

  const improvers = (data?.movers || []).filter((m) => m.improved)
  const decliners = (data?.movers || []).filter((m) => !m.improved)

  return (
    <ScoutModuleLayout
      title="Hot form feed"
      caption="Biggest season-on-season movers across every club roster BetterScout has already fetched"
    >
      {error && <p className="text-sm text-pb-red mb-3">{error}</p>}
      {data === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}

      {data && (
        <>
          <p className="font-mono text-[10.5px] uppercase tracking-wide2 text-pb-faint mb-4">
            {data.clubs_scanned} cached club{data.clubs_scanned === 1 ? '' : 's'} scanned · {data.movers.length} mover{data.movers.length === 1 ? '' : 's'}
          </p>

          {data.movers.length === 0 && (
            <p className="text-sm text-pb-dim">
              Not enough cached season-on-season history yet. Look a few clubs up on{' '}
              <Link to="/betterscout/app/discover" className="underline" style={{ color: 'var(--pb-accent)' }}>Discover</Link>{' '}
              to build this feed out.
            </p>
          )}

          {data.movers.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <MoverColumn title="Trending up" tone="up" movers={improvers} addingId={addingId} onOpenOrAdd={openOrAdd} />
              <MoverColumn title="Trending down" tone="down" movers={decliners} addingId={addingId} onOpenOrAdd={openOrAdd} />
            </div>
          )}
        </>
      )}
    </ScoutModuleLayout>
  )
}

function MoverColumn({ title, tone, movers, addingId, onOpenOrAdd }) {
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">{title}</div>
      {movers.length === 0 && <p className="text-sm text-pb-faint py-4">Nothing here.</p>}
      <div className="divide-y divide-pb-hairline -mx-4 mt-1">
        {movers.map((m) => (
          <div key={`${m.id}-${m.metric}`} className="flex items-center gap-3 px-4 py-3">
            <PlayerAvatar name={m.name} size={34} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{m.name}</div>
              <div className="text-xs text-pb-faint truncate">{[m.club_name, m.grade_name].filter(Boolean).join(' · ')}</div>
            </div>
            <Sparkline seasons={m.sparkline.map((s) => ({ year: s.year, v: s.value }))} metricKey="v" height={30} width={6} gap={2} />
            <div className="text-right shrink-0">
              <div className="font-mono text-sm font-bold">
                {m.current_value}
                <span className={tone === 'up' ? 'text-pb-accent' : 'text-pb-red'} style={{ marginLeft: 4 }}>
                  {tone === 'up' ? '▲' : '▼'} {Math.abs(m.delta)}
                </span>
              </div>
              <div className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint">{m.metric}</div>
            </div>
            {m.tracked
              ? <Btn sm variant="soft" onClick={() => onOpenOrAdd(m)}>Open</Btn>
              : <Btn sm variant="primary" onClick={() => onOpenOrAdd(m)} disabled={addingId === `${m.id}-${m.metric}`}>
                  {addingId === `${m.id}-${m.metric}` ? 'Adding…' : 'Track'}
                </Btn>}
          </div>
        ))}
      </div>
    </div>
  )
}
