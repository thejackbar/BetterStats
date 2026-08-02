import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, initials } from '../ui'

// Directory — one record per person, on REAL club data. The person spine is
// fee_members (a member's player_id links to a stats player where one exists,
// and is NULL for a non-player: committee member, life member, canteen parent,
// third party…). Players belong to Stats/Core and appear read-through; a
// player gets a member row lazily the first time ClubManager assigns them a
// role. ClubManager owns adding/editing non-player people and their roles here.

const DIR_SEGS = ['All', 'Player', 'Volunteer', 'Committee', 'Parent', 'Third party']
const CATS = [
  { value: 'volunteer', label: 'Volunteer' },
  { value: 'parent', label: 'Parent' },
  { value: 'committee', label: 'Committee' },
  { value: 'third_party', label: 'Third party' },
  { value: 'official', label: 'Official (umpire, scorer…)' },
  { value: 'life_member', label: 'Life member' },
  { value: 'other', label: 'Other' },
]

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
  const [err, setErr] = useState(null)
  const [roleCatalogue, setRoleCatalogue] = useState([])   // general (non-committee) club roles
  const [detail, setDetail] = useState({})     // { [memberId]: { quals, hours } }
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState(null)     // null | { editId, form }

  const reload = () => api.dirPeople().then(res => setPeople(res?.people || [])).catch(e => setErr(String(e?.message || e)))
  useEffect(() => {
    reload()
    api.raRoles().then(r => setRoleCatalogue((r?.roles || r || []).filter(x => !x.is_committee))).catch(() => {})
  }, [])

  const q = (st.dirQuery || '').toLowerCase()
  const seg = st.dirSeg || 'All'
  const roleFilter = st.dirRole || null
  const expiringOnly = !!st.dirExpiring

  const roleTitles = (p) => (p.roles || []).map(r => r.title)
  const list = (people || []).filter(p => {
    if (seg !== 'All' && !p.segs.includes(seg)) return false
    if (roleFilter && !roleTitles(p).includes(roleFilter)) return false
    if (expiringOnly && !p.flagged) return false
    if (q && !(p.name.toLowerCase().includes(q) || roleTitles(p).join(' ').toLowerCase().includes(q))) return false
    return true
  })

  const selId = st.dirSel && (people || []).some(p => p.key === st.dirSel) ? st.dirSel : (list[0] ? list[0].key : null)
  const sel = (people || []).find(p => p.key === selId) || null

  useEffect(() => {
    if (!sel || !sel.member_id || detail[sel.member_id]) return
    let alive = true
    Promise.all([
      api.qualListMemberQualifications(sel.member_id).catch(() => []),
      api.volunteerListHours(sel.member_id).catch(() => []),
    ]).then(([qRes, hRes]) => {
      if (!alive) return
      const quals = (Array.isArray(qRes) ? qRes : (qRes?.qualifications || qRes?.items || [])).map(x => ({
        name: x.type_name || x.name || x.qualification_name || 'Qualification',
        expiry: x.expires_at || x.expiry || null,
      }))
      const byAct = {}
      ;(Array.isArray(hRes) ? hRes : (hRes?.hours || [])).forEach(h => {
        const a = h.activity || h.activity_name || h.activity_type || 'Other'
        byAct[a] = (byAct[a] || 0) + Number(h.hours || 0)
      })
      const hours = Object.entries(byAct).sort((a, b) => b[1] - a[1])
      setDetail(d => ({ ...d, [sel.member_id]: { quals, hours } }))
    })
    return () => { alive = false }
  }, [sel?.member_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const det = sel && sel.member_id ? detail[sel.member_id] : null
  const quals = (det?.quals || []).map(qq => ({ ...qq, st: qualStatus(qq.expiry) }))
  const hours = det?.hours || []

  // ── mutations ──────────────────────────────────────────────────────────────
  const openAdd = () => setModal({ editId: null, form: { full_name: '', email: '', mobile: '', member_category: 'volunteer', notes: '' } })
  const openEdit = (p) => setModal({ editId: p.member_id, form: { full_name: p.name, email: p.email, mobile: p.phone, member_category: p.category || 'other', notes: '' } })
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
  const removeRole = async (p, roleId) => {
    if (!p.member_id) return
    setBusy(true); try { await api.dirRemoveRole(p.member_id, roleId); await reload() } finally { setBusy(false) }
  }

  const pill = (active, tone = 'accent') => {
    const on = { accent: ['rgba(99,102,241,0.45)', 'rgba(99,102,241,0.12)', C.accent], amber: ['rgba(245,181,66,0.45)', 'rgba(245,181,66,0.12)', C.warn] }[tone]
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
          {DIR_SEGS.map(s => <button key={s} onClick={() => patch({ dirSeg: s })} style={pill(seg === s)}>{s === 'All' ? 'Everyone' : (s === 'Third party' ? 'Third parties' : s + 's')}</button>)}
          <button onClick={() => patch({ dirExpiring: !expiringOnly })} style={pill(expiringOnly, 'amber')}>Quals to renew</button>
          {roleFilter && <button onClick={() => patch({ dirRole: null })} style={{ ...pill(true), display: 'inline-flex', alignItems: 'center', gap: 6 }}>Role: {roleFilter}  ✕</button>}
          <button onClick={openAdd} style={btnP}>+ Add person</button>
        </div>
      </ScreenHeader>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div className="pb-scroll" style={{ width: 300, flex: '0 0 300px', borderRight: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 10 }}>
          {people === null && <div style={{ padding: '20px 12px', fontSize: 13, color: C.faint }}>{err ? 'Could not load the directory.' : 'Loading your club…'}</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {list.map(p => (
              <div key={p.key} onClick={() => patch({ dirSel: p.key })}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 8, cursor: 'pointer', border: p.key === selId ? '1px solid rgba(99,102,241,0.4)' : '1px solid transparent', background: p.key === selId ? 'rgba(99,102,241,0.08)' : 'transparent' }}>
                <Avatar p={p} size={30} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{roleTitles(p).join(' · ') || (p.segs[0] || 'Member')}</div>
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
                  {sel.segs.map(s => <span key={s} style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.dim }}>{s}</span>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {sel.member_id && <button onClick={() => openEdit(sel)} style={btnS}>Edit</button>}
                {sel.member_id && <button onClick={() => archive(sel)} style={{ ...btnS, color: C.faint }}>Archive</button>}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 22 }}>
              {[
                { value: (sel.total_hours || 0) + 'h', label: 'HOURS THIS SEASON' },
                { value: '—', label: 'SHIFTS THIS WEEK' },
                { value: '—', label: 'DIARY TASKS' },
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
                    <span key={r.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,0.15)', color: C.accent, borderRadius: 5, padding: '3px 6px 3px 9px', fontSize: 12.5 }}>
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
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '8px 11px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text }}>{qq.name}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{fmtExpiry(qq.expiry)}</div>
                      </div>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 7px', borderRadius: 4, border: `1px solid ${qq.st.fg}66`, color: qq.st.fg, flexShrink: 0 }}>{qq.st.label}</span>
                    </div>
                  ))}
                  {sel.member_id && !det && <div style={{ fontSize: 13, color: C.faint }}>Loading…</div>}
                  {det && quals.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>None recorded. Assigning qualifications lands next.</div>}
                  {!sel.member_id && <div style={{ fontSize: 13, color: C.faint }}>Assign a role first to start tracking qualifications.</div>}
                </div>
              </section>

              <section>
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
              </section>

              <section>
                <div style={cap}>COMMITTEE &amp; FAMILY</div>
                <div style={{ fontSize: 13, color: C.faint, lineHeight: 1.5 }}>
                  {sel.segs.includes('Committee') ? 'Holds a committee position. ' : ''}Committee-position and family assignment land in the next update.
                </div>
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
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
              <button onClick={() => setModal(null)} style={btnS}>Cancel</button>
              <button onClick={saveMember} disabled={busy || !(modal.form.full_name || '').trim()} style={{ ...btnP, opacity: (busy || !(modal.form.full_name || '').trim()) ? 0.6 : 1 }}>{modal.editId ? 'Save' : 'Add person'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
