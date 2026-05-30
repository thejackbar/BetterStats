/* bs-availability.jsx — redesigned availability matrix.
   Players × upcoming dates. Cleaner filter bar, per-column at-a-glance, this-
   weekend emphasis with a direct "Pick XI" handoff into selection. */

const AV_CYCLE = ['NO_RESPONSE', 'AVAILABLE', 'UNAVAILABLE', 'MAYBE'];

// Seed a plausible (player,date) availability map.
function seedAvail() {
  const m = {};
  BS_PLAYERS.forEach((p, i) => {
    m[p.id] = {};
    BS_DATES.forEach((d, j) => {
      if (j === 0) { m[p.id][d.date] = p.avail; return; }
      // Later weeks: mostly unanswered, with some carried-through patterns.
      const pat = [p.avail, 'NO_RESPONSE', 'AVAILABLE', 'NO_RESPONSE'];
      let s = pat[(i + j) % pat.length];
      if (p.avail === 'UNAVAILABLE' && p.note && p.note.includes('Injured')) s = 'UNAVAILABLE'; // period
      m[p.id][d.date] = s;
    });
  });
  return m;
}

// Which cells come from a period (dashed border) — the injured player, all dates.
function isPeriodCell(p, date) {
  return p.note && p.note.includes('Injured');
}

function AvailCell({ status, period, onClick, current }) {
  const T = window.BST;
  const a = BS_AVAIL[status] || BS_AVAIL.NO_RESPONSE;
  const empty = status === 'NO_RESPONSE';
  return (
    <button onClick={onClick} title={`${a.label}${period ? ' · from a period (click to override)' : ''}`} style={{
      width: 38, height: 30, borderRadius: 7, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: T.mono, fontSize: 14, fontWeight: 600,
      color: empty ? T.faintest : a.text,
      background: empty ? 'transparent' : a.tint,
      border: period ? `1.5px dashed ${a.text}` : `1px solid ${empty ? T.hair : 'transparent'}`,
      transition: 'transform .1s', outline: current ? 'none' : 'none',
    }}
      onMouseDown={e => e.currentTarget.style.transform = 'scale(0.88)'}
      onMouseUp={e => e.currentTarget.style.transform = 'scale(1)'}
      onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}>
      {a.glyph}
    </button>
  );
}

