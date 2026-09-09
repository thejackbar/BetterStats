// A self-contained "layer" of freeform blocks (text / image / element / brand)
// with its own selection + all the edit operations the Blank Canvas editor and
// preview need. Used twice in AdminSocialPost: once as the standalone Blank
// Canvas, and once as the "Custom Edit" overlay that sits on top of any real
// template. Keeping it in a hook means both instances behave identically with
// no duplicated handler logic.
import { useState } from 'react'
import { newBlankItem, starterItems, itemBBox } from './blank-template'

const genId = () => `bi${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`

export function useBlankLayer(initial) {
  const [items, setItems] = useState(initial)
  const [selIds, setSelIds] = useState([])

  const patchMany = (patchMap) => setItems((its) => its.map((it) => (patchMap[it.id] ? { ...it, ...patchMap[it.id] } : it)))
  const update = (id, patch) => patchMany({ [id]: patch })
  const select = (id, additive) => setSelIds((cur) => (additive ? (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]) : [id]))
  const deselect = () => setSelIds([])

  const add = (type, opts) => {
    const it = newBlankItem(type, opts)
    if (!it) return
    setItems((its) => [...its, it])
    setSelIds([it.id])
    return it
  }
  const remove = (id) => {
    setItems((its) => its.filter((it) => it.id !== id))
    setSelIds((cur) => cur.filter((x) => x !== id))
  }
  const duplicate = (id) => {
    const src = items.find((it) => it.id === id)
    if (!src) return
    const copy = { ...src, id: genId(), x: src.x + 30, y: src.y + 30 }
    setItems((its) => [...its, copy])
    setSelIds([copy.id])
  }
  // Where the built-in layout sits in the stack. Items carrying `behind` are
  // drawn under it, the rest over it — and the array is kept PARTITIONED with
  // the behind group first, so array order is still simply z-order and an
  // adjacent swap is still an adjacent swap. Without that invariant a stack of
  // [behind, front, behind] would step "up" into something that isn't its
  // visual neighbour.
  const behindCount = (its) => its.filter((it) => it.behind).length

  // Move one block across the layout boundary, landing it against the layout on
  // the side it just arrived at (send-backward from the front lands directly
  // behind the layout, not at the very back of everything).
  const setBehind = (id, behind) => {
    setItems((its) => {
      const i = its.findIndex((it) => it.id === id)
      if (i < 0 || !!its[i].behind === behind) return its
      const next = its.slice()
      const [it] = next.splice(i, 1)
      // The boundary index is the same number either way: the end of the behind
      // group and the start of the front group are the same slot.
      next.splice(behindCount(next), 0, { ...it, behind: behind || undefined })
      return next
    })
  }

  // dir: 'front' | 'back' | 'up' | 'down' (up = towards the front / later in array)
  // crossLayout: stepping off the end of a group moves the block past the
  // built-in layout rather than doing nothing. Only the Custom Edit overlay
  // passes it — the standalone Blank Canvas has no layout to be behind.
  const reorder = (id, dir, { crossLayout = false } = {}) => {
    setItems((its) => {
      const i = its.findIndex((it) => it.id === id)
      if (i < 0) return its
      const next = its.slice()
      const b = behindCount(its)
      const isBehind = !!its[i].behind
      if (dir === 'front' || dir === 'back') {
        const [it] = next.splice(i, 1)
        // With a layout in the stack, the very back is behind it and the very
        // front is over it; without one, it is just the ends of the array.
        const moved = crossLayout ? { ...it, behind: dir === 'back' || undefined } : it
        next.splice(dir === 'front' ? next.length : 0, 0, moved)
        return next
      }
      // The group this block lives in, as a half-open range of the array.
      const lo = crossLayout && !isBehind ? b : 0
      const hi = crossLayout && isBehind ? b : next.length
      const j = dir === 'up' ? i + 1 : i - 1
      if (j < lo || j >= hi) {
        // Off the end of its own group: cross the layout, or stay put.
        if (!crossLayout) return its
        if (dir === 'up' && isBehind) { const [it] = next.splice(i, 1); next.splice(b - 1, 0, { ...it, behind: undefined }); return next }
        if (dir === 'down' && !isBehind) { const [it] = next.splice(i, 1); next.splice(b, 0, { ...it, behind: true }); return next }
        return its
      }
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }
  const moveBefore = (dragId, targetId) => {
    setItems((its) => {
      if (dragId === targetId) return its
      const from = its.findIndex((x) => x.id === dragId)
      if (from < 0) return its
      const next = its.slice()
      const [m] = next.splice(from, 1)
      const to = next.findIndex((x) => x.id === targetId)
      if (to < 0) return its
      // Dropped onto a row on the other side of the layout, the block takes
      // that side — otherwise the array stops being partitioned and every
      // later adjacent swap steps into something that is not its neighbour.
      next.splice(to, 0, { ...m, behind: next[to].behind })
      return next
    })
  }
  const align = (mode) => {
    const sel = items.filter((it) => selIds.includes(it.id))
    if (sel.length < 2) return
    const boxes = sel.map((it) => ({ id: it.id, bb: itemBBox(it) }))
    const minX = Math.min(...boxes.map((b) => b.bb.x))
    const maxR = Math.max(...boxes.map((b) => b.bb.x + b.bb.w))
    const cx = (minX + maxR) / 2
    const patch = {}
    boxes.forEach((b) => {
      let x
      if (mode === 'left') x = minX
      else if (mode === 'right') x = maxR - b.bb.w
      else x = cx - b.bb.w / 2
      patch[b.id] = { x: Math.round(x) }
    })
    patchMany(patch)
  }
  const applyStarter = (key) => { setItems(starterItems(key)); setSelIds([]) }
  const reset = (val) => { setItems(val || []); setSelIds([]) }

  return {
    items, selIds, setItems, setSelIds,
    patchMany, update, select, deselect,
    add, remove, duplicate, reorder, setBehind, moveBefore, align, applyStarter, reset,
  }
}
