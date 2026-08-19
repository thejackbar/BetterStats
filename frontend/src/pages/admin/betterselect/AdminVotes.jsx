// BetterSelect → Votes. Brownlow-style best-player vote collection.
//
// A club counts votes towards one MEDAL or several, each with its own ballot
// shape, voter mode, counting method, eligibility source, public link and set
// of grades. The medal picker sits above the tabs because every tab below
// shows exactly one medal's count, and the selection has to be visible and
// switchable wherever you are on the screen.
//
// Three tabs:
//   Hub         — every played game this medal counts, with its voting state,
//                 ballot progress, bulk open/lock/nudge and sharing.
//   Leaderboard — this medal's season count, replayable "as at" any round,
//                 with a podium, rank movement, form and awards-night mode.
//   Settings    — the medal itself: name, grades, who votes, ballot shape,
//                 counting method, tie policy, eligibility source, auto-close
//                 and the public link.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { CAP } from '../../../lib/capabilities'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import VotesHub from './votes/VotesHub'
import VotesLeaderboard from './votes/VotesLeaderboard'
import FixtureDetail from './votes/FixtureDetail'
import VotesSettings from './votes/VotesSettings'
import MedalBar from './votes/MedalBar'

export default function AdminVotes() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canManage = hasCapability(CAP.MANAGE_VOTES)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'hub'
  const urlMedal = params.get('medal') || ''
  const [openFixture, setOpenFixture] = useState(null)
  const [medals, setMedals] = useState(null)
  const [grades, setGrades] = useState([])

  const loadMedals = useCallback(
    () => api.votesMedals().then((d) => {
      setMedals(d.medals || [])
      setGrades(d.grades || [])
      return d
    }).catch((e) => { toast.error(e.message); setMedals([]) }),
    [toast],
  )
  useEffect(() => { loadMedals() }, [loadMedals])

  // A medal named in the URL that the club no longer holds falls back to the
  // first, rather than leaving an empty screen with no way out — the same rule
  // the Accounts season picker follows.
  const medalId = useMemo(() => {
    if (!medals?.length) return ''
    return medals.some((m) => m.medal_id === urlMedal) ? urlMedal : medals[0].medal_id
  }, [medals, urlMedal])

  // The medal rides in the URL so a link to one count is shareable and survives
  // a refresh. `replace` keeps the back button leaving the screen rather than
  // walking the medal history.
  const setUrl = (next) => setParams(next, { replace: true })
  const setTab = (t) => {
    setOpenFixture(null)
    setUrl({ ...(t === 'hub' ? {} : { tab: t }), ...(medalId ? { medal: medalId } : {}) })
  }
  const setMedal = (id) => {
    setOpenFixture(null)
    setUrl({ ...(tab === 'hub' ? {} : { tab }), medal: id })
  }

  const addMedal = async () => {
    const name = window.prompt('What is this medal called?', 'Best & Fairest')
    if (!name || !name.trim()) return
    try {
      const created = await api.votesCreateMedal({ name: name.trim() })
      await loadMedals()
      setOpenFixture(null)
      // Straight to Settings: a brand-new medal is off, has no grades and no
      // link, so the Games tab would show it with nothing to do.
      setUrl({ tab: 'settings', medal: created.medal_id })
    } catch (e) { toast.error(e.message || 'Could not add the medal') }
  }

  const tabs = useMemo(() => [
    { key: 'hub', label: 'Games' },
    { key: 'leaderboard', label: 'Leaderboard' },
    ...(canManage ? [{ key: 'settings', label: 'Settings' }] : []),
  ], [canManage])

  if (medals === null) return <BetterSelectLayout title="Votes"><PbSpinner message="Loading votes…" /></BetterSelectLayout>

  return (
    <BetterSelectLayout title="Votes">
      <MedalBar medals={medals} medalId={medalId} onSelect={setMedal}
        onAdd={canManage ? addMedal : null} canManage={canManage} />

      <div className="flex items-center gap-1.5 mb-5 border-b pb-hairline">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3.5 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.key ? 'border-pb-accent text-pb-accent' : 'border-transparent text-pb-faint hover:text-pb-text'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'hub' && (openFixture
        ? <FixtureDetail fixtureId={openFixture} medalId={medalId} onBack={() => setOpenFixture(null)} />
        : <VotesHub canManage={canManage} medalId={medalId} onOpenFixture={setOpenFixture} />)}
      {tab === 'leaderboard' && <VotesLeaderboard medalId={medalId} />}
      {tab === 'settings' && canManage && (
        <VotesSettings canManage={canManage} medalId={medalId} gradeOptions={grades}
          medalCount={medals.length} onChanged={loadMedals}
          onDeleted={() => { loadMedals(); setUrl({ tab: 'settings' }) }} />
      )}
    </BetterSelectLayout>
  )
}
