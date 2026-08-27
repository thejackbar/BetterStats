import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'

/**
 * Super Admin management for the /videos library: upload, edit, replace,
 * delete and reorder. Rendered only for a super admin, and every write it
 * makes is re-checked on the server — this file decides what is DRAWN, never
 * what is allowed.
 */

const MAX_VIDEO_MB = 512
const ACCEPT_VIDEO = 'video/mp4,video/webm'
const ACCEPT_POSTER = 'image/jpeg,image/png,image/webp'

/**
 * Grab a still out of the uploaded file, in the browser, so a video always has
 * a thumbnail without the admin having to make one and without the server
 * needing ffmpeg. Seeks a little way in rather than to frame zero, which on a
 * screen recording is usually a blank or fading-in desktop.
 *
 * Best-effort by design: a codec the browser cannot decode, or a seek that
 * never fires, resolves to null and the upload simply goes without a poster.
 */
export function capturePoster(file, { seekTo = 1.5, timeoutMs = 8000 } = {}) {
  return new Promise((resolve) => {
    let settled = false
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    const done = (value) => {
      if (settled) return
      settled = true
      URL.revokeObjectURL(url)
      video.removeAttribute('src')
      resolve(value)
    }
    const timer = setTimeout(() => done(null), timeoutMs)

    video.preload = 'metadata'
    video.muted = true
    video.playsInline = true
    video.onerror = () => { clearTimeout(timer); done(null) }
    video.onloadedmetadata = () => {
      // A very short clip has no 1.5s to seek to; take a quarter of the way in.
      const target = Number.isFinite(video.duration) && video.duration > 0
        ? Math.min(seekTo, video.duration / 4)
        : 0
      video.currentTime = target
    }
    video.onseeked = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = video.videoWidth || 1280
        canvas.height = video.videoHeight || 720
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(
          (blob) => {
            clearTimeout(timer)
            done(blob ? new File([blob], 'poster.jpg', { type: 'image/jpeg' }) : null)
          },
          'image/jpeg',
          0.82,
        )
      } catch {
        clearTimeout(timer)
        done(null)
      }
    }
    video.src = url
  })
}

function Field({ label, hint, children }) {
  return (
    <label className="block mb-4">
      <span className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">{label}</span>
      {children}
      {hint && <span className="block mt-1 text-xs text-pb-faint">{hint}</span>}
    </label>
  )
}

const INPUT = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text focus:outline-none focus:border-accent'

/**
 * Create or edit one video. `video` null means create, in which case a file is
 * required; editing leaves the existing file alone unless a new one is picked.
 */
