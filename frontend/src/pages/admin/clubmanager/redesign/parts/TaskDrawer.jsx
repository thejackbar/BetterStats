import { C, MONO, Drawer } from '../ui'
import { diaryModel, DIARY_TONE, fmtDate, money } from '../model'

// The diary task drawer — facts, budget, depends-on / holds-up chains (each
// clickable through to the other task) and the template provenance line.
export default function TaskDrawer({ taskId, patch, onClose }) {
  const { rById, cpSet, dependents } = diaryModel()
  const sel = rById[taskId]
  if (!sel) return null
  const tone = DIARY_TONE[sel.status]
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }

  const facts = [
    { label: 'CADENCE', value: sel.cadence },
    { label: 'ROLE', value: sel.role },
    { label: 'ASSIGNED', value: sel.person },
    { label: sel.rule ? 'RULE' : 'WINDOW', value: sel.rule || (fmtDate(sel.start) + ' → ' + fmtDate(sel.due)) },
  ]
  const chip = (t) => ({ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${DIARY_TONE[t.status].fg}66`, color: DIARY_TONE[t.status].fg, flexShrink: 0 })

  const upstream = sel.deps.map(id => rById[id])
  const downstream = (dependents[sel.id] || []).map(id => rById[id])

  return (
    <Drawer width={440} zIndex={90} onClose={onClose}>
      <div style={{ padding: 20, borderBottom: `1px solid ${C.hair}` }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 17, lineHeight: 1.3 }}>{sel.title}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${tone.fg}66`, color: tone.fg }}>{tone.label}</span>
              {cpSet[sel.id] && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, background: 'rgba(239,91,91,0.15)', color: C.block }}>ON CRITICAL PATH</span>}
            </div>
          </div>
          <span style={{ cursor: 'pointer', color: C.faint, fontSize: 16 }} onClick={onClose}>✕</span>
        </div>
      </div>
      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {facts.map((f, i) => (
            <div key={i} style={{ background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '9px 11px' }}>
              <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint }}>{f.label}</div>
              <div style={{ fontSize: 13, color: C.text, marginTop: 3, lineHeight: 1.4 }}>{f.value}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={cap}>BUDGET</div>
          <div style={{ fontSize: 13, color: C.text }}>{sel.budget ? money(sel.spent) + ' of ' + money(sel.budget) : 'No budget set'}</div>
          {sel.budget > 0 && (
            <div style={{ height: 5, borderRadius: 3, background: C.surface2, overflow: 'hidden', marginTop: 6 }}>
              <div style={{ height: '100%', width: Math.min(100, (sel.spent / sel.budget) * 100) + '%', background: sel.spent > sel.budget ? C.block : C.ok }} />
            </div>
          )}
        </div>

        <div>
          <div style={cap}>DEPENDS ON</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {upstream.map(u => (
              <div key={u.id} onClick={() => patch({ task: u.id })} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer' }}>
                <span style={{ fontSize: 12.5, flex: 1, minWidth: 0 }}>{u.title}</span>
                <span style={chip(u)}>{DIARY_TONE[u.status].label}</span>
              </div>
            ))}
            {upstream.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing — this one can start any time.</div>}
          </div>
        </div>

        <div>
          <div style={cap}>HOLDS UP</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {downstream.map(d => (
              <div key={d.id} onClick={() => patch({ task: d.id })} style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer' }}>
                <span style={{ fontSize: 12.5, flex: 1, minWidth: 0 }}>{d.title}</span>
                <span style={chip(d)}>{DIARY_TONE[d.status].label}</span>
              </div>
            ))}
            {downstream.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing downstream.</div>}
          </div>
        </div>

        <div style={{ borderTop: `1px solid ${C.hair}`, paddingTop: 14, fontSize: 12, color: C.faint, lineHeight: 1.5 }}>
          Generated from the {sel.cadence.toLowerCase()} template · {sel.role} substituted for {sel.person} this season.
        </div>
      </div>
    </Drawer>
  )
}
