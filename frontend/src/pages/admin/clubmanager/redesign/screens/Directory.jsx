import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, initials } from '../ui'

// Directory — one record per person, on REAL club data. The person spine is
// fee_members (a member's player_id links to a stats player where one exists,
// and is NULL for a non-player: committee member, life member, canteen parent,
// third party…). Players belong to Stats/Core and appear read-through; a
// player gets a member row lazily the first time ClubManager assigns them a
// role. ClubManager owns adding/editing non-player people and their roles here.

// The segments list_people computes, each as a filter. Life member / Official /
// Honorary were already worked out per person and simply had nowhere to be
// filtered on, so a club could not pull up its life members.
const DIR_SEGS = [
  { seg: 'All', label: 'Everyone' },
  { seg: 'Player', label: 'Players' },
  { seg: 'Volunteer', label: 'Volunteers' },
  { seg: 'Committee', label: 'Committees' },
  { seg: 'Parent', label: 'Parents' },
  { seg: 'Third party', label: 'Third parties' },
  { seg: 'Official', label: 'Officials' },
  { seg: 'Life member', label: 'Life members' },
  { seg: 'Honorary', label: 'Honorary' },
]
// Stored as full day names, matching what the Volunteers screen has always
// written and what services/roster.day_index reads back tolerantly.
const DAY_KEYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const CATS = [
  { value: 'volunteer', label: 'Volunteer' },
  { value: 'parent', label: 'Parent' },
  { value: 'committee', label: 'Committee' },
  { value: 'third_party', label: 'Third party' },
  { value: 'official', label: 'Official (umpire, scorer…)', short: 'Official' },
  { value: 'life_member', label: 'Life member' },
  { value: 'other', label: 'Other' },
]
const CAT_SHORT = Object.fromEntries(CATS.map(c => [c.value, c.short || c.label]))
// Filter value for "nobody has said what kind of member this is" — the gap a
// club works through when it first fills the catalogue in.
const NO_TYPE = '__none__'

// One line answering "what kind of member is this?". A club may keep the
// membership-type catalogue (Senior Player, Social Member, Sponsor Contact…),
// or just the category this module tags a non-player with, or neither and only
// play cricket — so this reads whichever they actually keep rather than
// insisting on one.
function typeLabel(p) {
  if (p.membership_type) return p.membership_type
  if (p.category) return CAT_SHORT[p.category] || p.category
  if (p.player_id) return p.player_status === 'inactive' ? 'Former player' : 'Player'
  return 'Member'
}

function qualStatus(expiryISO) {
  if (!expiryISO) return { key: 'current', label: 'NO EXPIRY', fg: C.ok }
  const days = Math.round((new Date(expiryISO) - new Date()) / 86400000)
  if (days < 0) return { key: 'expired', label: 'EXPIRED', fg: '#ef5b5b' }
  if (days <= 60) return { key: 'soon', label: 'EXPIRES SOON', fg: '#f5b542' }
  return { key: 'current', label: 'CURRENT', fg: '#16c784' }
}
function fmtExpiry(iso) {
  if (!iso) return 'no expiry'
  const d = new Date(iso)
  return 'expires ' + d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()] + ' ' + d.getFullYear()
}

