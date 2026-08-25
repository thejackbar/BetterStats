import { useState, useEffect, useRef } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, SegGroup, SegItem, StatReadout, Toast, Drawer, ManageLink, HEAD_SIDE, HEAD_CENTRE, HEAD_SIDE_END, HeaderSearch, matchesQuery } from '../ui'
import EntityManager from '../parts/EntityManager'

// Club Diary on real data — the board (one current occurrence per active task
// definition) rendered as a day-proportional season timeline. Blocked / overdue
// state and the critical path are derived client-side from the definitions'
// stored dependencies (the backend stores deps but doesn't analyse them).

const MONTH_LABELS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

// The twelve months of a club's diary year, starting wherever the club starts
// it. Day counts come from the real calendar so a February in a leap year is 29
// and the ruler stays aligned with the bars underneath it.
function monthDefs(startIdx, startYear) {
  return Array.from({ length: 12 }, (_, n) => {
    const m = (startIdx + n) % 12
    const y = startYear + Math.floor((startIdx + n) / 12)
    return [MONTH_LABELS[m], new Date(Date.UTC(y, m + 1, 0)).getUTCDate()]
  })
}
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

// The ISO date a day-offset from the season's start lands on — the inverse of
// `dayOf` below, so a bar dragged N days and written back reads at exactly the
// day it was dropped on.
const isoOfDay = (seasonStart, day) => new Date(seasonStart + day * 86400000).toISOString().slice(0, 10)

// ONE fetch of everything this screen reads, assembled into the shape it wants.
// A module-level function rather than an inline effect body BECAUSE ADDING A
// TASK HAS TO RE-RUN IT: /board is what materialises a brand-new definition
// into this period's occurrence, so re-reading it is what puts the new task on
// the plan — and it hands back the occurrence id any dates are written against.
function fetchDiary() {
  return Promise.all([
    api.diaryBoard().catch(() => []),
    api.adminGetSettings().catch(() => ({})),
    api.diaryListDefinitions().catch(() => ([])),
    api.diarySeasonYears().catch(() => ([])),
    api.raRoles().catch(() => ({ roles: [] })),
    api.feeAllMembers().catch(() => ({ members: [] })),
    api.diaryListCategories().catch(() => ({ categories: [] })),
  ]).then(([boardRes, settingsRes, defsRes, yearsRes, rolesRes, membersRes, catsRes]) => {
    // GET /club-diary/board returns { tasks: [...] }. This read `board`,
    // which is never present, so it silently fell back to an empty list and
    // the season plan claimed there were no tasks while the full editor
    // showed a season's worth.
    const board = Array.isArray(boardRes) ? boardRes : (boardRes?.tasks || boardRes?.board || [])
    const defs = Array.isArray(defsRes) ? defsRes : (defsRes?.definitions || [])
    const depsById = {}
    defs.forEach(d => { depsById[d.id] = d.depends_on || [] })
    const roles = rolesRes?.roles || rolesRes || []
    const roleName = {}
    roles.forEach(r => { roleName[r.id] = r.title })
    const memberName = {}
    ;(membersRes?.members || membersRes || []).forEach(m => { memberName[m.member_id] = m.full_name })
    const years = (Array.isArray(yearsRes) ? yearsRes : (yearsRes?.years || [])).map(Number).filter(Boolean)
    const categories = Array.isArray(catsRes) ? catsRes : (catsRes?.categories || [])
    // 1-12, July unless the club says otherwise. A club running Jan-Dec
    // administratively should not have its year cut in half.
    const startMonth = Number(settingsRes?.diary_start_month) || 7
    return { board, depsById, roles, roleName, memberName, defs, years, categories, startMonth }
  })
}

// ── Add a task ───────────────────────────────────────────────────────────────
// The four cadences the backend accepts (services/club_diary._FREQUENCIES).
// NOTED, NOT FIXED: the Template library's own picker below also offers Weekly
// and Conditional, which create_definition refuses with a 422 — a pre-existing
// gap in that control, and not one to repeat here.
const ADD_FREQUENCIES = [['annual', 'Annual'], ['quarterly', 'Quarterly'], ['monthly', 'Monthly'], ['once', 'One-time']]
const MONTH_NAMES = MONTH_LABELS.map(m => m[0] + m.slice(1).toLowerCase())