function AvailabilityScreen({ onNav, chrome = true }) {
  const T = window.BST;
  const [avail, setAvail] = React.useState(seedAvail);
  const [search, setSearch] = React.useState('');
  const [roster, setRoster] = React.useState('current');
  const [respFilter, setRespFilter] = React.useState(null);
  const [selected, setSelected] = React.useState(() => new Set());
  const [bulk, setBulk] = React.useState('AVAILABLE');
  // The "active week" — click a column header to change it. Drives the Pick XI
  // handoff and (when no range is set) what bulk-marking targets.
  const [selDate, setSelDate] = React.useState(() => (BS_DATES.find(d => d.current) || BS_DATES[0]).date);
  // Date range — scope the grid to a set of games and bulk-mark across them.
  const [rangeOn, setRangeOn] = React.useState(false);
  const [rangeFrom, setRangeFrom] = React.useState(BS_DATES[0].date);
  const [rangeTo, setRangeTo] = React.useState(BS_DATES[BS_DATES.length - 1].date);
  const idxOf = (dt) => BS_DATES.findIndex(d => d.date === dt);
  const inRange = (dt) => { const i = idxOf(dt), a = idxOf(rangeFrom), b = idxOf(rangeTo); return i >= Math.min(a, b) && i <= Math.max(a, b); };
  const rangeDates = () => BS_DATES.filter(d => inRange(d.date)).map(d => d.date);
  const dateLabel = (dt) => (BS_DATES.find(d => d.date === dt) || {}).label || dt;
  const [modal, setModal] = React.useState(null); // { pid, date }
  // Keep the active week inside the range when one is set.
  React.useEffect(() => { if (rangeOn && !inRange(selDate)) setSelDate(rangeFrom); }, [rangeOn, rangeFrom, rangeTo]);

  const cycle = (pid, date) => {
    setAvail(a => {
      const cur = a[pid][date];
      const next = AV_CYCLE[(AV_CYCLE.indexOf(cur) + 1) % AV_CYCLE.length];
      return { ...a, [pid]: { ...a[pid], [date]: next } };
    });
  };

  const players = React.useMemo(() => {
    let list = BS_PLAYERS.slice();
    if (roster === 'current') list = list.filter(p => !p.dormant);
    if (search.trim()) list = list.filter(p => p.name.toLowerCase().includes(search.toLowerCase()));
    if (respFilter) list = list.filter(p => Object.values(avail[p.id]).includes(respFilter));
    return list;
  }, [roster, search, respFilter, avail]);

  // Per-date tallies across shown players
  const colTally = (date) => {
    const t = { AVAILABLE: 0, MAYBE: 0, NO_RESPONSE: 0, UNAVAILABLE: 0 };
    players.forEach(p => { const s = avail[p.id][date]; t[s] = (t[s] || 0) + 1; });
    return t;
  };

  const toggleSel = (pid) => setSelected(s => { const n = new Set(s); n.has(pid) ? n.delete(pid) : n.add(pid); return n; });
  const applyBulk = () => {
    const targets = rangeOn ? rangeDates() : [selDate];
    setAvail(a => {
      const next = { ...a };
      selected.forEach(pid => { next[pid] = { ...next[pid] }; targets.forEach(dt => next[pid][dt] = bulk); });
      return next;
    });
    setSelected(new Set());
  };

  const content = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%' }}>
      {/* Filter bar — one compact row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Search value={search} onChange={setSearch} placeholder="Search players…" width={230} />
        <Segmented value={roster} onChange={setRoster} options={[
          { value: 'current', label: 'Current squad' }, { value: 'all', label: 'All' },
        ]} />
        <div style={{ display: 'flex', gap: 7, marginLeft: 4 }}>
          {BS_AVAIL_ORDER.map(s => (
            <Chip key={s} label={BS_AVAIL[s].label} dot={BS_AVAIL[s].dot}
              active={respFilter === s} onClick={() => setRespFilter(respFilter === s ? null : s)} />
          ))}
        </div>
        <button onClick={() => setRangeOn(v => !v)} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7,
          background: rangeOn ? 'rgba(22,199,132,0.12)' : 'transparent', border: `1px solid ${rangeOn ? 'rgba(22,199,132,0.4)' : T.hair2}`,
          color: rangeOn ? T.accent : T.dim, borderRadius: 8, padding: '7px 12px', fontSize: 12.5, cursor: 'pointer', fontFamily: T.body }}>
          <Icon name="fixtures" size={14} /> Date range {rangeOn ? '▲' : '▼'}
        </button>
      </div>

      {rangeOn && (() => {
        const games = BS_DATES.filter(d => inRange(d.date));
        const weekOpt = (val, onChange) => (
          <select value={val} onChange={e => onChange(e.target.value)} style={{ background: T.surface2, color: T.text, border: `1px solid ${T.hair2}`,
            borderRadius: 8, padding: '7px 10px', fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer' }}>
            {BS_DATES.map(d => <option key={d.date} value={d.date}>{d.label}</option>)}
          </select>
        );
        return (
          <div className="pb-card" style={{ padding: '13px 16px', display: 'flex', alignItems: 'center', gap: 12, background: T.surface, flexWrap: 'wrap' }}>
            <span className="eyebrow">Date range</span>
            {weekOpt(rangeFrom, setRangeFrom)}
            <span style={{ color: T.faint }}>→</span>
            {weekOpt(rangeTo, setRangeTo)}
            <div style={{ width: 1, height: 24, background: T.hair }} />
            <span style={{ fontSize: 12, color: T.faint }}>{games.length} game{games.length === 1 ? '' : 's'}:</span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {games.map(g => {
                const [rnd, opp] = g.sub.split(' · ');
                return <span key={g.date} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: T.dim,
                  background: T.surface2, border: `1px solid ${T.hair}`, borderRadius: 999, padding: '4px 10px' }}>
                  <span className="num" style={{ color: T.faint }}>{rnd}</span> {opp}</span>;
              })}
            </div>
            <span style={{ marginLeft: 'auto', fontSize: 11.5, color: T.faint, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Icon name="info" size={13} /> Tick players, then bulk-mark across the range
            </span>
          </div>
        );
      })()}

      {/* Matrix */}
      <div className="pb-card bs-scroll" style={{ flex: 1, minHeight: 0, overflow: 'auto', background: T.surface }}>
        <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%', minWidth: 760 }}>
          <thead>
            <tr>
              <th style={{ position: 'sticky', left: 0, top: 0, zIndex: 3, background: T.surface2, textAlign: 'left',
                padding: '12px 16px', minWidth: 250, borderBottom: `1px solid ${T.hair}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <input type="checkbox" checked={players.length > 0 && players.every(p => selected.has(p.id))}
                    onChange={() => setSelected(s => { const all = players.every(p => s.has(p.id)); const n = new Set(s); players.forEach(p => all ? n.delete(p.id) : n.add(p.id)); return n; })}
                    style={{ accentColor: T.accent, width: 15, height: 15 }} />
                  <span className="eyebrow">Player</span>
                  <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.faint }}>{players.length}</span>
                </div>
              </th>
              {BS_DATES.map(d => {
                const ct = colTally(d.date);
                const segs = BS_AVAIL_ORDER.map(s => ({ s, n: ct[s] })).filter(x => x.n > 0);
                const sel = d.date === selDate;
                const dim = rangeOn && !inRange(d.date);
                const ranged = rangeOn && inRange(d.date);
                return (
                  <th key={d.date} onClick={() => setSelDate(d.date)} style={{ position: 'sticky', top: 0, zIndex: 2, padding: '10px 12px', minWidth: 120, cursor: 'pointer',
                    background: sel ? 'rgba(22,199,132,0.07)' : ranged ? 'rgba(22,199,132,0.035)' : T.surface2, borderBottom: `1px solid ${T.hair}`,
                    borderLeft: `1px solid ${T.hair}`, borderTop: sel ? `2px solid ${T.accent}` : '2px solid transparent', textAlign: 'center',
                    opacity: dim ? 0.4 : 1, transition: 'opacity .15s' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', border: `1.5px solid ${sel ? T.accent : T.faintest}`, background: sel ? T.accent : 'transparent' }} />
                      <span style={{ fontFamily: T.display, fontWeight: 700, fontSize: 13.5, color: sel ? T.accent : T.text }}>{d.label}</span>
                    </div>
                    <div style={{ fontSize: 10.5, color: T.faint, marginTop: 2 }}>{d.sub}</div>
                    <div style={{ display: 'flex', height: 4, borderRadius: 999, overflow: 'hidden', background: T.surface, margin: '8px 0 0' }}>
                      {segs.map(({ s, n }) => <div key={s} style={{ flex: n, background: s === 'NO_RESPONSE' ? T.faintest : BS_AVAIL[s].dot, opacity: s === 'NO_RESPONSE' ? 0.5 : 1 }} />)}
                    </div>
                    <div className="num" style={{ fontSize: 10.5, color: T.dim, marginTop: 6 }}><b style={{ color: T.accent }}>{ct.AVAILABLE}</b> in</div>
                    {sel ? (
                      <button onClick={(e) => { e.stopPropagation(); onNav && onNav('selection'); }} style={{ marginTop: 8, width: '100%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                        background: T.accent, color: '#04130c', border: 'none', borderRadius: 6, padding: '5px 0', fontSize: 11.5, fontWeight: 700, fontFamily: T.display, cursor: 'pointer' }}>
                        Pick XI <Icon name="arrow" size={13} />
                      </button>
                    ) : (
                      <div style={{ marginTop: 8, fontSize: 10.5, color: T.faintest, padding: '5px 0' }}>select week</div>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => (
              <tr key={p.id} style={{ background: selected.has(p.id) ? 'rgba(22,199,132,0.05)' : 'transparent' }}>
                <td style={{ position: 'sticky', left: 0, zIndex: 1, padding: '8px 16px', borderBottom: `1px solid ${T.hair}`,
                  background: selected.has(p.id) ? '#11261c' : T.surface }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                    <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSel(p.id)} style={{ accentColor: T.accent, width: 15, height: 15 }} />
                    <Avatar p={p} size={30} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ fontSize: 14, fontWeight: 500 }}>{p.name}</span>
                        {p.captainPref && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.accent }}>(C)</span>}
                        {p.dormant && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.amber, opacity: 0.8 }}>dormant</span>}
                      </div>
                      <div style={{ marginTop: 3 }}><RoleChips roles={p.roles} muted /></div>
                    </div>
                  </div>
                </td>
                {BS_DATES.map(d => (
                  <td key={d.date} style={{ textAlign: 'center', padding: '8px 0', borderBottom: `1px solid ${T.hair}`,
                    borderLeft: `1px solid ${T.hair}`, background: d.date === selDate ? 'rgba(22,199,132,0.04)' : (rangeOn && inRange(d.date)) ? 'rgba(22,199,132,0.02)' : 'transparent',
                    opacity: rangeOn && !inRange(d.date) ? 0.4 : 1, transition: 'opacity .15s' }}>
                    <AvailCell status={avail[p.id][d.date]} period={isPeriodCell(p, d.date)} current={d.date === selDate} onClick={() => setModal({ pid: p.id, date: d.date })} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bulk bar */}
      {selected.size > 0 && (
        <div className="pb-card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px',
          border: `1px solid ${T.accent}`, background: 'rgba(22,199,132,0.06)' }}>
          <span style={{ fontFamily: T.mono, fontSize: 12, color: T.accent }}>{selected.size} selected</span>
          <span style={{ fontSize: 13, color: T.dim }}>mark</span>
          <Segmented sm value={bulk} onChange={setBulk} options={BS_AVAIL_ORDER.map(s => ({ value: s, label: BS_AVAIL[s].short }))} />
          {rangeOn ? (
            <>
              <span style={{ fontSize: 13, color: T.dim }}>across</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '6px 12px', borderRadius: 999,
                background: 'rgba(22,199,132,0.1)', border: '1px solid rgba(22,199,132,0.3)', color: T.accent, fontSize: 12.5 }}>
                {dateLabel(rangeFrom)} → {dateLabel(rangeTo)} <span className="num" style={{ color: T.accent }}>· {rangeDates().length} games</span>
              </span>
            </>
          ) : (
            <>
              <span style={{ fontSize: 13, color: T.dim }}>for</span>
              <select value={selDate} onChange={e => setSelDate(e.target.value)} style={{ background: T.surface2, color: T.text, border: `1px solid ${T.hair2}`,
                borderRadius: 8, padding: '7px 10px', fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer' }}>
                {BS_DATES.map(d => <option key={d.date} value={d.date}>{d.label}{d.current ? ' · this week' : ''}</option>)}
              </select>
            </>
          )}
          <Btn variant="primary" sm onClick={applyBulk}>Apply</Btn>
          <Btn variant="ghost" sm onClick={() => setSelected(new Set())}>Clear</Btn>
        </div>
      )}
    </div>
  );

  if (!chrome) return content;
  return (
    <BSShell active="availability" title="Availability" subtitle="Who's around — click any cell to update, or tick players to bulk-mark a week or date range" onNav={onNav}
      actions={<Btn variant="primary" sm icon="selection" onClick={() => onNav && onNav('selection')}>Pick this weekend</Btn>}
      overlay={modal && (() => {
        const pl = BS_PLAYERS.find(p => p.id === modal.pid);
        const cur = avail[modal.pid][modal.date];
        return <QuickAvailModal player={pl} dateLabel={dateLabel(modal.date)} current={cur}
          onPick={s => { setAvail(a => ({ ...a, [modal.pid]: { ...a[modal.pid], [modal.date]: s } })); setModal(null); }}
          onClose={() => setModal(null)} />;
      })()}>
      {content}
    </BSShell>
  );
}

Object.assign(window, { AvailabilityScreen });