export default function Directory({ st, patch, narrow }) {
  const [people, setPeople] = useState(null)   // null = loading
  const [memberTypes, setMemberTypes] = useState([])  // the club's membership-type catalogue
  const [err, setErr] = useState(null)
  const [roleCatalogue, setRoleCatalogue] = useState([])   // general (non-committee) club roles
  const [qualTypes, setQualTypes] = useState([])
  const [positions, setPositions] = useState([])
  const [families, setFamilies] = useState([])
  const [detail, setDetail] = useState({})     // { [memberId]: { quals, hours, overlays } }
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState(null)     // null | { editId, form }
  const [imp, setImp] = useState(null)         // null | { text, preview, result }
  const [qualForm, setQualForm] = useState({ type_id: '', obtained_at: '' })
  const [newFamily, setNewFamily] = useState('')
  const [activities, setActivities] = useState([])
  const [logForm, setLogForm] = useState({ hours: '', activity_id: '', logged_date: new Date().toISOString().slice(0, 10) })

  const reload = () => api.dirPeople(st.dirShowArchived).then(res => {
    setPeople(res?.people || [])
    setMemberTypes(res?.membership_types || [])
  }).catch(e => setErr(String(e?.message || e)))
  const reloadFamilies = () => api.dirFamilies().then(r => setFamilies(r?.families || [])).catch(() => {})
  useEffect(() => { reload() }, [st.dirShowArchived]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.raRoles().then(r => setRoleCatalogue((r?.roles || r || []).filter(x => !x.is_committee && x.role_type_category !== 'committee'))).catch(() => {})
    api.qualListTypes().then(r => setQualTypes(r?.types || r || [])).catch(() => {})
    api.dirCommitteePositions().then(r => setPositions(r?.positions || [])).catch(() => {})
    api.raActivities().then(r => setActivities(r?.activities || r || [])).catch(() => {})
    reloadFamilies()
  }, [])

  const q = (st.dirQuery || '').toLowerCase()
  const seg = st.dirSeg || 'All'
  const roleFilter = st.dirRole || null
  const expiringOnly = !!st.dirExpiring
  const typeFilter = st.dirType || ''          // '' = any membership type
  const playing = st.dirPlaying || 'all'       // all | active | inactive

  const roleTitles = (p) => (p.roles || []).map(r => r.title)
  const list = (people || []).filter(p => {
    if (seg !== 'All' && !p.segs.includes(seg)) return false
    if (typeFilter === NO_TYPE && p.membership_type_id) return false
    if (typeFilter && typeFilter !== NO_TYPE && p.membership_type_id !== typeFilter) return false
    // Playing status comes from Stats and only means something for someone with
    // a player record, so both filters exclude non-players rather than lumping
    // them in with the inactive.
    if (playing === 'active' && !(p.player_id && p.player_status !== 'inactive')) return false
    if (playing === 'inactive' && !(p.player_id && p.player_status === 'inactive')) return false
    if (roleFilter && !roleTitles(p).includes(roleFilter)) return false
    if (expiringOnly && !p.flagged) return false
    if (q && !(p.name.toLowerCase().includes(q) || roleTitles(p).join(' ').toLowerCase().includes(q) || typeLabel(p).toLowerCase().includes(q))) return false
    return true
  })

  const selId = st.dirSel && (people || []).some(p => p.key === st.dirSel) ? st.dirSel : (list[0] ? list[0].key : null)
  const sel = (people || []).find(p => p.key === selId) || null

  // Load (or reload) one member's quals + hours + overlays into the detail
  // cache. Called both on select and after a mutation — a mutation can't rely
  // on the select effect re-running (member_id is unchanged), so it re-fetches
  // through here directly.
  const loadDetail = (memberId) => Promise.all([
    api.qualListMemberQualifications(memberId).catch(() => []),
    api.volunteerListHours(memberId).catch(() => []),
    api.dirMemberOverlays(memberId).catch(() => ({ committee: [], families: [] })),
    api.volunteerProfile(memberId).catch(() => null),
  ]).then(([qRes, hRes, oRes, pRes]) => {
    const quals = (Array.isArray(qRes) ? qRes : (qRes?.qualifications || qRes?.items || [])).map(x => ({
      id: x.id, name: x.type_name || x.name || x.qualification_name || 'Qualification',
      expiry: x.expires_at || x.expiry || null,
    }))
    const raw = (Array.isArray(hRes) ? hRes : (hRes?.hours || []))
    const byAct = {}
    raw.forEach(h => {
      const a = h.activity || h.activity_name || h.activity_type || 'Other'
      byAct[a] = (byAct[a] || 0) + Number(h.hours || 0)
    })
    const hours = Object.entries(byAct).sort((a, b) => b[1] - a[1])
    const overlays = { committee: oRes?.committee || [], families: oRes?.families || [], shifts_this_week: oRes?.shifts_this_week || 0, diary_open: oRes?.diary_open || 0 }
    const profile = {
      available_days: pRes?.available_days || [],
      roles_interested: pRes?.roles_interested || [],
      lives_nearby: !!pRes?.lives_nearby,
    }
    setDetail(d => ({ ...d, [memberId]: { quals, hours, hoursRaw: raw, overlays, profile } }))
  })
  useEffect(() => {
    if (!sel || !sel.member_id || detail[sel.member_id]) return
    loadDetail(sel.member_id)
  }, [sel?.member_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const det = sel && sel.member_id ? detail[sel.member_id] : null
  const quals = (det?.quals || []).map(qq => ({ ...qq, st: qualStatus(qq.expiry) }))
  const hours = det?.hours || []
  const overlays = det?.overlays || { committee: [], families: [], shifts_this_week: 0, diary_open: 0 }
  const hoursRaw = det?.hoursRaw || []
  const profile = det?.profile || { available_days: [], roles_interested: [], lives_nearby: false }
  // Re-fetch this member's detail directly (not via the select effect, which
  // won't re-run for the same member_id) and refresh the people list.
  const refreshMember = async (mid) => { await Promise.all([loadDetail(mid), reload()]) }

  // ── mutations ──────────────────────────────────────────────────────────────
  const openAdd = () => setModal({ editId: null, form: { full_name: '', email: '', mobile: '', member_category: 'volunteer', membership_type_id: '', notes: '' } })
  const openEdit = (p) => setModal({ editId: p.member_id, form: { full_name: p.name, email: p.email, mobile: p.phone, member_category: p.category || 'other', membership_type_id: p.membership_type_id || '', notes: '' } })
  const setForm = (k, v) => setModal(m => ({ ...m, form: { ...m.form, [k]: v } }))
  const saveMember = async () => {
    const f = modal.form
    if (!(f.full_name || '').trim()) return
    setBusy(true)
    try {
      if (modal.editId) { await api.dirUpdateMember(modal.editId, f); await reload() }
      else { const r = await api.dirCreateMember(f); await reload(); patch({ dirSel: r.member_id }) }
      setModal(null)
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const archive = async (p) => {
    if (!p.member_id) return
    if (!window.confirm('Archive ' + p.name + '? They can be restored later, and their history is kept.')) return
    setBusy(true); try { await api.dirArchiveMember(p.member_id); await reload(); patch({ dirSel: null }) } finally { setBusy(false) }
  }
  const restore = async (p) => {
    if (!p.member_id) return
    setBusy(true); try { await api.dirRestoreMember(p.member_id); await reload() } finally { setBusy(false) }
  }
  const assignRole = async (p, roleId) => {
    if (!roleId) return
    setBusy(true)
    try {
      let memberId = p.member_id
      if (!memberId) { const r = await api.dirEnsureMemberForPlayer(p.player_id); memberId = r.member_id }
      await api.dirAddRole(memberId, roleId)
      await reload(); patch({ dirSel: memberId })
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  // The volunteer profile — when they can help, what they would help with,
  // whether they live close enough for a short-notice call. Saved a field at a
  // time; the endpoint leaves anything it is not sent alone.
  const saveProfile = async (p, patchFields) => {
    if (!p.member_id) return
    setBusy(true)
    try {
      await api.volunteerUpsertProfile({ member_id: p.member_id, ...patchFields })
      await refreshMember(p.member_id)
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const toggleDay = (p, day) => {
    const cur = profile.available_days || []
    const next = cur.includes(day) ? cur.filter(d => d !== day) : [...cur, day]
    saveProfile(p, { available_days: DAY_KEYS.filter(d => next.includes(d)) })
  }
  const addInterest = (p, text) => {
    const t = (text || '').trim()
    if (!t) return
    const cur = profile.roles_interested || []
    if (cur.some(x => x.toLowerCase() === t.toLowerCase())) return
    saveProfile(p, { roles_interested: [...cur, t] })
  }
  const removeInterest = (p, text) =>
    saveProfile(p, { roles_interested: (profile.roles_interested || []).filter(x => x !== text) })

  const removeRole = async (p, roleId) => {
    if (!p.member_id) return
    setBusy(true); try { await api.dirRemoveRole(p.member_id, roleId); await reload() } finally { setBusy(false) }
  }
  const runPreview = async () => {
    setBusy(true); try { const r = await api.dirImportPreview(imp.text); setImp(m => ({ ...m, preview: r, result: null })) } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const runImport = async () => {
    setBusy(true); try { const r = await api.dirImportCommit(imp.text); await reload(); setImp(m => ({ ...m, result: r })) } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const onImportFile = (file) => { if (!file) return; const rd = new FileReader(); rd.onload = () => setImp(m => ({ ...m, text: String(rd.result || ''), preview: null, result: null })); rd.readAsText(file) }
  const assignQual = async () => {
    if (!qualForm.type_id || !sel?.member_id) return
    setBusy(true)
    try { await api.qualAddQualification({ member_id: sel.member_id, qualification_type_id: qualForm.type_id, obtained_at: qualForm.obtained_at || null }); setQualForm({ type_id: '', obtained_at: '' }); await refreshMember(sel.member_id) }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const removeQual = async (qid) => { if (!qid) return; setBusy(true); try { await api.qualDeleteQualification(qid); await refreshMember(sel.member_id) } finally { setBusy(false) } }
  const assignCommittee = async (positionId) => {
    if (!positionId || !sel?.member_id) return
    setBusy(true); try { await api.dirAssignCommittee(sel.member_id, positionId); await refreshMember(sel.member_id) } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const removeCommittee = async (termId) => { setBusy(true); try { await api.dirRemoveCommittee(sel.member_id, termId); await refreshMember(sel.member_id) } finally { setBusy(false) } }
  const addToFamily = async (familyId) => {
    if (!familyId || !sel?.member_id) return
    setBusy(true); try { await api.dirAddToFamily(sel.member_id, familyId, { is_guardian: sel.category === 'parent' }); await refreshMember(sel.member_id) } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const removeFromFamily = async (familyId) => { setBusy(true); try { await api.dirRemoveFromFamily(sel.member_id, familyId); await refreshMember(sel.member_id) } finally { setBusy(false) } }
  const createAndAddFamily = async () => {
    const name = newFamily.trim()
    if (!name || !sel?.member_id) return
    setBusy(true)
    try { const r = await api.dirCreateFamily(name); await api.dirAddToFamily(sel.member_id, r.family_id, { is_guardian: sel.category === 'parent' }); setNewFamily(''); await reloadFamilies(); await refreshMember(sel.member_id) }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const logHours = async () => {
    if (!sel?.member_id || !Number(logForm.hours)) return
    setBusy(true)
    try { await api.volunteerLogHours({ member_id: sel.member_id, hours: Number(logForm.hours), activity_id: logForm.activity_id || null, logged_date: logForm.logged_date }); setLogForm({ hours: '', activity_id: '', logged_date: new Date().toISOString().slice(0, 10) }); await refreshMember(sel.member_id) }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const removeHours = async (id) => { setBusy(true); try { await api.volunteerDeleteHours(id); await refreshMember(sel.member_id) } finally { setBusy(false) } }

  const pill = (active, tone = 'accent') => {
    const on = { accent: ['color-mix(in srgb, var(--pb-accent) 45%, transparent)', 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', C.accent], amber: ['rgba(245,181,66,0.45)', 'rgba(245,181,66,0.12)', C.warn] }[tone]
    return { padding: '5px 11px', borderRadius: 999, fontSize: 12, cursor: 'pointer', border: `1px solid ${active ? on[0] : C.hair2}`, background: active ? on[1] : 'transparent', color: active ? on[2] : C.dim }
  }
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const inp = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '8px 11px', color: C.text, fontSize: 13, outline: 'none', width: '100%' }
  const btnP = { padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }
  const btnS = { padding: '6px 12px', borderRadius: 7, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }
  const avatar = (size, fs = 10) => ({ width: size, height: size, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: fs, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, overflow: 'hidden' })
  const Avatar = ({ p, size, fs }) => p?.photo
    ? <img src={p.photo} alt="" style={{ ...avatar(size, fs), objectFit: 'cover' }} />
    : <span style={avatar(size, fs)}>{initials(p.name)}</span>

  const assignedIds = new Set((sel?.roles || []).map(r => r.id))
  const unassignedRoles = roleCatalogue.filter(r => !assignedIds.has(r.id))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Directory</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>One record per person · {list.length}{people ? ' of ' + people.length : ''} shown</Caption>
        </div>
        <input placeholder="Search name or role…" value={st.dirQuery || ''} onChange={e => patch({ dirQuery: e.target.value })}
          style={{ flex: 1, minWidth: 180, maxWidth: 300, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {DIR_SEGS.map(s => <button key={s.seg} onClick={() => patch({ dirSeg: s.seg })} style={pill(seg === s.seg)}>{s.label}</button>)}
          {/* Playing status is the Stats active/inactive flag, so a club can
              tell this season's players from the ones who have stopped without
              losing either from the directory. */}
          <button onClick={() => patch({ dirPlaying: playing === 'active' ? 'all' : 'active' })} style={pill(playing === 'active')}>Playing</button>
          <button onClick={() => patch({ dirPlaying: playing === 'inactive' ? 'all' : 'inactive' })} style={pill(playing === 'inactive')}>Former players</button>
          {memberTypes.length > 0 && (
            <select value={typeFilter} onChange={e => patch({ dirType: e.target.value })}
              title="Filter by membership type"
              style={{ background: C.surface2, border: `1px solid ${typeFilter ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`, borderRadius: 999, padding: '5px 11px', color: typeFilter ? C.accent : C.dim, fontSize: 12, outline: 'none', cursor: 'pointer' }}>
              <option value="">Any membership type</option>
              {memberTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              <option value={NO_TYPE}>No type set</option>
            </select>
          )}
          <button onClick={() => patch({ dirExpiring: !expiringOnly })} style={pill(expiringOnly, 'amber')}>Quals to renew</button>
          <button onClick={() => patch({ dirShowArchived: !st.dirShowArchived })} style={pill(!!st.dirShowArchived, 'amber')}>Show archived</button>
          {roleFilter && <button onClick={() => patch({ dirRole: null })} style={{ ...pill(true), display: 'inline-flex', alignItems: 'center', gap: 6 }}>Role: {roleFilter}  ✕</button>}
          <button onClick={() => setImp({ text: '', preview: null, result: null })} style={btnS}>Import CSV</button>
          <button onClick={openAdd} style={btnP}>+ Add person</button>
          {/* The dedicated editors for the three overlays this record shows.
              The panels below cover the everyday case (add a role, log hours,
              record a qualification, link a family); these are where the
              catalogues and bulk work live. */}
          <Link to="/admin/clubhouse/directory/families" style={btnS}>Families</Link>
          <Link to="/admin/clubhouse/directory/qualifications" style={btnS}>Qualifications</Link>
          <Link to="/admin/clubhouse/directory/volunteers" style={btnS}>Volunteer bulk entry</Link>
        </div>
      </ScreenHeader>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div className="pb-scroll" style={{ width: 300, flex: '0 0 300px', borderRight: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 10 }}>
          {people === null && <div style={{ padding: '20px 12px', fontSize: 13, color: C.faint }}>{err ? 'Could not load the directory.' : 'Loading your club…'}</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {list.map(p => (
              <div key={p.key} onClick={() => patch({ dirSel: p.key })}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 8, cursor: 'pointer', border: p.key === selId ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : '1px solid transparent', background: p.key === selId ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : 'transparent' }}>
                <Avatar p={p} size={30} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: p.archived ? C.faint : C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}{p.archived ? <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '0.08em', color: C.warn, border: `1px solid ${C.warn}66`, borderRadius: 3, padding: '1px 4px', marginLeft: 6 }}>ARCHIVED</span> : null}</div>
                  {/* What kind of member they are first, then what they do —
                      the roles used to be the only line, so a person with no
                      role read as a blank "Member" whatever they actually are. */}
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    <span style={{ color: C.dim }}>{typeLabel(p)}</span>
                    {p.player_status === 'inactive' && <span style={{ color: C.faintest }}> · inactive</span>}
                    {p.is_life_member && <span style={{ color: C.accent }}> · life</span>}
                    {roleTitles(p).length > 0 && ' · ' + roleTitles(p).join(' · ')}
                  </div>
                </div>
                {p.flagged > 0 && <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.warn, flexShrink: 0 }} />}
                {p.total_hours > 0 && <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0 }}>{p.total_hours}h</span>}
              </div>
            ))}
            {people && list.length === 0 && <div style={{ padding: '20px 12px', fontSize: 13, color: C.faint }}>Nobody matches those filters.</div>}
          </div>
        </div>

        {sel && (
          <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
              <Avatar p={sel} size={52} fs={16} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 22, letterSpacing: '-0.01em' }}>{sel.name}</div>
                <div style={{ fontSize: 12.5, color: C.faint, marginTop: 3 }}>{[sel.email, sel.phone].filter(Boolean).join('  ·  ') || 'No contact details recorded'}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {/* The membership type leads, accented, because it is the
                      club's own answer for this person; the segments after it
                      are what the rest of the module worked out about them. */}
                  <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: C.accent }}>{typeLabel(sel)}</span>
                  {sel.player_status === 'inactive' && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.warn}66`, color: C.warn }}>NOT PLAYING</span>}
                  {sel.segs.map(s => <span key={s} style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.dim }}>{s}</span>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {sel.member_id && !sel.archived && <button onClick={() => openEdit(sel)} style={btnS}>Edit</button>}
                {sel.member_id && (sel.archived
                  ? <button onClick={() => restore(sel)} disabled={busy} style={{ ...btnP, opacity: busy ? 0.6 : 1 }}>Restore</button>
                  : <button onClick={() => archive(sel)} style={{ ...btnS, color: C.faint }}>Archive</button>)}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 22 }}>
              {[
                { value: (sel.total_hours || 0) + 'h', label: 'HOURS THIS SEASON' },
                { value: sel.member_id ? String(overlays.shifts_this_week) : '—', label: 'SHIFTS THIS WEEK' },
                { value: sel.member_id ? String(overlays.diary_open) : '—', label: 'DIARY TASKS' },
                { value: String(sel.flagged || 0), label: 'QUALS TO RENEW' },
              ].map((s, i) => (
                <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                  <div style={{ fontWeight: 700, fontSize: 19, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 3 }}>{s.label}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px' }}>
              <section>
                <div style={cap}>ROLES</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
                  {(sel.roles || []).map(r => (
                    <span key={r.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: C.accent, borderRadius: 5, padding: '3px 6px 3px 9px', fontSize: 12.5 }}>
                      <span onClick={() => patch({ dirRole: r.title, dirSeg: 'All' })} style={{ cursor: 'pointer' }}>{r.title}</span>
                      <span onClick={() => removeRole(sel, r.id)} title="Remove role" style={{ cursor: 'pointer', opacity: 0.7, fontSize: 13 }}>×</span>
                    </span>
                  ))}
                  {(sel.roles || []).length === 0 && <span style={{ fontSize: 13, color: C.faint }}>No club roles assigned.</span>}
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 10, alignItems: 'center' }}>
                  <select disabled={busy || unassignedRoles.length === 0} value="" onChange={e => assignRole(sel, e.target.value)} style={{ ...inp, width: 'auto', flex: 1, maxWidth: 240, opacity: busy ? 0.6 : 1 }}>
                    <option value="">{unassignedRoles.length ? '+ Assign a role…' : 'All roles assigned'}</option>
                    {unassignedRoles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
                  </select>
                </div>
                {!sel.member_id && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 6 }}>Assigning a role adds this player to the member directory.</div>}
              </section>
              <section>
                <div style={cap}>QUALIFICATIONS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {quals.map((qq, i) => (
                    <div key={qq.id || i} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '8px 11px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text }}>{qq.name}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{fmtExpiry(qq.expiry)}</div>
                      </div>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 7px', borderRadius: 4, border: `1px solid ${qq.st.fg}66`, color: qq.st.fg, flexShrink: 0 }}>{qq.st.label}</span>
                      {qq.id && <span onClick={() => removeQual(qq.id)} title="Remove" style={{ cursor: 'pointer', color: C.faint, fontSize: 14, flexShrink: 0 }}>×</span>}
                    </div>
                  ))}
                  {sel.member_id && !det && <div style={{ fontSize: 13, color: C.faint }}>Loading…</div>}
                  {det && quals.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>None recorded.</div>}
                  {!sel.member_id && <div style={{ fontSize: 13, color: C.faint }}>Assign a role first to start tracking qualifications.</div>}
                </div>
                {sel.member_id && (
                  <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <select value={qualForm.type_id} onChange={e => setQualForm(f => ({ ...f, type_id: e.target.value }))} style={{ ...inp, width: 'auto', flex: 1, minWidth: 130 }}>
                      <option value="">+ Add qualification…</option>
                      {qualTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                    <input type="date" title="Obtained on" value={qualForm.obtained_at} onChange={e => setQualForm(f => ({ ...f, obtained_at: e.target.value }))} style={{ ...inp, width: 'auto' }} />
                    <button onClick={assignQual} disabled={busy || !qualForm.type_id} style={{ ...btnS, opacity: (busy || !qualForm.type_id) ? 0.6 : 1 }}>Add</button>
                  </div>
                )}
              </section>
              <section>
                <div style={cap}>COMMITTEE</div>
                {!sel.member_id ? (
                  <div style={{ fontSize: 13, color: C.faint }}>Assign a role first, then committee positions can be recorded.</div>
                ) : (
                  <>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {overlays.committee.map(c => (
                        <span key={c.term_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: c.is_office_bearer ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : C.surface2, border: `1px solid ${c.is_office_bearer ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`, color: c.is_office_bearer ? C.accent : C.text, borderRadius: 5, padding: '3px 6px 3px 9px', fontSize: 12.5 }}>
                          {c.name}{c.is_office_bearer ? ' · office bearer' : ''}<span onClick={() => removeCommittee(c.term_id)} title="End term" style={{ cursor: 'pointer', opacity: 0.7, fontSize: 13 }}>×</span>
                        </span>
                      ))}
                      {overlays.committee.length === 0 && <span style={{ fontSize: 13, color: C.faint }}>No committee position.</span>}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <select value="" onChange={e => assignCommittee(e.target.value)} disabled={busy || positions.length === 0} style={{ ...inp, width: 'auto', maxWidth: 260, opacity: busy ? 0.6 : 1 }}>
                        <option value="">{positions.length ? '+ Assign a position…' : 'No positions set up'}</option>
                        {positions.filter(p => !overlays.committee.some(c => c.position_id === p.id)).map(p => <option key={p.id} value={p.id}>{p.name}{p.is_office_bearer ? ' (office bearer)' : ''}</option>)}
                      </select>
                    </div>
                    <div style={{ ...cap, marginTop: 16 }}>FAMILY</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {overlays.families.map(f => (
                        <span key={f.family_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.text, borderRadius: 5, padding: '3px 6px 3px 9px', fontSize: 12.5 }}>
                          {f.name}{f.is_guardian ? ' · guardian' : ''}<span onClick={() => removeFromFamily(f.family_id)} title="Remove from family" style={{ cursor: 'pointer', opacity: 0.7, fontSize: 13 }}>×</span>
                        </span>
                      ))}
                      {overlays.families.length === 0 && <span style={{ fontSize: 13, color: C.faint }}>No family linked.</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <select value="" onChange={e => addToFamily(e.target.value)} disabled={busy} style={{ ...inp, width: 'auto', maxWidth: 180, opacity: busy ? 0.6 : 1 }}>
                        <option value="">+ Add to family…</option>
                        {families.filter(f => !overlays.families.some(x => x.family_id === f.id)).map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                      </select>
                      <input value={newFamily} onChange={e => setNewFamily(e.target.value)} placeholder="New family name" style={{ ...inp, width: 'auto', flex: 1, minWidth: 120 }} />
                      <button onClick={createAndAddFamily} disabled={busy || !newFamily.trim()} style={{ ...btnS, opacity: (busy || !newFamily.trim()) ? 0.6 : 1 }}>Create</button>
                    </div>
                  </>
                )}
              </section>

              {/* Availability lives here rather than on a separate screen: it is
                  the thing you want to change at the moment you notice it is
                  wrong, which is while you are looking at the person. Each
                  control saves on its own — there is no Save button to miss. */}
              <section>
                <div style={cap}>AVAILABILITY</div>
                {!sel.member_id ? (
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>Assign a role first to record availability.</div>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {DAY_KEYS.map(d => {
                        const on = (profile.available_days || []).includes(d)
                        return (
                          <button key={d} disabled={busy} onClick={() => toggleDay(sel, d)}
                            title={on ? `Available ${d}` : `Not available ${d}`}
                            style={{ padding: '4px 9px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
                              border: `1px solid ${on ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`,
                              background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent',
                              color: on ? C.accent : C.dim }}>{d.slice(0, 3)}</button>
                        )
                      })}
                    </div>
                    {(profile.available_days || []).length === 0 && (
                      <div style={{ fontSize: 12.5, color: C.faint, marginTop: 7 }}>
                        No days set, so the roster will not offer them for a shift.
                      </div>
                    )}

                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, cursor: 'pointer', fontSize: 13, color: C.dim }}>
                      <input type="checkbox" disabled={busy} checked={!!profile.lives_nearby}
                        onChange={e => saveProfile(sel, { lives_nearby: e.target.checked })} />
                      Lives nearby
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>· can help at short notice</span>
                    </label>

                    <div style={{ ...cap, marginTop: 14 }}>WOULD ALSO HELP WITH</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
                      {(profile.roles_interested || []).map(r => (
                        <span key={r} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${C.hair2}`, color: C.dim, borderRadius: 999, padding: '3px 6px 3px 10px', fontSize: 12 }}>
                          {r}
                          <span onClick={() => removeInterest(sel, r)} title="Remove" style={{ cursor: 'pointer', opacity: 0.7, fontSize: 13 }}>×</span>
                        </span>
                      ))}
                      {(profile.roles_interested || []).length === 0 && (
                        <span style={{ fontSize: 12.5, color: C.faint }}>Nothing noted.</span>
                      )}
                    </div>
                    <input placeholder="Anything they have offered to do…" disabled={busy}
                      onKeyDown={e => { if (e.key === 'Enter') { addInterest(sel, e.currentTarget.value); e.currentTarget.value = '' } }}
                      style={{ ...inp, marginTop: 8 }} />
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 5 }}>
                      Free text, and theirs not yours — what this person said they would do, not what the club needs.
                    </div>
                  </>
                )}
              </section>
              {/* Pinned to the right-hand column. Five sections flowing row by
                  row would drop the fifth back onto the left, and this one
                  belongs under availability — the two together are the answer
                  to "when can they help, and how much have they already". */}
              <section style={{ gridColumn: 2 }}>
                <div style={cap}>HOURS BY ACTIVITY</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {hours.map(([activity, h], i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{ fontSize: 12.5, color: C.dim }}>{activity}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: C.text }}>{h}h</span>
                      </div>
                      <div style={{ height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden', marginTop: 4 }}>
                        <div style={{ height: '100%', width: Math.round((h / Math.max(...hours.map(x => x[1]))) * 100) + '%', background: C.accent }} />
                      </div>
                    </div>
                  ))}
                  {(!det || hours.length === 0) && <div style={{ fontSize: 13, color: C.faint }}>No hours logged yet.</div>}
                </div>
                {sel.member_id ? (
                  <>
                    <div style={{ display: 'flex', gap: 6, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                      <input type="number" min="0" step="0.5" value={logForm.hours} placeholder="Hrs" onChange={e => setLogForm(f => ({ ...f, hours: e.target.value }))} style={{ ...inp, width: 64 }} />
                      <select value={logForm.activity_id} onChange={e => setLogForm(f => ({ ...f, activity_id: e.target.value }))} style={{ ...inp, width: 'auto', flex: 1, minWidth: 120 }}>
                        <option value="">Activity (optional)…</option>
                        {activities.map(a => <option key={a.id} value={a.id}>{a.title}</option>)}
                      </select>
                      <input type="date" value={logForm.logged_date} onChange={e => setLogForm(f => ({ ...f, logged_date: e.target.value }))} style={{ ...inp, width: 'auto' }} />
                      <button onClick={logHours} disabled={busy || !Number(logForm.hours)} style={{ ...btnS, opacity: (busy || !Number(logForm.hours)) ? 0.6 : 1 }}>Log</button>
                    </div>
                    {hoursRaw.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 8 }}>
                        {hoursRaw.slice(0, 6).map(h => (
                          <div key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: MONO, fontSize: 10, color: C.faint }}>
                            <span style={{ width: 74, flexShrink: 0 }}>{h.logged_date || ''}</span>
                            <span style={{ color: C.dim, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{h.activity || 'Other'}</span>
                            <span style={{ color: C.text }}>{Number(h.hours)}h</span>
                            <span onClick={() => removeHours(h.id)} title="Remove" style={{ cursor: 'pointer', fontSize: 12 }}>×</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 6 }}>Assign a role first to log hours.</div>}
              </section>
            </div>

            <div style={{ marginTop: 24, borderTop: `1px solid ${C.hair}`, paddingTop: 16 }}>
              <button onClick={() => patch({ screen: 'roster', navOpen: false })} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Open this week's roster →</button>
            </div>
          </div>
        )}
      </div>

      {modal && (
        <div onClick={() => setModal(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 'min(460px, 100%)', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>{modal.editId ? 'Edit person' : 'Add a person'}</div>
            <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16 }}>{modal.editId ? 'Update this person’s details.' : 'Add a non-playing member or third party. Players are managed in Stats.'}</div>
            <div style={{ display: 'grid', gap: 11 }}>
              <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>NAME *<input value={modal.form.full_name} onChange={e => setForm('full_name', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 11 }}>
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>EMAIL<input value={modal.form.email} onChange={e => setForm('email', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>MOBILE<input value={modal.form.mobile} onChange={e => setForm('mobile', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
              </div>
              <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>TYPE<select value={modal.form.member_category} onChange={e => setForm('member_category', e.target.value)} style={{ ...inp, marginTop: 4 }}>{CATS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
              {/* The club's own catalogue, shared with BetterFees — only offered
                  when they keep one, since nothing seeds it automatically. */}
              {memberTypes.length > 0 && (
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>MEMBERSHIP TYPE
                  <select value={modal.form.membership_type_id} onChange={e => setForm('membership_type_id', e.target.value)} style={{ ...inp, marginTop: 4 }}>
                    <option value="">— none —</option>
                    {memberTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </label>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
              <button onClick={() => setModal(null)} style={btnS}>Cancel</button>
              <button onClick={saveMember} disabled={busy || !(modal.form.full_name || '').trim()} style={{ ...btnP, opacity: (busy || !(modal.form.full_name || '').trim()) ? 0.6 : 1 }}>{modal.editId ? 'Save' : 'Add person'}</button>
            </div>
          </div>
        </div>
      )}

      {imp && (
        <div onClick={() => setImp(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 'min(560px, 100%)', maxHeight: '86vh', overflowY: 'auto', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>Import people from CSV</div>
            <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 14, lineHeight: 1.5 }}>
              Non-players and third parties. Columns: <span style={{ fontFamily: MONO, fontSize: 11 }}>name, email, mobile, category, roles</span> (only <span style={{ fontFamily: MONO, fontSize: 11 }}>name</span> required; <span style={{ fontFamily: MONO, fontSize: 11 }}>roles</span> is a comma-separated list of role titles). Matched to existing people by name, so a re-run tops up rather than duplicates. Players are imported in Stats.
            </div>
            {imp.result ? (
              <div style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 14, fontSize: 13, color: C.text }}>
                Imported. {imp.result.created} added, {imp.result.updated} updated, {imp.result.roles_added} role assignments.
                <div style={{ marginTop: 12 }}><button onClick={() => setImp(null)} style={btnP}>Done</button></div>
              </div>
            ) : (
              <>
                <input type="file" accept=".csv,text/csv" onChange={e => onImportFile(e.target.files?.[0])} style={{ fontSize: 12.5, color: C.dim, marginBottom: 8 }} />
                <textarea value={imp.text} onChange={e => setImp(m => ({ ...m, text: e.target.value, preview: null }))} placeholder={'name,email,mobile,category,roles\nJane Doe,jane@x.com,0400000000,parent,"Canteen Manager, First Aid Officer"'}
                  style={{ ...inp, minHeight: 120, fontFamily: MONO, fontSize: 11.5, resize: 'vertical' }} />
                {imp.preview && (
                  <div style={{ marginTop: 12, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 12 }}>
                    <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>{imp.preview.total} row{imp.preview.total === 1 ? '' : 's'}: <b>{imp.preview.new}</b> new, <b>{imp.preview.existing}</b> existing.</div>
                    <div style={{ maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {imp.preview.rows.map((r, i) => (
                        <div key={i} style={{ fontSize: 12, color: C.dim, display: 'flex', gap: 8, alignItems: 'baseline' }}>
                          <span style={{ fontFamily: MONO, fontSize: 9, color: r.existing ? C.warn : C.ok, width: 46, flexShrink: 0 }}>{r.existing ? 'UPDATE' : 'NEW'}</span>
                          <span style={{ color: C.text }}>{r.name}</span>
                          {r.category && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{r.category}</span>}
                          {r.roles.length > 0 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.accent }}>{r.roles.join(', ')}</span>}
                          {r.unknown_roles.length > 0 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.warn }} title="Not a known role — skipped">?{r.unknown_roles.join(', ')}</span>}
                        </div>
                      ))}
                    </div>
                    {imp.preview.rows.some(r => r.unknown_roles.length > 0) && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.warn, marginTop: 8 }}>Role titles marked ? aren’t set up yet and will be skipped — add them in Areas &amp; Roles first.</div>}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                  <button onClick={() => setImp(null)} style={btnS}>Cancel</button>
                  {!imp.preview
                    ? <button onClick={runPreview} disabled={busy || !imp.text.trim()} style={{ ...btnP, opacity: (busy || !imp.text.trim()) ? 0.6 : 1 }}>Preview</button>
                    : <button onClick={runImport} disabled={busy || imp.preview.total === 0} style={{ ...btnP, opacity: (busy || imp.preview.total === 0) ? 0.6 : 1 }}>Import {imp.preview.total} {imp.preview.total === 1 ? 'person' : 'people'}</button>}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
