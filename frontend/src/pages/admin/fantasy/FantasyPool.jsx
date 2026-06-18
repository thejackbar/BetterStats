import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { FantasyFrame, PoolManager, PoolTable, useFantasySeason } from './shared'

// Player pool — add returning / new players and the priced pool table (edit a
// role, remove a player). Its own side-menu page. Build the pool itself from the
// Overview page.
export default function FantasyPool() {
  const { season, loading, msg, err, flash, fail } = useFantasySeason()
  const seasonId = season?.id
  const [pool, setPool] = useState(null)

  const loadPool = useCallback(async () => {
    if (!seasonId) return
    try { setPool((await api.fantasyListPool(seasonId)).players) } catch (e) { fail(e) }
  }, [seasonId, fail])
  useEffect(() => { loadPool() }, [loadPool])

  const setRole = async (pp, role) => {
    try { await api.fantasyPatchPool(pp.id, { role }); await loadPool() } catch (e) { fail(e) }
  }
  const removePool = async (id) => {
    if (!window.confirm('Remove this player from the pool?')) return
    try { await api.fantasyRemovePoolPlayer(id); await loadPool() } catch (e) { fail(e) }
  }

  return (
    <FantasyFrame title="Player pool" season={season} loading={loading} msg={msg} err={err}>
      {season && (
        <div className="space-y-6">
          <PoolManager season={season} flash={flash} fail={fail} onChanged={loadPool} />
          <PoolTable pool={pool} onRoleChange={setRole} onRemove={removePool} />
        </div>
      )}
    </FantasyFrame>
  )
}
