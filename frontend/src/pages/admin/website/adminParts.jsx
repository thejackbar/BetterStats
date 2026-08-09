// Shared bits for the Website admin sections.
import { useState, useCallback } from 'react'
import { validateImageFile, DIRECT_IMAGE_MAX_BYTES } from '../../../lib/validation'

export function useFlash() {
  const [flash, setFlash] = useState(null)
  const show = useCallback((msg) => {
    setFlash(msg)
    setTimeout(() => setFlash(null), 3000)
  }, [])
  return [flash, show]
}

export function Flash({ msg }) {
  if (!msg) return null
  return <div className="mb-4 px-4 py-2 rounded bg-green-500/10 text-green-400 text-sm font-mono">{msg}</div>
}

export function ErrorMsg({ msg }) {
  if (!msg) return null
  return <div className="mb-4 px-4 py-2 rounded bg-red-500/10 text-red-400 text-sm">{msg}</div>
}

// A file-picker styled as a button, with client-side image validation.
export function UploadButton({ label = 'UPLOAD', uploading, onFile, className = '' }) {
  const [err, setErr] = useState(null)
  return (
    <label className={`inline-flex items-center justify-center font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text px-3 py-1.5 rounded border pb-hairline cursor-pointer ${className}`}>
      {uploading ? 'UPLOADING…' : label}
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          e.target.value = ''
          if (!f) return
          // Direct upload, no crop editor — cap at what the server accepts.
          const v = validateImageFile(f, { maxBytes: DIRECT_IMAGE_MAX_BYTES })
          if (v) { setErr(v); return }
          setErr(null)
          onFile(f)
        }}
      />
      {err && <span className="ml-2 text-red-400">{err}</span>}
    </label>
  )
}

export const inputCls =
  'w-full px-3 py-2 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent'

export const btnPrimary =
  'px-4 py-2 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-40'

export const btnGhost =
  'px-3 py-1.5 rounded text-xs font-mono tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text'

export const btnDanger =
  'px-2 py-1 rounded text-[10px] font-mono text-red-400 hover:text-red-300 border border-red-400/30'
