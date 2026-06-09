import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import LadderBoard from '../../../components/LadderBoard'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import { formatSeason } from '../../../lib/cricketFormat'
import { Btn, Icon } from './ui'

// Inline grade-linker for a team that has no grade (so its ladder is missing —
// e.g. "3rd Grade" when auto-link couldn't match the team name to a grade).
// Linking it here makes its ladder appear without a trip to the Squads page.
function UnlinkedRow({ team, gradeSeasons, onLinked }) {
  const toast = useToast()
  const [gradeId, setGradeId] = useState('')
  const [saving, setSaving] = useState(false)

  const link = async () => {
    if (!gradeId) return
    setSaving(true)
    try {
      await api.bsUpdateTeam(team.team_id, { grade_id: gradeId })
      toast.success(`Linked ${team.team_name} — its ladder will load`)
      onLinked()
    } catch (e) { toast.error('Link failed: ' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="flex flex-wrap items-center gap-2.5 py-2 border-t border-pb-amber/20 first:border-0">
      <span className="font-medium text-sm text-pb-text">{team.team_name}</span>
      <span className="text-pb-amber/80 text-[12px]">no grade linked</span>
      <select value={gradeId} onChange={(e) => setGradeId(e.target.value)}
        className="ml-auto bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
        <option value="">— pick the grade —</option>
        {gradeSeasons.map((s) => (
          <optgroup key={s.season_id} label={formatSeason(s.season_name)}>
            {s.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </optgroup>
        ))}
      </select>
      <Btn variant="primary" sm onClick={link} disabled={!gradeId || saving}>{saving ? 'Linking…' : 'Link ladder'}</Btn>
    </div>
  )
}

export default function AdminLadders() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [gradeSeasons, setGradeSeasons] = useState([])
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback((showSpinner = true) => {
    if (showSpinner) setData(null)
    setRefreshing(true)
    api.bsTeamLadders()
      .then(setData)
      .catch((e) => { toast.error(e.message); setData({ teams: [], unlinked: [] }) })
      .finally(() => setRefreshing(false))
  }, [toast])

  useEffect(() => { load() }, [load])
  useEffect(() => { api.bsTeamGradeOptions().then((d) => setGradeSeasons(d.seasons || [])).catch(() => {}) }, [])

  const actions = <Btn variant="soft" sm icon="bolt" onClick={() => load(false)} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</Btn>

  if (data === null) return <BetterSelectLayout title="Ladders" actions={actions}><PbSpinner message="Loading ladders…" /></BetterSelectLayout>

  const unlinked = data.unlinked || []
  // Teams whose grade IS linked but the upstream ladder came back empty.
  const noData = (data.teams || []).filter((t) => !t.available)

  return (
    <BetterSelectLayout title="Ladders" actions={actions}>
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">
        Live grade standings for each of your squads. Teams are auto-linked to the grade they most recently
        played in; if a ladder is missing, link the right grade below or from the{' '}
        <Link to="/admin/betterselect/teams" className="text-pb-accent underline">Squads</Link> page.
      </p>

      {unlinked.length > 0 && (
        <div className="rounded-lg px-4 py-3 mb-4 bg-pb-amber/10 border border-pb-amber/30">
          <div className="flex items-center gap-2 text-pb-amber text-sm font-medium mb-1.5">
            <Icon name="info" size={15} />
            {unlinked.length} squad{unlinked.length === 1 ? '' : 's'} {unlinked.length === 1 ? 'has' : 'have'} no ladder — link a grade to show {unlinked.length === 1 ? 'it' : 'them'}
          </div>
          {unlinked.map((t) => <UnlinkedRow key={t.team_id} team={t} gradeSeasons={gradeSeasons} onLinked={() => load(false)} />)}
        </div>
      )}

      {unlinked.length === 0 && noData.length > 0 && (
        <div className="rounded-lg px-4 py-2.5 mb-4 text-sm bg-pb-amber/10 border border-pb-amber/30 text-pb-amber">
          {noData.map((t) => t.team_name).join(', ')} {noData.length === 1 ? 'is' : 'are'} linked to a grade, but no ladder has been published for {noData.length === 1 ? 'it' : 'them'} yet (or the linked grade is wrong — fix it on the <Link to="/admin/betterselect/teams" className="underline">Squads</Link> page).
        </div>
      )}

      <LadderBoard teams={data.teams} />
    </BetterSelectLayout>
  )
}
