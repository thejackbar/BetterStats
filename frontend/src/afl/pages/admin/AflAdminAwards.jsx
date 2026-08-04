import { useEffect, useRef, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminAwards() {
  const [achievements, setAchievements] = useState(null)
  const [imports, setImports] = useState(null)
  const [form, setForm] = useState({ player_name: '', season: '', category: '', subcategory: '', achievement: '', detail: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const fileRef = useRef(null)

  const refresh = () => {
    aflApi.listAchievements().then(setAchievements).catch(() => setAchievements([]))
    aflApi.listAchievementImports().then(setImports).catch(() => setImports([]))
  }
  useEffect(() => { refresh() }, [])

  const add = async () => {
    if (!form.player_name.trim() || !form.category.trim() || !form.achievement.trim()) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.createAchievement(form)
      setForm({ player_name: '', season: '', category: '', subcategory: '', achievement: '', detail: '' })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete this award?')) return
    setBusy(true)
    try {
      await aflApi.deleteAchievement(id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    setImportResult(null)
    try {
      const res = await aflApi.importAchievements(file)
      setImportResult(res)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const undoImport = async (batchId) => {
    if (!window.confirm('Undo this import? Every award it added will be removed.')) return
    setBusy(true)
    try {
      await aflApi.undoAchievementImport(batchId)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (achievements === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6">
      <SectionTitle>Awards ({achievements.length})</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">Record who actually won each award. Add one at a time, or import a season's worth from a spreadsheet.</p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      <div className="pb-card p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <SectionTitle>Add an award</SectionTitle>
          <div className="flex items-center gap-3">
            <a href={aflApi.achievementsTemplateUrl()} className="text-sm text-pb-dim underline hover:text-pb-text">Download CSV template</a>
            <label className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2 cursor-pointer">
              Import CSV
              <input ref={fileRef} type="file" accept=".csv" onChange={onFile} disabled={busy} className="hidden" />
            </label>
          </div>
        </div>
        {importResult && (
          <p className="text-sm text-[var(--pb-positive)]">
            Imported {importResult.created} award{importResult.created === 1 ? '' : 's'}, skipped {importResult.skipped}.
            {importResult.errors?.length > 0 && ` ${importResult.errors.length} row error(s).`}
          </p>
        )}
        <div className="grid grid-cols-2 gap-2">
          <input placeholder="Player name" value={form.player_name}
                 onChange={e => setForm(f => ({ ...f, player_name: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Season (e.g. 2025)" value={form.season}
                 onChange={e => setForm(f => ({ ...f, season: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Category (e.g. Club Award)" value={form.category}
                 onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Subcategory (e.g. A Grade)" value={form.subcategory}
                 onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Achievement (e.g. Best & Fairest)" value={form.achievement}
                 onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
          <input placeholder="Detail (optional)" value={form.detail}
                 onChange={e => setForm(f => ({ ...f, detail: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
        </div>
        <button disabled={busy || !form.player_name.trim() || !form.category.trim() || !form.achievement.trim()} onClick={add}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          Add award
        </button>
      </div>

      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              {['Season', 'Category', 'Award', 'Player', 'Detail', ''].map(h => (
                <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {achievements.map(a => (
              <tr key={a.id} className="pb-hairline-b last:border-0">
                <td className="px-2 py-1.5 text-pb-faint">{a.season || '—'}</td>
                <td className="px-2 py-1.5">{a.category}{a.subcategory ? ` · ${a.subcategory}` : ''}</td>
                <td className="px-2 py-1.5">{a.achievement}</td>
                <td className="px-2 py-1.5">{a.player_name}</td>
                <td className="px-2 py-1.5 text-pb-faint">{a.detail || '—'}</td>
                <td className="px-2 py-1.5 text-right">
                  <button disabled={busy} onClick={() => remove(a.id)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {achievements.length === 0 && (
              <tr><td colSpan={6} className="px-2 py-3 text-pb-faint">No awards recorded yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {imports && imports.length > 0 && (
        <div className="pb-card p-4">
          <SectionTitle>Import history</SectionTitle>
          <table className="w-full text-sm">
            <tbody>
              {imports.map(b => (
                <tr key={b.id} className="pb-hairline-b last:border-0">
                  <td className="px-2 py-1.5 text-pb-faint">{(b.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                  <td className="px-2 py-1.5">{b.filename}</td>
                  <td className="px-2 py-1.5 text-right pb-num">{b.created_count} rows</td>
                  <td className="px-2 py-1.5 text-right">
                    {b.status === 'undone'
                      ? <span className="text-pb-faint">Undone</span>
                      : <button disabled={busy} onClick={() => undoImport(b.id)} className="text-xs text-pb-dim hover:text-pb-text underline">Undo</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
