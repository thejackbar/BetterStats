import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { validateImageFile, DIRECT_IMAGE_MAX_BYTES } from '../../../lib/validation'
import { useFlash, Flash, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function ImageManager({ album, onBack, onChange }) {
  const toast = useToast()
  const [uploading, setUploading] = useState(false)
  const [captions, setCaptions] = useState(() => Object.fromEntries(album.images.map(i => [i.id, i.caption || ''])))

  async function onFiles(files) {
    setUploading(true)
    let added = [...album.images]
    for (const f of files) {
      const v = validateImageFile(f, { maxBytes: DIRECT_IMAGE_MAX_BYTES })
      if (v) { toast.error(`${f.name}: ${v}`); continue }
      try { const img = await api.webAdminAddGalleryImage(album.id, f); added = [...added, img] }
      catch (e) { toast.error(e.message) }
    }
    onChange({ ...album, images: added })
    setCaptions(Object.fromEntries(added.map(i => [i.id, i.caption || ''])))
    setUploading(false)
  }

  async function saveCaption(img) {
    try {
      const saved = await api.webAdminUpdateGalleryImage(img.id, { caption: captions[img.id] })
      onChange({ ...album, images: album.images.map(x => x.id === saved.id ? saved : x) })
    } catch (e) { toast.error(e.message) }
  }
  async function delImage(id) {
    if (!confirm('Delete this photo?')) return
    try { await api.webAdminDeleteGalleryImage(id); onChange({ ...album, images: album.images.filter(x => x.id !== id) }) }
    catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <button onClick={onBack} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text mb-4">← BACK TO ALBUMS</button>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display font-bold text-lg text-pb-text">{album.title}</h3>
        <label className={`${btnPrimary} cursor-pointer`}>
          {uploading ? 'Uploading…' : '+ Add photos'}
          <input type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
            onChange={e => { const fs = Array.from(e.target.files || []); e.target.value = ''; if (fs.length) onFiles(fs) }} />
        </label>
      </div>

      {album.images.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm">No photos yet — add some.</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {album.images.map(img => (
            <div key={img.id} className="rounded-lg border pb-hairline overflow-hidden bg-pb-surface">
              <div className="aspect-square bg-pb-surface2"><img src={img.image_url} alt="" className="w-full h-full object-cover" /></div>
              <div className="p-2">
                <input
                  value={captions[img.id] ?? ''} onChange={e => setCaptions(c => ({ ...c, [img.id]: e.target.value }))}
                  onBlur={() => saveCaption(img)} placeholder="Caption…"
                  className="w-full px-2 py-1 text-[12px] bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                />
                <button onClick={() => delImage(img.id)} className="mt-1 w-full text-[10px] font-mono text-red-400 hover:text-red-300">DELETE</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function WebsiteGalleryAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [albums, setAlbums] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)  // album id
  const [title, setTitle] = useState('')

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try { setAlbums(await api.webAdminListGallery()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  async function addAlbum() {
    if (!title.trim()) return
    try { const a = await api.webAdminCreateAlbum({ title }); setAlbums(p => [...p, a]); setTitle(''); showFlash('Album created') }
    catch (e) { toast.error(e.message) }
  }
  async function delAlbum(id) {
    if (!confirm('Delete this album and all its photos?')) return
    try { await api.webAdminDeleteAlbum(id); setAlbums(p => p.filter(a => a.id !== id)) }
    catch (e) { toast.error(e.message) }
  }
  async function renameAlbum(album) {
    const t = window.prompt('Album title', album.title)
    if (!t || !t.trim()) return
    try { const a = await api.webAdminUpdateAlbum(album.id, { title: t, description: album.description }); setAlbums(p => p.map(x => x.id === album.id ? { ...x, ...a } : x)) }
    catch (e) { toast.error(e.message) }
  }
  const update = (a) => setAlbums(p => p.map(x => x.id === a.id ? a : x))

  const current = albums.find(a => a.id === selected)
  if (current) return <ImageManager album={current} onBack={() => setSelected(null)} onChange={update} />

  return (
    <div>
      <Flash msg={flash} />
      <p className="text-pb-faint text-sm mb-4">Photo albums for your gallery page.</p>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : albums.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm mb-5">No albums yet.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-5">
          {albums.map(a => (
            <div key={a.id} className="rounded-xl border pb-hairline overflow-hidden bg-pb-surface">
              <button onClick={() => setSelected(a.id)} className="block w-full aspect-[4/3] bg-pb-surface2">
                {a.images[0]
                  ? <img src={a.images[0].image_url} alt="" className="w-full h-full object-cover" />
                  : <span className="text-pb-faintest font-mono text-[11px] flex items-center justify-center h-full">EMPTY</span>}
              </button>
              <div className="p-3">
                <div className="font-medium text-pb-text text-sm truncate">{a.title}</div>
                <div className="text-[11px] text-pb-faint">{a.images.length} photo{a.images.length === 1 ? '' : 's'}</div>
                <div className="flex gap-2 mt-2">
                  <button onClick={() => setSelected(a.id)} className={btnGhost}>MANAGE</button>
                  <button onClick={() => renameAlbum(a)} className={btnGhost}>RENAME</button>
                  <button onClick={() => delAlbum(a.id)} className={btnDanger}>DEL</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="pb-card p-4">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">New album</h3>
        <div className="flex gap-2">
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. 2025/26 Premiership" className={inputCls} onKeyDown={e => e.key === 'Enter' && addAlbum()} />
          <button onClick={addAlbum} className={btnPrimary}>Create</button>
        </div>
      </div>
    </div>
  )
}
