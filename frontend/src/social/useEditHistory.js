// Undo / redo + the action log shown in the Layers panel.
//
// Wrap useBlankLayer's mutators so every discrete edit pushes one snapshot.
// Drag/resize call commit() ONCE on pointerup (not per pointermove) — pass
// `onCommit` through to <BlankCanvas> for that.
//
//   const layer   = useBlankLayer(defaultBlankItems())
//   const history = useEditHistory(layer)
//
//   history.run('Added text', () => layer.add('text'))   // snapshot, then mutate
//   history.commit('Moved block')                        // snapshot after the fact
//   history.undo() / history.redo() / history.canUndo / history.canRedo / history.log
//
// Bind ⌘Z / ⇧⌘Z and Delete at the editor shell, ignoring events whose target is
// an INPUT / TEXTAREA / SELECT.
import { useCallback, useRef, useState } from 'react'

const LIMIT = 40
const LOG_LIMIT = 8

export function useEditHistory(layer) {
  const past = useRef([])
  const future = useRef([])
  const [log, setLog] = useState([])
  const [, force] = useState(0)
  const bump = () => force(n => n + 1)

  const note = (label) => setLog(l => [{ label, t: Date.now() }, ...l].slice(0, LOG_LIMIT))

  // Snapshot BEFORE the mutation, so undo restores the pre-edit state.
  const run = useCallback((label, mutate) => {
    past.current = [...past.current, layer.items].slice(-LIMIT)
    future.current = []
    mutate()
    note(label)
    bump()
  }, [layer.items])

  // For interactions that already mutated (drag, resize): the snapshot we push is
  // the state captured when the gesture started.
  const commit = useCallback((label, before) => {
    past.current = [...past.current, before ?? layer.items].slice(-LIMIT)
    future.current = []
    note(label)
    bump()
  }, [layer.items])

  const undo = useCallback(() => {
    if (!past.current.length) return
    const prev = past.current[past.current.length - 1]
    past.current = past.current.slice(0, -1)
    future.current = [layer.items, ...future.current]
    layer.reset(prev)
    note('Undo')
    bump()
  }, [layer])

  const redo = useCallback(() => {
    if (!future.current.length) return
    const next = future.current[0]
    future.current = future.current.slice(1)
    past.current = [...past.current, layer.items]
    layer.reset(next)
    note('Redo')
    bump()
  }, [layer])

  const clear = useCallback(() => { past.current = []; future.current = []; bump() }, [])

  return {
    run, commit, undo, redo, clear, log,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
    depth: past.current.length,
  }
}

export default useEditHistory
