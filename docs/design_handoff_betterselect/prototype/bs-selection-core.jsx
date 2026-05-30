/* bs-selection-core.jsx — shared selection logic used by the Selection screen.
   Eligible pool, XI state, the compact filter row, the context bar, and small
   atoms (Tag / FlagBtn / Empty). */

/* ── Shared eligible pool ───────────────────────────────────────────────── */
function eligiblePool() {
  // The club's players, annotated for this fixture. Dormant hidden by default.
  return BS_PLAYERS.filter(p => !p.dormant);
}

const byId = (id) => BS_PLAYERS.find(p => p.id === id);

/* ── Shared XI state hook (ordered XI with captain/keeper flags) ─────────── */
function useXI() {
  const init = BS_DEFAULT_XI.map(id => ({ id, isCaptain: id === 'p1', isKeeper: id === 'p10' }));
  const [xi, setXi] = React.useState(init);
  const has = (id) => xi.some(x => x.id === id);
  const add = (id) => setXi(x => x.some(e => e.id === id) ? x : [...x, { id, isCaptain: false, isKeeper: false }]);
  const remove = (id) => setXi(x => x.filter(e => e.id !== id));
  const toggle = (id) => setXi(x => x.some(e => e.id === id) ? x.filter(e => e.id !== id) : [...x, { id, isCaptain: false, isKeeper: false }]);
  const setFlag = (id, flag) => setXi(x => x.map(e => e.id === id ? { ...e, [flag]: !e[flag] } : { ...e, [flag]: false }));
  const reorder = (from, to) => setXi(x => { const n = [...x]; const [m] = n.splice(from, 1); n.splice(to, 0, m); return n; });
  return { xi, setXi, has, add, remove, toggle, setFlag, reorder };
}

/* ── Filter state + the compact filter row ──────────────────────────────── */
function useFilter() {
  const [state, setState] = React.useState({ q: '', role: null, availOnly: false });
  const set = (patch) => setState(s => ({ ...s, ...patch }));
  const apply = (list) => list.filter(p => {
    if (state.q && !p.name.toLowerCase().includes(state.q.toLowerCase())) return false;
    if (state.role && !p.roles.includes(state.role)) return false;
    if (state.availOnly && availOf(p) !== 'AVAILABLE') return false;
    return true;
  });
  return { state, set, apply };
}

function SelFilterRow({ state, set }) {
  const T = window.BST;
  const roleOpts = [['BAT', 'Batters'], ['BWL', 'Bowlers'], ['ALL', 'All-rounders'], ['WKT', 'Keepers']];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <Search value={state.q} onChange={v => set({ q: v })} placeholder="Search pool…" width={190} />
      <div style={{ width: 1, height: 24, background: T.hair }} />
      <div style={{ display: 'flex', gap: 6 }}>
        {roleOpts.map(([k, l]) => (
          <Chip key={k} label={l} active={state.role === k} onClick={() => set({ role: state.role === k ? null : k })} />
        ))}
      </div>
      <div style={{ width: 1, height: 24, background: T.hair }} />
      <Chip label="Available only" dot={T.accent} active={state.availOnly} onClick={() => set({ availOnly: !state.availOnly })} />
    </div>
  );
}

/* ── Context bar (fixture + count + format + save) ──────────────────────── */
function SelContextBar({ count, format, setFormat, dirty, onShare, onSave }) {
  const T = window.BST;
  const off = count !== format;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <span style={{ width: 38, height: 38, borderRadius: 9, background: 'rgba(22,199,132,0.12)', color: T.accent,
          display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon name="selection" size={19} /></span>
        <div>
          <div style={{ fontFamily: T.display, fontWeight: 700, fontSize: 16 }}>{BS_FIXTURE.team} vs {BS_FIXTURE.opponent}</div>
          <div style={{ fontSize: 12, color: T.faint }}>{BS_FIXTURE.date_label} · {BS_FIXTURE.venue} · R{BS_FIXTURE.round}</div>
        </div>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11.5, color: T.faint }}>Side</span>
          <Segmented sm value={format} onChange={setFormat} options={[{ value: 11, label: '11' }, { value: 12, label: '12' }, { value: 13, label: '13' }]} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 999,
          background: off ? 'rgba(245,181,66,0.12)' : 'rgba(22,199,132,0.12)', border: `1px solid ${off ? 'rgba(245,181,66,0.3)' : 'rgba(22,199,132,0.3)'}` }}>
          <span className="num" style={{ fontFamily: T.display, fontWeight: 700, fontSize: 16, color: off ? T.amber : T.accent }}>{count}</span>
          <span style={{ fontSize: 12, color: off ? T.amber : T.accent }}>/ {format} picked</span>
        </div>
        <Btn variant="ghost" sm icon="share" onClick={onShare}>Share</Btn>
        <Btn variant="primary" sm icon="check" disabled={!dirty} onClick={onSave}>{dirty ? 'Save XI' : 'Saved'}</Btn>
      </div>
    </div>
  );
}

/* ── Small atoms ────────────────────────────────────────────────────────── */
function Tag({ children }) {
  const T = window.BST;
  return <span style={{ fontFamily: T.mono, fontSize: 9, fontWeight: 700, color: T.accent, background: 'rgba(22,199,132,0.14)', padding: '1px 5px', borderRadius: 4 }}>{children}</span>;
}
function FlagBtn({ on, onClick, children }) {
  const T = window.BST;
  return <button onClick={onClick} style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, padding: '3px 6px', borderRadius: 5, cursor: 'pointer',
    background: on ? 'rgba(22,199,132,0.16)' : 'transparent', color: on ? T.accent : T.faint, border: `1px solid ${on ? 'rgba(22,199,132,0.4)' : T.hair2}` }}>{children}</button>;
}
function Empty({ children }) {
  const T = window.BST;
  return <div style={{ padding: '40px 20px', textAlign: 'center', color: T.faint, fontSize: 13 }}>{children}</div>;
}

Object.assign(window, { useXI, useFilter, SelFilterRow, SelContextBar, eligiblePool, byId, Tag, FlagBtn, Empty });
