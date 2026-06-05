import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { useFlash, Flash, UploadButton, inputCls, btnPrimary, btnGhost, btnDanger } from './adminParts'

function MemberRow({ m, onChange, onDelete }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(m)
  const [uploading, setUploading] = useState(false)
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  async function save() {
    try {
      const saved = await api.webAdminUpdateCommittee(m.id, {
        role: form.role, name: form.name, email: form.email, phone: form.phone, bio: form.bio,
      })
      onChange({ ...m, ...saved }); setEditing(false)
    } catch (e) { toast.error(e.message) }
  }
  async function uploadPhoto(file) {
    setUploading(true)
    try { const r = await api.webAdminUploadCommitteePhoto(m.id, file); onChange({ ...m, photo_url: r.photo_url }) }
    catch (e) { toast.error(e.message) } finally { setUploading(false) }
  }
  async function removePhoto() {
    try { await api.webAdminDeleteCommitteePhoto(m.id); onChange({ ...m, photo_url: null }) }
    catch (e) { toast.error(e.message) }
  }

  return (
    <div className="px-4 py-3 flex items-start gap-3 pb-hairline-t first:border-t-0">
      <div className="w-12 h-12 rounded-full bg-pb-surface2 overflow-hidden shrink-0 flex items-center justify-center">
        {m.photo_url ? <img src={m.photo_url} alt="" className="w-full h-full object-cover" /> : <span className="text-pb-faintest text-[9px] font-mono">PHOTO</span>}
      </div>
      <div className="flex-1 min-w-0">
        {editing ? (
          <div className="space-y-2">
            <div className="grid sm:grid-cols-2 gap-2">
              <input value={form.role} onChange={e => set('role', e.target.value)} placeholder="Role" className={inputCls} />
              <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="Name" className={inputCls} />
              <input value={form.email || ''} onChange={e => set('email', e.target.value)} placeholder="Email" className={inputCls} />
              <input value={form.phone || ''} onChange={e => set('phone', e.target.value)} placeholder="Phone" className={inputCls} />
            </div>
            <textarea value={form.bio || ''} onChange={e => set('bio', e.target.value)} placeholder="Short bio (optional)" rows={2} className={inputCls} />
            <div className="flex gap-2">
              <button onClick={save} className="px-3 py-1 text-xs rounded bg-pb-accent text-white">Save</button>
              <button onClick={() => { setForm(m); setEditing(false) }} className={btnGhost}>Cancel</button>
              <UploadButton label={m.photo_url ? 'REPLACE PHOTO' : 'ADD PHOTO'} uploading={uploading} onFile={uploadPhoto} />
              {m.photo_url && <button onClick={removePhoto} className={btnDanger}>RM PHOTO</button>}
            </div>
          </div>
        ) : (
          <>
            <div className="font-mono text-[10px] tracking-wide2 uppercase" style={{ color: 'var(--pb-accent)' }}>{m.role}</div>
            <div className="text-pb-text text-sm font-medium">{m.name}</div>
            {(m.email || m.phone) && <div className="text-pb-faint text-[12px]">{[m.email, m.phone].filter(Boolean).join(' · ')}</div>}
          </>
        )}
      </div>
      {!editing && (
        <div className="flex gap-2 shrink-0">
          <button onClick={() => { setForm(m); setEditing(true) }} className={btnGhost}>EDIT</button>
          <button onClick={() => onDelete(m.id)} className={btnDanger}>DELETE</button>
        </div>
      )}
    </div>
  )
}

export default function WebsiteCommitteeAdmin() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [role, setRole] = useState('')
  const [name, setName] = useState('')

  useEffect(() => { load() }, [])
  async function load() {
    setLoading(true)
    try { setList(await api.webAdminListCommittee()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  async function add() {
    if (!role.trim() || !name.trim()) { toast.error('Role and name are required'); return }
    try { const m = await api.webAdminCreateCommittee({ role, name }); setList(p => [...p, m]); setRole(''); setName(''); showFlash('Member added') }
    catch (e) { toast.error(e.message) }
  }
  async function del(id) {
    if (!confirm('Remove this member?')) return
    try { await api.webAdminDeleteCommittee(id); setList(p => p.filter(m => m.id !== id)) }
    catch (e) { toast.error(e.message) }
  }
  const update = (m) => setList(p => p.map(x => x.id === m.id ? m : x))

  return (
    <div>
      <Flash msg={flash} />
      <p className="text-pb-faint text-sm mb-4">The people who run the club — shown on your Committee page.</p>

      {loading ? <p className="text-pb-faint text-sm">Loading…</p> : list.length === 0 ? (
        <div className="pb-card px-4 py-10 text-center text-pb-faint text-sm">No committee members yet.</div>
      ) : (
        <div className="pb-card overflow-hidden mb-5">
          {list.map(m => <MemberRow key={m.id} m={m} onChange={update} onDelete={del} />)}
        </div>
      )}

      <div className="pb-card p-4">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">Add member</h3>
        <div className="flex flex-col sm:flex-row gap-2">
          <input value={role} onChange={e => setRole(e.target.value)} placeholder="Role (e.g. President)" className={inputCls} />
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Name" className={inputCls} onKeyDown={e => e.key === 'Enter' && add()} />
          <button onClick={add} className={`${btnPrimary} whitespace-nowrap`}>Add</button>
        </div>
        <p className="text-pb-faintest text-[11px] mt-2">Add a photo, email, phone and bio with EDIT after creating.</p>
      </div>
    </div>
  )
}
