import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import RichTextEditor from '../../../components/website/RichTextEditor'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function blankPage() {
  return { id: null, title: '', nav_label: '', body: '', show_in_nav: true, is_published: true }
}

export default function WebsitePagesAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try { setList(await api.webAdminListPages()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  const setField = (k, v) => setEditing(p => ({ ...p, [k]: v }))

  async function save() {
    if (!editing.title.trim()) { toast.error('Title is required'); return }
    setSaving(true)
    try {
      const payload = {
        title: editing.title, nav_label: editing.nav_label, body: editing.body,
        show_in_nav: editing.show_in_nav, is_published: editing.is_published,
      }
      editing.id ? await api.webAdminUpdatePage(editing.id, payload) : await api.webAdminCreatePage(payload)
      setEditing(null)
      await load()
      showFlash('Page saved')
    } catch (e) { toast.error(e.message) }
    finally { setSaving(false) }
  }

  async function remove(id) {
    if (!confirm('Delete this page?')) return
    try { await api.webAdminDeletePage(id); setList(l => l.filter(p => p.id !== id)); showFlash('Page deleted') }
    catch (e) { toast.error(e.message) }
  }

  async function move(index, dir) {
    const next = [...list]
    const j = index + dir
    if (j < 0 || j >= next.length) return
    ;[next[index], next[j]] = [next[j], next[index]]
    setList(next)
    try { await api.webAdminReorderPages(next.map(p => p.id)) }
    catch (e) { toast.error(e.message); load() }
  }

  if (editing) {
    return (
      <div>
        <Flash msg={flash} />
        <button onClick={() => setEditing(null)} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text mb-4">← BACK TO PAGES</button>
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <input value={editing.title || ''} onChange={e => setField('title', e.target.value)} placeholder="Page title (e.g. About Us)" className={`${inputCls} font-semibold`} />
            <input value={editing.nav_label || ''} onChange={e => setField('nav_label', e.target.value)} placeholder="Short nav label (optional, e.g. About)" className={inputCls} />
          </div>
          <div>
            <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Content</label>
            <RichTextEditor key={editing.id || 'new'} value={editing.body} onChange={v => setField('body', v)} placeholder="Write this page…" minHeight={320} />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.show_in_nav} onChange={e => setField('show_in_nav', e.target.checked)} /> Show in website menu
            </label>
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.is_published} onChange={e => setField('is_published', e.target.checked)} /> Published
            </label>
            <div className="flex-1" />
            <button onClick={save} disabled={saving} className={btnPrimary}>{saving ? 'Saving…' : 'Save page'}</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <Flash msg={flash} />
      <div className="flex justify-between items-center mb-2">
        <p className="text-pb-faint text-sm">{list.length} page{list.length === 1 ? '' : 's'}</p>
        <button onClick={() => setEditing(blankPage())} className={btnPrimary}>+ New page</button>
      </div>
      <p className="text-pb-faintest text-[11px] mb-4">Pages in the website menu appear in this order. Use ↑ ↓ to reorder.</p>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : list.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm">No pages yet. Add About, History, Join Us…</div>
      ) : (
        <div className="pb-card overflow-hidden">
          {list.map((p, i) => (
            <div key={p.id} className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 flex items-center gap-3`}>
              <div className="flex flex-col">
                <button onClick={() => move(i, -1)} disabled={i === 0} className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-xs leading-none">▲</button>
                <button onClick={() => move(i, 1)} disabled={i === list.length - 1} className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-xs leading-none">▼</button>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-pb-text text-sm font-medium truncate">{p.title}</span>
                  {!p.show_in_nav && <span className="text-[9px] font-mono px-1 rounded bg-pb-surface2 text-pb-faint">HIDDEN</span>}
                  {!p.is_published && <span className="text-[9px] font-mono px-1 rounded bg-amber-400/15 text-amber-400">DRAFT</span>}
                </div>
                <div className="font-mono text-[10px] text-pb-faintest">/{p.slug}</div>
              </div>
              <button onClick={() => setEditing({ ...blankPage(), ...p })} className={btnGhost}>EDIT</button>
              <button onClick={() => remove(p.id)} className={btnDanger}>DELETE</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
