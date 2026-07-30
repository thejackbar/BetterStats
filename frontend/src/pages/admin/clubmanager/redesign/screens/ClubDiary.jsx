import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout, Toast } from '../ui'
import {
  diaryModel, MONTH_DEFS, SEASON_DAYS, TODAY_DAY, CADENCES, DIARY_TONE,
  DIARY_TEMPLATES, ROLE_HOLDERS, fmtDate, money,
} from '../model'

// Club Diary — a template library that generates a dated season plan, tracked by
// due date, budget, blockage and critical path. Blocked/overdue state and the
// critical path are all derived on read.
export default function ClubDiary({ st, patch, narrow }) {
  const tab = st.diaryTab || 'plan'
  const cadFilter = st.cadFilter || 'All'
  const issuesOnly = !!st.issuesOnly
  const collapsed = st.diaryCollapsed || {}
  const { resolved, rById, cpSet, cpPath, cpLen, dependents } = diaryModel()

  // Month headers are day-proportional; the track gridlines are built from the
  // same cumulative day offsets so they never drift from the real boundaries.
  let totalDays = 0
  const gridStops = []
  const months = MONTH_DEFS.map(([label, days]) => {
    totalDays += days
    const pct = (totalDays / SEASON_DAYS) * 100
    gridStops.push(`transparent calc(${pct}% - 1px), ${C.surface2} calc(${pct}% - 1px), ${C.surface2} ${pct}%`)
    return { label, days }
  })
  const trackGrid = `linear-gradient(to right, ${gridStops.join(', ')})`

  const visible = resolved.filter(t => {
    if (cadFilter !== 'All' && t.cadence !== cadFilter) return false
    if (issuesOnly && !(t.status === 'overdue' || t.status === 'blocked')) return false
    return true
  })

  const dated = resolved.filter(t => t.state !== 'recurring' && t.state !== 'conditional')
  const overdue = dated.filter(t => t.status === 'overdue')
  const blocked = dated.filter(t => t.status === 'blocked')
  const budget = resolved.reduce((a, t) => a + t.budget, 0)
  const spent = resolved.reduce((a, t) => a + t.spent, 0)
  const doneCount = dated.filter(t => t.status === 'done').length

  const blockages = overdue.map(t => {
    const holds = (dependents[t.id] || []).filter(id => rById[id].state !== 'done')
    return {
      id: t.id, title: t.title,
      detail: t.role + ' → ' + t.person + ' · was due ' + fmtDate(t.due) + (holds.length ? ' · holding up ' + holds.map(id => rById[id].title).join(', ') : ' · nothing downstream'),
    }
  })

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 7 }
  const pill = (active, tone = 'accent') => {
    const on = { accent: ['rgba(99,102,241,0.45)', 'rgba(99,102,241,0.12)', C.accent], red: ['rgba(239,91,91,0.45)', 'rgba(239,91,91,0.12)', C.block] }[tone]
    return { padding: '5px 10px', borderRadius: 999, fontSize: 12, cursor: 'pointer', border: `1px solid ${active ? on[0] : C.hair2}`, background: active ? on[1] : 'transparent', color: active ? on[2] : C.dim }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Club Diary</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>2026/27 SEASON · GENERATED FROM TEMPLATE, EDITED SINCE</Caption>
        </div>
        <SegTabs value={tab} onChange={k => patch({ diaryTab: k })} tabs={[{ key: 'plan', label: 'Season plan' }, { key: 'templates', label: 'Template library' }]} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <StatReadout value={doneCount + '/' + dated.length} label="DATED TASKS DONE" />
          <StatReadout value={String(overdue.length)} label="OVERDUE" fg={overdue.length ? C.block : C.ok} />
          <StatReadout value={String(blocked.length)} label="BLOCKED" fg={blocked.length ? C.block : C.ok} />
          <StatReadout value={money(spent) + ' / ' + money(budget)} label="SPENT / BUDGETED" />
        </div>
      </ScreenHeader>

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {tab === 'plan' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${C.hair}`, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
            <div>
              <div style={cap}>CRITICAL PATH — {cpLen} days of chained work</div>
              <div style={{ fontSize: 13, color: C.text, lineHeight: 1.5, background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', borderRadius: 8, padding: '10px 12px' }}>
                {cpPath.length ? cpPath.map(id => rById[id].title).join('  →  ') : 'No remaining dependency chain.'}
              </div>
            </div>
            <div>
              <div style={cap}>BLOCKAGES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {blockages.map(b => (
                  <div key={b.id} onClick={() => patch({ task: b.id })} style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 11px', borderRadius: 8, background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', cursor: 'pointer' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.block, marginTop: 5, flexShrink: 0 }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{b.title}</div>
                      <div style={{ fontSize: 11.5, color: C.dim, marginTop: 2, lineHeight: 1.4 }}>{b.detail}</div>
                    </div>
                  </div>
                ))}
                {blockages.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Nothing overdue. The season plan is on track.</div>}
              </div>
            </div>
          </div>

          <div style={{ padding: '11px 20px', borderBottom: `1px solid ${C.hair}`, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {['All'].concat(CADENCES).map(c => (
              <button key={c} onClick={() => patch({ cadFilter: c })} style={pill(cadFilter === c)}>{c}</button>
            ))}
            <button onClick={() => patch({ issuesOnly: !issuesOnly })} style={pill(issuesOnly, 'red')}>Overdue &amp; blocked only</button>
          </div>

          <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
            <div style={{ minWidth: 1000 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '330px 1fr', position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
                <div style={{ padding: '8px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest }}>TASK</div>
                <div style={{ display: 'flex' }}>
                  {months.map((m, i) => (
                    <div key={i} style={{ flex: `${m.days} 0 0`, padding: '8px 6px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.1em', color: C.faint }}>{m.label}</div>
                  ))}
                </div>
              </div>

              {CADENCES.map(cadence => {
                const items = visible.filter(t => t.cadence === cadence)
                if (!items.length) return null
                const isCol = !!collapsed[cadence]
                return (
                  <div key={cadence}>
                    <div onClick={() => patch({ diaryCollapsed: { ...collapsed, [cadence]: !isCol } })}
                      style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 16px', background: C.surface, borderBottom: `1px solid ${C.hair}`, borderTop: `1px solid ${C.hair}`, cursor: 'pointer' }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: C.faint }}>{isCol ? '▸' : '▾'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim }}>{cadence}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest }}>{items.length} task{items.length === 1 ? '' : 's'}</span>
                    </div>
                    {!isCol && items.map(t => {
                      const tone = DIARY_TONE[t.status]
                      const onCp = !!cpSet[t.id]
                      const recurs = t.status === 'recurring' || t.status === 'conditional'
                      const left = (t.startDay / SEASON_DAYS) * 100
                      const width = Math.max(1.4, (t.dur / SEASON_DAYS) * 100)
                      const overBudget = t.spent > t.budget && t.budget > 0
                      return (
                        <div key={t.id} style={{ display: 'grid', gridTemplateColumns: '330px 1fr', borderBottom: `1px solid ${C.surface2}`, background: st.task === t.id ? 'rgba(99,102,241,0.06)' : 'transparent' }}>
                          <div onClick={() => patch({ task: t.id })} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 14px', borderRight: `1px solid ${C.hair}`, cursor: 'pointer', minWidth: 0 }}>
                            <span style={{ width: 8, height: 8, borderRadius: t.milestone ? 2 : '50%', flexShrink: 0, background: tone.fg }} />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontSize: 13.5, fontWeight: 600, color: t.status === 'done' ? C.dim : C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: t.status === 'done' ? 'line-through' : undefined, textDecorationColor: t.status === 'done' ? C.faintest : undefined }}>{t.title}</div>
                              <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.role + ' → ' + t.person + (recurs ? '  ·  ' + t.rule : '  ·  due ' + fmtDate(t.due))}</div>
                            </div>
                            {t.blockers.length > 0 && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4, border: '1px solid rgba(239,91,91,0.4)', color: C.block, flexShrink: 0 }}>⛔ {t.blockers.length}</span>}
                            {onCp && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.1em', padding: '2px 5px', borderRadius: 4, background: 'rgba(239,91,91,0.15)', color: C.block, flexShrink: 0 }}>CP</span>}
                          </div>
                          <div style={{ position: 'relative', height: 42, backgroundImage: trackGrid }}>
                            <div style={{ position: 'absolute', top: 0, bottom: 0, left: (TODAY_DAY / SEASON_DAYS) * 100 + '%', width: 1, background: 'rgba(99,102,241,0.45)' }} />
                            <div onClick={() => patch({ task: t.id })} style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: left + '%', width: width + '%', height: 20, borderRadius: 5, display: 'flex', alignItems: 'center', padding: '0 6px', overflow: 'hidden', cursor: 'pointer',
                              ...(recurs
                                ? { backgroundImage: `repeating-linear-gradient(90deg, ${tone.fg}55 0 6px, transparent 6px 12px)`, border: `1px dashed ${tone.fg}66` }
                                : { background: `color-mix(in srgb, ${tone.fg} 22%, transparent)`, border: `1px solid ${onCp ? tone.fg : `color-mix(in srgb, ${tone.fg} 45%, transparent)`}` }),
                              ...(t.status === 'blocked' ? { backgroundImage: 'repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.28) 4px 8px)' } : {}) }}>
                              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', color: tone.fg, whiteSpace: 'nowrap' }}>{recurs ? tone.label : (t.budget ? money(t.budget) : tone.label)}</span>
                            </div>
                            {overBudget && <span style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: `calc(${left + width}% + 8px)`, fontFamily: MONO, fontSize: 9, color: C.block, whiteSpace: 'nowrap' }}>{money(t.spent - t.budget)} over</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {tab === 'templates' && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 340px', gap: 0, alignItems: 'start', minHeight: 0 }}>
          <div className="pb-scroll" style={{ padding: '18px 20px', overflowY: 'auto' }}>
            <div style={{ ...cap, marginBottom: 4 }}>TEMPLATE LIBRARY</div>
            <p style={{ fontSize: 13, color: C.dim, margin: '0 0 14px', maxWidth: '46rem', lineHeight: 1.55 }}>The club's standing knowledge — what has to happen every season, who owns it by role, when it falls relative to Round 1, what it costs and what it depends on. Edit here and every future season inherits it.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {DIARY_TEMPLATES.map((t, i) => (
                <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px', display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{t.title}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, background: C.surface2, color: C.dim, flexShrink: 0 }}>{t.cadence}</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginTop: 3 }}>{t.role} · {t.timing}</div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim }}>{t.budget ? money(t.budget) : '—'}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 2 }}>{t.deps ? t.deps + ' dep' + (t.deps === 1 ? '' : 's') : 'no deps'}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="pb-scroll" style={{ borderLeft: `1px solid ${C.hair}`, background: C.surface, padding: '18px 16px', overflowY: 'auto', alignSelf: 'stretch' }}>
            <div style={cap}>GENERATE A SEASON</div>
            <p style={{ fontSize: 12.5, color: C.dim, margin: '0 0 12px', lineHeight: 1.5 }}>Dates anchor to Round 1. Each template's role is substituted for whoever holds it in the season you generate.</p>
            <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.1em', color: C.faint, marginBottom: 6 }}>ROLE → 2027/28 HOLDER</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 14 }}>
              {ROLE_HOLDERS.map((r, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 6, padding: '6px 9px' }}>
                  <span style={{ fontSize: 12, color: C.dim }}>{r.role}</span>
                  <span style={{ fontSize: 12, color: C.text, fontWeight: 600 }}>{r.person}</span>
                </div>
              ))}
            </div>
            <button onClick={() => patch({ toast: { tone: 'ok', title: 'Generated 2027/28 from template.', body: DIARY_TEMPLATES.length + ' tasks created, dates anchored to Round 1, roles substituted for this season’s holders. Nothing is locked — edit the generated plan freely.' } })}
              style={{ width: '100%', padding: '9px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Generate 2027/28 plan</button>
          </div>
        </div>
      )}
    </div>
  )
}
