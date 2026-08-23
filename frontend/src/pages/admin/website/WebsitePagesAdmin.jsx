import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import RichTextEditor from '../../../components/website/RichTextEditor'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function blankPage() {
  return { id: null, title: '', nav_label: '', body: '', show_in_nav: true, is_published: true, parent_id: null, is_header: false }
}

// Flatten into menu order: each top-level item followed by its children.
function treeOrder(list) {
  const tops = list.filter(p => !p.parent_id).sort((a, b) => a.display_order - b.display_order)
  const kids = {}
  list.filter(p => p.parent_id).forEach(p => { (kids[p.parent_id] = kids[p.parent_id] || []).push(p) })
  const ids = new Set(list.map(p => p.id))
  const out = []
  tops.forEach(t => {
    out.push(t)
    ;(kids[t.id] || []).sort((a, b) => a.display_order - b.display_order).forEach(c => out.push(c))
  })
  // orphans whose parent no longer exists → show at the end as top-level
  list.filter(p => p.parent_id && !ids.has(p.parent_id)).forEach(o => out.push(o))
  return out
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
        is_header: editing.is_header, parent_id: editing.is_header ? null : (editing.parent_id || null),
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

  const ordered = treeOrder(list)
  async function move(index, dir) {
    const next = [...ordered]
    const j = index + dir
    if (j < 0 || j >= next.length) return
    ;[next[index], next[j]] = [next[j], next[index]]
    setList(next)
    try { await api.webAdminReorderPages(next.map(p => p.id)) }
    catch (e) { toast.error(e.message); load() }
  }

  if (editing) {
    // Eligible parents: the club's top-level items (incl. headers), not self.
    const parents = list.filter(p => !p.parent_id && p.id !== editing.id)
    return (
      <div>
        <Flash msg={flash} />
        <button onClick={() => setEditing(null)} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text mb-4">← BACK TO PAGES</button>
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <input value={editing.title || ''} onChange={e => setField('title', e.target.value)} placeholder={editing.is_header ? 'Menu name (e.g. Teams)' : 'Page title (e.g. About Us)'} className={`${inputCls} font-semibold`} />
            <input value={editing.nav_label || ''} onChange={e => setField('nav_label', e.target.value)} placeholder="Short menu label (optional)" className={inputCls} />
          </div>

          <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
            <input type="checkbox" checked={editing.is_header} onChange={e => setField('is_header', e.target.checked)} />
            Menu group (a dropdown with no page of its own, e.g. “Teams”)
          </label>

          {editing.is_header ? (
            <p className="px-4 py-3 rounded-lg border pb-hairline bg-pb-surface2/40 text-[12px] text-pb-faint">
              This is a dropdown menu only. Add pages under it by editing each page and setting its <span className="text-pb-dim">Parent menu</span> to this one.
            </p>
          ) : (
            <>
              {parents.length > 0 && (
                <div className="sm:w-72">
                  <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Parent menu (optional)</label>
                  <select value={editing.parent_id || ''} onChange={e => setField('parent_id', e.target.value || null)} className={inputCls}>
                    <option value="">. Top level, </option>
                    {parents.map(p => <option key={p.id} value={p.id}>{p.nav_label || p.title}{p.is_header ? ' (menu)' : ''}</option>)}
                  </select>
                </div>
              )}
              <div>
                <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Content</label>
                <RichTextEditor key={editing.id || 'new'} value={editing.body} onChange={v => setField('body', v)} placeholder="Write this page…" minHeight={320} />
              </div>
            </>
          )}

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.show_in_nav} onChange={e => setField('show_in_nav', e.target.checked)} /> Show in website menu
            </label>
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.is_published} onChange={e => setField('is_published', e.target.checked)} /> Published
            </label>
            <div className="flex-1" />
            <button onClick={save} disabled={saving} className={btnPrimary}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <Flash msg={flash} />
      <div className="flex justify-between items-center mb-2">
        <p className="text-pb-faint text-sm">{list.length} item{list.length === 1 ? '' : 's'}</p>
        <button onClick={() => setEditing(blankPage())} className={btnPrimary}>+ New page</button>
      </div>
      <p className="text-pb-faintest text-[11px] mb-4">Create pages, or a “menu group” (no page) to nest pages under, e.g. Teams → Mens / Womens. Use ↑ ↓ to reorder.</p>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : list.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm">No pages yet. Add About, History, Join Us…</div>
      ) : (
        <div className="pb-card overflow-hidden">
          {ordered.map((p, i) => (
            <div key={p.id} className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 flex items-center gap-3 ${p.parent_id ? 'pl-10 bg-pb-surface2/30' : ''}`}>
              <div className="flex flex-col">
                <button onClick={() => move(i, -1)} disabled={i === 0} className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-xs leading-none">▲</button>
                <button onClick={() => move(i, 1)} disabled={i === ordered.length - 1} className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-xs leading-none">▼</button>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {p.parent_id && <span className="text-pb-faintest text-xs">↳</span>}
                  <span className="text-pb-text text-sm font-medium truncate">{p.title}</span>
                  {p.is_header && <span className="text-[9px] font-mono px-1 rounded bg-pb-accent/15 text-pb-accent">MENU</span>}
                  {!p.show_in_nav && <span className="text-[9px] font-mono px-1 rounded bg-pb-surface2 text-pb-faint">HIDDEN</span>}
                  {!p.is_published && <span className="text-[9px] font-mono px-1 rounded bg-amber-400/15 text-amber-400">DRAFT</span>}
                </div>
                {!p.is_header && <div className="font-mono text-[10px] text-pb-faintest">/{p.slug}</div>}
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
