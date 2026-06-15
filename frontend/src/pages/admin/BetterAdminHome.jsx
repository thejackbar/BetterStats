import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { MODULE } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import AdminLayout from '../../components/admin/AdminLayout'

const BRAND = moduleBrand('admin')

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

function SubCard({ name, blurb, to, built, entitled }) {
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
  return (
    <div className="pb-card p-5 opacity-75" style={{ borderStyle: 'dashed' }}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-pb-faint"><span aria-hidden>🔒</span><ModuleName name={name} /></div>
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5 uppercase">Add-on</span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{blurb}</div>
    </div>
  )
}

export default function BetterAdminHome() {
  const { hasModule } = useAuth()
  return (
    <AdminLayout>
      <div className="max-w-3xl" style={{ '--pb-accent': BRAND.accent, '--pb-accent-rgb': BRAND.accentRgb }}>
        <div className="flex items-center gap-3 mb-1">
          <img src={BRAND.logo} alt="" className="w-9 h-9 rounded-lg" />
          <h1 className="font-display font-bold text-2xl text-pb-text">
            Better<span style={{ color: 'var(--pb-accent)' }}>Admin</span>
          </h1>
        </div>
        <p className="text-pb-faint text-sm mb-6">Your club's back office — money, comms and merch in one place.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SubCard
            name="BetterFees" to="/admin/fees" built entitled={hasModule(MODULE.FEES)}
            blurb="Fee schedules and match-day payment tracking for the treasurer."
          />
          <SubCard
            name="BetterComms" to="/admin/comms" built entitled={hasModule(MODULE.COMMS)}
            blurb="Bulk email to your member database — newsletters and announcements."
          />
          <SubCard
            name="BetterMerch" to="/admin/merch" built entitled={hasModule(MODULE.MERCH)}
            blurb="Track club stock — apparel, equipment and canteen — with low-stock alerts."
          />
        </div>
      </div>
    </AdminLayout>
  )
}
