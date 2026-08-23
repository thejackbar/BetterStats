import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { MODULE } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import AdminLayout from '../../components/admin/AdminLayout'

const BRAND = moduleBrand('socials')

// BetterSocials — the club's outward face. The public Website (Core, every club)
// plus the social Post Designer (Better tier). Each card opens its own surface,
// or shows an upsell when the plan doesn't include it.

function ModuleName({ name }) {
  return (
    <span className="font-display font-bold text-lg">
      Better<span style={{ color: 'var(--pb-accent)' }}>{name.slice('Better'.length)}</span>
    </span>
  )
}

function SubCard({ name, blurb, to, entitled }) {
  if (entitled) {
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

export default function BetterSocialsHome() {
  const { hasModule } = useAuth()
  return (
    <AdminLayout>
      <div className="max-w-3xl" style={{ '--pb-accent': BRAND.accent, '--pb-accent-rgb': BRAND.accentRgb }}>
        <div className="flex items-center gap-3 mb-1">
          <img src={BRAND.logo} alt="" className="w-9 h-9 rounded-lg" />
          <h1 className="font-display font-bold text-2xl text-pb-text">
            Better<span style={{ color: 'var(--pb-accent)' }}>Socials</span>
          </h1>
        </div>
        <p className="text-pb-faint text-sm mb-6">Your club's outward face. A public website and social posts in one place.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SubCard
            name="BetterWebsite" to="/admin/website" entitled
            blurb="Build your public club website: news, pages, menus, honours, committee and galleries."
          />
          <SubCard
            name="BetterPosts" to="/admin/social-post" entitled={hasModule(MODULE.SOCIALS)}
            blurb="Auto-post lineups, scorecards, milestones and match summaries."
          />
        </div>
      </div>
    </AdminLayout>
  )
}
