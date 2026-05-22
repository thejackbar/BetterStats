import { useEffect, useRef, useState, useCallback } from 'react'
import { Cropper } from 'react-cropper'
import 'cropperjs/dist/cropper.css'

// Reusable crop + background-removal modal.
//
// Props:
//   open                 - whether modal is shown
//   source               - File | Blob | string URL | null  (image to edit)
//   title                - heading shown at the top
//   aspect               - aspect ratio number (1, 16/9, etc.) or null for free
//   cropShape            - 'rect' (default) or 'round'  (round forces aspect=1)
//   allowBackgroundRemoval - bool, show "Remove background" button (default true)
//   outputType           - 'image/png' (default) or 'image/jpeg'
//   outputName           - filename for the resulting File
//   maxOutputSize        - max width/height of output canvas (default 1600)
//   onCancel             - () => void
//   onApply              - (file: File) => void | Promise<void>
export default function ImageEditorModal({
  open,
  source,
  title = 'Edit Image',
  aspect = null,
  cropShape = 'rect',
  allowBackgroundRemoval = true,
  outputType = 'image/png',
  outputName = 'edited.png',
  maxOutputSize = 1600,
  onCancel,
  onApply,
}) {
  const cropperRef = useRef(null)
  const [srcUrl, setSrcUrl] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [removingBg, setRemovingBg] = useState(false)
  const [applying, setApplying] = useState(false)
  const ownedBlobUrlRef = useRef(null)

  // Convert incoming source (File / Blob / URL) into a usable blob URL.
  useEffect(() => {
    if (!open || !source) {
      setSrcUrl(null)
      setLoadError(null)
      return
    }
    let cancelled = false

    const cleanup = () => {
      if (ownedBlobUrlRef.current) {
        URL.revokeObjectURL(ownedBlobUrlRef.current)
        ownedBlobUrlRef.current = null
      }
    }

    if (source instanceof File || source instanceof Blob) {
      cleanup()
      const url = URL.createObjectURL(source)
      ownedBlobUrlRef.current = url
      setSrcUrl(url)
      setLoadError(null)
    } else if (typeof source === 'string') {
      // For string URLs we always fetch and re-blob so the cropped canvas
      // isn't CORS-tainted (which would break toBlob).
      cleanup()
      setSrcUrl(null)
      setLoadError(null)
      fetch(source, { credentials: 'include', mode: 'cors' })
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob() })
        .then(blob => {
          if (cancelled) return
          const url = URL.createObjectURL(blob)
          ownedBlobUrlRef.current = url
          setSrcUrl(url)
        })
        .catch(err => {
          if (cancelled) return
          setLoadError(err.message || 'Could not load image')
        })
    }

    return () => { cancelled = true }
  }, [open, source])

  // Unmount cleanup
  useEffect(() => () => {
    if (ownedBlobUrlRef.current) {
      URL.revokeObjectURL(ownedBlobUrlRef.current)
      ownedBlobUrlRef.current = null
    }
  }, [])

  // Escape closes
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape' && !applying && !removingBg) onCancel?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, applying, removingBg, onCancel])

  const rotate = (deg) => cropperRef.current?.cropper?.rotate(deg)
  const reset = () => cropperRef.current?.cropper?.reset()

  const handleRemoveBg = useCallback(async () => {
    if (!srcUrl) return
    setRemovingBg(true)
    try {
      const { removeBackground } = await import('@imgly/background-removal')
      const blob = await removeBackground(srcUrl, { debug: false })
      if (ownedBlobUrlRef.current) URL.revokeObjectURL(ownedBlobUrlRef.current)
      const url = URL.createObjectURL(blob)
      ownedBlobUrlRef.current = url
      setSrcUrl(url)
    } catch (err) {
      setLoadError(err.message || 'Background removal failed')
    } finally {
      setRemovingBg(false)
    }
  }, [srcUrl])

  const handleApply = useCallback(async () => {
    const cropper = cropperRef.current?.cropper
    if (!cropper) return
    setApplying(true)
    try {
      const canvas = cropper.getCroppedCanvas({
        maxWidth: maxOutputSize,
        maxHeight: maxOutputSize,
        imageSmoothingQuality: 'high',
      })
      if (!canvas) throw new Error('Could not produce cropped canvas')
      // Round crop: mask the canvas to a circle before exporting.
      const finalCanvas = cropShape === 'round' ? maskToCircle(canvas) : canvas
      const blob = await new Promise((resolve, reject) => {
        finalCanvas.toBlob(
          b => b ? resolve(b) : reject(new Error('toBlob failed')),
          outputType,
          outputType === 'image/jpeg' ? 0.92 : undefined,
        )
      })
      const file = new File([blob], outputName, { type: outputType })
      await onApply?.(file)
    } catch (err) {
      setLoadError(err.message || 'Apply failed')
    } finally {
      setApplying(false)
    }
  }, [maxOutputSize, cropShape, outputType, outputName, onApply])

  if (!open) return null

  const effectiveAspect = cropShape === 'round' ? 1 : aspect

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70"
      style={{ backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget && !applying && !removingBg) onCancel?.() }}
    >
      <div className="bg-pb-surface pb-card w-full max-w-2xl mx-4 my-4 overflow-hidden flex flex-col max-h-[92vh]">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline-b shrink-0">
          <h2 className="text-pb-text text-sm font-semibold">{title}</h2>
          <button
            onClick={() => !applying && !removingBg && onCancel?.()}
            disabled={applying || removingBg}
            className="text-pb-faint hover:text-pb-text transition-colors font-mono text-[11px] px-2 py-1 disabled:opacity-40"
          >
            ✕
          </button>
        </div>

        <div className="px-5 py-4 overflow-auto flex-1">
          {loadError && (
            <p className="mb-3 text-[12px] font-mono text-red-400">{loadError}</p>
          )}
          {!srcUrl && !loadError && (
            <p className="font-mono text-[11px] text-pb-faint">Loading image…</p>
          )}
          {srcUrl && (
            <div className="relative bg-pb-surface2 rounded overflow-hidden" style={{ minHeight: 320 }}>
              <Cropper
                key={srcUrl}
                ref={cropperRef}
                src={srcUrl}
                style={{ height: 420, width: '100%' }}
                aspectRatio={effectiveAspect || NaN}
                viewMode={1}
                dragMode="move"
                autoCropArea={0.9}
                background={false}
                guides
                center
                responsive
                checkOrientation={false}
                cropBoxMovable
                cropBoxResizable
                toggleDragModeOnDblclick={false}
                restore={false}
              />
              {cropShape === 'round' && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <div className="text-[10px] font-mono text-white/50 bg-black/40 px-2 py-0.5 rounded">circular crop</div>
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 mt-3">
            <button
              type="button"
              onClick={() => rotate(-90)}
              disabled={!srcUrl || applying || removingBg}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
            >↺ Rotate left</button>
            <button
              type="button"
              onClick={() => rotate(90)}
              disabled={!srcUrl || applying || removingBg}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
            >↻ Rotate right</button>
            <button
              type="button"
              onClick={reset}
              disabled={!srcUrl || applying || removingBg}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-40"
            >Reset</button>
            {allowBackgroundRemoval && (
              <button
                type="button"
                onClick={handleRemoveBg}
                disabled={!srcUrl || applying || removingBg}
                className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
              >{removingBg ? '⏳ Removing background…' : '✂ Remove background'}</button>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t pb-hairline-t shrink-0">
          <button
            type="button"
            onClick={onCancel}
            disabled={applying || removingBg}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition disabled:opacity-40"
          >Cancel</button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!srcUrl || applying || removingBg}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 bg-pb-accent text-white hover:opacity-90 transition disabled:opacity-40"
          >{applying ? 'Applying…' : 'Apply'}</button>
        </div>
      </div>
    </div>
  )
}

function maskToCircle(canvas) {
  const out = document.createElement('canvas')
  out.width = canvas.width
  out.height = canvas.height
  const ctx = out.getContext('2d')
  ctx.save()
  ctx.beginPath()
  ctx.arc(out.width / 2, out.height / 2, Math.min(out.width, out.height) / 2, 0, Math.PI * 2)
  ctx.closePath()
  ctx.clip()
  ctx.drawImage(canvas, 0, 0)
  ctx.restore()
  return out
}
