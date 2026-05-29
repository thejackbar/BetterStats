import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'

const TILES = [
  { to: '/admin/betterselect/fixtures', label: 'Fixtures', icon: '◴', cap: CAP.MANAGE_FIXTURES,
    desc: 'Sync from PlayHQ or add fixtures by hand (friendlies, pre-season).' },
  { to: '/admin/betterselect/teams', label: 'Teams', icon: '⊞', cap: CAP.MANAGE_SELECTIONS,
    desc: 'Your club’s teams — auto-seeded from match data or created manually.' },
  { to: '/admin/betterselect/availability', label: 'Availability', icon: '✓', cap: CAP.MANAGE_SELECTIONS,
    desc: 'Mark who’s available each weekend across all upcoming fixtures.' },
  { to: '/admin/betterselect/fixtures', label: 'Selection', icon: '✦', cap: CAP.MANAGE_SELECTIONS,
    desc: 'Pick your XI per fixture from the available pool — open a fixture and hit Select.' },
]

export default function BetterSelectHome() {
  const { hasCapability } = useAuth()
  const [counts, setCounts] = useState({ fixtures: null, teams: null })

  useEffect(() => {
    if (hasCapability(CAP.MANAGE_FIXTURES)) {
      api.bsListFixtures(true).then(f => setCounts(c => ({ ...c, fixtures: f.length }))).catch(() => {})
    }
    if (hasCapability(CAP.MANAGE_SELECTIONS)) {
      api.bsListTeams().then(t => setCounts(c => ({ ...c, teams: t.length }))).catch(() => {})
    }
  }, [hasCapability])

  return (
    <BetterSelectLayout title="BetterSelect">
      <div className="space-y-6">
        <div>
          <h2 className="font-display font-bold text-2xl mb-1">Availability &amp; team selection</h2>
          <p className="text-pb-faint text-sm max-w-2xl">
            Plan your weekends — track who’s available and pick your sides, powered by your BetterStats data.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {TILES.filter(t => t.cap == null || hasCapability(t.cap)).map(t => (
            <Link key={t.to} to={t.to} className="pb-card p-5 hover:border-pb-accent/40 transition-colors group">
              <div className="flex items-center justify-between mb-3">
                <span className="text-2xl">{t.icon}</span>
                {t.label === 'Fixtures' && counts.fixtures != null && (
                  <span className="font-mono text-[11px] text-pb-faint">{counts.fixtures} upcoming</span>
                )}
                {t.label === 'Teams' && counts.teams != null && (
                  <span className="font-mono text-[11px] text-pb-faint">{counts.teams} teams</span>
                )}
              </div>
              <div className="font-semibold group-hover:text-pb-accent">{t.label}</div>
              <div className="text-pb-faint text-xs mt-1 leading-relaxed">{t.desc}</div>
            </Link>
          ))}
        </div>
      </div>
    </BetterSelectLayout>
  )
}
