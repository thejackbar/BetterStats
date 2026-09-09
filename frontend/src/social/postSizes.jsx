// The canvas a post is designed on.
//
// Every built-in template COMPOSES its artwork at 1080×1080 (ART_W × ART_H) and
// renders it into whichever of these canvases is picked — see PostCanvas in
// social/cricket-templates, which every template's root goes through. A
// template is therefore NOT re-laid-out per size (three separately-tuned copies
// of one layout is how they start disagreeing with each other): the artwork
// keeps its own proportions, sits centred, and the template's own background,
// texture and full-height chrome carry out to the real canvas edges.
//
// WIDTH IS 1080 IN ALL THREE, which is what makes that work. Adding a size that
// is NOT 1080 wide means deciding how the artwork scales, and that is a
// different change from this one.
//
// The Blank Canvas is different again: its blocks carry their own x/y, so a
// portrait canvas there is genuinely portrait with nothing to place.
//
// PostFrame/frameTransform below are the FALLBACK for a layout that cannot fill
// a canvas of another shape — today only the 1920×1080 scorecards, which are
// excluded from the size picker entirely. Kept because a future template with
// its own fixed w/h would need it; nothing else should reach for it.

export const POST_SIZES = [
  { key: 'square',   w: 1080, h: 1080, label: 'Square',   sub: '1:1',  where: 'Feed post' },
  { key: 'portrait', w: 1080, h: 1350, label: 'Portrait', sub: '4:5',  where: 'Instagram feed' },
  { key: 'story',    w: 1080, h: 1920, label: 'Story',    sub: '9:16', where: 'Story / Reel' },
]

export const DEFAULT_POST_SIZE = 'square'

// The size a template's artwork is composed at, and the band a taller canvas
// leaves above and below it. One definition, read by the templates themselves.
export const ART_W = 1080
export const ART_H = 1080
export function matteFor(h) {
  return Math.max(0, Math.round(((h || ART_H) - ART_H) / 2))
}

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
