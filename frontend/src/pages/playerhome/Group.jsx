// A section of the player's page that can be minimised: a header with the title, a
// one-line summary that stays visible when it is closed (so a closed section still
// says "2 to answer" or "$60 owing"), and a chevron. Every section starts closed, so
// the page opens as five short lines; which ones a player has opened is remembered on
// their device only; it is a convenience, never needed, so
// every read and write of it is guarded.
import { useCallback, useEffect, useState } from 'react'
import { GroupContext } from './ui'

const STORE = 'bs.playerpage.open'

function readOpen() {
  try {
    const v = JSON.parse(window.localStorage.getItem(STORE) || '{}')
    return v && typeof v === 'object' ? v : {}
  } catch { return {} }
}

// { isOpen(id), toggle(id), setAll(ids, open) } over the remembered choices. A section
// nobody has opened is closed.
export function useOpenSections() {
  const [open, setOpen] = useState(readOpen)
  useEffect(() => {
    try { window.localStorage.setItem(STORE, JSON.stringify(open)) } catch { /* private window: it just will not be remembered */ }
  }, [open])
  const isOpen = useCallback((id) => open[id] === true, [open])
  const toggle = useCallback((id) => setOpen((c) => ({ ...c, [id]: c[id] !== true })), [])
  const setAll = useCallback((ids, value) => setOpen((c) => ({ ...c, ...Object.fromEntries(ids.map((i) => [i, value])) })), [])
  return { isOpen, toggle, setAll }
}

export default function Group({ id, title, summary, tone, open, onToggle, hideTitle = false, children }) {
  const panel = `group-${id}`
  return (
    <section data-group={id} data-open={open ? 'yes' : 'no'} className="rounded-2xl border pb-hairline mb-3 min-w-0 break-inside-avoid">
      <button type="button" onClick={() => onToggle(id)} aria-expanded={open} aria-controls={panel} data-group-toggle={id}
        className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className="font-display font-bold text-[16px] shrink-0">{title}</span>
        {summary ? (
          <span className="ml-auto min-w-0 truncate text-[12.5px]" data-group-summary style={{ color: tone || 'var(--pb-faint)' }}>{summary}</span>
        ) : <span className="ml-auto" />}
        <span aria-hidden="true" className="shrink-0 text-pb-faint transition-transform" style={{ transform: open ? 'rotate(180deg)' : 'none' }}>⌄</span>
      </button>
      {/* Hidden, not unmounted: an unsaved choice or an opened list survives a close. */}
      <div id={panel} hidden={!open} className="px-4 pb-4">
        <GroupContext.Provider value={{ hideTitle }}>{children}</GroupContext.Provider>
      </div>
    </section>
  )
}
