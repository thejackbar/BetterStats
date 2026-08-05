import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import { C, MONO, ScreenHeader, NavToggle, Toast, initials } from '../ui'

// Roster on the real backend. Operational areas + shift patterns are config; a
// roster week materialises shifts from the patterns; assignments run through the
// server rules engine (and are mirrored client-side here for candidate ranking).

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
function fmtHour(h) {
  const hh = Math.floor(h), mm = Math.round((h - hh) * 60)
  if (hh === 24) return '12am'
  const ampm = hh >= 12 && hh < 24 ? 'pm' : 'am'
  let base = hh % 12; if (base === 0) base = 12
  return base + (mm ? ':' + String(mm).padStart(2, '0') : '') + ampm
}
function weekDates(weekStartISO) {
  const start = weekStartISO ? new Date(weekStartISO + 'T00:00:00') : new Date()
  return DOW.map((_, i) => {
    const d = new Date(start); d.setDate(start.getDate() + i)
    return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()]
  })
}
const DEFAULT_CAP = 3

// Client mirror of services/roster.check_assignment.
function checkClient(area, shift, cand, shifts, settings) {
  const blocks = [], warns = []
  const cap = settings.weekly_shift_cap || cand.max_shifts || DEFAULT_CAP
  if (area.required_qualification_type_id && !cand.qual_type_ids.includes(area.required_qualification_type_id)) {
    (settings.enforce_qualifications === false ? warns : blocks).push('Missing ' + (area.required_qualification_name || 'required qualification'))
  }
  if (!cand.available_days.includes(shift.day_of_week)) blocks.push('Not available ' + DOW[shift.day_of_week])
  const mine = shifts.filter(s => s.assignee_member_id === cand.member_id && s.id !== shift.id)
  if (mine.some(s => s.day_of_week === shift.day_of_week && s.start_time < shift.end_time && shift.start_time < s.end_time)) blocks.push('Overlaps another shift')
  if (area.required_role_id && !cand.role_ids.includes(area.required_role_id)) warns.push('Not in the ' + (area.required_role_name || 'required') + ' role')
  if (mine.length + 1 > cap) warns.push('Over their ' + cap + '-shift weekly cap')
  if (mine.length + 1 >= 4) warns.push('Heavy week — spread the load')
  if (cand.player_id && shift.day_of_week === 5 && shift.start_time < 18.5) warns.push('May be selected to play Saturday')
  return { blocks, warns }
}

// "Email everyone rostered" for a day, a week or a month. The recipients are
// resolved server-side from the shifts themselves and handed to the composer as
// a ready-made list, so nobody rebuilds the group by hand from the grid they
// are already looking at.
function EmailRostered({ weekStart, onToast }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function go(scope) {
    setBusy(true); setOpen(false)
    try {
      const res = await api.rosterContacts(scope, weekStart)
      if (!res.contact_ids.length) {
        onToast({ tone: 'warn', title: 'Nobody to email.',
          body: res.people.length
            ? `${res.people.length} rostered, but none of them have an email contact on file.`
            : `Nobody is rostered ${scope === 'day' ? 'that day' : 'in that ' + scope}.` })
        return
      }
      // The audience goes on at creation. The composer reads it back from the
      // campaign, so nothing has to be threaded through router state.
      const c = await api.commsCreateCampaign({
        name: `Rostered · ${res.from}${res.to !== res.from ? ` to ${res.to}` : ''}`,
        audience: { type: 'list', contact_ids: res.contact_ids },
      })
      if (res.unreachable.length) {
        onToast({ tone: 'warn', title: `${res.contact_ids.length} on the list.`,
          body: `${res.unreachable.length} rostered ${res.unreachable.length === 1 ? 'person has' : 'people have'} no email contact: ${res.unreachable.slice(0, 3).join(', ')}${res.unreachable.length > 3 ? '…' : ''}` })
      }
      navigate(`/admin/comms/${c.id}`, { state: { skipIntro: true } })
    } catch (e) {
      onToast({ tone: 'block', title: 'Could not build the list.', body: String(e?.message || e) })
    } finally { setBusy(false) }
  }

  return (
    <span style={{ position: 'relative' }}>
      <button disabled={busy} onClick={() => setOpen(o => !o)}
        style={{ padding: '8px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', opacity: busy ? 0.6 : 1, whiteSpace: 'nowrap' }}>
        {busy ? 'Building…' : 'Email rostered'}
      </button>
      {open && (
        <span style={{ position: 'absolute', top: '100%', right: 0, marginTop: 6, zIndex: 60, background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 4, display: 'flex', flexDirection: 'column', minWidth: 132, boxShadow: '0 8px 30px rgba(0,0,0,0.4)' }}>
          {[['day', 'Rostered today'], ['week', 'This week'], ['month', 'This month']].map(([k, l]) => (
            <button key={k} onClick={() => go(k)}
              style={{ padding: '7px 10px', borderRadius: 6, fontSize: 12.5, textAlign: 'left', border: 'none', background: 'transparent', color: C.dim, cursor: 'pointer' }}>{l}</button>
          ))}
        </span>
      )}
    </span>
  )
}