const M_INP = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '8px 11px', color: C.text, fontSize: 13, outline: 'none', width: '100%', boxSizing: 'border-box', fontFamily: 'inherit' }
const M_LBL = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.1em', color: C.faint, display: 'block' }
// Text on an accent fill is `--pb-on-accent` — one answer everywhere, so a club
// whose accent is navy gets white ink rather than near-black on near-black.
const BTN_P = { padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: 'var(--pb-on-accent)', cursor: 'pointer' }
const BTN_S = { padding: '8px 13px', borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }

// Adding a task to the season plan. The fields are the full diary editor's own
// (AdminClubDiary's DefinitionFields), because a task added here is the same
// record that screen edits — a DEFINITION, which is what makes it a standing
// obligation rather than a one-off note on this season. The two dates at the
// bottom are the extra half: they land on THIS season's occurrence, so the task
// arrives on the plan already placed rather than as an unplaced row.
//
// Declared at module level, never inside the screen's render — React compares
// element types by identity, so a component built during a render is a new type
// every time and its subtree (with the caret in whatever field is focused) is
// torn down and rebuilt on every keystroke.
function AddTaskModal({ categories, roles, seasonLabel, onCreateCategory, onClose, onCreated }) {
  const [form, setForm] = useState({
    title: '', category_id: '', frequency: 'annual', default_month: '', responsibility_role_id: '',
    third_party: '', budget_estimate: '', description: '',
    reminder_enabled: false, reminder_days_before: 14, start_date: '', due_date: '',
  })
  const [newCat, setNewCat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const showMonth = form.frequency === 'annual' || form.frequency === 'once'
  const title = form.title.trim()

  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  async function addCategory() {
    const name = newCat.trim()
    if (!name) return
    setBusy(true); setError(null)
    try {
      const c = await onCreateCategory(name)
      setNewCat('')
      if (c && c.id) set('category_id', c.id)
    } catch (e) { setError(String(e?.message || e)) } finally { setBusy(false) }
  }

  async function submit() {
    if (!title) return
    setBusy(true); setError(null)
    try {
      await onCreated({
        definition: {
          title,
          category_id: form.category_id || null,
          frequency: form.frequency,
          default_month: showMonth && form.default_month ? Number(form.default_month) : null,
          description: form.description.trim() || null,
          responsibility_role_id: form.responsibility_role_id || null,
          third_party: form.third_party.trim() || null,
          budget_estimate: form.budget_estimate === '' ? null : Number(form.budget_estimate),
          reminder_enabled: form.reminder_enabled,
          reminder_days_before: Number(form.reminder_days_before) || 14,
        },
        // Only the dates actually typed are sent. An omitted key leaves the
        // generated default alone; sending null would clear it.
        dates: {
          ...(form.start_date ? { start_date: form.start_date } : {}),
          ...(form.due_date ? { due_date: form.due_date } : {}),
        },
      })
    } catch (e) {
      setError(String(e?.message || e))
      setBusy(false)
    }
  }

  const row2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 11 }
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
      <div onClick={e => e.stopPropagation()} className="pb-scroll" role="dialog" aria-label="Add a diary task"
        style={{ width: 'min(580px, 100%)', maxHeight: '88vh', overflowY: 'auto', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}>
        <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>Add a task</div>
        <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16, lineHeight: 1.5 }}>
          Lands on the {seasonLabel} plan straight away, and becomes one of the club's standing obligations — every season you generate from here includes it.
        </div>

        <div style={{ display: 'grid', gap: 11 }}>
          <label style={M_LBL}>TASK *
            <input autoFocus aria-label="TASK" value={form.title} onChange={e => set('title', e.target.value)}
              placeholder="e.g. Ground lease review" style={{ ...M_INP, marginTop: 4 }} />
          </label>

          <div style={row2}>
            <label style={M_LBL}>CATEGORY
              <select aria-label="CATEGORY" value={form.category_id} onChange={e => set('category_id', e.target.value)} style={{ ...M_INP, marginTop: 4 }}>
                <option value="">No category</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <div>
              <div style={M_LBL}>NEW CATEGORY</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <input aria-label="NEW CATEGORY" value={newCat} onChange={e => setNewCat(e.target.value)} placeholder="Add one"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCategory() } }}
                  style={{ ...M_INP, flex: 1, minWidth: 0 }} />
                <button type="button" onClick={addCategory} disabled={busy || !newCat.trim()}
                  style={{ ...BTN_S, flexShrink: 0, opacity: (busy || !newCat.trim()) ? 0.5 : 1 }}>Add</button>
              </div>
            </div>
          </div>

          <div style={row2}>
            <label style={M_LBL}>CADENCE
              <select aria-label="CADENCE" value={form.frequency} onChange={e => set('frequency', e.target.value)} style={{ ...M_INP, marginTop: 4 }}>
                {ADD_FREQUENCIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            {showMonth ? (
              <label style={M_LBL}>USUAL MONTH
                <select aria-label="USUAL MONTH" value={form.default_month} onChange={e => set('default_month', e.target.value)} style={{ ...M_INP, marginTop: 4 }}>
                  <option value="">No set month</option>
                  {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </label>
            ) : <div />}
          </div>

          <div style={row2}>
            <label style={M_LBL}>OWNER ROLE
              <select aria-label="OWNER ROLE" value={form.responsibility_role_id} onChange={e => set('responsibility_role_id', e.target.value)} style={{ ...M_INP, marginTop: 4 }}>
                <option value="">Unassigned</option>
                {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
              </select>
            </label>
            <label style={M_LBL}>BUDGET ($)
              <input type="number" min="0" step="1" aria-label="BUDGET" value={form.budget_estimate}
                onChange={e => set('budget_estimate', e.target.value)} style={{ ...M_INP, marginTop: 4 }} />
            </label>
          </div>

          <div style={row2}>
            <label style={M_LBL}>THIRD PARTY
              <input aria-label="THIRD PARTY" value={form.third_party} onChange={e => set('third_party', e.target.value)}
                placeholder="Contractor / supplier" style={{ ...M_INP, marginTop: 4 }} />
            </label>
            <div />
          </div>

          <label style={M_LBL}>NOTES
            <input aria-label="NOTES" value={form.description} onChange={e => set('description', e.target.value)}
              placeholder="What this involves (optional)" style={{ ...M_INP, marginTop: 4 }} />
          </label>

          <div>
            <div style={{ ...M_LBL, marginBottom: 4 }}>ON THIS SEASON'S PLAN</div>
            <div style={row2}>
              <label style={M_LBL}>START
                <input type="date" aria-label="START" value={form.start_date} onChange={e => set('start_date', e.target.value)} style={{ ...M_INP, marginTop: 4 }} />
              </label>
              <label style={M_LBL}>DUE
                <input type="date" aria-label="DUE" value={form.due_date} onChange={e => set('due_date', e.target.value)} style={{ ...M_INP, marginTop: 4 }} />
              </label>
            </div>
            <div style={{ fontSize: 11.5, color: C.faintest, marginTop: 5, lineHeight: 1.5 }}>
              Both are optional — a task with a start and a due date draws as a bar you can drag along the timeline, one with only a due date as a marker.
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: C.dim, cursor: 'pointer' }}>
            <input type="checkbox" checked={form.reminder_enabled} onChange={e => set('reminder_enabled', e.target.checked)} />
            Email whoever it is on before it falls due
          </label>
          {form.reminder_enabled && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: MONO, fontSize: 10, color: C.faint }}>
              <input type="number" min="1" max="180" value={form.reminder_days_before}
                onChange={e => set('reminder_days_before', e.target.value)} style={{ ...M_INP, width: 76 }} />
              days before due
            </label>
          )}
        </div>

        {error && <div style={{ marginTop: 12, fontSize: 12.5, color: C.block, lineHeight: 1.5 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={BTN_S}>Cancel</button>
          <button onClick={submit} disabled={busy || !title} style={{ ...BTN_P, opacity: (busy || !title) ? 0.6 : 1 }}>
            {busy ? 'Adding…' : 'Add task'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ClubDiary({ st, patch, narrow }) {
  const tab = st.diaryTab || 'plan'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  // Which season "Generate" targets. Null until the officer picks one, so the
  // default can follow the data (the first season not yet generated).
  const [pickedYear, setPickedYear] = useState(null)
  const [adding, setAdding] = useState(false)

  // ── Dragging a task along the timeline ─────────────────────────────────────
  // POINTER EVENTS, NOT HTML5 DRAG-AND-DROP, and that is the whole reason this
  // is hand-rolled: a Gantt bar has to follow the cursor continuously and land
  // on a DAY, which a dragstart/drop pair — which reports nothing in between —
  // cannot express. `drag` drives the live preview and re-renders on every
  // move; `dragRef` is the gesture's own state, read by window listeners that
  // are attached once per gesture rather than on every pixel.
  const [drag, setDrag] = useState(null)
  const dragRef = useRef(null)
  // A drag ends in a click on the same element. Without this the drawer would
  // open every time a bar was moved.
  const suppressClick = useRef(false)
  // The commit closure is re-pointed on every render, so the listeners below —
  // attached once when the gesture starts — always call the current one rather
  // than the one captured at pointerdown.
  const commitRef = useRef(null)

  useEffect(() => {
    let alive = true
    fetchDiary()
      .then(d => { if (alive) setData(d) })
      .catch(e => { if (alive) setErr(String(e?.message || e)) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!drag) return
    const move = (e) => {
      const d = dragRef.current
      if (!d) return
      const dx = e.clientX - d.x0
      if (Math.abs(dx) > 3) d.moved = true
      let shift = Math.round((dx / d.width) * SEASON_DAYS)
      // Keep the task inside the season being drawn — a bar dragged off the end
      // would simply vanish. Clamped ONE-WAY, so a task whose dates already sit
      // outside the window (a due date in the next year) can still be dragged
      // back towards it rather than being snapped the moment it is touched.
      if (shift < 0 && d.lo + shift < 0) shift = Math.min(0, -d.lo)
      if (shift > 0 && d.hi + shift > SEASON_DAYS) shift = Math.max(0, SEASON_DAYS - d.hi)
      if (shift !== d.shift) {
        d.shift = shift
        setDrag(s => (s && s.id === d.id ? { ...s, shift } : s))
      }
    }
    const up = () => {
      const d = dragRef.current
      dragRef.current = null
      setDrag(null)
      if (!d || !d.moved) return
      suppressClick.current = true
      // Cleared once the click that closes this gesture has been and gone.
      setTimeout(() => { suppressClick.current = false }, 0)
      if (d.shift && commitRef.current) commitRef.current(d)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
  }, [drag ? drag.id : null]) // eslint-disable-line react-hooks/exhaustive-deps

  // A bar (start + due, moves as a block) or a due marker (the due date alone).
  // `width` is the TRACK's pixel width, measured once at pointerdown, which is
  // what turns a pixel delta into a number of days.
  const beginDrag = (e, t, kind) => {
    if (!t.occId) return                       // nothing to write the dates to
    if (e.button != null && e.button !== 0) return
    const track = e.currentTarget.parentElement
    const width = track ? track.getBoundingClientRect().width : 0
    if (!width) return
    dragRef.current = {
      id: t.id, kind, x0: e.clientX, width, shift: 0, moved: false,
      lo: kind === 'bar' ? t.startDay : t.dueDay, hi: t.dueDay,
    }
    setDrag({ id: t.id, kind, shift: 0 })
    e.preventDefault()
    e.stopPropagation()
  }

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 7 }
  const q = (st.diaryQuery || '').trim()

  // NEVER DECLARE A COMPONENT INSIDE A RENDER. React compares element types by
  // identity, so a `const Header = () => …` written here is a different type on
  // every render and its whole subtree is torn down and rebuilt — which throws
  // the caret out of the search box below after every character typed. A plain
  // function returning elements, CALLED rather than mounted, keeps the types
  // stable. Same fix the Committee screen carries.
  const header = (children) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div style={HEAD_SIDE}>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Club Diary</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>THE CLUB'S RECURRING OBLIGATIONS, BY SEASON</Caption>
      </div>
      <div style={HEAD_CENTRE}>
        <SegTabs value={tab} onChange={k => patch({ diaryTab: k })} tabs={[{ key: 'plan', label: 'Season plan' }, { key: 'templates', label: 'Template library' }]} />
      </div>
      <div style={HEAD_SIDE_END}>
        <ManageLink to="/admin/clubhouse/diary/manage">Full diary editor</ManageLink>
        {children}
      </div>
    </ScreenHeader>
  )

  if (!data) return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>{header()}<div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load the club diary.' : 'Loading the club diary…'}</div></div>

  const { board, depsById, roles, roleName, memberName, defs, years, categories } = data
  const nowUTC = Date.now()
  // season window: prefer the club's own season years, else derive from today
  const nowY = new Date().getUTCFullYear(), nowM = new Date().getUTCMonth()
  // The season we are actually IN (rolls in July), kept separate from the
  // newest season that happens to have a generated plan. Conflating the two is
  // what made "Generate" always offer next season even when this one had never
  // been generated.
  const startMonth = data?.startMonth || 7
  const startIdx = startMonth - 1                 // JS months are 0-based
  const currentSeasonYear = nowM >= startIdx ? nowY : nowY - 1
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
  const SEASON_START = Date.UTC(seasonYear, startIdx, 1)
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
      id: r.id, occId: occ.id || null, title: r.title, cadence, recurs, deps, blockers, status,
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

  // Write straight into the held board row rather than re-reading the whole
  // screen — a reschedule is one field on one occurrence, and a full reload
  // between grabbing a bar and letting go of the next one would be a jolt.
  const applyOccurrence = (defId, fields) => setData(d => (d ? {
    ...d,
    board: d.board.map(r => (r.id === defId && r.occurrence ? { ...r, occurrence: { ...r.occurrence, ...fields } } : r)),
  } : d))

  // A finished drag. The bar is moved locally first so it stays where it was
  // dropped rather than snapping back for the length of the request, and put
  // back where it came from if the write fails — the same optimistic-with-
  // rollback rule the Committee board's own card moves follow.
  const commitDrag = (d) => {
    const t = byId[d.id]
    if (!t || !t.occId || !d.shift) return
    const fields = { due_date: isoOfDay(SEASON_START, t.dueDay + d.shift) }
    if (d.kind === 'bar') fields.start_date = isoOfDay(SEASON_START, t.startDay + d.shift)
    const before = { start_date: t.start || null, due_date: t.due || null }
    applyOccurrence(d.id, fields)
    api.diaryUpdateOccurrence(t.occId, fields).catch(() => {
      applyOccurrence(d.id, before)
      patch({ toast: { tone: 'block', title: 'Could not move "' + t.title + '".', body: 'It has been put back where it was.' } })
    })
  }
  commitRef.current = commitDrag

  const createCategory = async (name) => {
    const c = await api.diaryCreateCategory(name)
    // get_or_create_category hands back the existing row for a name the club
    // already has, so filter before appending rather than listing it twice.
    setData(d => (d ? { ...d, categories: [...d.categories.filter(x => x.id !== c.id), c] } : d))
    return c
  }

  const addTask = async ({ definition, dates }) => {
    const def = await api.diaryCreateDefinition(definition)
    // /board is what mints this period's occurrence for a brand-new definition,
    // so re-reading is what puts the task on the plan — and it is the only
    // place the occurrence id the dates are written against comes from.
    const fresh = await fetchDiary()
    const row = fresh.board.find(r => r.id === def.id)
    if (row && row.occurrence && Object.keys(dates).length) {
      row.occurrence = await api.diaryUpdateOccurrence(row.occurrence.id, dates)
    }
    setData(fresh)
    setAdding(false)
    patch({ toast: { tone: 'ok', title: 'Added "' + def.title + '" to the ' + seasonLabel(seasonYear) + ' plan.', body: "It is a standing task now, so every season you generate from here includes it." } })
  }

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
    // The search reaches who a task is ON as well as what it is called — the
    // diary is read as "what is Sam still holding" at least as often as by task
    // name.
    if (!matchesQuery(q, t.title, t.cadence, t.role, t.person)) return false
    return true
  })

  // day-proportional month headers + matching gridline stops
  let acc = 0; const stops = []
  const months = monthDefs(startIdx, seasonYear).map(([label, days]) => { acc += days; const pct = (acc / SEASON_DAYS) * 100; stops.push(`transparent calc(${pct}% - 1px), ${C.surface2} calc(${pct}% - 1px), ${C.surface2} ${pct}%`); return { label, days } })
  const trackGrid = `linear-gradient(to right, ${stops.join(', ')})`

  const clamp = (v) => Math.max(0, Math.min(100, v))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {header(<>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
          <StatReadout value={doneCount + '/' + dated.length} label="DATED TASKS DONE" />
          <StatReadout value={String(overdue.length)} label="OVERDUE" fg={overdue.length ? C.block : C.ok} />
          <StatReadout value={String(blocked.length)} label="BLOCKED" fg={blocked.length ? C.block : C.ok} />
          <StatReadout value={money(spent) + ' / ' + money(budget)} label="SPENT / BUDGETED" />
        </div>
      </>)}

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

          {/* Committee's own segmented control. Cadence is one value, so it is
              a SegTabs; "Overdue & blocked only" narrows on a different axis
              and can be on alongside any cadence, so it keeps its own box
              rather than pretending to be a fifth cadence. */}
          {/* The search sits UNDER the cadence buttons, on its own line: the two
              narrow the same list, and reading them top to bottom is what says
              the box applies to everything the buttons left standing. */}
          <div style={{ padding: '11px 20px', borderBottom: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <SegTabs value={cadFilter} onChange={c => patch({ cadFilter: c })}
                tabs={['All'].concat(CAD_ORDER.filter(c => tasks.some(t => t.cadence === c))).map(c => ({ key: c, label: c }))} />
              <SegGroup>
                <SegItem tone="red" active={issuesOnly} onClick={() => patch({ issuesOnly: !issuesOnly })}>Overdue &amp; blocked only</SegItem>
              </SegGroup>
            </div>
            {/* NARROWING A LIST AND ADDING TO IT ARE ONE LINE — the action sits
                on the right of the box that searches the very list it adds to,
                the same row the Directory, Roster and Committee all carry.
                `alignSelf: 'stretch'` is load-bearing: the column above sets
                `alignItems: 'flex-start'`, so without it the row is only as
                wide as its own contents and HeaderSearch's `marginLeft: auto`
                has nothing to push the button against. */}
            <HeaderSearch value={st.diaryQuery} onChange={v => patch({ diaryQuery: v })}
              placeholder="Search tasks, roles and who is doing them…"
              style={{ flex: '0 0 auto', alignSelf: 'stretch' }}
              trailing={<button onClick={() => setAdding(true)} style={BTN_P}>+ Add task</button>} />
            <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faintest }}>
              DRAG A BAR OR A DUE MARKER ALONG THE TIMELINE TO RESCHEDULE IT
            </div>
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
                      // While this task is being dragged, everything below is
                      // drawn from its SHIFTED days, so the bar follows the
                      // cursor before anything has been written.
                      const dragging = !!drag && drag.id === t.id
                      const shift = dragging ? drag.shift : 0
                      const sDay = t.startDay == null ? null : t.startDay + shift
                      const dDay = t.dueDay == null ? null : t.dueDay + shift
                      const hasBar = sDay != null && dDay != null
                      // A generated occurrence carries a due date and no start
                      // (see club_diary._due_for_period), which used to draw
                      // nothing at all in the track. It gets a marker, so what
                      // the club actually knows is on the timeline and can be
                      // moved without inventing a start date for it.
                      const dueOnly = sDay == null && dDay != null
                      const movable = !!t.occId
                      const left = hasBar ? clamp((sDay / SEASON_DAYS) * 100) : 0
                      const width = hasBar ? Math.max(1.4, clamp((Math.max(1, dDay - sDay) / SEASON_DAYS) * 100)) : 0
                      const overBudget = t.spent > t.budget && t.budget > 0
                      const openTask = () => { if (!suppressClick.current) patch({ task: t.id }) }
                      const grab = movable ? (dragging ? 'grabbing' : 'grab') : 'pointer'
                      const dragHint = movable
                        ? (dueOnly ? 'Drag to move the due date' : 'Drag to reschedule')
                        : 'This season has no occurrence for this task yet'
                      const dragLabel = dragging
                        ? (hasBar ? fmtDate(isoOfDay(SEASON_START, sDay)) + ' → ' + fmtDate(isoOfDay(SEASON_START, dDay))
                          : 'due ' + fmtDate(isoOfDay(SEASON_START, dDay)))
                        : null
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
                              <div onPointerDown={e => beginDrag(e, t, 'bar')} onClick={openTask}
                                title={dragHint} role="button" aria-label={t.title + ' — ' + dragHint}
                                style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: left + '%', width: width + '%', height: 20, borderRadius: 5, display: 'flex', alignItems: 'center', padding: '0 6px', overflow: 'hidden', cursor: grab, touchAction: 'none', zIndex: dragging ? 6 : 1,
                                ...(t.recurs ? { backgroundImage: `repeating-linear-gradient(90deg, ${tone.fg}55 0 6px, transparent 6px 12px)`, border: `1px dashed ${tone.fg}66` } : { background: `color-mix(in srgb, ${tone.fg} 22%, transparent)`, border: `1px solid ${onCp ? tone.fg : `color-mix(in srgb, ${tone.fg} 45%, transparent)`}` }),
                                ...(t.status === 'blocked' ? { backgroundImage: 'repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.28) 4px 8px)' } : {}),
                                ...(dragging ? { boxShadow: `0 0 0 1px ${tone.fg}, 0 4px 14px rgba(0,0,0,0.45)` } : {}) }}>
                                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', color: tone.fg, whiteSpace: 'nowrap' }}>{t.budget ? money(t.budget) : tone.label}</span>
                              </div>
                            )}
                            {/* A due date with no start: the one thing the row
                                knows, drawn where it falls and draggable on its
                                own. Never widened into a bar — a start date
                                nobody set is not ours to invent. */}
                            {dueOnly && (
                              <div onPointerDown={e => beginDrag(e, t, 'due')} onClick={openTask}
                                title={dragHint} role="button" aria-label={t.title + ' — ' + dragHint}
                                style={{ position: 'absolute', top: '50%', left: clamp((dDay / SEASON_DAYS) * 100) + '%', transform: 'translate(-50%, -50%) rotate(45deg)', width: 11, height: 11, borderRadius: 2, cursor: grab, touchAction: 'none', zIndex: dragging ? 6 : 1,
                                  background: `color-mix(in srgb, ${tone.fg} 30%, transparent)`,
                                  border: `1px solid ${onCp ? tone.fg : `color-mix(in srgb, ${tone.fg} 60%, transparent)`}`,
                                  ...(dragging ? { boxShadow: `0 0 0 1px ${tone.fg}` } : {}) }} />
                            )}
                            {/* Where it will land, read off the drag itself —
                                the bar is often too narrow to hold a date, and
                                a marker has no room for one at all. */}
                            {dragLabel && (
                              <span style={{ position: 'absolute', top: 2, left: clamp(hasBar ? left : (dDay / SEASON_DAYS) * 100) + '%', fontFamily: MONO, fontSize: 9, letterSpacing: '0.04em', color: tone.fg, whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 7 }}>{dragLabel}</span>
                            )}
                            {overBudget && hasBar && <span style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: `calc(${clamp(left + width)}% + 8px)`, fontFamily: MONO, fontSize: 9, color: C.block, whiteSpace: 'nowrap' }}>{money(t.spent - t.budget)} over</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })}
              {tasks.length === 0 && <div style={{ padding: 24, fontSize: 13, color: C.faint }}>No diary tasks yet. Add one with the button above, or build the club's standing list in the Template library and generate a season from it.</div>}
            </div>
          </div>
        </div>
      )}

      {tab === 'templates' && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 340px', gap: 0, alignItems: 'start', minHeight: 0 }}>
          <div className="pb-scroll" style={{ padding: '18px 20px', overflowY: 'auto' }}>
            <div style={{ ...cap, marginBottom: 4 }}>TEMPLATE LIBRARY</div>
            {/* The template library has no button row of its own, so its box
                sits at the top of the list it narrows. Moving the season plan's
                search down beside its cadence buttons must not leave this tab
                with no search at all. */}
            <div style={{ marginBottom: 12 }}>
              <HeaderSearch value={st.diaryQuery} onChange={v => patch({ diaryQuery: v })}
                placeholder="Search the template library…" style={{ flex: '0 0 auto' }} />
            </div>
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
              addLabel="Add task" emptyText="No task definitions yet." query={q} />
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

      {adding && (
        <AddTaskModal
          categories={categories} roles={roles} seasonLabel={seasonLabel(seasonYear)}
          onCreateCategory={createCategory}
          onClose={() => setAdding(false)}
          onCreated={addTask} />
      )}
    </div>
  )
}
