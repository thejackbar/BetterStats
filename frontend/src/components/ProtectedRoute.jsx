import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import TrialBanner from './admin/TrialBanner'
import SetupReturnBar from './admin/SetupReturnBar'

export default function ProtectedRoute({ children, requireRole, requireModule, requireCore, requireActivePlan }) {
  const { user, hasModule, coreLive } = useAuth()
  const location = useLocation()

  if (user === undefined) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--pb-accent)', borderTopColor: 'transparent' }} />
      </div>
    )
  }

  // Remember where the user was trying to go so Login can send them back there
  // after a successful sign-in, instead of always dumping them on /admin.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />

  // requireRole accepts a single role string (the original shape) or an
  // array of roles (e.g. Sales Workspace: ["super_admin", "sales"]) — a
  // super_admin always passes either form, matching every existing
  // single-string caller unchanged.
  //
  // A 'sales' user is deliberately NOT given the ordinary "no requireRole
  // set = allowed" default every other role gets — most club-admin routes
  // (the dashboard, Players, Settings…) carry no requireRole at all, since
  // they only ever expected a real club_admin/club_member to reach them. A
  // sales account's one ClubMembership is pinned to the platform's internal
  // outreach org (see routers/auth.py's login note), so without this it
  // reads as that org's own club_admin and lands on an ordinary — and
  // meaningless — admin dashboard. Sales is restricted to routes that
  // explicitly opt it in via requireRole; today that's Sales Workspace only.
  const isSales = user.role === 'sales'
  const requireRoleIncludesSales = Array.isArray(requireRole) ? requireRole.includes('sales') : requireRole === 'sales'
  const roleAllowed = user.role === 'super_admin' || (
    isSales
      ? requireRoleIncludesSales
      : (!requireRole || (Array.isArray(requireRole) ? requireRole.includes(user.role) : user.role === requireRole))
  )
  if (!roleAllowed) {
    return <Navigate to={isSales ? '/admin/super/crm/workspace' : '/admin'} replace />
  }

  // Module entitlement gate — clubs not entitled to the module are bounced back
  // to the dashboard, where the locked tile explains the add-on.
  if (requireModule && !hasModule(requireModule)) {
    return <Navigate to="/admin" replace />
  }

  // BetterStats (Core) gate — a lapsed Core trial / cancelled Core subscription
  // blocks the club's own BetterStats admin data tools. Bounced to the
  // dashboard, where the locked BetterStats tile (and the all-expired reminder)
  // point the primary admin at subscribing. Super admins read coreLive=true, so
  // they're never gated. The Account, Settings, Users and Setup pages are never
  // marked requireCore, so a lapsed club can always still reach billing to
  // subscribe and recover.
  if (requireCore && !coreLive) {
    return <Navigate to="/admin" replace />
  }

  // All-expired gate — once EVERYTHING has lapsed (Core not live AND no add-on
  // entitled), even the general admin pages that aren't BetterStats data tools
  // (Settings, Activity, Setup) are closed off, leaving only the dashboard,
  // Login and Plan & Billing reachable so the club can subscribe and recover.
  // A club with any live module (e.g. an add-on still in trial) is NOT
  // all-expired, so those pages stay open for it. Super admins and fail-open
  // (coreLive defaults true) are never caught by this.
  if (requireActivePlan) {
    const anyModule = Array.isArray(user.entitlements?.modules) && user.entitlements.modules.length > 0
    const allExpired = user.role !== 'super_admin' && !coreLive && !anyModule
    if (allExpired) return <Navigate to="/admin" replace />
  }

  return (
    <>
      <TrialBanner />
      <SetupReturnBar />
      {children}
    </>
  )
}
