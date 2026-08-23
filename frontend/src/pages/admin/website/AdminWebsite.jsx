import { useState } from 'react'
import { Link } from 'react-router-dom'
import AdminLayout from '../../../components/admin/AdminLayout'
import { useAuth } from '../../../contexts/AuthContext'
import WebsiteSettings from './WebsiteSettings'
import WebsiteNewsAdmin from './WebsiteNewsAdmin'
import WebsitePagesAdmin from './WebsitePagesAdmin'
import WebsiteHonoursAdmin from './WebsiteHonoursAdmin'
import WebsiteCommitteeAdmin from './WebsiteCommitteeAdmin'
import WebsiteGalleryAdmin from './WebsiteGalleryAdmin'

const TABS = [
  { key: 'settings', label: 'Site setup', Comp: WebsiteSettings },
  { key: 'news', label: 'News', Comp: WebsiteNewsAdmin },
  { key: 'pages', label: 'Pages', Comp: WebsitePagesAdmin },
  { key: 'honours', label: 'Honours', Comp: WebsiteHonoursAdmin },
  { key: 'committee', label: 'Committee', Comp: WebsiteCommitteeAdmin },
  { key: 'gallery', label: 'Gallery', Comp: WebsiteGalleryAdmin },
]

export default function AdminWebsite() {
  const { user } = useAuth()
  const [tab, setTab] = useState('settings')
  const Active = TABS.find(t => t.key === tab)?.Comp || WebsiteSettings

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Website</h1>
          {user?.club_slug && (
            <Link
              to={`/${user.club_slug}/website`}
              target="_blank"
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5"
            >
              VIEW PUBLIC WEBSITE ↗
            </Link>
          )}
        </div>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          Build your club's public website: news, info pages, honour boards, committee and photo
          galleries. Living alongside your stats at <span className="font-mono text-pb-dim">/{user?.club_slug || 'yourclub'}/website</span>.
        </p>

        {/* Tabs */}
        <div className="flex flex-wrap gap-1 border-b pb-hairline-b mb-6">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-2 text-[12px] font-mono font-semibold tracking-wide2 border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? 'text-pb-text border-pb-accent'
                  : 'text-pb-faint border-transparent hover:text-pb-text'
              }`}
              style={tab === t.key ? { borderColor: 'var(--pb-accent)' } : {}}
            >
              {t.label.toUpperCase()}
            </button>
          ))}
        </div>

        <Active />
      </div>
    </AdminLayout>
  )
}
