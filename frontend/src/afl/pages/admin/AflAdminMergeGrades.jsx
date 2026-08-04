import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminMergeGrades() {
  const [names, setNames] = useState(null)
  const [history, setHistory] = useState(null)
  const [alias, setAlias] = useState('')
  const [canonical, setCanonical] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refresh = () => {
    aflApi.gradeNames().then(d => setNames(d.names)).catch(() => setNames([]))
    aflApi.gradeMergeHistory().then(setHistory).catch(() => setHistory([]))
  }
  useEffect(() => { refresh() }, [])

  const merge = async () => {
    if (!alias || !canonical) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.mergeGrades(alias, canonical)
      setAlias('')
      setCanonical('')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const undo = async (id) => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.undoGradeMerge(id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (names === null || history === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6">
      <SectionTitle>Merge Grades</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">
        If the same competition shows up under two different names (e.g. a
        sponsor name change mid-season), mark one as an alias of the other so
        stats and records combine.
      </p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      <div className="pb-card p-4 space-y-3 max-w-lg">
        <label className="block text-xs text-pb-faint">This grade name…
          <select value={alias} onChange={e => setAlias(e.target.value)}
                  className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
            <option value="">— select —</option>
            {names.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="block text-xs text-pb-faint">…is really the same as
          <select value={canonical} onChange={e => setCanonical(e.target.value)}
                  className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
            <option value="">— select —</option>
            {names.filter(n => n !== alias).map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button disabled={busy || !alias || !canonical} onClick={merge}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {busy ? 'Merging…' : 'Merge grades'}
        </button>
      </div>

      <div className="pb-card p-4">
        <SectionTitle>Merge history</SectionTitle>
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              {['Merged', 'Alias', 'Canonical', 'Status', ''].map(h => (
                <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map(h => (
              <tr key={h.id} className="pb-hairline-b last:border-0">
                <td className="px-2 py-1.5 pb-num text-pb-faint">{(h.merged_at || '').replace('T', ' ').slice(0, 16)}</td>
                <td className="px-2 py-1.5">{h.alias_name}</td>
                <td className="px-2 py-1.5">{h.canonical_name}</td>
                <td className="px-2 py-1.5">{h.undone ? <span className="text-pb-faint">Undone</span> : <span className="text-[var(--pb-positive)]">Active</span>}</td>
                <td className="px-2 py-1.5 text-right">
                  {!h.undone && (
                    <button disabled={busy} onClick={() => undo(h.id)} className="text-xs text-pb-dim hover:text-pb-text underline">
                      Undo
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {history.length === 0 && (
              <tr><td colSpan={5} className="px-2 py-3 text-pb-faint">No merges yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
