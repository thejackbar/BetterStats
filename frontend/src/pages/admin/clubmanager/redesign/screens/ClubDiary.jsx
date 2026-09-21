import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import {
  C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, SegGroup, SegItem, StatReadout,
  Toast, Drawer, HEAD_SIDE, HEAD_CENTRE, HEAD_SIDE_END, HeaderSearch, matchesQuery,
  MenuButton, MenuItem, MenuHeading, MenuDivider, usePref,
} from '../ui'
import EntityManager from '../parts/EntityManager'
import DiaryGantt from '../../../../../components/admin/clubmanager/DiaryGantt'

// The Club Diary landing. Rebuilt (Sep 2026) from a single season-plan timeline
// into a workflow: an Overview that answers "where are we — what's late, what's
// due, who's holding it", then List / Calendar / Timeline / By-role readings of
// the SAME tasks, every one drilling into an actionable task drawer.
//
// The one relationship this screen exists to make visible: a diary task is owned
// by a COMMITTEE ROLE, which has a current HOLDER. The chain is
//   definition.responsibility_role_id  (the template says which seat owns it)
//     → occurrence.assigned_to_role_id  (copied onto each generated season task)
//       → committee_position.role_id    (the seat)
//         → its current term's holder    (the person)
// so every task carries `role → holder`, and the By-role view is the whole
// responsibility picture: each seat, its holder, and its load split by status.
//
// Two datasets, on purpose (see the plan): `board` is the always-populated
// current state (drives Overview + By-role + who-is-done, and is the only place
// STANDING duties live — weekly/matchday/ongoing generate no dated occurrence);
// `season/{year}` is the full-year set of dated occurrences (drives List /
// Calendar / Timeline, empty until a season is generated). Both are
// occurrence-based and share ids for the current period, so a drawer edit is
// consistent wherever the task appears.

// ─── Constants + small helpers (module scope, never re-declared in render) ───

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const CAD_ORDER = ['Annual', 'One-Time', 'Quarterly', 'Monthly', 'Weekly', 'Conditional', 'Other']
const STANDING = new Set(['weekly', 'matchday', 'ongoing'])
const DAY = 86400000

function mapFreq(f) {
  const m = { once: 'One-Time', one_time: 'One-Time', annual: 'Annual', yearly: 'Annual', quarterly: 'Quarterly', monthly: 'Monthly', weekly: 'Weekly', matchday: 'Weekly', ongoing: 'Other', conditional: 'Conditional', season_start: 'Annual', season_end: 'Annual' }
  return m[(f || '').toLowerCase()] || (f ? f[0].toUpperCase() + f.slice(1) : 'Other')
}

// Status is ALWAYS shown as a colour AND a word — never colour alone. Under
// protanopia this app's own green/amber separate by only ~7.2 ΔE, so the label
// carries the meaning and the colour reinforces it. `text` is the legible text
// tone (grey for "not started", whose accent grey is too pale to read as a word).
const TONE = {
  done: { fg: '#16c784', label: 'DONE', text: '#16c784' },
  open: { fg: 'var(--pb-accent)', label: 'IN PROGRESS', text: 'var(--pb-accent-ink, var(--pb-accent))' },
  overdue: { fg: '#ef5b5b', label: 'OVERDUE', text: '#ef5b5b' },
  blocked: { fg: '#ef5b5b', label: 'BLOCKED', text: '#ef5b5b' },
  upcoming: { fg: '#8a90a2', label: 'NOT STARTED', text: C.dim },
  recurs: { fg: '#06b6d4', label: 'ONGOING', text: '#06b6d4' },
}
const STATUS_ORDER = ['overdue', 'blocked', 'open', 'upcoming', 'recurs', 'done']

const money = (n) => '$' + Number(n || 0).toLocaleString('en-AU')
// A date-only ISO ("2026-09-01") parses as UTC midnight, and every cell
// timestamp below is built with Date.UTC too, so day placement never drifts by
// a timezone offset (an AU +08/+10 offset would otherwise push a task onto the
// previous day's cell). Times are ignored — the diary deals in whole dates.
const parseISO = (s) => (s ? Date.parse(String(s).slice(0, 10)) : null)
function fmtDate(iso) {
  const t = parseISO(iso)
  if (t == null) return ''
  const d = new Date(t)
  return d.getUTCDate() + ' ' + MONTH_ABBR[d.getUTCMonth()]
}
// Today's UTC-midnight instant, anchored to the viewer's LOCAL calendar date, so
// it lines up with the date-only due dates above.
const midnight = () => { const d = new Date(); return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) }

// The one status decision, shared by every view so no two disagree.
function statusOf({ raw, standing, blockers, due, pct, isLate }) {
  const r = (raw || '').toLowerCase()
  if (/done|complet/.test(r)) return 'done'
  if (standing) return 'recurs'
  if (blockers && blockers.length) return 'blocked'
  if (isLate === true || (due != null && parseISO(due) != null && parseISO(due) < midnight())) return 'overdue'
  if (r === 'in_progress' || (pct || 0) > 0) return 'open'
  return 'upcoming'
}

// The fill/border used for a bar or band. Blocked = hatched, overdue = solid +
// hard border, not-started = dashed outline, ongoing = dashed hatch, else a
// tinted fill. Category colour rides on the LEFT EDGE separately so the two
// signals (what kind of task / what state) don't fight.
function bandStyle(status) {
  const t = TONE[status] || TONE.upcoming
  const fg = t.fg
  if (status === 'blocked') return { background: `repeating-linear-gradient(45deg, color-mix(in srgb, ${fg} 22%, transparent) 0 5px, transparent 5px 10px)`, border: `1px solid ${fg}` }
  if (status === 'overdue') return { background: `color-mix(in srgb, ${fg} 26%, transparent)`, border: `1px solid ${fg}` }
  if (status === 'upcoming') return { background: 'transparent', border: `1px dashed color-mix(in srgb, ${fg} 60%, transparent)` }
  if (status === 'recurs') return { background: `repeating-linear-gradient(90deg, ${fg}44 0 6px, transparent 6px 12px)`, border: `1px dashed ${fg}66` }
  return { background: `color-mix(in srgb, ${fg} 22%, transparent)`, border: `1px solid color-mix(in srgb, ${fg} 50%, transparent)` }
}

const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8, textTransform: 'uppercase' }

// ─── Presentational atoms ────────────────────────────────────────────────────

function StatusDot({ status, size = 8 }) {
  const t = TONE[status] || TONE.upcoming
  const outline = status === 'upcoming'
  return <span style={{ width: size, height: size, borderRadius: '50%', flexShrink: 0, background: outline ? 'transparent' : t.fg, boxShadow: outline ? `inset 0 0 0 1.5px ${t.fg}` : undefined }} />
}

function StatusBadge({ status, small }) {
  const t = TONE[status] || TONE.upcoming
  return (
    <span data-testid="diary-status" data-status={status} style={{ fontFamily: MONO, fontSize: small ? 8.5 : 9, letterSpacing: '0.08em', padding: small ? '2px 5px' : '3px 7px', borderRadius: 4, border: `1px solid color-mix(in srgb, ${t.fg} 55%, transparent)`, color: t.text, whiteSpace: 'nowrap', flexShrink: 0 }}>{t.label}</span>
  )
}

// The legend, so the colours are readable rather than learned.
function StatusKey() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: '9px 20px', borderBottom: `1px solid ${C.hair}` }}>
      {STATUS_ORDER.map(s => (
        <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 20, height: 11, borderRadius: 3, ...bandStyle(s) }} />
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: TONE[s].text }}>{TONE[s].label}</span>
        </span>
      ))}
    </div>
  )
}

// "role → holder" — the responsibility line, drawn the same everywhere. A seat
// with no current holder reads VACANT (in red) rather than blank, because an
// owned-but-vacant task is exactly what a committee needs to notice.
function OwnerLine({ task, style }) {
  const role = task.roleLabel
  const holder = task.holder
  const person = task.person
  return (
    <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...style }}>
      {role || 'No role set'}
      {role && (holder || task.isCommitteeRole)
        ? <> → <span style={{ color: holder ? C.dim : C.block }}>{holder || 'VACANT'}</span></>
        : (person ? <> → <span style={{ color: C.dim }}>{person}</span></> : '')}
    </span>
  )
}

// ─── The model (pure) ────────────────────────────────────────────────────────

