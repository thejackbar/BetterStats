import { useState, useMemo } from 'react'

// A reusable Month/Week/Day calendar surface for BetterClubManager (Events,
// Bookings, Club Diary). Hand-rolled with native Date — matches the CRM Sales
// Pipeline calendar (no library in the repo). Generic over any item that has a
// start (and optional end) date: a multi-day item (e.g. a facility booked for a
// whole season) is drawn in every day cell it spans.
//
// Props:
//   items        array of items
//   getStart(i)  -> Date | ISO string
//   getEnd(i)    -> Date | ISO string | null (defaults to start)
//   renderChip(i, { compact }) -> JSX for a calendar chip
//   onItemClick(i)
//   onDayAdd(date)   optional — a "+ add on this day" affordance
//   accent       hex colour (default violet)

const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }
const endOfDay = (d) => { const x = new Date(d); x.setHours(23, 59, 59, 999); return x }
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const addMonths = (d, n) => { const x = new Date(d); x.setMonth(x.getMonth() + n); return x }
const startOfWeek = (d) => { const x = startOfDay(d); const dow = (x.getDay() + 6) % 7; return addDays(x, -dow) }
const startOfMonth = (d) => { const x = startOfDay(d); x.setDate(1); return x }
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
const isToday = (d) => sameDay(new Date(d), new Date())
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function calendarWindow(calMode, cursor) {
  if (calMode === 'day') return [startOfDay(cursor), endOfDay(cursor)]
  if (calMode === 'week') { const s = startOfWeek(cursor); return [s, endOfDay(addDays(s, 6))] }
  const s = startOfWeek(startOfMonth(cursor)); return [s, endOfDay(addDays(s, 41))]
}

export default function Calendar({ items = [], getStart, getEnd, renderChip, onItemClick, onDayAdd, accent = '#8b7cf6' }) {
  const [calMode, setCalMode] = useState('month')
  const [cursor, setCursor] = useState(() => new Date())

  const spans = useMemo(() => items.map(it => {
    const s = startOfDay(getStart(it))
    const rawEnd = getEnd ? getEnd(it) : null
    const e = rawEnd ? startOfDay(rawEnd) : s
    return { it, start: s, end: e < s ? s : e }
  }), [items, getStart, getEnd])

  const itemsForDay = (day) => {
    const d0 = startOfDay(day)
    return spans.filter(sp => d0 >= sp.start && d0 <= sp.end).map(sp => sp.it)
  }

  const step = (dir) => setCursor(c => calMode === 'month' ? addMonths(c, dir) : addDays(c, dir * (calMode === 'week' ? 7 : 1)))

  const periodLabel = useMemo(() => {
    if (calMode === 'day') return cursor.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
    if (calMode === 'week') {
      const s = startOfWeek(cursor), e = addDays(s, 6)
      return `${s.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })} – ${e.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}`
    }
    return cursor.toLocaleDateString('en-AU', { month: 'long', year: 'numeric' })
  }, [calMode, cursor])

  const pill = (active) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${
    active ? 'text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`
  const pillStyle = (active) => active ? { background: `${accent}26`, borderColor: `${accent}80`, color: accent } : undefined

  const days = calMode === 'month'
    ? Array.from({ length: 42 }, (_, i) => addDays(startOfWeek(startOfMonth(cursor)), i))
    : calMode === 'day' ? [startOfDay(cursor)]
    : Array.from({ length: 7 }, (_, i) => addDays(startOfWeek(cursor), i))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button onClick={() => step(-1)} className="px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text text-[13px]">‹</button>
          <button onClick={() => setCursor(new Date())} className="px-2.5 py-1 rounded-full text-[11.5px] border border-pb-hairline2 text-pb-faint hover:text-pb-accent">Today</button>
          <button onClick={() => step(1)} className="px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text text-[13px]">›</button>
          <span className="font-display font-bold text-[14px] ml-1">{periodLabel}</span>
        </div>
        <div className="flex items-center gap-2">
          {['month', 'week', 'day'].map(m => (
            <button key={m} onClick={() => setCalMode(m)} className={pill(calMode === m)} style={pillStyle(calMode === m)}>
              {m[0].toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {calMode === 'month' ? (
        <div className="pb-card overflow-hidden">
          <div className="grid grid-cols-7 text-[10.5px] font-mono uppercase tracking-wide text-pb-faint border-b border-pb-hairline">
            {WEEKDAYS.map(d => <div key={d} className="px-2 py-1.5 text-center">{d}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day, i) => {
              const inMonth = day.getMonth() === cursor.getMonth()
              const dayItems = itemsForDay(day)
              const today = isToday(day)
              return (
                <div key={i} className={`h-[82px] overflow-y-auto border-b border-r border-pb-hairline p-1 ${inMonth ? '' : 'bg-pb-surface2/40'}`}>
                  <div className="flex items-center justify-between">
                    <button onClick={() => onDayAdd && onDayAdd(day)} title={onDayAdd ? 'Add on this day' : undefined}
                      className={`text-[11px] w-5 h-5 rounded-full flex items-center justify-center ${
                        today ? 'text-white font-bold' : inMonth ? 'text-pb-text hover:bg-pb-surface2' : 'text-pb-faintest'}`}
                      style={today ? { background: accent } : undefined}>
                      {day.getDate()}
                    </button>
                  </div>
                  <div className="space-y-0.5 mt-0.5">
                    {dayItems.slice(0, 3).map((it, k) => (
                      <div key={k} onClick={() => onItemClick && onItemClick(it)} className="cursor-pointer">{renderChip(it, { compact: true })}</div>
                    ))}
                    {dayItems.length > 3 && <div className="text-[9px] text-pb-faint px-1">+{dayItems.length - 3} more</div>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className={`grid gap-2 ${calMode === 'day' ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-7'}`}>
          {days.map((day, i) => {
            const dayItems = itemsForDay(day)
            const today = isToday(day)
            return (
              <div key={i} className="min-w-0">
                <div className={`text-[11px] font-mono uppercase tracking-wide mb-1 px-1 py-1 rounded flex items-center justify-between ${today ? 'font-bold' : 'text-pb-faint'}`}
                  style={today ? { color: accent, background: `${accent}1a` } : undefined}>
                  <span>{day.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: calMode === 'day' ? 'long' : 'short' })}</span>
                  <div className="flex items-center gap-1">
                    {today && <span>Today</span>}
                    {onDayAdd && <button onClick={() => onDayAdd(day)} title="Add on this day" className="text-pb-faint hover:text-pb-accent">+</button>}
                  </div>
                </div>
                <div className="space-y-1.5">
                  {dayItems.length === 0 && <div className="text-[10.5px] text-pb-faintest px-1 py-2">—</div>}
                  {dayItems.map((it, k) => (
                    <div key={k} onClick={() => onItemClick && onItemClick(it)} className="cursor-pointer">{renderChip(it, { compact: calMode === 'week' })}</div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
