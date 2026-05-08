import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminSeasons() {
  const [seasons, setSeasons] = useState([])

  useEffect(() => {
    api.adminListSeasons().then(setSeasons).catch(() => {})
  }, [])

  return (
    <AdminLayout>
      <div className="max-w-2xl">
        <h1 className="text-xl font-display font-bold text-white mb-4">Seasons</h1>
        <p className="text-slate-400 text-sm mb-4">
          Seasons are created automatically when data is synced from PlayHQ.
        </p>
        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          {seasons.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">No seasons found</div>
          )}
          {seasons.map((s, i) => (
            <div key={s.id} className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
              <div>
                <span className="text-white text-sm">{s.name}</span>
                <span className="text-slate-500 text-xs ml-2">{s.year || ''}</span>
              </div>
              <span className="text-slate-500 text-xs">
                {s.synced_at ? `Synced ${new Date(s.synced_at).toLocaleDateString('en-AU')}` : 'Not synced'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
