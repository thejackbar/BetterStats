import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

const GRADE_CATEGORIES = [
  ['senior', 'Senior'],
  ['colts', 'Colts'],
  ['womens', "Women's"],
  ['masters', 'Masters'],
  ['integrated', 'Integrated'],
]

function GradePicker({ grades, value, onChange, placeholder, exclude }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value || null)}
      className="w-full bg-pb-surface2 border border-pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-[var(--pb-accent)]"
    >
      <option value="">{placeholder}</option>
      {grades.filter(g => g.grade_name !== exclude).map(g => (
        <option key={g.grade_name} value={g.grade_name}>
          {g.display_name} ({g.games} games · {g.goals} goals)
        </option>
      ))}
    </select>
  )
}

function MergeBuilder({ grades, onMerged }) {
  const [alias, setAlias] = useState(null)
  const [canonical, setCanonical] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const canMerge = alias && canonical && alias !== canonical

  const handleMerge = async () => {
    if (!canMerge) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.mergeGrades(alias, canonical)
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
    <div className="pb-card p-5">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge Grades</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Use this when one grade is sponsored or renamed across seasons (e.g. "A Grade"
        and "A Grade (XYZ Finance)" are actually the same competition). Games and stats
        combine wherever you filter by either name.
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
        <p className="font-mono text-[11px] text-[var(--pb-amber)] mb-3">Pick two different grades.</p>
      )}
      {error && <p className="mb-3 text-sm text-[var(--pb-negative)]">{error}</p>}
      <button
        onClick={handleMerge}
        disabled={!canMerge || busy}
        className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-40 text-black"
        style={{ background: 'var(--pb-accent)' }}
      >
        {busy ? 'Merging…' : `Merge ${alias || '…'} into ${canonical || '…'}`}
      </button>
    </div>
  )
}

