// Sizing helpers that let a board fill the screen instead of scrolling.
//
// useFitHeight(): the height from the top of an element down to the bottom of
// the viewport. Put the ref on the panel and give the panel that height; the
// panel's own list then divides what is left between its rows.
//
// useBoxHeight(): the live height of an element (its list), so a row can work
// out how much room it has and pick how much to show.
//
// Both are measured, not guessed: the banners, rule strip and filter bar above a
// panel change height all the time, and a hard-coded `100vh - 300px` was wrong
// every time one of them wrapped.
import { useState, useLayoutEffect, useRef, useCallback } from 'react'

export function useFitHeight({ enabled = true, bottom = 16, min = 240 } = {}) {
  const ref = useRef(null)
  const [height, setHeight] = useState(null)

  const measure = useCallback(() => {
    const el = ref.current
    if (!enabled || !el) { setHeight((h) => (h === null ? h : null)); return }
    // Top of the panel on the page, not on the screen, so scrolling the page
    // does not resize the panel under the reader.
    const top = el.getBoundingClientRect().top + window.scrollY
    const next = Math.max(min, Math.floor(window.innerHeight - top - bottom))
    setHeight((h) => (h === next ? h : next))
  }, [enabled, bottom, min])

  useLayoutEffect(() => {
    measure()
    if (!enabled) return undefined
    let raf = 0
    const again = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(measure) }
    window.addEventListener('resize', again)
    // Anything above the panel growing or shrinking moves its top. Our own
    // height change lands on the same value, so this settles after one pass.
    const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(again) : null
    if (ro) ro.observe(document.body)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', again)
      if (ro) ro.disconnect()
    }
  }, [measure, enabled])

  return [ref, height]
}

export function useBoxHeight() {
  const ref = useRef(null)
  const [height, setHeight] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const read = () => setHeight((h) => { const n = Math.floor(el.clientHeight); return h === n ? h : n })
    read()
    if (typeof ResizeObserver !== 'function') return undefined
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, height]
}

// How much a slot row shows, from the room each row has. `full` is the card the
// board has always drawn (two or three lines); `compact` keeps the name and one
// line; `tight` is a single line. Rows never go below the `tight` height: past
// that the list scrolls rather than crushing the names.
export const ROW_MIN = 30
export function rowDensity(listHeight, rows, { gap = 4, pad = 12, full = 56, compact = 40 } = {}) {
  if (!listHeight || !rows) return 'full'
  const per = (listHeight - pad - gap * Math.max(0, rows - 1)) / rows
  if (per >= full) return 'full'
  if (per >= compact) return 'compact'
  return 'tight'
}
