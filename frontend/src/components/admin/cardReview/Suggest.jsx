import { useEffect, useId, useRef, useState } from 'react'
import { suggest } from '../../../lib/fuzzyMatch'
import { INPUT_CLS } from '../ui'

// A text box that offers the club's own names as it is typed: players, oppositions, grades. The
// person can still type anything; a pick only fills the box. Matching is forgiving ("richie" offers
// "Ritchie, Peter"), and when nothing matches exactly the list is headed "Closest matches" so it is
// clear these are guesses. Keyboard: Down and Up move, Enter picks, Escape closes.
//
// Not wrapped in a <label>: a list of buttons inside a label forwards every click to the input and
// cancels the pick. The caption is a separate <label htmlFor>.
export default function Suggest({ label, value, onChange, items = [], placeholder, minChars = 1, testId, showAll = false }) {
  const id = useId()
  const box = useRef(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const found = showAll && !value.trim()
    ? { shown: items.slice(0, 8), total: items.length, closest: false }
    : suggest(items, value, { minChars })
  const list = found.shown.filter(x => x !== value)
  const visible = open && list.length > 0

  useEffect(() => { setActive(-1) }, [value])
  useEffect(() => {
    const away = e => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const pick = v => { onChange(v); setOpen(false); setActive(-1) }
  const onKey = e => {
    if (e.key === 'Escape') { setOpen(false); return }
    if (!visible) { if (e.key === 'ArrowDown' && list.length) setOpen(true); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => (a + 1) % list.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => (a <= 0 ? list.length - 1 : a - 1)) }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(list[active]) }
    else if (e.key === 'Tab') setOpen(false)
  }

  return (
    <div ref={box} className="relative min-w-0">
      <label htmlFor={id} className="block text-[11.5px] text-pb-dim">{label}</label>
      <input
        id={id} type="text" autoComplete="off" spellCheck={false}
        className={`${INPUT_CLS} mt-1`} value={value} placeholder={placeholder} data-testid={testId}
        role="combobox" aria-expanded={visible} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)} onKeyDown={onKey}
      />
      {visible && (
        <ul id={`${id}-list`} role="listbox" data-testid={testId ? `${testId}-list` : undefined}
          className="absolute left-0 right-0 z-30 mt-1 max-h-[280px] overflow-y-auto rounded-lg border border-pb-hairline2 bg-pb-surface py-1 shadow-xl">
          {found.closest && <li role="presentation" className="px-3 pb-1 pt-1.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-pb-faint">Closest matches</li>}
          {list.map((x, i) => (
            <li key={x} id={`${id}-${i}`} role="option" aria-selected={i === active} data-testid="suggestion"
              onMouseDown={e => { e.preventDefault(); pick(x) }} onMouseEnter={() => setActive(i)}
              className={`cursor-pointer truncate px-3 py-1.5 text-[13px] ${i === active ? 'bg-pb-surface2 text-pb-text' : 'text-pb-dim'}`}>
              {x}
            </li>
          ))}
          {found.total > list.length && <li role="presentation" className="px-3 pt-1 text-[11px] text-pb-faint">{found.total - list.length} more. Keep typing to narrow it.</li>}
        </ul>
      )}
    </div>
  )
}
