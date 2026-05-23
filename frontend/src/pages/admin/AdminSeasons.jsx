import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminSeasons() {
  const [seasons, setSeasons] = useState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    api.adminListSeasons().then(setSeasons).catch(() => {})
  }, [])

  function move(index, direction) {
    const next = [...seasons]
    const swapWith = index + direction
    if (swapWith < 0 || swapWith >= next.length) return
    ;[next[index], next[swapWith]] = [next[swapWith], next[index]]
    setSeasons(next)
    setDirty(true)
    setSaveError(null)
  }

  async function saveOrder() {
    setSaving(true)
    setSaveError(null)
    try {
      await api.adminReorderSeasons(seasons.map((s, i) => ({ id: s.id, display_order: i + 1 })))
      setDirty(false)
    } catch (e) {
      setSaveError(e.message || 'Failed to save order')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-2xl">
        <div className="flex items-center justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Seasons</h1>
          {dirty && (
            <button
              onClick={saveOrder}
              disabled={saving}
              className="px-4 py-1.5 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save order'}
            </button>
          )}
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Seasons are created automatically when data is synced. Use the arrows to change the display order.
        </p>
        {saveError && (
          <p className="text-red-500 text-sm mb-4">{saveError}</p>
        )}
        <div className="pb-card overflow-hidden">
          {seasons.length === 0 && (
            <div className="px-4 py-8 text-center font-mono text-[11px] text-pb-faint">No seasons found</div>
          )}
          {seasons.map((s, i) => (
            <div key={s.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="flex items-center gap-3">
                <div className="flex flex-col gap-0.5">
                  <button
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    className="text-pb-faint hover:text-pb-text disabled:opacity-20 leading-none"
                    aria-label="Move up"
                  >
                    ▲
                  </button>
                  <button
                    onClick={() => move(i, 1)}
                    disabled={i === seasons.length - 1}
                    className="text-pb-faint hover:text-pb-text disabled:opacity-20 leading-none"
                    aria-label="Move down"
                  >
                    ▼
                  </button>
                </div>
                <div>
                  <span className="text-pb-text text-sm">{s.name}</span>
                  {s.year && <span className="font-mono text-[10px] text-pb-faintest ml-2">{s.year}</span>}
                </div>
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
