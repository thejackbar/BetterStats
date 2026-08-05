import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout, Toast, Drawer , ManageLink } from '../ui'
import EntityManager from '../parts/EntityManager'

// Club Diary on real data — the board (one current occurrence per active task
// definition) rendered as a day-proportional season timeline. Blocked / overdue
// state and the critical path are derived client-side from the definitions'
// stored dependencies (the backend stores deps but doesn't analyse them).

const MONTH_DEFS = [['JUL', 31], ['AUG', 31], ['SEP', 30], ['OCT', 31], ['NOV', 30], ['DEC', 31], ['JAN', 31], ['FEB', 28], ['MAR', 31], ['APR', 30], ['MAY', 31], ['JUN', 30]]
const CAD_ORDER = ['Annual', 'One-Time', 'Quarterly', 'Monthly', 'Weekly', 'Conditional', 'Other']
const RECURRING = new Set(['Quarterly', 'Monthly', 'Weekly', 'Conditional'])
const SEASON_DAYS = 365

function mapFreq(f) {
  const m = { once: 'One-Time', one_time: 'One-Time', annual: 'Annual', yearly: 'Annual', quarterly: 'Quarterly', monthly: 'Monthly', weekly: 'Weekly', conditional: 'Conditional' }
  return m[(f || '').toLowerCase()] || (f ? f[0].toUpperCase() + f.slice(1) : 'Other')
}
const TONE = {
  done: { fg: '#16c784', label: 'DONE' }, open: { fg: 'var(--pb-accent)', label: 'IN PROGRESS' },
  overdue: { fg: '#ef5b5b', label: 'OVERDUE' }, blocked: { fg: '#ef5b5b', label: 'BLOCKED' },
  upcoming: { fg: '#5b6072', label: 'NOT STARTED' }, recurs: { fg: '#06b6d4', label: 'RECURS' },
}
const money = (n) => '$' + Number(n || 0).toLocaleString('en-AU')
function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.getUTCDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()]
}

