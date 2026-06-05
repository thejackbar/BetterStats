import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import RichTextEditor from '../../../components/website/RichTextEditor'
import { useFlash, Flash, UploadButton, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function blankArticle() {
  return { id: null, title: '', author: '', summary: '', body: '', is_published: true, is_pinned: false, cover_image_url: null }
}

export default function WebsiteNewsAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)  // article object or null (list view)
  const [saving, setSaving] = useState(false)
  const [coverUploading, setCoverUploading] = useState(false)

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try { setList(await api.webAdminListNews()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  const setField = (k, v) => setEditing(p => ({ ...p, [k]: v }))

  async function save() {
    if (!editing.title.trim()) { toast.error('Title is required'); return }
    setSaving(true)
    try {
      const payload = {
        title: editing.title, author: editing.author, summary: editing.summary,
        body: editing.body, is_published: editing.is_published, is_pinned: editing.is_pinned,
      }
      const saved = editing.id
        ? await api.webAdminUpdateNews(editing.id, payload)
        : await api.webAdminCreateNews(payload)
      setEditing(saved)  // now has an id → cover upload enabled
      await load()
      showFlash('Article saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this article?')) return
    try { await api.webAdminDeleteNews(id); setList(l => l.filter(a => a.id !== id)); showFlash('Article deleted') }
    catch (e) { toast.error(e.message) }
  }

  async function uploadCover(file) {
    setCoverUploading(true)
    try {
      const r = await api.webAdminUploadNewsCover(editing.id, file)
      setField('cover_image_url', r.cover_image_url)
      showFlash('Cover updated')
    } catch (e) { toast.error(e.message) }
    finally { setCoverUploading(false) }
  }

  async function removeCover() {
    try { await api.webAdminDeleteNewsCover(editing.id); setField('cover_image_url', null) }
    catch (e) { toast.error(e.message) }
  }

  // ── Editor view ───────────────────────────────────────────────────────────
  if (editing) {
    return (
      <div>
        <Flash msg={flash} />
        <button onClick={() => { setEditing(null); load() }} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text mb-4">← BACK TO NEWS</button>

        <div className="space-y-4">
          <input value={editing.title || ''} onChange={e => setField('title', e.target.value)} placeholder="Headline" className={`${inputCls} text-lg font-semibold`} />
          <div className="grid sm:grid-cols-2 gap-3">
            <input value={editing.author || ''} onChange={e => setField('author', e.target.value)} placeholder="Author (optional)" className={inputCls} />
            <input value={editing.summary || ''} onChange={e => setField('summary', e.target.value)} placeholder="Summary (optional — auto-generated if blank)" className={inputCls} />
          </div>

          {/* Cover */}
          <div className="pb-card p-4">
            <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">Cover image</h3>
            <div className="aspect-[16/9] max-w-md rounded-lg overflow-hidden bg-pb-surface2 mb-3 flex items-center justify-center">
              {editing.cover_image_url
                ? <img src={editing.cover_image_url} alt="" className="w-full h-full object-cover" />
                : <span className="text-pb-faintest font-mono text-[11px]">NO COVER</span>}
            </div>
            {editing.id ? (
              <div className="flex items-center gap-2">
                <UploadButton label={editing.cover_image_url ? 'REPLACE' : 'UPLOAD COVER'} uploading={coverUploading} onFile={uploadCover} />
                {editing.cover_image_url && <button onClick={removeCover} className={btnDanger}>REMOVE</button>}
              </div>
            ) : (
              <p className="text-pb-faintest text-[11px]">Save the article first, then add a cover.</p>
            )}
          </div>

          <div>
            <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Body</label>
            <RichTextEditor key={editing.id || 'new'} value={editing.body} onChange={v => setField('body', v)} placeholder="Write the story…" />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.is_published} onChange={e => setField('is_published', e.target.checked)} />
              Published
            </label>
            <label className="flex items-center gap-2 text-sm text-pb-dim cursor-pointer">
              <input type="checkbox" checked={editing.is_pinned} onChange={e => setField('is_pinned', e.target.checked)} />
              Pin to top
            </label>
            <div className="flex-1" />
            <button onClick={save} disabled={saving} className={btnPrimary}>{saving ? 'Saving…' : 'Save article'}</button>
          </div>
        </div>
      </div>
    )
  }

  // ── List view ─────────────────────────────────────────────────────────────
  return (
    <div>
      <Flash msg={flash} />
      <div className="flex justify-between items-center mb-4">
        <p className="text-pb-faint text-sm">{list.length} article{list.length === 1 ? '' : 's'}</p>
        <button onClick={() => setEditing(blankArticle())} className={btnPrimary}>+ New article</button>
      </div>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : list.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm">No news yet. Write your first article.</div>
      ) : (
        <div className="pb-card overflow-hidden">
          {list.map((a, i) => (
            <div key={a.id} className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 flex items-center gap-3`}>
              <div className="w-14 h-10 rounded bg-pb-surface2 overflow-hidden shrink-0 flex items-center justify-center">
                {a.cover_image_url ? <img src={a.cover_image_url} alt="" className="w-full h-full object-cover" /> : <span className="text-pb-faintest text-[9px] font-mono">—</span>}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-pb-text text-sm font-medium truncate">{a.title}</span>
                  {a.is_pinned && <span className="text-[9px] font-mono px-1 rounded bg-pb-accent/15 text-pb-accent">PIN</span>}
                  {!a.is_published && <span className="text-[9px] font-mono px-1 rounded bg-amber-400/15 text-amber-400">DRAFT</span>}
                </div>
                <div className="font-mono text-[10px] text-pb-faintest">{a.published_at ? new Date(a.published_at).toLocaleDateString() : '—'}{a.author ? ` · ${a.author}` : ''}</div>
              </div>
              <button onClick={() => setEditing({ ...blankArticle(), ...a })} className={btnGhost}>EDIT</button>
              <button onClick={() => remove(a.id)} className={btnDanger}>DELETE</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
