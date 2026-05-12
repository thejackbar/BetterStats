import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import LoadingSpinner from '../../components/LoadingSpinner'

function GradePicker({ grades, value, onChange, placeholder, exclude }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value || null)}
      className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
    >
      <option value="">{placeholder}</option>
      {grades
        .filter(g => g.grade_name !== exclude)
        .map(g => (
          <option key={g.grade_name} value={g.grade_name}>
            {g.grade_name} ({g.games} games · {g.runs} runs)
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
    <div className="card p-5 mb-8">
      <h3 className="display-heading text-base text-white mb-3">MERGE GRADES</h3>
      <p className="text-slate-400 text-sm mb-4">
        Use this when one grade is sponsored or renamed across seasons (e.g. "One Day Grade 3" and "One Day Grade 3 - East" are actually the same).
        Stats will be combined in the player by-grade view.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="section-label text-xs mb-2 block">Variant to merge</label>
          <GradePicker
            grades={grades}
            value={alias}
            onChange={setAlias}
            placeholder="— Select grade —"
            exclude={canonical}
          />
        </div>
        <div>
          <label className="section-label text-xs mb-2 block">Merge into (keep this name)</label>
          <GradePicker
            grades={grades}
            value={canonical}
            onChange={setCanonical}
            placeholder="— Select canonical grade —"
            exclude={alias}
          />
        </div>
      </div>
      {alias && canonical && alias === canonical && (
        <p className="text-amber-400 text-sm mb-3">Pick two different grades.</p>
      )}
      {error && (
        <div className="mb-3 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
      )}
      <button
        onClick={handleMerge}
        disabled={!canMerge || busy}
        className="btn-primary text-sm w-full disabled:opacity-40"
      >
        {busy ? 'Merging…' : `Merge ${alias || '…'} into ${canonical || '…'}`}
      </button>
    </div>
  )
}

function GradeList({ grades }) {
  if (!grades.length) {
    return <p className="text-slate-500 text-sm">No grades found for this club.</p>
  }
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Grade</th>
            <th className="table-header text-right">Games</th>
            <th className="table-header text-right">Runs</th>
          </tr>
        </thead>
        <tbody>
          {grades.map(g => (
            <tr key={g.grade_name} className="table-row align-top">
              <td className="table-cell">
                <div className="text-white">{g.grade_name}</div>
                {g.aliases?.length > 0 && (
                  <div className="text-xs text-slate-500 mt-1">
                    Includes: {g.aliases.join(', ')}
                  </div>
                )}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{g.games}</td>
              <td className="table-cell stat-number text-right text-slate-300">{g.runs}</td>
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
      <h3 className="display-heading text-base text-white mb-3">MERGE HISTORY</h3>
      {error && (
        <div className="mb-3 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
      )}
      <div className="flex flex-col gap-2">
        {history.map(entry => (
          <div
            key={entry.id}
            className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${entry.undone ? 'border-navy-700 bg-navy-900/40 opacity-50' : 'border-navy-700 bg-navy-900'}`}
          >
            <div className="flex-1 min-w-0">
              <span className="text-white font-medium">{entry.canonical_name}</span>
              <span className="text-slate-500 mx-2">←</span>
              <span className="text-amber-300">{entry.alias_name}</span>
              <span className="text-slate-600 text-xs ml-3">{new Date(entry.merged_at).toLocaleDateString()}</span>
            </div>
            {entry.undone ? (
              <span className="text-xs text-slate-500 shrink-0">Undone</span>
            ) : (
              <button
                onClick={() => handleUndo(entry)}
                disabled={undoing === entry.id}
                className="btn-ghost border border-navy-600 text-xs px-3 py-1 shrink-0 disabled:opacity-50"
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
        <LoadingSpinner message="Loading grades…" />
      </AdminLayout>
    )
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl mx-auto">
        <div className="mb-6">
          <div className="accent-bar mb-3" />
          <p className="section-label mb-1">Admin Tools</p>
          <h1 className="display-heading text-3xl text-white">MERGE GRADES</h1>
          <p className="text-slate-400 mt-2 text-sm">
            Combine grades that are actually the same competition but were named differently across seasons (e.g. sponsorship changes).
          </p>
        </div>

        <MergeBuilder orgId={orgId} grades={grades || []} onMerged={refresh} />

        <h3 className="display-heading text-base text-white mb-3">
          ALL GRADES <span className="text-slate-500 text-sm font-normal">({(grades || []).length})</span>
        </h3>
        <GradeList grades={grades || []} />

        <MergeHistory orgId={orgId} refreshKey={historyKey} onChanged={refresh} />
      </div>
    </AdminLayout>
  )
}
