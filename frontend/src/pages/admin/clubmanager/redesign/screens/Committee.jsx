import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout , ManageLink } from '../ui'
import { MeetingRoomPanel } from '../../../MeetingRoom'
// The Plans, Actions, Documents and Calendar sections are the manage screen's
// own editors, mounted here rather than copied — two versions of "the club's
// documents" is how the two start disagreeing about what the club holds.
//
// Lazily, because they are a large slice of the bundle and most visits to this
// screen only ever look at Meetings. Same call the Comms shell makes about its
// HTML editor.
const PlanTab = lazy(() => import('../../../../../components/admin/clubmanager/governance').then(m => ({ default: m.PlanTab })))
const TasksTab = lazy(() => import('../../../AdminCommittee').then(m => ({ default: m.TasksTab })))
const DocumentsTab = lazy(() => import('../../../AdminCommittee').then(m => ({ default: m.DocumentsTab })))
const CalendarTab = lazy(() => import('../../../AdminCommittee').then(m => ({ default: m.CalendarTab })))

// The buttons across the top, and the ones that appear on the line below when a
// section holds more than one thing. Keys are what `st` stores, so renaming a
// label never moves anyone's view.
const TABS = [
  { key: 'meetings', label: 'Meetings' },
  { key: 'motions', label: 'Motions & Actions' },
  { key: 'plans', label: 'Plans' },
  { key: 'documents', label: 'Documents' },
  { key: 'calendar', label: 'Calendar' },
  { key: 'positions', label: 'Positions' },
]
const MEETING_VIEWS = [{ key: 'meetings', label: 'Meetings' }, { key: 'templates', label: 'Meeting Templates' }]
const MA_VIEWS = [{ key: 'actions', label: 'Actions' }, { key: 'motions', label: 'Motions' }]
const ACTION_VIEWS = [{ key: 'list', label: 'List' }, { key: 'board', label: 'Board' }, { key: 'timeline', label: 'Timeline' }]
const PLAN_VIEWS = [{ key: 'plans', label: 'Plans' }, { key: 'themes', label: 'Themes' }, { key: 'objectives', label: 'Objectives' }]

// Committee — positions, meetings (agenda / attendance / motions) and the
// club's committee tasks (the closest thing to action items), all on real data.
// Member IDs on agenda/motions/tasks resolve to names via the club member list.

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()] + ' ' + d.getFullYear()
}
const isToday = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString()

// Newest meeting first — the list and anything inserted into it after a meeting
// is created have to agree on the order, so both sort through here.
const byNewest = (a, b) => new Date(b.scheduled_at || 0) - new Date(a.scheduled_at || 0)

// `meeting_type` is free text on the server, so this is the vocabulary the club
// actually writes. Same list the manage screen offers — keep the two in step.
const MEETING_TYPES = ['committee', 'agm', 'special_general', 'sub_committee', 'other']
const typeLabel = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

function meetingStatus(m) {
  if (isToday(m.scheduled_at)) return { label: 'TODAY', fg: 'var(--pb-accent)' }
  const s = (m.status || '').toLowerCase()
  if (s.includes('complet') || s.includes('held') || s.includes('approv') || s.includes('minutes')) return { label: (m.status || 'COMPLETED').toUpperCase().replace(/_/g, ' '), fg: '#16c784' }
  if (m.scheduled_at && new Date(m.scheduled_at) > new Date()) return { label: 'SCHEDULED', fg: '#8a90a2' }
  return { label: (m.status || 'DRAFT').toUpperCase().replace(/_/g, ' '), fg: '#8a90a2' }
}
function taskState(t) {
  const s = (t.status || '').toLowerCase()
  if (s.includes('done') || s.includes('complet')) return { label: 'DONE', fg: '#16c784' }
  if (t.due_date && new Date(t.due_date) < new Date()) return { label: 'OVERDUE', fg: '#ef5b5b' }
  return { label: (t.status || 'OPEN').toUpperCase().replace(/_/g, ' '), fg: 'var(--pb-accent)' }
}
const Loading = () => <div style={{ fontSize: 13, color: C.faint }}>Loading…</div>

function motionOutcome(o) {
  const s = (o || '').toLowerCase()
  const lost = s.includes('lost') || s.includes('fail') || s.includes('reject')
  return { label: (o || 'RECORDED').toUpperCase(), fg: lost ? '#ef5b5b' : '#16c784' }
}


