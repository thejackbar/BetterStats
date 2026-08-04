import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminAwardDefinitions() {
  const [defs, setDefs] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({ category: '', subcategory: '', achievement: '', display_name: '' })

  const refresh = () => aflApi.listAwardDefinitions().then(setDefs).catch(() => setDefs([]))
  useEffect(() => { refresh() }, [])

  const seed = async () => {
    if (defs?.length && !window.confirm('This replaces your current award catalogue with the starter template. Continue?')) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.seedAwardDefinitions('starter')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const add = async () => {
    if (!form.category.trim()) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.createAwardDefinition(form)
      setForm({ category: '', subcategory: '', achievement: '', display_name: '' })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (d) => {
    setBusy(true)
    try {
      await aflApi.updateAwardDefinition(d.id, { active: !d.active })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (d) => {
    if (!window.confirm(`Delete "${d.display_name || d.achievement}"?`)) return
    setBusy(true)
    try {
      await aflApi.deleteAwardDefinition(d.id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (defs === null) return <p className="text-sm text-pb-faint">Loading…</p>

  const grouped = defs.reduce((acc, d) => {
    (acc[d.category] = acc[d.category] || []).push(d)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Award Types ({defs.length})</SectionTitle>
        <button disabled={busy} onClick={seed} className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2">
          {defs.length ? 'Reset to starter template' : 'Seed starter template'}
        </button>
      </div>
      <p className="text-sm text-pb-dim max-w-2xl">
        The award types your club hands out — these fill the dropdowns on the
        Awards page. Add your own teams and trophies, or start from a lean
        template.
      </p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      <div className="pb-card p-4 space-y-3 max-w-lg">
        <SectionTitle>Add an award type</SectionTitle>
        <div className="grid grid-cols-2 gap-2">
          <input placeholder="Category (e.g. Club Award)" value={form.category}
                 onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Subcategory (e.g. A Grade)" value={form.subcategory}
                 onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Achievement (e.g. Best & Fairest)" value={form.achievement}
                 onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
        </div>
        <button disabled={busy || !form.category.trim()} onClick={add}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          Add
        </button>
      </div>

      {Object.entries(grouped).map(([category, rows]) => (
        <div key={category} className="pb-card p-4">
          <SectionTitle>{category}</SectionTitle>
          <table className="w-full text-sm">
            <tbody>
              {rows.map(d => (
                <tr key={d.id} className="pb-hairline-b last:border-0">
                  <td className="px-2 py-1.5 text-pb-faint w-32">{d.subcategory || '—'}</td>
                  <td className="px-2 py-1.5">{d.display_name || d.achievement}</td>
                  <td className={`px-2 py-1.5 text-right ${d.active ? 'text-[var(--pb-positive)]' : 'text-pb-faint'}`}>
                    {d.active ? 'Active' : 'Hidden'}
                  </td>
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">
                    <button disabled={busy} onClick={() => toggleActive(d)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                      {d.active ? 'Hide' : 'Show'}
                    </button>
                    <button disabled={busy} onClick={() => remove(d)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {defs.length === 0 && (
        <p className="pb-card p-4 text-pb-faint text-sm">No award types yet — seed the starter template or add one above.</p>
      )}
    </div>
  )
}
