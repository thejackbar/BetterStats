import { C, MONO, ScreenHeader, NavToggle, Toast, initials } from '../ui'
import { AREAS, DOW, DATES, PEOPLE, RULES, personById, checkAssign, bestFor, fmtHour } from '../model'

// Roster — build and publish the repeating weekly roster. Two drag directions:
// in People view a shift chip is dragged onto a person's day cell (or the Open
// row); in Areas view a volunteer card from the side panel is dragged onto a
// shift. Every rule violation is derived on the drop through the rules engine.
export default function Roster({ st, patch, opts, narrow }) {
  const slots = st.slots
  const view = st.view
  const gridCols = narrow ? '176px repeat(7, minmax(0, 1fr))' : '216px repeat(7, minmax(150px, 1fr))'
  const open = slots.filter(x => !x.assignee)
  const filled = slots.length - open.length
  const pct = Math.round((filled / slots.length) * 100)

  // ── assignment through the rules engine ─────────────────────────────────
  const assign = (slotId, personId) => patch(s => {
    const next = s.slots.map(x => ({ ...x }))
    const slot = next.find(x => x.id === slotId)
    if (!slot) return {}
    if (!personId) {
      slot.assignee = null; slot.warns = []
      return { slots: next, toast: { tone: 'info', title: 'Shift returned to Open.', body: AREAS[slot.area].name + ' · ' + DOW[slot.day] } }
    }
    const p = personById(personId)
    const res = checkAssign(p, slot, next, opts)
    if (res.blocks.length) return { toast: { tone: 'block', title: 'Can’t roster ' + p.name + ' here.', body: res.blocks.join(' · ') } }
    slot.assignee = personId; slot.warns = res.warns
    return {
      slots: next,
      toast: res.warns.length
        ? { tone: 'warn', title: p.name + ' rostered with a warning.', body: res.warns.join(' · ') }
        : { tone: 'ok', title: p.name + ' rostered.', body: AREAS[slot.area].name + ' · ' + DOW[slot.day] + ' ' + fmtHour(slot.start) + '–' + fmtHour(slot.end) },
    }
  })

  const autoFill = () => patch(s => {
    const next = s.slots.map(x => ({ ...x }))
    let placed = 0
    next.filter(x => !x.assignee).forEach(slot => {
      const ranked = bestFor(slot, next, opts)
      const best = ranked.filter(x => x.res.warns.length === 0)[0] || ranked[0]
      if (best) { slot.assignee = best.p.id; slot.warns = best.res.warns; placed++ }
    })
    const still = next.filter(x => !x.assignee).length
    return { slots: next, toast: { tone: placed ? 'ok' : 'warn', title: 'Auto-fill proposed ' + placed + ' assignment' + (placed === 1 ? '' : 's') + '.', body: still ? still + ' shift' + (still === 1 ? '' : 's') + ' still need a qualified volunteer — check the amber chips.' : 'Every shift is covered. Review the amber chips, then publish.' } }
  })

  const publish = () => patch({ toast: open.length
    ? { tone: 'warn', title: 'Published with ' + open.length + ' open shift' + (open.length === 1 ? '' : 's') + '.', body: 'Volunteers can self-nominate for the gaps; you confirm each one.' }
    : { tone: 'ok', title: 'Week published.', body: 'Everyone rostered gets their shift and a check-in tap that logs their hours.' } })

  // ── drag helpers ────────────────────────────────────────────────────────
  const cellDrop = (key, personId) => ({
    onDragOver: e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
    onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
    onDrop: e => { e.preventDefault(); const id = st.dragId; patch({ overCell: null, dragId: null }); if (id) assign(id, personId) },
  })
  const slotDrop = (slotId) => {
    const key = 'slot-' + slotId
    return {
      onDragOver: e => { if (!st.dragPerson) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (st.overCell !== key) patch({ overCell: key }) },
      onDragLeave: () => { if (st.overCell === key) patch({ overCell: null }) },
      onDrop: e => { e.preventDefault(); const pid = st.dragPerson; patch({ overCell: null, dragPerson: null }); if (pid) assign(slotId, pid) },
    }
  }

  const cellStyle = (isOver, extra) => ({ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5, ...(isOver ? { background: 'rgba(99,102,241,0.14)', boxShadow: 'inset 0 0 0 1.5px #6366F1' } : {}), ...extra })

  // A draggable shift chip (People view + Open row).
  const ShiftChip = ({ slot, inOpen, count }) => {
    const a = AREAS[slot.area]
    const warned = slot.warns && slot.warns.length
    return (
      <div draggable
        onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragId: slot.id, selected: slot.id }) }}
        onDragEnd={() => patch({ dragId: null, overCell: null })}
        onClick={() => patch({ selected: slot.id })}
        style={{ borderRadius: 7, padding: '6px 8px', cursor: 'grab', userSelect: 'none',
          border: `1px solid ${inOpen ? 'rgba(245,181,66,0.45)' : (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color} 40%, transparent)`)}`,
          background: inOpen ? 'rgba(245,181,66,0.10)' : `color-mix(in srgb, ${a.color} 13%, transparent)`,
          color: inOpen ? C.warn : a.color }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: a.color }} />
          <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{count > 1 ? a.name + ' ×' + count : a.name}</span>
          {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{fmtHour(slot.start)}–{fmtHour(slot.end)}</div>
      </div>
    )
  }

  // ── People view: person rows ────────────────────────────────────────────
  const rows = PEOPLE.map(p => {
    const mine = slots.filter(x => x.assignee === p.id)
    const cap = opts.weeklyShiftCap || p.max
    const loadPct = Math.min(100, Math.round((mine.length / cap) * 100))
    const over = mine.length > cap
    return { p, mine, cap, loadPct, over }
  })

  // ── Areas view: department bands + area rows ─────────────────────────────
  const depts = []
  Object.keys(AREAS).forEach(k => { if (depts.indexOf(AREAS[k].dept) === -1) depts.push(AREAS[k].dept) })

  // ── side panel ──────────────────────────────────────────────────────────
  const sel = st.selected ? slots.find(x => x.id === st.selected) : null
  const cands = sel ? bestFor(sel, slots, opts) : PEOPLE.map(p => ({ p, res: { warns: [] }, load: slots.filter(x => x.assignee === p.id).length }))
  const candidates = cands.slice(0, 12)

  // ── open shifts row: collapse identical unfilled slots ──────────────────
  const openCells = DOW.map((_, d) => {
    const groups = []
    open.filter(x => x.day === d).forEach(x => {
      const g = groups.find(y => y.slot.area === x.area && y.slot.start === x.start && y.slot.end === x.end)
      if (g) g.count++; else groups.push({ slot: x, count: 1 })
    })
    return { d, groups }
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Roster</h1>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint, marginTop: 2 }}>WEEK OF MON 3 NOV 2026</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 3 }}>
          {['people', 'areas'].map(v => (
            <button key={v} onClick={() => patch({ view: v, selected: null })} style={{ padding: '5px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer', textTransform: 'capitalize', background: view === v ? 'rgba(99,102,241,0.15)' : 'transparent', color: view === v ? C.accent : C.faint }}>{v}</button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
            <span style={{ fontWeight: 700, fontSize: 18, color: C.text, fontVariantNumeric: 'tabular-nums' }}>{filled}</span>
            <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, letterSpacing: '0.08em' }}>/ {slots.length} FILLED</span>
          </div>
          <div style={{ width: 120, height: 6, borderRadius: 3, background: C.surface2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: pct + '%', background: pct === 100 ? C.ok : C.accent }} />
          </div>
          <button onClick={() => patch(s => ({ panelOpen: !s.panelOpen }))} style={{ padding: '8px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', ...(st.panelOpen ? { border: '1px solid rgba(99,102,241,0.45)', color: C.accent, background: 'rgba(99,102,241,0.10)' } : { border: `1px solid ${C.hair2}`, color: C.dim, background: 'transparent' }) }}>{st.panelOpen ? 'Hide candidates' : 'Candidates'}</button>
          <button onClick={autoFill} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Auto-fill open shifts</button>
          <button onClick={publish} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Publish week</button>
        </div>
      </ScreenHeader>

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      <div style={{ display: 'flex', flex: 1, minHeight: 0, alignItems: 'stretch' }}>
        <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
          <div style={{ minWidth: narrow ? 0 : 1266 }}>

            {/* header row */}
            <div style={{ display: 'grid', gridTemplateColumns: gridCols, position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
              <div style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, display: 'flex', alignItems: 'center' }}>{view === 'areas' ? 'OPERATIONAL AREA' : 'VOLUNTEER'}</div>
              {DOW.map((d, i) => (
                <div key={i} style={{ padding: '10px 12px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'rgba(99,102,241,0.05)' : undefined }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint }}>{d.toUpperCase()}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: C.dim }}>{DATES[i]}</span>
                </div>
              ))}
            </div>

            {/* open shifts row (People view only) */}
            {view === 'people' && (
              <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair2}`, background: 'rgba(245,181,66,0.04)' }}>
                <div style={{ padding: '12px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 3, justifyContent: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: C.warn }}>Open shifts</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{open.length} unfilled · drag onto a person</span>
                </div>
                {openCells.map(({ d, groups }) => {
                  const key = 'open-' + d
                  const shown = st.openExpanded ? groups : groups.slice(0, 2)
                  const hidden = groups.length - shown.length
                  return (
                    <div key={d} style={cellStyle(st.overCell === key)} {...cellDrop(key, null)}>
                      {shown.map(g => <ShiftChip key={g.slot.id} slot={g.slot} inOpen count={g.count} />)}
                      {(hidden > 0 || (st.openExpanded && groups.length > 2)) && (
                        <button onClick={() => patch(s => ({ openExpanded: !s.openExpanded }))} style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.warn, background: 'transparent', border: '1px dashed rgba(245,181,66,0.4)', borderRadius: 6, padding: '4px 6px', cursor: 'pointer', textAlign: 'left' }}>{hidden > 0 ? '+ ' + hidden + ' more' : 'show less'}</button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* People view rows */}
            {view === 'people' && rows.map(({ p, mine, cap, loadPct, over }) => (
              <div key={p.id} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                <div onClick={() => patch({ person: p.id })} style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <span style={{ width: 28, height: 28, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 10, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(p.name)}</span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.roles.join(' · ') || 'No roles set'}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 7 }}>
                    <div style={{ flex: 1, height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: loadPct + '%', background: over ? C.block : C.accent }} />
                    </div>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: over ? C.block : C.faint }}>{mine.length}/{cap}</span>
                  </div>
                </div>
                {DOW.map((_, d) => {
                  const key = p.id + '-' + d
                  const chips = mine.filter(x => x.day === d)
                  const avail = p.days.includes(d)
                  return (
                    <div key={d} style={cellStyle(st.overCell === key, avail ? {} : { background: 'repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(58,63,80,0.10) 6px, rgba(58,63,80,0.10) 12px)' })} {...cellDrop(key, p.id)}>
                      {chips.map(x => <ShiftChip key={x.id} slot={x} />)}
                      {!chips.length && !avail && <div style={{ fontFamily: MONO, fontSize: 9, color: C.faintest, letterSpacing: '0.08em', margin: 'auto' }}>UNAVAILABLE</div>}
                    </div>
                  )
                })}
              </div>
            ))}

            {/* Areas view rows */}
            {view === 'areas' && depts.map(dept => (
              <div key={dept}>
                <div style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}`, background: C.surface }}>
                  <div style={{ padding: '8px 14px', fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.dim, gridColumn: '1 / -1' }}>{dept}</div>
                </div>
                {Object.keys(AREAS).filter(k => AREAS[k].dept === dept).map(k => {
                  const a = AREAS[k]
                  const mine = slots.filter(x => x.area === k)
                  const filledN = mine.filter(x => x.assignee).length
                  return (
                    <div key={k} style={{ display: 'grid', gridTemplateColumns: gridCols, borderBottom: `1px solid ${C.hair}` }}>
                      <div style={{ padding: '10px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                          <span style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: a.color }} />
                          <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{a.name}</span>
                          <span style={{ fontFamily: MONO, fontSize: 9.5, color: filledN === mine.length ? C.ok : C.warn }}>{filledN}/{mine.length}</span>
                        </div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{a.qual ? a.role + ' · ' + a.qual : a.role}</div>
                      </div>
                      {DOW.map((_, d) => (
                        <div key={d} style={{ borderRight: `1px solid ${C.hair}`, padding: 6, minHeight: 74, display: 'flex', flexDirection: 'column', gap: 5, background: d >= 5 ? 'rgba(99,102,241,0.03)' : undefined }}>
                          {mine.filter(x => x.day === d).map(x => {
                            const who = x.assignee ? personById(x.assignee) : null
                            const warned = x.warns && x.warns.length
                            const over = st.overCell === 'slot-' + x.id
                            return (
                              <div key={x.id} onClick={() => patch({ selected: x.id })} {...slotDrop(x.id)}
                                style={{ borderRadius: 7, padding: '6px 8px', cursor: 'pointer', userSelect: 'none',
                                  border: `1px solid ${who ? (warned ? 'rgba(245,181,66,0.5)' : `color-mix(in srgb, ${a.color} 40%, transparent)`) : 'rgba(245,181,66,0.45)'}`,
                                  background: who ? `color-mix(in srgb, ${a.color} 13%, transparent)` : 'rgba(245,181,66,0.10)',
                                  color: who ? a.color : C.warn,
                                  ...(over ? { boxShadow: '0 0 0 1.5px #6366F1' } : {}),
                                  ...(st.selected === x.id ? { outline: '1.5px solid #6366F1', outlineOffset: 1 } : {}) }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                  <span style={{ fontWeight: 600, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...(who ? {} : { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em' }) }}>{who ? who.name : 'OPEN'}</span>
                                  {warned ? <span style={{ marginLeft: 'auto', color: C.warn, fontSize: 11 }}>!</span> : null}
                                </div>
                                <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.75, marginTop: 2 }}>{fmtHour(x.start)}–{fmtHour(x.end)}</div>
                              </div>
                            )
                          })}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Side panel */}
        {st.panelOpen && (
          <aside className="pb-scroll" style={narrow
            ? { width: 320, maxWidth: '92vw', position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 65, borderLeft: `1px solid ${C.hair2}`, background: C.surface, overflowY: 'auto', padding: 16, boxShadow: '0 0 40px rgba(0,0,0,0.5)' }
            : { width: 296, flex: '0 0 296px', borderLeft: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 16 }}>
            {sel && (
              <div>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>BEST FIT FOR THIS SHIFT</div>
                <div style={{ background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: 12, marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: AREAS[sel.area].color }} />
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{AREAS[sel.area].name}</span>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim, marginTop: 4 }}>{DOW[sel.day]} {fmtHour(sel.start)}–{fmtHour(sel.end)}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, marginTop: 4 }}>{AREAS[sel.area].qual ? 'Requires ' + AREAS[sel.area].role + ' · ' + AREAS[sel.area].qual : 'Requires ' + AREAS[sel.area].role}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button onClick={() => { if (cands[0]) assign(sel.id, cands[0].p.id) }} style={{ flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Fill best match</button>
                    <button onClick={() => { assign(sel.id, null); patch({ selected: null }) }} style={{ padding: '6px 10px', borderRadius: 6, fontSize: 12, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Clear</button>
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest }}>{sel ? 'RANKED CANDIDATES' : 'VOLUNTEER POOL'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{candidates.length} people</span>
            </div>
            <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.45, marginBottom: 10 }}>{view === 'areas' ? 'Drag a volunteer onto a shift, or select a shift to rank them.' : 'Drag a shift between rows, or select one to rank candidates.'}</div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {candidates.map(({ p, res, load }) => (
                <div key={p.id} draggable
                  onClick={() => { if (sel) assign(sel.id, p.id); else patch({ person: p.id }) }}
                  onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; patch({ dragPerson: p.id }) }}
                  onDragEnd={() => patch({ dragPerson: null, overCell: null })}
                  style={{ background: C.surface2, border: `1px solid ${sel && !res.warns.length ? 'rgba(99,102,241,0.35)' : C.hair}`, borderRadius: 8, padding: '9px 10px', cursor: 'pointer' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 26, height: 26, borderRadius: '50%', background: C.surface, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 9.5, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(p.name)}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sel ? (res.warns.length ? res.warns[0] : 'Clear match · ' + load + ' shift' + (load === 1 ? '' : 's')) : (p.roles.join(' · ') || 'No roles set')}</div>
                    </div>
                    {sel && (
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 5px', borderRadius: 4, flexShrink: 0, ...(res.warns.length ? { background: 'rgba(245,181,66,0.15)', color: C.warn } : { background: 'rgba(99,102,241,0.15)', color: C.accent }) }}>{res.warns.length ? 'WARN' : 'FIT'}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 18, borderTop: `1px solid ${C.hair}`, paddingTop: 14 }}>
              <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }}>RULES APPLIED</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {RULES.map((r, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 7, fontSize: 11.5, color: C.dim, lineHeight: 1.35 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', marginTop: 5, flexShrink: 0, background: r.tone === 'block' ? C.block : C.warn }} />
                    <span>{r.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