// Enrich one row (a board definition+occurrence, or a season occurrence) into
// the unified task the whole screen renders.
function enrich(row, isBoard, ctx) {
  const occ = isBoard ? (row.occurrence || {}) : row
  const defId = isBoard ? row.id : row.definition_id
  const occId = isBoard ? (row.occurrence?.id || null) : row.id
  const frequency = (row.frequency || '').toLowerCase()
  const standing = STANDING.has(frequency)
  const deps = (row.depends_on || []).filter(id => ctx.defById[id])
  const blockers = deps.filter(id => !ctx.doneByDef[id])
  const roleId = occ.assigned_to_role_id || (isBoard ? row.responsibility_role_id : null) || null
  const cm = roleId ? ctx.committeeByRole[roleId] : null
  const status = statusOf({ raw: occ.status, standing, blockers, due: occ.due_date, pct: occ.percent_complete, isLate: occ.is_late })
  return {
    key: occId || ('def:' + defId),
    defId, occId, standing,
    title: row.title,
    description: row.description || null,
    cadence: mapFreq(frequency),
    frequency,
    status,
    deps, blockers,
    roleId,
    roleLabel: cm?.name || ctx.roleTitle[roleId] || '',
    isCommitteeRole: !!cm,
    holder: cm?.holder || null,
    seatId: cm?.positionId || null,
    person: ctx.memberName[occ.assigned_to_member_id] || (isBoard ? ctx.memberName[row.default_assignee_member_id] : null) || null,
    start: occ.start_date || null,
    due: occ.due_date || null,
    pct: occ.percent_complete || 0,
    budget: occ.budget_estimate != null ? Number(occ.budget_estimate) : (isBoard && row.budget_estimate != null ? Number(row.budget_estimate) : 0),
    spent: occ.actual_expenditure != null ? Number(occ.actual_expenditure) : 0,
    categoryName: row.category_name || null,
    categoryColor: row.category_color || null,
    period: occ.period_label || null,
    rawStatus: occ.status || 'pending',
    memberId: occ.assigned_to_member_id || null,
  }
}

// ─── Screen ──────────────────────────────────────────────────────────────────

export default function ClubDiary({ st, patch, narrow }) {
  const tab = st.diaryTab || 'overview'
  const navigate = useNavigate()
  const [base, setBase] = useState(null)     // board + roles + members + positions + settings + years
  const [season, setSeason] = useState(null) // { year, tasks } | null (not loaded / none)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  // Per-person view prefs (survive a reload, keyed on the user).
  const [calZoom, setCalZoom] = usePref('diary_cal_zoom', 'month')
  const [calCursor, setCalCursor] = usePref('diary_cal_cursor', null) // {y, m} or null → derive
  const [collapsedCats, setCollapsedCats] = usePref('diary_list_collapsed', {})

  const q = (st.diaryQuery || '').trim()

  // The season we are IN (rolls at the club's diary-start month; 7/July default).
  const startMonth = base?.startMonth || 7
  const now = new Date()
  const currentSeasonYear = now.getMonth() >= (startMonth - 1) ? now.getFullYear() : now.getFullYear() - 1
  const selectedYear = st.diaryYear ?? currentSeasonYear

  // ── load ──
  const loadBase = useCallback(async () => {
    const [boardRes, settingsRes, rolesRes, membersRes, posRes, yearsRes] = await Promise.all([
      api.diaryBoard().catch(() => ({ tasks: [] })),
      api.adminGetSettings().catch(() => ({})),
      api.raRoles().catch(() => ({ roles: [] })),
      api.feeAllMembers().catch(() => ({ members: [] })),
      api.committeePositionsCurrent().catch(() => ({ positions: [] })),
      api.diarySeasonYears().catch(() => ({ years: [] })),
    ])
    // Guard with Array.isArray on BOTH shapes — `x?.key || x || []` returns the
    // object itself when x is a non-null object with no such key, and the next
    // `.map`/`.forEach` then throws and blanks the screen.
    const arr = (v, key) => (Array.isArray(v) ? v : (Array.isArray(v?.[key]) ? v[key] : []))
    const board = arr(boardRes, 'tasks')
    const roles = arr(rolesRes, 'roles')
    const members = arr(membersRes, 'members')
    const positions = arr(posRes, 'positions')
    const years = arr(yearsRes, 'years').map(Number).filter(Boolean)
    setBase({
      board, roles, members, positions, years,
      startMonth: Number(settingsRes?.diary_start_month) || 7,
    })
  }, [])

  const loadSeason = useCallback(async (year) => {
    const res = await api.diarySeasonPlan(year).catch(() => null)
    if (res && Array.isArray(res.tasks)) setSeason({ year, tasks: res.tasks })
    else setSeason({ year, tasks: [] })
  }, [])

  useEffect(() => { loadBase().catch(e => setErr(String(e?.message || e))) }, [loadBase])
  useEffect(() => { if (base) loadSeason(selectedYear) }, [base, selectedYear, loadSeason])

  const reload = useCallback(async () => { await Promise.all([loadBase(), loadSeason(selectedYear)]) }, [loadBase, loadSeason, selectedYear])

  // ── derive ──
  const model = useMemo(() => {
    if (!base) return null
    const roleTitle = {}, roleIsCommittee = {}
    base.roles.forEach(r => { roleTitle[r.id] = r.title; roleIsCommittee[r.id] = !!r.is_committee })
    const memberName = {}
    base.members.forEach(m => { memberName[m.member_id] = m.full_name })
    // roleId → { positionId, name, holder } — the committee-seat link.
    const committeeByRole = {}
    const seats = base.positions.map(p => {
      const holder = p.current_term?.holder_name || null
      if (p.role_id) committeeByRole[p.role_id] = { positionId: p.id, name: p.name, holder }
      return { id: p.id, roleId: p.role_id, name: p.name, holder, responsibilities: p.responsibilities || null }
    })
    // defById + doneByDef come from the board (all active definitions, incl.
    // standing; the current occurrence's done-state gates a dependant's blocker).
    const defById = {}, doneByDef = {}
    base.board.forEach(r => {
      defById[r.id] = { title: r.title, frequency: (r.frequency || '').toLowerCase() }
      doneByDef[r.id] = /done|complet/.test((r.occurrence?.status || '').toLowerCase())
    })
    const ctx = { defById, doneByDef, committeeByRole, roleTitle, memberName }
    const boardTasks = base.board.map(r => enrich(r, true, ctx))
    const seasonTasks = (season?.tasks || []).map(r => enrich(r, false, ctx))
    // dependents graph (definition level), for the drawer's "holds up".
    const dependentsByDef = {}
    boardTasks.forEach(t => t.deps.forEach(d => { (dependentsByDef[d] = dependentsByDef[d] || []).push(t.defId) }))
    // one canonical task per key for the drawer (season carries category + the
    // backend's is_late; board fills anything season lacks and adds standing).
    const taskByKey = {}
    seasonTasks.forEach(t => { taskByKey[t.key] = t })
    boardTasks.forEach(t => { if (!taskByKey[t.key]) taskByKey[t.key] = t })
    const boardByDef = {}; boardTasks.forEach(t => { boardByDef[t.defId] = t })
    return { seats, committeeByRole, roleTitle, roleIsCommittee, memberName, defById, boardTasks, seasonTasks, dependentsByDef, taskByKey, boardByDef }
  }, [base, season])

  const openTask = useCallback((key) => patch({ task: key }), [patch])

  // Occurrence write actions (drawer). After a change refetch both datasets so
  // every derived status / critical path recomputes.
  const saveOccurrence = useCallback(async (occId, fields) => {
    if (!occId) return
    setBusy(true)
    try { await api.diaryUpdateOccurrence(occId, fields); await reload() }
    catch { patch({ toast: { tone: 'block', title: 'Could not save the change.', body: 'Try again.' } }) }
    finally { setBusy(false) }
  }, [reload, patch])

  const generateSeason = useCallback(async (year) => {
    setBusy(true)
    try {
      await api.diaryGenerateSeason(year)
      await reload()
      patch({ toast: { tone: 'ok', title: `Generated the ${seasonLabel(year)} season.`, body: 'Every active template is now a dated task. You can edit the generated plan freely afterwards.' } })
    } catch { patch({ toast: { tone: 'block', title: 'Could not generate the season.', body: 'Check the diary configuration and try again.' } }) }
    finally { setBusy(false) }
  }, [reload, patch])

  // ── header ──
  // Called, never mounted, so its element types stay stable and the search box
  // below keeps focus per keystroke (the trap this screen already documents).
  const header = (children) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div style={HEAD_SIDE}>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Club Diary</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>WHERE THE CLUB IS: TASKS, DEADLINES, WHO'S RESPONSIBLE</Caption>
      </div>
      <div style={HEAD_CENTRE}>
        <SegTabs value={tab === 'templates' ? '' : tab} onChange={t => patch({ diaryTab: t })}
          tabs={[
            { key: 'overview', label: 'Overview' },
            { key: 'list', label: 'List' },
            { key: 'calendar', label: 'Calendar' },
            { key: 'timeline', label: 'Timeline' },
            { key: 'roles', label: 'By role' },
          ]} />
      </div>
      <div style={HEAD_SIDE_END}>
        {children}
      </div>
    </ScreenHeader>
  )

  if (!model) {
    return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>{header()}<div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load the club diary.' : 'Loading the club diary…'}</div></div>
  }

  const { boardTasks } = model
  const T = midnight()
  const dated = boardTasks.filter(t => !t.standing)
  const overdueNow = dated.filter(t => t.status === 'overdue')
  const dueThisWeek = dated.filter(t => t.status !== 'done' && withinDays(t.due, 7, T))

  // The right side of every header is IDENTICAL across every view — the two
  // figures a committee glances at, then the Setup menu (templates/season-setup,
  // off the day-to-day path but one click away). The season selector is
  // deliberately NOT here: it belongs to the three date views that it scopes and
  // lives in each of their own toolbars (`SeasonSelect`). Keeping the header's
  // right cluster the same everywhere is what stops List/Calendar/Timeline
  // wrapping it onto a second row and dropping the title/tabs out of line with
  // Overview and By-role.
  const rightSide = (
    <>
      <StatReadout value={String(overdueNow.length)} label="OVERDUE" fg={overdueNow.length ? C.block : C.ok} />
      <StatReadout value={String(dueThisWeek.length)} label="DUE THIS WEEK" fg={dueThisWeek.length ? C.warn : C.ok} />
      <MenuButton label="Setup" width={230} align="right">
        {(close) => (
          <>
            <MenuHeading>SEASON SETUP</MenuHeading>
            <MenuItem onClick={() => { patch({ diaryTab: 'templates', diaryTemplatesFocus: 'library' }); close() }}>Task templates</MenuItem>
            <MenuItem onClick={() => { patch({ diaryTab: 'templates', diaryTemplatesFocus: 'generate' }); close() }}>Generate a season…</MenuItem>
            <MenuDivider />
            <MenuItem onClick={() => { navigate('/admin/clubhouse/diary/manage'); close() }}>Full diary editor ↗</MenuItem>
          </>
        )}
      </MenuButton>
    </>
  )

  const ctxView = { model, patch, openTask, T, selectedYear, calZoom, setCalZoom, calCursor, setCalCursor, collapsedCats, setCollapsedCats, q, rawQuery: st.diaryQuery, base, currentSeasonYear, generateSeason, season, busy, startMonth }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {header(rightSide)}
      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {tab === 'overview' && <OverviewView v={ctxView} st={st} />}
      {tab === 'list' && <ListView v={ctxView} st={st} />}
      {tab === 'calendar' && <CalendarView v={ctxView} />}
      {tab === 'timeline' && <TimelineView v={ctxView} />}
      {tab === 'roles' && <RolesView v={ctxView} />}
      {tab === 'templates' && <TemplatesView v={ctxView} focus={st.diaryTemplatesFocus} />}

      {st.task && model.taskByKey[st.task] && (
        <TaskDrawer task={model.taskByKey[st.task]} model={model} base={base} busy={busy}
          onClose={() => patch({ task: null })} onOpen={openTask} onSave={saveOccurrence}
          onManage={() => navigate('/admin/clubhouse/diary/manage')} />
      )}
    </div>
  )
}

