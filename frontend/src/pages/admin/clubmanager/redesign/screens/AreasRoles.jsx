import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'
import { AREAS, SHIFT_DEFS, DIRECTORY, POSITIONS, qualState, DOW, fmtHour } from '../model'

// Areas & Roles — the configuration every other screen reads from. Absorbs
// Roles, Activities and Qualification types, and configures the roster.
export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'areas'
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  const depts = []
  Object.keys(AREAS).forEach(k => { if (depts.indexOf(AREAS[k].dept) === -1) depts.push(AREAS[k].dept) })

  const roleUse = {}
  DIRECTORY.forEach(p => p.roles.forEach(r => { roleUse[r] = (roleUse[r] || 0) + 1 }))
  const areaByRole = {}
  Object.keys(AREAS).forEach(k => { (areaByRole[AREAS[k].role] = areaByRole[AREAS[k].role] || []).push(AREAS[k].name) })

  const activityTotals = {}
  DIRECTORY.forEach(p => p.hours.forEach(([a, h]) => { activityTotals[a] = (activityTotals[a] || 0) + h }))
  const activityRows = Object.keys(activityTotals).sort((a, b) => activityTotals[b] - activityTotals[a])
  const maxAct = Math.max(...activityRows.map(a => activityTotals[a]))

  const qualTotals = {}
  DIRECTORY.forEach(p => p.quals.forEach(q => {
    const s = qualState(q.expiry)
    const rec = qualTotals[q.name] = qualTotals[q.name] || { holders: 0, flagged: 0 }
    rec.holders++
    if (s.key !== 'current') rec.flagged++
  }))
  const qualUsedBy = {}
  Object.keys(AREAS).forEach(k => { if (AREAS[k].qual) (qualUsedBy[AREAS[k].qual] = qualUsedBy[AREAS[k].qual] || []).push(AREAS[k].name) })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Areas &amp; Roles</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>THE CONFIGURATION EVERY OTHER SCREEN READS FROM</Caption>
        </div>
        <SegTabs value={tab} onChange={k => patch({ setupTab: k })} tabs={[{ key: 'areas', label: 'Operational areas' }, { key: 'roles', label: 'Roles' }, { key: 'activities', label: 'Activities' }, { key: 'quals', label: 'Qualifications' }]} />
      </ScreenHeader>

      {tab === 'areas' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '68rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 18px', lineHeight: 1.55, maxWidth: '46rem' }}>An operational area is a slice of club work with its own weekly shift pattern, the role that can cover it, and the qualification that gates it. Change a pattern here and next week's roster is generated from it.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
            {depts.map(dept => (
              <div key={dept}>
                <div style={cap}>{dept}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {Object.keys(AREAS).filter(k => AREAS[k].dept === dept).map(k => {
                    const a = AREAS[k]
                    const defs = SHIFT_DEFS.filter(d => d[0] === k)
                    const slots = defs.reduce((acc, d) => acc + d[4], 0)
                    return (
                      <div key={k} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: '13px 15px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span style={{ width: 9, height: 9, borderRadius: 3, background: a.color, flexShrink: 0 }} />
                          <span style={{ fontSize: 14.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{a.name}</span>
                          <span style={{ fontFamily: MONO, fontSize: 10, color: C.dim, flexShrink: 0 }}>{slots} shift{slots === 1 ? '' : 's'} / week</span>
                        </div>
                        <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, margin: '6px 0 9px' }}>{a.qual ? a.role + ' · must hold ' + a.qual : a.role + ' · no qualification required'}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                          {defs.map((d, i) => (
                            <span key={i} style={{ fontFamily: MONO, fontSize: 9.5, padding: '3px 7px', borderRadius: 5, background: `color-mix(in srgb, ${a.color} 12%, transparent)`, border: `1px solid color-mix(in srgb, ${a.color} 35%, transparent)`, color: a.color }}>
                              {DOW[d[1]]} {fmtHour(d[2])}–{fmtHour(d[3])}{d[4] > 1 ? ' ×' + d[4] : ''}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'roles' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: '72rem' }}>
            <div>
              <div style={cap}>GENERAL ROLES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {Object.keys(roleUse).sort().map(r => (
                  <div key={r} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{r}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.dim }}>{roleUse[r]} hold{roleUse[r] === 1 ? 's' : ''} this role</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: areaByRole[r] ? C.accent : C.faintest, marginTop: 4 }}>{areaByRole[r] ? 'Rosters: ' + areaByRole[r].join(', ') : 'Not tied to a roster area'}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div style={cap}>COMMITTEE POSITIONS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {POSITIONS.map((p, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                    <span style={{ fontSize: 13, color: C.text }}>{p.title}</span>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: p.holder ? C.dim : C.warn }}>{p.holder || 'Vacant'}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'activities' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '44rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 16px', lineHeight: 1.55 }}>What logged volunteer hours are spent on. A completed roster shift books its hours straight against one of these once the volunteer taps to confirm.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
            {activityRows.map(a => (
              <div key={a}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                  <span style={{ fontSize: 13, color: C.text }}>{a}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.dim }}>{activityTotals[a]}h logged</span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden', marginTop: 4 }}>
                  <div style={{ height: '100%', width: Math.round((activityTotals[a] / maxAct) * 100) + '%', background: C.accent }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'quals' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '48rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 16px', lineHeight: 1.55 }}>Qualification types and what they gate. A gating qualification blocks rostering outright — an expired RSA is why a bar shift refuses a drop.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.keys(qualTotals).sort().map(q => (
              <div key={q} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{q}</span>
                  <span style={{ fontFamily: MONO, fontSize: 9.5, color: qualTotals[q].flagged ? C.warn : C.faint }}>{qualTotals[q].holders} hold · {qualTotals[q].flagged} to renew</span>
                </div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: qualUsedBy[q] ? C.block : C.faintest, marginTop: 4 }}>{qualUsedBy[q] ? 'Gates rostering for ' + qualUsedBy[q].join(', ') : 'Recorded only — gates nothing'}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