// Adding a shift that no weekly pattern covers: a final, a night game, an extra
// hand behind the bar. Editing the pattern would change every week.
function AddShift({ areas, weekId, onDone, onCancel }) {
  const [f, setF] = useState({ area_id: areas[0]?.id || '', day_of_week: 5, start_time: '17', end_time: '21' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const inp = { padding: '6px 8px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: C.surface2, color: C.text }
  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 10, marginBottom: 10 }}>
      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>NEW SHIFT</div>
      <div style={{ display: 'grid', gap: 6 }}>
        <select value={f.area_id} onChange={e => setF(v => ({ ...v, area_id: e.target.value }))} style={inp}>
          {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={f.day_of_week} onChange={e => setF(v => ({ ...v, day_of_week: Number(e.target.value) }))} style={inp}>
          {DOW.map((d, i) => <option key={i} value={i}>{d}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="number" step="0.25" min="0" max="24" value={f.start_time} onChange={e => setF(v => ({ ...v, start_time: e.target.value }))} style={{ ...inp, flex: 1 }} placeholder="From" />
          <input type="number" step="0.25" min="0" max="24" value={f.end_time} onChange={e => setF(v => ({ ...v, end_time: e.target.value }))} style={{ ...inp, flex: 1 }} placeholder="To" />
        </div>
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>Times are 24-hour, so 17.5 is 5:30pm.</div>
        {err && <div style={{ fontSize: 11.5, color: C.block }}>{err}</div>}
        <div style={{ display: 'flex', gap: 6 }}>
          <button disabled={busy || !f.area_id} onClick={async () => {
            setBusy(true); setErr(null)
            try {
              await api.rosterCreateShift({
                week_id: weekId, area_id: f.area_id, day_of_week: f.day_of_week,
                start_time: Number(f.start_time), end_time: Number(f.end_time),
              })
              onDone()
            } catch (e) { setErr(e.message) } finally { setBusy(false) }
          }} style={{ flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>
            {busy ? 'Adding…' : 'Add shift'}
          </button>
          <button onClick={onCancel} style={{ padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// The roster is where you notice someone's availability is wrong, so it should
// be where you can fix it, rather than sending them to another screen.
function PersonPanel({ memberId, onClose, onSaved }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    api.rosterMember(memberId).then(r => { if (alive) setD(r) }).catch(e => alive && setErr(e.message))
    return () => { alive = false }
  }, [memberId])

  const toggle = async (day) => {
    const next = d.available_days.includes(day)
      ? d.available_days.filter(x => x !== day) : [...d.available_days, day].sort()
    setD(v => ({ ...v, available_days: next }))   // optimistic
    setBusy(true)
    try { await api.rosterSetAvailability(memberId, next); onSaved?.() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (err) return <div style={{ fontSize: 12, color: C.block, marginBottom: 10 }}>{err}</div>
  if (!d) return <div style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, marginBottom: 10 }}>Loading…</div>
  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 10, marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 13.5 }}>{d.full_name}</span>
        <button onClick={onClose} style={{ fontFamily: MONO, fontSize: 10, background: 'none', border: 'none', color: C.faint, cursor: 'pointer' }}>close</button>
      </div>
      {(d.email || d.mobile) && (
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{[d.email, d.mobile].filter(Boolean).join(' · ')}</div>
      )}

      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, margin: '10px 0 5px' }}>AVAILABLE</div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {DOW.map((label, i) => {
          const on = d.available_days.includes(i)
          return (
            <button key={i} disabled={busy} onClick={() => toggle(i)}
              style={{ padding: '4px 8px', borderRadius: 6, fontFamily: MONO, fontSize: 10, cursor: 'pointer',
                border: `1px solid ${on ? 'transparent' : C.hair2}`,
                background: on ? C.accent : 'transparent', color: on ? '#fff' : C.faint }}>{label}</button>
          )
        })}
      </div>

      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, margin: '10px 0 5px' }}>QUALIFICATIONS</div>
      {d.qualifications.length === 0
        ? <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>None recorded.</div>
        : d.qualifications.map(q => (
          <div key={q.id} style={{ fontSize: 12, color: C.dim }}>
            {q.name}{q.expires_at && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}> · expires {q.expires_at}</span>}
          </div>
        ))}

      {d.roles.length > 0 && (
        <>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, margin: '10px 0 5px' }}>ROLES</div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {d.roles.map(r => (
              <span key={r.id} style={{ fontFamily: MONO, fontSize: 9.5, padding: '2px 6px', borderRadius: 4, border: `1px solid ${C.hair2}`, color: r.is_paid ? C.warn : C.faint }}>
                {r.title}{r.is_paid ? ' · PAID' : ''}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// Rostered against worked, paid against volunteer.
//
// Four numbers per person rather than one total, because they answer different
// questions. Rostered is what the club committed someone to; worked is what
// they logged afterwards, and the gap between the two is the thing worth
// looking at. Paid is split out because a club's wage bill and its volunteer
// effort are not the same number and should never be added together — one goes
// to the treasurer, the other to the grant application.
function HoursView({ weekStart }) {
  const [span, setSpan] = useState('week')
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)

  const range = useMemo(() => {
    const start = new Date(weekStart + 'T00:00:00Z')
    if (span === 'week') {
      const end = new Date(start); end.setUTCDate(end.getUTCDate() + 6)
      return [weekStart, end.toISOString().slice(0, 10)]
    }
    if (span === 'month') {
      const s = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1))
      const e = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0))
      return [s.toISOString().slice(0, 10), e.toISOString().slice(0, 10)]
    }
    // A season runs Jul-Jun, so anything before July belongs to the year before.
    const y = start.getUTCMonth() >= 6 ? start.getUTCFullYear() : start.getUTCFullYear() - 1
    return [`${y}-07-01`, `${y + 1}-06-30`]
  }, [weekStart, span])

  useEffect(() => {
    let alive = true
    setD(null); setErr(null)
    api.rosterHours(range[0], range[1])
      .then(r => { if (alive) setD(r) })
      .catch(e => alive && setErr((e?.status ? `HTTP ${e.status} · ` : '') + String(e?.message || e)))
    return () => { alive = false }
  }, [range[0], range[1]])

  const hrs = n => (n || 0) === 0 ? '—' : (Math.round(n * 10) / 10).toString()
  const T = d?.totals

  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: '18px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 3, width: 'fit-content', marginBottom: 16 }}>
        {[['week', 'This week'], ['month', 'This month'], ['season', 'This season']].map(([k, label]) => (
          <button key={k} onClick={() => setSpan(k)}
            style={{ padding: '5px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer',
              background: span === k ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : 'transparent',
              color: span === k ? C.accent : C.faint }}>{label}</button>
        ))}
        <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, padding: '0 8px' }}>{range[0]} → {range[1]}</span>
      </div>

      {err && <div style={{ fontSize: 13, color: C.block }}>{err}</div>}
      {!d && !err && <div style={{ fontFamily: MONO, fontSize: 10, color: C.faintest }}>Loading hours…</div>}

      {d && (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }}>
            {[['Volunteer rostered', T.rostered_volunteer], ['Volunteer worked', T.worked_volunteer],
              ['Paid rostered', T.rostered_paid], ['Paid worked', T.worked_paid]].map(([label, v], i) => (
              <div key={label} style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 10, padding: '12px 16px', minWidth: 150 }}>
                <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest }}>{label.toUpperCase()}</div>
                <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4, fontVariantNumeric: 'tabular-nums', color: i >= 2 ? C.warn : C.text }}>
                  {hrs(v)}<span style={{ fontSize: 12, fontWeight: 500, color: C.faint, marginLeft: 3 }}>hrs</span>
                </div>
              </div>
            ))}
          </div>

          {d.people.length === 0 ? (
            <div style={{ fontSize: 13, color: C.faint, maxWidth: '46rem', lineHeight: 1.6 }}>
              Nobody was rostered or logged hours in this period. Hours appear here once a shift has
              someone assigned to it, and worked hours once they have been logged against a volunteer.
            </div>
          ) : (
            <div style={{ border: `1px solid ${C.hair}`, borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr repeat(4, 126px)', background: C.surface2, borderBottom: `1px solid ${C.hair}` }}>
                {['PERSON', 'VOL ROSTERED', 'VOL WORKED', 'PAID ROSTERED', 'PAID WORKED'].map((h, i) => (
                  <div key={h} style={{ padding: '9px 12px', fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest, textAlign: i ? 'right' : 'left' }}>{h}</div>
                ))}
              </div>
              {d.people.map(p => (
                <div key={p.member_id} style={{ display: 'grid', gridTemplateColumns: '1fr repeat(4, 126px)', borderBottom: `1px solid ${C.hair}` }}>
                  <div style={{ padding: '9px 12px', fontSize: 13, fontWeight: 600 }}>{p.full_name}</div>
                  {['rostered_volunteer', 'worked_volunteer', 'rostered_paid', 'worked_paid'].map((k, i) => (
                    <div key={k} style={{ padding: '9px 12px', textAlign: 'right', fontFamily: MONO, fontSize: 12, fontVariantNumeric: 'tabular-nums', color: p[k] ? (i >= 2 ? C.warn : C.dim) : C.faintest }}>{hrs(p[k])}</div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function Roster({ st, patch, narrow }) {
  const [data, setData] = useState(null)  // { week, areas, candidates, settings }
  const [shifts, setShifts] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [addingShift, setAddingShift] = useState(false)
  const [openPerson, setOpenPerson] = useState(null)

  // api.js stamps the HTTP status onto the error, which is the difference
  // between "you lack a capability" (403) and "the server threw" (500).
  // st.rosterWeek is how another screen hands us a week — Events uses it for
  // "Roster this event" so you land on the week the event falls in.
  const load = () => api.rosterWeek(st.rosterWeek)
    .then(res => { setData(res); setShifts(res.week.shifts || []) })
    .catch(e => setErr((e?.status ? `HTTP ${e.status} · ` : '') + String(e?.message || e)))
  useEffect(() => { load() }, [st.rosterWeek])

  const view = st.view
  const gridCols = narrow ? '176px repeat(7, minmax(0, 1fr))' : '216px repeat(7, minmax(150px, 1fr))'

  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Roster</h1>
        <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint, marginTop: 2 }}>{data?.week ? 'WEEK OF ' + weekDates(data.week.week_start)[0].toUpperCase() + (data.week.status === 'published' ? ' · PUBLISHED' : '') : 'THIS WEEK'}</div>
      </div>
      {children}
    </ScreenHeader>
  )

  // A failure here used to read "Could not load the roster." and nothing else,
  // which is the same message whether the club lacks a capability, the request
  // timed out, or the server threw. Say which, so it can be acted on.
  if (!data) return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />
      <div style={{ padding: 24, fontSize: 13, color: C.faint, maxWidth: '46rem' }}>
        {!err ? 'Loading the roster…' : (
          <div style={{ background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 9, padding: 18, lineHeight: 1.6 }}>
            <div style={{ color: C.block, fontWeight: 600, fontSize: 13.5, marginBottom: 6 }}>Could not load the roster.</div>
            <div style={{ color: C.dim }}>{err}</div>
            <div style={{ marginTop: 12 }}>
              <button onClick={() => { setErr(null); load() }}
                style={{ padding: '7px 13px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#0a0d14', cursor: 'pointer' }}>Try again</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )

  const { areas, candidates, settings } = data
  const areaById = {}; areas.forEach(a => { areaById[a.id] = a })
  const candById = {}; candidates.forEach(c => { candById[c.member_id] = c })

  // no config yet → offer to seed a starter set (also handy for testing)
  if (areas.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Header />
        <div style={{ padding: 24, maxWidth: '46rem' }}>
          <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 22, fontSize: 13.5, color: C.dim, lineHeight: 1.6 }}>
            No operational areas set up yet. An area is a slice of club work (Bar, Umpires, Groundsman…) with its own weekly shift pattern, the role that covers it and the qualification that gates it. Add a starter set to see the weekly roster generate — you can rename, re-time or remove them afterwards in Areas &amp; Roles.
            <div style={{ marginTop: 14 }}>
              <button disabled={busy} onClick={async () => { setBusy(true); await api.rosterSeedStarter().catch(() => {}); await load(); setBusy(false) }}
                style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>{busy ? 'Setting up…' : 'Add Operational Areas Starter Pack'}</button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const DATES = weekDates(data.week.week_start)
  const open = shifts.filter(x => !x.assignee_member_id)
  const filled = shifts.length - open.length
  const pct = shifts.length ? Math.round((filled / shifts.length) * 100) : 0

  const doAssign = async (shiftId, memberId) => {
    const res = await api.rosterAssign(data.week.id, shiftId, memberId).catch(() => ({ ok: false, blocks: ['Network error'] }))
    if (!res.ok) {
      const cand = candById[memberId]
      patch({ toast: { tone: 'block', title: cand ? 'Can’t roster ' + cand.name + ' here.' : 'Could not update the shift.', body: (res.blocks || []).join(' · ') } })
      return
    }
    if (res.cleared) {
      setShifts(prev => prev.map(s => s.id === shiftId ? { ...s, assignee_member_id: null, assignee_name: null, warnings: [] } : s))
      const sh = shifts.find(s => s.id === shiftId); const a = sh && areaById[sh.area_id]
      patch({ toast: { tone: 'info', title: 'Shift returned to Open.', body: a ? a.name + ' · ' + DOW[sh.day_of_week] : '' } })
      return
    }
    setShifts(prev => prev.map(s => s.id === shiftId ? { ...s, assignee_member_id: memberId, assignee_name: res.assignee_name, warnings: res.warns || [] } : s))
    const sh = shifts.find(s => s.id === shiftId); const a = sh && areaById[sh.area_id]
    patch({ toast: (res.warns && res.warns.length)
      ? { tone: 'warn', title: res.assignee_name + ' rostered with a warning.', body: res.warns.join(' · ') }
      : { tone: 'ok', title: res.assignee_name + ' rostered.', body: a ? a.name + ' · ' + DOW[sh.day_of_week] + ' ' + fmtHour(sh.start_time) + '–' + fmtHour(sh.end_time) : '' } })
  }
  const autoFill = async () => {
    setBusy(true)
    const res = await api.rosterAutofill(data.week.id).catch(() => null)
    setBusy(false)
    if (!res) return
    setShifts(res.shifts || shifts)
    patch({ toast: { tone: res.placed ? 'ok' : 'warn', title: 'Auto-fill proposed ' + res.placed + ' assignment' + (res.placed === 1 ? '' : 's') + '.', body: res.remaining ? res.remaining + ' shift' + (res.remaining === 1 ? '' : 's') + ' still need a qualified, available volunteer.' : 'Every shift is covered. Review the amber chips, then publish.' } })
  }
  const publish = async () => {
    const res = await api.rosterPublish(data.week.id).catch(() => null)
    if (!res) return
    setData(d => ({ ...d, week: { ...d.week, status: 'published' } }))
    patch({ toast: res.open
      ? { tone: 'warn', title: 'Published with ' + res.open + ' open shift' + (res.open === 1 ? '' : 's') + '.', body: 'Volunteers can self-nominate for the gaps; you confirm each one.' }
      : { tone: 'ok', title: 'Week published.', body: 'Everyone rostered gets their shift and a check-in tap that logs their hours.' } })
  }
  const resetWeek = async () => {
    if (!window.confirm('Reset this week? Every assignment is cleared and the shifts are regenerated from your patterns. This only affects this week.')) return
    const res = await api.rosterReset(data.week.id).catch(() => null)
    if (!res) return
    setShifts(res.shifts || [])
    setData(d => ({ ...d, week: { ...d.week, status: 'draft' } }))
    patch({ toast: { tone: 'info', title: 'Week reset.', body: 'Every shift is open again.' } })
  }

  const cellDrop = (key, personId) => ({
    onDragOver: e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
    onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
    onDrop: e => { e.preventDefault(); const id = st.dragId; patch({ overCell: null, dragId: null }); if (id) doAssign(id, personId) },
  })
  const slotDrop = (shiftId) => {
    const key = 'slot-' + shiftId
    return {
      onDragOver: e => { if (!st.dragPerson) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
      onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
      onDrop: e => { e.preventDefault(); const pid = st.dragPerson; patch({ overCell: null, dragPerson: null }); if (pid) doAssign(shiftId, pid) },
    }
  }
  const cellStyle = (isOver, extra) => ({ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5, ...(isOver ? { background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', boxShadow: 'inset 0 0 0 1.5px var(--pb-accent)' } : {}), ...extra })

  const ShiftChip = ({ shift, inOpen, count }) => {
    const a = areaById[shift.area_id] || {}
    const warned = shift.warnings && shift.warnings.length
    return (
      <div draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragId: shift.id, selected: shift.id }) }} onDragEnd={() => patch({ dragId: null, overCell: null })} onClick={() => patch({ selected: shift.id })}
        style={{ borderRadius: 7, padding: '6px 8px', cursor: 'grab', userSelect: 'none',
          border: `1px solid ${inOpen ? 'rgba(245,181,66,0.45)' : (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 40%, transparent)`)}`,
          background: inOpen ? 'rgba(245,181,66,0.10)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 13%, transparent)`, color: inOpen ? C.warn : (a.color || C.accent) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: a.color || 'var(--pb-accent)' }} />
          <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{count > 1 ? a.name + ' ×' + count : a.name}</span>
          {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{fmtHour(shift.start_time)}–{fmtHour(shift.end_time)}</div>
      </div>
    )
  }

  const sel = st.selected ? shifts.find(x => x.id === st.selected) : null
  const selArea = sel ? areaById[sel.area_id] : null
  const ranked = sel ? candidates.map(c => ({ c, res: checkClient(selArea, sel, c, shifts, settings), load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))
    .filter(x => x.res.blocks.length === 0).sort((a, b) => (a.res.warns.length * 10 + a.load) - (b.res.warns.length * 10 + b.load))
    : candidates.map(c => ({ c, res: { warns: [] }, load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))
  const candList = ranked.slice(0, 14)

  const openCells = DOW.map((_, d) => {
    const groups = []
    open.filter(x => x.day_of_week === d).forEach(x => {
      const g = groups.find(y => areaById[y.shift.area_id]?.name === areaById[x.area_id]?.name && y.shift.start_time === x.start_time && y.shift.end_time === x.end_time)
      if (g) g.count++; else groups.push({ shift: x, count: 1 })
    })
    return { d, groups }
  })

  const depts = []; areas.forEach(a => { if (!depts.includes(a.department || 'Areas')) depts.push(a.department || 'Areas') })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 3 }}>
          {['people', 'areas', 'hours'].map(v => (
            <button key={v} onClick={() => patch({ view: v, selected: null })} style={{ padding: '5px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer', textTransform: 'capitalize', background: view === v ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : 'transparent', color: view === v ? C.accent : C.faint }}>{v}</button>
          ))}
        </div>
        {/* Every one of these acts on the shift grid, so none of them mean
            anything while the hours tab is showing. */}
        <div style={{ display: view === 'hours' ? 'none' : 'flex', alignItems: 'center', gap: 14, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
            <span style={{ fontWeight: 700, fontSize: 18, color: C.text, fontVariantNumeric: 'tabular-nums' }}>{filled}</span>
            <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, letterSpacing: '0.08em' }}>/ {shifts.length} FILLED</span>
          </div>
          <div style={{ width: 120, height: 6, borderRadius: 3, background: C.surface2, overflow: 'hidden' }}><div style={{ height: '100%', width: pct + '%', background: pct === 100 ? C.ok : C.accent }} /></div>
          <button onClick={() => patch(s => ({ panelOpen: !s.panelOpen }))} style={{ padding: '8px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', ...(st.panelOpen ? { border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: C.accent, background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' } : { border: `1px solid ${C.hair2}`, color: C.dim, background: 'transparent' }) }}>{st.panelOpen ? 'Hide candidates' : 'Candidates'}</button>
          <button disabled={busy} onClick={autoFill} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>Auto-fill open shifts</button>
          <EmailRostered weekStart={data.week.week_start} onToast={t => patch({ toast: t })} />
          <button onClick={resetWeek} style={{ padding: '8px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer' }}>Reset</button>
          <button onClick={publish} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Publish week</button>
        </div>
      </Header>

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {view === 'hours' && <HoursView weekStart={data.week.week_start} />}

      {view !== 'hours' && (
      <div style={{ display: 'flex', flex: 1, minHeight: 0, alignItems: 'stretch' }}>
        <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
          <div style={{ minWidth: narrow ? 0 : 1266 }}>
            <div style={{ display: 'grid', gridTemplateColumns: gridCols, position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
              <div style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, display: 'flex', alignItems: 'center' }}>{view === 'areas' ? 'OPERATIONAL AREA' : 'VOLUNTEER'}</div>
              {DOW.map((d, i) => (
                <div key={i} style={{ padding: '10px 12px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : undefined }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint }}>{d.toUpperCase()}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: C.dim }}>{DATES[i]}</span>
                </div>
              ))}
            </div>

            {view === 'people' && (
              <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair2}`, background: 'rgba(245,181,66,0.04)' }}>
                <div style={{ padding: '12px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 3, justifyContent: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: C.warn }}>Open shifts</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{open.length} unfilled · drag onto a person</span>
                </div>
                {openCells.map(({ d, groups }) => {
                  const key = 'open-' + d
                  const shown = st.openExpanded ? groups : groups.slice(0, 2)
                  const hidden = groups.length - shown.length
                  return (
                    <div key={d} style={cellStyle(st.overCell === key)} {...cellDrop(key, null)}>
                      {shown.map(g => <ShiftChip key={g.shift.id} shift={g.shift} inOpen count={g.count} />)}
                      {(hidden > 0 || (st.openExpanded && groups.length > 2)) && (
                        <button onClick={() => patch(s => ({ openExpanded: !s.openExpanded }))} style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.warn, background: 'transparent', border: '1px dashed rgba(245,181,66,0.4)', borderRadius: 6, padding: '4px 6px', cursor: 'pointer', textAlign: 'left' }}>{hidden > 0 ? '+ ' + hidden + ' more' : 'show less'}</button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {view === 'people' && candidates.map(p => {
              const mine = shifts.filter(x => x.assignee_member_id === p.member_id)
              const cap = settings.weekly_shift_cap || p.max_shifts || DEFAULT_CAP
              const loadPct = Math.min(100, Math.round((mine.length / cap) * 100))
              const over = mine.length > cap
              return (
                <div key={p.member_id} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                  <div style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                      <span style={{ width: 28, height: 28, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 10, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(p.name)}</span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.available_days.length ? 'Avail ' + p.available_days.map(d => DOW[d]).join(' ') : 'No availability set'}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 7 }}>
                      <div style={{ flex: 1, height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden' }}><div style={{ height: '100%', width: loadPct + '%', background: over ? C.block : C.accent }} /></div>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: over ? C.block : C.faint }}>{mine.length}/{cap}</span>
                    </div>
                  </div>
                  {DOW.map((_, d) => {
                    const key = p.member_id + '-' + d
                    const chips = mine.filter(x => x.day_of_week === d)
                    const avail = p.available_days.includes(d)
                    return (
                      <div key={d} style={cellStyle(st.overCell === key, avail ? {} : { background: 'repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(58,63,80,0.10) 6px, rgba(58,63,80,0.10) 12px)' })} {...cellDrop(key, p.member_id)}>
                        {chips.map(x => <ShiftChip key={x.id} shift={x} />)}
                        {!chips.length && !avail && <div style={{ fontFamily: MONO, fontSize: 9, color: C.faintest, letterSpacing: '0.08em', margin: 'auto' }}>UNAVAILABLE</div>}
                      </div>
                    )
                  })}
                </div>
              )
            })}

            {view === 'areas' && depts.map(dept => (
              <div key={dept}>
                <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}`, background: C.surface }}>
                  <div style={{ padding: '8px 14px', fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim, gridColumn: '1 / -1' }}>{dept}</div>
                </div>
                {areas.filter(a => (a.department || 'Areas') === dept).map(a => {
                  const mine = shifts.filter(x => x.area_id === a.id)
                  const filledN = mine.filter(x => x.assignee_member_id).length
                  return (
                    <div key={a.id} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                      <div style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                          <span style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: a.color || 'var(--pb-accent)' }} />
                          <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{a.name}</span>
                          <span style={{ fontFamily: MONO, fontSize: 9.5, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>
                        </div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{[a.required_role_name, a.required_qualification_name].filter(Boolean).join(' · ') || 'No role/qual set'}</div>
                      </div>
                      {DOW.map((_, d) => (
                        <div key={d} style={{ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5, background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined }}>
                          {mine.filter(x => x.day_of_week === d).map(x => {
                            const warned = x.warnings && x.warnings.length
                            const over = st.overCell === 'slot-' + x.id
                            return (
                              <div key={x.id} onClick={() => patch({ selected: x.id })} {...slotDrop(x.id)}
                                style={{ borderRadius: 7, padding: '6px 8px', cursor: 'pointer', userSelect: 'none',
                                  border: `1px solid ${x.assignee_member_id ? (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 40%, transparent)`) : 'rgba(245,181,66,0.45)'}`,
                                  background: x.assignee_member_id ? `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 13%, transparent)` : 'rgba(245,181,66,0.10)',
                                  color: x.assignee_member_id ? (a.color || C.accent) : C.warn,
                                  ...(over ? { boxShadow: '0 0 0 1.5px var(--pb-accent)' } : {}), ...(st.selected === x.id ? { outline: '1.5px solid var(--pb-accent)', outlineOffset: 1 } : {}) }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                  <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...(x.assignee_member_id ? {} : { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em' }) }}>{x.assignee_name || 'OPEN'}</span>
                                  {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
                                </div>
                                <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{fmtHour(x.start_time)}–{fmtHour(x.end_time)}</div>
                              </div>
                            )
                          })}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {st.panelOpen && (
          <aside className="pb-scroll" style={narrow
            ? { width: 320, maxWidth: '92vw', position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 65, borderLeft: `1px solid ${C.hair2}`, background: C.surface, overflowY: 'auto', padding: 16, boxShadow: '0 0 40px rgba(0,0,0,0.5)' }
            : { width: 296, flex: '0 0 296px', borderLeft: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 16 }}>
            {sel && selArea && (
              <div>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>BEST FIT FOR THIS SHIFT</div>
                <div style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 12, marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: selArea.color || 'var(--pb-accent)' }} />
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{selArea.name}</span>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim, marginTop: 4 }}>{DOW[sel.day_of_week]} {fmtHour(sel.start_time)}–{fmtHour(sel.end_time)}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginTop: 4 }}>{[selArea.required_role_name, selArea.required_qualification_name].filter(Boolean).join(' · ') || 'No requirement'}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button onClick={() => { if (candList[0]) doAssign(sel.id, candList[0].c.member_id) }} style={{ flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Fill best match</button>
                    <button onClick={() => { doAssign(sel.id, null); patch({ selected: null }) }} style={{ padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Clear</button>
                  </div>
                </div>
              </div>
            )}

            {sel && (
              <button onClick={async () => {
                if (!confirm('Delete this shift?')) return
                try { await api.rosterDeleteShift(sel.id); patch({ selected: null }); load() }
                catch (e) { patch({ toast: e.message }) }
              }} style={{ width: '100%', padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.block, cursor: 'pointer', marginBottom: 10 }}>
                Delete this shift
              </button>
            )}

            {addingShift
              ? <AddShift areas={areas} weekId={data.week.id}
                  onDone={() => { setAddingShift(false); load() }} onCancel={() => setAddingShift(false)} />
              : <button onClick={() => setAddingShift(true)} style={{ width: '100%', padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', marginBottom: 10 }}>+ Add a shift</button>}

            {openPerson && <PersonPanel memberId={openPerson} onClose={() => setOpenPerson(null)} onSaved={load} />}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest }}>{sel ? 'RANKED CANDIDATES' : 'VOLUNTEER POOL'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{candList.length} people</span>
            </div>
            <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.45, marginBottom: 10 }}>{view === 'areas' ? 'Drag a volunteer onto a shift, or select a shift to rank them.' : 'Drag a shift between rows, or select one to rank candidates.'}</div>
            {candidates.length === 0 && <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>No volunteers yet. Add volunteer profiles (with availability) in the Directory/Volunteers so they can be rostered.</div>}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {candList.map(({ c, res, load }) => (
                <div key={c.member_id} draggable onClick={() => { if (sel) doAssign(sel.id, c.member_id); else setOpenPerson(c.member_id) }} onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragPerson: c.member_id }) }} onDragEnd={() => patch({ dragPerson: null, overCell: null })}
                  style={{ background: C.surface2, border: `1px solid ${sel && !res.warns.length ? 'color-mix(in srgb, var(--pb-accent) 35%, transparent)' : C.hair}`, borderRadius: 8, padding: '9px 10px', cursor: 'pointer' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 26, height: 26, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 9.5, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(c.name)}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sel ? (res.warns.length ? res.warns[0] : 'Clear match · ' + load + ' shift' + (load === 1 ? '' : 's')) : (load + ' shift' + (load === 1 ? '' : 's') + ' this week')}</div>
                    </div>
                    {sel && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4, flexShrink: 0, ...(res.warns.length ? { background: 'rgba(245,181,66,0.15)', color: C.warn } : { background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: C.accent }) }}>{res.warns.length ? 'WARN' : 'FIT'}</span>}
                  </div>
                </div>
              ))}
            </div>
          </aside>
        )}
      </div>
      )}
    </div>
  )
}
