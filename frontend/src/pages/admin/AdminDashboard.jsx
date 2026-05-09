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
        <h1 className="text-2xl font-display font-bold text-white mb-1">
          Welcome{user?.display_name ? `, ${user.display_name}` : ''}
        </h1>
        {settings && (
          <p className="text-slate-400 text-sm mb-6">
            Managing <span className="text-white">{settings.name}</span>
            {settings.slug && (
              <>
                {' · '}
                <Link
                  to={`/${settings.slug}/dashboard`}
                  className="text-accent hover:underline"
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
              className="bg-navy-900 border border-navy-700 rounded-lg p-4 hover:border-accent transition-colors group"
            >
              <div className="font-medium text-white group-hover:text-accent transition-colors">
                {link.label}
              </div>
              <div className="text-sm text-slate-400 mt-0.5">{link.desc}</div>
            </Link>
          ))}
        </div>

        {seasons.length > 0 && (
          <div>
            <h2 className="section-label mb-3">Seasons</h2>
            <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
              {seasons.slice(0, 5).map((s, i) => (
                <div key={s.id} className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
                  <span className="text-white text-sm">{s.name}</span>
                  <span className="text-slate-500 text-xs">{s.year || '—'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
