import { CAP } from '../../lib/capabilities'
import { useAuth } from '../../contexts/AuthContext'
import ModuleLayout from './ModuleLayout'

// BetterSocials runs as its own module surface: the post designer, and in an
// association workspace the Performance Tracker (a round across every
// competition, read from match links, routers/performance.py).
const NAV = [
  { to: '/admin/social-post', label: 'Post Designer', icon: 'share', cap: CAP.MANAGE_SOCIAL, exact: true },
]
const ASSOCIATION_NAV = [
  ...NAV,
  { to: '/admin/performance', label: 'Performance Tracker', icon: 'list', cap: CAP.MANAGE_SOCIAL, exact: true },
]

export default function BetterSocialsLayout({ children, title, actions }) {
  const { user } = useAuth()
  const nav = user?.workspace_kind === 'association' ? ASSOCIATION_NAV : NAV
  return (
    <ModuleLayout moduleName="Socials" nav={nav} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
