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
  // dir: 'front' | 'back' | 'up' | 'down' (up = towards the front / later in array)
  const reorder = (id, dir) => {
    setItems((its) => {
      const i = its.findIndex((it) => it.id === id)
      if (i < 0) return its
      const next = its.slice()
      if (dir === 'front' || dir === 'back') {
        const j = dir === 'front' ? next.length - 1 : 0
        if (i === j) return its
        const [it] = next.splice(i, 1)
        next.splice(j, 0, it)
        return next
      }
      const j = dir === 'up' ? i + 1 : i - 1
      if (j < 0 || j >= next.length) return its
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
      next.splice(to, 0, m)
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
    add, remove, duplicate, reorder, moveBefore, align, applyStarter, reset,
  }
}