function GradeList({ grades, onChanged }) {
  const [savingName, setSavingName] = useState(null)
  const [applyingAll, setApplyingAll] = useState(false)
  const [error, setError] = useState(null)
  const [editingName, setEditingName] = useState(null) // { grade_name, value }

  const save = async (gradeName, patch) => {
    setSavingName(gradeName)
    setError(null)
    try {
      await aflApi.classifyGrade(gradeName, patch)
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingName(null)
    }
  }

  const saveDisplayName = async () => {
    if (!editingName) return
    await save(editingName.grade_name, { display_name: editingName.value || '' })
    setEditingName(null)
  }

  const applyAll = async () => {
    setApplyingAll(true)
    setError(null)
    try {
      await aflApi.applyGradeSuggestions()
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setApplyingAll(false)
    }
  }

  if (!grades.length) return <p className="text-sm text-pb-faint">No grades found for this club.</p>

  const anyUnconfirmed = grades.some(g => !g.category_confirmed)

  return (
    <div>
      <p className="text-pb-dim text-sm mb-3 leading-relaxed">
        Label each grade so the public site can split them (Seniors / Colts / Women's / Masters
        / Integrated), and choose which ones to share. A hidden grade drops off public grade
        filters and per-grade breakdowns; your admin views and whole-club career totals are unchanged.
        Hover a grade's name to rename it — useful for keeping merged or sponsor-suffixed names
        uniform (e.g. "A Grade (XYZ Finance)" → "A Grade").
      </p>
      {anyUnconfirmed && (
        <button onClick={applyAll} disabled={applyingAll}
                className="mb-3 font-mono text-[10px] tracking-wide2 border border-pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50">
          {applyingAll ? 'Applying…' : 'Confirm all suggestions'}
        </button>
      )}
      {error && <p className="mb-3 text-sm text-[var(--pb-negative)]">{error}</p>}
      <div className="pb-card overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-2.5 pl-4">Grade</th>
              <th className="font-medium py-2.5">Category</th>
              <th className="font-medium py-2.5 text-center">Public</th>
              <th className="font-medium py-2.5 text-right">Games</th>
              <th className="font-medium py-2.5 pr-4 text-right">Goals</th>
            </tr>
          </thead>
          <tbody>
            {grades.map((g, i) => {
              const busy = savingName === g.grade_name
              return (
                <tr key={g.grade_name} className={`${i ? 'pb-hairline-t' : ''} align-top hover:bg-pb-surface2 ${g.is_public ? '' : 'opacity-60'}`}>
                  <td className="py-2.5 pl-4">
                    {editingName?.grade_name === g.grade_name ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          autoFocus
                          type="text"
                          value={editingName.value}
                          onChange={e => setEditingName(ed => ({ ...ed, value: e.target.value }))}
                          placeholder="Blank to clear"
                          className="flex-1 min-w-0 bg-pb-surface2 border rounded px-2 py-1 text-pb-text text-sm focus:outline-none"
                          style={{ borderColor: 'var(--pb-accent)' }}
                          onKeyDown={e => { if (e.key === 'Enter') saveDisplayName(); if (e.key === 'Escape') setEditingName(null) }}
                        />
                        <button onClick={saveDisplayName} disabled={busy}
                                className="font-mono text-[10px] px-2 py-1 rounded text-black shrink-0 disabled:opacity-50"
                                style={{ background: 'var(--pb-accent)' }}>Save</button>
                        <button onClick={() => setEditingName(null)}
                                className="font-mono text-[10px] px-2 py-1 rounded border border-pb-hairline text-pb-faint hover:text-pb-text shrink-0">Cancel</button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 group">
                        <div className="min-w-0">
                          <span className="text-pb-text">{g.display_name}</span>
                          {g.display_name !== g.grade_name && (
                            <div className="font-mono text-[10px] text-pb-faintest mt-0.5">raw: {g.grade_name}</div>
                          )}
                          {g.aliases?.length > 0 && (
                            <div className="font-mono text-[10px] text-pb-faintest mt-0.5">Includes: {g.aliases.join(', ')}</div>
                          )}
                        </div>
                        <button onClick={() => setEditingName({ grade_name: g.grade_name, value: g.display_name === g.grade_name ? '' : g.display_name })}
                                className="font-mono text-[9px] px-1.5 py-0.5 rounded border border-pb-hairline text-pb-faintest opacity-0 group-hover:opacity-100 hover:text-pb-text transition-opacity shrink-0">
                          Rename
                        </button>
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-2">
                      <select value={g.category || 'senior'} disabled={busy}
                              onChange={e => save(g.grade_name, { category: e.target.value })}
                              className="bg-pb-surface2 border border-pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-[var(--pb-accent)] disabled:opacity-50">
                        {GRADE_CATEGORIES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                      </select>
                      {!g.category_confirmed && (
                        <span className="font-mono text-[9px] text-[var(--pb-amber)] uppercase tracking-wide" title="Auto-detected from the grade name — pick to confirm">
                          suggested
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 text-center">
                    <button onClick={() => save(g.grade_name, { is_public: !g.is_public })} disabled={busy}
                            className={`font-mono text-[10px] tracking-wide2 rounded px-2.5 py-1 border transition-colors disabled:opacity-50 ${
                              g.is_public
                                ? 'text-[var(--pb-positive)] border-[var(--pb-positive)]/40 hover:bg-[var(--pb-positive)]/10'
                                : 'text-pb-faint border-pb-hairline hover:text-pb-text'}`}>
                      {g.is_public ? 'Public' : 'Hidden'}
                    </button>
                  </td>
                  <td className="py-2.5 font-mono text-pb-dim text-right pb-num">{g.games}</td>
                  <td className="py-2.5 pr-4 font-mono text-pb-dim text-right pb-num">{g.goals}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MergeHistory({ refreshKey }) {
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => { aflApi.gradeMergeHistory().then(setHistory).catch(() => setHistory([])) }, [refreshKey])

  const undo = async (entry) => {
    setUndoing(entry.id)
    setError(null)
    try {
      await aflApi.undoGradeMerge(entry.id)
      setHistory(hs => hs.map(h => h.id === entry.id ? { ...h, undone: true } : h))
    } catch (e) {
      setError(e.message)
    } finally {
      setUndoing(null)
    }
  }

  if (history.length === 0) return null

  return (
    <div className="pb-card p-4">
      <SectionTitle>Merge history</SectionTitle>
      {error && <p className="text-sm text-[var(--pb-negative)] mb-2">{error}</p>}
      <table className="w-full text-sm">
        <tbody>
          {history.map(h => (
            <tr key={h.id} className="pb-hairline-b last:border-0">
              <td className="px-2 py-1.5 pb-num text-pb-faint">{(h.merged_at || '').replace('T', ' ').slice(0, 16)}</td>
              <td className="px-2 py-1.5">{h.alias_name}</td>
              <td className="px-2 py-1.5">→ {h.canonical_name}</td>
              <td className="px-2 py-1.5 text-right">
                {h.undone
                  ? <span className="text-pb-faint">Undone</span>
                  : <button disabled={undoing === h.id} onClick={() => undo(h)} className="text-xs text-pb-dim hover:text-pb-text underline">
                      {undoing === h.id ? 'Undoing…' : 'Undo'}
                    </button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AflAdminMergeGrades() {
  const [grades, setGrades] = useState(null)
  const [historyKey, setHistoryKey] = useState(0)

  const load = () => aflApi.listGradesWithStats().then(setGrades).catch(() => setGrades([]))
  useEffect(() => { load() }, [])

  const refresh = () => {
    setHistoryKey(k => k + 1)
    load()
  }

  if (grades === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6 max-w-3xl">
      <SectionTitle>Merge Grades ({grades.length})</SectionTitle>
      <p className="text-sm text-pb-dim">
        Label grades by type, choose which to share publicly, and merge grades that are
        really the same competition under different names.
      </p>

      <MergeBuilder grades={grades} onMerged={refresh} />

      <div>
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
          Labels &amp; Visibility <span className="text-pb-faintest">({grades.length})</span>
        </p>
        <GradeList grades={grades} onChanged={refresh} />
      </div>

      <MergeHistory refreshKey={historyKey} />
    </div>
  )
}
