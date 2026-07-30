import { C, MONO, Caption, ScreenHeader, NavToggle } from '../ui'
import {
  diaryModel, DIRECTORY, qualState, POSITIONS, MEETINGS, EVENTS,
  REQUESTS_SEED, BOOKINGS_SEED, LOANS, overlaps,
} from '../model'

// Today — "what needs me right now", derived from every other screen. Rows are
// blocking-first and omitted entirely when their count is zero.
export default function Today({ st, patch, narrow }) {
  const slots = st.slots
  const openShifts = slots.filter(x => !x.assignee).length
  const coverage = slots.length ? Math.round(((slots.length - openShifts) / slots.length) * 100) : 0

  const { resolved } = diaryModel()
  const dated = resolved.filter(t => t.state !== 'recurring' && t.state !== 'conditional')
  const overdueTasks = dated.filter(t => t.status === 'overdue')
  const blockedTasks = dated.filter(t => t.status === 'blocked')

  const requests = st.requests || REQUESTS_SEED
  const bookings = st.bookings || BOOKINGS_SEED
  const clashing = requests.filter(r => bookings.some(b => overlaps(r, b))).length

  const returned = st.returned || {}
  const overdueLoans = LOANS.filter(l => !returned[l.id] && l.overdue)

  const flaggedQuals = []
  DIRECTORY.forEach(p => p.quals.forEach(q => {
    const s = qualState(q.expiry)
    if (s.key !== 'current') flaggedQuals.push({ who: p.name, name: q.name, key: s.key, id: p.id })
  }))
  const expiredQuals = flaggedQuals.filter(q => q.key === 'expired')

  const vacancies = POSITIONS.filter(p => !p.holder)
  const overdueActions = []
  MEETINGS.forEach(m => m.actions.forEach(a => { if (a.state === 'overdue') overdueActions.push({ ...a }) }))

  const meetingToday = MEETINGS.find(m => m.status === 'today')
  const nextMeeting = MEETINGS.find(m => m.status === 'scheduled')
  const eventsOnSale = EVENTS.filter(e => e.status === 'on sale' || e.status === 'open')
  const unstaffedEvents = EVENTS.filter(e => e.needs.indexOf('nobody') > -1)

  const go = (p) => () => patch({ ...p, navOpen: false })

  const attention = [
    overdueTasks.length && {
      count: overdueTasks.length, unit: overdueTasks.length === 1 ? 'diary task overdue' : 'diary tasks overdue',
      detail: overdueTasks.map(t => t.title).join(' · '),
      tone: 'block', cta: 'Open the Club Diary', go: go({ screen: 'diary', diaryTab: 'plan', issuesOnly: true }),
    },
    blockedTasks.length && {
      count: blockedTasks.length, unit: blockedTasks.length === 1 ? 'task blocked by another' : 'tasks blocked by another',
      detail: blockedTasks.map(t => t.title).join(' · ') + ' — waiting on work that has not finished.',
      tone: 'block', cta: 'See the critical path', go: go({ screen: 'diary', diaryTab: 'plan', issuesOnly: true }),
    },
    expiredQuals.length && {
      count: expiredQuals.length, unit: expiredQuals.length === 1 ? 'qualification expired' : 'qualifications expired',
      detail: expiredQuals.map(q => q.who + ' — ' + q.name).join(' · ') + '. Rostering is blocked where it gates the area.',
      tone: 'block', cta: 'Review in the Directory', go: go({ screen: 'directory', dirExpiring: true, dirSeg: 'All', dirQuery: '', dirRole: null }),
    },
    clashing && {
      count: clashing, unit: clashing === 1 ? 'booking request clashes' : 'booking requests clash',
      detail: 'Double-bookings caught before approval — move, shorten or decline.',
      tone: 'block', cta: 'Open the requests queue', go: go({ screen: 'facilities', facTab: 'requests' }),
    },
    openShifts && {
      count: openShifts, unit: openShifts === 1 ? 'shift unfilled this week' : 'shifts unfilled this week',
      detail: 'Coverage is at ' + coverage + '%. Auto-fill proposes qualified, available volunteers.',
      tone: 'warn', cta: 'Open the roster', go: go({ screen: 'roster' }),
    },
    overdueActions.length && {
      count: overdueActions.length, unit: overdueActions.length === 1 ? 'committee action overdue' : 'committee actions overdue',
      detail: overdueActions.map(a => a.who + ' — ' + a.what).join(' · '),
      tone: 'warn', cta: 'Open motions & actions', go: go({ screen: 'committee', cteTab: 'motions' }),
    },
    overdueLoans.length && {
      count: overdueLoans.length, unit: overdueLoans.length === 1 ? 'item overdue back' : 'items overdue back',
      detail: overdueLoans.map(l => l.item + ' — ' + l.to).join(' · '),
      tone: 'warn', cta: 'Open assets & loans', go: go({ screen: 'facilities', facTab: 'assets' }),
    },
    vacancies.length && {
      count: vacancies.length, unit: vacancies.length === 1 ? 'committee position vacant' : 'committee positions vacant',
      detail: vacancies.map(v => v.title).join(' and ') + ' — diary tasks for these roles have nobody to substitute in.',
      tone: 'warn', cta: 'Open positions', go: go({ screen: 'committee', cteTab: 'positions' }),
    },
    unstaffedEvents.length && {
      count: unstaffedEvents.length, unit: unstaffedEvents.length === 1 ? 'event with no volunteers' : 'events with no volunteers',
      detail: unstaffedEvents.map(e => e.title).join(' · '),
      tone: 'warn', cta: 'Open events', go: go({ screen: 'events', event: unstaffedEvents[0].id }),
    },
  ].filter(Boolean)

  const toneMap = { block: C.block, warn: C.warn }

  const weekCards = [
    { value: coverage + '%', label: 'ROSTER COVERAGE', detail: (slots.length - openShifts) + ' of ' + slots.length + ' shifts filled across 6 areas', go: go({ screen: 'roster' }) },
    { value: String(bookings.length), label: 'BOOKINGS THIS WEEK', detail: 'Across 5 facilities · ' + requests.length + ' requests waiting on you', go: go({ screen: 'facilities', facTab: 'availability' }) },
    { value: meetingToday ? 'Tonight' : (nextMeeting ? nextMeeting.date : '—'), label: 'NEXT MEETING', detail: meetingToday ? meetingToday.title + ' · ' + meetingToday.agenda.length + ' agenda items' : (nextMeeting ? nextMeeting.title : 'Nothing scheduled'), go: go({ screen: 'committee', cteTab: 'meetings', cteMeeting: meetingToday ? meetingToday.id : (nextMeeting ? nextMeeting.id : 'm5') }) },
    { value: String(eventsOnSale.length), label: 'EVENTS LIVE', detail: eventsOnSale.map(e => e.title).join(' · '), go: go({ screen: 'events', event: eventsOnSale[0] ? eventsOnSale[0].id : 'e3' }) },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Tuesday 3 November</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>Round 4 weekend ahead · committee meeting tonight</Caption>
        </div>
      </ScreenHeader>

      <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        <div style={{ maxWidth: '74rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 26 }}>
            {weekCards.map((c, i) => (
              <div key={i} onClick={c.go} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 10, padding: '14px 16px', cursor: 'pointer' }}>
                <div style={{ fontWeight: 700, fontSize: 21, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{c.value}</div>
                <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 4 }}>{c.label}</div>
                <div style={{ fontSize: 12, color: C.dim, marginTop: 7, lineHeight: 1.45 }}>{c.detail}</div>
              </div>
            ))}
          </div>

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
        </div>
      </div>
    </div>
  )
}
