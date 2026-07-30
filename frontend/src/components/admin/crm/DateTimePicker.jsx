import { useState, useRef, useEffect } from 'react'
import { TextInput } from './ui'

// A date & time field that keeps native manual entry (type straight into the
// field) AND offers a themed calendar popover for point-and-click picking —
// the browser's own datetime-local picker is inconsistent across browsers and
// its icon is easy to miss, so we hide that icon and provide our own.
//
// `value`/`onChange` speak the datetime-local string format 'YYYY-MM-DDTHH:mm'
// (local time), the same shape EventForm already stores in `starts_at`.

const pad = (n) => String(n).padStart(2, '0')
const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const parseLocal = (v) => {
  if (!v) return null
  const d = new Date(v)
  return isNaN(d) ? null : d
}
const toLocalString = (d) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }
const addMonths = (d, n) => { const x = new Date(d); x.setDate(1); x.setMonth(x.getMonth() + n); return x }
// Monday-based grid start for the month containing `d`.
const monthGridStart = (d) => {
  const first = new Date(d.getFullYear(), d.getMonth(), 1)
  const dow = (first.getDay() + 6) % 7
  return new Date(first.getFullYear(), first.getMonth(), 1 - dow)
}
const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

export default function DateTimePicker({ value, onChange, required }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const selected = parseLocal(value)
  const [viewMonth, setViewMonth] = useState(() => selected || new Date())

  // Re-centre the calendar on the current value each time it's opened.
  useEffect(() => { if (open) setViewMonth(selected || new Date()) }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  const timeStr = selected ? `${pad(selected.getHours())}:${pad(selected.getMinutes())}` : '09:00'

  const pickDay = (day) => {
    const [h, m] = timeStr.split(':').map(Number)
    onChange(toLocalString(new Date(day.getFullYear(), day.getMonth(), day.getDate(), h || 0, m || 0)))
  }
  const setTime = (t) => {
    if (!t) return
    const [h, m] = t.split(':').map(Number)
    const base = selected || new Date()
    onChange(toLocalString(new Date(base.getFullYear(), base.getMonth(), base.getDate(), h || 0, m || 0)))
  }
  const pickToday = () => {
    const [h, m] = timeStr.split(':').map(Number)
    const now = new Date()
    onChange(toLocalString(new Date(now.getFullYear(), now.getMonth(), now.getDate(), h || 0, m || 0)))
    setViewMonth(new Date())
  }

  const gridStart = monthGridStart(viewMonth)
  const cells = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(gridStart); d.setDate(gridStart.getDate() + i); return d
  })
  const today = startOfDay(new Date())

  return (
    <div className="relative" ref={wrapRef}>
      {/* Manual entry stays fully functional; the native picker icon is hidden
          (via the arbitrary variant) in favour of our own calendar button. */}
      <TextInput type="datetime-local" value={value || ''} required={required}
        onChange={(e) => onChange(e.target.value)}
        className="pr-9 [&::-webkit-calendar-picker-indicator]:opacity-0 [&::-webkit-calendar-picker-indicator]:hidden" />
      <button type="button" onClick={() => setOpen(o => !o)} aria-label="Open calendar"
        className="absolute right-2 top-1/2 -translate-y-1/2 text-pb-faint hover:text-pb-accent p-0.5">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <path d="M16 2v4M8 2v4M3 10h18" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-30 mt-1 left-0 pb-card bg-pb-surface p-2.5 w-[260px] shadow-xl">
          <div className="flex items-center justify-between mb-1.5">
            <button type="button" onClick={() => setViewMonth(m => addMonths(m, -1))}
              className="px-2 py-0.5 rounded text-pb-faint hover:text-pb-accent hover:bg-pb-surface2 text-[15px] leading-none">‹</button>
            <span className="font-display font-bold text-[12.5px]">{MONTHS[viewMonth.getMonth()]} {viewMonth.getFullYear()}</span>
            <button type="button" onClick={() => setViewMonth(m => addMonths(m, 1))}
              className="px-2 py-0.5 rounded text-pb-faint hover:text-pb-accent hover:bg-pb-surface2 text-[15px] leading-none">›</button>
          </div>
          <div className="grid grid-cols-7 gap-0.5 mb-0.5">
            {WEEKDAYS.map(d => <div key={d} className="text-center text-[9.5px] font-mono uppercase text-pb-faintest py-0.5">{d}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-0.5">
            {cells.map((d, i) => {
              const inMonth = d.getMonth() === viewMonth.getMonth()
              const isSel = sameDay(d, selected)
              const isToday = sameDay(d, today)
              return (
                <button type="button" key={i} onClick={() => pickDay(d)}
                  className={`h-7 rounded text-[11.5px] transition ${
                    isSel ? 'bg-pb-accent text-black font-bold'
                    : `hover:bg-pb-surface2 ${inMonth ? 'text-pb-text' : 'text-pb-faintest'} ${isToday ? 'ring-1 ring-pb-accent/50' : ''}`}`}>
                  {d.getDate()}
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-pb-hairline">
            <input type="time" value={timeStr} onChange={(e) => setTime(e.target.value)}
              className="bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2 py-1 text-[12.5px] outline-none focus:border-pb-accent flex-1" />
            <button type="button" onClick={pickToday}
              className="px-2 py-1 rounded-lg text-[11.5px] border border-pb-hairline2 text-pb-faint hover:text-pb-accent hover:border-pb-accent/50">Today</button>
            <button type="button" onClick={() => setOpen(false)}
              className="px-2 py-1 rounded-lg text-[11.5px] bg-pb-accent text-black font-medium hover:brightness-110">Done</button>
          </div>
        </div>
      )}
    </div>
  )
}