export function VideoEditorModal({ video, onClose, onSaved }) {
  const editing = !!video
  const [title, setTitle] = useState(video?.title ?? '')
  const [description, setDescription] = useState(video?.description ?? '')
  const [moduleLabel, setModuleLabel] = useState(video?.module_label ?? '')
  const [videoFile, setVideoFile] = useState(null)
  const [posterFile, setPosterFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)
  const titleRef = useRef(null)

  useEffect(() => { titleRef.current?.focus() }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, busy])

  const pickVideo = (file) => {
    setVideoFile(file || null)
    setError(null)
    if (!file) return
    if (file.size > MAX_VIDEO_MB * 1024 * 1024) {
      setError(`That file is ${Math.round(file.size / 1024 / 1024)}MB. The limit is ${MAX_VIDEO_MB}MB.`)
    }
  }

  const save = async (e) => {
    e.preventDefault()
    if (busy) return
    if (!title.trim()) { setError('Give the video a title.'); return }
    if (!editing && !videoFile) { setError('Choose a video file to upload.'); return }

    setBusy(true)
    setError(null)
    try {
      // No poster chosen and a new file picked: take a frame from it, so the
      // library never ends up with a card that has nothing to show.
      let poster = posterFile
      if (!poster && videoFile) {
        setNote('Grabbing a thumbnail from the video…')
        poster = await capturePoster(videoFile)
      }
      setNote(videoFile ? 'Uploading…' : 'Saving…')

      const fields = { title: title.trim(), description, module_label: moduleLabel }
      const saved = editing
        ? await api.adminUpdateVideo(video.id, fields, videoFile, poster)
        : await api.adminCreateVideo(fields, videoFile, poster)
      onSaved(saved)
    } catch (err) {
      setError(err.message || 'That did not save.')
    } finally {
      setBusy(false)
      setNote(null)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm overflow-y-auto p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label={editing ? 'Edit video' : 'Add video'}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose() }}
    >
      <form
        onSubmit={save}
        className="mx-auto max-w-lg bg-pb-surface border pb-hairline rounded-xl p-6"
      >
        <h2 className="font-display font-bold text-xl text-pb-text mb-5">
          {editing ? 'Edit video' : 'Add video'}
        </h2>

        <Field label="Title">
          <input type="text" ref={titleRef} className={INPUT} value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="BetterCricket - Merge Players" />
        </Field>

        <Field label="Description" hint="Shown on the card and above the player.">
          <textarea className={INPUT} rows={4} value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What this walkthrough covers." />
        </Field>

        <Field label="Module" hint="Optional. The small label above the title, e.g. BetterStats.">
          <input type="text" className={INPUT} value={moduleLabel} onChange={(e) => setModuleLabel(e.target.value)}
                 placeholder="BetterStats" />
        </Field>

        <Field
          label={editing ? 'Replace video file' : 'Video file'}
          hint={editing
            ? `Leave empty to keep the current file. MP4 or WebM, up to ${MAX_VIDEO_MB}MB.`
            : `MP4 or WebM, up to ${MAX_VIDEO_MB}MB.`}
        >
          <input type="file" accept={ACCEPT_VIDEO} className={`${INPUT} file:mr-3 file:rounded file:border-0 file:px-3 file:py-1 file:text-xs`}
                 onChange={(e) => pickVideo(e.target.files?.[0])} />
        </Field>

        <Field label="Thumbnail" hint="Optional. Left empty, a frame is taken from the video itself.">
          <input type="file" accept={ACCEPT_POSTER} className={`${INPUT} file:mr-3 file:rounded file:border-0 file:px-3 file:py-1 file:text-xs`}
                 onChange={(e) => setPosterFile(e.target.files?.[0] || null)} />
        </Field>

        {error && <p className="mb-4 text-sm" style={{ color: 'var(--pb-red-ink, #f87171)' }}>{error}</p>}
        {note && <p className="mb-4 text-sm text-pb-dim">{note}</p>}

        <div className="flex gap-3 justify-end pt-2">
          <button type="button" onClick={onClose} disabled={busy}
                  className="px-4 py-2 border pb-hairline rounded font-mono text-[11px] tracking-wide2 text-pb-dim hover:text-pb-text disabled:opacity-50">
            CANCEL
          </button>
          <button type="submit" disabled={busy}
                  className="px-5 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-60"
                  style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'SAVING…' : editing ? 'SAVE CHANGES' : 'UPLOAD VIDEO'}
          </button>
        </div>
      </form>
    </div>
  )
}

/** The row of controls above the grid. */
export function VideoAdminBar({ onAdd, reordering, onToggleReorder, count, saving }) {
  return (
    <div className="mb-8 flex flex-wrap items-center gap-3 pb-card p-3">
      <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Super admin</span>
      <button type="button" onClick={onAdd}
              className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
        + ADD VIDEO
      </button>
      {count > 1 && (
        <button type="button" onClick={onToggleReorder}
                className="px-4 py-2 border pb-hairline rounded font-mono text-[11px] tracking-wide2 text-pb-dim hover:text-pb-text">
          {reordering ? 'DONE REORDERING' : 'REORDER'}
        </button>
      )}
      {reordering && <span className="text-xs text-pb-dim">Drag a card to change the order visitors see.</span>}
      {saving && <span className="text-xs text-pb-dim">Saving order…</span>}
    </div>
  )
}

/** Edit / Delete beside one card. */
export function VideoCardControls({ video, onEdit, onDeleted, onError }) {
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    if (busy) return
    const ok = window.confirm(
      `Delete “${video.title}”?\n\nThis removes the entry and its video file for good. ` +
      `Anyone holding a link to it will get the videos list instead.`,
    )
    if (!ok) return
    setBusy(true)
    try {
      await api.adminDeleteVideo(video.id)
      onDeleted(video)
    } catch (err) {
      onError?.(err.message || 'That did not delete.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-2 flex items-center gap-3">
      <button type="button" onClick={() => onEdit(video)}
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
        EDIT
      </button>
      <button type="button" onClick={remove} disabled={busy}
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50">
        {busy ? 'DELETING…' : 'DELETE'}
      </button>
    </div>
  )
}
