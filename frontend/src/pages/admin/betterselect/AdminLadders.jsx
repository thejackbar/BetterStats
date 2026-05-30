import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import LadderBoard from '../../../components/LadderBoard'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import { Btn } from './ui'

export default function AdminLadders() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback((showSpinner = true) => {
    if (showSpinner) setData(null)
    setRefreshing(true)
    api.bsTeamLadders()
      .then(setData)
      .catch(e => { toast.error(e.message); setData({ teams: [], unlinked: [] }) })
      .finally(() => setRefreshing(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const actions = <Btn variant="soft" sm icon="bolt" onClick={() => load(false)} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</Btn>

  if (data === null) return <BetterSelectLayout title="Ladders" actions={actions}><PbSpinner message="Loading ladders…" /></BetterSelectLayout>

  const unlinked = data.unlinked || []

  return (
    <BetterSelectLayout title="Ladders" actions={actions}>
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">
        Live grade standings for each of your teams. Teams are auto-linked to the grade they most recently
        played in — fix any wrong links from the <Link to="/admin/betterselect/teams" className="text-pb-accent underline">Teams</Link> page.
      </p>

      {unlinked.length > 0 && (
        <div className="rounded-lg px-4 py-2.5 mb-4 text-sm bg-pb-amber/10 border border-pb-amber/30 text-pb-amber">
          {unlinked.length} team{unlinked.length === 1 ? '' : 's'} aren’t linked to a grade yet
          ({unlinked.map(t => t.team_name).join(', ')}). Set a grade on the{' '}
          <Link to="/admin/betterselect/teams" className="underline">Teams</Link> page to show their ladder.
        </div>
      )}

      <LadderBoard teams={data.teams} />
    </BetterSelectLayout>
  )
}
