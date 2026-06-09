import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

function SeasonPicker({ seasons, value, onChange, placeholder, exclude }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value || null)}
      className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
    >
      <option value="">{placeholder}</option>
      {seasons
        .filter(s => s.id !== exclude)
        .map(s => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
    </select>
  )
}

function MergeBuilder({ seasons, onMerged }) {
  const [alias, setAlias] = useState(null)
  const [canonical, setCanonical] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const canMerge = alias && canonical && alias !== canonical
  const aliasName = seasons.find(s => s.id === alias)?.name
  const canonicalName = seasons.find(s => s.id === canonical)?.name

  async function handleMerge() {
    if (!canMerge) return
    setBusy(true)
    setError(null)
    try {
      await api.adminCreateSeasonMerge(canonical, alias)
      setAlias(null)
      setCanonical(null)
      onMerged()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-5 mb-6">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge Seasons</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Use this when one calendar year has been split into multiple seasons by the data source — e.g. "Summer 2025/26" and "Winter 2025/26" are both really 2025/26.
        Stats from the variant will roll up into the canonical season everywhere (leaderboards, player profiles, records). The variant is hidden from the season dropdown but kept in the database, so this is fully reversible.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Variant to merge (will be hidden)</label>
          <SeasonPicker seasons={seasons} value={alias} onChange={setAlias} placeholder="— Select variant —" exclude={canonical} />
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Merge into (keep this season)</label>
          <SeasonPicker seasons={seasons} value={canonical} onChange={setCanonical} placeholder="— Select canonical —" exclude={alias} />
        </div>
      </div>
      {alias && canonical && alias === canonical && (
        <p className="font-mono text-[11px] text-pb-amber mb-3">Pick two different seasons.</p>
      )}
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <button
        onClick={handleMerge}
        disabled={!canMerge || busy}
        className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
        style={{ background: 'var(--pb-accent)' }}
      >
        {busy ? 'Merging…' : `Merge ${aliasName || '…'} into ${canonicalName || '…'}`}
      </button>
    </div>
  )
}

function MergeHistory({ refreshKey, onChanged }) {
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.adminListSeasonMerges().then(setHistory).catch(() => {})
  }, [refreshKey])

  async function handleUndo(entry) {
    setUndoing(entry.id)
    setError(null)
    try {
      await api.adminUndoSeasonMerge(entry.id)
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setUndoing(null)
    }
  }

  if (history.length === 0) return null

  return (
    <div className="mt-8">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge History</p>
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <div className="flex flex-col gap-2">
        {history.map(entry => (
          <div
            key={entry.id}
            className={`flex items-center gap-3 rounded border px-4 py-3 text-sm pb-hairline ${entry.undone ? 'opacity-40' : 'bg-pb-surface'}`}
          >
            <div className="flex-1 min-w-0">
              <span className="text-pb-text font-medium">{entry.canonical_name}</span>
              <span className="text-pb-faint mx-2">←</span>
              <span className="text-pb-amber">{entry.alias_name}</span>
              <span className="font-mono text-[10px] text-pb-faintest ml-3">{new Date(entry.merged_at).toLocaleDateString()}</span>
            </div>
            {entry.undone ? (
              <span className="font-mono text-[10px] text-pb-faintest shrink-0">Undone</span>
            ) : (
              <button
                onClick={() => handleUndo(entry)}
                disabled={undoing === entry.id}
                className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-faint hover:text-pb-text transition-colors shrink-0 disabled:opacity-50"
              >
                {undoing === entry.id ? 'Undoing…' : 'Undo'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AdminSeasons() {
  const [seasons, setSeasons] = useState([])
  const [mergeRefresh, setMergeRefresh] = useState(0)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  function refresh() {
    api.adminListSeasons().then(setSeasons).catch(() => {})
    setMergeRefresh(n => n + 1)
  }

  useEffect(() => {
    refresh()
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
          Seasons are created automatically when data is synced automatically. Use the arrows to change the display order.
        </p>
        {saveError && (
          <p className="text-red-500 text-sm mb-4">{saveError}</p>
        )}
        <div className="pb-card overflow-hidden mb-8">
          {seasons.length === 0 && (
            <div className="px-4 py-8 text-center font-mono text-[11px] text-pb-faint">No seasons found</div>
          )}
          {seasons.map((s, i) => (
            <div key={s.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex flex-col gap-0.5 shrink-0">
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
                <div className="min-w-0">
                  <span className={`text-sm ${s.alias_of ? 'text-pb-faint italic' : 'text-pb-text'}`}>{s.name}</span>
                  {s.year && <span className="font-mono text-[10px] text-pb-faintest ml-2">{s.year}</span>}
                  {s.alias_of && (
                    <div className="font-mono text-[10px] text-pb-amber mt-0.5 truncate">
                      → merged into {seasons.find(x => x.id === s.alias_of)?.name || '(unknown)'}
                    </div>
                  )}
                  {s.aliases?.length > 0 && (
                    <div className="font-mono text-[10px] text-pb-faintest mt-0.5 truncate">
                      Includes: {s.aliases.map(a => a.name).join(', ')}
                    </div>
                  )}
                </div>
              </div>
              <span className="font-mono text-[10px] text-pb-faint shrink-0">
                {s.synced_at ? `Synced ${new Date(s.synced_at).toLocaleDateString('en-AU')}` : 'Not synced'}
              </span>
            </div>
          ))}
        </div>

        <MergeBuilder seasons={seasons} onMerged={refresh} />
        <MergeHistory refreshKey={mergeRefresh} onChanged={refresh} />
      </div>
    </AdminLayout>
  )
}
