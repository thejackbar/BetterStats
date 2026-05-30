/* bs-selection-c.jsx — Selection (Option C): batting-order slots.
   Position-led picking. Focus a slot, tap/drag/right-click a pool player to
   fill it. Smart helpers: team-balance readout, autofill, per-slot suggestions,
   role-fit hints, and a shareable team sheet. */

const POS_HINTS = ['Opener', 'Opener', 'First drop', 'Top order', 'Top order', 'Middle order', 'Finisher', 'All-rounder', 'Bowler', 'Bowler', 'Bowler', '12th', '13th'];
// Roles that "fit" each batting position — used for suggestions + gentle hints.
const slotAccepts = (i) => i <= 4 ? ['BAT', 'WKT', 'ALL'] : i <= 6 ? ['BAT', 'ALL', 'WKT'] : i === 7 ? ['ALL', 'BWL'] : ['BWL', 'ALL'];
const fitsSlot = (p, i) => p && p.roles.some(r => slotAccepts(i).includes(r));

function SelectionC({ onNav, chrome = true, subtitle }) {
  const T = window.BST;
  const filt = useFilter();
  useAvailVersion();
  const [modalP, setModalP] = React.useState(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const [format, setFormat] = React.useState(11);
  const [slots, setSlots] = React.useState(() => {
    const a = BS_DEFAULT_XI.slice(0, 11);
    while (a.length < 11) a.push(null);
    return a;
  });
  const [captain, setCaptain] = React.useState('p1');
  const [keeper, setKeeper] = React.useState('p10');
  const [focus, setFocus] = React.useState(() => BS_DEFAULT_XI.length);
  const [dirty, setDirty] = React.useState(false);
  const dragId = React.useRef(null);

  React.useEffect(() => {
    setSlots(s => { const n = s.slice(0, format); while (n.length < format) n.push(null); return n; });
    setFocus(f => Math.min(f, format - 1));
  }, [format]);

  const filled = slots.filter(Boolean);
  const inXI = (id) => slots.includes(id);
  const firstEmpty = () => slots.indexOf(null);

  const placeAt = (id, idx) => {
    setSlots(s => { const n = s.map(x => x === id ? null : x); n[idx] = id; return n; });
    setDirty(true);
    setFocus(() => { const after = slots.findIndex((x, k) => k > idx && !x); return after === -1 ? idx : after; });
  };
  const tapPlayer = (p) => {
    if (p.clash || inXI(p.id)) return;
    let target = slots[focus] == null ? focus : firstEmpty();
    if (target === -1) target = focus;
    placeAt(p.id, target);
  };
  // Right-click shortcut: drop straight into the next empty slot.
  const addNext = (p) => { if (p.clash || inXI(p.id)) return; const e = firstEmpty(); if (e !== -1) placeAt(p.id, e); };
  const clearSlot = (i) => { setSlots(s => { const n = [...s]; const id = n[i]; if (id === captain) setCaptain(null); if (id === keeper) setKeeper(null); n[i] = null; return n; }); setFocus(i); setDirty(true); };

  const squadRank = (p) => squadOf(p) === BS_FIXTURE.team ? 0 : 1;
  const pool = filt.apply(eligiblePool().filter(p => !inXI(p.id)))
    .sort((a, b) => (squadRank(a) - squadRank(b)) || (BS_AVAIL[availOf(a)].rank - BS_AVAIL[availOf(b)].rank) || a.name.localeCompare(b.name));

  // Suggested pick for an empty slot: best-fitting available player.
  const suggestionFor = (i) => {
    const cands = pool.filter(p => !p.clash);
    const fit = cands.filter(p => fitsSlot(p, i));
    return (fit.length ? fit : cands)[0] || null;
  };
  // Fill empty slots from last week's team (position-aware), then top up any
  // remaining gaps with the best available fitting player.
  const autofill = () => {
    setSlots(s => {
      const n = [...s];
      const used = new Set(n.filter(Boolean));
      for (let i = 0; i < n.length; i++) {
        if (n[i]) continue;
        const prevId = BS_PREV_XI[i];
        const pp = prevId && byId(prevId);
        if (pp && !used.has(prevId) && !pp.clash && availOf(pp) !== 'UNAVAILABLE') { n[i] = prevId; used.add(prevId); }
      }
      let avail = eligiblePool().filter(p => !used.has(p.id) && !p.clash && availOf(p) !== 'UNAVAILABLE')
        .sort((a, b) => (squadRank(a) - squadRank(b)) || (BS_AVAIL[availOf(a)].rank - BS_AVAIL[availOf(b)].rank) || a.name.localeCompare(b.name));
      for (let i = 0; i < n.length; i++) {
        if (n[i]) continue;
        const fi = avail.findIndex(p => fitsSlot(p, i));
        const pick = fi >= 0 ? avail.splice(fi, 1)[0] : avail.shift();
        if (pick) { n[i] = pick.id; used.add(pick.id); }
      }
      return n;
    });
    setDirty(true);
  };

  // Team-balance readout.
  const cats = filled.map(byId);
  const cBat = cats.filter(p => p.roles.includes('BAT')).length;
  const cAll = cats.filter(p => p.roles.includes('ALL')).length;
  const cBwl = cats.filter(p => p.roles.includes('BWL')).length;
  const cWk = cats.filter(p => p.roles.includes('WKT')).length;
  const bowlingOptions = cats.filter(p => p.roles.includes('BWL') || p.roles.includes('ALL')).length;
  const keeperOk = keeper && inXI(keeper);
  const emptyCount = slots.filter(x => !x).length;
  const lightBowling = filled.length >= 8 && bowlingOptions < 5;

  // Distinct suggestion per empty slot (don't repeat the same name across slots).
  const suggestMap = {};
  { const taken = new Set(); slots.forEach((id, i) => {
    if (id) return;
    const cands = pool.filter(p => !p.clash && !taken.has(p.id));
    const fit = cands.filter(p => fitsSlot(p, i));
    const pick = (fit.length ? fit : cands)[0];
    if (pick) { suggestMap[i] = pick; taken.add(pick.id); }
  }); }

  const content = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%' }}>
      <SelContextBar count={filled.length} format={format} setFormat={setFormat} dirty={dirty}
        onShare={() => setSheetOpen(true)} onSave={() => setDirty(false)} />

      {/* Team balance + roles + autofill */}
      <div className="pb-card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: T.surface, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 7 }}>
          <RoleCount code="BAT" label="batting" n={cBat} />
          <RoleCount code="ALL" label="all-round" n={cAll} />
          <RoleCount code="BWL" label="bowling" n={cBwl} warn={lightBowling} />
          <RoleCount code="WK" label="keeper" n={cWk} warn={cWk === 0} />
        </div>
        <div style={{ width: 1, height: 26, background: T.hair }} />
        <StatusPill ok={!!captain && inXI(captain)} label="Capt" value={captain && inXI(captain) ? byId(captain).name.split(' ')[0] + ' ' + (byId(captain).name.split(' ')[1] || '') : 'None'} />
        <StatusPill ok={keeperOk} label="Keeper" value={keeperOk ? byId(keeper).name.split(' ')[0] + ' ' + (byId(keeper).name.split(' ')[1] || '') : 'Not named'} warn />
        {lightBowling && <span style={{ fontSize: 11.5, color: T.amber, display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="info" size={13} /> Light on bowling</span>}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {emptyCount > 0 && <Btn variant="soft" sm icon="bolt" onClick={autofill} title="Fill empty slots from last week's team">Fill from last week</Btn>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.25fr 1fr', gap: 16, flex: 1, minHeight: 0 }}>
        {/* Slots (right) */}
        <div className="pb-card bs-scroll" style={{ order: 2, overflow: 'auto', background: T.surface, padding: 12 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {slots.map((id, i) => {
              const p = id ? byId(id) : null;
              const focused = i === focus;
              const sug = !p ? suggestMap[i] : null;
              return (
                <div key={i} onClick={() => setFocus(i)}
                  onDragOver={ev => ev.preventDefault()}
                  onDrop={() => { if (dragId.current) { placeAt(dragId.current, i); dragId.current = null; } }}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px', borderRadius: 9, cursor: 'pointer',
                    background: p ? T.surface2 : focused ? 'rgba(22,199,132,0.04)' : 'transparent',
                    border: focused ? `1.5px solid ${T.accent}` : `1.5px ${p ? 'solid' : 'dashed'} ${p ? T.hair : T.hair2}`,
                    transition: 'all .12s' }}>
                  <span className="num" style={{ width: 22, textAlign: 'center', fontFamily: T.display, fontWeight: 700, fontSize: 17, color: p ? T.text : T.faint, lineHeight: 1 }}>{i + 1}</span>
                  <span style={{ fontSize: 10.5, color: T.faint, width: 74, fontFamily: T.mono, display: 'flex', alignItems: 'center', gap: 5 }}>
                    {POS_HINTS[i]}
                  </span>
                  {p ? (
                    <>
                      <AvailDot p={p} onEdit={setModalP} />
                      <Avatar p={p} size={28} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ fontSize: 13.5, fontWeight: 500 }}>{p.name}</span>
                          {captain === id && <Tag>C</Tag>}{keeper === id && <Tag>WK</Tag>}
                        </div>
                      </div>
                      <RoleChips roles={p.roles} muted />
                      <div style={{ display: 'flex', gap: 3 }}>
                        <FlagBtn on={captain === id} onClick={(e) => { e.stopPropagation(); setCaptain(c => c === id ? null : id); setDirty(true); }}>C</FlagBtn>
                        <FlagBtn on={keeper === id} onClick={(e) => { e.stopPropagation(); setKeeper(k => k === id ? null : id); setDirty(true); }}>WK</FlagBtn>
                        <button onClick={(e) => { e.stopPropagation(); clearSlot(i); }} style={{ background: 'none', border: 'none', color: T.faint, cursor: 'pointer', display: 'flex', padding: 3 }}><Icon name="close" size={14} /></button>
                      </div>
                    </>
                  ) : sug && focused ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 9 }}>
                      <span style={{ fontSize: 11, color: T.faint, fontStyle: 'italic' }}>Suggested</span>
                      <AvailDot p={sug} onEdit={setModalP} />
                      <span style={{ fontSize: 13, fontWeight: 500, color: T.dim }}>{sug.name}</span>
                      <RoleChips roles={sug.roles} muted />
                      <button onClick={(e) => { e.stopPropagation(); placeAt(sug.id, i); }} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5,
                        background: 'rgba(22,199,132,0.14)', color: T.accent, border: '1px solid rgba(22,199,132,0.35)', borderRadius: 7, padding: '4px 10px', fontSize: 12, fontWeight: 600, fontFamily: T.display, cursor: 'pointer' }}>
                        <Icon name="plus" size={13} /> Add
                      </button>
                    </div>
                  ) : (
                    <span style={{ flex: 1, fontSize: 12.5, color: T.faintest, fontStyle: 'italic' }}>
                      Empty{sug ? <> · <span style={{ color: T.faint, fontStyle: 'normal' }}>try {sug.name}</span></> : ' — click to focus'}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Pool (left, given more room) */}
        <div className="pb-card" style={{ order: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: T.surface }}>
          <div className="pb-hair-b" style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 11 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
              <h3 style={{ margin: 0, fontFamily: T.display, fontWeight: 700, fontSize: 15 }}>Available pool</h3>
              <span className="num" style={{ fontSize: 12, color: T.faint }}>{pool.length} · tap → slot <b style={{ color: T.accent }}>{focus + 1}</b> · right-click → next empty</span>
            </div>
            <SelFilterRow state={filt.state} set={filt.set} />
          </div>
          <div className="bs-scroll" style={{ overflow: 'auto', flex: 1 }}>
            {pool.map(p => (
              <div key={p.id} draggable={!p.clash} onDragStart={() => dragId.current = p.id}
                onClick={() => tapPlayer(p)} onContextMenu={(e) => { e.preventDefault(); addNext(p); }}
                className="pb-hair-b" style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 14px',
                  borderBottom: `1px solid ${T.hair}`, cursor: p.clash ? 'not-allowed' : 'pointer', background: BS_AVAIL[availOf(p)].tint, opacity: p.clash ? 0.5 : 1 }}>
                <AvailDot p={p} onEdit={setModalP} />
                <Avatar p={p} size={28} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 500 }}>{p.name}</span>
                    {p.clash && <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.red }}>⛔ {p.clash}</span>}
                  </div>
                  {p.note && <div style={{ fontSize: 11, color: T.faint, marginTop: 1 }}>{p.note}</div>}
                </div>
                <RoleChips roles={p.roles} muted />
                <span style={{ fontFamily: T.mono, fontSize: 9, color: squadOf(p) === BS_FIXTURE.team ? T.accent : T.faint,
                  background: squadOf(p) === BS_FIXTURE.team ? 'rgba(22,199,132,0.1)' : T.surface2, padding: '2px 6px', borderRadius: 4 }}>{squadOf(p)}</span>
                {!p.clash && <span style={{ color: T.accent, display: 'flex' }}><Icon name="arrow" size={15} /></span>}
              </div>
            ))}
            {pool.length === 0 && <Empty>No players match.</Empty>}
          </div>
        </div>
      </div>
    </div>
  );

  const sheet = sheetOpen && (
    <TeamSheetModal slots={slots} captain={captain} keeper={keeper} format={format} onClose={() => setSheetOpen(false)} />
  );

  if (!chrome) return content;
  return <BSShell active="selection" title="Selection" subtitle={subtitle || 'Option C — batting-order slots'} onNav={onNav}
    overlay={<>{modalP && <QuickAvailModal player={modalP} dateLabel={BS_FIXTURE.date_label} current={availOf(modalP)}
      onPick={s => { setAvailOverride(modalP.id, s); setModalP(null); }} onClose={() => setModalP(null)} />}{sheet}</>}>{content}</BSShell>;
}

