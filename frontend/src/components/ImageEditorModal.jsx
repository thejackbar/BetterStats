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
//   allowBackgroundRemoval - bool, show the background-removal tools (default true):
//                            an AI subject cut-out (photos) + a colour-key flood
//                            fill with a tolerance slider (logos on solid backgrounds)
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
  const [keying, setKeying] = useState(false)
  const [showColourKey, setShowColourKey] = useState(false)
  const [tolerance, setTolerance] = useState(48)
  const [keyMode, setKeyMode] = useState('edges') // 'edges' | 'all'
  const [applying, setApplying] = useState(false)
  const ownedBlobUrlRef = useRef(null) // the originally-loaded source (base for colour keying)
  const derivedUrlRef = useRef(null)   // a processed result (AI cut-out or colour key)

  // Convert incoming source (File / Blob / URL) into a usable blob URL.
  useEffect(() => {
    if (!open || !source) {
      setSrcUrl(null)
      setLoadError(null)
      return
    }
    let cancelled = false
    setShowColourKey(false)

    const cleanup = () => {
      if (derivedUrlRef.current) {
        URL.revokeObjectURL(derivedUrlRef.current)
        derivedUrlRef.current = null
      }
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
    if (derivedUrlRef.current) {
      URL.revokeObjectURL(derivedUrlRef.current)
      derivedUrlRef.current = null
    }
    if (ownedBlobUrlRef.current) {
      URL.revokeObjectURL(ownedBlobUrlRef.current)
      ownedBlobUrlRef.current = null
    }
  }, [])

  // Escape closes
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape' && !applying && !removingBg && !keying) onCancel?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, applying, removingBg, keying, onCancel])

  const rotate = (deg) => cropperRef.current?.cropper?.rotate(deg)
  const reset = () => cropperRef.current?.cropper?.reset()

  const setDerived = useCallback((blob) => {
    if (derivedUrlRef.current) URL.revokeObjectURL(derivedUrlRef.current)
    const url = URL.createObjectURL(blob)
    derivedUrlRef.current = url
    setSrcUrl(url)
  }, [])

  // AI subject cut-out — good for photos (people, products). Runs on whatever
  // is currently shown.
  //
  // The underlying @imgly/background-removal call is a black-box WASM/ONNX
  // pipeline with no way to cancel it, and has been observed to never settle
  // (neither resolve nor reject) for some inputs. Race it against a timeout
  // so a stuck call always surfaces as an error instead of leaving the modal
  // permanently undismissable (Cancel/✕/Escape are all gated on `removingBg`).
  const handleRemoveBg = useCallback(async () => {
    if (!srcUrl) return
    setShowColourKey(false)
    setRemovingBg(true)
    try {
      const timeout = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Background removal timed out. Please try again or use "Remove background (logo)" instead.')), 30000)
      })
      const { removeBackground } = await import('@imgly/background-removal')
      const blob = await Promise.race([removeBackground(srcUrl, { debug: false }), timeout])
      setDerived(blob)
    } catch (err) {
      setLoadError(err.message || 'Background removal failed')
    } finally {
      setRemovingBg(false)
    }
  }, [srcUrl, setDerived])

  // Colour keying — clears the background colour, built for logos sitting on a
  // solid or near-solid background where the AI cut-out leaves a haze (no
  // photographic subject to lock onto). 'edges' floods inward from the border
  // (safe: keeps logo internals that share the background colour); 'all' matches
  // the colour everywhere, so it also clears pockets the logo fences off from
  // the edge. Always runs on the original so the tolerance slider isn't cumulative.
  const runColourKey = useCallback(async (tol, mode) => {
    const base = ownedBlobUrlRef.current
    if (!base) return
    setKeying(true)
    try {
      const blob = await keyOutBackgroundColour(base, tol, mode)
      setDerived(blob)
    } catch (err) {
      setLoadError(err.message || 'Colour keying failed')
    } finally {
      setKeying(false)
    }
  }, [setDerived])

  const handleColourKeyToggle = useCallback(() => {
    setShowColourKey((on) => {
      const next = !on
      if (next) runColourKey(tolerance, keyMode)
      return next
    })
  }, [runColourKey, tolerance, keyMode])

  const handleKeyModeChange = useCallback((mode) => {
    setKeyMode(mode)
    runColourKey(tolerance, mode)
  }, [runColourKey, tolerance])

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
      onClick={(e) => { if (e.target === e.currentTarget && !applying && !removingBg && !keying) onCancel?.() }}
    >
      <div className="bg-pb-surface pb-card w-full max-w-2xl mx-4 my-4 overflow-hidden flex flex-col max-h-[92vh]">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline-b shrink-0">
          <h2 className="text-pb-text text-sm font-semibold">{title}</h2>
          <button
            onClick={() => !applying && !removingBg && !keying && onCancel?.()}
            disabled={applying || removingBg || keying}
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
              disabled={!srcUrl || applying || removingBg || keying}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
            >↺ Rotate left</button>
            <button
              type="button"
              onClick={() => rotate(90)}
              disabled={!srcUrl || applying || removingBg || keying}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
            >↻ Rotate right</button>
            <button
              type="button"
              onClick={reset}
              disabled={!srcUrl || applying || removingBg || keying}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-40"
            >Reset</button>
            {allowBackgroundRemoval && (
              <>
                <button
                  type="button"
                  onClick={handleRemoveBg}
                  disabled={!srcUrl || applying || removingBg || keying}
                  title="Best for photos of people or products"
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-40"
                >{removingBg ? '⏳ Removing background…' : '✂ Remove background (photo)'}</button>
                <button
                  type="button"
                  onClick={handleColourKeyToggle}
                  disabled={!srcUrl || applying || removingBg || keying}
                  title="Best for logos on a solid or near-solid background"
                  className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline transition disabled:opacity-40 ${showColourKey ? 'bg-pb-surface2 text-pb-text' : 'text-pb-text hover:bg-pb-surface2'}`}
                >{keying ? '⏳ Keying colour…' : '🎨 Remove background (logo)'}</button>
              </>
            )}
          </div>

          {allowBackgroundRemoval && showColourKey && (
            <div className="mt-3 rounded border pb-hairline bg-pb-surface2 px-4 py-3">
              <div className="flex items-center justify-between gap-3 mb-3">
                <span className="font-mono text-[10px] tracking-wide2 text-pb-text">Reach</span>
                <div className="flex rounded border pb-hairline overflow-hidden">
                  <button
                    type="button"
                    onClick={() => handleKeyModeChange('edges')}
                    disabled={keying || removingBg || applying}
                    title="Clears background connected to the edges. Keeps logo internals."
                    className={`px-3 py-1 font-mono text-[10px] tracking-wide2 transition disabled:opacity-40 ${keyMode === 'edges' ? 'bg-pb-accent text-white' : 'text-pb-faint hover:text-pb-text'}`}
                  >Edges</button>
                  <button
                    type="button"
                    onClick={() => handleKeyModeChange('all')}
                    disabled={keying || removingBg || applying}
                    title="Clears the background colour everywhere, including pockets between the logo and text."
                    className={`px-3 py-1 font-mono text-[10px] tracking-wide2 transition disabled:opacity-40 ${keyMode === 'all' ? 'bg-pb-accent text-white' : 'text-pb-faint hover:text-pb-text'}`}
                  >Everywhere</button>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3">
                <label htmlFor="bg-tolerance" className="font-mono text-[10px] tracking-wide2 text-pb-text">
                  Colour match strength
                </label>
                <span className="font-mono text-[10px] text-pb-faint tabular-nums">{tolerance}</span>
              </div>
              <input
                id="bg-tolerance"
                type="range"
                min={8}
                max={200}
                step={1}
                value={tolerance}
                disabled={keying || removingBg || applying}
                onChange={(e) => setTolerance(Number(e.target.value))}
                onMouseUp={(e) => runColourKey(Number(e.target.value), keyMode)}
                onTouchEnd={(e) => runColourKey(Number(e.target.value), keyMode)}
                onKeyUp={(e) => runColourKey(Number(e.target.value), keyMode)}
                className="w-full mt-2 accent-pb-accent"
              />
              <p className="mt-2 font-mono text-[10px] leading-relaxed text-pb-faint">
                Clears the background colour. Drag up if it's still showing, down if it eats into
                the logo. If pockets near the text won't clear, switch Reach to "Everywhere".
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t pb-hairline-t shrink-0">
          <button
            type="button"
            onClick={onCancel}
            disabled={applying || removingBg || keying}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition disabled:opacity-40"
          >Cancel</button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!srcUrl || applying || removingBg || keying}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 bg-pb-accent text-white hover:opacity-90 transition disabled:opacity-40"
          >{applying ? 'Applying…' : 'Apply'}</button>
        </div>
      </div>
    </div>
  )
}

// Colour-key the background out of a logo. Samples the background colour from
// the four corners, then clears anything within `tolerance` of that colour. A
// feather band just past the tolerance softens anti-aliased edges so there's no
// jaggy halo. Returns a PNG blob.
//
// mode 'edges' (default): flood-fill from the border only, so logo internals
//   that happen to share the background colour are kept. Safe but leaves pockets
//   the logo fences off from the edge.
// mode 'all': match the colour at every pixel, clearing those fenced-off pockets
//   too. More thorough; can nibble dark parts of the logo at high tolerance.
async function keyOutBackgroundColour(url, tolerance, mode = 'edges') {
  const img = await new Promise((resolve, reject) => {
    const im = new Image()
    im.crossOrigin = 'anonymous'
    im.onload = () => resolve(im)
    im.onerror = () => reject(new Error('Could not load image for colour keying'))
    im.src = url
  })

  const w = img.naturalWidth
  const h = img.naturalHeight
  if (!w || !h) throw new Error('Image has no dimensions')

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(img, 0, 0)
  const image = ctx.getImageData(0, 0, w, h)
  const px = image.data

  // Background colour = average of the four corners.
  const corners = [0, (w - 1) * 4, (h - 1) * w * 4, ((h - 1) * w + (w - 1)) * 4]
  let br = 0, bg = 0, bb = 0
  for (const c of corners) { br += px[c]; bg += px[c + 1]; bb += px[c + 2] }
  br /= 4; bg /= 4; bb /= 4

  const tol = Math.max(1, tolerance)
  const tol2 = tol * tol
  const feather = tol * 1.6
  const feather2 = feather * feather

  // Apply the tolerance/feather test to one pixel. Returns true if it's full
  // background (alpha cleared), so the flood fill knows to keep spreading.
  const clearPixel = (o) => {
    const dr = px[o] - br
    const dg = px[o + 1] - bg
    const db = px[o + 2] - bb
    const dist2 = dr * dr + dg * dg + db * db
    if (dist2 <= tol2) {
      px[o + 3] = 0 // fully background → transparent
      return true
    }
    if (dist2 <= feather2) {
      // Edge band: scale alpha by how far into the band the pixel sits so the
      // cut-out feathers instead of leaving a hard ring.
      const t = (Math.sqrt(dist2) - tol) / (feather - tol)
      px[o + 3] = Math.round(px[o + 3] * t)
    }
    return false
  }

  if (mode === 'all') {
    for (let i = 0; i < w * h; i++) clearPixel(i * 4)
  } else {
    const visited = new Uint8Array(w * h)
    const stack = []
    const consider = (x, y) => {
      if (x < 0 || y < 0 || x >= w || y >= h) return
      const i = y * w + x
      if (visited[i]) return
      visited[i] = 1
      if (clearPixel(i * 4)) stack.push(i) // only flood through full background
    }
    for (let x = 0; x < w; x++) { consider(x, 0); consider(x, h - 1) }
    for (let y = 0; y < h; y++) { consider(0, y); consider(w - 1, y) }
    while (stack.length) {
      const i = stack.pop()
      const x = i % w
      const y = (i - x) / w
      consider(x + 1, y)
      consider(x - 1, y)
      consider(x, y + 1)
      consider(x, y - 1)
    }
  }

  ctx.putImageData(image, 0, 0)
  return new Promise((resolve, reject) => {
    canvas.toBlob(b => b ? resolve(b) : reject(new Error('toBlob failed')), 'image/png')
  })
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
