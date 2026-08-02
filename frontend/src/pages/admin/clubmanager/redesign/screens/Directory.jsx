import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, initials } from '../ui'

// Directory — one record per person, on REAL club data. The person spine is
// fee_members (the club's member list; a member's player_id links to a stats
// player where one exists, and is NULL for a non-player — a committee member,
// life member, canteen parent, etc.). We union that with the club's players so
// every player still appears, then enrich with volunteer roles/hours and
// expiring qualifications. Committee position and family cross-links land with
// those screens; per-person quals and hours-by-activity load lazily on select.

const DIR_SEGS = ['All', 'Committee', 'Volunteer', 'Parent', 'Player']

// Real "today" qualification status (the fixtures used a fixed season day).
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
const roleName = (r) => typeof r === 'string' ? r : (r?.name || r?.role_name || r?.label || '')

export default function Directory({ st, patch, narrow }) {
  const [people, setPeople] = useState(null)   // null = loading
  const [err, setErr] = useState(null)
  // lazily-loaded per-person detail, keyed by member_id
  const [detail, setDetail] = useState({})     // { [memberId]: { quals, hours } }

  useEffect(() => {
    let alive = true
    Promise.all([
      api.feeAllMembers().catch(() => ({ members: [] })),
      api.adminListPlayers().catch(() => []),
      api.volunteerDirectory().catch(() => ({ volunteers: [] })),
      api.qualExpiringReport(3650).catch(() => []),
    ]).then(([membersRes, playersRes, volRes, expRes]) => {
      if (!alive) return
      const members = (membersRes?.members || membersRes || [])
      const players = Array.isArray(playersRes) ? playersRes : (playersRes?.players || [])
      const vols = (volRes?.volunteers || volRes || [])
      const expRows = Array.isArray(expRes) ? expRes : (expRes?.expiring || expRes?.items || [])

      const playerById = {}
      players.forEach(p => { playerById[p.id] = p })
      const volByMember = {}
      vols.forEach(v => { if (v.member_id) volByMember[v.member_id] = v })
      // expiring-qual count per member (guarded — the report's member key varies)
      const expByMember = {}
      expRows.forEach(r => {
        const mid = r.member_id || r.fee_member_id || r.memberId
        if (mid) expByMember[mid] = (expByMember[mid] || 0) + 1
      })

      const seenPlayer = new Set()
      const list = members.map(m => {
        if (m.player_id) seenPlayer.add(m.player_id)
        const player = m.player_id ? playerById[m.player_id] : null
        const vol = volByMember[m.member_id]
        const roles = (vol?.roles || []).map(roleName).filter(Boolean)
        const segs = []
        if (m.player_id) segs.push('Player')
        if (vol) segs.push('Volunteer')
        return {
          key: m.member_id, memberId: m.member_id, playerId: m.player_id || null,
          name: m.full_name, email: m.email || '', phone: m.mobile || '',
          photo: player?.photo_url || null,
          roles, interested: (vol?.roles_interested || []).map(roleName).filter(Boolean),
          totalHours: Number(vol?.total_hours || 0),
          flagged: expByMember[m.member_id] || 0,
          segs,
        }
      })
      // players with no member row still appear as people
      players.forEach(p => {
        if (seenPlayer.has(p.id)) return
        list.push({
          key: 'player:' + p.id, memberId: null, playerId: p.id,
          name: p.display_name || p.name, email: '', phone: '',
          photo: p.photo_url || null, roles: [], interested: [], totalHours: 0, flagged: 0,
          segs: ['Player'],
        })
      })
      list.sort((a, b) => a.name.localeCompare(b.name))
      setPeople(list)
    }).catch(e => { if (alive) setErr(String(e?.message || e)) })
    return () => { alive = false }
  }, [])

  const q = (st.dirQuery || '').toLowerCase()
  const seg = st.dirSeg || 'All'
  const roleFilter = st.dirRole || null
  const expiringOnly = !!st.dirExpiring

  const list = (people || []).filter(p => {
    if (seg !== 'All' && !p.segs.includes(seg)) return false
    if (roleFilter && !p.roles.includes(roleFilter)) return false
    if (expiringOnly && !p.flagged) return false
    if (q && !(p.name.toLowerCase().includes(q) || p.roles.join(' ').toLowerCase().includes(q))) return false
    return true
  })

  const selId = st.dirSel && (people || []).some(p => p.key === st.dirSel) ? st.dirSel : (list[0] ? list[0].key : null)
  const sel = (people || []).find(p => p.key === selId) || null

  // lazily load the selected person's quals + hours-by-activity
  useEffect(() => {
    if (!sel || !sel.memberId || detail[sel.memberId]) return
    let alive = true
    Promise.all([
      api.qualListMemberQualifications(sel.memberId).catch(() => []),
      api.volunteerListHours(sel.memberId).catch(() => []),
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
      setDetail(d => ({ ...d, [sel.memberId]: { quals, hours } }))
    })
    return () => { alive = false }
  }, [sel?.memberId]) // eslint-disable-line react-hooks/exhaustive-deps

  const det = sel && sel.memberId ? detail[sel.memberId] : null
  const quals = (det?.quals || []).map(qq => ({ ...qq, st: qualStatus(qq.expiry) }))
  const hours = det?.hours || []

  const pill = (active, tone = 'accent') => {
    const on = { accent: ['rgba(99,102,241,0.45)', 'rgba(99,102,241,0.12)', C.accent], amber: ['rgba(245,181,66,0.45)', 'rgba(245,181,66,0.12)', C.warn] }[tone]
    return { padding: '5px 11px', borderRadius: 999, fontSize: 12, cursor: 'pointer', border: `1px solid ${active ? on[0] : C.hair2}`, background: active ? on[1] : 'transparent', color: active ? on[2] : C.dim }
  }
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const avatar = (size, fs = 10) => ({ width: size, height: size, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: fs, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, overflow: 'hidden' })
  const Avatar = ({ p, size, fs }) => p?.photo
    ? <img src={p.photo} alt="" style={{ ...avatar(size, fs), objectFit: 'cover' }} />
    : <span style={avatar(size, fs)}>{initials(p.name)}</span>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Directory</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>One record per person · {list.length}{people ? ' of ' + people.length : ''} shown</Caption>
        </div>
        <input placeholder="Search name or role…" value={st.dirQuery || ''} onChange={e => patch({ dirQuery: e.target.value })}
          style={{ flex: 1, minWidth: 200, maxWidth: 340, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {DIR_SEGS.map(s => <button key={s} onClick={() => patch({ dirSeg: s })} style={pill(seg === s)}>{s === 'All' ? 'Everyone' : s + 's'}</button>)}
          <button onClick={() => patch({ dirExpiring: !expiringOnly })} style={pill(expiringOnly, 'amber')}>Quals to renew</button>
          {roleFilter && <button onClick={() => patch({ dirRole: null })} style={{ ...pill(true), display: 'inline-flex', alignItems: 'center', gap: 6 }}>Role: {roleFilter}  ✕</button>}
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
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.roles.join(' · ') || (p.playerId ? 'Player' : 'Member')}</div>
                </div>
                {p.flagged > 0 && <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.warn, flexShrink: 0 }} />}
                {p.totalHours > 0 && <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0 }}>{p.totalHours}h</span>}
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
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 22 }}>
              {[
                { value: sel.totalHours + 'h', label: 'HOURS THIS SEASON' },
                { value: '—', label: 'SHIFTS THIS WEEK' },
                { value: '—', label: 'DIARY TASKS' },
                { value: String(sel.flagged), label: 'QUALS TO RENEW' },
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
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {sel.roles.map(r => <span key={r} onClick={() => patch({ dirRole: r, dirSeg: 'All' })} style={{ background: 'rgba(99,102,241,0.15)', color: C.accent, borderRadius: 5, padding: '3px 9px', fontSize: 12.5, cursor: 'pointer' }}>{r}</span>)}
                </div>
                {sel.roles.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No club roles assigned.</div>}
                {sel.interested.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                    {sel.interested.map(r => <span key={r} style={{ border: `1px dashed ${C.faintest}`, color: C.dim, borderRadius: 5, padding: '3px 9px', fontSize: 12.5 }}>{r} · interested</span>)}
                  </div>
                )}
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
                  {sel.memberId && !det && <div style={{ fontSize: 13, color: C.faint }}>Loading…</div>}
                  {det && quals.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>None recorded.</div>}
                  {!sel.memberId && <div style={{ fontSize: 13, color: C.faint }}>Not a member record — add them to track qualifications.</div>}
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
                <div style={{ fontSize: 13, color: C.faint, lineHeight: 1.5 }}>Committee position and linked family show here once those screens are wired to live data.</div>
              </section>
            </div>

            <div style={{ marginTop: 24, borderTop: `1px solid ${C.hair}`, paddingTop: 16 }}>
              <button onClick={() => patch({ screen: 'roster', navOpen: false })} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Open this week's roster →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