function RoleCount({ code, label, n, warn }) {
  const T = window.BST;
  const c = warn ? T.amber : (n > 0 ? T.text : T.faint);
  return (
    <div title={`${n} ${label}`} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 9px', borderRadius: 7,
      background: warn ? 'rgba(245,181,66,0.10)' : T.surface2, border: `1px solid ${warn ? 'rgba(245,181,66,0.3)' : T.hair}` }}>
      <span className="num" style={{ fontFamily: T.display, fontWeight: 700, fontSize: 15, color: c }}>{n}</span>
      <span style={{ fontFamily: T.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.04em', color: warn ? T.amber : T.faint }}>{code}</span>
    </div>
  );
}

function StatusPill({ ok, label, value, warn }) {
  const T = window.BST;
  const c = ok ? T.accent : (warn ? T.amber : T.faint);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 11px', borderRadius: 8,
      background: T.surface2, border: `1px solid ${ok ? 'rgba(22,199,132,0.25)' : warn ? 'rgba(245,181,66,0.25)' : T.hair}` }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: c }} />
      <span style={{ fontSize: 11, color: T.faint }}>{label}</span>
      <span style={{ fontSize: 12.5, fontWeight: 600, color: ok ? T.text : c }}>{value}</span>
    </div>
  );
}

/* Shareable team sheet — the named XI, formatted for sending out. */
function TeamSheetModal({ slots, captain, keeper, format, onClose }) {
  const T = window.BST;
  const xi = slots.filter(Boolean).map(byId);
  const complete = xi.length === format;
  const [copied, setCopied] = React.useState(false);
  const copyText = () => {
    const lines = [
      `${BS_FIXTURE.team} v ${BS_FIXTURE.opponent} — ${BS_FIXTURE.date_label}, ${BS_FIXTURE.venue}, ${BS_FIXTURE.start_time}`,
      '',
      ...xi.map((p, i) => `${i + 1}. ${p.name}${captain === p.id ? ' (C)' : ''}${keeper === p.id ? ' (WK)' : ''}`),
    ];
    const text = lines.join('\n');
    try { navigator.clipboard && navigator.clipboard.writeText(text); } catch (e) {}
    setCopied(true); setTimeout(() => setCopied(false), 1800);
  };
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(4,6,11,0.62)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(2px)' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 420, maxHeight: '86%', display: 'flex', flexDirection: 'column',
        background: T.surface, borderRadius: 14, border: `1px solid ${T.hair2}`, overflow: 'hidden', boxShadow: '0 24px 70px rgba(0,0,0,0.55)' }}>
        <div style={{ padding: '18px 20px', borderBottom: `1px solid ${T.hair}`,
          background: 'linear-gradient(150deg, rgba(22,199,132,0.12), transparent 60%)' }}>
          <div className="eyebrow" style={{ color: T.accent }}>Team sheet · Round {BS_FIXTURE.round}</div>
          <div style={{ fontFamily: T.display, fontWeight: 800, fontSize: 22, marginTop: 4 }}>{BS_FIXTURE.team} vs {BS_FIXTURE.opponent}</div>
          <div style={{ fontSize: 12.5, color: T.dim, marginTop: 3 }}>{BS_FIXTURE.date_label} · {BS_FIXTURE.venue} · {BS_FIXTURE.start_time}</div>
        </div>
        <div className="bs-scroll" style={{ overflow: 'auto', flex: 1, padding: '8px 0' }}>
          {xi.map((p, i) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '8px 20px' }}>
              <span className="num" style={{ width: 18, textAlign: 'right', color: T.faint, fontSize: 13 }}>{i + 1}</span>
              <Avatar p={p} size={28} />
              <span style={{ flex: 1, fontSize: 14, fontWeight: 500 }}>
                {p.name} {captain === p.id && <Tag>C</Tag>} {keeper === p.id && <Tag>WK</Tag>}
              </span>
              <RoleChips roles={p.roles} muted />
            </div>
          ))}
          {Array.from({ length: Math.max(0, format - xi.length) }).map((_, i) => (
            <div key={'e' + i} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '8px 20px', color: T.faintest }}>
              <span className="num" style={{ width: 18, textAlign: 'right', fontSize: 13 }}>{xi.length + i + 1}</span>
              <span style={{ fontSize: 13, fontStyle: 'italic' }}>—</span>
            </div>
          ))}
        </div>
        <div style={{ padding: 16, borderTop: `1px solid ${T.hair}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          {!complete && <span style={{ fontSize: 11.5, color: T.amber, display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="info" size={13} /> {format - xi.length} slot{format - xi.length === 1 ? '' : 's'} empty</span>}
          <div style={{ marginLeft: 'auto' }}>
            <Btn variant="primary" sm icon={copied ? 'check' : 'share'} onClick={copyText}>{copied ? 'Copied to clipboard' : 'Copy lineup as text'}</Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SelectionC });
