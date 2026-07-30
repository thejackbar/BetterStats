// BetterSelect → Votes. Brownlow-style best-player vote collection.
//
// Three tabs:
//   Hub         — every played game with its voting state, ballot progress,
//                 bulk open/lock/nudge and sharing. (Was "Fixtures".)
//   Leaderboard — the season count, club-wide or per grade, replayable "as at"
//                 any round, with a podium, rank movement, form and a
//                 presentation mode for awards night.
//   Settings    — who votes, ballot shape, counting method, tie policy,
//                 eligibility source, auto-close and the public link.
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { CAP } from '../../../lib/capabilities'
import VotesHub from './votes/VotesHub'
import VotesLeaderboard from './votes/VotesLeaderboard'
import FixtureDetail from './votes/FixtureDetail'
import VotesSettings from './votes/VotesSettings'

export default function AdminVotes() {
  const { hasCapability } = useAuth()
  const canManage = hasCapability(CAP.MANAGE_VOTES)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'hub'
  const [openFixture, setOpenFixture] = useState(null)

  const setTab = (t) => { setOpenFixture(null); setParams(t === 'hub' ? {} : { tab: t }, { replace: true }) }

  const tabs = useMemo(() => [
    { key: 'hub', label: 'Games' },
    { key: 'leaderboard', label: 'Leaderboard' },
    ...(canManage ? [{ key: 'settings', label: 'Settings' }] : []),
  ], [canManage])

  return (
    <BetterSelectLayout title="Votes">
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
        ? <FixtureDetail fixtureId={openFixture} onBack={() => setOpenFixture(null)} />
        : <VotesHub canManage={canManage} onOpenFixture={setOpenFixture} />)}
      {tab === 'leaderboard' && <VotesLeaderboard />}
      {tab === 'settings' && canManage && <VotesSettings canManage={canManage} />}
    </BetterSelectLayout>
  )
}
