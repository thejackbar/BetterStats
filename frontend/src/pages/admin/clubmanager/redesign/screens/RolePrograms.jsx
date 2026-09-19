import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, HEAD_SIDE, HeaderSearch, matchesQuery, ManageLink } from '../ui'

// Role Programs — what a role entails, and its measurable handover.
//
// Two halves on one screen. The PROGRAM (left = roles, right = the selected
// role's purpose, its recurring/seasonal/match-day duties and the areas it
// covers) is assembled on read; a duty is a Club Diary task tagged to the role,
// so adding one here writes a diary definition and the two screens stay one
// engine. The HANDOVER is the succession tool: when a role changes hands a
// responsible person works a checklist seeded from the program and records, per
// element, whether the incoming volunteer has been walked through it and has
// understood and accepted it — so the club sees onboarding status and the gaps.
// Nothing is mandatory: a club that has built nothing still gets a role with a
// title, and everything fills in progressively.

// Cadence vocabulary — mirrors the backend's widened frequency set. Operational
// (match day / weekly) first, seasonal in the middle, standing responsibilities
// last, so the program reads top-to-bottom from "every match" to "all season".
const CAD = [
  ['matchday', 'Match day', 'Before or on every match day'],
  ['weekly', 'Weekly', 'Each week in season'],
  ['monthly', 'Monthly', 'Once a month'],
  ['quarterly', 'Quarterly', 'Each quarter'],
  ['season_start', 'Season start', 'Pre-season set-up'],
  ['season_end', 'Season end', 'End-of-season wrap-up'],
  ['annual', 'Annual', 'Once a year'],
  ['once', 'One-off', 'A single task'],
  ['ongoing', 'Ongoing responsibility', 'Standing, no fixed date'],
]
const CAD_LABEL = Object.fromEntries(CAD.map(([k, l]) => [k, l]))

const ITEM_STATUS = [
  ['pending', 'Not started', C.faint],
  ['walked_through', 'Walked through', C.warn],
  ['accepted', 'Understood & accepted', C.ok],
  ['na', 'N/A', C.dim],
]

const btn = (tone, solid) => ({
  padding: '7px 12px', borderRadius: 7, fontSize: 12.5, cursor: 'pointer',
  border: `1px solid ${solid ? tone : C.hair2}`, whiteSpace: 'nowrap',
  background: solid ? tone : 'transparent', color: solid ? '#08110b' : (tone || C.text),
})

function Btn({ children, onClick, tone, solid, disabled, style }) {
  return (
    <button disabled={disabled} onClick={onClick}
      style={{ ...btn(tone, solid), opacity: disabled ? 0.5 : 1, ...style }}>{children}</button>
  )
}

function Chip({ children, tone = C.faint }) {
  return (
    <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.04em', textTransform: 'uppercase',
      color: tone, border: `1px solid ${C.hair2}`, borderRadius: 5, padding: '1px 6px' }}>{children}</span>
  )
}

function Bar({ percent, tone = C.accent }) {
  return (
    <div style={{ height: 6, borderRadius: 4, background: C.hair, overflow: 'hidden' }}>
      <div style={{ width: `${percent}%`, height: '100%', background: tone, transition: 'width .2s' }} />
    </div>
  )
}

function progTone(p) {
  if (!p || !p.applicable) return C.faint
  if (p.complete) return C.ok
  return p.percent >= 50 ? C.warn : C.accent
}

// ── Left rail: roles ─────────────────────────────────────────────────────────