// An agenda item, with what it produced folded away underneath it.
//
// Collapsed, the summary answers "did anything come of this?" without a click:
// how many motions and how they went, how many actions and how many are still
// open, and whether anything was minuted against it. Expanded, it shows the
// actual motions, actions and note. Items that produced nothing stay a plain
// row with nothing to open, because a disclosure arrow that reveals "nothing"
// is a small lie.
function AgendaRow({ item, idx, name, motions, actions, open, onToggle }) {
  const carried = motions.filter(m => (m.outcome || '').toLowerCase() === 'carried').length
  const openActions = actions.filter(t => !['done', 'completed', 'cancelled'].includes((t.status || '').toLowerCase())).length
  const note = (item.outcome_notes || '').trim()
  const bits = []
  if (motions.length) bits.push(`${motions.length} motion${motions.length === 1 ? '' : 's'}${carried ? ` · ${carried} carried` : ''}`)
  if (actions.length) bits.push(`${actions.length} action${actions.length === 1 ? '' : 's'}${openActions ? ` · ${openActions} open` : ''}`)
  if (note) bits.push('minuted')
  const has = motions.length > 0 || actions.length > 0 || !!note

  const sub = item.proposed_by_member_id ? name(item.proposed_by_member_id) : item.description

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8 }}>
      <div onClick={has ? onToggle : undefined}
        style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 13px', cursor: has ? 'pointer' : 'default' }}>
        <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0, width: 12 }}>{item.position ?? idx + 1}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13.5, color: C.text }}>{item.title}</div>
          {(sub || bits.length > 0) && (
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>
              {[sub, ...bits].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
        {has && (
          <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, flexShrink: 0 }}>{open ? '▾' : '▸'}</span>
        )}
      </div>

      {has && open && (
        <div style={{ borderTop: `1px solid ${C.hair}`, padding: '10px 13px 12px 36px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {motions.length > 0 && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>MOTIONS</div>
              {motions.map(mo => (
                <div key={mo.id} style={{ fontSize: 12.5, color: C.dim, marginBottom: 4 }}>
                  {mo.description}
                  <span style={{ fontFamily: MONO, fontSize: 9.5, marginLeft: 7, color: outcomeTone(mo.outcome) }}>
                    {(mo.outcome || 'pending').toUpperCase()}
                  </span>
                  {(mo.votes_for != null || mo.votes_against != null) && (
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>
                      {mo.votes_for || 0} for · {mo.votes_against || 0} against{mo.votes_abstain ? ` · ${mo.votes_abstain} abstain` : ''}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {actions.length > 0 && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>ACTIONS</div>
              {actions.map(t => (
                <div key={t.id} style={{ fontSize: 12.5, color: C.dim, marginBottom: 4 }}>
                  {t.title}
                  <span style={{ fontFamily: MONO, fontSize: 9.5, marginLeft: 7, color: outcomeTone(t.status) }}>
                    {(t.status || 'todo').replace('_', ' ').toUpperCase()}
                  </span>
                  {t.due_date && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>due {t.due_date}</span>}
                  {t.assigned_to_member_id && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>{name(t.assigned_to_member_id)}</span>}
                </div>
              ))}
            </div>
          )}
          {note && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>NOTES</div>
              <div style={{ fontSize: 12.5, color: C.dim, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{note}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Carried and done read green, lost and blocked red, everything mid-flight amber.
function outcomeTone(v) {
  const k = (v || '').toLowerCase()
  if (['carried', 'done', 'completed'].includes(k)) return 'var(--pb-positive-ink)'
  if (['lost', 'blocked', 'withdrawn'].includes(k)) return 'var(--pb-red-ink)'
  return C.warn
}


export default function Committee({ st, patch, narrow }) {
  const tab = st.cteTab || 'meetings'
  const meetingsView = st.cteMeetingsView || 'meetings'
  const maView = st.cteMaView || 'actions'
  const actionsView = st.cteActionsView || 'list'
  const plansView = st.ctePlansView || 'plans'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)
  // Which agenda items are open. Keyed by item id and kept per meeting view, so
  // opening one item does not collapse the rest.
  const [expanded, setExpanded] = useState({})
  // The new-meeting modal. One modal on two steps: the meeting itself, and the
  // agenda template it can be built from — because "I need a template first" is
  // discovered halfway through creating the meeting, not before it.
  //   null | { step: 'meeting' | 'template', form, tpl, busy, error }
  const [mk, setMk] = useState(null)
  // Templates are only fetched when the modal is first opened — null means not
  // asked for yet, so glancing at the committee costs nothing extra.
  const [templates, setTemplates] = useState(null)
  // The template open in the detail pane: { id | null, name, items, draft, busy }.
  // `id` null means one being written for the first time.
  const [tplEdit, setTplEdit] = useState(null)
  // Anything that failed while writing, said where it happened rather than as a
  // toast this screen has no room for.
  const [msg, setMsg] = useState(null)

  // Reorder a position before another and persist the new sequence.
  const movePosition = (fromId, toId) => {
    setDragId(null); setOverId(null)
    if (!fromId || fromId === toId) return
    setData(d => {
      const arr = [...d.positions]
      const fi = arr.findIndex(p => p.id === fromId)
      const ti = arr.findIndex(p => p.id === toId)
      if (fi < 0 || ti < 0) return d
      const [moved] = arr.splice(fi, 1)
      arr.splice(ti, 0, moved)
      api.committeeReorderPositions(arr.map(p => p.id)).catch(() => {})
      return { ...d, positions: arr }
    })
  }

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [posRes, meetList, tasksRes, membersRes] = await Promise.all([
          api.committeePositionsCurrent().catch(() => ({ positions: [] })),
          api.committeeListMeetings().catch(() => []),
          api.committeeListTasks().catch(() => []),
          api.feeAllMembers().catch(() => ({ members: [] })),
        ])
        const meetingsLite = Array.isArray(meetList) ? meetList : (meetList?.meetings || [])
        // pull full detail (agenda/attendance/motions) for each meeting — few per season
        const meetings = await Promise.all(meetingsLite.map(m => api.committeeGetMeeting(m.id).catch(() => ({ ...m, agenda_items: [], motions: [], attendance: [] }))))
        if (!alive) return
        const nameById = {}
        ;(membersRes?.members || membersRes || []).forEach(m => { nameById[m.member_id] = m.full_name })
        setData({
          positions: posRes?.positions || [],
          meetings: meetings.sort(byNewest),
          tasks: Array.isArray(tasksRes) ? tasksRes : (tasksRes?.tasks || []),
          members: membersRes?.members || membersRes || [],
          nameById,
        })
      } catch (e) { if (alive) setErr(String(e?.message || e)) }
    })()
    return () => { alive = false }
  }, [])

  // Coming out of the meeting room, pull that one meeting's record again so the
  // summary beside the list shows what was just minuted. One fetch, on the way
  // out — the room reloads itself after every edit while it is open.
  const refreshMeeting = useCallback(async (id) => {
    try {
      const fresh = await api.committeeGetMeeting(id)
      setData(d => (d ? { ...d, meetings: d.meetings.map(m => (m.id === id ? { ...m, ...fresh } : m)) } : d))
    } catch { /* the room reports its own failures */ }
  }, [])

  // While the room is open it hands back the meeting record on every load, so
  // the card's status pill follows a change made in the room straight away.
  const onRoomMeta = useCallback((meta) => {
    const m = meta?.meeting
    if (!m) return
    setData(d => (d ? {
      ...d,
      meetings: d.meetings.map(x => (x.id === m.id
        ? { ...x, title: m.title, status: m.status, scheduled_at: m.scheduled_at, location: m.location }
        : x)),
    } : d))
  }, [])

  const loadTemplates = useCallback(async () => {
    try {
      const res = await api.committeeListAgendaTemplates()
      setTemplates(res?.templates || [])
    } catch { setTemplates([]) }
  }, [])

  // Meeting Templates are fetched on entering their own view too, not only when
  // the new-meeting dialog is opened.
  useEffect(() => {
    if (tab === 'meetings' && meetingsView === 'templates' && templates === null) loadTemplates()
  }, [tab, meetingsView, templates, loadTemplates])

  // Deleting a meeting takes its agenda, motions, attendance and minutes with
  // it, so it asks first. A template the meeting was BUILT from is untouched —
  // the items were copied onto the meeting when it was created.
  async function deleteMeeting(m) {
    if (!window.confirm(`Delete “${m.title}”?\n\nIts agenda, motions, attendance and minutes go with it. This cannot be undone.`)) return
    setMsg(null)
    try {
      await api.committeeDeleteMeeting(m.id)
      setData(d => (d ? { ...d, meetings: d.meetings.filter(x => x.id !== m.id) } : d))
      if (st.cteMeeting === m.id) patch({ cteMeeting: null, cteRoom: null })
    } catch (e) { setMsg(`Could not delete that meeting — ${String(e?.message || e)}`) }
  }

  const openNewTemplate = () => {
    patch({ cteTab: 'meetings', cteMeetingsView: 'templates', cteTemplate: null })
    if (templates === null) loadTemplates()
    setTplEdit({ id: null, name: '', items: [], draft: '', busy: false })
  }
  const openTemplate = (t) => {
    patch({ cteTemplate: t.id })
    setTplEdit({ id: t.id, name: t.name || '', items: [...(t.items || [])], draft: '', busy: false })
  }
  const setTpl = (k, v) => setTplEdit(t => ({ ...t, [k]: v }))
  const addTplRow = () => setTplEdit(t => (t.draft.trim()
    ? { ...t, items: [...t.items, { title: t.draft.trim() }], draft: '' }
    : t))

  async function saveTemplateEdit() {
    const items = tplEdit.draft.trim() ? [...tplEdit.items, { title: tplEdit.draft.trim() }] : tplEdit.items
    if (!tplEdit.name.trim() || items.length === 0) return
    setTplEdit(t => ({ ...t, busy: true })); setMsg(null)
    try {
      const saved = tplEdit.id
        ? await api.committeeUpdateAgendaTemplate(tplEdit.id, { name: tplEdit.name.trim(), items })
        : await api.committeeCreateAgendaTemplate({ name: tplEdit.name.trim(), items })
      setTemplates(ts => {
        const rest = (ts || []).filter(x => x.id !== saved.id)
        return [...rest, saved].sort((a, b) => (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase()))
      })
      patch({ cteTemplate: saved.id })
      setTplEdit({ id: saved.id, name: saved.name || '', items: [...(saved.items || [])], draft: '', busy: false })
    } catch (e) {
      setTplEdit(t => ({ ...t, busy: false }))
      setMsg(String(e?.message || e))
    }
  }

  // A template can be deleted whatever has been built from it. Creating a
  // meeting COPIES the template's items onto that meeting's own agenda, and the
  // meeting's back-reference is ON DELETE SET NULL — so every past meeting keeps
  // its agenda word for word, it just stops naming the template it came from.
  async function deleteTemplate(t) {
    if (!window.confirm(`Delete the “${t.name}” template?\n\nMeetings already built from it keep their agendas — they simply stop naming it.`)) return
    setMsg(null)
    try {
      await api.committeeDeleteAgendaTemplate(t.id)
      setTemplates(ts => (ts || []).filter(x => x.id !== t.id))
      if (tplEdit?.id === t.id) setTplEdit(null)
      if (st.cteTemplate === t.id) patch({ cteTemplate: null })
    } catch (e) { setMsg(`Could not delete that template — ${String(e?.message || e)}`) }
  }

  const openNew = () => {
    setMk({
      step: 'meeting', busy: false, error: null,
      form: { title: '', meeting_type: 'committee', scheduled_at: '', location: '', agenda_template_id: '' },
      tpl: { name: '', items: [], draft: '' },
    })
    if (templates === null) loadTemplates()
  }
  const setField = (k, v) => setMk(m => ({ ...m, form: { ...m.form, [k]: v } }))
  const setTplField = (k, v) => setMk(m => ({ ...m, tpl: { ...m.tpl, [k]: v } }))
  const addTplItem = () => setMk(m => (m.tpl.draft.trim()
    ? { ...m, tpl: { ...m.tpl, items: [...m.tpl.items, { title: m.tpl.draft.trim() }], draft: '' } }
    : m))

  async function createMeeting() {
    const f = mk.form
    if (!f.title.trim() || !f.scheduled_at) return
    setMk(m => ({ ...m, busy: true, error: null }))
    try {
      const created = await api.committeeCreateMeeting({
        title: f.title.trim(),
        meeting_type: f.meeting_type,
        scheduled_at: new Date(f.scheduled_at).toISOString(),
        location: f.location.trim() || null,
        agenda_template_id: f.agenda_template_id || null,
      })
      // Read the new meeting back the same way the first load does, so a meeting
      // built from a template shows its agenda straight away instead of reading
      // as empty until the screen is opened again.
      const full = await api.committeeGetMeeting(created.id).catch(() => created)
      const row = { agenda_items: [], motions: [], actions: [], attendance: [], ...full }
      setData(d => (d ? { ...d, meetings: [row, ...d.meetings].sort(byNewest) } : d))
      setMk(null)
      patch({ cteMeeting: created.id, cteRoom: null })
    } catch (e) {
      setMk(m => ({ ...m, busy: false, error: String(e?.message || e) }))
    }
  }

  async function saveTemplate() {
    // A title typed but not yet added counts — losing the last line someone
    // typed because they pressed Save instead of Enter is its own small bug.
    const items = mk.tpl.draft.trim() ? [...mk.tpl.items, { title: mk.tpl.draft.trim() }] : mk.tpl.items
    if (!mk.tpl.name.trim() || items.length === 0) return
    setMk(m => ({ ...m, busy: true, error: null }))
    try {
      const created = await api.committeeCreateAgendaTemplate({ name: mk.tpl.name.trim(), items })
      setTemplates(ts => [...(ts || []), created])
      // Back to the meeting, with the template just written already chosen —
      // which is the only reason to have gone and made one mid-flow.
      setMk(m => ({
        ...m, busy: false, error: null, step: 'meeting',
        tpl: { name: '', items: [], draft: '' },
        form: { ...m.form, agenda_template_id: created.id },
      }))
    } catch (e) {
      setMk(m => ({ ...m, busy: false, error: String(e?.message || e) }))
    }
  }

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const chip = (fg, fs = 8.5) => ({ fontFamily: MONO, fontSize: fs, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg, flexShrink: 0 })
  // The OPEN pill is a button, and its colour is the club's accent rather than
  // a hex — so it can't take `chip`'s `${fg}66` edge (a var() with 66 stuck on
  // the end is not a colour and the border silently vanishes). color-mix is how
  // the rest of this screen tints the accent, and --pb-accent-ink is the accent
  // as text, which stays legible on a light theme.
  const openChip = (active, fs = 8.5) => ({
    ...chip(C.accent, fs),
    color: 'var(--pb-accent-ink)',
    border: `1px solid color-mix(in srgb, var(--pb-accent) ${active ? 55 : 38}%, transparent)`,
    background: active ? 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' : 'transparent',
    cursor: 'pointer',
  })

  // Form furniture, matching the Directory's — these two screens sit beside each
  // other in BetterAdmin and their dialogs should read as the same dialog.
  const inp = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '8px 11px', color: C.text, fontSize: 13, outline: 'none', width: '100%', fontFamily: 'inherit' }
  const lbl = { fontFamily: MONO, fontSize: 9.5, color: C.faint }
  // Amber is the module's brand, not the club's, so the ink on it is the fixed
  // ON_ACCENT constant rather than a token that follows a club's own accent.
  const btnP = { padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#0a0d14', cursor: 'pointer', fontFamily: 'inherit' }
  const btnS = { padding: '8px 13px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', fontFamily: 'inherit' }
  // The small destructive control on a list row. Quiet by default — it sits
  // beside OPEN, and a delete that shouts is a delete that gets pressed.
  const delBtn = { background: 'transparent', border: `1px solid ${C.hair2}`, borderRadius: 4, padding: '2px 5px', lineHeight: 1, fontSize: 11, color: C.faint, cursor: 'pointer', fontFamily: MONO, flexShrink: 0 }

  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Committee</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>Positions, meetings, motions and actions</Caption>
      </div>
      <SegTabs value={tab} onChange={k => patch({ cteTab: k })} tabs={TABS} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto', flexWrap: 'wrap' }}>
        <ManageLink to="/admin/clubhouse/committee/manage">Manage meetings &amp; positions</ManageLink>
        {/* The primary action belongs to whatever is on screen, so the button
            names the record this view actually makes. */}
        {data && tab === 'meetings' && meetingsView === 'meetings' && (
          <button onClick={openNew} style={btnP}>+ New meeting</button>
        )}
        {data && tab === 'meetings' && meetingsView === 'templates' && (
          <button onClick={openNewTemplate} style={btnP}>+ New Meeting Template</button>
        )}
      </div>
      {children}
    </ScreenHeader>
  )

  // The buttons on the line below the top row. Two rows where a section is
  // three deep (Motions & Actions → Actions → List / Board / Timeline), and
  // nothing at all where a section holds one thing.
  const subRows = []
  if (tab === 'meetings') {
    subRows.push({ value: meetingsView, tabs: MEETING_VIEWS, onChange: v => { patch({ cteMeetingsView: v }); setTplEdit(null); setMsg(null) } })
  } else if (tab === 'motions') {
    subRows.push({ value: maView, tabs: MA_VIEWS, onChange: v => patch({ cteMaView: v }) })
    if (maView === 'actions') subRows.push({ value: actionsView, tabs: ACTION_VIEWS, onChange: v => patch({ cteActionsView: v }) })
  } else if (tab === 'plans') {
    subRows.push({ value: plansView, tabs: PLAN_VIEWS, onChange: v => patch({ ctePlansView: v }) })
  }
  const SubBar = () => (subRows.length === 0 ? null : (
    <div style={{ borderBottom: `1px solid ${C.hair}`, background: C.surface, padding: '10px 20px', display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
      {subRows.map((r, i) => <SegTabs key={i} value={r.value} tabs={r.tabs} onChange={r.onChange} />)}
    </div>
  ))

  if (!data) {
    return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}><Header /><div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load committee data.' : 'Loading committee…'}</div></div>
  }

  const { positions, meetings, tasks, members, nameById } = data
  const name = (id) => (id && nameById[id]) || 'Unknown'
  const vacancies = positions.filter(p => !p.current_term)
  const openTasks = tasks.filter(t => taskState(t).label !== 'DONE')
  const allMotions = []
  meetings.forEach(m => (m.motions || []).forEach(mo => allMotions.push({ ...mo, from: (m.meeting_type || 'Meeting') + ' · ' + fmtDate(m.scheduled_at) })))

  const sel = meetings.find(m => m.id === st.cteMeeting) || meetings[0] || null
  // The room is only ever open on the meeting that is selected, so the card the
  // list highlights and the pane beside it can never disagree.
  const room = sel && st.cteRoom === sel.id ? sel.id : null
  const openRoom = (id) => patch({ cteMeeting: id, cteRoom: id })
  const closeRoom = () => { if (room) refreshMeeting(room); patch({ cteRoom: null }) }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <StatReadout value={(positions.length - vacancies.length) + '/' + positions.length} label="POSITIONS FILLED" fg={vacancies.length ? C.warn : C.ok} />
          <StatReadout value={String(openTasks.length)} label="OPEN ACTIONS" fg={openTasks.some(t => taskState(t).label === 'OVERDUE') ? C.block : C.text} />
          <StatReadout value={String(allMotions.length)} label="MOTIONS THIS SEASON" />
        </div>
      </Header>
      <SubBar />

      {msg && (
        <div style={{ padding: '10px 20px', fontSize: 12.5, color: C.block, borderBottom: `1px solid ${C.hair}` }}>{msg}</div>
      )}

      {tab === 'meetings' && meetingsView === 'meetings' && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
            <div style={cap}>MEETINGS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {meetings.map(m => {
                const s = meetingStatus(m)
                return (
                  <div key={m.id} onClick={() => patch({ cteMeeting: m.id, cteRoom: null })}
                    style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: sel && m.id === sel.id ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : `1px solid ${C.hair}`, background: sel && m.id === sel.id ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : C.surface }}>
                    {/* The title gets the full width of a 290px rail; the two
                        pills sit on the meta line under it rather than
                        squeezing it into three wrapped lines. */}
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{m.title}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, flex: 1, minWidth: 0 }}>
                        {(m.meeting_type || 'Meeting')} · {fmtDate(m.scheduled_at)}
                      </span>
                      {/* Opens the meeting room in the pane beside the list, so
                          the night is minuted here rather than on a page of its
                          own with the other meetings out of sight. */}
                      <button onClick={e => { e.stopPropagation(); openRoom(m.id) }}
                        title="Open the meeting room and record this meeting"
                        style={openChip(room === m.id)}>
                        OPEN
                      </button>
                      <span style={chip(s.fg)}>{s.label}</span>
                      {/* Deleting takes the whole record with it, so it asks
                          first — see deleteMeeting. */}
                      <button onClick={e => { e.stopPropagation(); deleteMeeting(m) }}
                        title={`Delete "${m.title}"`} aria-label={`Delete ${m.title}`}
                        style={delBtn}>✕</button>
                    </div>
                  </div>
                )
              })}
              {meetings.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No meetings recorded yet.</div>}
            </div>
          </div>

          {sel && room && (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              {/* Keyed on the meeting, so switching rooms starts a clean one
                  rather than showing the last one's agenda while it loads. */}
              <MeetingRoomPanel key={room} meetingId={room} inlineHeader
                onMeta={onRoomMeta} onExit={closeRoom} />
            </div>
          )}

          {sel && !room && (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
                <span style={{ ...chip(meetingStatus(sel).fg, 9), padding: '3px 7px' }}>{meetingStatus(sel).label}</span>
                <button onClick={() => openRoom(sel.id)}
                  title="Open the meeting room and record this meeting"
                  style={{ ...openChip(false, 9), padding: '3px 7px' }}>
                  OPEN
                </button>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 22px' }}>{(sel.meeting_type || 'Meeting')} · {fmtDate(sel.scheduled_at)}{sel.location ? ' · ' + sel.location : ''}</div>

              <div style={cap}>AGENDA</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 24 }}>
                {(sel.agenda_items || []).map((i, idx) => (
                  <AgendaRow key={i.id} item={i} idx={idx} name={name}
                    motions={(sel.motions || []).filter(mo => mo.agenda_item_id === i.id)}
                    actions={(sel.actions || []).filter(t => t.agenda_item_id === i.id)}
                    open={!!expanded[i.id]}
                    onToggle={() => setExpanded(e => ({ ...e, [i.id]: !e[i.id] }))} />
                ))}
                {(sel.agenda_items || []).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No agenda items.</div>}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px' }}>
                <div>
                  <div style={cap}>PRESENT</div>
                  <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{(sel.attendance || []).filter(a => (a.status || '').toLowerCase().includes('present')).map(a => a.full_name).join(', ') || 'Attendance recorded on the night.'}</div>
                  <div style={{ ...cap, margin: '16px 0 7px' }}>APOLOGIES</div>
                  <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{(sel.attendance || []).filter(a => (a.status || '').toLowerCase().includes('apolog')).map(a => a.full_name).join(', ') || 'None'}</div>
                </div>
                <div>
                  <div style={cap}>MOTIONS</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {(sel.motions || []).map(mo => {
                      const oc = motionOutcome(mo.outcome)
                      const tally = [mo.votes_for != null ? mo.votes_for + ' for' : null, mo.votes_against ? mo.votes_against + ' against' : null, mo.votes_abstain ? mo.votes_abstain + ' abstain' : null].filter(Boolean).join(', ')
                      return (
                        <div key={mo.id} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                            <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.description}</span>
                            <span style={chip(oc.fg)}>{oc.label}</span>
                          </div>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{mo.proposed_by_member_id ? 'Moved ' + name(mo.proposed_by_member_id) : ''}{mo.seconded_by_member_id ? ', seconded ' + name(mo.seconded_by_member_id) : ''}{tally ? ' · ' + tally : ''}</div>
                        </div>
                      )
                    })}
                    {(sel.motions || []).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No motions recorded.</div>}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Meeting Templates — the same two panes as Meetings: the club's saved
          agenda shapes down the left, the one being written or edited beside
          them. A template is only ever COPIED onto a meeting at the moment that
          meeting is created, so editing one here changes what the next meeting
          starts from and never rewrites a meeting already held. */}
      {tab === 'meetings' && meetingsView === 'templates' && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
            <div style={cap}>MEETING TEMPLATES</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(templates || []).map(t => {
                const on = tplEdit?.id === t.id
                return (
                  <div key={t.id} onClick={() => openTemplate(t)}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: on ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : `1px solid ${C.hair}`, background: on ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : C.surface }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{t.name}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3 }}>
                        {(t.items || []).length} item{(t.items || []).length === 1 ? '' : 's'}
                      </div>
                    </div>
                    <button onClick={e => { e.stopPropagation(); deleteTemplate(t) }}
                      title={`Delete "${t.name}"`} aria-label={`Delete ${t.name}`}
                      style={delBtn}>✕</button>
                  </div>
                )
              })}
              {templates === null && <div style={{ fontSize: 13, color: C.faint }}>Loading templates…</div>}
              {templates !== null && templates.length === 0 && (
                <div style={{ fontSize: 13, color: C.faint, lineHeight: 1.5 }}>
                  No templates saved yet. Make one and every meeting after this can start from it.
                </div>
              )}
            </div>
          </div>

          <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
            {!tplEdit ? (
              <div style={{ fontSize: 13, color: C.faint }}>
                Pick a template to edit it, or press <strong style={{ color: C.text }}>+ New Meeting Template</strong> to write one.
              </div>
            ) : (
              <div style={{ maxWidth: '38rem' }}>
                <h2 style={{ fontWeight: 700, fontSize: 21, margin: '0 0 4px', letterSpacing: '-0.01em' }}>
                  {tplEdit.id ? 'Edit meeting template' : 'New meeting template'}
                </h2>
                <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 18, lineHeight: 1.55 }}>
                  A saved agenda shape. Its items are copied onto a meeting’s agenda when that meeting
                  is created, so changing it here sets what the next meeting starts from.
                </div>

                <div style={{ display: 'grid', gap: 13 }}>
                  <label style={lbl}>TEMPLATE NAME *
                    <input value={tplEdit.name} onChange={e => setTpl('name', e.target.value)}
                      placeholder="e.g. Standard committee meeting" style={{ ...inp, marginTop: 4 }} />
                  </label>
                  <div>
                    <div style={lbl}>AGENDA ITEMS *</div>
                    {tplEdit.items.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, margin: '6px 0 8px' }}>
                        {tplEdit.items.map((it, idx) => (
                          <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '7px 10px' }}>
                            <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, width: 12, flexShrink: 0 }}>{idx + 1}</span>
                            <input value={it.title || ''}
                              onChange={e => setTplEdit(t => ({ ...t, items: t.items.map((x, i) => (i === idx ? { ...x, title: e.target.value } : x)) }))}
                              style={{ ...inp, flex: 1, padding: '2px 0', background: 'transparent', border: 'none', borderRadius: 0 }} />
                            <button onClick={() => setTplEdit(t => ({ ...t, items: t.items.filter((_, i) => i !== idx) }))}
                              title="Remove this item" style={delBtn}>✕</button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, marginTop: tplEdit.items.length ? 0 : 4 }}>
                      <input value={tplEdit.draft} onChange={e => setTpl('draft', e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTplRow() } }}
                        placeholder="Agenda item title, press Enter" style={{ ...inp, flex: 1 }} />
                      <button onClick={addTplRow} disabled={!tplEdit.draft.trim()}
                        style={{ ...btnS, opacity: tplEdit.draft.trim() ? 1 : 0.6, flexShrink: 0 }}>Add item</button>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' }}>
                  <button onClick={saveTemplateEdit}
                    disabled={tplEdit.busy || !tplEdit.name.trim() || !(tplEdit.items.length || tplEdit.draft.trim())}
                    style={{ ...btnP, opacity: (tplEdit.busy || !tplEdit.name.trim() || !(tplEdit.items.length || tplEdit.draft.trim())) ? 0.6 : 1 }}>
                    {tplEdit.busy ? 'Saving…' : (tplEdit.id ? 'Save template' : 'Create template')}
                  </button>
                  <button onClick={() => { setTplEdit(null); patch({ cteTemplate: null }) }} disabled={tplEdit.busy} style={btnS}>
                    {tplEdit.id ? 'Close' : 'Cancel'}
                  </button>
                  {tplEdit.id && (
                    <button
                      onClick={() => {
                        const t = (templates || []).find(x => x.id === tplEdit.id)
                        if (t) deleteTemplate(t)
                      }}
                      disabled={tplEdit.busy}
                      style={{ ...btnS, marginLeft: 'auto', color: C.block, borderColor: 'color-mix(in srgb, var(--pb-red) 40%, transparent)' }}>
                      Delete template
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'positions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '56rem' }}>
          {vacancies.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 12px', borderRadius: 8, background: 'rgba(245,181,66,0.07)', border: '1px solid rgba(245,181,66,0.25)', fontSize: 12.5, color: C.warn, lineHeight: 1.45, marginBottom: 14 }}>
              <span style={{ flexShrink: 0 }}>⚠</span>
              <span>{vacancies.length} position{vacancies.length === 1 ? '' : 's'} unfilled — {vacancies.map(v => v.name).join(', ')}.</span>
            </div>
          )}
          <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faintest, marginBottom: 8 }}>DRAG THE GRIP TO REORDER</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {positions.map(p => {
              const t = p.current_term
              const dragging = dragId === p.id
              const isOver = overId === p.id && dragId && dragId !== p.id
              return (
                <div key={p.id}
                  onDragOver={e => { if (dragId) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (overId !== p.id) setOverId(p.id) } }}
                  onDrop={e => { e.preventDefault(); movePosition(dragId, p.id) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, background: C.surface, borderRadius: 8, padding: '11px 13px',
                    border: `1px solid ${isOver ? C.accent : (t ? C.hair : 'rgba(245,181,66,0.35)')}`,
                    boxShadow: isOver ? 'inset 0 2px 0 var(--pb-accent)' : undefined, opacity: dragging ? 0.5 : 1 }}>
                  <span draggable
                    onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; setDragId(p.id) }}
                    onDragEnd={() => { setDragId(null); setOverId(null) }}
                    title="Drag to reorder"
                    style={{ cursor: 'grab', color: C.faint, fontSize: 15, lineHeight: 1, padding: '0 2px', flexShrink: 0, userSelect: 'none' }}>⠿</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13, color: C.dim }}>{p.name}</div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: t ? C.text : C.warn }}>{t ? t.holder_name : 'Vacant'}</div>
                  </div>
                  {t?.started_at && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, flexShrink: 0 }}>since {fmtDate(t.started_at)}</span>}
                </div>
              )
            })}
            {positions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No committee positions set up yet.</div>}
          </div>
        </div>
      )}

      {tab === 'motions' && maView === 'motions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ maxWidth: '48rem' }}>
            <div>
              <div style={cap}>MOTION REGISTER</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {allMotions.map((mo, i) => {
                  const oc = motionOutcome(mo.outcome)
                  return (
                    <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                        <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.description}</span>
                        <span style={chip(oc.fg)}>{oc.label}</span>
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{mo.from}{mo.proposed_by_member_id ? ' · moved ' + name(mo.proposed_by_member_id) : ''}</div>
                    </div>
                  )
                })}
                {allMotions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No motions recorded this season.</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Actions → List: the open committee actions, read straight down. Board
          and Timeline are the manage screen's own views of the same rows, with
          their filter row, so all three answer the same question three ways. */}
      {tab === 'motions' && maView === 'actions' && actionsView === 'list' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ maxWidth: '48rem' }}>
            <div>
              <div style={cap}>OPEN COMMITTEE ACTIONS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {openTasks.map(t => {
                  const s = taskState(t)
                  return (
                    <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text, lineHeight: 1.4 }}>{t.title}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3 }}>{t.assigned_to_member_id ? name(t.assigned_to_member_id) : 'Unassigned'}{t.due_date ? ' · due ' + fmtDate(t.due_date) : ''}</div>
                      </div>
                      <span style={chip(s.fg)}>{s.label}</span>
                    </div>
                  )
                })}
                {openTasks.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No open committee actions.</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'motions' && maView === 'actions' && actionsView !== 'list' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div className="max-w-5xl">
            <Suspense fallback={<Loading />}>
              <TasksTab members={members} view={actionsView}
                onView={v => patch({ cteActionsView: v })} />
            </Suspense>
          </div>
        </div>
      )}

      {tab === 'plans' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div className="max-w-5xl"><Suspense fallback={<Loading />}><PlanTab members={members} section={plansView} /></Suspense></div>
        </div>
      )}

      {tab === 'documents' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div className="max-w-5xl"><Suspense fallback={<Loading />}><DocumentsTab /></Suspense></div>
        </div>
      )}

      {tab === 'calendar' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div className="max-w-5xl"><Suspense fallback={<Loading />}><CalendarTab /></Suspense></div>
        </div>
      )}

      {mk && (
        <div onClick={() => { if (!mk.busy) setMk(null) }}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: 'min(460px, 100%)', maxHeight: '90vh', overflowY: 'auto', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}
            className="pb-scroll">

            {mk.step === 'meeting' ? (
              <>
                <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>New meeting</div>
                <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16 }}>
                  Schedule a committee meeting or an AGM. Pick an agenda template and its items are copied straight onto the new meeting’s agenda.
                </div>
                <div style={{ display: 'grid', gap: 11 }}>
                  <label style={lbl}>TITLE *
                    <input value={mk.form.title} onChange={e => setField('title', e.target.value)}
                      placeholder="e.g. Committee Meeting - September 2026" style={{ ...inp, marginTop: 4 }} />
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 11 }}>
                    <label style={lbl}>TYPE
                      <select value={mk.form.meeting_type} onChange={e => setField('meeting_type', e.target.value)} style={{ ...inp, marginTop: 4 }}>
                        {MEETING_TYPES.map(t => <option key={t} value={t}>{typeLabel(t)}</option>)}
                      </select>
                    </label>
                    <label style={lbl}>DATE &amp; TIME *
                      <input type="datetime-local" value={mk.form.scheduled_at} onChange={e => setField('scheduled_at', e.target.value)}
                        style={{ ...inp, marginTop: 4 }} />
                    </label>
                  </div>
                  <label style={lbl}>LOCATION
                    <input value={mk.form.location} onChange={e => setField('location', e.target.value)}
                      placeholder="e.g. Clubrooms" style={{ ...inp, marginTop: 4 }} />
                  </label>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                      <span style={lbl}>AGENDA TEMPLATE</span>
                      {/* Making one is a step people reach for from here, halfway
                          through the meeting they came to create — so it is on
                          this dialog rather than back on the manage screen. */}
                      <button onClick={() => setMk(m => ({ ...m, step: 'template', error: null }))}
                        style={{ marginLeft: 'auto', background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12, fontWeight: 600, color: 'var(--pb-accent-ink)' }}>
                        + New template
                      </button>
                    </div>
                    <select value={mk.form.agenda_template_id} onChange={e => setField('agenda_template_id', e.target.value)}
                      style={{ ...inp, marginTop: 4 }}>
                      <option value="">{templates === null ? 'Loading templates…' : 'No agenda template'}</option>
                      {(templates || []).map(t => (
                        <option key={t.id} value={t.id}>{t.name} ({(t.items || []).length} item{(t.items || []).length === 1 ? '' : 's'})</option>
                      ))}
                    </select>
                    {templates !== null && templates.length === 0 && (
                      <div style={{ fontSize: 12, color: C.faint, marginTop: 6, lineHeight: 1.5 }}>
                        No templates saved yet. Make one and every meeting after this can start from it.
                      </div>
                    )}
                  </div>
                </div>
                {mk.error && <div style={{ fontSize: 12.5, color: C.block, marginTop: 12 }}>{mk.error}</div>}
                <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
                  <button onClick={() => setMk(null)} disabled={mk.busy} style={btnS}>Cancel</button>
                  <button onClick={createMeeting}
                    disabled={mk.busy || !mk.form.title.trim() || !mk.form.scheduled_at}
                    style={{ ...btnP, opacity: (mk.busy || !mk.form.title.trim() || !mk.form.scheduled_at) ? 0.6 : 1 }}>
                    {mk.busy ? 'Creating…' : 'Create meeting'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>New agenda template</div>
                <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16 }}>
                  A saved agenda shape. Save it and it is chosen for the meeting you are creating, and offered on every meeting after that.
                </div>
                <div style={{ display: 'grid', gap: 11 }}>
                  <label style={lbl}>TEMPLATE NAME *
                    <input value={mk.tpl.name} onChange={e => setTplField('name', e.target.value)}
                      placeholder="e.g. Standard committee meeting" style={{ ...inp, marginTop: 4 }} />
                  </label>
                  <div>
                    <div style={lbl}>AGENDA ITEMS *</div>
                    {mk.tpl.items.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, margin: '6px 0 8px' }}>
                        {mk.tpl.items.map((it, idx) => (
                          <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '7px 10px' }}>
                            <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, width: 12, flexShrink: 0 }}>{idx + 1}</span>
                            <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0 }}>{it.title}</span>
                            <button onClick={() => setMk(m => ({ ...m, tpl: { ...m.tpl, items: m.tpl.items.filter((_, i) => i !== idx) } }))}
                              title="Remove this item"
                              style={{ background: 'transparent', border: 'none', color: C.faint, cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: '2px 4px' }}>✕</button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, marginTop: mk.tpl.items.length ? 0 : 4 }}>
                      <input value={mk.tpl.draft} onChange={e => setTplField('draft', e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTplItem() } }}
                        placeholder="Agenda item title, press Enter" style={{ ...inp, flex: 1 }} />
                      <button onClick={addTplItem} disabled={!mk.tpl.draft.trim()} style={{ ...btnS, opacity: mk.tpl.draft.trim() ? 1 : 0.6, flexShrink: 0 }}>Add item</button>
                    </div>
                  </div>
                </div>
                {mk.error && <div style={{ fontSize: 12.5, color: C.block, marginTop: 12 }}>{mk.error}</div>}
                <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
                  <button onClick={() => setMk(m => ({ ...m, step: 'meeting', error: null }))} disabled={mk.busy} style={btnS}>Back</button>
                  <button onClick={saveTemplate}
                    disabled={mk.busy || !mk.tpl.name.trim() || !(mk.tpl.items.length || mk.tpl.draft.trim())}
                    style={{ ...btnP, opacity: (mk.busy || !mk.tpl.name.trim() || !(mk.tpl.items.length || mk.tpl.draft.trim())) ? 0.6 : 1 }}>
                    {mk.busy ? 'Saving…' : 'Save template'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
