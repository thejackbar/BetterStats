import { C, MONO, Drawer, initials } from '../ui'
import { personById, AREAS, DOW, QUAL_STATUS, PEOPLE, fmtHour } from '../model'

// The roster person record drawer (opened from a person row in the Roster).
export default function PersonDrawer({ personId, slots, opts, onClose }) {
  const pp = personById(personId)
  if (!pp) return null
  const pShifts = slots.filter(x => x.assignee === pp.id)
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }
  const qualMap = { ok: ['CURRENT', C.ok], soon: ['EXPIRES SOON', C.warn], expired: ['EXPIRED', C.block] }

  const stats = [
    { value: pShifts.length, label: 'SHIFTS THIS WK' },
    { value: pp.hoursYtd + 'h', label: 'HOURS YTD' },
    { value: opts.weeklyShiftCap || pp.max, label: 'WEEKLY CAP' },
  ]

  return (
    <Drawer width={460} zIndex={60} onClose={onClose}>
      <div style={{ padding: 20, borderBottom: `1px solid ${C.hair}`, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ width: 44, height: 44, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(pp.name)}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{pp.name}</div>
          <div style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint, marginTop: 2 }}>{pp.roles.join(' · ') || 'No roles set'}</div>
        </div>
        <span style={{ cursor: 'pointer', color: C.faint, fontSize: 16 }} onClick={onClose}>✕</span>
      </div>
      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
          {stats.map((s, i) => (
            <div key={i} style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 12px' }}>
              <div style={{ fontWeight: 700, fontSize: 18, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faint, marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={cap}>ROLES</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {(pp.roles.length ? pp.roles : ['No roles set']).map(r => (
              <span key={r} style={{ background: 'rgba(99,102,241,0.15)', color: C.accent, borderRadius: 5, padding: '3px 8px', fontSize: 12 }}>{r}</span>
            ))}
          </div>
        </div>

        {pp.quals.length > 0 && (
          <div>
            <div style={cap}>QUALIFICATIONS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {pp.quals.map(q => {
                const [label, fg] = qualMap[QUAL_STATUS[q] || 'ok']
                return (
                  <div key={q} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px' }}>
                    <span style={{ fontSize: 13 }}>{q}</span>
                    <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg }}>{label}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div>
          <div style={cap}>THIS WEEK'S SHIFTS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {pShifts.map(x => (
              <div key={x.id} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: AREAS[x.area].color }} />
                <span style={{ fontSize: 13, flex: 1 }}>{AREAS[x.area].name}</span>
                <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.dim }}>{DOW[x.day]} {fmtHour(x.start)}–{fmtHour(x.end)}</span>
              </div>
            ))}
            {pShifts.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Not rostered this week.</div>}
          </div>
        </div>

        <div>
          <div style={cap}>AVAILABILITY</div>
          <div style={{ display: 'flex', gap: 5 }}>
            {DOW.map((d, i) => (
              <span key={i} style={{ fontFamily: MONO, fontSize: 10, padding: '4px 7px', borderRadius: 5, ...(pp.days.includes(i) ? { background: C.surface2, border: `1px solid ${C.hair}`, color: C.text } : { border: `1px dashed ${C.faintest}`, color: C.faintest }) }}>{d}</span>
            ))}
          </div>
        </div>

        <div>
          <div style={cap}>FAMILY</div>
          <div style={{ fontSize: 13, color: C.dim }}>{PEOPLE.filter(x => x.family === pp.family && x.id !== pp.id).map(x => x.name).join(', ') || 'No linked family members'}</div>
        </div>
      </div>
    </Drawer>
  )
}
