// "Add a player by hand" for the BetterPosts lineup. A player who is not on the
// roster (a fill-in, a new signing, someone the sync has not seen) is typed in
// here, becomes a real player record in the club's data, and drops straight into
// the lineup. Before anything is created the club's own players are checked for
// the same person, so a hand-typed "Steve Smith" does not become a second record
// next to "Smith, Steven": the admin is shown the likely matches and decides.
//
// The parent owns the roster and the lineup. It gets the player through `onAdd`
// (a roster-shaped record, so the photo, role and icon come with it).
import { useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { ROLE_OPTS } from '../../../lib/playerAttributes'
import { validateImageFile } from '../../../lib/validation'
import ImageEditorModal from '../../ImageEditorModal'

const input = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest'
const label = 'block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1'

export default function ManualPlayerForm({ roster, onAdd, onClose }) {
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [role, setRole] = useState('')
  const [photo, setPhoto] = useState(null)       // File, after the editor (crop, cut-out)
  const [editing, setEditing] = useState(null)     // File | blob URL open in the editor
  const [preview, setPreview] = useState(null)   // object URL
  const [step, setStep] = useState('form')       // form | similar
  const [similar, setSimilar] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef(null)

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const written = [first.trim(), last.trim()].filter(Boolean).join(' ')

  const pickFile = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    const bad = validateImageFile(f)
    if (bad) { setError(bad); return }
    setError('')
    // Every photo goes through the same editor as the player profile (crop, and
    // the AI cut-out for a clean headshot) before it is kept.
    setEditing(f)
  }
  const applyEdited = (file) => {
    setEditing(null)
    setPhoto(file)
    setPreview((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(file) })
  }

  // The photo is best effort: the player exists either way, so a failed upload
  // says so rather than losing the player.
  const uploadPhoto = async (playerId) => {
    if (!photo) return { url: null, failed: false }
    try {
      const r = await api.adminUploadPlayerPhoto(playerId, photo)
      return { url: r?.photo_url || null, failed: false }
    } catch (e) {
      return { url: null, failed: true, message: e?.message }
    }
  }

  const check = async () => {
    if (!last.trim()) { setError('Add at least a surname.'); return }
    setBusy(true); setError('')
    try {
      const r = await api.adminSimilarPlayers(written)
      const found = (r?.candidates || []).filter((c) => !!roster.find((p) => String(p.id) === String(c.id)))
      if (found.length) { setSimilar(found); setStep('similar'); return }
      await create()
    } catch (e) {
      // A failed check must not let a duplicate through unseen, nor strand the
      // admin: say so and let them add the player anyway.
      setError(`Could not check the club's players for this name (${e?.message || 'no answer'}). Add as a new player to carry on.`)
      setStep('unchecked')
    } finally { setBusy(false) }
  }

  const create = async () => {
    setBusy(true); setError('')
    try {
      const made = await api.adminCreatePlayer({ first_name: first.trim(), last_name: last.trim(), player_role: role || undefined })
      const up = await uploadPhoto(made.id)
      onAdd({ ...made, photo_url: up.url || made.photo_url || null }, up.failed
        ? `${made.display_name || made.name} was added, but the photo did not upload (${up.message || 'try again from Admin, Players'}).`
        : `${made.display_name || made.name} was added to the club's players and to this post.`)
    } catch (e) {
      setError(e?.message || 'Could not add the player.')
    } finally { setBusy(false) }
  }

  const useExisting = async (c) => {
    const p = roster.find((x) => String(x.id) === String(c.id))
    if (!p) return
    setBusy(true); setError('')
    let note = `${p.display_name || p.name} is already one of the club's players, so no new record was made.`
    let updated = p
    // Fill an empty photo only. Replacing somebody's photo is not this form's job.
    if (photo && !p.photo_url) {
      const up = await uploadPhoto(p.id)
      if (up.url) { updated = { ...p, photo_url: up.url }; note += ' Your photo was added to their profile.' }
    }
    onAdd(updated, note, { existing: true })
    setBusy(false)
  }

  return (
    <div className="mb-3 rounded border pb-hairline p-3 bg-pb-surface" data-testid="manual-player">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Add a player by hand</h3>
        <button onClick={onClose} className="text-pb-faintest hover:text-pb-text text-xs" aria-label="Close">✕</button>
      </div>

      {step === 'similar' ? (
        <div data-testid="manual-player-similar">
          <p className="text-[11px] text-pb-dim leading-relaxed mb-2">
            The club already has {similar.length === 1 ? 'a player' : 'players'} who could be <span className="text-pb-text">{written}</span>. Is it one of them?
          </p>
          <div className="flex flex-col gap-1.5 mb-3">
            {similar.map((c) => (
              <button key={c.id} onClick={() => useExisting(c)} disabled={busy} data-testid="similar-player"
                className="flex items-center gap-2 text-left px-2.5 py-2 rounded border pb-hairline hover:border-pb-accent disabled:opacity-50 min-w-0">
                {c.photo_url
                  ? <img src={c.photo_url} alt="" className="w-7 h-7 rounded-full object-cover object-top shrink-0" />
                  : <span className="w-7 h-7 rounded-full bg-pb-surface2 shrink-0" />}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-pb-text truncate">{c.name}</span>
                  <span className="block font-mono text-[9px] text-pb-faintest truncate">{[c.player_role, c.reason].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="font-mono text-[10px] text-pb-dim shrink-0">THAT'S THEM</span>
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={create} disabled={busy} data-testid="add-as-new"
              className="px-3 py-1.5 rounded border pb-hairline text-[11px] font-mono text-pb-text hover:border-pb-text disabled:opacity-50">
              {busy ? 'ADDING…' : 'NO, ADD AS A NEW PLAYER'}
            </button>
            <button onClick={() => setStep('form')} disabled={busy} className="px-3 py-1.5 text-[11px] font-mono text-pb-faint hover:text-pb-text">BACK</button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div><label className={label}>First name</label><input value={first} onChange={(e) => setFirst(e.target.value)} placeholder="Ash" className={input} data-testid="manual-first" /></div>
            <div><label className={label}>Surname</label><input value={last} onChange={(e) => setLast(e.target.value)} placeholder="North" className={input} data-testid="manual-last" /></div>
          </div>
          <label className={label}>Role (optional)</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className={`${input} mb-2`} data-testid="manual-role">
            {ROLE_OPTS.map((r) => <option key={r} value={r}>{r || 'Not set'}</option>)}
          </select>
          <label className={label}>Photo (optional)</label>
          <div className="flex items-center gap-2 mb-3">
            {preview && <img src={preview} alt="" className="w-10 h-10 rounded-full object-cover object-top" />}
            <button onClick={() => fileRef.current?.click()} type="button"
              className="px-2.5 py-1.5 rounded border pb-hairline2 text-xs font-mono text-pb-dim hover:text-pb-text hover:border-pb-accent">
              {photo ? 'Change photo' : 'Upload photo'}
            </button>
            {photo && <button onClick={() => setEditing(photo)} data-testid="manual-photo-edit" className="text-xs font-mono text-pb-dim hover:text-pb-text">Edit / cut out</button>}
            {photo && <button onClick={() => { setPhoto(null); setPreview(null) }} className="text-xs font-mono text-pb-faint hover:text-pb-text">Remove</button>}
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={pickFile} data-testid="manual-photo" />
          </div>
          <div className="flex items-center gap-2">
            <button onClick={step === 'unchecked' ? create : check} disabled={busy || !last.trim()} data-testid="manual-add"
              className="px-3 py-1.5 rounded text-[11px] font-mono tracking-wide2 disabled:opacity-50"
              style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent, var(--pb-bg))' }}>
              {busy ? 'CHECKING…' : step === 'unchecked' ? 'ADD AS A NEW PLAYER' : 'ADD TO THIS POST'}
            </button>
          </div>
          <p className="text-[11px] text-pb-faintest leading-relaxed mt-2">
            Saved to the club's players, photo included, so they are there next time and in stats. You can crop it and cut the background out before it is saved. We check for the same person first.
          </p>
        </>
      )}
      {error && <p className="text-[11px] text-red-400 mt-2" role="alert">{error}</p>}
      <ImageEditorModal
        open={!!editing}
        source={editing}
        title="Edit Player Photo"
        aspect={1}
        outputType="image/png"
        outputName="player-photo.png"
        onCancel={() => setEditing(null)}
        onApply={applyEdited}
      />
    </div>
  )
}