function RoleRow({ role, active, onClick }) {
  const badge = role._handover
  return (
    <button onClick={onClick} style={{
      display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
      padding: '10px 12px', border: 'none', borderBottom: `1px solid ${C.hair}`,
      background: active ? C.surface2 : 'transparent',
      borderLeft: `2px solid ${active ? C.accent : 'transparent'}`,
    }}>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{role.title}</div>
      <div style={{ fontSize: 11.5, color: C.dim, marginTop: 2, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        {role.is_committee ? <Chip tone={C.warn}>Committee</Chip> : (role.role_type_name ? <span>{role.role_type_name}</span> : null)}
        {badge && <Chip tone={progTone(badge.progress)}>{badge.progress?.percent ?? 0}% onboarded</Chip>}
      </div>
    </button>
  )
}

// ── Duties (the program) ─────────────────────────────────────────────────────

function DutyGroup({ cadence, label, duties, onRemove, busy }) {
  if (!duties.length) return null
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.dim, marginBottom: 6 }}>{label}</div>
      {duties.map(d => (
        <div key={d.definition_id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '6px 0', borderBottom: `1px solid ${C.hair}` }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, color: C.text }}>{d.title}</div>
            {d.description && <div style={{ fontSize: 11.5, color: C.dim, marginTop: 1 }}>{d.description}</div>}
          </div>
          <button title="Remove this duty" disabled={busy} onClick={() => onRemove(d)}
            style={{ border: 'none', background: 'transparent', color: C.faint, cursor: 'pointer', fontSize: 15, lineHeight: 1 }}>×</button>
        </div>
      ))}
    </div>
  )
}

function AddDuty({ onAdd, busy }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [cadence, setCadence] = useState('matchday')
  const [desc, setDesc] = useState('')
  const submit = async () => {
    if (!title.trim()) return
    await onAdd({ title: title.trim(), frequency: cadence, description: desc.trim() || null })
    setTitle(''); setDesc(''); setOpen(false)
  }
  if (!open) return <Btn onClick={() => setOpen(true)} tone={C.accent} style={{ marginTop: 4 }}>+ Add a duty</Btn>
  const inp = { width: '100%', padding: '7px 9px', borderRadius: 7, border: `1px solid ${C.hair2}`, background: C.surface, color: C.text, fontSize: 13 }
  return (
    <div style={{ border: `1px solid ${C.hair2}`, borderRadius: 9, padding: 12, marginTop: 6, background: C.surface }}>
      <input autoFocus placeholder="What is the duty? (e.g. Set up the covers)" value={title} onChange={e => setTitle(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setOpen(false) }} style={{ ...inp, marginBottom: 8 }} />
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={cadence} onChange={e => setCadence(e.target.value)} style={{ ...inp, flex: 1 }}>
          {CAD.map(([k, l, hint]) => <option key={k} value={k}>{l} — {hint}</option>)}
        </select>
      </div>
      <input placeholder="Notes (optional)" value={desc} onChange={e => setDesc(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit() }} style={{ ...inp, marginBottom: 10 }} />
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn onClick={submit} tone={C.accent} solid disabled={busy || !title.trim()}>Add duty</Btn>
        <Btn onClick={() => setOpen(false)}>Cancel</Btn>
      </div>
    </div>
  )
}

// ── Handover checklist ───────────────────────────────────────────────────────

function StatusPicker({ value, onChange, busy }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {ITEM_STATUS.map(([k, label, tone]) => (
        <button key={k} disabled={busy} onClick={() => onChange(k)} style={{
          padding: '3px 8px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
          border: `1px solid ${value === k ? tone : C.hair2}`,
          background: value === k ? tone : 'transparent',
          color: value === k ? '#08110b' : C.dim, fontWeight: value === k ? 600 : 400,
        }}>{label}</button>
      ))}
    </div>
  )
}

