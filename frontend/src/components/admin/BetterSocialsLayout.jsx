import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterSocials runs as its own module surface. Single tool today (the post
// designer); the nav is ready for more (milestone posts, scheduling) later.
const NAV = [
  { to: '/admin/social-post', label: 'Post Designer', icon: 'share', cap: CAP.MANAGE_SOCIAL, exact: true },
]

export default function BetterSocialsLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Socials" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
