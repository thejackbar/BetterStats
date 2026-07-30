import { useMemo, useState } from 'react'

// Custom Gantt chart for the Club Diary season plan. No chart library exists in
// the repo, so this is hand-rolled: a scrollable time grid with one bar per
// task, dependency connector lines, a "today" marker, and late / budget flags.
//
// Props:
//   tasks       season-plan occurrences (see diarySeasonPlan). Each carries
//               definition_id, title, category_color, start_date, due_date,
//               estimated_completion_date, budget_estimate, actual_expenditure,
//               is_late, depends_on[], frequency.
//   categories  [{id,name,color}]  (unused directly, colours come off tasks)
//   roles, members, year

const DAY = 86400000
const ACCENT = '#8b7cf6'
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const parseDate = (s) => {
  if (!s) return null
  const [y, m, d] = String(s).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
}
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1)
const startOfWeek = (d) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); const dow = (x.getDay() + 6) % 7; return addDays(x, -dow) }
const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))

const LABEL_W = 200
const ROW_H = 34
const HEADER_H = 36

export default function DiaryGantt({ tasks = [], year }) {
  const [unit, setUnit] = useState('month') // month | week | day

  // Bar extents per task (start/end fallbacks per the spec).
  const rows = useMemo(() => tasks.map(t => {
    const start = t.start_date ? parseDate(t.start_date)
      : (t.due_date ? addDays(parseDate(t.due_date), -7) : null)
    const end = t.due_date ? parseDate(t.due_date)
      : (t.estimated_completion_date ? parseDate(t.estimated_completion_date) : start)
    return { t, start, end: end && start && end < start ? start : end }
  }), [tasks])

  const domain = useMemo(() => {
    const dates = []
    rows.forEach(r => { if (r.start) dates.push(r.start.getTime()); if (r.end) dates.push(r.end.getTime()) })
    let lo, hi
    if (dates.length === 0) {
      const y = year || new Date().getFullYear()
      lo = new Date(y, 0, 1); hi = new Date(y, 11, 31)
    } else {
      lo = startOfMonth(new Date(Math.min(...dates)))
      const maxD = new Date(Math.max(...dates))
      hi = new Date(maxD.getFullYear(), maxD.getMonth() + 1, 0) // last day of that month
    }
    return { lo, hi: new Date(hi.getFullYear(), hi.getMonth(), hi.getDate(), 23, 59, 59) }
  }, [rows, year])

  const { totalW, ticks } = useMemo(() => {
    const lo = domain.lo, hi = domain.hi
    const totalDays = Math.max(1, Math.round((hi - lo) / DAY) + 1)
    const colW = unit === 'month' ? 92 : unit === 'week' ? 46 : 30
    let width
    const list = []
    if (unit === 'month') {
      let cur = startOfMonth(lo)
      while (cur <= hi) { list.push(cur); cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1) }
      width = list.length * colW
    } else if (unit === 'week') {
      let cur = startOfWeek(lo)
      while (cur <= hi) { list.push(cur); cur = addDays(cur, 7) }
      width = list.length * colW
    } else {
      let cur = new Date(lo.getFullYear(), lo.getMonth(), lo.getDate())
      while (cur <= hi) { list.push(cur); cur = addDays(cur, 1) }
      width = list.length * colW
    }
    const span = hi - lo || 1
    const tickList = list.map(d => ({
      d,
      x: ((d - lo) / span) * width,
      label: unit === 'month' ? `${MONTH_NAMES[d.getMonth()]}${d.getMonth() === 0 ? ` ${String(d.getFullYear()).slice(2)}` : ''}`
        : unit === 'week' ? `${d.getDate()}/${d.getMonth() + 1}`
        : String(d.getDate()),
    }))
    return { totalW: Math.max(width, 320), ticks: tickList, colW, totalDays }
  }, [domain, unit])

  const span = domain.hi - domain.lo || 1
  const xFor = (d) => ((d - domain.lo) / span) * totalW
  const todayX = (() => { const now = new Date(); return now >= domain.lo && now <= domain.hi ? xFor(now) : null })()

  // Row index by definition_id for dependency links.
  const rowIndexByDef = useMemo(() => {
    const m = {}
    rows.forEach((r, i) => { if (r.t.definition_id) m[r.t.definition_id] = i })
    return m
  }, [rows])

  const links = useMemo(() => {
    const out = []
    rows.forEach((r, i) => {
      const deps = r.t.depends_on || []
      deps.forEach(depId => {
        const j = rowIndexByDef[depId]
        if (j === undefined || j === i) return
        const from = rows[j], to = r
        if (!from.end || !to.start) return
        out.push({
          x1: xFor(from.end), y1: HEADER_H + j * ROW_H + ROW_H / 2,
          x2: xFor(to.start), y2: HEADER_H + i * ROW_H + ROW_H / 2,
        })
      })
    })
    return out
  }, [rows, rowIndexByDef, totalW, domain]) // eslint-disable-line react-hooks/exhaustive-deps

  const chartH = HEADER_H + rows.length * ROW_H

  if (tasks.length === 0) {
    return (
      <div className="pb-card p-6 text-center text-pb-dim text-sm">
        No tasks to chart. Generate this season under "Season Plan" first, or clear the filters above.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="font-mono text-[10px] tracking-wide2 text-pb-faintest">
          {tasks.length} task{tasks.length === 1 ? '' : 's'} · {domain.lo.toLocaleDateString('en-AU', { month: 'short', year: 'numeric' })} to {domain.hi.toLocaleDateString('en-AU', { month: 'short', year: 'numeric' })}
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest mr-1">ZOOM</span>
          {['month', 'week', 'day'].map(u => (
            <button key={u} onClick={() => setUnit(u)}
              className={`px-2.5 py-1 rounded-full text-[11px] border transition ${unit === u ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
              {u === 'month' ? 'Months' : u === 'week' ? 'Weeks' : 'Days'}
            </button>
          ))}
        </div>
      </div>

      <div className="pb-card overflow-x-auto">
        <div className="relative" style={{ width: LABEL_W + totalW, minHeight: chartH }}>
          {/* Header ticks */}
          <div className="absolute top-0 left-0 z-10 bg-pb-card border-b border-r border-pb-hairline flex items-end px-2 pb-1"
            style={{ width: LABEL_W, height: HEADER_H }}>
            <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">TASK</span>
          </div>
          <div className="absolute top-0" style={{ left: LABEL_W, width: totalW, height: HEADER_H }}>
            {ticks.map((tk, i) => (
              <div key={i} className="absolute top-0 border-l border-pb-hairline text-[9px] font-mono text-pb-faint px-1 pt-1"
                style={{ left: tk.x, height: chartH }}>
                <span className="whitespace-nowrap">{tk.label}</span>
              </div>
            ))}
          </div>

          {/* Today line */}
          {todayX !== null && (
            <div className="absolute z-20 pointer-events-none" style={{ left: LABEL_W + todayX, top: 0, height: chartH, width: 0 }}>
              <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 2, background: '#ef4444', opacity: 0.7 }} />
              <div className="absolute -top-0 -translate-x-1/2 text-[8px] font-mono text-pb-red" style={{ top: HEADER_H - 12 }}>today</div>
            </div>
          )}

          {/* Dependency links overlay */}
          <svg className="absolute pointer-events-none z-20" style={{ left: LABEL_W, top: 0, width: totalW, height: chartH }}>
            {links.map((l, i) => (
              <g key={i}>
                <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke={ACCENT} strokeWidth="1.2" strokeDasharray="3 2" opacity="0.55" />
                <circle cx={l.x2} cy={l.y2} r="2.5" fill={ACCENT} opacity="0.75" />
              </g>
            ))}
          </svg>

          {/* Rows */}
          <div style={{ paddingTop: HEADER_H }}>
            {rows.map((r, i) => {
              const t = r.t
              const color = t.category_color || ACCENT
              const late = t.is_late
              const budget = num(t.budget_estimate), actual = num(t.actual_expenditure)
              const over = budget != null && actual != null && actual > budget
              const under = budget != null && actual != null && actual <= budget
              const hasBar = r.start && r.end
              const x = hasBar ? xFor(r.start) : 0
              const w = hasBar ? Math.max(6, xFor(r.end) - xFor(r.start)) : 0
              return (
                <div key={t.id} className="relative flex items-stretch border-b border-pb-hairline" style={{ height: ROW_H }}>
                  <div className="sticky left-0 z-10 bg-pb-card border-r border-pb-hairline flex items-center gap-1.5 px-2 shrink-0"
                    style={{ width: LABEL_W }}>
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                    <span className="truncate text-[11.5px] text-pb-text" title={t.title}>{t.title}</span>
                  </div>
                  <div className="relative" style={{ width: totalW }}>
                    {hasBar ? (
                      <div className="absolute top-1/2 -translate-y-1/2 rounded flex items-center px-1"
                        title={`${t.title}\n${r.start.toLocaleDateString('en-AU')} → ${r.end.toLocaleDateString('en-AU')}${budget != null ? `\nBudget $${budget}${actual != null ? ` · Spent $${actual}` : ''}` : ''}`}
                        style={{
                          left: x, width: w, height: 18,
                          background: `${color}cc`,
                          border: late ? '1.5px solid #ef4444' : `1px solid ${color}`,
                          boxShadow: late ? '0 0 0 1px rgba(239,68,68,0.3)' : undefined,
                        }}>
                        {(over || under) && (
                          <span className="text-[9px] font-bold ml-auto" style={{ color: over ? '#fca5a5' : '#86efac' }}>$</span>
                        )}
                      </div>
                    ) : (
                      <div className="absolute top-1/2 -translate-y-1/2 left-2 text-[9px] font-mono text-pb-faintest">no dates set</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 mt-3 font-mono text-[9px] tracking-wide2 text-pb-faintest">
        <span className="inline-flex items-center gap-1"><span className="w-3 h-2 rounded-sm" style={{ border: '1.5px solid #ef4444' }} /> LATE</span>
        <span className="inline-flex items-center gap-1"><span style={{ color: '#fca5a5' }}>$</span> OVER BUDGET</span>
        <span className="inline-flex items-center gap-1"><span style={{ color: '#86efac' }}>$</span> UNDER BUDGET</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-4 border-t border-dashed" style={{ borderColor: ACCENT }} /> DEPENDS ON</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-0.5 h-3" style={{ background: '#ef4444' }} /> TODAY</span>
      </div>
    </div>
  )
}
