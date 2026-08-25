import { useState, useEffect, useRef } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO } from '../ui'

// Full editor for roster Operational Areas: Starter Pack, create/edit/delete,
// drag-reorder, and a nested shift-pattern editor per area (add/remove the
// repeating weekly shifts the roster generates from). Each area's Department is
// picked from a managed catalogue (with an inline "＋ New" option); the
// Departments catalogue itself is CRUD'd + seeded on its own "Departments"
// secondary tab (see AreasRoles).

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const SWATCHES = ['#f5b542', '#f97316', '#3b82f6', '#06b6d4', '#16c784', '#a855f7', 'var(--pb-accent)', '#ef5b5b']
const fmtHour = (h) => { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); if (hh >= 24) return '12am'; let b = hh % 12; if (b === 0) b = 12; return b + (mm ? ':' + String(mm).padStart(2, '0') : '') + (hh >= 12 ? 'pm' : 'am') }

const inp = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '7px 10px', color: C.text, fontSize: 13, outline: 'none', width: '100%' }
const btnP = { padding: '7px 13px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }
const btnS = { padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }

// `query` narrows what is DRAWN and nothing else — `areas` stays whole, so a
// drag still renumbers against the real list rather than against whatever
// happens to be on screen. Same contract EntityManager's own `query` keeps.
export default function AreaEditor({ focusAreaId = null, onFocused = null, query = '' }) {
  const [areas, setAreas] = useState(null)
  const [roles, setRoles] = useState([])
  const [quals, setQuals] = useState([])
  const [departments, setDepartments] = useState([])
  const [newDept, setNewDept] = useState(false)  // area form: "＋ New department" chosen
  const [busy, setBusy] = useState(false)
  const [editId, setEditId] = useState(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({})
  const [openId, setOpenId] = useState(null)
  const [pat, setPat] = useState({ day_of_week: 5, start_time: '12', end_time: '18', headcount: '1' })
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)

  const refresh = () => api.rosterAreas().then(r => setAreas(r?.areas || r || []))
  const reloadDepartments = () => api.rosterDepartments().then(r => setDepartments(r?.departments || r || [])).catch(() => {})
  useEffect(() => {
    refresh()
    api.raRoles().then(r => setRoles(r?.roles || r || [])).catch(() => {})
    api.qualListTypes().then(r => setQuals(r?.types || r || [])).catch(() => {})
    reloadDepartments()
  }, [])

  // Arriving from a link on another screen (the Roster's area names): open that
  // area's shift editor, ring it and scroll it into view. It waits for the areas
  // to load, then fires once — `onFocused` tells the parent to forget the link
  // so coming back to this tab later doesn't re-open the same area. The ring is
  // held in local state rather than read from the prop, so clearing the link
  // doesn't take the highlight away with it.
  const focused = useRef(false)
  const rowRefs = useRef({})
  const [linkedId, setLinkedId] = useState(null)
  useEffect(() => {
    if (focused.current || !focusAreaId || !areas) return
    const hit = areas.find(a => String(a.id) === String(focusAreaId))
    if (!hit) return
    focused.current = true
    setOpenId(hit.id); setLinkedId(hit.id)
    setTimeout(() => { rowRefs.current[String(hit.id)]?.scrollIntoView({ block: 'center', behavior: 'smooth' }) }, 60)
    if (onFocused) onFocused()
  }, [areas, focusAreaId])

  const blank = { name: '', department: '', color: SWATCHES[0], required_role_id: '', required_qualification_type_id: '' }
  const startAdd = () => { setForm({ ...blank }); setNewDept(false); setAdding(true); setEditId(null) }
  const startEdit = (a) => { setForm({ name: a.name || '', department: a.department || '', color: a.color || SWATCHES[0], required_role_id: a.required_role_id || '', required_qualification_type_id: a.required_qualification_type_id || '' }); setNewDept(false); setEditId(a.id); setAdding(false) }
  const cancel = () => { setAdding(false); setEditId(null); setNewDept(false) }
  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.name) return
    setBusy(true)
    const dept = (form.department || '').trim()
    const body = { name: form.name, department: dept || null, color: form.color || null, required_role_id: form.required_role_id || null, required_qualification_type_id: form.required_qualification_type_id || null }
    try {
      // A department typed in the "new" field that isn't in the catalogue yet is
      // added to it, so it shows in the dropdown from now on.
      if (dept && !departments.some(d => d.name.toLowerCase() === dept.toLowerCase())) {
        await api.rosterCreateDepartment({ name: dept }).catch(() => {})
      }
      if (editId) await api.rosterUpdateArea(editId, body); else await api.rosterCreateArea(body)
      await refresh(); await reloadDepartments(); cancel()
    } finally { setBusy(false) }
  }
  const remove = async (a) => { if (!window.confirm('Remove the "' + a.name + '" area and its shift patterns?')) return; setBusy(true); try { await api.rosterDeleteArea(a.id); await refresh() } finally { setBusy(false) } }
  const seed = async () => { setBusy(true); try { await api.rosterSeedStarter(); await refresh(); await reloadDepartments() } finally { setBusy(false) } }

  const addPattern = async (areaId) => {
    const s = Number(pat.start_time), e = Number(pat.end_time), hc = Math.max(1, Number(pat.headcount) || 1)
    if (isNaN(s) || isNaN(e) || e <= s) return
    await api.rosterAddPattern(areaId, { day_of_week: Number(pat.day_of_week), start_time: s, end_time: e, headcount: hc }).catch(() => {})
    await refresh()
  }
  const delPattern = async (pid) => { await api.rosterDeletePattern(pid).catch(() => {}); await refresh() }

  const move = (fromId, toId) => {
    setDragId(null); setOverId(null)
    if (!fromId || fromId === toId) return
    const arr = [...areas]; const fi = arr.findIndex(x => x.id === fromId), ti = arr.findIndex(x => x.id === toId)
    if (fi < 0 || ti < 0) return
    const [m] = arr.splice(fi, 1); arr.splice(ti, 0, m); setAreas(arr)
    api.rosterReorderAreas(arr.map(x => x.id)).catch(() => {})
  }

  const roleOpts = roles.filter(r => !r.is_committee)
  // A stored department value that isn't (any longer) in the catalogue — show it
  // in the free-text field so it's editable rather than silently lost.
  const deptIsCustom = !!(form.department && !departments.some(d => d.name.toLowerCase() === (form.department || '').toLowerCase()))
  const formCard = (
    <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: 14, marginBottom: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>NAME *<input value={form.name} onChange={e => setF('name', e.target.value)} style={{ ...inp, marginTop: 3 }} /></label>
        <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>DEPARTMENT
          <select value={(newDept || deptIsCustom) ? '__new__' : (form.department || '')}
            onChange={e => { const v = e.target.value; if (v === '__new__') { setNewDept(true); if (!deptIsCustom) setF('department', '') } else { setNewDept(false); setF('department', v) } }}
            style={{ ...inp, marginTop: 3 }}>
            <option value="">None</option>
            {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            <option value="__new__">＋ New department…</option>
          </select>
          {(newDept || deptIsCustom) && <input value={form.department} placeholder="New department name" onChange={e => setF('department', e.target.value)} style={{ ...inp, marginTop: 6 }} />}
        </label>
        <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>ROLE THAT COVERS IT<select value={form.required_role_id} onChange={e => setF('required_role_id', e.target.value)} style={{ ...inp, marginTop: 3 }}><option value="">Any role</option>{roleOpts.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label>
        <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>QUALIFICATION THAT GATES IT<select value={form.required_qualification_type_id} onChange={e => setF('required_qualification_type_id', e.target.value)} style={{ ...inp, marginTop: 3 }}><option value="">None</option>{quals.map(q => <option key={q.id} value={q.id}>{q.name}</option>)}</select></label>
      </div>
      <div style={{ marginTop: 10 }}>
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginBottom: 5 }}>COLOUR</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {SWATCHES.map(c => <span key={c} onClick={() => setF('color', c)} style={{ width: 20, height: 20, borderRadius: 5, background: c, cursor: 'pointer', outline: form.color === c ? '2px solid #fff' : 'none', outlineOffset: 1 }} />)}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button onClick={submit} disabled={busy || !form.name} style={{ ...btnP, opacity: (busy || !form.name) ? 0.6 : 1 }}>{editId ? 'Save area' : 'Add area'}</button>
        <button onClick={cancel} style={btnS}>Cancel</button>
      </div>
    </div>
  )

  if (areas === null) return <div style={{ fontSize: 13, color: C.faint }}>Loading operational areas…</div>

  const q = (query || '').trim().toLowerCase()
  const shown = !q ? areas : areas.filter(a => [a.name, a.department, a.required_role_name, a.required_qualification_name]
    .some(v => v != null && String(v).toLowerCase().includes(q)))

  return (
    <div>
      <p style={{ fontSize: 13, color: C.dim, margin: '0 0 14px', lineHeight: 1.55, maxWidth: '46rem' }}>An operational area is a slice of club work with its own weekly shift pattern, the role that can cover it and the qualification that gates it. Change a pattern here and next week's roster is generated from it.</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {!adding && editId == null && <button onClick={startAdd} style={btnS}>+ Add area</button>}
        {areas.length === 0 && <button onClick={seed} disabled={busy} style={{ ...btnP, opacity: busy ? 0.6 : 1 }}>{busy ? 'Adding…' : 'Add Operational Areas Starter Pack'}</button>}
        {!q && areas.length > 1 && <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faintest, alignSelf: 'center' }}>DRAG THE GRIP TO REORDER</span>}
      </div>

      {adding && formCard}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {shown.map(a => {
          if (editId === a.id) return <div key={a.id}>{formCard}</div>
          const slots = (a.patterns || []).reduce((n, p) => n + (p.headcount || 1), 0)
          const isOver = overId === a.id && dragId && dragId !== a.id
          const open = openId === a.id
          const linked = linkedId === a.id
          return (
            <div key={a.id} ref={el => { rowRefs.current[String(a.id)] = el }}
              onDragOver={e => { if (dragId && !q) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (overId !== a.id) setOverId(a.id) } }}
              onDrop={e => { e.preventDefault(); move(dragId, a.id) }}
              style={{ background: C.surface, border: `1px solid ${isOver || linked ? C.accent : C.hair}`, borderRadius: 9, padding: '13px 15px', boxShadow: isOver ? 'inset 0 2px 0 var(--pb-accent)' : (linked ? '0 0 0 2px color-mix(in srgb, var(--pb-accent) 25%, transparent)' : undefined), opacity: dragId === a.id ? 0.5 : 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {!q && <span draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; setDragId(a.id) }} onDragEnd={() => { setDragId(null); setOverId(null) }} title="Drag to reorder" style={{ cursor: 'grab', color: C.faint, fontSize: 15, lineHeight: 1, flexShrink: 0, userSelect: 'none' }}>⠿</span>}
                <span style={{ width: 9, height: 9, borderRadius: 3, background: a.color || C.accent, flexShrink: 0 }} />
                <span style={{ fontSize: 14.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{a.name}{a.department ? <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 8 }}>{a.department}</span> : null}</span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.dim, flexShrink: 0 }}>{slots} shift{slots === 1 ? '' : 's'} / week</span>
                <button onClick={() => setOpenId(open ? null : a.id)} style={{ ...btnS, padding: '5px 10px', fontSize: 11.5 }}>{open ? 'Hide shifts' : 'Shifts'}</button>
                <button onClick={() => startEdit(a)} style={{ ...btnS, padding: '5px 10px', fontSize: 11.5 }}>Edit</button>
                <button onClick={() => remove(a)} style={{ padding: '5px 10px', borderRadius: 6, fontSize: 11.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer' }}>Delete</button>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, margin: '6px 0 0' }}>{[a.required_role_name, a.required_qualification_name ? 'must hold ' + a.required_qualification_name : null].filter(Boolean).join(' · ') || 'Any role · no qualification'}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 9 }}>
                {(a.patterns || []).map(p => (
                  <span key={p.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 9.5, padding: '3px 5px 3px 7px', borderRadius: 5, background: `color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 12%, transparent)`, border: `1px solid color-mix(in srgb, ${a.color || 'var(--pb-accent)'} 35%, transparent)`, color: a.color || 'var(--pb-accent)' }}>
                    {DOW[p.day_of_week]} {fmtHour(p.start_time)}–{fmtHour(p.end_time)}{p.headcount > 1 ? ' ×' + p.headcount : ''}
                    {open && <span onClick={() => delPattern(p.id)} title="Remove" style={{ cursor: 'pointer', opacity: 0.7, fontSize: 12 }}>×</span>}
                  </span>
                ))}
                {(a.patterns || []).length === 0 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>No shift pattern yet</span>}
              </div>
              {open && (
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginTop: 10, flexWrap: 'wrap', borderTop: `1px solid ${C.hair}`, paddingTop: 10 }}>
                  <label style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>DAY<select value={pat.day_of_week} onChange={e => setPat(p => ({ ...p, day_of_week: e.target.value }))} style={{ ...inp, width: 78, marginTop: 3 }}>{DOW.map((d, i) => <option key={i} value={i}>{d}</option>)}</select></label>
                  <label style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>START (24h)<input type="number" step="0.5" value={pat.start_time} onChange={e => setPat(p => ({ ...p, start_time: e.target.value }))} style={{ ...inp, width: 82, marginTop: 3 }} /></label>
                  <label style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>END (24h)<input type="number" step="0.5" value={pat.end_time} onChange={e => setPat(p => ({ ...p, end_time: e.target.value }))} style={{ ...inp, width: 82, marginTop: 3 }} /></label>
                  <label style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>PEOPLE<input type="number" min="1" value={pat.headcount} onChange={e => setPat(p => ({ ...p, headcount: e.target.value }))} style={{ ...inp, width: 64, marginTop: 3 }} /></label>
                  <button onClick={() => addPattern(a.id)} style={{ ...btnP, padding: '7px 12px' }}>Add shift</button>
                </div>
              )}
            </div>
          )
        })}
        {shown.length === 0 && !adding && (
          <div style={{ fontSize: 13, color: C.faint }}>{q ? 'Nothing matches “' + query.trim() + '”.' : 'No operational areas yet.'}</div>
        )}
      </div>
    </div>
  )
}
