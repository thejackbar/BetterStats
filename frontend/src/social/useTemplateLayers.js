// The stack for a built-in template: the layout's own elements and the blocks
// somebody has added, in one order.
//
// The order held here is a PREFERENCE over what the template naturally paints,
// not a copy of it — `applyOrder` in postLayers.jsx puts anything this has
// never heard of back where it would have been. That is what lets the list
// survive a template re-rendering with an element more or less than last time
// (a POTM strip appearing, a block added) instead of scrambling.
//
// EVERY PIECE OF STATE CARRIES THE TEMPLATE IT BELONGS TO, and a mismatch is
// resolved during render rather than by an effect that clears it afterwards.
// Restoring a saved design sets the template and its stacking order in the same
// tick, so a clear-on-change effect would land second and wipe what was just
// restored.
//
// PICKING ANOTHER TEMPLATE IS A NEW DESIGN, so the stack starts fresh rather
// than being kept per template and handed back later. That matches what
// `selectTemplate` already does (it turns Custom Edit off), and an arrangement
// silently reappearing on a layout somebody came back to a week later is a
// worse surprise than starting from what the layout draws. Saving it as a
// template is how you keep one.
import { useCallback, useMemo, useRef, useState } from 'react'
import { applyOrder } from './postLayers'

const EMPTY_HIDDEN = new Set()

export function useTemplateLayers(templateId) {
  const [state, setState] = useState(() => ({ forId: templateId, layers: [], order: [], hidden: EMPTY_HIDDEN }))
  const fresh = { forId: templateId, layers: [], order: [], hidden: EMPTY_HIDDEN }
  const cur = state.forId === templateId ? state : fresh
  const { layers, order, hidden } = cur

  // Writers always stamp the template they are about, so a write that races a
  // template change belongs to whichever template was on screen when it ran.
  const idRef = useRef(templateId)
  idRef.current = templateId
  const patch = useCallback((fn) => {
    setState((s) => {
      const base = s.forId === idRef.current ? s : { forId: idRef.current, layers: [], order: [], hidden: EMPTY_HIDDEN }
      return { ...base, ...fn(base), forId: idRef.current }
    })
  }, [])

  // Called from render by LayerRoot, so it must not set state when nothing has
  // actually changed or the render loops.
  const register = useCallback((next) => {
    setState((s) => {
      const same = s.forId === idRef.current
        && s.layers.length === next.length
        && s.layers.every((l, i) => l.id === next[i].id && l.label === next[i].label)
      if (same) return s
      const base = s.forId === idRef.current ? s : { forId: idRef.current, layers: [], order: [], hidden: EMPTY_HIDDEN }
      return { ...base, forId: idRef.current, layers: next }
    })
  }, [])

  const ids = useMemo(() => layers.map((l) => l.id), [layers])

  // The full stack as it currently paints, with the blocks folded in. Front of
  // the stack is LAST, matching the array-order-is-z-order rule the freeform
  // blocks already keep.
  const stack = useCallback((blocks = []) => {
    const natural = [...ids, ...blocks.map((b) => b.id)]
    const byId = new Map([
      ...layers.map((l) => [l.id, { ...l, kind: 'template' }]),
      ...blocks.map((b) => [b.id, { id: b.id, kind: 'block', item: b }]),
    ])
    return applyOrder(natural, order).map((id) => byId.get(id)).filter(Boolean)
  }, [ids, layers, order])

  // Reordering writes the WHOLE stack back, never the moved pair. A partial
  // order would be reconciled against stale neighbours on the next render.
  const commit = useCallback((nextIds) => patch(() => ({ order: nextIds })), [patch])

  const move = useCallback((allIds, dragId, targetId) => {
    if (dragId === targetId) return
    const from = allIds.indexOf(dragId)
    const to = allIds.indexOf(targetId)
    if (from < 0 || to < 0) return
    const next = allIds.slice()
    next.splice(from, 1)
    next.splice(next.indexOf(targetId) + (from < to ? 1 : 0), 0, dragId)
    commit(next)
  }, [commit])

  const step = useCallback((allIds, id, dir) => {
    const i = allIds.indexOf(id)
    if (i < 0) return
    const j = dir === 'up' ? i + 1 : i - 1
    if (j < 0 || j >= allIds.length) return
    const next = allIds.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    commit(next)
  }, [commit])

  const send = useCallback((allIds, id, where) => {
    const i = allIds.indexOf(id)
    if (i < 0) return
    const next = allIds.slice()
    const [m] = next.splice(i, 1)
    next.splice(where === 'front' ? next.length : 0, 0, m)
    commit(next)
  }, [commit])

  const toggleHidden = useCallback((id) => {
    patch((base) => {
      const next = new Set(base.hidden)
      if (next.has(id)) next.delete(id); else next.add(id)
      return { hidden: next }
    })
  }, [patch])

  const clear = useCallback(() => patch(() => ({ order: [], hidden: EMPTY_HIDDEN })), [patch])

  // What a saved template carries. Ids are structural (`t:div#2`) or an
  // explicit name, never a block's own id alone — a saved order that mentions
  // blocks is meaningless without them, and the blocks are saved beside it.
  const serialise = useCallback(
    () => (order.length || hidden.size ? { order, hidden: [...hidden] } : null),
    [order, hidden],
  )
  // Restoring names the template it is for, because the caller sets the
  // template and the stack in one go and `templateId` here is still the old one
  // until the next render.
  const restore = useCallback((forId, saved) => {
    setState({
      forId,
      layers: [],
      order: Array.isArray(saved?.order) ? saved.order : [],
      hidden: new Set(Array.isArray(saved?.hidden) ? saved.hidden : []),
    })
  }, [])

  const touched = order.length > 0 || hidden.size > 0

  return { layers, order, hidden, register, stack, move, step, send, toggleHidden, clear, serialise, restore, touched }
}