// ─── Overview: where are we ──────────────────────────────────────────────────

function OverviewView({ v, st }) {
  const { model, openTask, T, patch } = v
  const dated = model.boardTasks.filter(t => !t.standing)
  const standing = model.boardTasks.filter(t => t.standing)
  const overdue = dated.filter(t => t.status === 'overdue')
  const blocked = dated.filter(t => t.status === 'blocked')
  const attention = overdue.concat(blocked)
  const doneCount = dated.filter(t => t.status === 'done').length
  const budget = dated.reduce((a, t) => a + t.budget, 0)
  const spent = dated.reduce((a, t) => a + t.spent, 0)

  const upTo = st.diaryUpTo || 'month'
  const upDays = upTo === 'week' ? 7 : upTo === 'month' ? 31 : 90
  const coming = dated
    .filter(t => t.status !== 'done' && t.status !== 'overdue' && withinDays(t.due, upDays, T))
    .sort((a, b) => (parseISO(a.due) || 0) - (parseISO(b.due) || 0))

  // Per committee-seat load, so "who is carrying what" is on the landing itself.
  const seatLoad = seatLoads(model)

  const tiles = [
    { label: 'OVERDUE', value: overdue.length, fg: overdue.length ? C.block : C.ok },
    { label: 'BLOCKED', value: blocked.length, fg: blocked.length ? C.block : C.ok },
    { label: 'DUE THIS MONTH', value: dated.filter(t => t.status !== 'done' && withinDays(t.due, 31, T)).length, fg: C.warn },
    { label: 'ON TRACK', value: `${doneCount}/${dated.length}`, fg: C.ok },
    { label: 'SPENT / BUDGET', value: `${money(spent)} / ${money(budget)}`, fg: spent > budget && budget > 0 ? C.block : C.text },
  ]

  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* stat tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        {tiles.map((s, i) => (
          <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 10, padding: '13px 15px' }}>
            <div style={{ fontWeight: 700, fontSize: 22, fontVariantNumeric: 'tabular-nums', color: s.fg }}>{s.value}</div>
            <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.12em', color: C.faint, marginTop: 3 }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18, alignItems: 'start' }}>
        {/* needs attention now */}
        <section>
          <div style={cap}>NEEDS ATTENTION NOW</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {attention.length === 0 && <Empty>Nothing overdue or blocked. The diary is on track.</Empty>}
            {attention.map(t => {
              const holds = (model.dependentsByDef[t.defId] || []).map(id => model.boardByDef[id]).filter(x => x && x.status !== 'done')
              return (
                <button key={t.key} data-testid="diary-attn" onClick={() => openTask(t.key)} style={attnRow}>
                  <StatusDot status={t.status} />
                  <div style={{ minWidth: 0, textAlign: 'left', flex: 1 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.title}</div>
                    <div style={{ marginTop: 3, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <OwnerLine task={t} />
                      {t.due && t.status === 'overdue' && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.block }}>was due {fmtDate(t.due)}</span>}
                      {holds.length > 0 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>holds up {holds.map(x => x.title).join(', ')}</span>}
                    </div>
                  </div>
                  <StatusBadge status={t.status} small />
                </button>
              )
            })}
          </div>
        </section>

        {/* coming up */}
        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 10, flexWrap: 'wrap' }}>
            <div style={{ ...cap, marginBottom: 0 }}>COMING UP</div>
            <SegGroup>
              {[['week', 'This week'], ['month', 'This month'], ['quarter', 'Next 90 days']].map(([k, l]) => (
                <SegItem key={k} active={upTo === k} onClick={() => patch({ diaryUpTo: k })}>{l}</SegItem>
              ))}
            </SegGroup>
          </div>
          <div data-testid="diary-coming" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {coming.length === 0 && <Empty>Nothing due in this window.</Empty>}
            {coming.map(t => (
              <button key={t.key} data-testid="diary-coming-row" onClick={() => openTask(t.key)} style={comingRow}>
                <div style={{ width: 44, flexShrink: 0, textAlign: 'center' }}>
                  <div style={{ fontWeight: 700, fontSize: 15, color: C.text, lineHeight: 1 }}>{t.due ? new Date(parseISO(t.due)).getUTCDate() : '—'}</div>
                  <div style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.1em', color: C.faint }}>{t.due ? MONTH_ABBR[new Date(parseISO(t.due)).getUTCMonth()].toUpperCase() : ''}</div>
                </div>
                <div style={{ width: 1, alignSelf: 'stretch', background: C.hair }} />
                <div style={{ minWidth: 0, textAlign: 'left', flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.title}</div>
                  <OwnerLine task={t} style={{ marginTop: 2 }} />
                </div>
                <StatusBadge status={t.status} small />
              </button>
            ))}
          </div>
        </section>
      </div>

      {/* who's responsible — committee seat load, links into By role */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 10 }}>
          <div style={{ ...cap, marginBottom: 0 }}>WHO'S RESPONSIBLE</div>
          <button onClick={() => patch({ diaryTab: 'roles' })} style={linkBtn}>Open By role →</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 10 }}>
          {seatLoad.filter(s => s.total > 0).slice(0, 8).map(s => (
            <button key={s.id} onClick={() => patch({ diaryTab: 'roles' })} style={seatChip}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.name}</span>
                <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{s.total}</span>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, color: s.holder ? C.dim : C.block, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.holder || 'VACANT'}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                {s.late > 0 && <MiniStat n={s.late} label="late" fg={C.block} />}
                {s.open > 0 && <MiniStat n={s.open} label="in prog" fg={'var(--pb-accent)'} />}
                {s.upcoming > 0 && <MiniStat n={s.upcoming} label="upcoming" fg={C.dim} />}
              </div>
            </button>
          ))}
          {seatLoad.filter(s => s.total > 0).length === 0 && <Empty>No committee seats own diary tasks yet. Set an owner role on your task templates.</Empty>}
        </div>
      </section>

      {standing.length > 0 && (
        <section>
          <div style={cap}>ONGOING DUTIES</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {standing.map(t => (
              <button key={t.key} onClick={() => openTask(t.key)} style={ongoingChip}>
                <StatusDot status="recurs" size={7} />
                <span style={{ fontSize: 12.5, color: C.text }}>{t.title}</span>
                <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{t.roleLabel || 'Unassigned'}{t.holder ? ' · ' + t.holder : ''}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function MiniStat({ n, label, fg }) {
  return <span style={{ fontFamily: MONO, fontSize: 9, color: fg }}>{n} <span style={{ color: C.faint }}>{label}</span></span>
}

// ─── List ────────────────────────────────────────────────────────────────────

function ListView({ v, st }) {
  const { model, openTask, patch, q, season, selectedYear, currentSeasonYear, generateSeason, busy, collapsedCats, setCollapsedCats } = v
  const catFilter = st.diaryCatFilter || 'All'
  const statusFilter = st.diaryStatusFilter || 'All'
  const loading = !season

  const standing = model.boardTasks.filter(t => t.standing)
  const dated = model.seasonTasks

  const cats = ['All'].concat(Array.from(new Set(dated.map(t => t.cadence))).sort((a, b) => CAD_ORDER.indexOf(a) - CAD_ORDER.indexOf(b)))
  const matchTask = (t) => {
    if (catFilter !== 'All' && t.cadence !== catFilter) return false
    if (statusFilter !== 'All' && !statusMatches(statusFilter, t.status)) return false
    return matchesQuery(q, t.title, t.cadence, t.roleLabel, t.holder, t.person, t.categoryName)
  }
  const rows = dated.filter(matchTask).sort((a, b) => (parseISO(a.due) || 8e15) - (parseISO(b.due) || 8e15))
  const standingRows = standing.filter(t => (catFilter === 'All' || t.cadence === catFilter) && (statusFilter === 'All' || statusMatches(statusFilter, 'recurs')) && matchesQuery(q, t.title, t.roleLabel, t.holder, t.person))

  const empty = dated.length === 0

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <StatusKey />
      <div style={{ padding: '11px 20px', borderBottom: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', alignSelf: 'stretch' }}>
          <SegTabs value={catFilter} onChange={c => patch({ diaryCatFilter: c })} tabs={cats.map(c => ({ key: c, label: c }))} />
          <MenuButton label="Status" value={statusFilter === 'All' ? '' : (TONE[statusFilter]?.label || statusFilter)} width={200} seg>
            {(close) => (
              <>
                {[['All', 'All statuses']].concat(STATUS_ORDER.map(s => [s, TONE[s].label])).map(([k, l]) => (
                  <MenuItem key={k} on={statusFilter === k} onClick={() => { patch({ diaryStatusFilter: k }); close() }}>{l}</MenuItem>
                ))}
              </>
            )}
          </MenuButton>
          <div style={{ marginLeft: 'auto' }}><SeasonSelect v={v} /></div>
        </div>
        <HeaderSearch value={st.diaryQuery} onChange={val => patch({ diaryQuery: val })}
          placeholder="Search tasks, roles and who's responsible…" style={{ flex: '0 0 auto' }} />
      </div>

      <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading the {seasonLabel(selectedYear)} season…</div>
        ) : empty ? (
          <SeasonEmpty year={selectedYear} current={currentSeasonYear} onGenerate={generateSeason} busy={busy} />
        ) : (
          <div style={{ minWidth: 720 }}>
            <div style={listHeadRow}>
              <div>TASK</div><div>CADENCE</div><div>OWNER → HOLDER</div><div>DUE</div><div style={{ textAlign: 'right' }}>BUDGET</div><div style={{ textAlign: 'right' }}>STATUS</div>
            </div>
            {rows.map(t => <ListRow key={t.key} t={t} active={st.task === t.key} onClick={() => openTask(t.key)} />)}
            {rows.length === 0 && <div style={{ padding: 20, fontSize: 13, color: C.faint }}>No tasks match these filters.</div>}
            {standingRows.length > 0 && (
              <>
                <div onClick={() => setCollapsedCats({ ...collapsedCats, ongoing: !collapsedCats.ongoing })} style={groupHead}>
                  <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{collapsedCats.ongoing ? '▸' : '▾'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim }}>ONGOING DUTIES</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest }}>{standingRows.length} · not dated, they recur continuously</span>
                </div>
                {!collapsedCats.ongoing && standingRows.map(t => <ListRow key={t.key} t={t} active={st.task === t.key} onClick={() => openTask(t.key)} ongoing />)}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ListRow({ t, active, onClick, ongoing }) {
  return (
    <div data-testid="diary-list-row" data-status={t.status} onClick={onClick} style={{ ...listRow, background: active ? 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' : 'transparent', cursor: 'pointer' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
        <StatusDot status={t.status} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: t.status === 'done' ? C.dim : C.text, textDecoration: t.status === 'done' ? 'line-through' : undefined, textDecorationColor: C.faintest, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.title}</div>
          {t.categoryName && <div style={{ fontFamily: MONO, fontSize: 9, color: C.faintest, marginTop: 1 }}>{t.categoryName}</div>}
        </div>
      </div>
      <div style={{ fontSize: 12, color: C.dim }}>{t.cadence}</div>
      <div style={{ minWidth: 0 }}><OwnerLine task={t} /></div>
      <div style={{ fontSize: 12, color: t.status === 'overdue' ? C.block : C.dim }}>{ongoing ? '—' : (t.due ? fmtDate(t.due) : '—')}</div>
      <div style={{ fontSize: 12, textAlign: 'right', color: t.spent > t.budget && t.budget > 0 ? C.block : C.dim }}>{t.budget ? money(t.spent) + '/' + money(t.budget) : '—'}</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}><StatusBadge status={t.status} small /></div>
    </div>
  )
}

// ─── Calendar (zoomable date-grid; tasks span cells) ─────────────────────────

function CalendarView({ v }) {
  const { model, openTask, selectedYear, calZoom, setCalZoom, calCursor, setCalCursor, currentSeasonYear, generateSeason, busy, T, season } = v
  const tasks = model.seasonTasks.filter(t => t.due) // a calendar needs a date
  const loading = !season
  const empty = model.seasonTasks.length === 0

  // Which month the Month view shows: the stored cursor, else the current month
  // if we're viewing this season, else January of the selected year.
  const cursor = calCursor && calCursor.y === selectedYear
    ? calCursor
    : { y: selectedYear, m: selectedYear === currentSeasonYear ? new Date().getMonth() : 0 }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px', borderBottom: `1px solid ${C.hair}`, flexWrap: 'wrap' }}>
        <SegGroup>
          <SegItem active={calZoom === 'year'} onClick={() => setCalZoom('year')}>Year</SegItem>
          <SegItem active={calZoom === 'month'} onClick={() => setCalZoom('month')}>Month</SegItem>
        </SegGroup>
        {calZoom === 'month' && !empty && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => setCalCursor(stepMonth(cursor, -1))} style={navBtn}>‹</button>
            <span style={{ fontSize: 13, fontWeight: 600, color: C.text, minWidth: 96, textAlign: 'center' }}>{MONTH_ABBR[cursor.m]} {cursor.y}</span>
            <button onClick={() => setCalCursor(stepMonth(cursor, 1))} style={navBtn}>›</button>
          </div>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <SeasonSelect v={v} />
          <StatusMiniKey />
        </div>
      </div>
      {loading ? (
        <div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading the {seasonLabel(selectedYear)} season…</div>
      ) : empty ? (
        <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
          <SeasonEmpty year={selectedYear} current={currentSeasonYear} onGenerate={generateSeason} busy={busy} />
        </div>
      ) : calZoom === 'year' ? (
        <YearCalendar tasks={tasks} year={selectedYear} onOpen={openTask} onPickMonth={(m) => { setCalCursor({ y: selectedYear, m }); setCalZoom('month') }} T={T} />
      ) : (
        <MonthCalendar tasks={tasks} year={cursor.y} monthIdx={cursor.m} onOpen={openTask} T={T} />
      )}
    </div>
  )
}

function StatusMiniKey() {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      {['overdue', 'open', 'upcoming', 'done'].map(s => (
        <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 12, height: 8, borderRadius: 2, ...bandStyle(s) }} />
          <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', color: TONE[s].text }}>{TONE[s].label}</span>
        </span>
      ))}
    </div>
  )
}

// Year: 12 month cells; a task appears in every month its start→due window
// covers, so a task genuinely SPANS cells at this zoom.
function YearCalendar({ tasks, year, onOpen, onPickMonth, T }) {
  const byMonth = Array.from({ length: 12 }, () => [])
  tasks.forEach(t => {
    const due = parseISO(t.due), start = parseISO(t.start) || due
    const lo = new Date(Math.min(start, due)), hi = new Date(Math.max(start, due))
    for (let m = 0; m < 12; m++) {
      const mStart = Date.UTC(year, m, 1), mEnd = Date.UTC(year, m + 1, 0, 23, 59)
      if (hi.getTime() >= mStart && lo.getTime() <= mEnd) byMonth[m].push(t)
    }
  })
  const nowM = new Date().getMonth(), nowY = new Date().getFullYear()
  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 12 }}>
        {Array.from({ length: 12 }, (_, m) => {
          const items = byMonth[m].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status))
          const isNow = m === nowM && year === nowY
          return (
            <div key={m} style={{ background: C.surface, border: `1px solid ${isNow ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair}`, borderRadius: 10, overflow: 'hidden' }}>
              <button onClick={() => onPickMonth(m)} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: C.surface2, border: 'none', borderBottom: `1px solid ${C.hair}`, cursor: 'pointer' }}>
                <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.12em', color: isNow ? C.accent : C.dim }}>{MONTH_ABBR[m].toUpperCase()} {String(year).slice(2)}</span>
                <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{items.length || ''}</span>
              </button>
              <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 5, minHeight: 40 }}>
                {items.length === 0 && <span style={{ fontSize: 11.5, color: C.faintest }}>—</span>}
                {items.map(t => (
                  <button key={t.key} data-testid="diary-cal-year-band" data-status={t.status} onClick={() => onOpen(t.key)} title={t.title} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 8px', borderRadius: 6, cursor: 'pointer', textAlign: 'left', ...bandStyle(t.status) }}>
                    {t.categoryColor && <span style={{ width: 3, alignSelf: 'stretch', borderRadius: 2, background: t.categoryColor, flexShrink: 0 }} />}
                    <span style={{ fontSize: 11.5, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0, flex: 1 }}>{t.title}</span>
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Month: a real week×day grid where a task with a multi-day window renders as a
// horizontal band spanning the day cells it covers (clipped to the week), lanes
// stacked so overlapping tasks don't collide. Weeks start Monday.
function MonthCalendar({ tasks, year, monthIdx, onOpen, T }) {
  const weeks = weeksOfMonth(year, monthIdx)
  const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const LANE_H = 20, LANE_TOP = 26, MAX_LANES = 3
  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: 16 }}>
      <div style={{ minWidth: 640, border: `1px solid ${C.hair}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', background: C.surface2 }}>
          {DOW.map(d => <div key={d} style={{ padding: '7px 8px', fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, borderRight: `1px solid ${C.hair}` }}>{d.toUpperCase()}</div>)}
        </div>
        {weeks.map((week, wi) => {
          const wStart = week[0].t, wEnd = week[6].t + DAY - 1
          // pack overlapping tasks into lanes for this week
          const inWeek = tasks.filter(t => {
            const due = parseISO(t.due), start = parseISO(t.start) || due
            return Math.max(start, wStart) <= Math.min(Math.max(start, due), wEnd)
          })
          const lanes = packLanes(inWeek, wStart, wEnd)
          const rowH = LANE_TOP + Math.min(MAX_LANES, lanes.length) * LANE_H + 6
          return (
            <div key={wi} style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', borderTop: `1px solid ${C.hair}`, minHeight: rowH }}>
              {week.map((day, di) => {
                const isToday = sameDay(day.t, T)
                return (
                  <div key={di} style={{ borderRight: `1px solid ${C.hair}`, padding: 5, background: day.inMonth ? 'transparent' : 'color-mix(in srgb, var(--pb-faintest) 6%, transparent)' }}>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: isToday ? C.accent : (day.inMonth ? C.dim : C.faintest), fontWeight: isToday ? 700 : 400 }}>{new Date(day.t).getUTCDate()}</span>
                  </div>
                )
              })}
              {lanes.slice(0, MAX_LANES).map((lane, li) => lane.map(seg => {
                const left = (seg.from / 7) * 100, width = ((seg.to - seg.from + 1) / 7) * 100
                return (
                  <button key={seg.t.key} data-testid="diary-cal-band" data-span={seg.to - seg.from + 1} data-status={seg.t.status} onClick={() => onOpen(seg.t.key)} title={seg.t.title}
                    style={{ position: 'absolute', left: `calc(${left}% + 3px)`, width: `calc(${width}% - 6px)`, top: LANE_TOP + li * LANE_H, height: LANE_H - 4, display: 'flex', alignItems: 'center', gap: 5, padding: '0 6px', borderRadius: 5, cursor: 'pointer', overflow: 'hidden', ...bandStyle(seg.t.status) }}>
                    {seg.t.categoryColor && <span style={{ width: 3, height: 10, borderRadius: 2, background: seg.t.categoryColor, flexShrink: 0 }} />}
                    <span style={{ fontSize: 11, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{seg.t.title}</span>
                  </button>
                )
              }))}
              {lanes.length > MAX_LANES && (
                <span style={{ position: 'absolute', right: 6, top: LANE_TOP + MAX_LANES * LANE_H, fontFamily: MONO, fontSize: 9, color: C.faint }}>+{lanes.length - MAX_LANES} more</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Timeline (reuses the existing Gantt: bars + dependency links + zoom) ─────

function TimelineView({ v }) {
  const { season, selectedYear, currentSeasonYear, generateSeason, busy, openTask, model } = v
  const empty = !season || season.tasks.length === 0
  const cp = criticalPath(model.seasonTasks, model)
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', borderBottom: `1px solid ${C.hair}`, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <SeasonSelect v={v} />
      </div>
      <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {empty ? (
          <SeasonEmpty year={selectedYear} current={currentSeasonYear} onGenerate={generateSeason} busy={busy} />
        ) : (
          <>
            {cp.path.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={cap}>CRITICAL PATH · {cp.len} days of chained work</div>
                <div style={{ fontSize: 13, color: C.text, lineHeight: 1.5, background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', borderRadius: 8, padding: '10px 12px' }}>
                  {cp.path.map(id => model.defById[id]?.title || '?').join('  →  ')}
                </div>
              </div>
            )}
            <DiaryGantt tasks={season.tasks} year={selectedYear} onTaskClick={(occId) => openTask(occId)} />
          </>
        )}
      </div>
    </div>
  )
}

// ─── By role (the responsibility perspective) ────────────────────────────────

function RolesView({ v }) {
  const { model, openTask, patch } = v
  const seats = seatDetail(model) // [{id, name, holder, responsibilities, tasks[]}]
  const withTasks = seats.filter(s => s.tasks.length > 0)
  // Only the dated diary tasks belong here. A STANDING duty (weekly/matchday/
  // ongoing) is a perpetual responsibility, not something in the season's diary
  // with a deadline and a status — it reads as the seat's job description rather
  // than work to track, so it is confined to the Overview's "ongoing duties"
  // strip and excluded from every seat's task list here.
  const other = model.boardTasks.filter(t => !t.standing && !t.seatId) // no committee seat
  const nonCommittee = other.filter(t => t.roleId)
  const unassigned = other.filter(t => !t.roleId)

  const grp = (tasks) => {
    const g = { overdue: [], blocked: [], open: [], upcoming: [], recurs: [], done: [] }
    tasks.forEach(t => (g[t.status] || g.upcoming).push(t))
    return g
  }

  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 12.5, color: C.dim, lineHeight: 1.5, maxWidth: 760 }}>
        Every diary task is owned by a committee role, set on its template. This is that ownership made visible: each seat, who currently holds it, and the tasks they're carrying. A seat with tasks but <span style={{ color: C.block }}>no current holder</span> is work nobody has picked up.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14, alignItems: 'start' }}>
        {withTasks.map(s => <SeatCard key={s.id} seat={s} onOpen={openTask} groups={grp(s.tasks)} />)}
        {nonCommittee.length > 0 && <SeatCard key="__nc" seat={{ name: 'Other roles (not on the committee)', holder: null, responsibilities: null, tasks: nonCommittee, notCommittee: true }} onOpen={openTask} groups={grp(nonCommittee)} />}
        {unassigned.length > 0 && <SeatCard key="__un" seat={{ name: 'Unassigned', holder: null, responsibilities: 'These tasks have no owner role. Set one on the template so a committee seat is responsible.', tasks: unassigned, unassigned: true }} onOpen={openTask} groups={grp(unassigned)} />}
      </div>
      {withTasks.length === 0 && nonCommittee.length === 0 && unassigned.length === 0 && <Empty>No diary tasks yet.</Empty>}
      {seats.filter(s => s.tasks.length === 0).length > 0 && (
        <div>
          <div style={cap}>SEATS WITH NO DIARY TASKS</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {seats.filter(s => s.tasks.length === 0).map(s => (
              <span key={s.id} style={{ ...ongoingChip, cursor: 'default' }}>
                <span style={{ fontSize: 12.5, color: C.dim }}>{s.name}</span>
                <span style={{ fontFamily: MONO, fontSize: 9, color: s.holder ? C.faint : C.block }}>{s.holder || 'VACANT'}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SeatCard({ seat, onOpen, groups }) {
  const late = groups.overdue.length + groups.blocked.length
  const total = seat.tasks.length
  const border = late > 0 ? 'rgba(239,91,91,0.35)' : C.hair
  const vacant = !seat.holder && !seat.notCommittee && !seat.unassigned
  return (
    <div data-testid="diary-seat" data-vacant={vacant ? '1' : '0'} data-late={late} data-tasks={total} style={{ background: C.surface, border: `1px solid ${border}`, borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ padding: '12px 14px', borderBottom: `1px solid ${C.hair}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
          <span style={{ fontSize: 14.5, fontWeight: 700, color: C.text }}>{seat.name}</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{total} task{total === 1 ? '' : 's'}</span>
        </div>
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {!seat.notCommittee && !seat.unassigned && (
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.05em', color: seat.holder ? C.dim : C.block }}>{seat.holder ? '● ' + seat.holder : '○ VACANT: nobody holds this seat'}</span>
          )}
          {late > 0 && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 4, background: 'rgba(239,91,91,0.15)', color: C.block }}>{late} NEED{late === 1 ? 'S' : ''} ATTENTION</span>}
        </div>
        {seat.responsibilities && <div style={{ fontSize: 11.5, color: C.faint, marginTop: 6, lineHeight: 1.45 }}>{seat.responsibilities}</div>}
      </div>
      <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
        {STATUS_ORDER.filter(s => groups[s]?.length).map(s => groups[s].map(t => (
          <button key={t.key} onClick={() => onOpen(t.key)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 9px', borderRadius: 7, border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', width: '100%' }}
            onMouseEnter={e => { e.currentTarget.style.background = C.surface2 }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
            <StatusDot status={t.status} />
            <span style={{ fontSize: 13, color: t.status === 'done' ? C.dim : C.text, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: t.status === 'done' ? 'line-through' : undefined, textDecorationColor: C.faintest }}>{t.title}</span>
            {t.due && !t.standing && <span style={{ fontFamily: MONO, fontSize: 9.5, color: t.status === 'overdue' ? C.block : C.faint }}>{fmtDate(t.due)}</span>}
            <StatusBadge status={t.status} small />
          </button>
        )))}
      </div>
    </div>
  )
}

