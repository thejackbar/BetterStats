import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminDashboard() {
  const { user } = useAuth()
  const [settings, setSettings] = useState(null)
  const [seasons, setSeasons] = useState([])

  useEffect(() => {
    api.adminGetSettings().then(setSettings).catch(() => {})
    api.adminListSeasons().then(setSeasons).catch(() => {})
  }, [])

  const quickLinks = [
    { to: '/admin/players', label: 'Manage Players', desc: 'Edit display names' },
    { to: '/admin/awards', label: 'Awards', desc: 'Add season awards & achievements' },
    { to: '/admin/merge', label: 'Merge Players', desc: 'Fix duplicate player entries' },
    { to: '/admin/sync', label: 'Data Sync', desc: 'Trigger sync & view sync log' },
    { to: '/admin/games', label: 'View Matches', desc: 'Browse match results' },
    { to: '/admin/settings', label: 'Club Settings', desc: 'Name, colours, contact' },
  ]

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">
          Welcome{user?.display_name ? `, ${user.display_name}` : ''}
        </h1>
        {settings && (
          <p className="text-pb-faint text-sm mb-6">
            Managing <span className="text-pb-text">{settings.name}</span>
            {settings.slug && (
              <>
                {' · '}
                <Link
                  to={`/${settings.slug}/dashboard`}
                  className="hover:underline transition-colors"
                  style={{ color: 'var(--pb-accent)' }}
                  target="_blank"
                >
                  View public page ↗
                </Link>
              </>
            )}
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
          {quickLinks.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className="pb-card p-4 hover:bg-pb-surface2 transition-colors group"
            >
              <div className="font-medium text-pb-text group-hover:text-pb-accent transition-colors text-sm"
                style={{ ['--tw-text-opacity']: '1' }}
                onMouseEnter={e => e.currentTarget.style.color = 'var(--pb-accent)'}
                onMouseLeave={e => e.currentTarget.style.color = ''}
              >
                {link.label}
              </div>
              <div className="text-sm text-pb-faint mt-0.5">{link.desc}</div>
            </Link>
          ))}
        </div>

        {seasons.length > 0 && (
          <div>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Seasons</p>
            <div className="pb-card overflow-hidden">
              {seasons.slice(0, 5).map((s, i) => (
                <div key={s.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                  <span className="text-pb-text text-sm">{s.name}</span>
                  <span className="font-mono text-[10px] text-pb-faintest">{s.year || '—'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
