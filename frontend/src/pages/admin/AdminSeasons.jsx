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
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Seasons</h1>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Seasons are created automatically when data is synced from PlayHQ.
        </p>
        <div className="pb-card overflow-hidden">
          {seasons.length === 0 && (
            <div className="px-4 py-8 text-center font-mono text-[11px] text-pb-faint">No seasons found</div>
          )}
          {seasons.map((s, i) => (
            <div key={s.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div>
                <span className="text-pb-text text-sm">{s.name}</span>
                {s.year && <span className="font-mono text-[10px] text-pb-faintest ml-2">{s.year}</span>}
              </div>
              <span className="font-mono text-[10px] text-pb-faint">
                {s.synced_at ? `Synced ${new Date(s.synced_at).toLocaleDateString('en-AU')}` : 'Not synced'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
