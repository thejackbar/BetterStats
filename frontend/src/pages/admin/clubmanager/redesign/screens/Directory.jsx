import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../../../../lib/api'
import { useAuth } from '../../../../../contexts/AuthContext'
import { CAP } from '../../../../../lib/capabilities'
import { C, MONO, Caption, ScreenHeader, NavToggle, initials, MenuButton, MenuItem, MenuHeading, MenuDivider, FilterChip } from '../ui'

// Directory — one record per person, on REAL club data. The person spine is
// fee_members (a member's player_id links to a stats player where one exists,
// and is NULL for a non-player: committee member, life member, canteen parent,
// third party…). Players belong to Stats/Core and appear read-through; a
// player gets a member row lazily the first time ClubManager assigns them a
// role. ClubManager owns adding/editing non-player people and their roles here.

// THREE AXES, and each gets ONE control rather than a row of pills.
//
//   MEMBERSHIP — what kind of member. Built from the club's OWN catalogue, so a
//     club that adds "Country Member" gets it for free. Players is derived from
//     the Stats record rather than the catalogue, so the axis still works for a
//     club that has adopted no catalogue at all.
//   ROLES      — what they do. Independent of membership: an umpire may hold
//     the role and no membership whatsoever.
//   HONOURS    — Life membership, bestowed on a member of any type.
//
// Each axis is its own single-select and they AND together, so Senior Player +
// Volunteers is now askable — one shared `dirSeg` could not express it. They
// are menus rather than pills because the membership options come from club
// data: as one flat row the control count grew with the club's catalogue, which
// is how this header reached ~26 controls.
//
// A membership type carries the `type:` prefix so a club that named a type
// "Volunteer" (every club that adopted the pre-235 starter set has one) cannot
// collide with the Volunteer ROLE.
const TYPE_PREFIX = 'type:'
const ROLE_SEGS = [
  { seg: 'Volunteer', label: 'Volunteers' },
  { seg: 'Committee', label: 'Committee' },
  { seg: 'Official', label: 'Officials' },
]
const HONOUR_SEGS = [
  { seg: 'Life member', label: 'Life members' },
]
const PLAYING_LABEL = { active: 'Playing', inactive: 'Former players' }
const EMAIL_LABEL = { has: 'Has email', none: 'No email' }
// Stored as full day names, matching what the Volunteers screen has always
// written and what services/roster.day_index reads back tolerantly.
const DAY_KEYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
// The pre-235 single-valued tag. No longer written here — membership is the
// catalogue and roles are roles — but still READ, so a club that tagged people
// before the split keeps a sensible label until it types them properly.
const CAT_SHORT = {
  volunteer: 'Volunteer', parent: 'Parent', committee: 'Committee',
  third_party: 'External contact', official: 'Official',
  life_member: 'Life member', other: 'Member',
}
// Filter value for "nobody has said what kind of member this is" — the gap a
// club works through when it first fills the catalogue in.
const NO_TYPE = '__none__'

// One line answering "what kind of member is this?". Every type they hold, not
// just the primary — a Senior Player who is also a Parent is both, and showing
// one of them was the whole problem. A club may keep no catalogue at all, so
// this falls back to the pre-235 category tag and then to the Stats record.
function typeLabel(p) {
  const held = (p.membership_types || []).map(t => t.name)
  if (held.length) return held.join(' · ')
  if (p.category) return CAT_SHORT[p.category] || p.category
  if (p.player_id) return p.player_status === 'inactive' ? 'Former player' : 'Player'
  // NULL, not "Member" — someone with no membership type may genuinely not be
  // one. A panel umpire holds an Official role and joined nothing, and calling
  // them a member on the strength of having a record is the assertion this
  // whole split exists to stop.
  return null
}

