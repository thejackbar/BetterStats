import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

function GradePicker({ grades, value, onChange, placeholder, exclude }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value || null)}
      className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
    >
      <option value="">{placeholder}</option>
      {grades
        .filter(g => g.grade_name !== exclude)
        .map(g => (
          <option key={g.grade_name} value={g.grade_name}>
            {g.display_name} ({g.games} games · {g.runs} runs)
          </option>
        ))}
    </select>
  )
}

function MergeBuilder({ orgId, grades, onMerged }) {
  const [alias, setAlias] = useState(null)
  const [canonical, setCanonical] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const canMerge = alias && canonical && alias !== canonical

  async function handleMerge() {
    if (!canMerge) return
    setBusy(true)
    setError(null)
    try {
      await api.mergeGrades(orgId, alias, canonical)
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
    <div className="pb-card p-5 mb-8">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge Grades</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Use this when one grade is sponsored or renamed across seasons (e.g. "One Day Grade 3" and "One Day Grade 3 - East" are actually the same).
        Stats will be combined in the player by-grade view.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Variant to merge</label>
          <GradePicker grades={grades} value={alias} onChange={setAlias} placeholder="— Select grade —" exclude={canonical} />
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Merge into (keep this name)</label>
          <GradePicker grades={grades} value={canonical} onChange={setCanonical} placeholder="— Select canonical grade —" exclude={alias} />
        </div>
      </div>
      {alias && canonical && alias === canonical && (
        <p className="font-mono text-[11px] text-pb-amber mb-3">Pick two different grades.</p>
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
        {busy ? 'Merging…' : `Merge ${alias || '…'} into ${canonical || '…'}`}
      </button>
    </div>
  )
}

function GradeList({ grades }) {
  if (!grades.length) return <p className="font-mono text-[11px] text-pb-faint">No grades found for this club.</p>
  return (
    <div className="pb-card overflow-hidden">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-2.5 pl-5">GRADE</th>
            <th className="font-medium py-2.5 text-right">GAMES</th>
            <th className="font-medium py-2.5 pr-5 text-right">RUNS</th>
          </tr>
        </thead>
        <tbody>
          {grades.map((g, i) => (
            <tr key={g.grade_name} className={`${i ? 'pb-hairline-t' : ''} align-top hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5">
                <div className="text-pb-text">{g.display_name}</div>
                {g.display_name !== g.grade_name && (
                  <div className="font-mono text-[10px] text-pb-faintest mt-0.5">raw: {g.grade_name}</div>
                )}
                {g.aliases?.length > 0 && (
                  <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                    Includes: {g.aliases.join(', ')}
                  </div>
                )}
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{g.games}</td>
              <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{g.runs}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MergeHistory({ orgId, refreshKey, onChanged }) {
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getGradeMergeHistory(orgId).then(setHistory).catch(() => {})
  }, [orgId, refreshKey])

  async function handleUndo(entry) {
    setUndoing(entry.id)
    setError(null)
    try {
      await api.undoGradeMerge(entry.id, orgId)
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setUndoing(null)
    }
  }

  if (history.length === 0) return null

  return (
    <div className="mt-10">
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

function RenameGrades() {
  const [grades, setGrades] = useState(null)
  const [editing, setEditing] = useState(null) // { original_name, value }
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function load() {
    api.adminListGrades().then(setGrades).catch(() => setGrades([]))
  }

  useEffect(() => { load() }, [])

  async function saveRename() {
    if (!editing) return
    setSaving(true)
    setError(null)
    try {
      await api.adminRenameGrade(editing.original_name, editing.value || null)
      setEditing(null)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function clearOverride(originalName) {
    setSaving(true)
    setError(null)
    try {
      await api.adminRenameGrade(originalName, null)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!grades) return <PbSpinner message="Loading grades…" />

  return (
    <div className="mt-10">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">Rename Grades</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Set a display name for a grade. The display name is shown everywhere instead of the original sync'd name.
        Useful for shortening sponsor-suffixed names like "One Day Grade 5 - Black" → "One Day Grade 5".
      </p>
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <div className="pb-card overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-2.5 pl-5">ORIGINAL NAME</th>
              <th className="font-medium py-2.5">DISPLAY NAME</th>
              <th className="font-medium py-2.5 pr-5 text-right">GAMES</th>
            </tr>
          </thead>
          <tbody>
            {grades.map((g, i) => (
              <tr key={g.original_name} className={`${i ? 'pb-hairline-t' : ''} align-middle`}>
                <td className="py-2.5 pl-5 text-pb-dim font-mono text-[11px] max-w-[220px] truncate">{g.original_name}</td>
                <td className="py-2 pr-3">
                  {editing?.original_name === g.original_name ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        type="text"
                        value={editing.value}
                        onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                        placeholder="Blank to clear override"
                        className="flex-1 bg-pb-surface2 border rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none"
                        style={{ borderColor: 'var(--pb-accent)' }}
                        onKeyDown={e => { if (e.key === 'Enter') saveRename(); if (e.key === 'Escape') setEditing(null) }}
                      />
                      <button
                        onClick={saveRename}
                        disabled={saving}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 shrink-0"
                        style={{ background: 'var(--pb-accent)' }}
                      >
                        SAVE
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors shrink-0"
                      >
                        CANCEL
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span
                        className={`flex-1 text-sm ${g.display_name_override ? 'text-pb-text font-medium' : 'text-pb-faintest italic'}`}
                      >
                        {g.display_name_override || 'no override'}
                      </span>
                      <button
                        onClick={() => setEditing({ original_name: g.original_name, value: g.display_name_override || '' })}
                        className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-faint hover:text-pb-text transition-colors shrink-0"
                      >
                        Edit
                      </button>
                      {g.display_name_override && (
                        <button
                          onClick={() => clearOverride(g.original_name)}
                          disabled={saving}
                          className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-red/60 hover:text-pb-red transition-colors shrink-0 disabled:opacity-50"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  )}
                </td>
                <td className="py-2.5 pr-5 font-mono text-pb-dim text-right text-[11px]">{g.games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function AdminGrades() {
  const { user } = useAuth()
  const [orgId, setOrgId] = useState(null)
  const [grades, setGrades] = useState(null)
  const [loading, setLoading] = useState(true)
  const [historyKey, setHistoryKey] = useState(0)

  useEffect(() => {
    if (user?.club_id) {
      setOrgId(user.club_id)
    } else {
      api.adminGetSettings().then(s => setOrgId(s.id)).catch(() => {})
    }
  }, [user])

  function load() {
    if (!orgId) return
    setLoading(true)
    api.listGradesWithStats(orgId)
      .then(setGrades)
      .catch(() => setGrades([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [orgId])

  function refresh() {
    setHistoryKey(k => k + 1)
    load()
  }

  if (!orgId || loading) {
    return (
      <AdminLayout>
        <PbSpinner message="Loading grades…" />
      </AdminLayout>
    )
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Grades</h1>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Merge grades that are the same competition under different names, or set display name overrides.
        </p>

        <MergeBuilder orgId={orgId} grades={grades || []} onMerged={refresh} />

        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
          All Grades <span className="text-pb-faintest">({(grades || []).length})</span>
        </p>
        <GradeList grades={grades || []} />

        <MergeHistory orgId={orgId} refreshKey={historyKey} onChanged={refresh} />

        <RenameGrades />
      </div>
    </AdminLayout>
  )
}
