import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { MODULE, tierInfo } from '../../lib/modules'
import AdminLayout from '../../components/admin/AdminLayout'

// BetterAdmin — the club back-office umbrella. One hub for the operational
// modules (BetterFees + BetterComms today, BetterMerch next). Each card opens
// that module's own surface, or shows an upsell / "soon" when unavailable.

function ModuleName({ name }) {
  return (
    <span className="font-display font-bold text-lg">
      Better<span style={{ color: 'var(--pb-accent)' }}>{name.slice('Better'.length)}</span>
    </span>
  )
}

function SubCard({ name, blurb, to, built, entitled, requiredTier }) {
  if (built && entitled) {
    return (
      <Link
        to={to}
        className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
        style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
      >
        <div className="flex items-center justify-between gap-4">
          <ModuleName name={name} />
          <span className="text-2xl group-hover:translate-x-1 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
        </div>
        <div className="text-pb-faint text-sm mt-1">{blurb}</div>
      </Link>
    )
  }
  if (!built) {
    return (
      <div className="pb-card p-5 opacity-70">
        <div className="flex items-center justify-between gap-4">
          <ModuleName name={name} />
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5">SOON</span>
        </div>
        <div className="text-pb-faint text-sm mt-1">{blurb}</div>
      </div>
    )
  }
  const tier = tierInfo(requiredTier)
  return (
    <div className="pb-card p-5 opacity-75" style={{ borderStyle: 'dashed' }}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-pb-faint"><span aria-hidden>🔒</span><ModuleName name={name} /></div>
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5 uppercase">{tier.label} plan</span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{blurb}</div>
    </div>
  )
}

export default function BetterAdminHome() {
  const { hasModule } = useAuth()
  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">
          Better<span style={{ color: 'var(--pb-accent)' }}>Admin</span>
        </h1>
        <p className="text-pb-faint text-sm mb-6">Your club's back office — money, comms and merch in one place.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SubCard
            name="BetterFees" to="/admin/fees" built entitled={hasModule(MODULE.FEES)} requiredTier="best"
            blurb="Fee schedules and match-day payment tracking for the treasurer."
          />
          <SubCard
            name="BetterComms" to="/admin/comms" built entitled={hasModule(MODULE.COMMS)} requiredTier="best"
            blurb="Bulk email to your member database — newsletters and announcements."
          />
          <SubCard
            name="BetterMerch" built={false} entitled={false} requiredTier="best"
            blurb="Track merch stock and sales. Coming soon."
          />
        </div>
      </div>
    </AdminLayout>
  )
}