// ─── Templates & season setup (secondary — off the day-to-day path) ──────────

function TemplatesView({ v }) {
  const { model, base, patch, q, rawQuery, currentSeasonYear, generateSeason, busy } = v
  const roleName = model.roleTitle
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '11px 20px', borderBottom: `1px solid ${C.hair}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={() => patch({ diaryTab: 'overview' })} style={linkBtn}>← Back to diary</button>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.12em', color: C.faintest }}>TEMPLATES &amp; SEASON SETUP · edit before a new season, or when a new annual task appears</span>
      </div>
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 340px', gap: 0, alignItems: 'start', minHeight: 0 }}>
        <div className="pb-scroll" style={{ padding: '18px 20px', overflowY: 'auto' }}>
          <div style={{ ...cap, marginBottom: 4 }}>TASK TEMPLATES</div>
          <div style={{ marginBottom: 12 }}>
            <HeaderSearch value={rawQuery} onChange={val => patch({ diaryQuery: val })} placeholder="Search the templates…" style={{ flex: '0 0 auto' }} />
          </div>
          <EntityManager
            describe="Your club's standing obligations: what has to happen every season and which committee seat owns it. Edit here, and every season you generate inherits it. This is set-and-forget, so you shouldn't need it week to week."
            load={() => api.diaryListDefinitions().then(r => r?.definitions || r || [])}
            fields={[
              { key: 'title', label: 'Task', type: 'text', required: true, span: 2 },
              { key: 'frequency', label: 'Cadence', type: 'select', required: true, options: [{ value: 'annual', label: 'Annual' }, { value: 'once', label: 'One-time' }, { value: 'quarterly', label: 'Quarterly' }, { value: 'monthly', label: 'Monthly' }, { value: 'weekly', label: 'Weekly' }, { value: 'conditional', label: 'Conditional' }] },
              { key: 'responsibility_role_id', label: 'Owner role (committee seat)', type: 'select', options: Object.entries(roleName).map(([id, title]) => ({ value: id, label: title })) },
              { key: 'default_month', label: 'Month (1-12)', type: 'number' },
              { key: 'budget_estimate', label: 'Budget ($)', type: 'number' },
              { key: 'description', label: 'Notes', type: 'text', span: 2 },
            ]}
            onCreate={val => api.diaryCreateDefinition(val)} onUpdate={(id, val) => api.diaryUpdateDefinition(id, val)} onDelete={id => api.diaryArchiveDefinition(id)}
            seed={{ label: 'Add Club Diary Starter Pack', fn: () => api.diarySeedStarterDefinitions() }}
            primaryKey="title"
            subtitle={it => [mapFreq(it.frequency), roleName[it.responsibility_role_id], it.budget_estimate ? money(it.budget_estimate) : null].filter(Boolean).join(' · ')}
            addLabel="Add task" emptyText="No task templates yet." query={q} />
        </div>
        <div className="pb-scroll" style={{ borderLeft: `1px solid ${C.hair}`, background: C.surface, padding: '18px 16px', overflowY: 'auto', alignSelf: 'stretch' }}>
          <div style={cap}>GENERATE A SEASON</div>
          <p style={{ fontSize: 12.5, color: C.dim, margin: '0 0 12px', lineHeight: 1.5 }}>Turns every active template into dated tasks for the season you pick, with each task's owner role carried across. You can edit the plan freely afterwards.</p>
          <GenerateSeason base={base} current={currentSeasonYear} onGenerate={generateSeason} busy={busy} />
        </div>
      </div>
    </div>
  )
}

function GenerateSeason({ base, current, onGenerate, busy }) {
  const [year, setYear] = useState(() => {
    let y = current
    while ((base.years || []).includes(y)) y += 1
    return y
  })
  return (
    <>
      <select value={year} onChange={e => setYear(Number(e.target.value))} style={{ ...selStyle, width: '100%', marginBottom: 8 }}>
        {[current - 1, current, current + 1, current + 2].map(y => (
          <option key={y} value={y}>{seasonLabel(y)}{(base.years || []).includes(y) ? ' · already generated' : ''}</option>
        ))}
      </select>
      <button disabled={busy} onClick={() => onGenerate(year)} style={{ width: '100%', padding: '9px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: 'var(--pb-on-accent, #0a0d14)', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1 }}>Generate {seasonLabel(year)}</button>
      {(base.years || []).includes(year) && <p style={{ fontSize: 11.5, color: C.warn, margin: '8px 0 0', lineHeight: 1.5 }}>{seasonLabel(year)} already has a plan. Generating again tops it up from your templates rather than starting over.</p>}
    </>
  )
}

// ─── Task drawer (actionable) ────────────────────────────────────────────────

function TaskDrawer({ task, model, base, busy, onClose, onOpen, onSave, onManage }) {
  const t = task
  const up = t.deps.map(id => model.boardByDef[id]).filter(Boolean)
  const down = (model.dependentsByDef[t.defId] || []).map(id => model.boardByDef[id]).filter(Boolean)
  const dcap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8, textTransform: 'uppercase' }
  const canEdit = !!t.occId // a standing duty has no occurrence to track

  const set = (fields) => onSave(t.occId, fields)

  return (
    <Drawer width={460} zIndex={90} onClose={onClose}>
     <div data-testid="diary-drawer" data-status={t.status}>
      <div style={{ padding: 20, borderBottom: `1px solid ${C.hair}` }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 17, lineHeight: 1.3 }}>{t.title}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
              <StatusBadge status={t.status} />
              <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{t.cadence}</span>
            </div>
          </div>
          <span style={{ cursor: 'pointer', color: C.faint, fontSize: 16 }} onClick={onClose}>✕</span>
        </div>
      </div>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* responsibility — the committee-seat link */}
        <div>
          <div style={dcap}>RESPONSIBLE</div>
          <div style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 13, color: C.text }}>{t.roleLabel || 'No owner role set'}</div>
            {t.isCommitteeRole
              ? <div style={{ fontFamily: MONO, fontSize: 10, marginTop: 3, color: t.holder ? C.dim : C.block }}>{t.holder ? 'held by ' + t.holder : 'VACANT: this seat has no current holder'}</div>
              : (t.person ? <div style={{ fontFamily: MONO, fontSize: 10, marginTop: 3, color: C.dim }}>assigned to {t.person}</div> : null)}
            {!t.roleLabel && <button onClick={onManage} style={{ ...linkBtn, marginTop: 6 }}>Set an owner in templates →</button>}
          </div>
        </div>

        {canEdit ? (
          <>
            {/* status action */}
            <div>
              <div style={dcap}>UPDATE STATUS</div>
              <SegGroup>
                <SegItem active={t.status === 'upcoming'} onClick={() => set({ status: 'pending', percent_complete: 0 })}>Not started</SegItem>
                <SegItem active={t.status === 'open'} onClick={() => set({ status: 'in_progress', percent_complete: Math.max(t.pct, 1) })}>In progress</SegItem>
                <SegItem active={t.status === 'done'} onClick={() => set({ status: 'done' })}>Done</SegItem>
              </SegGroup>
            </div>

            {/* progress */}
            <div>
              <div style={dcap}>PROGRESS · {t.pct}%</div>
              <input type="range" min={0} max={100} step={5} defaultValue={t.pct} disabled={busy}
                onMouseUp={e => set({ percent_complete: Number(e.target.value), status: Number(e.target.value) >= 100 ? 'done' : (Number(e.target.value) > 0 ? 'in_progress' : t.rawStatus) })}
                onTouchEnd={e => set({ percent_complete: Number(e.target.value) })}
                style={{ width: '100%', accentColor: 'var(--pb-accent)' }} />
            </div>

            {/* window */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <Field label="START">
                <input type="date" defaultValue={t.start || ''} disabled={busy} onChange={e => set({ start_date: e.target.value || null })} style={dateInput} />
              </Field>
              <Field label="DUE">
                <input type="date" defaultValue={t.due || ''} disabled={busy} onChange={e => set({ due_date: e.target.value || null })} style={dateInput} />
              </Field>
            </div>

            {/* assign a specific person (over and above the owner role) */}
            <Field label="ASSIGNED PERSON (OPTIONAL)">
              <select defaultValue={t.memberId || ''} disabled={busy} onChange={e => set({ assigned_to_member_id: e.target.value || null })} style={{ ...selStyle, width: '100%' }}>
                <option value="">— by the owner role —</option>
                {base.members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
              </select>
            </Field>

            {/* budget */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <Field label="BUDGET ($)">
                <input type="number" defaultValue={t.budget || ''} disabled={busy} onChange={e => set({ budget_estimate: e.target.value === '' ? null : Number(e.target.value) })} style={dateInput} />
              </Field>
              <Field label="SPENT ($)">
                <input type="number" defaultValue={t.spent || ''} disabled={busy} onChange={e => set({ actual_expenditure: e.target.value === '' ? null : Number(e.target.value) })} style={dateInput} />
              </Field>
            </div>
            {t.budget > 0 && <div style={{ height: 5, borderRadius: 3, background: C.surface2, overflow: 'hidden', marginTop: -8 }}><div style={{ height: '100%', width: Math.min(100, (t.spent / t.budget) * 100) + '%', background: t.spent > t.budget ? C.block : C.ok }} /></div>}
          </>
        ) : (
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
            This is an ongoing duty ({t.cadence.toLowerCase()}), so it has no single deadline to track — it recurs continuously. Change how it works in <button onClick={onManage} style={{ ...linkBtn, display: 'inline' }}>the templates</button>.
          </div>
        )}

        {/* dependencies */}
        <div>
          <div style={dcap}>DEPENDS ON</div>
          <DepList tasks={up} onOpen={onOpen} empty="Nothing yet, so this one can start any time." />
        </div>
        <div>
          <div style={dcap}>HOLDS UP</div>
          <DepList tasks={down} onOpen={onOpen} empty="Nothing downstream." />
        </div>
      </div>
     </div>
    </Drawer>
  )
}

function DepList({ tasks, onOpen, empty }) {
  if (tasks.length === 0) return <div style={{ fontSize: 13, color: C.faint }}>{empty}</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {tasks.map(x => (
        <button key={x.key} onClick={() => onOpen(x.key)} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer', textAlign: 'left', width: '100%' }}>
          <StatusDot status={x.status} />
          <span style={{ fontSize: 12.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{x.title}</span>
          <StatusBadge status={x.status} small />
        </button>
      ))}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginBottom: 5 }}>{label}</div>
      {children}
    </label>
  )
}

// ─── Shared bits ─────────────────────────────────────────────────────────────

function Empty({ children }) {
  return <div style={{ fontSize: 13, color: C.faint, padding: '10px 0' }}>{children}</div>
}

// The season-year selector for the date views (List / Calendar / Timeline). It
// lives on each view's own toolbar rather than in the screen header, so the
// header's right cluster stays identical across all five views and none of them
// wraps it onto a second row.
function SeasonSelect({ v }) {
  const { base, selectedYear, currentSeasonYear, patch } = v
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 7, flexShrink: 0 }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.12em', color: C.faint }}>SEASON</span>
      <select value={selectedYear} onChange={e => patch({ diaryYear: Number(e.target.value) })}
        aria-label="Season" style={selStyle}>
        {seasonOptions(base.years, currentSeasonYear).map(y => (
          <option key={y} value={y}>{seasonLabel(y)}{base.years.includes(y) ? '' : ' · not generated'}</option>
        ))}
      </select>
    </label>
  )
}

function SeasonEmpty({ year, current, onGenerate, busy }) {
  return (
    <div style={{ padding: '40px 24px', textAlign: 'center', maxWidth: 460, margin: '0 auto' }}>
      <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>No plan generated for {seasonLabel(year)} yet</div>
      <p style={{ fontSize: 13, color: C.faint, lineHeight: 1.6, margin: '8px 0 16px' }}>
        Generate the season to turn your task templates into dated tasks, each carrying the committee seat that owns it. Then the calendar, list and timeline fill in.
      </p>
      <button disabled={busy} onClick={() => onGenerate(year)} style={{ padding: '9px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: 'var(--pb-on-accent, #0a0d14)', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1 }}>
        Generate {seasonLabel(year)}
      </button>
    </div>
  )
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

const seasonLabel = (y) => `${y}/${String((y + 1) % 100).padStart(2, '0')}`
function seasonOptions(years, current) {
  const set = new Set([current - 1, current, current + 1, ...years])
  return Array.from(set).sort((a, b) => b - a)
}
function withinDays(iso, days, T) {
  const t = parseISO(iso)
  if (t == null) return false
  return t >= T && t <= T + days * DAY
}
function statusMatches(filter, status) { return filter === status }

function stepMonth({ y, m }, delta) {
  let nm = m + delta, ny = y
  while (nm < 0) { nm += 12; ny -= 1 }
  while (nm > 11) { nm -= 12; ny += 1 }
  return { y: ny, m: nm }
}
function sameDay(a, b) { const x = new Date(a), y = new Date(b); return x.getUTCFullYear() === y.getUTCFullYear() && x.getUTCMonth() === y.getUTCMonth() && x.getUTCDate() === y.getUTCDate() }

// Monday-start weeks covering a calendar month (leading/trailing days flagged
// out-of-month), as [{t, inMonth}] rows of 7. All UTC so the cells align with
// the date-only due dates. Six rows are generated then the fully-out-of-month
// ones dropped, so a month spans 4–6 weeks.
function weeksOfMonth(year, monthIdx) {
  const firstDow = (new Date(Date.UTC(year, monthIdx, 1)).getUTCDay() + 6) % 7 // Monday = 0
  const weeks = []
  for (let w = 0; w < 6; w++) {
    const row = []
    for (let d = 0; d < 7; d++) {
      const t = Date.UTC(year, monthIdx, 1 - firstDow + w * 7 + d)
      row.push({ t, inMonth: new Date(t).getUTCMonth() === monthIdx })
    }
    weeks.push(row)
  }
  return weeks.filter(row => row.some(c => c.inMonth))
}

// Greedy lane packing for one week: each task becomes a segment clipped to the
// week's day columns [0..6]; segments that overlap go on separate lanes.
function packLanes(tasks, wStart, wEnd) {
  const segs = tasks.map(t => {
    const due = parseISO(t.due), start = parseISO(t.start) || due
    const s = Math.max(Math.min(start, due), wStart)
    const e = Math.min(Math.max(start, due), wEnd)
    return { t, from: dayCol(s, wStart), to: dayCol(e, wStart) }
  }).filter(x => x.to >= x.from).sort((a, b) => a.from - b.from || a.to - b.to)
  const lanes = []
  segs.forEach(seg => {
    let placed = false
    for (const lane of lanes) {
      if (lane[lane.length - 1].to < seg.from) { lane.push(seg); placed = true; break }
    }
    if (!placed) lanes.push([seg])
  })
  return lanes
}
function dayCol(t, wStart) { return Math.max(0, Math.min(6, Math.floor((t - wStart) / DAY))) }

// Per committee-seat load counts, for the Overview strip.
function seatLoads(model) {
  const map = {}
  model.seats.forEach(s => { map[s.id] = { id: s.id, name: s.name, holder: s.holder, total: 0, late: 0, open: 0, upcoming: 0, done: 0 } })
  model.boardTasks.forEach(t => {
    if (t.standing || !t.seatId || !map[t.seatId]) return
    const m = map[t.seatId]; m.total++
    if (t.status === 'overdue' || t.status === 'blocked') m.late++
    else if (t.status === 'open') m.open++
    else if (t.status === 'done') m.done++
    else m.upcoming++
  })
  return Object.values(map).sort((a, b) => b.late - a.late || b.total - a.total)
}

// Full per-seat task lists, for the By-role cards.
function seatDetail(model) {
  const map = {}
  model.seats.forEach(s => { map[s.id] = { id: s.id, name: s.name, holder: s.holder, responsibilities: s.responsibilities, tasks: [] } })
  // Standing duties are excluded — the By-role cards list only the dated diary
  // tasks a seat is carrying, not its perpetual ongoing responsibilities.
  model.boardTasks.forEach(t => { if (!t.standing && t.seatId && map[t.seatId]) map[t.seatId].tasks.push(t) })
  return Object.values(map).sort((a, b) => {
    const la = a.tasks.filter(t => t.status === 'overdue' || t.status === 'blocked').length
    const lb = b.tasks.filter(t => t.status === 'overdue' || t.status === 'blocked').length
    return lb - la || b.tasks.length - a.tasks.length || a.name.localeCompare(b.name)
  })
}

// Critical path over the season's dated occurrences (longest chain of remaining
// work through the definition-level dependency graph). Titles resolve via defById.
function criticalPath(tasks, model) {
  const byDef = {}; tasks.forEach(t => { if (!t.standing) byDef[t.defId] = t })
  const memo = {}
  const span = (t) => Math.max(1, ((parseISO(t.due) || 0) - (parseISO(t.start) || parseISO(t.due) || 0)) / DAY || 1)
  const chain = (defId, seen) => {
    if (memo[defId]) return memo[defId]
    if (seen.has(defId)) return { len: 0, path: [] }
    const t = byDef[defId]; if (!t) return { len: 0, path: [] }
    const s = span(t)
    let best = { len: s, path: [defId] }
    t.deps.filter(d => byDef[d] && byDef[d].status !== 'done').forEach(d => {
      const c = chain(d, new Set(seen).add(defId))
      if (c.len + s > best.len) best = { len: c.len + s, path: c.path.concat([defId]) }
    })
    return (memo[defId] = best)
  }
  let cp = { len: 0, path: [] }
  Object.values(byDef).filter(t => t.status !== 'done').forEach(t => { const c = chain(t.defId, new Set()); if (c.len > cp.len) cp = c })
  return { len: Math.round(cp.len), path: cp.path }
}

// ─── inline styles ───────────────────────────────────────────────────────────

const selStyle = { padding: '7px 10px', borderRadius: 8, fontSize: 12.5, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.text, fontFamily: 'inherit', flexShrink: 0 }
const dateInput = { width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8, fontSize: 13, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.text, fontFamily: 'inherit' }
const navBtn = { width: 28, height: 28, borderRadius: 7, border: `1px solid ${C.hair2}`, background: C.surface2, color: C.dim, cursor: 'pointer', fontSize: 15, lineHeight: 1 }
const linkBtn = { background: 'transparent', border: 'none', color: C.accent, fontSize: 12, cursor: 'pointer', padding: 0, fontFamily: 'inherit' }
const attnRow = { display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px', borderRadius: 9, background: 'rgba(239,91,91,0.06)', border: '1px solid rgba(239,91,91,0.22)', cursor: 'pointer', width: '100%', fontFamily: 'inherit' }
const comingRow = { display: 'flex', alignItems: 'center', gap: 11, padding: '8px 11px', borderRadius: 9, background: C.surface, border: `1px solid ${C.hair}`, cursor: 'pointer', width: '100%', fontFamily: 'inherit' }
const seatChip = { display: 'block', textAlign: 'left', padding: '10px 12px', borderRadius: 10, background: C.surface, border: `1px solid ${C.hair}`, cursor: 'pointer', width: '100%', fontFamily: 'inherit' }
const ongoingChip = { display: 'inline-flex', alignItems: 'center', gap: 7, padding: '7px 11px', borderRadius: 999, background: C.surface, border: `1px solid ${C.hair}`, cursor: 'pointer', fontFamily: 'inherit' }
const listHeadRow = { display: 'grid', gridTemplateColumns: 'minmax(0, 2.4fr) 0.9fr minmax(0, 1.7fr) 0.9fr 1fr 1.1fr', gap: 10, padding: '9px 20px', position: 'sticky', top: 0, zIndex: 5, background: C.bg, borderBottom: `1px solid ${C.hair2}`, fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faintest }
const listRow = { display: 'grid', gridTemplateColumns: 'minmax(0, 2.4fr) 0.9fr minmax(0, 1.7fr) 0.9fr 1fr 1.1fr', gap: 10, padding: '10px 20px', alignItems: 'center', borderBottom: `1px solid ${C.surface2}` }
const groupHead = { display: 'flex', alignItems: 'center', gap: 9, padding: '9px 20px', background: C.surface, borderBottom: `1px solid ${C.hair}`, borderTop: `1px solid ${C.hair}`, cursor: 'pointer' }
