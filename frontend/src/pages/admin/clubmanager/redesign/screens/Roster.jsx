import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import { useAuth } from '../../../../../contexts/AuthContext'
import { CAP } from '../../../../../lib/capabilities'
import { C, MONO, ScreenHeader, NavToggle, Toast, initials, usePref, SegTabs, SegGroup, segItemStyle, HEAD_SIDE, HEAD_CENTRE, HEAD_SIDE_END, HeaderSearch } from '../ui'

// Roster on the real backend. Operational areas + shift patterns are config; a
// roster week materialises shifts from the patterns; assignments run through the
// server rules engine (and are mirrored client-side here for candidate ranking).

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
// The long form the volunteer-profile endpoint stores. Its `available_days` is
// typed List[str], and the roster reads it back tolerantly (day_index accepts
// names, abbreviations or indexes), so a new volunteer's days go over as names —
// the vocabulary the Volunteers screen already uses. The inline availability
// toggle writes through a different endpoint (List[int]) and stays integers.
const DOW_FULL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
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

// Client mirror of services/roster.check_assignment. The role/qualification
// requirement is the SHIFT's own now (its role, and the qualification that
// role's area-pairing gates on), not the area's.
// No `area` argument: since the multi-role migration the role/qualification
// requirement is the SHIFT's own, so the area was only ever ignored here. The
// stale guard on it (an archived area is not in the active-only areas list)
// blocked filling a shift whose area was later archived.
function checkClient(shift, cand, shifts, settings) {
  const blocks = [], warns = []
  const cap = settings.weekly_shift_cap || cand.max_shifts || DEFAULT_CAP
  if (shift.required_qualification_type_id && !cand.qual_type_ids.includes(shift.required_qualification_type_id)) {
    (settings.enforce_qualifications === false ? warns : blocks).push('Missing ' + (shift.required_qualification_name || 'required qualification'))
  }
  if (!cand.available_days.includes(shift.day_of_week)) blocks.push('Not available ' + DOW[shift.day_of_week])
  const mine = shifts.filter(s => s.assignee_member_id === cand.member_id && s.id !== shift.id)
  if (mine.some(s => s.day_of_week === shift.day_of_week && s.start_time < shift.end_time && shift.start_time < s.end_time)) blocks.push('Overlaps another shift')
  if (shift.role_id && !cand.role_ids.includes(shift.role_id)) warns.push('Not in the ' + (shift.role_name || 'required') + ' role')
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
        style={{ ...segItemStyle(open), opacity: busy ? 0.6 : 1 }}>
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
  const [f, setF] = useState({ area_id: areas[0]?.id || '', role_id: '', day_of_week: 5, start_time: '17', end_time: '21' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const inp = { padding: '6px 8px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: C.surface2, color: C.text }
  // The role this one-off shift is for, from the chosen area's palette. Picking
  // another area drops a role that isn't in the new area's palette.
  const areaRoles = (areas.find(a => a.id === f.area_id)?.roles) || []
  const roleOk = f.role_id && areaRoles.some(r => r.role_id === f.role_id)
  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 10, marginBottom: 10 }}>
      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>NEW SHIFT</div>
      <div style={{ display: 'grid', gap: 6 }}>
        <select value={f.area_id} onChange={e => setF(v => ({ ...v, area_id: e.target.value, role_id: '' }))} style={inp}>
          {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        {areaRoles.length > 0 && (
          <select value={roleOk ? f.role_id : ''} onChange={e => setF(v => ({ ...v, role_id: e.target.value }))} style={inp} data-testid="add-shift-role">
            <option value="">Any role</option>
            {areaRoles.map(r => <option key={r.role_id} value={r.role_id}>{r.role_name}</option>)}
          </select>
        )}
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
                role_id: roleOk ? f.role_id : null,
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

// Confirming the roster.
//
// The grid is what the club INTENDED. This is where someone says what actually
// happened: every filled shift, its hours open to correction, and one button
// that writes them into the volunteer hours ledger. Hours default to the
// rostered length because that is right most weeks; the point of the screen is
// the handful of rows where it is not.
function ConfirmRoster({ weekId, onDone, onToast }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [edits, setEdits] = useState({})     // shift_id -> hours, as typed

  const load = () => api.rosterConfirmReview(weekId)
    .then(r => { setD(r); setEdits({}) })
    .catch(e => setErr((e?.status ? `HTTP ${e.status} · ` : '') + String(e?.message || e)))
  useEffect(() => { load() }, [weekId])

  const entries = () => Object.entries(edits)
    .filter(([, v]) => v !== '' && !Number.isNaN(Number(v)))
    .map(([shift_id, v]) => ({ shift_id, hours: Number(v) }))

  const hoursFor = r => (edits[r.shift_id] !== undefined ? edits[r.shift_id] : r.worked_hours)
  const num = v => (v === '' || v == null || Number.isNaN(Number(v)) ? 0 : Number(v))

  async function save() {
    setBusy(true)
    try { await api.rosterSaveWorkedHours(weekId, entries()); await load(); onToast({ tone: 'ok', title: 'Hours saved.', body: 'The roster is not confirmed yet.' }) }
    catch (e) { onToast({ tone: 'block', title: 'Could not save.', body: String(e?.message || e) }) }
    finally { setBusy(false) }
  }
  async function confirm() {
    setBusy(true)
    try {
      const res = await api.rosterConfirm(weekId, entries())
      await load(); onDone?.()
      onToast({ tone: 'ok', title: 'Roster confirmed.',
        body: `${res.posted} shift${res.posted === 1 ? '' : 's'} recorded against the volunteers who worked them.`
          + (res.removed ? ` ${res.removed} withdrawn.` : '') })
    } catch (e) { onToast({ tone: 'block', title: 'Could not confirm the roster.', body: String(e?.message || e) }) }
    finally { setBusy(false) }
  }
  async function unconfirm() {
    setBusy(true)
    try { await api.rosterUnconfirm(weekId); await load(); onDone?.()
      onToast({ tone: 'info', title: 'Reopened for editing.', body: 'The hours already recorded stay as they are until you confirm again.' }) }
    catch (e) { onToast({ tone: 'block', title: 'Could not reopen.', body: String(e?.message || e) }) }
    finally { setBusy(false) }
  }

  if (err) return <div style={{ padding: 22, fontSize: 13, color: C.block }}>{err}</div>
  if (!d) return <div style={{ padding: 22, fontFamily: MONO, fontSize: 10, color: C.faintest }}>Loading the week…</div>

  const confirmed = d.week.status === 'confirmed'
  const dirty = Object.keys(edits).length > 0
  const live = d.rows.reduce((acc, r) => {
    const h = num(hoursFor(r))
    acc.total += h; acc[r.is_paid ? 'paid' : 'volunteer'] += h
    return acc
  }, { total: 0, paid: 0, volunteer: 0 })
  const byDay = {}
  d.rows.forEach(r => { (byDay[r.day_of_week] = byDay[r.day_of_week] || []).push(r) })
  const hrs = n => (Math.round(n * 10) / 10).toString()

  return (
    <div className="pb-scroll" style={{ flex: 1, overflow: 'auto', padding: '18px 22px' }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>
        {[['Shifts worked', d.rows.length], ['Total hours', hrs(live.total)],
          ['Volunteer', hrs(live.volunteer)], ['Paid', hrs(live.paid)]].map(([label, v], i) => (
          <div key={label} style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 10, padding: '10px 14px', minWidth: 118 }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest }}>{label.toUpperCase()}</div>
            <div style={{ fontSize: 19, fontWeight: 700, marginTop: 3, fontVariantNumeric: 'tabular-nums', color: i === 3 ? C.warn : C.text }}>{v}</div>
          </div>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {confirmed && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.1em', color: C.ok }}>CONFIRMED</span>}
          {!confirmed && dirty && (
            <button disabled={busy} onClick={save}
              style={{ padding: '8px 13px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Save without confirming</button>
          )}
          {confirmed
            ? <button disabled={busy} onClick={unconfirm}
                style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Reopen to edit</button>
            : <button disabled={busy || !d.rows.length} onClick={confirm}
                style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#0a0d14', cursor: 'pointer', opacity: (busy || !d.rows.length) ? 0.6 : 1 }}>Confirm roster</button>}
        </div>
      </div>

      {d.open_shifts > 0 && !confirmed && (
        <div style={{ background: 'rgba(245,181,66,0.08)', border: '1px solid rgba(245,181,66,0.35)', borderRadius: 9, padding: '10px 14px', fontSize: 12.5, color: C.dim, marginBottom: 14, lineHeight: 1.55 }}>
          {d.open_shifts} shift{d.open_shifts === 1 ? '' : 's'} nobody was rostered to. Confirming records only the shifts below; the open ones are left as they are.
        </div>
      )}

      {d.rows.length === 0 ? (
        <div style={{ fontSize: 13, color: C.faint, maxWidth: '46rem', lineHeight: 1.6 }}>
          Nobody is rostered this week, so there are no hours to confirm. Fill some shifts on the People or Areas view first.
        </div>
      ) : (
        <div style={{ border: `1px solid ${C.hair}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 150px 96px 108px 84px', background: C.surface2, borderBottom: `1px solid ${C.hair}` }}>
            {['VOLUNTEER', 'AREA', 'ROSTERED', 'HOURS WORKED', 'KIND'].map((h, i) => (
              <div key={h} style={{ padding: '9px 12px', fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest, textAlign: i === 2 || i === 3 ? 'right' : 'left' }}>{h}</div>
            ))}
          </div>
          {Object.keys(byDay).sort((a, b) => a - b).map(day => (
            <div key={day}>
              <div style={{ padding: '6px 12px', background: C.surface, borderBottom: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.dim }}>{DOW[day]}</div>
              {byDay[day].map(r => {
                const changed = edits[r.shift_id] !== undefined && num(edits[r.shift_id]) !== r.rostered_hours
                return (
                  <div key={r.shift_id} style={{ display: 'grid', gridTemplateColumns: '1fr 150px 96px 108px 84px', borderBottom: `1px solid ${C.hair}`, alignItems: 'center' }}>
                    <div style={{ padding: '8px 12px', fontSize: 13, fontWeight: 600 }}>{r.full_name}</div>
                    <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: r.color || 'var(--pb-accent)' }} />
                      <span style={{ fontSize: 12.5, color: C.dim, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.area_name}{r.role_name ? ' · ' + r.role_name : ''}</span>
                    </div>
                    <div style={{ padding: '8px 12px', textAlign: 'right', fontFamily: MONO, fontSize: 11.5, color: C.faint, fontVariantNumeric: 'tabular-nums' }}>
                      {hrs(r.rostered_hours)}
                    </div>
                    <div style={{ padding: '6px 12px', textAlign: 'right' }}>
                      <input type="number" step="0.25" min="0" max="24" disabled={confirmed}
                        value={hoursFor(r)}
                        onChange={e => setEdits(s => ({ ...s, [r.shift_id]: e.target.value }))}
                        style={{ width: 72, textAlign: 'right', padding: '5px 7px', borderRadius: 6, fontFamily: MONO, fontSize: 12,
                          border: `1px solid ${changed ? 'var(--pb-accent)' : C.hair2}`, background: confirmed ? 'transparent' : C.surface2, color: C.text }} />
                    </div>
                    <div style={{ padding: '8px 12px' }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4,
                        ...(r.is_paid ? { background: 'rgba(245,181,66,0.15)', color: C.warn } : { background: C.surface2, color: C.faint }) }}>
                        {r.is_paid ? 'PAID' : 'VOLUNTEER'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, color: C.faint, marginTop: 14, maxWidth: '52ch', lineHeight: 1.6 }}>
        Set a volunteer's hours to zero if they did not turn up. Confirming again after a
        correction updates what was already recorded rather than adding to it.
      </div>
    </div>
  )
}

// A shared field style for the small forms/modals below.
const inpStyle = { padding: '6px 8px', borderRadius: 6, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: C.surface2, color: C.text }

// A small centred modal shell. Declared at MODULE level (never inside a render)
// so its child inputs keep their caret across re-renders.
function ModalShell({ title, sub, onClose, children, maxWidth = 460 }) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} className="pb-scroll" data-testid="roster-modal"
        style={{ width: '100%', maxWidth, maxHeight: '86vh', overflow: 'auto', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 18, boxShadow: '0 20px 60px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: sub ? 4 : 10 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{title}</div>
          <button onClick={onClose} style={{ fontFamily: MONO, fontSize: 10.5, background: 'none', border: 'none', color: C.faint, cursor: 'pointer', paddingTop: 3 }}>close</button>
        </div>
        {sub && <div style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint, marginBottom: 12 }}>{sub}</div>}
        {children}
      </div>
    </div>
  )
}

// A ranked, clickable list of volunteers for a shift — available first, blocked
// hidden, warnings noted. Shared by the assign modal (Areas view) and reused for
// the "add a shift" flow. Uses the same rule mirror the side pool ranks with.
function CandidatePicker({ shift, candidates, shifts, settings, onPick }) {
  const [q, setQ] = useState('')
  const ranked = candidates
    .map(c => ({ c, res: checkClient(shift, c, shifts, settings), load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))
    .filter(x => x.res.blocks.length === 0)
    .sort((a, b) => (a.res.warns.length * 10 + a.load) - (b.res.warns.length * 10 + b.load))
  const term = q.trim().toLowerCase()
  const list = term ? ranked.filter(x => x.c.name.toLowerCase().includes(term) || (x.c.role_names || []).some(r => r.toLowerCase().includes(term))) : ranked
  const blockedCount = candidates.length - ranked.length
  return (
    <div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search a volunteer…" autoFocus
        data-testid="assign-search" style={{ ...inpStyle, width: '100%', marginBottom: 8 }} />
      {list.length === 0 ? (
        <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5, padding: '6px 0' }}>
          {candidates.length === 0 ? 'No volunteers on file yet.' : `Nobody available and qualified for this shift${blockedCount ? ` (${blockedCount} blocked by the rules)` : ''}.`}
        </div>
      ) : (
        <div className="pb-scroll" data-testid="assign-candidates" style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflow: 'auto' }}>
          {list.map(({ c, res, load }) => (
            <button key={c.member_id} onClick={() => onPick(c.member_id)} data-testid={`assign-cand-${c.member_id}`}
              style={{ textAlign: 'left', background: C.surface2, border: `1px solid ${res.warns.length ? 'rgba(245,181,66,0.4)' : C.hair}`, borderRadius: 8, padding: '8px 10px', cursor: 'pointer', color: C.text }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 24, height: 24, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 9, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(c.name)}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{res.warns.length ? res.warns[0] : 'Clear match · ' + load + ' shift' + (load === 1 ? '' : 's')}</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4, flexShrink: 0, ...(res.warns.length ? { background: 'rgba(245,181,66,0.15)', color: C.warn } : { background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: C.accent }) }}>{res.warns.length ? 'WARN' : 'FIT'}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Areas view: clicking a shift that nobody is on opens this so a volunteer can be
// picked without hunting through the side pool — it works whether the pool is
// open or minimised. Fill best match / Clear sit above the picker.
function AssignModal({ shift, areaName, candidates, shifts, settings, onPick, onFillBest, onClear, onClose }) {
  return (
    <ModalShell title={`Assign · ${areaName}`}
      sub={`${shift.role_name ? shift.role_name + ' · ' : ''}${DOW[shift.day_of_week]} ${fmtHour(shift.start_time)}–${fmtHour(shift.end_time)}`}
      onClose={onClose}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button onClick={onFillBest} data-testid="assign-fill-best" style={{ flex: 1, padding: '7px 10px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Fill best match</button>
        <button onClick={onClear} data-testid="assign-clear" style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Clear</button>
      </div>
      <CandidatePicker shift={shift} candidates={candidates} shifts={shifts} settings={settings} onPick={onPick} />
    </ModalShell>
  )
}

// People view: a volunteer's free day with no shift on it shows a "+ add" link;
// this lists the day's open shifts so one can be handed straight to them. A shift
// the rules block for this person is shown disabled, with the reason.
function AddOpenShiftModal({ personName, cand, day, openShifts, shifts, settings, areaLabelFor, onPick, onClose }) {
  const forDay = openShifts.filter(s => s.day_of_week === day)
  return (
    <ModalShell title={`Add ${personName} to a shift`} sub={`Open shifts on ${DOW[day]}`} onClose={onClose}>
      {forDay.length === 0 ? (
        <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>No open shifts on {DOW[day]}. Add one from the Areas view, or the “+ Add a shift” panel.</div>
      ) : (
        <div className="pb-scroll" data-testid="add-open-list" style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflow: 'auto' }}>
          {forDay.map(s => {
            const res = cand ? checkClient(s, cand, shifts, settings) : { blocks: [], warns: [] }
            const blocked = res.blocks.length > 0
            return (
              <button key={s.id} disabled={blocked} onClick={() => !blocked && onPick(s.id)}
                data-testid={`add-open-shift-${s.id}`} title={blocked ? res.blocks.join(' · ') : (res.warns.join(' · ') || undefined)}
                style={{ textAlign: 'left', background: C.surface2, border: `1px solid ${blocked ? C.hair : (res.warns.length ? 'rgba(245,181,66,0.4)' : 'color-mix(in srgb, var(--pb-accent) 30%, transparent)')}`, borderRadius: 8, padding: '8px 10px', cursor: blocked ? 'not-allowed' : 'pointer', color: C.text, opacity: blocked ? 0.55 : 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 12.5 }}>{areaLabelFor(s)}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, color: C.faint }}>{fmtHour(s.start_time)}–{fmtHour(s.end_time)}</span>
                </div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: blocked ? C.block : (res.warns.length ? C.warn : C.faint), marginTop: 3 }}>
                  {s.role_name || 'General help'}{blocked ? ' · ' + res.blocks[0] : (res.warns.length ? ' · ' + res.warns[0] : '')}
                </div>
              </button>
            )
          })}
        </div>
      )}
    </ModalShell>
  )
}

// Areas view: an empty day cell offers "+ Add" to create a one-off shift there —
// its role (from the area's palette, prefilled to the row's own role) and time —
// and hand it straight to a volunteer, all in one step.
function NewAreaShiftModal({ area, day, roleId, candidates, shifts, settings, onCreate, onClose }) {
  const palette = area.roles || []
  const [f, setF] = useState({ role_id: roleId || '', start_time: '17', end_time: '21' })
  const [assignee, setAssignee] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const start = Number(f.start_time), end = Number(f.end_time)
  const role = palette.find(r => r.role_id === f.role_id)
  // Preview candidate fit against the shift being defined, so the volunteer
  // dropdown only offers people who can actually take it.
  const hypo = {
    id: '__new', area_id: area.id, day_of_week: day, start_time: start, end_time: end,
    role_id: f.role_id || null, role_name: role?.role_name,
    required_qualification_type_id: role?.required_qualification_type_id || null,
    required_qualification_name: role?.required_qualification_name || null,
  }
  const available = candidates
    .map(c => ({ c, res: checkClient(hypo, c, shifts, settings) }))
    .filter(x => x.res.blocks.length === 0)
    .sort((a, b) => a.res.warns.length - b.res.warns.length || a.c.name.localeCompare(b.c.name))
  return (
    <ModalShell title={`Add a shift · ${area.name}`} sub={`${DOW[day]} · new shift`} onClose={onClose}>
      <div style={{ display: 'grid', gap: 8 }}>
        <label style={{ display: 'grid', gap: 3 }}>
          <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest }}>ROLE</span>
          <select value={f.role_id} onChange={e => { setF(v => ({ ...v, role_id: e.target.value })); setAssignee('') }} style={inpStyle} data-testid="new-area-shift-role">
            <option value="">General help (no role)</option>
            {palette.map(r => <option key={r.role_id} value={r.role_id}>{r.role_name}{r.required_qualification_name ? ` · needs ${r.required_qualification_name}` : ''}</option>)}
          </select>
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          <label style={{ display: 'grid', gap: 3, flex: 1 }}>
            <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest }}>FROM</span>
            <input type="number" step="0.25" min="0" max="24" value={f.start_time} onChange={e => setF(v => ({ ...v, start_time: e.target.value }))} style={inpStyle} data-testid="new-area-shift-start" />
          </label>
          <label style={{ display: 'grid', gap: 3, flex: 1 }}>
            <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest }}>TO</span>
            <input type="number" step="0.25" min="0" max="24" value={f.end_time} onChange={e => setF(v => ({ ...v, end_time: e.target.value }))} style={inpStyle} data-testid="new-area-shift-end" />
          </label>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 9, color: C.faintest }}>Times are 24-hour, so 17.5 is 5:30pm.</div>
        <label style={{ display: 'grid', gap: 3 }}>
          <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest }}>ASSIGN A VOLUNTEER (OPTIONAL)</span>
          <select value={assignee} onChange={e => setAssignee(e.target.value)} style={inpStyle} data-testid="new-area-shift-assignee">
            <option value="">— leave open —</option>
            {available.map(({ c, res }) => <option key={c.member_id} value={c.member_id}>{c.name}{res.warns.length ? ' (warning)' : ''}</option>)}
          </select>
        </label>
        {err && <div style={{ fontSize: 11.5, color: C.block }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
          <button disabled={busy} data-testid="new-area-shift-create" onClick={async () => {
            if (!(end > start)) { setErr('A shift has to finish after it starts.'); return }
            setBusy(true); setErr(null)
            try { await onCreate({ start_time: start, end_time: end, role_id: f.role_id || null, assignee: assignee || null }) }
            catch (e) { setErr(String(e?.message || e)); setBusy(false) }
          }} style={{ flex: 1, padding: '7px 10px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
            {busy ? 'Adding…' : (assignee ? 'Add shift & assign' : 'Add shift')}
          </button>
          <button onClick={onClose} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Cancel</button>
        </div>
      </div>
    </ModalShell>
  )
}

// Clicking a shift lets its day and time be changed in place, and it deleted.
// Rendered with key={shift.id} where it sits, so switching shifts reseeds it.
function ShiftEditForm({ shift, onSave, onDelete, busy }) {
  const [day, setDay] = useState(shift.day_of_week)
  const [start, setStart] = useState(String(shift.start_time))
  const [end, setEnd] = useState(String(shift.end_time))
  const [err, setErr] = useState(null)
  const changed = day !== shift.day_of_week || Number(start) !== shift.start_time || Number(end) !== shift.end_time
  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 10, marginBottom: 10 }}>
      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>EDIT DAY &amp; TIME</div>
      <div style={{ display: 'grid', gap: 6 }}>
        <select value={day} onChange={e => setDay(Number(e.target.value))} style={{ ...inpStyle, fontSize: 12 }} data-testid="edit-shift-day">
          {DOW.map((d, i) => <option key={i} value={i}>{d}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="number" step="0.25" min="0" max="24" value={start} onChange={e => setStart(e.target.value)} style={{ ...inpStyle, flex: 1, fontSize: 12 }} placeholder="From" data-testid="edit-shift-start" />
          <input type="number" step="0.25" min="0" max="24" value={end} onChange={e => setEnd(e.target.value)} style={{ ...inpStyle, flex: 1, fontSize: 12 }} placeholder="To" data-testid="edit-shift-end" />
        </div>
        {err && <div style={{ fontSize: 11.5, color: C.block }}>{err}</div>}
        <div style={{ display: 'flex', gap: 6 }}>
          <button disabled={busy || !changed} data-testid="edit-shift-save" onClick={() => {
            const s = Number(start), e = Number(end)
            if (!(e > s)) { setErr('A shift has to finish after it starts.'); return }
            setErr(null); onSave({ day_of_week: day, start_time: s, end_time: e })
          }} style={{ flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, border: 'none', background: changed ? C.accent : C.surface, color: changed ? '#fff' : C.faint, cursor: changed ? 'pointer' : 'default', opacity: busy ? 0.6 : 1 }}>Save changes</button>
          <button disabled={busy} data-testid="edit-shift-delete" onClick={onDelete}
            style={{ padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.block, cursor: 'pointer' }}>Delete</button>
        </div>
      </div>
    </div>
  )
}

// The seven day-of-week toggles, shown inline on the People rail when a
// volunteer is expanded so their availability is set where they are read rather
// than in a panel on the other side of the screen. stopPropagation on the row
// so a day tap does not also collapse the person it belongs to.
function AvailabilityRow({ days, onToggle, testid }) {
  return (
    <div data-testid={testid} onClick={e => e.stopPropagation()}
      style={{ display: 'flex', gap: 3, flexWrap: 'wrap', marginTop: 7 }}>
      {DOW.map((label, i) => {
        const on = (days || []).includes(i)
        return (
          <button key={i} onClick={() => onToggle(i)} data-testid={`${testid}-${i}`}
            style={{ padding: '3px 6px', borderRadius: 5, fontFamily: MONO, fontSize: 9.5, cursor: 'pointer',
              border: `1px solid ${on ? 'transparent' : C.hair2}`,
              background: on ? C.accent : 'transparent', color: on ? '#fff' : C.faint }}>{label}</button>
        )
      })}
    </div>
  )
}

// The "+ Add" beside a volunteer's roles: pick a club role they don't already
// hold. Roles already assigned are left out so the list is only ever additions.
function AddRoleModal({ memberName, currentIds, roles, onPick, onClose }) {
  const [q, setQ] = useState('')
  const avail = roles.filter(r => !currentIds.includes(r.id))
  const term = q.trim().toLowerCase()
  const list = term ? avail.filter(r => r.title.toLowerCase().includes(term)) : avail
  return (
    <ModalShell title={`Add a role · ${memberName}`} onClose={onClose} maxWidth={380}>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search a role…" autoFocus
        data-testid="add-role-search" style={{ ...inpStyle, width: '100%', marginBottom: 8 }} />
      {list.length === 0 ? (
        <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5, padding: '4px 0' }}>
          {roles.length === 0 ? 'No roles set up yet. Add them in Areas & Roles.'
            : avail.length === 0 ? 'They already hold every role.' : 'No role matches.'}
        </div>
      ) : (
        <div className="pb-scroll" data-testid="add-role-list" style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 300, overflow: 'auto' }}>
          {list.map(r => (
            <button key={r.id} onClick={() => onPick(r.id)} data-testid={`add-role-opt-${r.id}`}
              style={{ textAlign: 'left', background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '8px 10px', cursor: 'pointer', color: C.text, fontSize: 13, fontWeight: 600 }}>{r.title}</button>
          ))}
        </div>
      )}
    </ModalShell>
  )
}

// The "+ Add volunteer" launcher opens this: search every club member, pick one,
// and give them a volunteer profile in one step — the roles they cover, the days
// they can do, and (only where the user holds MANAGE_QUALIFICATIONS) any
// accreditations. A member who is already a volunteer is not hidden; picking
// them updates their profile rather than making a second one.
function AddVolunteerModal({ roles, qualTypes, canQuals, onAdd, onClose }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [picked, setPicked] = useState(null)   // { member_id, full_name, is_volunteer }
  const [roleIds, setRoleIds] = useState([])
  const [days, setDays] = useState([])
  const [qualIds, setQualIds] = useState([])
  const [more, setMore] = useState(false)   // the club has more members than shown
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const seq = useRef(0)
  // A big club has hundreds of members, so the list is capped and the search is
  // the way to the rest — the same trade the volunteer pool makes. The note
  // below says so, so a first page of A-surnames doesn't read as the whole club.
  const LIMIT = 50

  // Debounced member search. A stale response is dropped (the sequence guard),
  // so a slow search for "sm" never lands on top of the results for "smith".
  // Once a member is picked the search stops entirely.
  useEffect(() => {
    if (picked) return
    const term = q.trim()
    const mine = ++seq.current
    setSearching(true)
    const t = setTimeout(async () => {
      try {
        const r = await api.volunteerSearchMembers(term || undefined, LIMIT)
        if (seq.current === mine) { setResults(r.members || []); setMore(!!r.more) }
      } catch { if (seq.current === mine) { setResults([]); setMore(false) } }
      finally { if (seq.current === mine) setSearching(false) }
    }, 220)
    return () => clearTimeout(t)
  }, [q, picked])

  const toggleRole = id => setRoleIds(v => v.includes(id) ? v.filter(x => x !== id) : [...v, id])
  const toggleDay = i => setDays(v => v.includes(i) ? v.filter(x => x !== i) : [...v, i].sort((a, b) => a - b))
  const toggleQual = id => setQualIds(v => v.includes(id) ? v.filter(x => x !== id) : [...v, id])

  async function submit() {
    setBusy(true); setErr(null)
    try { await onAdd({ member_id: picked.member_id, role_ids: roleIds, days, qual_ids: qualIds }) }
    catch (e) { setErr(String(e?.message || e)); setBusy(false) }
  }

  const chip = (on) => ({ padding: '4px 9px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
    border: `1px solid ${on ? 'transparent' : C.hair2}`, background: on ? C.accent : 'transparent', color: on ? '#fff' : C.dim })

  return (
    <ModalShell title="Add a volunteer" sub={picked ? picked.full_name : 'Pick a club member'} onClose={onClose}>
      {!picked ? (
        <div>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search club members…" autoFocus
            data-testid="add-vol-search" style={{ ...inpStyle, width: '100%', marginBottom: 8 }} />
          {searching && <div style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, padding: '4px 0' }}>Searching…</div>}
          {!searching && results.length === 0 && <div style={{ fontSize: 12.5, color: C.faint, padding: '4px 0' }}>No members found.</div>}
          <div className="pb-scroll" data-testid="add-vol-results" style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 320, overflow: 'auto' }}>
            {results.map(m => (
              <button key={m.member_id} onClick={() => setPicked(m)} data-testid={`add-vol-member-${m.member_id}`}
                style={{ textAlign: 'left', background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '8px 10px', cursor: 'pointer', color: C.text, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 24, height: 24, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 9, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(m.full_name)}</span>
                <span style={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.full_name}</span>
                {m.is_volunteer && <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '0.06em', padding: '2px 5px', borderRadius: 4, flexShrink: 0, background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: C.accent }}>ALREADY IN</span>}
              </button>
            ))}
          </div>
          {/* The list is capped, so a first page of A-surnames is not the whole
              club. Say so, and point at the search — the way to everyone else. */}
          {more && !searching && (
            <div data-testid="add-vol-more" style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, letterSpacing: '0.04em', padding: '8px 2px 2px', lineHeight: 1.5 }}>
              {q.trim()
                ? `Showing the first ${results.length} matches — keep typing to narrow.`
                : `Showing the first ${results.length} members — search by name to find anyone else.`}
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {picked.is_volunteer && (
            <div style={{ fontSize: 11.5, color: C.warn, lineHeight: 1.45 }}>{picked.full_name} is already a volunteer — this updates their profile.</div>
          )}
          <div>
            <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest, marginBottom: 5 }}>VOLUNTEER ROLES</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {roles.length === 0 && <div style={{ fontSize: 12, color: C.faint }}>No roles set up yet.</div>}
              {roles.map(r => (
                <button key={r.id} onClick={() => toggleRole(r.id)} data-testid={`add-vol-role-${r.id}`} style={chip(roleIds.includes(r.id))}>{r.title}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest, marginBottom: 5 }}>AVAILABLE</div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {DOW.map((label, i) => {
                const on = days.includes(i)
                return (
                  <button key={i} onClick={() => toggleDay(i)} data-testid={`add-vol-day-${i}`}
                    style={{ padding: '4px 8px', borderRadius: 6, fontFamily: MONO, fontSize: 10, cursor: 'pointer', border: `1px solid ${on ? 'transparent' : C.hair2}`, background: on ? C.accent : 'transparent', color: on ? '#fff' : C.faint }}>{label}</button>
                )
              })}
            </div>
          </div>
          {canQuals && qualTypes.length > 0 && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.12em', color: C.faintest, marginBottom: 5 }}>QUALIFICATIONS (OPTIONAL)</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {qualTypes.map(t => (
                  <button key={t.id} onClick={() => toggleQual(t.id)} data-testid={`add-vol-qual-${t.id}`} style={chip(qualIds.includes(t.id))}>{t.name}</button>
                ))}
              </div>
            </div>
          )}
          {err && <div style={{ fontSize: 11.5, color: C.block }}>{err}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button disabled={busy} onClick={submit} data-testid="add-vol-save"
              style={{ flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              {busy ? 'Adding…' : (picked.is_volunteer ? 'Update volunteer' : 'Add to volunteer pool')}
            </button>
            <button disabled={busy} onClick={() => setPicked(null)}
              style={{ padding: '8px 12px', borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Back</button>
          </div>
        </div>
      )}
    </ModalShell>
  )
}

export default function Roster({ st, patch, narrow }) {
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  // Choosing what lands in a volunteer's own profile only needs MANAGE_VOLUNTEERS;
  // recording an accreditation is MANAGE_QUALIFICATIONS, which a roster user may
  // not hold — so the optional-qualifications half of "add a volunteer" is gated
  // on it rather than widening the roster capability.
  const canQuals = hasCapability(CAP.MANAGE_QUALIFICATIONS)
  const [data, setData] = useState(null)  // { week, areas, candidates, settings }
  const [shifts, setShifts] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [addingShift, setAddingShift] = useState(false)
  const [openPerson, setOpenPerson] = useState(null)
  // Modals: assign a volunteer to an unassigned shift (Areas view), add an
  // available person to one of a day's open shifts (People view "+ add"), and
  // create a one-off shift in a blank Areas cell (Areas view "+ Add").
  const [assignFor, setAssignFor] = useState(null)   // shift id
  const [addFor, setAddFor] = useState(null)         // { personId, day }
  const [addAreaFor, setAddAreaFor] = useState(null) // { areaId, day, roleId }
  // People rail (left column): add a volunteer from the club member list, add a
  // role to one, and expand a volunteer to set their availability inline.
  const [addVolOpen, setAddVolOpen] = useState(false)
  const [addRoleFor, setAddRoleFor] = useState(null) // member id
  const [expandedPerson, setExpandedPerson] = useState(null) // member id
  // The club's role catalogue and qualification types, for the two add flows.
  // Fetched once; a role/qual list is small and does not change mid-session.
  const [allRoles, setAllRoles] = useState([])
  const [qualTypes, setQualTypes] = useState([])
  // Both of these belong to the person, not the club, and both survive the
  // browser closing. A club with fourteen operational areas wants the first
  // column narrow; one with three does not.
  const [railMin, setRailMin] = usePref('roster_rail_min', false)
  const [poolOpen, setPoolOpen] = usePref('roster_pool_open', true)
  // Which operational areas have their roles collapsed on the Areas view. An
  // area is a set of roles now (Umpire, Scorer, Turf Curator…) and shifts are
  // created per role, so the grid draws a sub-row per role by default; this
  // remembers the ones a person has folded away. Keyed by area, so a club with
  // one Match Day area folded keeps the rest open.
  const [areasCollapsed, setAreasCollapsed] = usePref('roster_areas_collapsed', {})
  // Pool search / role filter / sort. Deliberately NOT a saved preference —
  // a filter you left on last week hiding half the club is worse than retyping.
  const [poolQuery, setPoolQuery] = useState('')
  const [poolRole, setPoolRole] = useState('')
  const [poolSort, setPoolSort] = useState('fit')   // 'fit' | 'name'

  // api.js stamps the HTTP status onto the error, which is the difference
  // between "you lack a capability" (403) and "the server threw" (500).
  // st.rosterWeek is how another screen hands us a week — Events uses it for
  // "Roster this event" so you land on the week the event falls in.
  const load = () => api.rosterWeek(st.rosterWeek)
    .then(res => { setData(res); setShifts(res.week.shifts || []) })
    .catch(e => setErr((e?.status ? `HTTP ${e.status} · ` : '') + String(e?.message || e)))
  useEffect(() => { load() }, [st.rosterWeek])
  // Roles are shown as pickers (add a volunteer, add a role), so they read by
  // NAME alphabetically rather than in the catalogue's own sort order.
  useEffect(() => {
    api.raRoles({ committee: false })
      .then(r => setAllRoles((r.roles || []).slice().sort((a, b) => (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase()))))
      .catch(() => {})
  }, [])
  useEffect(() => { if (canQuals) api.qualListTypes(false).then(r => setQualTypes(r.types || [])).catch(() => {}) }, [canQuals])

  const view = st.view
  // The first column carries who or what each row is, so it has to stay put
  // while the days scroll sideways — reading a shift you can no longer attach
  // to a name is worthless. Minimised it keeps just enough to identify a row.
  const railW = railMin ? 52 : (narrow ? 176 : 216)
  const gridCols = `${railW}px repeat(7, ${narrow ? 'minmax(0, 1fr)' : 'minmax(150px, 1fr)'})`
  const rail = (extra = {}) => ({
    position: 'sticky', left: 0, zIndex: 12, background: C.bg,
    borderRight: `1px solid ${C.hair2}`, ...extra,
  })

  // NEVER DECLARE A COMPONENT INSIDE A RENDER — a `const X = () => …` written
  // here is a new element type on every render, so React rebuilds its whole
  // subtree and any focused input inside it loses the caret after one
  // character. This is a plain function returning elements, called below.
  // DECLARED ABOVE `header` DELIBERATELY. The header draws the week's primary
  // action, and two of the three `header(...)` calls are in early returns that
  // run before this point in the render body — so leaving it further down made
  // the "no operational areas yet" screen throw on a `const` in its temporal
  // dead zone. Nothing between here and where it used to sit is read by it.
  const publish = async () => {
    const res = await api.rosterPublish(data.week.id).catch(() => null)
    if (!res) return
    setData(d => ({ ...d, week: { ...d.week, status: 'published' } }))
    patch({ toast: res.open
      ? { tone: 'warn', title: 'Published with ' + res.open + ' open shift' + (res.open === 1 ? '' : 's') + '.', body: 'Volunteers can self-nominate for the gaps; you confirm each one.' }
      : { tone: 'ok', title: 'Week published.', body: 'Everyone rostered gets their shift and a check-in tap that logs their hours.' } })
  }

  const header = (children) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div style={HEAD_SIDE}>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Roster</h1>
        <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint, marginTop: 2 }}>{data?.week ? 'WEEK OF ' + weekDates(data.week.week_start)[0].toUpperCase() + (data.week.status === 'published' ? ' · PUBLISHED' : (data.week.status === 'confirmed' ? ' · CONFIRMED' : '')) : 'THIS WEEK'}</div>
      </div>
      {children}
      {/* The search sits on its own line under the heading, the place every
          Committee screen and the Directory carry theirs. `flex: 1 1 100%` is
          what makes the wrapping header break before it. */}
      <HeaderSearch value={st.rosterQuery} onChange={v => patch({ rosterQuery: v })}
        placeholder="Search people, areas, roles and shifts…"
        // The week's primary action rides on the search line rather than up in
        // the right-hand group, where it wrapped onto a line of its own.
        // Withheld on Hours and Confirm for the same reason the rest of that
        // group is: neither of those is the shift grid.
        trailing={data && view !== 'hours' && view !== 'confirm' ? (
          <button onClick={publish} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Publish week</button>
        ) : null} />
    </ScreenHeader>
  )

  // A failure here used to read "Could not load the roster." and nothing else,
  // which is the same message whether the club lacks a capability, the request
  // timed out, or the server threw. Say which, so it can be acted on.
  if (!data) return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {header(null)}
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

  // A shift now names its own area (`area_name`, off the shift row), so a chip
  // never depends on the area being in the active-areas list to label it — a
  // shift whose area was archived reads as its real area, and a role-only /
  // orphaned shift still says SOMETHING rather than the literal "undefined".
  const areaLabel = (shift) => shift.area_name || areaById[shift.area_id]?.name || shift.role_name || 'Shift'

  // The roster shows an area's shifts; Areas & Roles is where they are created,
  // re-timed and removed. Clicking the name takes you there with that area
  // already open, rather than making you find it in the list a second time.
  const openArea = (a) => navigate(`/admin/clubhouse/areas-roles?tab=areas&area=${a.id}`)
  const areaLinkStyle = { cursor: 'pointer', textDecoration: 'underline dotted', textDecorationColor: C.faint, textUnderlineOffset: 3 }

  // no config yet → offer to seed a starter set (also handy for testing)
  if (areas.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        {header(null)}
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
  const resetWeek = async () => {
    if (!window.confirm('Reset this week? Every assignment is cleared and the shifts are regenerated from your patterns. This only affects this week.')) return
    const res = await api.rosterReset(data.week.id).catch(() => null)
    if (!res) return
    setShifts(res.shifts || [])
    setData(d => ({ ...d, week: { ...d.week, status: 'draft' } }))
    patch({ toast: { tone: 'info', title: 'Week reset.', body: 'Every shift is open again.' } })
  }

  // The best-fitting volunteer for a shift — the first the rules don't block,
  // ranked by fewest warnings then lightest week. Used by "Fill best match".
  const bestFor = (shift) => {
    const r = candidates
      .map(c => ({ c, res: checkClient(shift, c, shifts, settings), load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))
      .filter(x => x.res.blocks.length === 0)
      .sort((a, b) => (a.res.warns.length * 10 + a.load) - (b.res.warns.length * 10 + b.load))
    return r[0]?.c.member_id || null
  }

  // Move a shift to a new day/time (and, in the People view, a new person).
  //
  // A shift is a first-class row now, so it can be dragged to another day or
  // edited in place. `want` carries the intended day/time (and area/role); the
  // position change goes through PATCH /shifts. `assignTo` is the member it
  // should end up on — undefined KEEPS whoever is on it (an Areas-view day move
  // or an in-place edit), a member id reassigns it (a People-view drop). If the
  // new position no longer suits the assignee (e.g. they aren't available the
  // new day), the shift is left open rather than in a half-moved state.
  const relocateShift = async (shiftId, want, assignTo) => {
    const shift = shifts.find(s => s.id === shiftId)
    if (!shift) return
    const fields = {}
    if (want.day_of_week != null && want.day_of_week !== shift.day_of_week) fields.day_of_week = want.day_of_week
    if (want.area_id && want.area_id !== shift.area_id) fields.area_id = want.area_id
    if ('role_id' in want && (want.role_id || null) !== (shift.role_id || null)) fields.role_id = want.role_id || null
    // Times are coupled: send both whenever either changes, so the server can
    // check the shift still finishes after it starts.
    const timeChanged = (want.start_time != null && want.start_time !== shift.start_time) ||
                        (want.end_time != null && want.end_time !== shift.end_time)
    if (timeChanged) { fields.start_time = want.start_time ?? shift.start_time; fields.end_time = want.end_time ?? shift.end_time }
    const movingPos = Object.keys(fields).length > 0
    const keepAssignee = assignTo === undefined
    const finalAssignee = keepAssignee ? shift.assignee_member_id : assignTo
    if (!movingPos && finalAssignee === shift.assignee_member_id) return   // nothing to do
    if (movingPos) {
      try { await api.rosterUpdateShift(shiftId, fields) }
      catch (e) { patch({ toast: { tone: 'block', title: 'Could not update the shift.', body: String(e?.message || e) } }); return }
      setShifts(prev => prev.map(s => s.id === shiftId ? { ...s, ...fields } : s))
    }
    if (finalAssignee) {
      const res = await api.rosterAssign(data.week.id, shiftId, finalAssignee).catch(() => ({ ok: false, blocks: ['Network error'] }))
      if (!res.ok) {
        await api.rosterAssign(data.week.id, shiftId, null).catch(() => {})
        setShifts(prev => prev.map(s => s.id === shiftId ? { ...s, assignee_member_id: null, assignee_name: null, warnings: [] } : s))
        const cand = candById[finalAssignee]
        patch({ toast: { tone: 'warn', title: 'Shift moved, left open.', body: (cand ? cand.name + ': ' : '') + (res.blocks || []).join(' · ') } })
        return
      }
      setShifts(prev => prev.map(s => s.id === shiftId ? { ...s, assignee_member_id: finalAssignee, assignee_name: res.assignee_name, warnings: res.warns || [] } : s))
      if (movingPos) patch({ toast: (res.warns && res.warns.length)
        ? { tone: 'warn', title: (res.assignee_name || 'Shift') + ' rostered with a warning.', body: res.warns.join(' · ') }
        : { tone: 'ok', title: (res.assignee_name || 'Shift') + ' rostered.', body: '' } })
    } else if (movingPos) {
      patch({ toast: { tone: 'info', title: 'Shift updated.', body: '' } })
    }
  }

  const deleteSelectedShift = async (id) => {
    if (!window.confirm('Delete this shift? This only affects this week.')) return
    try { await api.rosterDeleteShift(id); patch({ selected: null }); load() }
    catch (e) { patch({ toast: { tone: 'block', title: 'Could not delete the shift.', body: String(e?.message || e) } }) }
  }

  // ── People rail (left column) edits ─────────────────────────────────────
  //
  // A volunteer's availability is set where they are read, from the inline row
  // that opens when their name is clicked. Optimistic: the People grid shades
  // its cells off `candidates[].available_days`, so the day the cell reflects
  // the change moves with the toggle rather than waiting on the round trip.
  const toggleAvailability = async (memberId, dayIdx) => {
    const c = candById[memberId]; if (!c) return
    const has = (c.available_days || []).includes(dayIdx)
    const next = has ? c.available_days.filter(x => x !== dayIdx) : [...(c.available_days || []), dayIdx].sort((a, b) => a - b)
    setData(d => ({ ...d, candidates: d.candidates.map(x => x.member_id === memberId ? { ...x, available_days: next } : x) }))
    try { await api.rosterSetAvailability(memberId, next) }
    catch (e) { patch({ toast: { tone: 'block', title: 'Could not save availability.', body: String(e?.message || e) } }); load() }
  }

  // Add a role a volunteer doesn't already hold, from the "+ Add" beside their
  // roles. Sends the WHOLE role set (the profiles endpoint replaces, not appends),
  // and updates the pool optimistically so the chip appears at once.
  const addRoleToVolunteer = async (memberId, roleId) => {
    const c = candById[memberId]; if (!c) return
    setAddRoleFor(null)
    const nextIds = [...new Set([...(c.role_ids || []), roleId])]
    const role = allRoles.find(r => r.id === roleId)
    const nextNames = role && !(c.role_names || []).includes(role.title)
      ? [...(c.role_names || []), role.title].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
      : (c.role_names || [])
    setData(d => ({ ...d, candidates: d.candidates.map(x => x.member_id === memberId ? { ...x, role_ids: nextIds, role_names: nextNames } : x) }))
    try { await api.volunteerUpsertProfile({ member_id: memberId, role_ids: nextIds }) }
    catch (e) { patch({ toast: { tone: 'block', title: 'Could not add the role.', body: String(e?.message || e) } }); load() }
  }

  // Give a club member a volunteer profile in one step — the roles they cover,
  // the days they can do, and (only where the user holds MANAGE_QUALIFICATIONS)
  // any accreditations. A full reload afterwards is what lands them in the pool
  // and, when they are already a volunteer, refreshes the merged profile.
  const addVolunteer = async ({ member_id, role_ids, days, qual_ids }) => {
    // The profile endpoint types available_days as List[str], so the day indexes
    // go over as names (the roster reads either back).
    await api.volunteerUpsertProfile({ member_id, role_ids, available_days: (days || []).map(i => DOW_FULL[i]) })
    if (canQuals) {
      for (const qid of (qual_ids || [])) {
        await api.qualAddQualification({ member_id, qualification_type_id: qid }).catch(() => {})
      }
    }
    setAddVolOpen(false)
    await load()
    patch({ toast: { tone: 'ok', title: 'Volunteer added.', body: 'They are in the pool and ready to be rostered.' } })
  }

  // What the drag currently in flight would do if dropped here.
  //
  // A shift now carries its own day, so it CAN be moved to another day: dropping
  // it on a different-day cell moves it there (and, in the People view, onto that
  // person). The cell is judged against the shift AT the destination day, so an
  // unavailable day reads as blocked. A blocked SAME-day reassign is still
  // offered (the server judges it and refuses with a sentence); a blocked
  // day MOVE is refused before the drop so nothing half-moves.
  const dragShift = st.dragId ? shifts.find(s => s.id === st.dragId) : null
  const dropVerdict = (personId, day) => {
    if (!dragShift) return null
    if (personId === null) return { kind: 'unassign' }      // the Open shifts row
    const moved = dragShift.day_of_week !== day
    if (!moved && dragShift.assignee_member_id === personId) return { kind: 'noop' }  // already theirs
    const cand = candById[personId]
    if (!cand) return { kind: 'move', moved }
    const res = checkClient(moved ? { ...dragShift, day_of_week: day } : dragShift, cand, shifts, settings)
    return { kind: res.blocks.length ? 'blocked' : (res.warns.length ? 'warn' : 'move'), res, moved }
  }

  const cellDrop = (key, personId, day) => {
    const v = dropVerdict(personId, day)
    // Refuse a no-op, and refuse a blocked MOVE up front (so a shift never lands
    // half-moved on a day its assignee can't work). A blocked same-day reassign
    // is still accepted and left to the server to refuse with a reason.
    const accepts = !!v && v.kind !== 'noop' && !(v.moved && v.kind === 'blocked')
    return {
      onDragOver: e => {
        if (!accepts) return               // no preventDefault ⇒ the cursor shows "no drop"
        e.preventDefault(); e.dataTransfer.dropEffect = 'move'
        if (st.overCell !== key) patch({ overCell: key })
      },
      onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
      onDrop: e => {
        if (!accepts) return
        e.preventDefault(); const id = st.dragId
        const sh = id ? shifts.find(s => s.id === id) : null
        patch({ overCell: null, dragId: null })
        if (!sh) return
        if (personId === null) doAssign(sh.id, null)                       // Open row → unassign
        else if (sh.day_of_week === day) doAssign(sh.id, personId)         // same day → plain reassign
        else relocateShift(sh.id, { day_of_week: day }, personId)          // cross-day → move + assign
      },
    }
  }
  // The mirror of the above: a person dragged from the pool onto a shift.
  const slotDrop = (shiftId) => {
    const key = 'slot-' + shiftId
    return {
      onDragOver: e => { if (!st.dragPerson) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
      onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
      onDrop: e => { if (!st.dragPerson) return; e.preventDefault(); const pid = st.dragPerson; patch({ overCell: null, dragPerson: null }); if (pid) doAssign(shiftId, pid) },
    }
  }
  const OVER = {
    move: { background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', boxShadow: 'inset 0 0 0 1.5px var(--pb-accent)' },
    warn: { background: 'rgba(245,181,66,0.14)', boxShadow: 'inset 0 0 0 1.5px rgba(245,181,66,0.8)' },
    blocked: { background: 'rgba(239,68,68,0.12)', boxShadow: 'inset 0 0 0 1.5px rgba(239,68,68,0.7)' },
    unassign: { background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', boxShadow: 'inset 0 0 0 1.5px var(--pb-accent)' },
  }
  const cellStyle = (isOver, extra, kind) => ({ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5, ...(isOver ? (OVER[kind] || OVER.move) : {}), ...extra })

  // `onCancel` turns an assigned chip back into an open shift without having to
  // find it in the sidebar first. `dropTarget` lets an OPEN chip accept a
  // volunteer dragged from the pool, which is the whole point of the pool and
  // did not work at all in the people view before.
  const ShiftChip = ({ shift, inOpen, count, onCancel, dropTarget }) => {
    const a = areaById[shift.area_id] || {}
    const warned = shift.warnings && shift.warnings.length
    const over = dropTarget && st.overCell === 'slot-' + shift.id
    return (
      <div draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragId: shift.id, selected: shift.id }) }} onDragEnd={() => patch({ dragId: null, overCell: null })} onClick={() => { patch({ selected: shift.id }); if (!poolOpen) setPoolOpen(true) }}
        {...(dropTarget ? slotDrop(shift.id) : {})}
        style={{ borderRadius: 7, padding: '6px 8px', cursor: 'grab', userSelect: 'none',
          border: `1px solid ${inOpen ? 'rgba(245,181,66,0.45)' : (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 40%, transparent)`)}`,
          background: inOpen ? 'rgba(245,181,66,0.10)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 13%, transparent)`,
          color: inOpen ? C.warn : (a.color || C.accent),
          ...(over ? { boxShadow: '0 0 0 1.5px var(--pb-accent)' } : {}) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: a.color || 'var(--pb-accent)' }} />
          <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{areaLabel(shift) + (count > 1 ? ' ×' + count : '')}</span>
          {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
          {onCancel && (
            <button title="Return this shift to Open"
              onClick={e => { e.stopPropagation(); onCancel() }}
              style={{ marginLeft: warned ? 4 : 'auto', flexShrink: 0, background: 'transparent', border: 'none', color: 'inherit', opacity: 0.55, cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: 0 }}>×</button>
          )}
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{shift.role_name ? shift.role_name + ' · ' : ''}{fmtHour(shift.start_time)}–{fmtHour(shift.end_time)}</div>
      </div>
    )
  }

  const sel = st.selected ? shifts.find(x => x.id === st.selected) : null
  const selArea = sel ? areaById[sel.area_id] : null
  const ranked = sel ? candidates.map(c => ({ c, res: checkClient(sel, c, shifts, settings), load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))
    .filter(x => x.res.blocks.length === 0).sort((a, b) => (a.res.warns.length * 10 + a.load) - (b.res.warns.length * 10 + b.load))
    : candidates.map(c => ({ c, res: { warns: [] }, load: shifts.filter(s => s.assignee_member_id === c.member_id).length }))

  // Every role anyone in the pool has put their hand up for, for the filter.
  // Built from the names the candidates carry rather than a second fetch of the
  // roles catalogue — a role nobody volunteers for is not worth filtering by.
  const poolRoles = [...new Set(candidates.flatMap(c => c.role_names || []))].sort((a, b) => a.localeCompare(b))
  const q = poolQuery.trim().toLowerCase()
  const filtered = ranked.filter(({ c }) => {
    if (poolRole && !(c.role_names || []).includes(poolRole)) return false
    if (!q) return true
    return c.name.toLowerCase().includes(q) || (c.role_names || []).some(r => r.toLowerCase().includes(q))
  })
  // Best fit is only a real ordering when a shift is selected — with nothing
  // selected `ranked` carries no verdicts, so it falls back to name either way.
  const byName = poolSort === 'name' || !sel
  const sorted = byName ? [...filtered].sort((a, b) => a.c.name.localeCompare(b.c.name)) : filtered
  const POOL_CAP = 25
  const candList = sorted.slice(0, POOL_CAP)

  // A shift is FOR one role now, so two open shifts only collapse into one
  // "×N" chip when they share an area AND a role AND the same hours — otherwise
  // an Umpire slot and a Scorer slot at the same time in one Match Day area
  // would merge and hide one of the roles. Keyed on the ids the shift already
  // carries (not the area NAME, which is undefined for an archived area and so
  // used to lump every orphaned shift together regardless of what it was for).
  const openCells = DOW.map((_, d) => {
    const groups = new Map()
    open.filter(x => x.day_of_week === d).forEach(x => {
      const key = [x.area_id, x.role_id || '', x.start_time, x.end_time].join('|')
      const g = groups.get(key)
      if (g) g.count++; else groups.set(key, { shift: x, count: 1 })
    })
    return { d, groups: [...groups.values()] }
  })

  // ── the section search ────────────────────────────────────────────────
  //
  // A roster is people, areas, roles and shifts at once, so the box reaches all
  // four: a person is kept when their own name or role matches OR one of their
  // shifts does, and an area when its own name, department or required role
  // matches OR one of its shifts does. Filtering the ROWS rather than the cells
  // keeps a week readable — a row with its shifts blanked out would say the
  // person is free when they are not.
  const rq = (st.rosterQuery || '').trim().toLowerCase()
  const rHit = (...vals) => vals.some(v => v != null && String(v).toLowerCase().includes(rq))
  const shiftHit = (x) => {
    const a = areaById[x.area_id]
    return rHit(a?.name, a?.department, a?.required_role_name, x.area_name, x.role_name,
                x.notes, x.full_name, DOW[x.day_of_week])
  }
  const personMatches = (p) => !rq
    || rHit(p.name, ...(p.role_names || []))
    || shifts.some(x => x.assignee_member_id === p.member_id && shiftHit(x))
  const areaMatches = (a) => !rq
    || rHit(a.name, a.department, a.required_role_name, a.required_qualification_name)
    || shifts.some(x => x.area_id === a.id && shiftHit(x))
  const shownCandidates = candidates.filter(personMatches)
  const shownAreas = areas.filter(areaMatches)

  // A shift whose area was later archived still exists and still carries its
  // own name (`area_name`, off the shift row). The People view groups by
  // VOLUNTEER, so an assigned volunteer on such a shift shows there — but the
  // Areas view iterates the ACTIVE areas (list_areas is active-only), and had
  // no home for a shift whose area_id is not a live area, so those shifts,
  // assigned volunteers and all, silently dropped out of this view (while
  // still being counted in the "N / M FILLED" total). Every shift whose area
  // is not shown is grouped under its own pseudo-area here so it can never
  // vanish — named off the shift's own `area_name`, the same signal the
  // People-view open-shifts chip already uses. `roles: []` means
  // `areaRoleGroups` draws a sub-row per role the shifts actually carry.
  const ORPHAN_DEPT = 'Archived areas'
  const orphanAreas = (() => {
    const byId = new Map()
    shifts.forEach(x => {
      if (areaById[x.area_id]) return            // a live area — drawn already
      if (rq && !shiftHit(x)) return             // respect the section search
      if (!byId.has(x.area_id)) byId.set(x.area_id, {
        id: x.area_id, name: areaLabel(x), color: null, department: ORPHAN_DEPT, roles: [], __orphan: true,
      })
    })
    return [...byId.values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  })()
  const allShownAreas = [...shownAreas, ...orphanAreas]
  // How many shifts sit on an area that is no longer active — the signal that
  // this week was built before the club changed its areas & roles. Counted
  // over ALL shifts (not the search-filtered orphanAreas) so the staleness
  // banner is not hidden by a query.
  const orphanShiftCount = shifts.filter(x => !areaById[x.area_id]).length

  const depts = []; allShownAreas.forEach(a => { if (!depts.includes(a.department || 'Areas')) depts.push(a.department || 'Areas') })

  // ── Areas view: an area's roles, and the day cells that draw its shifts ──
  //
  // A shift belongs to a role now, so an area with several roles becomes a
  // header that expands into a sub-row per role — which is what a shift is
  // created and filled for. A shift with no role is the "General help" group.
  //
  // A shift dragged onto a DIFFERENT DAY of the SAME area+role row moves there.
  // Restricted to the same area+role (the grid position the row already fixes),
  // so a day drag only ever changes the day — the requested "move it to another
  // day". Dropping keeps whoever is on it (the person is orthogonal in this view).
  const areaCellDrop = (areaId, roleId, day) => {
    const key = 'acell-' + areaId + '-' + (roleId || 'none') + '-' + day
    const accepts = !!dragShift && dragShift.area_id === areaId &&
      (dragShift.role_id || null) === (roleId || null) && dragShift.day_of_week !== day
    return {
      over: st.overCell === key,
      onDragOver: e => { if (!accepts) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
      onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
      onDrop: e => { if (!accepts) return; e.preventDefault(); const id = st.dragId; patch({ overCell: null, dragId: null }); if (id) relocateShift(id, { day_of_week: day }, undefined) },
    }
  }

  // `areaDayCol` is the one place a shift chip is drawn on the Areas view,
  // shared by the single-role row and the per-role sub-rows so they behave
  // identically — same click, same drop targets, same warning tint. `roleId` is
  // the row's own role: a chip is draggable to another day of the same row, an
  // unassigned chip opens the assign modal on click, and an EMPTY cell offers
  // "+ Add" to create a shift for that role/day and hand it to a volunteer.
  const areaDayCol = (a, cellShifts, d, roleId) => {
    const dayShifts = cellShifts.filter(x => x.day_of_week === d)
    const drop = areaCellDrop(a.id, roleId, d)
    return (
      <div key={d} onDragOver={drop.onDragOver} onDragLeave={drop.onDragLeave} onDrop={drop.onDrop}
        style={{ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5,
          background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined, ...(drop.over ? OVER.move : {}) }}>
        {dayShifts.map(x => {
          const warned = x.warnings && x.warnings.length
          const over = st.overCell === 'slot-' + x.id
          return (
            <div key={x.id} draggable
              onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragId: x.id, selected: x.id }) }}
              onDragEnd={() => patch({ dragId: null, overCell: null })}
              onClick={() => { patch({ selected: x.id }); if (!poolOpen) setPoolOpen(true); if (!x.assignee_member_id) setAssignFor(x.id) }} {...slotDrop(x.id)}
              style={{ borderRadius: 7, padding: '6px 8px', cursor: 'grab', userSelect: 'none',
                border: `1px solid ${x.assignee_member_id ? (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 40%, transparent)`) : 'rgba(245,181,66,0.45)'}`,
                background: x.assignee_member_id ? `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 13%, transparent)` : 'rgba(245,181,66,0.10)',
                color: x.assignee_member_id ? (a.color || C.accent) : C.warn,
                ...(over ? { boxShadow: '0 0 0 1.5px var(--pb-accent)' } : {}), ...(st.selected === x.id ? { outline: '1.5px solid var(--pb-accent)', outlineOffset: 1 } : {}) }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...(x.assignee_member_id ? {} : { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em' }) }}>{x.assignee_name || 'OPEN'}</span>
                {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
              </div>
              <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{x.role_name ? x.role_name + ' · ' : ''}{fmtHour(x.start_time)}–{fmtHour(x.end_time)}</div>
            </div>
          )
        })}
        {dayShifts.length === 0 && !a.__orphan && (
          <button onClick={() => setAddAreaFor({ areaId: a.id, day: d, roleId: roleId || null })}
            data-testid={`area-add-${a.id}-${roleId || 'none'}-${d}`}
            style={{ margin: 'auto', fontFamily: MONO, fontSize: 10, letterSpacing: '0.06em', color: C.faint, background: 'transparent', border: `1px dashed ${C.hair2}`, borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>+ Add</button>
        )}
      </div>
    )
  }

  // Collapsed multi-role area: the header's day cells still name the shifts
  // folded away underneath, so collapsing an area doesn't hide which roles it
  // needs on a given day or whether they are covered. One compact chip per
  // shift — a status marker beside the ROLE name, BOTH in the area's own colour
  // so every chip reads as belonging to this area rather than looking like a
  // different role. Filled vs open is carried by the marker's SHAPE alone — a
  // solid disc for a filled shift, a hollow ring (same colour) for one still
  // open — not by a second colour, which made the open ones read as a different
  // area at a glance. Clicking a day that has shifts expands the area.
  const MAX_COLLAPSED_ROWS = 6
  const areaCollapsedDayCol = (a, mine, d) => {
    const dayShifts = mine.filter(x => x.day_of_week === d)
    const n = dayShifts.length
    const f = dayShifts.filter(x => x.assignee_member_id).length
    const o = n - f
    const areaColor = a.color || 'var(--pb-accent)'
    const chip = (x) => {
      const filled = !!x.assignee_member_id
      const label = x.role_name || 'General help'
      return (
        <div key={x.id} data-filled={filled ? '1' : undefined} data-open={filled ? undefined : '1'}
          title={`${label} — ${filled ? (x.assignee_name ? 'filled · ' + x.assignee_name : 'filled') : 'open'}`}
          style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
          <span style={{ width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
            ...(filled
              ? { background: areaColor }
              : { background: 'transparent', border: `1.75px solid ${areaColor}` }) }} />
          <span data-role-label style={{ fontSize: 10.5, fontWeight: filled ? 600 : 500, color: areaColor,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        </div>
      )
    }
    // Keep the last row budget for the "+N more" tally rather than a shift, so a
    // busy day reads as "more than shown" instead of losing the count.
    const shown = n > MAX_COLLAPSED_ROWS ? dayShifts.slice(0, MAX_COLLAPSED_ROWS - 1) : dayShifts
    return (
      <div key={d} data-testid={`area-collapsed-day-${a.id}-${d}`} data-shift-count={n}
        onClick={n ? () => setAreasCollapsed(m => ({ ...m, [a.id]: false })) : undefined}
        title={n ? `${n} shift${n === 1 ? '' : 's'} · ${f} filled${o ? `, ${o} open` : ''} — click to expand` : undefined}
        style={{ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 40,
          display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3, minWidth: 0,
          cursor: n ? 'pointer' : 'default',
          background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined }}>
        {shown.map(chip)}
        {n > MAX_COLLAPSED_ROWS && <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>+{n - (MAX_COLLAPSED_ROWS - 1)} more</span>}
      </div>
    )
  }

  // The roles of an area, in palette order, each with this week's shifts for it.
  //
  // Every role configured on the area is drawn, even one with no shift yet — a
  // club sets an area's roles up (Match Day → Umpire, Scorer, Turf Curator,
  // Groundskeeper) before, or without, a weekly shift pattern, and the whole
  // point here is to SEE those roles and give each one shifts. Tying "show a
  // role" to "has a shift this week" hid the roles of any area that had none, so
  // a multi-role area with an empty week looked like a plain single row and
  // would not open. A shift whose role was removed from the palette, or general
  // help with no role at all, is a leftover group kept last.
  const areaRoleGroups = (a, areaShifts) => {
    const palette = a.roles || []
    const known = new Set(palette.map(r => r.role_id))
    const groups = new Map()
    // Seed a row per configured role first, in palette order; shifts fill in.
    palette.forEach(r => groups.set(r.role_id, { role_id: r.role_id, role_name: r.role_name, shifts: [] }))
    areaShifts.forEach(x => {
      const key = x.role_id && known.has(x.role_id) ? x.role_id : (x.role_id || '__none')
      if (!groups.has(key)) groups.set(key, { role_id: x.role_id || null, role_name: x.role_name || 'General help', shifts: [] })
      groups.get(key).shifts.push(x)
    })
    const paletteOrder = new Map(palette.map((r, i) => [r.role_id, i]))
    return [...groups.values()].sort((g1, g2) => {
      if (g1.role_id === null) return 1
      if (g2.role_id === null) return -1
      const i1 = paletteOrder.has(g1.role_id) ? paletteOrder.get(g1.role_id) : 1e9
      const i2 = paletteOrder.has(g2.role_id) ? paletteOrder.get(g2.role_id) : 1e9
      return (i1 - i2) || (g1.role_name || '').localeCompare(g2.role_name || '')
    })
  }

  return (
    // The screen is bounded to the viewport (like Directory) rather than
    // `minHeight: 100vh`, so the roster grid and the volunteer pool each scroll
    // WITHIN their own region instead of the whole page scrolling as one.
    // That is what keeps the day/date header row sticky under the grid, and
    // stops scrolling the shifts from moving the pool (and vice versa).
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {header(<>
        {/* Centred on the title line: the title block and the actions on the
            right each take an equal share of what is left, so the four
            buttons land in the middle of the header rather than wherever the
            week label happens to end. */}
        <div style={HEAD_CENTRE}>
          <SegTabs value={view} onChange={v => patch({ view: v, selected: null })}
            tabs={[{ key: 'people', label: 'People' }, { key: 'areas', label: 'Areas' }, { key: 'confirm', label: 'Confirm' }, { key: 'hours', label: 'Hours' }]} />
        </div>
        {/* Every one of these acts on the shift grid, so none of them mean
            anything on the hours or confirmation tabs. The BOX stays either
            way — it has a zero basis, so it costs nothing empty, and dropping
            it would let the title take the whole row and slide the buttons off
            centre. */}
        <div style={{ ...HEAD_SIDE_END, gap: 14 }}>
          {(view === 'hours' || view === 'confirm') ? null : <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
            <span style={{ fontWeight: 700, fontSize: 18, color: C.text, fontVariantNumeric: 'tabular-nums' }}>{filled}</span>
            <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, letterSpacing: '0.08em' }}>/ {shifts.length} FILLED</span>
          </div>
          <div style={{ width: 120, height: 6, borderRadius: 3, background: C.surface2, overflow: 'hidden' }}><div style={{ height: '100%', width: pct + '%', background: pct === 100 ? C.ok : C.accent }} /></div>
          <button onClick={() => setPoolOpen(v => !v)} style={{ padding: '8px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', ...(poolOpen ? { border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: C.accent, background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' } : { border: `1px solid ${C.hair2}`, color: C.dim, background: 'transparent' }) }}>{poolOpen ? 'Hide pool' : 'Volunteer pool'}</button>
          {/* The three that act on the week itself, in Committee's own
              segmented control — one box rather than three loose buttons.
              "Volunteer pool" is a view toggle, so it does not join them, and
              "Publish week" is the primary action and has moved up onto the
              search line. */}
          <SegGroup>
            <button disabled={busy} onClick={autoFill} style={{ ...segItemStyle(false), opacity: busy ? 0.6 : 1 }}>Auto-fill open shifts</button>
            <EmailRostered weekStart={data.week.week_start} onToast={t => patch({ toast: t })} />
            <button onClick={resetWeek} style={segItemStyle(false)}>Reset</button>
          </SegGroup>
          </>}
        </div>
      </>)}

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {/* This week still holds shifts on areas that are no longer active, which
          means it was generated before the club last changed its areas & roles
          — editing a pattern only rebuilds a week that has no shifts yet, so an
          existing draft goes quietly stale. Rather than leave the "Archived
          areas" section to be puzzled over, say what it means and offer the one
          action that fixes it (Reset regenerates from the current patterns).
          Draft weeks only — a published week is a record, not a draft to
          rebuild. */}
      {view !== 'hours' && view !== 'confirm' && orphanShiftCount > 0 && data.week.status !== 'published' && (
        <div data-testid="roster-stale-banner" style={{ margin: '0 16px 4px', padding: '11px 14px', borderRadius: 9,
          border: '1px solid rgba(245,181,66,0.35)', background: 'rgba(245,181,66,0.08)',
          display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220, fontSize: 12.5, color: C.dim, lineHeight: 1.5 }}>
            <span style={{ fontWeight: 700, color: C.warn }}>This week predates your latest areas &amp; roles.</span>{' '}
            {orphanShiftCount} shift{orphanShiftCount === 1 ? '' : 's'} here belong to areas you have since changed or archived (shown under <span style={{ fontFamily: MONO, fontSize: 11 }}>Archived areas</span> on the Areas view). Reset the week to rebuild it from your current patterns.
          </div>
          <button onClick={resetWeek}
            style={{ flexShrink: 0, padding: '8px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: C.accent, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' }}>
            Reset the week
          </button>
        </div>
      )}

      {view === 'hours' && <HoursView weekStart={data.week.week_start} />}
      {view === 'confirm' && (
        <ConfirmRoster weekId={data.week.id} onToast={t => patch({ toast: t })}
          onDone={load} />
      )}

      {view !== 'hours' && view !== 'confirm' && (
      <div style={{ display: 'flex', flex: 1, minHeight: 0, alignItems: 'stretch' }}>
        <div className="pb-scroll" data-testid="roster-grid-scroll" style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
          <div style={{ minWidth: narrow ? 0 : 1266 }}>
            <div data-testid="roster-day-header" style={{ display: 'grid', gridTemplateColumns: gridCols, position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
              <div style={rail({ zIndex: 22, padding: railMin ? '10px 6px' : '10px 14px', display: 'flex', alignItems: 'center', gap: 6 })}>
                {!railMin && (
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {view === 'areas' ? 'OPERATIONAL AREA' : 'VOLUNTEER'}
                  </span>
                )}
                <button onClick={() => setRailMin(v => !v)}
                  title={railMin ? 'Widen this column' : 'Minimise this column'}
                  style={{ marginLeft: railMin ? 'auto' : 0, marginRight: railMin ? 'auto' : 0, background: 'transparent', border: `1px solid ${C.hair2}`, borderRadius: 5, color: C.faint, cursor: 'pointer', fontSize: 11, lineHeight: 1, padding: '3px 5px', flexShrink: 0 }}>
                  {railMin ? '»' : '«'}
                </button>
              </div>
              {DOW.map((d, i) => (
                <div key={i} style={{ padding: '10px 12px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : undefined }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint }}>{d.toUpperCase()}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: C.dim }}>{DATES[i]}</span>
                </div>
              ))}
            </div>

            {view === 'people' && (
              <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair2}`, background: 'rgba(245,181,66,0.04)' }}>
                {/* The row's amber tint is barely opaque, so it goes on TOP of
                    the rail's own solid background rather than replacing it —
                    otherwise the shifts scrolling underneath show through. */}
                <div style={rail({ padding: railMin ? '12px 4px' : '12px 14px', display: 'flex', flexDirection: 'column', gap: 3, justifyContent: 'center', alignItems: railMin ? 'center' : 'stretch', backgroundImage: 'linear-gradient(rgba(245,181,66,0.04), rgba(245,181,66,0.04))' })}
                  title={railMin ? `Open shifts — ${open.length} unfilled` : undefined}>
                  {railMin ? (
                    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: C.warn }}>{open.length}</span>
                  ) : (
                    <>
                      <span style={{ fontSize: 13, fontWeight: 700, color: C.warn }}>Open shifts</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{open.length} unfilled · drag onto a person</span>
                    </>
                  )}
                </div>
                {openCells.map(({ d, groups }) => {
                  const key = 'open-' + d
                  const shown = st.openExpanded ? groups : groups.slice(0, 2)
                  const hidden = groups.length - shown.length
                  return (
                    <div key={d} style={cellStyle(st.overCell === key, {}, 'unassign')} {...cellDrop(key, null, d)}>
                      {shown.map(g => <ShiftChip key={g.shift.id} shift={g.shift} inOpen count={g.count} dropTarget />)}
                      {(hidden > 0 || (st.openExpanded && groups.length > 2)) && (
                        <button onClick={() => patch(s => ({ openExpanded: !s.openExpanded }))} style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.warn, background: 'transparent', border: '1px dashed rgba(245,181,66,0.4)', borderRadius: 6, padding: '4px 6px', cursor: 'pointer', textAlign: 'left' }}>{hidden > 0 ? '+ ' + hidden + ' more' : 'show less'}</button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Above the list of volunteers: add one from the club member list.
                The search over every member lives in the modal this opens, so a
                new volunteer is a member picked, given roles/availability, and
                dropped straight into the pool. */}
            {view === 'people' && (
              <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair2}` }}>
                <div style={rail({ padding: railMin ? '8px 4px' : '8px 10px', display: 'flex', alignItems: 'center' })}>
                  <button onClick={() => setAddVolOpen(true)} data-testid="add-volunteer-open"
                    title={railMin ? 'Add a volunteer' : undefined}
                    style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: railMin ? '5px 0' : '7px 10px', borderRadius: 7, fontSize: railMin ? 14 : 12.5, fontWeight: 600, cursor: 'pointer', border: '1px dashed color-mix(in srgb, var(--pb-accent) 40%, transparent)', background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)', color: C.accent }}>
                    {railMin ? '+' : '+ Add volunteer'}
                  </button>
                </div>
                {DOW.map((_, d) => <div key={d} style={{ borderRight: `1px solid ${C.hair}`, background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined }} />)}
              </div>
            )}

            {view === 'people' && shownCandidates.map(p => {
              const mine = shifts.filter(x => x.assignee_member_id === p.member_id)
              const cap = settings.weekly_shift_cap || p.max_shifts || DEFAULT_CAP
              const loadPct = Math.min(100, Math.round((mine.length / cap) * 100))
              const over = mine.length > cap
              return (
                <div key={p.member_id} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                  <div style={rail({ padding: railMin ? '10px 4px' : '10px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: railMin ? 'center' : 'stretch', cursor: 'pointer' })}
                    onClick={() => railMin ? setOpenPerson(p.member_id) : setExpandedPerson(x => x === p.member_id ? null : p.member_id)}
                    title={railMin ? `${p.name} — ${mine.length}/${cap} shifts` : (expandedPerson === p.member_id ? 'Hide availability' : 'Show availability')}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                      <span style={{ width: 28, height: 28, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${over ? C.block : C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 10, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(p.name)}</span>
                      {!railMin && (
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                        </div>
                      )}
                    </div>
                    {!railMin && (
                      <>
                        {/* The volunteer's roles sit beneath their name, always,
                            with a "+ Add" for a quick new one. stopPropagation so
                            a chip or the add tap doesn't collapse the row. */}
                        <div data-testid={`people-roles-${p.member_id}`} onClick={e => e.stopPropagation()}
                          style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6, alignItems: 'center' }}>
                          {(p.role_names || []).map(r => (
                            <span key={r} style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', padding: '2px 5px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 28%, transparent)', color: C.accent, whiteSpace: 'nowrap' }}>{r.toUpperCase()}</span>
                          ))}
                          {!(p.role_names || []).length && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', color: C.faintest }}>NO ROLE</span>}
                          <button onClick={() => setAddRoleFor(p.member_id)} data-testid={`add-role-${p.member_id}`}
                            title="Add a role" style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', color: C.faint, background: 'transparent', border: `1px dashed ${C.hair2}`, borderRadius: 4, padding: '2px 5px', cursor: 'pointer' }}>+ ADD</button>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 7 }}>
                          <div style={{ flex: 1, height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden' }}><div style={{ height: '100%', width: loadPct + '%', background: over ? C.block : C.accent }} /></div>
                          <span style={{ fontFamily: MONO, fontSize: 9.5, color: over ? C.block : C.faint }}>{mine.length}/{cap}</span>
                        </div>
                        {/* Clicking the row shows their availability inline here,
                            rather than in the panel on the far side of the grid. */}
                        {expandedPerson === p.member_id && (
                          <AvailabilityRow days={p.available_days} testid={`people-avail-${p.member_id}`}
                            onToggle={i => toggleAvailability(p.member_id, i)} />
                        )}
                      </>
                    )}
                  </div>
                  {DOW.map((_, d) => {
                    const key = p.member_id + '-' + d
                    const chips = mine.filter(x => x.day_of_week === d)
                    const avail = p.available_days.includes(d)
                    const verdict = dropVerdict(p.member_id, d)
                    return (
                      <div key={d} style={cellStyle(st.overCell === key, avail ? {} : { background: 'repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(58,63,80,0.10) 6px, rgba(58,63,80,0.10) 12px)' }, verdict?.kind)} {...cellDrop(key, p.member_id, d)}>
                        {chips.map(x => <ShiftChip key={x.id} shift={x} onCancel={() => doAssign(x.id, null)} />)}
                        {/* Available and free → offer to add them to one of the
                            day's open shifts; not available → shaded UNAVAILABLE. */}
                        {!chips.length && avail && (
                          <button onClick={() => setAddFor({ personId: p.member_id, day: d })}
                            data-testid={`people-add-${p.member_id}-${d}`}
                            style={{ margin: 'auto', fontFamily: MONO, fontSize: 10, letterSpacing: '0.06em', color: C.faint, background: 'transparent', border: `1px dashed ${C.hair2}`, borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>+ add</button>
                        )}
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
                  <div style={{ position: 'sticky', left: 0, zIndex: 12, background: C.surface, padding: railMin ? '8px 6px' : '8px 14px', fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim, whiteSpace: 'nowrap' }}
                    title={dept}>{railMin ? dept.slice(0, 3).toUpperCase() : dept}</div>
                </div>
                {allShownAreas.filter(a => (a.department || 'Areas') === dept).map(a => {
                  const mine = shifts.filter(x => x.area_id === a.id)
                  const filledN = mine.filter(x => x.assignee_member_id).length
                  const groups = areaRoleGroups(a, mine)
                  const multi = groups.length > 1
                  const collapsed = multi && !!areasCollapsed[a.id]

                  // One role (or no shifts yet): a single row, exactly as before.
                  // The role and its qualification read on the meta line, so
                  // there is nothing to expand.
                  if (!multi) {
                    return (
                      <div key={a.id} data-testid={`area-row-${a.id}`} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                        <div style={rail({ padding: railMin ? '10px 4px' : '10px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4, alignItems: railMin ? 'center' : 'stretch' })}
                          title={railMin ? `${a.name} — ${filledN}/${mine.length} filled · click to edit the area` : undefined}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                            <span onClick={() => openArea(a)} title={railMin ? undefined : `Edit ${a.name} and its shifts`}
                              style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: a.color || 'var(--pb-accent)', cursor: 'pointer' }} />
                            {!railMin && <>
                              <span onClick={() => openArea(a)} title={`Edit ${a.name} and its shifts`}
                                style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0, ...areaLinkStyle }}>{a.name}</span>
                              <span style={{ fontFamily: MONO, fontSize: 9.5, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>
                            </>}
                          </div>
                          {railMin
                            ? <span style={{ fontFamily: MONO, fontSize: 9, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>
                            : <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{[groups[0]?.role_name || a.required_role_name, a.required_qualification_name].filter(Boolean).join(' · ') || 'No role/qual set'}</div>}
                        </div>
                        {DOW.map((_, d) => areaDayCol(a, mine, d, groups[0]?.role_id ?? null))}
                      </div>
                    )
                  }

                  // Several roles: a header that folds its per-role rows away.
                  // The header carries the area total; each sub-row is one role,
                  // with only that role's shifts in its day cells — which is what
                  // a shift is created and assigned for.
                  return (
                    <div key={a.id} data-testid={`area-header-${a.id}`}>
                      <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                        <div style={rail({ padding: railMin ? '9px 4px' : '9px 10px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3, alignItems: railMin ? 'center' : 'stretch' })}
                          title={railMin ? `${a.name} — ${groups.length} roles · ${filledN}/${mine.length} filled` : undefined}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <button onClick={() => setAreasCollapsed(m => ({ ...m, [a.id]: !m[a.id] }))}
                              title={collapsed ? `Show ${a.name}'s roles` : `Hide ${a.name}'s roles`}
                              data-testid={`area-toggle-${a.id}`}
                              style={{ background: 'transparent', border: 'none', color: C.faint, cursor: 'pointer', fontSize: 10, lineHeight: 1, padding: 0, flexShrink: 0, width: 12 }}>
                              {collapsed ? '▸' : '▾'}
                            </button>
                            <span onClick={() => openArea(a)} title={railMin ? undefined : `Edit ${a.name} and its shifts`}
                              style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: a.color || 'var(--pb-accent)', cursor: 'pointer' }} />
                            {!railMin && <>
                              <span onClick={() => openArea(a)} title={`Edit ${a.name} and its shifts`}
                                style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...areaLinkStyle }}>{a.name}</span>
                              <span style={{ fontFamily: MONO, fontSize: 9.5, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>
                            </>}
                          </div>
                          {!railMin && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, paddingLeft: 18 }}>{groups.length} roles</div>}
                          {railMin && <span style={{ fontFamily: MONO, fontSize: 9, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>}
                        </div>
                        {/* Expanded, the header's day cells stay empty (the
                            shifts show in the per-role sub-rows below).
                            Collapsed, they carry a colour-coded dot per shift so
                            the folded-away days are still visible. */}
                        {DOW.map((_, d) => collapsed
                          ? areaCollapsedDayCol(a, mine, d)
                          : <div key={d} style={{ borderRight: `1px solid ${C.hair}`, background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined }} />)}
                      </div>
                      {!collapsed && groups.map(g => {
                        const gFilled = g.shifts.filter(x => x.assignee_member_id).length
                        const qual = g.role_id ? (a.roles || []).find(r => r.role_id === g.role_id)?.required_qualification_name : null
                        return (
                          <div key={g.role_id || '__none'} data-testid={`area-role-row-${a.id}-${g.role_id || 'none'}`} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                            <div style={rail({ padding: railMin ? '8px 4px' : '8px 12px 8px 26px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3, alignItems: railMin ? 'center' : 'stretch', background: C.surface })}
                              title={railMin ? `${g.role_name} — ${gFilled}/${g.shifts.length} filled` : undefined}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                {!railMin && <span style={{ width: 5, height: 5, borderRadius: '50%', flexShrink: 0, background: a.color || 'var(--pb-accent)', opacity: 0.7 }} />}
                                <span style={{ fontSize: 12.5, fontWeight: 600, color: C.dim, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {railMin ? (g.role_name || 'Gen').slice(0, 3) : g.role_name}
                                </span>
                                {!railMin && <span style={{ fontFamily: MONO, fontSize: 9, color: gFilled === g.shifts.length ? C.ok : C.warn }}>{gFilled}/{g.shifts.length}</span>}
                              </div>
                              {!railMin && qual && <div style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>needs {qual}</div>}
                            </div>
                            {DOW.map((_, d) => areaDayCol(a, g.shifts, d, g.role_id))}
                          </div>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Minimised, the pool becomes a thin rail rather than vanishing, so
            there is always a way back to it from where it used to be. */}
        {!poolOpen && !narrow && (
          <aside style={{ width: 30, flex: '0 0 30px', borderLeft: `1px solid ${C.hair}`, background: C.surface, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 14, gap: 10 }}>
            <button onClick={() => setPoolOpen(true)} title="Show the volunteer pool"
              style={{ background: 'transparent', border: `1px solid ${C.hair2}`, borderRadius: 5, color: C.faint, cursor: 'pointer', fontSize: 11, lineHeight: 1, padding: '3px 5px' }}>«</button>
            <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, writingMode: 'vertical-rl', whiteSpace: 'nowrap' }}>VOLUNTEER POOL</span>
          </aside>
        )}

        {poolOpen && (
          <aside className="pb-scroll" data-testid="roster-pool" style={narrow
            ? { width: 320, maxWidth: '92vw', position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 65, borderLeft: `1px solid ${C.hair2}`, background: C.surface, overflowY: 'auto', padding: 16, boxShadow: '0 0 40px rgba(0,0,0,0.5)' }
            : { width: 296, flex: '0 0 296px', borderLeft: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 16 }}>
            {sel && (
              <div>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>BEST FIT FOR THIS SHIFT</div>
                <div style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 12, marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: (selArea && selArea.color) || 'var(--pb-accent)' }} />
                    {/* An archived area is not in the areas list, so it can't be
                        edited from here — name it off the shift's own area_name
                        rather than hiding the whole fill panel for it. */}
                    {selArea
                      ? <span onClick={() => openArea(selArea)} title={`Edit ${selArea.name} and its shifts`}
                          style={{ fontWeight: 600, fontSize: 14, ...areaLinkStyle }}>{selArea.name}</span>
                      : <span style={{ fontWeight: 600, fontSize: 14 }}>{areaLabel(sel)}</span>}
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim, marginTop: 4 }}>{sel.role_name ? sel.role_name + ' · ' : ''}{DOW[sel.day_of_week]} {fmtHour(sel.start_time)}–{fmtHour(sel.end_time)}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginTop: 4 }}>{[sel.role_name, sel.required_qualification_name ? 'needs ' + sel.required_qualification_name : null].filter(Boolean).join(' · ') || 'No requirement'}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button onClick={() => { if (candList[0]) doAssign(sel.id, candList[0].c.member_id) }} style={{ flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Fill best match</button>
                    <button onClick={() => { doAssign(sel.id, null); patch({ selected: null }) }} style={{ padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Clear</button>
                  </div>
                </div>
              </div>
            )}

            {/* Clicking a shift lets its day and time be changed here, and it
                deleted. Keyed on the shift so switching shifts reseeds the form. */}
            {sel && (
              <ShiftEditForm key={sel.id} shift={sel} busy={busy}
                onSave={fields => relocateShift(sel.id, fields, undefined)}
                onDelete={() => deleteSelectedShift(sel.id)} />
            )}

            {addingShift
              ? <AddShift areas={areas} weekId={data.week.id}
                  onDone={() => { setAddingShift(false); load() }} onCancel={() => setAddingShift(false)} />
              : <button onClick={() => setAddingShift(true)} style={{ width: '100%', padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', marginBottom: 10 }}>+ Add a shift</button>}

            {openPerson && <PersonPanel memberId={openPerson} onClose={() => setOpenPerson(null)} onSaved={load} />}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest }}>{sel ? 'RANKED CANDIDATES' : 'VOLUNTEER POOL'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginLeft: 'auto' }}>
                {sorted.length === candidates.length ? `${sorted.length} people` : `${sorted.length} of ${candidates.length}`}
              </span>
              <button onClick={() => setPoolOpen(false)} title="Minimise the volunteer pool"
                style={{ background: 'transparent', border: `1px solid ${C.hair2}`, borderRadius: 5, color: C.faint, cursor: 'pointer', fontSize: 11, lineHeight: 1, padding: '3px 5px', flexShrink: 0 }}>»</button>
            </div>
            <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.45, marginBottom: 10 }}>{view === 'areas' ? 'Drag a volunteer onto a shift, or select a shift to rank them.' : 'Drag a volunteer onto an open shift, or a shift onto someone else on the same day.'}</div>
            {candidates.length === 0 && <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>No volunteers yet. Add volunteer profiles (with availability) in the Directory/Volunteers so they can be rostered.</div>}

            {candidates.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                <div style={{ position: 'relative' }}>
                  <input value={poolQuery} onChange={e => setPoolQuery(e.target.value)} placeholder="Search name or role…"
                    style={{ width: '100%', background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '6px 24px 6px 9px', color: C.text, fontSize: 12.5, outline: 'none' }} />
                  {poolQuery && (
                    <button onClick={() => setPoolQuery('')} title="Clear the search"
                      style={{ position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', color: C.faint, cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: '2px 4px' }}>×</button>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <select value={poolRole} onChange={e => setPoolRole(e.target.value)} title="Filter by the role a volunteer put their hand up for"
                    style={{ flex: 1, minWidth: 0, background: C.surface2, border: `1px solid ${poolRole ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`, borderRadius: 7, padding: '6px 8px', color: poolRole ? C.text : C.dim, fontSize: 12, outline: 'none' }}>
                    <option value="">All roles</option>
                    {poolRoles.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <select value={byName ? 'name' : 'fit'} onChange={e => setPoolSort(e.target.value)} title={sel ? 'Order the candidates' : 'Best fit needs a shift selected'} disabled={!sel}
                    style={{ width: 104, flexShrink: 0, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '6px 8px', color: sel ? C.dim : C.faintest, fontSize: 12, outline: 'none', cursor: sel ? 'pointer' : 'default' }}>
                    <option value="name">By name</option>
                    <option value="fit">Best fit</option>
                  </select>
                </div>
              </div>
            )}

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
                  {/* What they volunteered for and when they can do it — the two
                      things you need to know before dragging someone onto a shift. */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 7 }}>
                    {(c.role_names || []).length
                      ? c.role_names.map(r => (
                        <span key={r} style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', padding: '2px 5px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 28%, transparent)', color: C.accent, whiteSpace: 'nowrap' }}>{r.toUpperCase()}</span>
                      ))
                      : <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', color: C.faintest }}>NO ROLE SET</span>}
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>
                    {c.available_days.length
                      ? <>AVAIL {DOW.map((d, i) => (
                        <span key={i} style={{ marginRight: 3, color: c.available_days.includes(i) ? (sel && sel.day_of_week === i ? C.accent : C.dim) : C.faintest, fontWeight: c.available_days.includes(i) ? 600 : 400 }}>{d}</span>
                      ))}</>
                      : 'NO AVAILABILITY SET'}
                  </div>
                </div>
              ))}
              {candidates.length > 0 && sorted.length === 0 && (
                <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
                  Nobody matches{poolRole ? ` the ${poolRole} role` : ''}{q ? ` "${poolQuery.trim()}"` : ''}
                  {sel ? '. Ranked candidates already exclude anyone the rules block for this shift.' : '.'}
                </div>
              )}
              {sorted.length > POOL_CAP && (
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, textAlign: 'center', padding: '4px 0' }}>
                  SHOWING {POOL_CAP} OF {sorted.length} — SEARCH TO NARROW
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
      )}

      {/* Areas view: assign a volunteer to an unassigned shift, from anywhere. */}
      {assignFor && (() => {
        const s = shifts.find(x => x.id === assignFor)
        if (!s) return null
        return (
          <AssignModal shift={s} areaName={areaLabel(s)} candidates={candidates} shifts={shifts} settings={settings}
            onPick={mid => { setAssignFor(null); doAssign(s.id, mid) }}
            onFillBest={() => { const b = bestFor(s); setAssignFor(null); if (b) doAssign(s.id, b); else patch({ toast: { tone: 'warn', title: 'Nobody available.', body: 'No qualified, available volunteer for this shift.' } }) }}
            onClear={() => { setAssignFor(null); doAssign(s.id, null) }}
            onClose={() => setAssignFor(null)} />
        )
      })()}

      {/* People rail: add a volunteer from the club member list. */}
      {addVolOpen && (
        <AddVolunteerModal roles={allRoles} qualTypes={qualTypes} canQuals={canQuals}
          onAdd={addVolunteer} onClose={() => setAddVolOpen(false)} />
      )}

      {/* People rail "+ Add" beside a volunteer's roles. */}
      {addRoleFor && (() => {
        const c = candById[addRoleFor]
        return (
          <AddRoleModal memberName={c?.name || 'this volunteer'} currentIds={c?.role_ids || []} roles={allRoles}
            onPick={rid => addRoleToVolunteer(addRoleFor, rid)} onClose={() => setAddRoleFor(null)} />
        )
      })()}

      {/* People view "+ add": hand the person one of the day's open shifts. */}
      {addFor && (() => {
        const cand = candById[addFor.personId]
        return (
          <AddOpenShiftModal personName={cand?.name || 'this volunteer'} cand={cand} day={addFor.day}
            openShifts={open} shifts={shifts} settings={settings} areaLabelFor={areaLabel}
            onPick={sid => { setAddFor(null); doAssign(sid, addFor.personId) }}
            onClose={() => setAddFor(null)} />
        )
      })()}

      {/* Areas view "+ Add": create a one-off shift for a role/day and, in the
          same step, hand it to a volunteer. */}
      {addAreaFor && (() => {
        const a = areaById[addAreaFor.areaId]
        if (!a) return null
        return (
          <NewAreaShiftModal area={a} day={addAreaFor.day} roleId={addAreaFor.roleId}
            candidates={candidates} shifts={shifts} settings={settings}
            onClose={() => setAddAreaFor(null)}
            onCreate={async ({ start_time, end_time, role_id, assignee }) => {
              const res = await api.rosterCreateShift({ week_id: data.week.id, area_id: a.id, day_of_week: addAreaFor.day, start_time, end_time, role_id })
              const newId = res.id
              let assigned = null
              if (assignee) assigned = await api.rosterAssign(data.week.id, newId, assignee).catch(() => ({ ok: false }))
              const day = addAreaFor.day
              setAddAreaFor(null)
              await load()
              patch({ selected: newId, toast: (assignee && assigned?.ok)
                ? { tone: assigned.warns?.length ? 'warn' : 'ok', title: `Shift added, ${assigned.assignee_name || 'volunteer'} rostered.`, body: (assigned.warns || []).join(' · ') || `${a.name} · ${DOW[day]}` }
                : { tone: 'ok', title: 'Shift added.', body: `${a.name} · ${DOW[day]}` } })
            }} />
        )
      })()}
    </div>
  )
}