function ItemRow({ item, onStatus, onNote, onDelete, busy }) {
  const [note, setNote] = useState(item.note || '')
  useEffect(() => { setNote(item.note || '') }, [item.id])
  return (
    <div style={{ padding: '10px 0', borderBottom: `1px solid ${C.hair}` }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: C.text, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            {item.label}
            {item.cadence && <Chip>{CAD_LABEL[item.cadence] || item.cadence}</Chip>}
            {item.source_kind === 'custom' && <Chip tone={C.accent}>Knowledge</Chip>}
            {item.source_kind === 'area' && <Chip>Roster</Chip>}
          </div>
          {item.detail && <div style={{ fontSize: 11.5, color: C.dim, marginTop: 1 }}>{item.detail}</div>}
        </div>
        {item.source_kind === 'custom' && (
          <button title="Remove" disabled={busy} onClick={() => onDelete(item)}
            style={{ border: 'none', background: 'transparent', color: C.faint, cursor: 'pointer', fontSize: 15 }}>×</button>
        )}
      </div>
      <div style={{ marginTop: 7, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <StatusPicker value={item.status} onChange={s => onStatus(item, s)} busy={busy} />
      </div>
      <input placeholder="Handover note (what was shown, where to find it…)" value={note}
        onChange={e => setNote(e.target.value)} onBlur={() => { if (note !== (item.note || '')) onNote(item, note) }}
        style={{ width: '100%', marginTop: 7, padding: '5px 8px', borderRadius: 6, border: `1px solid ${C.hair}`, background: 'transparent', color: C.dim, fontSize: 12 }} />
    </div>
  )
}

function AddKnowledge({ onAdd, busy }) {
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [detail, setDetail] = useState('')
  const submit = async () => { if (!label.trim()) return; await onAdd({ label: label.trim(), detail: detail.trim() || null }); setLabel(''); setDetail(''); setOpen(false) }
  if (!open) return <Btn onClick={() => setOpen(true)}>+ Add knowledge / access</Btn>
  const inp = { width: '100%', padding: '7px 9px', borderRadius: 7, border: `1px solid ${C.hair2}`, background: C.surface, color: C.text, fontSize: 13, marginBottom: 8 }
  return (
    <div style={{ border: `1px solid ${C.hair2}`, borderRadius: 9, padding: 12, marginTop: 8, background: C.surface }}>
      <input autoFocus placeholder="e.g. Where the shed key lives" value={label} onChange={e => setLabel(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setOpen(false) }} style={inp} />
      <input placeholder="Detail (optional)" value={detail} onChange={e => setDetail(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit() }} style={inp} />
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn onClick={submit} tone={C.accent} solid disabled={busy || !label.trim()}>Add</Btn>
        <Btn onClick={() => setOpen(false)}>Cancel</Btn>
      </div>
    </div>
  )
}

function HandoverPanel({ handover, onStatus, onNote, onAddItem, onDeleteItem, onReseed, onComplete, onDelete, busy }) {
  const p = handover.progress || {}
  const done = handover.status === 'completed'
  return (
    <div style={{ border: `1px solid ${C.hair2}`, borderRadius: 11, padding: 14, marginTop: 10, background: C.surface }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            Onboarding {handover.incoming_name || 'a new volunteer'}
          </div>
          <div style={{ fontSize: 11.5, color: C.dim, marginTop: 2 }}>
            {handover.outgoing_name ? `Handing over from ${handover.outgoing_name}. ` : ''}
            {handover.target_date ? `Target: ${handover.target_date}. ` : ''}
            {done ? 'Completed.' : `${p.accepted}/${p.applicable} accepted, ${p.gaps} to go.`}
          </div>
        </div>
        <Chip tone={progTone(p)}>{done ? 'Complete' : `${p.percent ?? 0}%`}</Chip>
      </div>
      <div style={{ margin: '10px 0 14px' }}><Bar percent={p.percent ?? 0} tone={progTone(p)} /></div>

      {(handover.items || []).map(it => (
        <ItemRow key={it.id} item={it} busy={busy}
          onStatus={onStatus} onNote={onNote} onDelete={onDeleteItem} />
      ))}

      <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <AddKnowledge onAdd={onAddItem} busy={busy} />
        <Btn onClick={onReseed} busy={busy}>Refresh from program</Btn>
        {!done && <Btn onClick={onComplete} tone={C.ok} solid disabled={busy}>Mark complete</Btn>}
        <Btn onClick={onDelete} tone={C.block} disabled={busy} style={{ marginLeft: 'auto' }}>Delete</Btn>
      </div>
    </div>
  )
}

function StartHandover({ members, onStart, busy }) {
  const [open, setOpen] = useState(false)
  const [inMember, setInMember] = useState('')
  const [inName, setInName] = useState('')
  const [outMember, setOutMember] = useState('')
  const [target, setTarget] = useState('')
  const submit = async () => {
    await onStart({
      incoming_member_id: inMember || null, incoming_name: inMember ? null : (inName.trim() || null),
      outgoing_member_id: outMember || null, target_date: target || null,
    })
    setOpen(false); setInMember(''); setInName(''); setOutMember(''); setTarget('')
  }
  if (!open) return <Btn onClick={() => setOpen(true)} tone={C.accent} solid>Start a handover</Btn>
  const inp = { width: '100%', padding: '7px 9px', borderRadius: 7, border: `1px solid ${C.hair2}`, background: C.surface, color: C.text, fontSize: 13, marginBottom: 8 }
  const memberOpts = members.map(m => <option key={m.id} value={m.id}>{m.full_name || m.name}</option>)
  return (
    <div style={{ border: `1px solid ${C.hair2}`, borderRadius: 11, padding: 14, background: C.surface }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Start a handover</div>
      <Caption tone={C.dim} style={{ marginBottom: 4 }}>WHO IS TAKING THE ROLE ON</Caption>
      <select value={inMember} onChange={e => setInMember(e.target.value)} style={inp}>
        <option value="">A member…</option>{memberOpts}
      </select>
      {!inMember && <input placeholder="…or type a name" value={inName} onChange={e => setInName(e.target.value)} style={inp} />}
      <Caption tone={C.dim} style={{ marginBottom: 4 }}>HANDING OVER FROM (OPTIONAL)</Caption>
      <select value={outMember} onChange={e => setOutMember(e.target.value)} style={inp}>
        <option value="">Nobody / not recorded</option>{memberOpts}
      </select>
      <Caption tone={C.dim} style={{ marginBottom: 4 }}>TARGET DATE TO FINISH ONBOARDING (OPTIONAL)</Caption>
      <input type="date" value={target} onChange={e => setTarget(e.target.value)} style={inp} />
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <Btn onClick={submit} tone={C.accent} solid disabled={busy || (!inMember && !inName.trim())}>Start</Btn>
        <Btn onClick={() => setOpen(false)}>Cancel</Btn>
      </div>
    </div>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────────

export default function RolePrograms({ st, patch, narrow }) {
  const [roles, setRoles] = useState([])
  const [members, setMembers] = useState([])
  const [sel, setSel] = useState(null)
  const [program, setProgram] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [openDetail, setOpenDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [params, setParams] = useSearchParams()
  const q = (st.rpQuery || '').trim()

  const loadRoles = useCallback(async () => {
    const r = await api.raRoles({ includeInactive: false }).then(x => x?.roles || x || []).catch(() => [])
    // Attach the active handover (if any) for the onboarding badge, cheaply: one
    // list call across the whole club, indexed by role.
    const hs = await api.rpListHandovers({ status: 'in_progress' }).then(x => x?.handovers || []).catch(() => [])
    const byRole = {}
    hs.forEach(h => { if (h.role_id && !byRole[h.role_id]) byRole[h.role_id] = h })
    setRoles(r.map(x => ({ ...x, _handover: byRole[x.id] })))
  }, [])

  useEffect(() => {
    loadRoles()
    api.feeAllMembers().then(r => setMembers(r?.members || r || [])).catch(() => setMembers([]))
  }, [loadRoles])

  // Deep link ?role=<id>
  useEffect(() => {
    const rid = params.get('role')
    if (rid && rid !== sel) { setSel(rid); setParams({}, { replace: true }) }
  }, [])  // eslint-disable-line

  const loadProgram = useCallback(async (roleId) => {
    if (!roleId) { setProgram(null); return }
    const p = await api.rpProgram(roleId).catch(() => null)
    setProgram(p)
    setOpenId(p?.active_handover_id || null)
  }, [])

  useEffect(() => { loadProgram(sel) }, [sel, loadProgram])

  useEffect(() => {
    if (!openId) { setOpenDetail(null); return }
    api.rpHandover(openId).then(setOpenDetail).catch(() => setOpenDetail(null))
  }, [openId])

  const toast = (msg) => patch({ toast: msg })
  const guard = async (fn, msg) => {
    setBusy(true)
    try { await fn() } catch (e) { toast(e?.message || msg || 'Something went wrong') } finally { setBusy(false) }
  }

  const addDuty = (body) => guard(async () => {
    await api.diaryCreateDefinition({ ...body, responsibility_role_id: sel })
    await loadProgram(sel)
  }, 'Could not add the duty')
  const removeDuty = (d) => guard(async () => {
    if (!window.confirm(`Remove "${d.title}" from this role's program? (It is archived in the Club Diary, not deleted.)`)) return
    await api.diaryArchiveDefinition(d.definition_id)
    await loadProgram(sel)
  })

  const startHandover = (body) => guard(async () => {
    const h = await api.rpCreateHandover({ role_id: sel, ...body })
    await loadProgram(sel); await loadRoles()
    setOpenId(h.id); setOpenDetail(h)
  }, 'Could not start the handover')

  // Item/handover writes all return the full handover — set it straight in.
  const setStatus = (item, status) => guard(async () => setOpenDetail(await api.rpUpdateItem(openId, item.id, { status })))
  const setNote = (item, note) => guard(async () => setOpenDetail(await api.rpUpdateItem(openId, item.id, { note })))
  const addItem = (body) => guard(async () => setOpenDetail(await api.rpAddItem(openId, body)))
  const deleteItem = (item) => guard(async () => setOpenDetail(await api.rpDeleteItem(openId, item.id)))
  const reseed = () => guard(async () => { const h = await api.rpReseedHandover(openId); setOpenDetail(h); toast(h.added ? `Added ${h.added} new item${h.added > 1 ? 's' : ''}` : 'Already up to date') })
  const complete = () => guard(async () => { setOpenDetail(await api.rpUpdateHandover(openId, { status: 'completed' })); await loadProgram(sel); await loadRoles() })
  const deleteHandover = () => guard(async () => {
    if (!window.confirm('Delete this handover record? This cannot be undone.')) return
    await api.rpDeleteHandover(openId); setOpenId(null); setOpenDetail(null)
    await loadProgram(sel); await loadRoles()
  })

  const shown = roles.filter(r => matchesQuery(q, r.title, r.role_type_name))
  const role = program?.role
  const duties = program?.duties || []
  const pastHandovers = (program?.handovers || []).filter(h => h.id !== openId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div style={HEAD_SIDE}>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Role programs</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>WHAT EACH ROLE INVOLVES, AND HANDING IT OVER</Caption>
        </div>
        <HeaderSearch value={st.rpQuery} onChange={v => patch({ rpQuery: v })} placeholder="Search roles…" width={300} />
      </ScreenHeader>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Roles rail */}
        <div className="pb-scroll" style={{ width: 260, borderRight: `1px solid ${C.hair}`, overflowY: 'auto', flexShrink: 0 }}>
          {shown.length === 0 && <div style={{ padding: 16, fontSize: 12.5, color: C.dim }}>No roles yet. Add them under Areas &amp; roles, or add committee positions on the Committee screen.</div>}
          {shown.map(r => <RoleRow key={r.id} role={r} active={r.id === sel} onClick={() => setSel(r.id)} />)}
        </div>

        {/* Program + handovers */}
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, minWidth: 0 }}>
          {!role && <div style={{ color: C.dim, fontSize: 13, maxWidth: 460 }}>Pick a role to see what it involves and to track handing it over to a new volunteer. A role's duties are Club Diary tasks tagged to it, so the calendar and the program stay in step.</div>}
          {role && (
            <div style={{ maxWidth: 760 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{role.title}</h2>
                {role.is_committee ? <Chip tone={C.warn}>Committee</Chip> : (role.role_type_name && <Chip>{role.role_type_name}</Chip>)}
                {program.current_holders?.length > 0 && <span style={{ fontSize: 12, color: C.dim }}>Held by {program.current_holders.join(', ')}</span>}
              </div>
              {role.description && <p style={{ fontSize: 13.5, color: C.dim, marginTop: 8, marginBottom: 0 }}>{role.description}</p>}
              {program.committee?.responsibilities && (
                <p style={{ fontSize: 13, color: C.dim, marginTop: 8, whiteSpace: 'pre-wrap' }}>{program.committee.responsibilities}</p>
              )}

              {/* What this role involves */}
              <div style={{ marginTop: 22 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>What this role involves</div>
                  <ManageLink to="/admin/club-diary">Edit in Club Diary</ManageLink>
                </div>
                <div style={{ marginTop: 10 }}>
                  {duties.length === 0 && <div style={{ fontSize: 12.5, color: C.dim, marginBottom: 8 }}>No duties recorded yet. Add the recurring, seasonal and match-day tasks this role does — they become Club Diary tasks tagged to the role.</div>}
                  {CAD.map(([k, l]) => (
                    <DutyGroup key={k} cadence={k} label={l} busy={busy}
                      duties={duties.filter(d => d.cadence === k)} onRemove={removeDuty} />
                  ))}
                  <AddDuty onAdd={addDuty} busy={busy} />
                </div>
              </div>

              {/* Areas it covers */}
              {program.areas?.length > 0 && (
                <div style={{ marginTop: 22 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>Operational areas it covers</div>
                  {program.areas.map(a => (
                    <div key={a.area_id} style={{ fontSize: 13, color: C.text, padding: '4px 0', borderBottom: `1px solid ${C.hair}` }}>
                      {a.name}{a.required_qualification && <span style={{ color: C.dim }}> — needs {a.required_qualification}</span>}
                    </div>
                  ))}
                </div>
              )}

              {/* Succession & handover */}
              <div style={{ marginTop: 26 }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Succession &amp; handover</div>
                <Caption tone={C.dim} style={{ marginBottom: 10 }}>TRACK A NEW VOLUNTEER UNDERSTANDING AND ACCEPTING THE ROLE</Caption>
                {!openDetail && <StartHandover members={members} onStart={startHandover} busy={busy} />}
                {openDetail && (
                  <HandoverPanel handover={openDetail} busy={busy}
                    onStatus={setStatus} onNote={setNote} onAddItem={addItem} onDeleteItem={deleteItem}
                    onReseed={reseed} onComplete={complete} onDelete={deleteHandover} />
                )}
                {pastHandovers.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <Caption tone={C.dim} style={{ marginBottom: 6 }}>{openDetail ? 'OTHER HANDOVERS' : 'HANDOVERS'}</Caption>
                    {pastHandovers.map(h => (
                      <button key={h.id} onClick={() => setOpenId(h.id)} style={{
                        display: 'flex', width: '100%', textAlign: 'left', gap: 10, alignItems: 'center', cursor: 'pointer',
                        padding: '8px 0', border: 'none', borderBottom: `1px solid ${C.hair}`, background: 'transparent',
                      }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, color: C.text }}>{h.incoming_name || 'A new volunteer'}</div>
                          <div style={{ fontSize: 11, color: C.dim }}>{h.status === 'completed' ? 'Completed' : 'In progress'}{h.started_on ? ` · started ${h.started_on}` : ''}</div>
                        </div>
                        <div style={{ width: 90 }}><Bar percent={h.progress?.percent ?? 0} tone={progTone(h.progress)} /></div>
                        <Chip tone={progTone(h.progress)}>{h.progress?.percent ?? 0}%</Chip>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