// A field edited where it is read. Click the value, type, Enter or blur saves,
// Escape cancels.
//
// Name, email and phone are all searchable or filterable ("Has email" / "No
// email" drive the whole Create-a-list flow), so they have to be settable AND
// clearable on the person — a filter you can act on but not fix sends you to a
// dialog to undo what you just found.
function InlineField({ value, placeholder, onSave, busy, type = 'text', style }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const start = () => { setDraft(value || ''); setEditing(true) }
  const commit = () => {
    setEditing(false)
    if ((draft || '') !== (value || '')) onSave(draft.trim())
  }
  if (!editing) {
    return (
      <span onClick={start} title="Click to edit"
        style={{ cursor: 'pointer', borderBottom: `1px dashed ${C.hair2}`, ...style }}>
        {value || <span style={{ color: C.faint }}>{placeholder}</span>}
      </span>
    )
  }
  return (
    <input autoFocus type={type} value={draft} disabled={busy} placeholder={placeholder}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
        if (e.key === 'Escape') { setEditing(false) }
      }}
      style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 6,
        padding: '2px 7px', color: C.text, fontSize: 'inherit', fontWeight: 'inherit', outline: 'none', ...style }} />
  )
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
  const navigate = useNavigate()
  // Playing status lives on the Stats player record and its endpoint wants
  // MANAGE_PLAYERS, which a volunteer or committee manager working the
  // Directory does not necessarily hold. Gate the control rather than offer one
  // that 403s; without the capability the status is still shown, just read-only.
  const { hasCapability } = useAuth()
  const canEditPlayers = hasCapability(CAP.MANAGE_PLAYERS)
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
  const [mkList, setMkList] = useState(null)   // null | { name, result, error }
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
  // One selection per axis, AND-combined. `dirSeg` keeps its name (and its
  // 'All' reset value) because Today.jsx and the role chip already send it.
  const seg = st.dirSeg || 'All'               // membership axis
  const roleSeg = st.dirRoleSeg || null        // role axis
  const honourSeg = st.dirHonour || null       // honour axis
  const roleFilter = st.dirRole || null        // a specific role TITLE
  const expiringOnly = !!st.dirExpiring
  const typeFilter = st.dirType || ''          // '' = any membership type
  const playing = st.dirPlaying || 'all'       // all | active | inactive

  // The catalogue, split by scope. Internal types are the club's own members;
  // external ones are people it records but has not gained as members.
  const internalTypes = memberTypes.filter(t => (t.scope || 'internal') !== 'external')
  const externalTypes = memberTypes.filter(t => (t.scope || 'internal') === 'external')

  const roleTitles = (p) => (p.roles || []).map(r => r.title)
  const emailFilter = st.dirEmail || null   // null | 'has' | 'none'
  const hasEmail = (p) => !!(p.email || '').trim()
  const list = (people || []).filter(p => {
    if (seg !== 'All' && !p.segs.includes(seg)) return false
    if (roleSeg && !p.segs.includes(roleSeg)) return false
    if (honourSeg && !p.segs.includes(honourSeg)) return false
    // "No type set" is about the whole set now, not the primary — someone
    // holding two types and no primary is plainly typed.
    if (typeFilter === NO_TYPE && (p.membership_types || []).length) return false
    // Playing status comes from Stats and only means something for someone with
    // a player record, so both filters exclude non-players rather than lumping
    // them in with the inactive.
    if (playing === 'active' && !(p.player_id && p.player_status !== 'inactive')) return false
    if (playing === 'inactive' && !(p.player_id && p.player_status === 'inactive')) return false
    if (roleFilter && !roleTitles(p).includes(roleFilter)) return false
    if (expiringOnly && !p.flagged) return false
    if (emailFilter === 'has' && !hasEmail(p)) return false
    if (emailFilter === 'none' && hasEmail(p)) return false
    if (q && !(p.name.toLowerCase().includes(q) || roleTitles(p).join(' ').toLowerCase().includes(q) || (typeLabel(p) || '').toLowerCase().includes(q))) return false
    return true
  })
  // How much of the current filter is actually reachable. Shown on the header
  // and used to talk the admin through what a list will and will not contain.
  const emailable = list.filter(hasEmail).length

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
  const openAdd = () => setModal({ editId: null, playerId: null, form: { full_name: '', email: '', mobile: '', notes: '' }, types: [] })
  const openEdit = (p) => setModal({ editId: p.member_id, playerId: p.player_id, form: { full_name: p.name, email: p.email, mobile: p.phone, notes: '' }, types: (p.membership_types || []).map(t => t.id) })
  const setForm = (k, v) => setModal(m => ({ ...m, form: { ...m.form, [k]: v } }))
  const toggleModalType = (id) => setModal(m => ({ ...m, types: m.types.includes(id) ? m.types.filter(x => x !== id) : [...m.types, id] }))
  const saveMember = async () => {
    const f = modal.form
    if (!(f.full_name || '').trim()) return
    setBusy(true)
    try {
      // Resolve the person row FIRST, three ways: an existing member, a
      // read-through player whose row is minted on demand (never create — that
      // would leave two records for one person), or somebody genuinely new.
      let mid = modal.editId
      if (!mid && modal.playerId) mid = (await api.dirEnsureMemberForPlayer(modal.playerId)).member_id
      if (!mid) mid = (await api.dirCreateMember(f)).member_id
      else await api.dirUpdateMember(mid, f)
      await api.dirSetMemberTypes(mid, { type_ids: modal.types })
      await reload()
      patch({ dirSel: mid })
      setModal(null)
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  // Membership types. A read-through player has no person row until something
  // is recorded about them, so the player endpoint mints one — same as
  // assigning a role.
  const toggleType = async (p, typeId) => {
    const held = (p.membership_types || []).map(t => t.id)
    const next = held.includes(typeId) ? held.filter(x => x !== typeId) : [...held, typeId]
    setBusy(true)
    try {
      if (p.member_id) await api.dirSetMemberTypes(p.member_id, { type_ids: next })
      else { const r = await api.dirSetPlayerTypes(p.player_id, { type_ids: next }); patch({ dirSel: r.member_id }) }
      await reload()
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const setPrimaryType = async (p, typeId) => {
    if (!p.member_id) return
    setBusy(true)
    try {
      await api.dirSetMemberTypes(p.member_id, { type_ids: (p.membership_types || []).map(t => t.id), primary_id: typeId })
      await reload()
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const setLifeMember = async (p, on, since) => {
    setBusy(true)
    try {
      const body = { is_life_member: on, ...(since === undefined ? {} : { since }) }
      if (p.member_id) await api.dirSetLifeMembership(p.member_id, body)
      else { const r = await api.dirSetPlayerLifeMembership(p.player_id, body); patch({ dirSel: r.member_id }) }
      await reload()
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  // Name, email and phone, saved from the person's own header. Resolves the
  // person row the same three ways saveMember does, so a read-through player
  // can have contact details recorded without being duplicated.
  const savePersonField = async (p, key, value) => {
    setBusy(true)
    try {
      let mid = p.member_id
      if (!mid && p.player_id) mid = (await api.dirEnsureMemberForPlayer(p.player_id)).member_id
      if (!mid) return
      await api.dirUpdateMember(mid, { [key]: value })
      await reload()
      patch({ dirSel: mid })
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  // Playing status is the Stats active/inactive flag, and the Directory filters
  // on it — so it has to be settable here too, or "Former players" is a filter
  // with nothing behind it.
  const setPlayerStatus = async (p, status) => {
    if (!p.player_id) return
    setBusy(true)
    try { await api.bsUpdatePlayerProfile(p.player_id, { status }); await reload() }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  // The expiry is what drives "Quals to renew", so it has to be correctable.
  // add_qualification derives it from the type's validity period, which is
  // right for a fresh certificate and wrong for one obtained years ago.
  const setQualExpiry = async (qid, expires_at) => {
    if (!qid || !sel?.member_id) return
    setBusy(true)
    try { await api.qualUpdateQualification(qid, { expires_at: expires_at || null }); await refreshMember(sel.member_id) }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const seedTypes = async () => {
    setBusy(true)
    try { const r = await api.dirSeedMembershipTypes(); setMemberTypes(r?.membership_types || []) }
    catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
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

  // A name the admin will recognise a week later, built from whatever the
  // filters are actually set to rather than a generic "Directory list".
  const filterName = () => {
    const bits = []
    // A membership-type segment carries its own name, so it reads as the club
    // wrote it ("Senior Player") rather than through a lookup table.
    bits.push(seg === 'All' ? 'Everyone'
      : seg.startsWith(TYPE_PREFIX) ? seg.slice(TYPE_PREFIX.length)
      : seg === 'External' ? 'Not members'
      : ([...ROLE_SEGS, ...HONOUR_SEGS].find(s => s.seg === seg) || {}).label || seg)
    if (playing === 'active') bits.push('playing')
    if (playing === 'inactive') bits.push('former players')
    if (typeFilter === NO_TYPE) bits.push('no type set')
    if (roleFilter) bits.push(roleFilter)
    if (expiringOnly) bits.push('quals to renew')
    if (q) bits.push(`matching “${st.dirQuery.trim()}”`)
    return bits.join(' · ')
  }
  const openMakeList = () => setMkList({ name: filterName(), result: null, error: null })
  const createList = async () => {
    setBusy(true)
    try {
      const r = await api.commsCreateListFromDirectory({
        name: (mkList.name || '').trim(),
        keys: list.filter(hasEmail).map(p => p.key),
      })
      setMkList(m => ({ ...m, result: r, error: null }))
    } catch (e) {
      setMkList(m => ({ ...m, error: e?.detail || e?.message || 'Could not create the list.' }))
    } finally { setBusy(false) }
  }

  const assignedIds = new Set((sel?.roles || []).map(r => r.id))
  const unassignedRoles = roleCatalogue.filter(r => !assignedIds.has(r.id))

  // What each menu button says when something under it is on. The button
  // carries the selection so the menu never has to be opened to read it.
  const segLabel = (s) => s.startsWith(TYPE_PREFIX) ? s.slice(TYPE_PREFIX.length)
    : s === 'External' ? 'Not members' : s === 'Player' ? 'Players' : s
  const membershipLabel = seg !== 'All' ? segLabel(seg) : (typeFilter === NO_TYPE ? 'No type set' : null)
  const roleLabel = roleFilter || (roleSeg ? (ROLE_SEGS.find(r => r.seg === roleSeg) || {}).label : null)
  // "More" holds several unrelated switches, so its button counts rather than
  // naming one and hiding the rest.
  const moreOn = [honourSeg, playing !== 'all' ? playing : null, emailFilter,
    expiringOnly ? 'quals' : null, st.dirShowArchived ? 'arch' : null].filter(Boolean)
  const moreLabel = moreOn.length === 1
    ? (honourSeg || PLAYING_LABEL[playing] || EMAIL_LABEL[emailFilter] || (expiringOnly ? 'Quals to renew' : 'Archived'))
    : moreOn.length ? String(moreOn.length) : null

  // Every filter that is on, each with the one patch that clears it. This is
  // the whole point of moving the options into menus: the controls collapse,
  // the STATE stays on the page.
  const activeFilters = [
    seg !== 'All' && { key: 'seg', label: segLabel(seg), clear: () => patch({ dirSeg: 'All' }) },
    typeFilter === NO_TYPE && { key: 'notype', label: 'No type set', clear: () => patch({ dirType: '' }) },
    roleSeg && { key: 'roleseg', label: (ROLE_SEGS.find(r => r.seg === roleSeg) || {}).label, clear: () => patch({ dirRoleSeg: null }) },
    roleFilter && { key: 'role', label: 'Role: ' + roleFilter, clear: () => patch({ dirRole: null }) },
    honourSeg && { key: 'honour', label: honourSeg + 's', clear: () => patch({ dirHonour: null }) },
    playing !== 'all' && { key: 'playing', label: PLAYING_LABEL[playing], clear: () => patch({ dirPlaying: 'all' }) },
    emailFilter && { key: 'email', label: EMAIL_LABEL[emailFilter], clear: () => patch({ dirEmail: null }) },
    expiringOnly && { key: 'quals', label: 'Quals to renew', clear: () => patch({ dirExpiring: false }) },
    st.dirShowArchived && { key: 'arch', label: 'Including archived', clear: () => patch({ dirShowArchived: false }) },
    q && { key: 'q', label: `“${st.dirQuery.trim()}”`, clear: () => patch({ dirQuery: '' }) },
  ].filter(Boolean)
  const clearFilters = () => patch({
    dirSeg: 'All', dirType: '', dirRoleSeg: null, dirRole: null, dirHonour: null,
    dirPlaying: 'all', dirEmail: null, dirExpiring: false, dirShowArchived: false, dirQuery: '',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Directory</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>
            One record per person · {list.length}{people ? ' of ' + people.length : ''} shown
            {list.length > 0 && emailable < list.length && ` · ${list.length - emailable} with no email`}
          </Caption>
        </div>
        <input placeholder="Search name or role…" value={st.dirQuery || ''} onChange={e => patch({ dirQuery: e.target.value })}
          style={{ flex: 1, minWidth: 180, maxWidth: 300, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none' }} />
        {/* One row: the three axes as menus, then what you can DO, ending in
            the single primary action. Every option that used to be its own pill
            still exists — it lives in the menu for its axis, so the number of
            controls no longer grows with the club's catalogue. Whatever is
            actually filtered is drawn as chips underneath, so hiding the
            options never hides the state. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flex: '1 1 100%' }}>
          <MenuButton label="Membership" value={membershipLabel} width={260}>
            {close => (
              <>
                <MenuItem on={seg === 'All' && !typeFilter} onClick={() => { patch({ dirSeg: 'All', dirType: '' }); close() }}>Everyone</MenuItem>
                <MenuItem on={seg === 'Player'} onClick={() => { patch({ dirSeg: seg === 'Player' ? 'All' : 'Player' }); close() }}>Players</MenuItem>
                {internalTypes.length > 0 && <MenuHeading>MEMBERS</MenuHeading>}
                {internalTypes.map(t => (
                  <MenuItem key={t.id} on={seg === TYPE_PREFIX + t.name}
                    onClick={() => { patch({ dirSeg: seg === TYPE_PREFIX + t.name ? 'All' : TYPE_PREFIX + t.name }); close() }}>{t.name}</MenuItem>
                ))}
                {externalTypes.length > 0 && <MenuHeading>NOT MEMBERS</MenuHeading>}
                {externalTypes.map(t => (
                  <MenuItem key={t.id} on={seg === TYPE_PREFIX + t.name}
                    onClick={() => { patch({ dirSeg: seg === TYPE_PREFIX + t.name ? 'All' : TYPE_PREFIX + t.name }); close() }}>{t.name}</MenuItem>
                ))}
                {externalTypes.length > 0 && (
                  <MenuItem on={seg === 'External'} onClick={() => { patch({ dirSeg: seg === 'External' ? 'All' : 'External' }); close() }}>Anyone who is not a member</MenuItem>
                )}
                <MenuDivider />
                <MenuItem on={typeFilter === NO_TYPE} onClick={() => { patch({ dirType: typeFilter === NO_TYPE ? '' : NO_TYPE }); close() }}>No type set</MenuItem>
                {memberTypes.length === 0 && (
                  <MenuItem onClick={() => { seedTypes(); close() }} disabled={busy}>+ Set up membership types</MenuItem>
                )}
              </>
            )}
          </MenuButton>

          <MenuButton label="Role" value={roleLabel} width={230}>
            {close => (
              <>
                <MenuItem on={!roleSeg && !roleFilter} onClick={() => { patch({ dirRoleSeg: null, dirRole: null }); close() }}>Any role</MenuItem>
                {ROLE_SEGS.map(s => (
                  <MenuItem key={s.seg} on={roleSeg === s.seg}
                    onClick={() => { patch({ dirRoleSeg: roleSeg === s.seg ? null : s.seg }); close() }}>{s.label}</MenuItem>
                ))}
                {roleFilter && (
                  <>
                    <MenuDivider />
                    <MenuItem on onClick={() => { patch({ dirRole: null }); close() }}>{roleFilter}</MenuItem>
                  </>
                )}
              </>
            )}
          </MenuButton>

          <MenuButton label="More" value={moreLabel} width={230}>
            {close => (
              <>
                <MenuHeading>HONOURS</MenuHeading>
                {HONOUR_SEGS.map(s => (
                  <MenuItem key={s.seg} on={honourSeg === s.seg}
                    onClick={() => { patch({ dirHonour: honourSeg === s.seg ? null : s.seg }); close() }}>{s.label}</MenuItem>
                ))}
                {/* Playing status is the Stats active/inactive flag, so a club
                    can tell this season's players from the ones who have
                    stopped without losing either from the directory. */}
                <MenuHeading>PLAYING</MenuHeading>
                <MenuItem on={playing === 'active'} onClick={() => { patch({ dirPlaying: playing === 'active' ? 'all' : 'active' }); close() }}>Playing</MenuItem>
                <MenuItem on={playing === 'inactive'} onClick={() => { patch({ dirPlaying: playing === 'inactive' ? 'all' : 'inactive' }); close() }}>Former players</MenuItem>
                <MenuHeading>CONTACT</MenuHeading>
                <MenuItem on={emailFilter === 'has'} onClick={() => { patch({ dirEmail: emailFilter === 'has' ? null : 'has' }); close() }}>Has email</MenuItem>
                <MenuItem on={emailFilter === 'none'} onClick={() => { patch({ dirEmail: emailFilter === 'none' ? null : 'none' }); close() }}>No email</MenuItem>
                <MenuDivider />
                <MenuItem on={expiringOnly} onClick={() => { patch({ dirExpiring: !expiringOnly }); close() }}>Quals to renew</MenuItem>
                <MenuItem on={!!st.dirShowArchived} onClick={() => { patch({ dirShowArchived: !st.dirShowArchived }); close() }}>Show archived</MenuItem>
              </>
            )}
          </MenuButton>

          {/* Everything that is not a filter. Families, Qualifications and
              Volunteer bulk entry are PAGES, and Import/Create list are
              actions — mixing them in among the filters is what made the row
              read as one undifferentiated wall. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
            <MenuButton label="Manage" width={230} align="right">
              {close => (
                <>
                  <MenuHeading>OPEN</MenuHeading>
                  <MenuItem onClick={() => { close(); navigate('/admin/clubhouse/directory/families') }}>Families</MenuItem>
                  <MenuItem onClick={() => { close(); navigate('/admin/clubhouse/directory/qualifications') }}>Qualifications</MenuItem>
                  <MenuItem onClick={() => { close(); navigate('/admin/clubhouse/directory/volunteers') }}>Volunteer bulk entry</MenuItem>
                  <MenuDivider />
                  <MenuItem disabled={!emailable} onClick={() => { close(); openMakeList() }}>
                    Create a list{emailable ? ` (${emailable})` : ''}
                  </MenuItem>
                  <MenuItem onClick={() => { close(); setImp({ text: '', preview: null, result: null }) }}>Import people from CSV</MenuItem>
                </>
              )}
            </MenuButton>
            <button onClick={openAdd} style={btnP}>+ Add person</button>
          </div>
        </div>

        {/* What is actually filtered, and how to undo it. Drawn only when
            something is on, so an unfiltered Directory carries no extra row. */}
        {activeFilters.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', flex: '1 1 100%' }}>
            {activeFilters.map(f => <FilterChip key={f.key} onClear={f.clear}>{f.label}</FilterChip>)}
            <button onClick={clearFilters} style={{ ...btnS, border: 'none', color: C.faint }}>Clear all</button>
          </div>
        )}
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
                    {typeLabel(p) ? <span style={{ color: C.dim }}>{typeLabel(p)}</span>
                      : <span style={{ color: C.faintest }}>No membership type</span>}
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
                {/* Name and contact are edited here, not behind Edit: the
                    search matches on name and two filters ask about email, so
                    all three have to be settable and clearable on the person. */}
                <div style={{ fontWeight: 700, fontSize: 22, letterSpacing: '-0.01em' }}>
                  <InlineField value={sel.name} placeholder="Name" busy={busy}
                    onSave={v => v && savePersonField(sel, 'full_name', v)} />
                </div>
                <div style={{ fontSize: 12.5, color: C.faint, marginTop: 5, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <InlineField value={sel.email} placeholder="Add an email" busy={busy} type="email"
                    onSave={v => savePersonField(sel, 'email', v)} />
                  <InlineField value={sel.phone} placeholder="Add a mobile" busy={busy}
                    onSave={v => savePersonField(sel, 'mobile', v)} />
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {/* Membership types lead, accented, because they are the
                      club's own answer for this person. Then what the module
                      worked out: roles, honours, playing status. The `type:`
                      segments are already shown as the accented chips, so they
                      are stripped here rather than repeated raw. */}
                  {typeLabel(sel) && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)', color: C.accent }}>{typeLabel(sel)}</span>}
                  {sel.is_external && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.hair2}`, color: C.faint }} title="Recorded by the club, not counted as a member">NOT A MEMBER</span>}
                  {sel.player_status === 'inactive' && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.warn}66`, color: C.warn }}>NOT PLAYING</span>}
                  {sel.segs.filter(s => !s.startsWith(TYPE_PREFIX) && s !== 'External').map(s => <span key={s} style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.dim }}>{s}</span>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {/* Editable whether or not they already have a person row —
                    saving mints one. A read-through player used to have no Edit
                    button at all, which in a stats-first club meant most of the
                    Directory could not be edited. */}
                {!sel.archived && <button onClick={() => openEdit(sel)} style={btnS}>Edit</button>}
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
              {/* AXIS 1 — what kind of member. Several at once, ticked straight
                  on the person; no dialog, because this is the thing most often
                  wrong and a dialog is what stops anyone fixing it. */}
              <section>
                <div style={cap}>MEMBERSHIP</div>
                {memberTypes.length === 0 ? (
                  <div style={{ fontSize: 13, color: C.faint }}>
                    Your club has no membership types yet.
                    <button onClick={seedTypes} disabled={busy} style={{ ...btnS, marginLeft: 8, opacity: busy ? 0.6 : 1 }}>Set up the starter types</button>
                  </div>
                ) : (
                  <>
                    {[['MEMBERS', internalTypes], ['NOT MEMBERS', externalTypes]].map(([heading, opts]) => opts.length === 0 ? null : (
                      <div key={heading} style={{ marginBottom: 10 }}>
                        <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faintest, marginBottom: 5 }}>{heading}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                          {opts.map(t => {
                            const on = (sel.membership_types || []).some(x => x.id === t.id)
                            const primary = sel.membership_type_id === t.id
                            return (
                              <button key={t.id} disabled={busy} onClick={() => toggleType(sel, t.id)}
                                title={on ? (primary ? 'Held, and the type BetterFees bills' : 'Held — click to remove') : 'Click to add'}
                                style={{ ...pill(on), display: 'inline-flex', alignItems: 'center', gap: 5, opacity: busy ? 0.6 : 1 }}>
                                {t.name}
                                {/* aria-hidden, or the glyph joins the button's
                                    accessible name and it reads as "Senior
                                    Player ★". The title carries the meaning. */}
                                {primary && <span aria-hidden="true" style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '0.08em' }}>★</span>}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                    {/* Which one the money hangs off. Only worth asking once
                        they hold more than one, and only answerable for a
                        person who already has a row. */}
                    {(sel.membership_types || []).length > 1 && sel.member_id && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>★ BILLED AS</span>
                        <select value={sel.membership_type_id || ''} disabled={busy} onChange={e => setPrimaryType(sel, e.target.value)}
                          style={{ ...inp, width: 'auto', maxWidth: 200, opacity: busy ? 0.6 : 1 }}>
                          {(sel.membership_types || []).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </select>
                      </div>
                    )}
                    {(sel.membership_types || []).length === 0 && (
                      <div style={{ fontSize: 12.5, color: C.faint, marginTop: 2 }}>
                        No membership type recorded{sel.player_id ? '. They have a record in Stats, so they play — the club still decides whether that is a Senior or a Junior Player.' : '.'}
                      </div>
                    )}
                    {!sel.member_id && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 6 }}>Ticking a type adds this player to the member directory.</div>}
                  </>
                )}

                {/* Playing status. The Directory filters on it, so it is set
                    here rather than only in Stats. Its endpoint wants
                    MANAGE_PLAYERS, which a volunteer or committee manager need
                    not hold — without it the status still reads, it just says
                    where to change it instead of offering a button that 403s. */}
                {sel.player_id && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faintest, marginBottom: 5 }}>PLAYING</div>
                    {canEditPlayers ? (
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                        {[['active', 'Playing'], ['inactive', 'Not playing']].map(([v, label]) => (
                          <button key={v} disabled={busy} onClick={() => setPlayerStatus(sel, v)}
                            style={{ ...pill((sel.player_status || 'active') === v), opacity: busy ? 0.6 : 1 }}>{label}</button>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: 12.5, color: C.faint }}>
                        {sel.player_status === 'inactive' ? 'Not playing' : 'Playing'}
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}> · changed on the player’s record in Stats</span>
                      </div>
                    )}
                  </div>
                )}
              </section>

              {/* AXIS 3 — honours. Sits beside membership because "what are
                  they to the club" is one question; roles are the other. */}
              <section>
                <div style={cap}>HONOURS</div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: busy ? 'default' : 'pointer', fontSize: 13, color: C.dim }}>
                  <input type="checkbox" disabled={busy} checked={!!sel.life_member_flag}
                    onChange={e => setLifeMember(sel, e.target.checked)} />
                  Life member
                </label>
                {sel.life_member_flag && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>SINCE</span>
                    <input type="date" disabled={busy} value={sel.life_member_since || ''}
                      onChange={e => setLifeMember(sel, true, e.target.value)}
                      style={{ ...inp, width: 'auto' }} />
                  </div>
                )}
                {/* The honour board is the ceremonial record and the Awards
                    screen owns it, so this says where the answer came from
                    rather than pretending the tick is the only truth. */}
                {sel.life_member_award && (
                  <div style={{ fontSize: 12.5, color: C.faint, marginTop: 8, lineHeight: 1.5 }}>
                    Life membership is on their honour board, so they read as a life member whether or not this is ticked.
                    Remove it on the Awards screen if that is wrong.
                  </div>
                )}
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 8 }}>
                  An honour, not a membership type — a life member is still whatever kind of member they already were.
                </div>
              </section>

              {/* AXIS 2 — what they do. */}
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
                        {/* The expiry is what "Quals to renew" filters on, so it
                            has to be settable and clearable. Adding a
                            qualification derives it from the type's validity
                            period, which is right for a fresh certificate and
                            wrong for one obtained years ago. */}
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3, display: 'flex', alignItems: 'center', gap: 6 }}>
                          {qq.id ? (
                            <>
                              <input type="date" value={qq.expiry ? String(qq.expiry).slice(0, 10) : ''} disabled={busy}
                                title="Expiry — clear it for a qualification that never expires"
                                onChange={e => setQualExpiry(qq.id, e.target.value)}
                                style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 5, padding: '1px 5px', color: C.dim, fontFamily: MONO, fontSize: 9.5, outline: 'none' }} />
                              {!qq.expiry && <span>never expires</span>}
                            </>
                          ) : fmtExpiry(qq.expiry)}
                        </div>
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
            <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16 }}>{modal.editId ? 'Update this person’s details.' : 'Add a non-playing member or external contact. Players are managed in Stats.'}</div>
            <div style={{ display: 'grid', gap: 11 }}>
              <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>NAME *<input value={modal.form.full_name} onChange={e => setForm('full_name', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 11 }}>
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>EMAIL<input value={modal.form.email} onChange={e => setForm('email', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>MOBILE<input value={modal.form.mobile} onChange={e => setForm('mobile', e.target.value)} style={{ ...inp, marginTop: 4 }} /></label>
              </div>
              {/* The club's own catalogue, several at once. Only offered when
                  they keep one, since nothing seeds it automatically — a club
                  with none can still add the person and type them after. */}
              {memberTypes.length > 0 && (
                <div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginBottom: 5 }}>MEMBERSHIP TYPES</div>
                  {[['MEMBERS', internalTypes], ['NOT MEMBERS', externalTypes]].map(([heading, opts]) => opts.length === 0 ? null : (
                    <div key={heading} style={{ marginBottom: 7 }}>
                      <div style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.1em', color: C.faintest, marginBottom: 4 }}>{heading}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                        {opts.map(t => (
                          <button key={t.id} type="button" onClick={() => toggleModalType(t.id)} style={pill(modal.types.includes(t.id))}>{t.name}</button>
                        ))}
                      </div>
                    </div>
                  ))}
                  <div style={{ fontFamily: MONO, fontSize: 9, color: C.faintest }}>Pick as many as apply. Roles and life membership are recorded on the person after this.</div>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
              <button onClick={() => setModal(null)} style={btnS}>Cancel</button>
              <button onClick={saveMember} disabled={busy || !(modal.form.full_name || '').trim()} style={{ ...btnP, opacity: (busy || !(modal.form.full_name || '').trim()) ? 0.6 : 1 }}>{modal.editId ? 'Save' : 'Add person'}</button>
            </div>
          </div>
        </div>
      )}

      {mkList && (
        <div onClick={() => setMkList(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 'min(460px, 100%)', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}>
            {!mkList.result ? (
              <>
                <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>Create a list</div>
                <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 16 }}>
                  This makes a list in BetterClubhouse → Comms → Lists, under “Auto-generated lists”, so you can use it as an audience on an email.
                </div>
                <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>LIST NAME *
                  <input value={mkList.name} onChange={e => setMkList(m => ({ ...m, name: e.target.value }))} style={{ ...inp, marginTop: 4 }} />
                </label>
                <div style={{ fontSize: 12.5, color: C.faint, marginTop: 14, lineHeight: 1.5 }}>
                  <strong style={{ color: C.text }}>{emailable}</strong> {emailable === 1 ? 'person goes' : 'people go'} on the list.
                  {list.length > emailable && <> The other {list.length - emailable} in this filter have no email address, so they are left off. Use the <strong style={{ color: C.text }}>No email</strong> filter to see who they are.</>}
                  <div style={{ marginTop: 8 }}>Anyone who has unsubscribed or bounced stays suppressed and will not be emailed, even from this list.</div>
                </div>
                {mkList.error && <div style={{ fontSize: 12.5, color: C.block, marginTop: 12 }}>{mkList.error}</div>}
                <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
                  <button onClick={() => setMkList(null)} style={btnS}>Cancel</button>
                  <button onClick={createList} disabled={busy || !(mkList.name || '').trim()} style={{ ...btnP, opacity: (busy || !(mkList.name || '').trim()) ? 0.6 : 1 }}>{busy ? 'Creating…' : 'Create list'}</button>
                </div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>List created</div>
                <div style={{ fontSize: 13, color: C.faint, marginTop: 8, lineHeight: 1.55 }}>
                  <strong style={{ color: C.text }}>{mkList.result.name}</strong> has {mkList.result.count} {mkList.result.count === 1 ? 'contact' : 'contacts'}.
                  {mkList.result.name !== (mkList.name || '').trim() && <> A list of that name already existed, so this one was numbered.</>}
                  <div style={{ marginTop: 8 }}>Find it in Comms → Lists under “Auto-generated lists”.</div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
                  <button onClick={() => setMkList(null)} style={btnS}>Close</button>
                  <Link to="/admin/comms/lists" style={btnP}>Go to Lists</Link>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {imp && (
        <div onClick={() => setImp(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 'min(560px, 100%)', maxHeight: '86vh', overflowY: 'auto', background: C.surface, border: `1px solid ${C.hair2}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>Import people from CSV</div>
            <div style={{ fontSize: 12.5, color: C.faint, marginBottom: 14, lineHeight: 1.5 }}>
              Non-players and external contacts. Columns: <span style={{ fontFamily: MONO, fontSize: 11 }}>name, email, mobile, category, roles</span> (only <span style={{ fontFamily: MONO, fontSize: 11 }}>name</span> required; <span style={{ fontFamily: MONO, fontSize: 11 }}>roles</span> is a comma-separated list of role titles). Matched to existing people by name, so a re-run tops up rather than duplicates. Players are imported in Stats.
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
