// Carousel pages for the post designer.
//
// The live page's blocks stay in useBlankLayer (so every existing handler keeps
// working untouched); this hook only stashes/restores the other pages around it.
//
//   const layer = useBlankLayer(defaultBlankItems())
//   const pages = usePages(layer)
//
//   pages.count / pages.index / pages.goTo(i) / pages.add() / pages.duplicate() / pages.remove(i)
//   pages.all()   → items[][] in page order — use this for multi-slide export
import { useCallback, useRef, useState } from 'react'
import { starterItems } from './blank-template'

export function usePages(layer, { onPageChange } = {}) {
  const store = useRef({})            // { [pageIndex]: items[] } for the INACTIVE pages
  const [index, setIndex] = useState(0)
  const [count, setCount] = useState(1)

  const stash = useCallback(() => { store.current[index] = layer.items }, [index, layer.items])

  const goTo = useCallback((i) => {
    if (i === index) return
    stash()
    layer.reset(store.current[i] || [])
    setIndex(i)
    onPageChange?.(i)
  }, [index, stash, layer, onPageChange])

  const add = useCallback(() => {
    stash()
    const i = count
    setCount(c => c + 1)
    layer.reset(starterItems('blank'))
    setIndex(i)
    onPageChange?.(i)
  }, [count, stash, layer, onPageChange])

  const duplicate = useCallback(() => {
    stash()
    // New ids so the copy's blocks are independently selectable.
    store.current[count] = layer.items.map(it => ({ ...it, id: `${it.id}c${count}` }))
    setCount(c => c + 1)
  }, [count, stash, layer.items])

  const remove = useCallback((i) => {
    if (count < 2) return
    stash()
    const kept = []
    for (let k = 0; k < count; k++) if (k !== i) kept.push(store.current[k] || [])
    store.current = {}
    kept.forEach((v, k) => { store.current[k] = v })
    const next = Math.max(0, Math.min(kept.length - 1, index > i ? index - 1 : index))
    setCount(kept.length)
    setIndex(next)
    layer.reset(store.current[next] || [])
    onPageChange?.(next)
  }, [count, index, stash, layer, onPageChange])

  const all = useCallback(() => {
    const out = []
    for (let k = 0; k < count; k++) out.push(k === index ? layer.items : (store.current[k] || []))
    return out
  }, [count, index, layer.items])

  return { index, count, goTo, add, duplicate, remove, all }
}

export default usePages