export default function ClubDiary({ st, patch, narrow }) {
  const tab = st.diaryTab || 'plan'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  // Which season "Generate" targets. Null until the officer picks one, so the
  // default can follow the data (the first season not yet generated).
  const [pickedYear, setPickedYear] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      api.diaryBoard().catch(() => []),
      api.diaryListDefinitions().catch(() => ([])),
      api.diarySeasonYears().catch(() => ([])),
      api.raRoles().catch(() => ({ roles: [] })),
      api.feeAllMembers().catch(() => ({ members: [] })),
    ]).then(([boardRes, defsRes, yearsRes, rolesRes, membersRes]) => {
      if (!alive) return
      const board = Array.isArray(boardRes) ? boardRes : (boardRes?.board || [])
      const defs = Array.isArray(defsRes) ? defsRes : (defsRes?.definitions || [])
      const depsById = {}
      defs.forEach(d => { depsById[d.id] = d.depends_on || [] })
      const roleName = {}
      ;(rolesRes?.roles || rolesRes || []).forEach(r => { roleName[r.id] = r.title })
      const memberName = {}
      ;(membersRes?.members || membersRes || []).forEach(m => { memberName[m.member_id] = m.full_name })
      const years = (Array.isArray(yearsRes) ? yearsRes : (yearsRes?.years || [])).map(Number).filter(Boolean)
      setData({ board, depsById, roleName, memberName, defs, years })
    }).catch(e => { if (alive) setErr(String(e?.message || e)) })
    return () => { alive = false }
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 7 }
  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Club Diary</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>THE CLUB'S RECURRING OBLIGATIONS, BY SEASON</Caption>
      </div>
      <SegTabs value={tab} onChange={k => patch({ diaryTab: k })} tabs={[{ key: 'plan', label: 'Season plan' }, { key: 'templates', label: 'Template library' }]} />
      <ManageLink to="/admin/clubhouse/diary/manage">Full diary editor</ManageLink>
      {children}
    </ScreenHeader>
  )

  if (!data) return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}><Header /><div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load the club diary.' : 'Loading the club diary…'}</div></div>

  const { board, depsById, roleName, memberName, defs, years } = data
  const nowUTC = Date.now()
  // season window: prefer the club's own season years, else derive from today
  const nowY = new Date().getUTCFullYear(), nowM = new Date().getUTCMonth()
  // The season we are actually IN (rolls in July), kept separate from the
  // newest season that happens to have a generated plan. Conflating the two is
  // what made "Generate" always offer next season even when this one had never
  // been generated.
  const currentSeasonYear = nowM >= 6 ? nowY : nowY - 1
  const seasonYear = years[0] || currentSeasonYear
  // Offer the first season from this one onwards that hasn't been generated
  // yet, so a club with nothing generated is offered THIS season.
  const nextUngenerated = (() => {
    let y = currentSeasonYear
    while (years.includes(y)) y += 1
    return y
  })()
  const seasonLabel = y => `${y}/${String((y + 1) % 100).padStart(2, '0')}`
  const genYear = pickedYear ?? nextUngenerated
  const setGenYear = setPickedYear
  const SEASON_START = Date.UTC(seasonYear, 6, 1)
  const TODAY_DAY = Math.round((nowUTC - SEASON_START) / 86400000)
  const dayOf = (iso) => iso ? Math.round((Date.parse(iso) - SEASON_START) / 86400000) : null

  // resolve each board row into a task with derived status
  const doneOf = {}
  board.forEach(r => { doneOf[r.id] = (r.occurrence?.status || '').toLowerCase().match(/done|complet/) != null })
  const tasks = board.map(r => {
    const occ = r.occurrence || {}
    const cadence = mapFreq(r.frequency)
    const recurs = RECURRING.has(cadence)
    const deps = (depsById[r.id] || []).filter(id => board.some(b => b.id === id))
    const blockers = deps.filter(id => !doneOf[id])
    const rawDone = doneOf[r.id]
    const startDay = dayOf(occ.start_date)
    const dueDay = dayOf(occ.due_date)
    let status = 'upcoming'
    if (rawDone) status = 'done'
    else if (recurs) status = 'recurs'
    else if (blockers.length) status = 'blocked'
    else if (dueDay != null && occ.due_date && Date.parse(occ.due_date) < nowUTC) status = 'overdue'
    else if ((occ.percent_complete || 0) > 0 || (startDay != null && startDay <= TODAY_DAY)) status = 'open'
    return {
      id: r.id, title: r.title, cadence, recurs, deps, blockers, status,
      role: roleName[r.responsibility_role_id] || '',
      person: memberName[occ.assigned_to_member_id || r.default_assignee_member_id] || '',
      startDay, dueDay, start: occ.start_date, due: occ.due_date,
      budget: Number(occ.budget_estimate ?? r.budget_estimate ?? 0),
      spent: Number(occ.actual_expenditure ?? 0),
      pct: occ.percent_complete || 0,
    }
  })
  const byId = {}; tasks.forEach(t => { byId[t.id] = t })
  const dependents = {}; tasks.forEach(t => t.deps.forEach(d => { (dependents[d] = dependents[d] || []).push(t.id) }))

  // critical path — longest dependency chain through remaining (not-done) work
  const memo = {}
  const chain = (id) => {
    if (memo[id]) return memo[id]
    const t = byId[id]; const span = Math.max(1, (t.dueDay ?? 0) - (t.startDay ?? 0))
    let best = { len: span, path: [id] }
    t.deps.filter(d => byId[d] && byId[d].status !== 'done').forEach(d => {
      const c = chain(d); if (c.len + span > best.len) best = { len: c.len + span, path: c.path.concat([id]) }
    })
    return (memo[id] = best)
  }
  let cp = { len: 0, path: [] }
  tasks.filter(t => t.status !== 'done' && !t.recurs && t.startDay != null).forEach(t => { const c = chain(t.id); if (c.len > cp.len) cp = c })
  const cpSet = {}; cp.path.forEach(id => { cpSet[id] = true })

  const dated = tasks.filter(t => !t.recurs && t.startDay != null)
  const overdue = dated.filter(t => t.status === 'overdue')
  const blocked = dated.filter(t => t.status === 'blocked')
  const doneCount = dated.filter(t => t.status === 'done').length
  const budget = tasks.reduce((a, t) => a + t.budget, 0)
  const spent = tasks.reduce((a, t) => a + t.spent, 0)

  const cadFilter = st.cadFilter || 'All'
  const issuesOnly = !!st.issuesOnly
  const collapsed = st.diaryCollapsed || {}
  const visible = tasks.filter(t => {
    if (cadFilter !== 'All' && t.cadence !== cadFilter) return false
    if (issuesOnly && !(t.status === 'overdue' || t.status === 'blocked')) return false
    return true
  })

  // day-proportional month headers + matching gridline stops
  let acc = 0; const stops = []
  const months = MONTH_DEFS.map(([label, days]) => { acc += days; const pct = (acc / SEASON_DAYS) * 100; stops.push(`transparent calc(${pct}% - 1px), ${C.surface2} calc(${pct}% - 1px), ${C.surface2} ${pct}%`); return { label, days } })
  const trackGrid = `linear-gradient(to right, ${stops.join(', ')})`

  const pill = (active, tone = 'accent') => {
    const on = { accent: ['color-mix(in srgb, var(--pb-accent) 45%, transparent)', 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', C.accent], red: ['rgba(239,91,91,0.45)', 'rgba(239,91,91,0.12)', C.block] }[tone]
    return { padding: '5px 10px', borderRadius: 999, fontSize: 12, cursor: 'pointer', border: `1px solid ${active ? on[0] : C.hair2}`, background: active ? on[1] : 'transparent', color: active ? on[2] : C.dim }
  }
  const clamp = (v) => Math.max(0, Math.min(100, v))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <StatReadout value={doneCount + '/' + dated.length} label="DATED TASKS DONE" />
          <StatReadout value={String(overdue.length)} label="OVERDUE" fg={overdue.length ? C.block : C.ok} />
          <StatReadout value={String(blocked.length)} label="BLOCKED" fg={blocked.length ? C.block : C.ok} />
          <StatReadout value={money(spent) + ' / ' + money(budget)} label="SPENT / BUDGETED" />
        </div>
      </Header>

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {tab === 'plan' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${C.hair}`, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
            <div>
              <div style={cap}>CRITICAL PATH — {cp.len} days of chained work</div>
              <div style={{ fontSize: 13, color: C.text, lineHeight: 1.5, background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', borderRadius: 8, padding: '10px 12px' }}>{cp.path.length ? cp.path.map(id => byId[id].title).join('  →  ') : 'No remaining dependency chain.'}</div>
            </div>
            <div>
              <div style={cap}>BLOCKAGES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {overdue.map(t => {
                  const holds = (dependents[t.id] || []).filter(id => byId[id].status !== 'done')
                  return (
                    <div key={t.id} onClick={() => patch({ task: t.id })} style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 11px', borderRadius: 8, background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', cursor: 'pointer' }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.block, marginTop: 5, flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{t.title}</div>
                        <div style={{ fontSize: 11.5, color: C.dim, marginTop: 2, lineHeight: 1.4 }}>{[t.role, t.person].filter(Boolean).join(' → ')}{t.due ? ' · was due ' + fmtDate(t.due) : ''}{holds.length ? ' · holding up ' + holds.map(id => byId[id].title).join(', ') : ''}</div>
                      </div>
                    </div>
                  )
                })}
                {overdue.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing overdue. The season plan is on track.</div>}
              </div>
            </div>
          </div>

          <div style={{ padding: '11px 20px', borderBottom: `1px solid ${C.hair}`, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {['All'].concat(CAD_ORDER.filter(c => tasks.some(t => t.cadence === c))).map(c => <button key={c} onClick={() => patch({ cadFilter: c })} style={pill(cadFilter === c)}>{c}</button>)}
            <button onClick={() => patch({ issuesOnly: !issuesOnly })} style={pill(issuesOnly, 'red')}>Overdue &amp; blocked only</button>
          </div>

          <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
            <div style={{ minWidth: 1000 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '330px 1fr', position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
                <div style={{ padding: '8px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest }}>TASK · {seasonYear}/{String((seasonYear + 1) % 100).padStart(2, '0')}</div>
                <div style={{ display: 'flex' }}>{months.map((m, i) => <div key={i} style={{ flex: `${m.days} 0 0`, padding: '8px 6px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.1em', color: C.faint }}>{m.label}</div>)}</div>
              </div>

              {CAD_ORDER.map(cadence => {
                const items = visible.filter(t => t.cadence === cadence)
                if (!items.length) return null
                const isCol = !!collapsed[cadence]
                return (
                  <div key={cadence}>
                    <div onClick={() => patch({ diaryCollapsed: { ...collapsed, [cadence]: !isCol } })} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 16px', background: C.surface, borderBottom: `1px solid ${C.hair}`, borderTop: `1px solid ${C.hair}`, cursor: 'pointer' }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{isCol ? '▸' : '▾'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim }}>{cadence}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest }}>{items.length} task{items.length === 1 ? '' : 's'}</span>
                    </div>
                    {!isCol && items.map(t => {
                      const tone = TONE[t.status] || TONE.upcoming
                      const onCp = !!cpSet[t.id]
                      const hasBar = t.startDay != null && t.dueDay != null
                      const left = hasBar ? clamp((t.startDay / SEASON_DAYS) * 100) : 0
                      const width = hasBar ? Math.max(1.4, clamp((Math.max(1, t.dueDay - t.startDay) / SEASON_DAYS) * 100)) : 0
                      const overBudget = t.spent > t.budget && t.budget > 0
                      return (
                        <div key={t.id} style={{ display: 'grid', gridTemplateColumns: '330px 1fr', borderBottom: `1px solid ${C.surface2}`, background: st.task === t.id ? 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' : 'transparent' }}>
                          <div onClick={() => patch({ task: t.id })} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 14px', borderRight: `1px solid ${C.hair}`, cursor: 'pointer', minWidth: 0 }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: tone.fg }} />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontSize: 13.5, fontWeight: 600, color: t.status === 'done' ? C.dim : C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: t.status === 'done' ? 'line-through' : undefined, textDecorationColor: t.status === 'done' ? C.faintest : undefined }}>{t.title}</div>
                              <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{[t.role, t.person].filter(Boolean).join(' → ') || 'Unassigned'}{t.recurs ? '' : (t.due ? '  ·  due ' + fmtDate(t.due) : '')}</div>
                            </div>
                            {t.blockers.length > 0 && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4, border: '1px solid rgba(239,91,91,0.4)', color: C.block, flexShrink: 0 }}>⛔ {t.blockers.length}</span>}
                            {onCp && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.1em', padding: '2px 5px', borderRadius: 4, background: 'rgba(239,91,91,0.15)', color: C.block, flexShrink: 0 }}>CP</span>}
                          </div>
                          <div style={{ position: 'relative', height: 42, backgroundImage: trackGrid }}>
                            {TODAY_DAY >= 0 && TODAY_DAY <= SEASON_DAYS && <div style={{ position: 'absolute', top: 0, bottom: 0, left: (TODAY_DAY / SEASON_DAYS) * 100 + '%', width: 1, background: 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }} />}
                            {hasBar && (
                              <div onClick={() => patch({ task: t.id })} style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: left + '%', width: width + '%', height: 20, borderRadius: 5, display: 'flex', alignItems: 'center', padding: '0 6px', overflow: 'hidden', cursor: 'pointer',
                                ...(t.recurs ? { backgroundImage: `repeating-linear-gradient(90deg, ${tone.fg}55 0 6px, transparent 6px 12px)`, border: `1px dashed ${tone.fg}66` } : { background: `color-mix(in srgb, ${tone.fg} 22%, transparent)`, border: `1px solid ${onCp ? tone.fg : `color-mix(in srgb, ${tone.fg} 45%, transparent)`}` }),
                                ...(t.status === 'blocked' ? { backgroundImage: 'repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.28) 4px 8px)' } : {}) }}>
                                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', color: tone.fg, whiteSpace: 'nowrap' }}>{t.budget ? money(t.budget) : tone.label}</span>
                              </div>
                            )}
                            {overBudget && hasBar && <span style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: `calc(${clamp(left + width)}% + 8px)`, fontFamily: MONO, fontSize: 9, color: C.block, whiteSpace: 'nowrap' }}>{money(t.spent - t.budget)} over</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })}
              {tasks.length === 0 && <div style={{ padding: 24, fontSize: 13, color: C.faint }}>No diary tasks yet. Add task definitions in the Template library, then generate a season.</div>}
            </div>
          </div>
        </div>
      )}

      {tab === 'templates' && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 340px', gap: 0, alignItems: 'start', minHeight: 0 }}>
          <div className="pb-scroll" style={{ padding: '18px 20px', overflowY: 'auto' }}>
            <div style={{ ...cap, marginBottom: 4 }}>TEMPLATE LIBRARY</div>
            <EntityManager
              describe="The club's standing obligations — what has to happen every season and who owns it by role. Edit here and every future season you generate inherits it."
              load={() => api.diaryListDefinitions().then(r => r?.definitions || r || [])}
              fields={[
                { key: 'title', label: 'Task', type: 'text', required: true, span: 2 },
                { key: 'frequency', label: 'Cadence', type: 'select', required: true, options: [{ value: 'annual', label: 'Annual' }, { value: 'once', label: 'One-time' }, { value: 'quarterly', label: 'Quarterly' }, { value: 'monthly', label: 'Monthly' }, { value: 'weekly', label: 'Weekly' }, { value: 'conditional', label: 'Conditional' }] },
                { key: 'responsibility_role_id', label: 'Owner role', type: 'select', options: Object.entries(roleName).map(([id, title]) => ({ value: id, label: title })) },
                { key: 'default_month', label: 'Month (1-12)', type: 'number' },
                { key: 'budget_estimate', label: 'Budget ($)', type: 'number' },
                { key: 'description', label: 'Notes', type: 'text', span: 2 },
              ]}
              onCreate={v => api.diaryCreateDefinition(v)} onUpdate={(id, v) => api.diaryUpdateDefinition(id, v)} onDelete={id => api.diaryArchiveDefinition(id)}
              seed={{ label: 'Add Club Diary Starter Pack', fn: () => api.diarySeedStarterDefinitions() }}
              primaryKey="title"
              subtitle={it => [mapFreq(it.frequency), roleName[it.responsibility_role_id], it.budget_estimate ? money(it.budget_estimate) : null].filter(Boolean).join(' · ')}
              addLabel="Add task" emptyText="No task definitions yet." />
          </div>
          <div className="pb-scroll" style={{ borderLeft: `1px solid ${C.hair}`, background: C.surface, padding: '18px 16px', overflowY: 'auto', alignSelf: 'stretch' }}>
            <div style={cap}>GENERATE A SEASON</div>
            <p style={{ fontSize: 12.5, color: C.dim, margin: '0 0 12px', lineHeight: 1.5 }}>Materialises every active definition into dated tasks for the season you pick. Nothing is locked — edit the generated plan freely afterwards.</p>
            <select value={genYear} onChange={e => setGenYear(Number(e.target.value))}
              style={{ width: '100%', marginBottom: 8, padding: '8px 10px', borderRadius: 8, fontSize: 13, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.text }}>
              {[currentSeasonYear - 1, currentSeasonYear, currentSeasonYear + 1, currentSeasonYear + 2].map(y => (
                <option key={y} value={y}>{seasonLabel(y)}{years.includes(y) ? ' · already generated' : ''}</option>
              ))}
            </select>
            <button onClick={() => {
              const target = genYear
              api.diaryGenerateSeason(target)
                .then(() => patch({ toast: { tone: 'ok', title: 'Generated ' + seasonLabel(target) + ' from your templates.', body: defs.length + ' definitions materialised into dated tasks. Open the season plan to review.' } }))
                .catch(() => patch({ toast: { tone: 'block', title: 'Could not generate the season.', body: 'Check the club diary configuration and try again.' } }))
            }} style={{ width: '100%', padding: '9px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#0a0d14', cursor: 'pointer' }}>Generate {seasonLabel(genYear)} plan</button>
            {years.includes(genYear) && (
              <p style={{ fontSize: 11.5, color: C.warn, margin: '8px 0 0', lineHeight: 1.5 }}>
                {seasonLabel(genYear)} already has a plan. Generating again tops it up from your definitions rather than starting over.
              </p>
            )}
          </div>
        </div>
      )}

      {st.task && byId[st.task] && (() => {
        const t = byId[st.task]
        const tone = TONE[t.status] || TONE.upcoming
        const chip = (x) => ({ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${(TONE[x.status] || TONE.upcoming).fg}66`, color: (TONE[x.status] || TONE.upcoming).fg, flexShrink: 0 })
        const dcap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }
        const up = t.deps.map(id => byId[id]).filter(Boolean)
        const down = (dependents[t.id] || []).map(id => byId[id]).filter(Boolean)
        return (
          <Drawer width={440} zIndex={90} onClose={() => patch({ task: null })}>
            <div style={{ padding: 20, borderBottom: `1px solid ${C.hair}` }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 17, lineHeight: 1.3 }}>{t.title}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${tone.fg}66`, color: tone.fg }}>{tone.label}</span>
                    {cpSet[t.id] && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, background: 'rgba(239,91,91,0.15)', color: C.block }}>ON CRITICAL PATH</span>}
                  </div>
                </div>
                <span style={{ cursor: 'pointer', color: C.faint, fontSize: 16 }} onClick={() => patch({ task: null })}>✕</span>
              </div>
            </div>
            <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {[['CADENCE', t.cadence], ['ROLE', t.role || '—'], ['ASSIGNED', t.person || 'Unassigned'], ['WINDOW', t.start ? fmtDate(t.start) + ' → ' + fmtDate(t.due) : '—']].map(([l, v], i) => (
                  <div key={i} style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '9px 11px' }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint }}>{l}</div>
                    <div style={{ fontSize: 13, color: C.text, marginTop: 3, lineHeight: 1.4 }}>{v}</div>
                  </div>
                ))}
              </div>
              <div>
                <div style={dcap}>BUDGET</div>
                <div style={{ fontSize: 13, color: C.text }}>{t.budget ? money(t.spent) + ' of ' + money(t.budget) : 'No budget set'}</div>
                {t.budget > 0 && <div style={{ height: 5, borderRadius: 3, background: C.surface2, overflow: 'hidden', marginTop: 6 }}><div style={{ height: '100%', width: Math.min(100, (t.spent / t.budget) * 100) + '%', background: t.spent > t.budget ? C.block : C.ok }} /></div>}
              </div>
              <div>
                <div style={dcap}>DEPENDS ON</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {up.map(u => <div key={u.id} onClick={() => patch({ task: u.id })} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer' }}><span style={{ fontSize: 12.5, flex: 1, minWidth: 0 }}>{u.title}</span><span style={chip(u)}>{(TONE[u.status] || TONE.upcoming).label}</span></div>)}
                  {up.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing — this one can start any time.</div>}
                </div>
              </div>
              <div>
                <div style={dcap}>HOLDS UP</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {down.map(d => <div key={d.id} onClick={() => patch({ task: d.id })} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer' }}><span style={{ fontSize: 12.5, flex: 1, minWidth: 0 }}>{d.title}</span><span style={chip(d)}>{(TONE[d.status] || TONE.upcoming).label}</span></div>)}
                  {down.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing downstream.</div>}
                </div>
              </div>
            </div>
          </Drawer>
        )
      })()}
    </div>
  )
}
