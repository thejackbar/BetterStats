import { C, MONO, Caption, ScreenHeader, NavToggle, initials } from '../ui'
import { DIRECTORY, DIR_SEGS, qualState, diaryModel, DIARY_TASKS, DIARY_TONE, fmtDate } from '../model'

// Directory — one record per person. Absorbs Volunteers, Families,
// Qualifications and the hours half of Activities. No page navigation between
// people; the list column selects and the detail pane scrolls.
export default function Directory({ st, patch, narrow }) {
  const q = (st.dirQuery || '').toLowerCase()
  const seg = st.dirSeg || 'All'
  const roleFilter = st.dirRole || null
  const expiringOnly = !!st.dirExpiring

  const enriched = DIRECTORY.map(p => {
    const quals = p.quals.map(qq => ({ ...qq, st: qualState(qq.expiry) }))
    const flagged = quals.filter(x => x.st.key !== 'current')
    return { ...p, quals, flagged, totalHours: p.hours.reduce((a, h) => a + h[1], 0) }
  })

  const list = enriched.filter(p => {
    if (seg !== 'All' && !p.segs.includes(seg)) return false
    if (roleFilter && !p.roles.includes(roleFilter) && (!p.position || p.position.title !== roleFilter)) return false
    if (expiringOnly && !p.flagged.length) return false
    if (q && !(p.name.toLowerCase().includes(q) || p.roles.join(' ').toLowerCase().includes(q)
      || (p.position && p.position.title.toLowerCase().includes(q)))) return false
    return true
  })

  const selId = st.dirSel && enriched.some(p => p.id === st.dirSel) ? st.dirSel : (list[0] ? list[0].id : null)
  const sel = enriched.find(p => p.id === selId) || null

  const shiftCount = sel ? st.slots.filter(x => x.assignee === sel.id).length : 0
  const selTasks = sel ? DIARY_TASKS.filter(t => t.person === sel.name) : []
  const { rById } = diaryModel()

  const pill = (active, tone = 'accent') => {
    const map = {
      accent: 'rgba(99,102,241,0.45); background: rgba(99,102,241,0.12); color: #6366F1',
      amber: 'rgba(245,181,66,0.45); background: rgba(245,181,66,0.12); color: #f5b542',
    }
    return {
      padding: '5px 11px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
      border: active ? `1px solid ${map[tone].split(';')[0]}` : `1px solid ${C.hair2}`,
      background: active ? map[tone].match(/background: ([^;]+)/)[1] : 'transparent',
      color: active ? map[tone].match(/color: (#\w+)/)[1] : C.dim,
    }
  }

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Directory</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>One record per person · {list.length} of {DIRECTORY.length} shown</Caption>
        </div>
        <input placeholder="Search name, role or position…" value={st.dirQuery || ''} onChange={e => patch({ dirQuery: e.target.value })}
          style={{ flex: 1, minWidth: 200, maxWidth: 340, background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {DIR_SEGS.map(s => (
            <button key={s} onClick={() => patch({ dirSeg: s })} style={pill(seg === s)}>{s === 'All' ? 'Everyone' : s + 's'}</button>
          ))}
          <button onClick={() => patch({ dirExpiring: !expiringOnly })} style={pill(expiringOnly, 'amber')}>Quals to renew</button>
          {roleFilter && (
            <button onClick={() => patch({ dirRole: null })} style={{ ...pill(true), display: 'inline-flex', alignItems: 'center', gap: 6 }}>Role: {roleFilter}  ✕</button>
          )}
        </div>
      </ScreenHeader>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div className="pb-scroll" style={{ width: 300, flex: '0 0 300px', borderRight: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {list.map(p => (
              <div key={p.id} onClick={() => patch({ dirSel: p.id })}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 8, cursor: 'pointer', border: p.id === selId ? '1px solid rgba(99,102,241,0.4)' : '1px solid transparent', background: p.id === selId ? 'rgba(99,102,241,0.08)' : 'transparent' }}>
                <span style={avatar(30)}>{initials(p.name)}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.position ? p.position.title : (p.roles.join(' · ') || 'Member')}</div>
                </div>
                {p.flagged.length > 0 && <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.warn, flexShrink: 0 }} />}
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0 }}>{p.totalHours}h</span>
              </div>
            ))}
            {list.length === 0 && <div style={{ padding: '20px 12px', fontSize: 13, color: C.faint }}>Nobody matches those filters.</div>}
          </div>
        </div>

        {sel && (
          <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
              <span style={avatar(52, 16)}>{initials(sel.name)}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 22, letterSpacing: '-0.01em' }}>{sel.name}</div>
                <div style={{ fontSize: 12.5, color: C.faint, marginTop: 3 }}>{sel.email}  ·  {sel.phone}  ·  member since {sel.since}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {sel.segs.map(s => <span key={s} style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '3px 7px', borderRadius: 4, background: C.surface2, border: `1px solid ${C.hair2}`, color: C.dim }}>{s}</span>)}
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 22 }}>
              {[
                { value: sel.totalHours + 'h', label: 'HOURS THIS SEASON' },
                { value: String(shiftCount), label: 'SHIFTS THIS WEEK' },
                { value: String(selTasks.length), label: 'DIARY TASKS' },
                { value: String(sel.flagged.length), label: 'QUALS TO RENEW' },
              ].map((s, i) => (
                <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                  <div style={{ fontWeight: 700, fontSize: 19, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 3 }}>{s.label}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px' }}>
              <section>
                <div style={cap}>COMMITTEE POSITION</div>
                {sel.position ? (
                  <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{sel.position.title}</div>
                    <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginTop: 3 }}>{sel.position.term}</div>
                  </div>
                ) : <div style={{ fontSize: 13, color: C.faint }}>Not on the committee.</div>}
              </section>

              <section>
                <div style={cap}>ROLES</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {sel.roles.map(r => (
                    <span key={r} onClick={() => patch({ dirRole: r, dirSeg: 'All' })} style={{ background: 'rgba(99,102,241,0.15)', color: C.accent, borderRadius: 5, padding: '3px 9px', fontSize: 12.5, cursor: 'pointer' }}>{r}</span>
                  ))}
                </div>
                {sel.roles.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No general roles.</div>}
                {sel.interested.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                    {sel.interested.map(r => <span key={r} style={{ border: `1px dashed ${C.faintest}`, color: C.dim, borderRadius: 5, padding: '3px 9px', fontSize: 12.5 }}>{r} · interested</span>)}
                  </div>
                )}
              </section>

              <section>
                <div style={cap}>QUALIFICATIONS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {sel.quals.map((qq, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '8px 11px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text }}>{qq.name}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>expires {fmtDate(qq.expiry)}</div>
                      </div>
                      <span style={statusChip(qq.st.fg)}>{qq.st.label}</span>
                    </div>
                  ))}
                  {sel.quals.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>None recorded.</div>}
                </div>
              </section>

              <section>
                <div style={cap}>HOURS BY ACTIVITY</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sel.hours.map(([activity, h], i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{ fontSize: 12.5, color: C.dim }}>{activity}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: C.text }}>{h}h</span>
                      </div>
                      <div style={barTrack}><div style={{ height: '100%', width: Math.round((h / Math.max(...sel.hours.map(x => x[1]))) * 100) + '%', background: C.accent }} /></div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div style={cap}>DIARY TASKS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {selTasks.map(t => {
                    const r = rById[t.id]
                    const tone = DIARY_TONE[r.status]
                    return (
                      <div key={t.id} onClick={() => patch({ task: t.id })} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '8px 11px', cursor: 'pointer' }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 13, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.title}</div>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{r.rule ? r.rule : 'due ' + fmtDate(t.due)}</div>
                        </div>
                        <span style={statusChip(tone.fg)}>{tone.label}</span>
                      </div>
                    )
                  })}
                  {selTasks.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No diary tasks assigned.</div>}
                </div>
              </section>

              <section>
                <div style={cap}>{sel.family} family</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {DIRECTORY.filter(x => x.family === sel.family && x.id !== sel.id).map(x => (
                    <div key={x.id} onClick={() => patch({ dirSel: x.id })} style={{ display: 'flex', alignItems: 'center', gap: 9, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 7, padding: '8px 11px', cursor: 'pointer' }}>
                      <span style={avatar(26, 9.5)}>{initials(x.name)}</span>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text }}>{x.name}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{x.segs.join(' · ')}</div>
                      </div>
                      <span style={{ color: C.faintest, fontSize: 13 }}>→</span>
                    </div>
                  ))}
                  {!DIRECTORY.some(x => x.family === sel.family && x.id !== sel.id) && <div style={{ fontSize: 13, color: C.faint }}>No linked family members.</div>}
                </div>
              </section>
            </div>

            <div style={{ marginTop: 24, borderTop: `1px solid ${C.hair}`, paddingTop: 16 }}>
              <button onClick={() => patch({ screen: 'roster', person: null, navOpen: false })} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Open this week's roster →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const avatar = (size, fs = 10) => ({ width: size, height: size, borderRadius: '50%', background: 'var(--pb-surface)', border: `1.5px solid var(--pb-hairline2)`, color: 'var(--pb-dim)', fontFamily: MONO, fontSize: fs, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 })
const statusChip = (fg) => ({ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 7px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg, flexShrink: 0 })
const barTrack = { height: 4, borderRadius: 2, background: 'var(--pb-surface2)', overflow: 'hidden', marginTop: 4 }
