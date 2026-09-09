// The canvas a post is designed on.
//
// Every built-in template now takes the real width and height and carries its
// own design for each of the three shapes — see postAspect.js, which owns the
// vocabulary a template designs against. So a portrait post is a portrait
// design, not a square one placed inside a taller box.
//
// The scorecards are the exception and keep their own fixed 1920×1080: they are
// a landscape document rather than a feed post, and they are offered no size
// picker. `PostFrame` below is what places one of those into a canvas that is
// not its own shape — the only remaining caller of it.
//
// ONE definition of the maths, used by the live canvas AND the off-screen export
// node — two copies is how the preview and the downloaded PNG start disagreeing
// about where the artwork sits.

export const POST_SIZES = [
  { key: 'square',   w: 1080, h: 1080, label: 'Square',   sub: '1:1',  where: 'Feed post' },
  { key: 'portrait', w: 1080, h: 1350, label: 'Portrait', sub: '4:5',  where: 'Instagram feed' },
  { key: 'story',    w: 1080, h: 1920, label: 'Story',    sub: '9:16', where: 'Story / Reel' },
]

export const DEFAULT_POST_SIZE = 'square'

export const postSizeOf = (key) => POST_SIZES.find((s) => s.key === key) || POST_SIZES[0]

/**
 * How much to scale a nativeW×nativeH layout to sit in a canvasW×canvasH post.
 *   fit  → the whole layout is visible, letterboxed onto the background
 *   fill → the layout covers the canvas, overflow cropped evenly
 * Returns the scale plus the top-left offset that centres it.
 */
export function frameTransform(canvasW, canvasH, nativeW, nativeH, mode = 'fit') {
  const sx = canvasW / nativeW
  const sy = canvasH / nativeH
  const scale = mode === 'fill' ? Math.max(sx, sy) : Math.min(sx, sy)
  return {
    scale,
    left: (canvasW - nativeW * scale) / 2,
    top: (canvasH - nativeH * scale) / 2,
    // True when the layout doesn't reach the canvas edges — the caller uses
    // this to explain the bands rather than letting them read as a bug.
    letterboxed: nativeW * scale < canvasW - 0.5 || nativeH * scale < canvasH - 0.5,
  }
}

/**
 * Places a fixed-size template into the post canvas. A square canvas holding a
 * square template resolves to scale 1 and no offset, so the common case renders
 * byte-for-byte what it did before this existed.
 */
export function PostFrame({ canvasW, canvasH, nativeW, nativeH, mode = 'fit', children }) {
  const { scale, left, top } = frameTransform(canvasW, canvasH, nativeW, nativeH, mode)
  if (scale === 1 && left === 0 && top === 0) return children
  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
      <div data-post-frame="" style={{
        position: 'absolute', left, top,
        width: nativeW, height: nativeH,
        transform: `scale(${scale})`, transformOrigin: 'top left',
      }}>{children}</div>
    </div>
  )
}

export default POST_SIZES
