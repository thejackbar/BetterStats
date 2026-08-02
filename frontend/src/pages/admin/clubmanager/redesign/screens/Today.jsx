import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle } from '../ui'

// Today — "what needs me right now", aggregated from the screens that are on
// real data (diary, committee, events, qualifications). Roster and facilities
// rows will join once those backends land. Rows are blocking-first and omitted
// when their count is zero.

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()]
}

export default function Today({ patch, narrow }) {
  const [d, setD] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      api.diaryBoard().catch(() => []),
      api.diaryListDefinitions().catch(() => []),
      api.qualExpiringReport(60).catch(() => []),
      api.committeeListTasks().catch(() => []),
      api.committeePositionsCurrent().catch(() => ({ positions: [] })),
      api.committeeListMeetings().catch(() => []),
      api.committeeListEvents().catch(() => []),
    ]).then(([board, defs, exp, tasks, pos, meetings, events]) => {
      if (!alive) return
      const b = Array.isArray(board) ? board : (board?.board || [])
      const defsArr = Array.isArray(defs) ? defs : (defs?.definitions || [])
      const depsById = {}; defsArr.forEach(x => { depsById[x.id] = x.depends_on || [] })
      const doneOf = {}; b.forEach(r => { doneOf[r.id] = (r.occurrence?.status || '').toLowerCase().match(/done|complet/) != null })
      const now = Date.now()
      const isRecurring = (f) => !['once', 'annual', 'yearly'].includes((f || '').toLowerCase())
      const overdue = [], blocked = []
      b.forEach(r => {
        if (doneOf[r.id] || isRecurring(r.frequency)) return
        const deps = (depsById[r.id] || []).filter(id => b.some(x => x.id === id))
        if (deps.some(id => !doneOf[id])) { blocked.push(r); return }
        if (r.occurrence?.due_date && Date.parse(r.occurrence.due_date) < now) overdue.push(r)
      })
      const expRows = Array.isArray(exp) ? exp : (exp?.expiring || exp?.items || [])
      const taskArr = Array.isArray(tasks) ? tasks : (tasks?.tasks || [])
      const overdueActions = taskArr.filter(t => {
        const s = (t.status || '').toLowerCase()
        return !s.match(/done|complet/) && t.due_date && Date.parse(t.due_date) < now
      })
      const positions = pos?.positions || []
      const vacancies = positions.filter(p => !p.current_term)
      const meets = Array.isArray(meetings) ? meetings : (meetings?.meetings || [])
      const upcoming = meets.filter(m => m.scheduled_at && Date.parse(m.scheduled_at) >= now - 86400000).sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at))
      const nextMeeting = upcoming[0] || null
      const evs = Array.isArray(events) ? events : (events?.events || [])
      const liveEvents = evs.filter(e => e.registration_open !== false)
      setD({ overdue, blocked, expRows, overdueActions, positions, vacancies, nextMeeting, liveEvents })
    })
    return () => { alive = false }
  }, [])

  const go = (p) => () => patch({ ...p, navOpen: false })
  const toneMap = { block: C.block, warn: C.warn }

  const Header = () => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Today</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>What needs you across the club</Caption>
      </div>
    </ScreenHeader>
  )

  if (!d) return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}><Header /><div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading your club…</div></div>

  const attention = [
    d.overdue.length && { count: d.overdue.length, unit: d.overdue.length === 1 ? 'diary task overdue' : 'diary tasks overdue', detail: d.overdue.map(t => t.title).join(' · '), tone: 'block', cta: 'Open the Club Diary', go: go({ screen: 'diary', diaryTab: 'plan', issuesOnly: true }) },
    d.blocked.length && { count: d.blocked.length, unit: d.blocked.length === 1 ? 'task blocked by another' : 'tasks blocked by another', detail: d.blocked.map(t => t.title).join(' · ') + ' — waiting on work that has not finished.', tone: 'block', cta: 'See the critical path', go: go({ screen: 'diary', diaryTab: 'plan', issuesOnly: true }) },
    d.expRows.length && { count: d.expRows.length, unit: d.expRows.length === 1 ? 'qualification to renew' : 'qualifications to renew', detail: 'Expiring or expired — rostering is blocked where a qualification gates the area.', tone: 'warn', cta: 'Review in the Directory', go: go({ screen: 'directory', dirExpiring: true, dirSeg: 'All', dirQuery: '', dirRole: null }) },
    d.overdueActions.length && { count: d.overdueActions.length, unit: d.overdueActions.length === 1 ? 'committee action overdue' : 'committee actions overdue', detail: d.overdueActions.map(a => a.title).join(' · '), tone: 'warn', cta: 'Open motions & actions', go: go({ screen: 'committee', cteTab: 'motions' }) },
    d.vacancies.length && { count: d.vacancies.length, unit: d.vacancies.length === 1 ? 'committee position vacant' : 'committee positions vacant', detail: d.vacancies.map(v => v.name).join(', '), tone: 'warn', cta: 'Open positions', go: go({ screen: 'committee', cteTab: 'positions' }) },
  ].filter(Boolean)

  const cards = [
    { value: String(d.overdue.length), label: 'DIARY OVERDUE', detail: d.overdue.length ? 'Dated tasks past due' : 'Season plan on track', go: go({ screen: 'diary', diaryTab: 'plan', issuesOnly: true }) },
    { value: String(d.overdueActions.length), label: 'OPEN ACTIONS', detail: 'Committee actions still to close', go: go({ screen: 'committee', cteTab: 'motions' }) },
    { value: d.nextMeeting ? fmtDate(d.nextMeeting.scheduled_at) : '—', label: 'NEXT MEETING', detail: d.nextMeeting ? d.nextMeeting.title : 'Nothing scheduled', go: go({ screen: 'committee', cteTab: 'meetings', cteMeeting: d.nextMeeting?.id }) },
    { value: String(d.liveEvents.length), label: 'EVENTS LIVE', detail: d.liveEvents.map(e => e.title).join(' · ') || 'No live events', go: go({ screen: 'events', event: d.liveEvents[0]?.id }) },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />
      <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        <div style={{ maxWidth: '74rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 26 }}>
            {cards.map((c, i) => (
              <div key={i} onClick={c.go} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 10, padding: '14px 16px', cursor: 'pointer' }}>
                <div style={{ fontWeight: 700, fontSize: 21, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{c.value}</div>
                <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 4 }}>{c.label}</div>
                <div style={{ fontSize: 12, color: C.dim, marginTop: 7, lineHeight: 1.45 }}>{c.detail}</div>
              </div>
            ))}
          </div>

          {attention.length > 0 ? (
            <>
              <Caption style={{ marginBottom: 10 }}>{attention.length} thing{attention.length === 1 ? '' : 's'} need you</Caption>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {attention.map((a, i) => (
                  <div key={i} onClick={a.go} style={{ display: 'flex', alignItems: 'flex-start', gap: 14, background: C.surface, border: `1px solid ${toneMap[a.tone]}40`, borderRadius: 10, padding: '14px 16px', cursor: 'pointer' }}>
                    <span style={{ fontWeight: 700, fontSize: 26, lineHeight: 1, fontVariantNumeric: 'tabular-nums', color: toneMap[a.tone], flexShrink: 0, width: 40 }}>{a.count}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 14.5, fontWeight: 600, color: C.text }}>{a.unit}</div>
                      <div style={{ fontSize: 12.5, color: C.dim, marginTop: 4, lineHeight: 1.5 }}>{a.detail}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.1em', color: toneMap[a.tone], marginTop: 7 }}>{a.cta} →</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 13.5, color: C.dim, padding: '8px 2px' }}>Nothing needs you right now. New issues across the diary, committee and events land here.</div>
          )}

          <div style={{ marginTop: 22, fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', color: C.faintest }}>Roster coverage and facility bookings join this view once those screens are on live data.</div>
        </div>
      </div>
    </div>
  )
}
