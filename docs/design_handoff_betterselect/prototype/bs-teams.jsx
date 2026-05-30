/* bs-teams.jsx — Squads: the selection pools. Players are assigned to a squad
   (drives selection suggestions). Drag between squads, or bulk-add many at once.
   Reads/writes the shared squad store so Players & Selection stay in sync. */

const SQUAD_GRADE = { '1st XI': 'A-Grade', '2nd XI': 'B-Grade', '3rd XI': 'C-Grade', '4th XI': 'D-Grade', 'Veterans': 'Masters' };
const SQUAD_TINT = { '1st XI': '#16c784', '2nd XI': '#3b82f6', '3rd XI': '#a855f7', '4th XI': '#f5b542', 'Veterans': '#06b6d4' };

function SquadCard({ p, onDragStart }) {
  const T = window.BST;
  const st = availOf(p);
  const tint = BS_AVAIL[st].tint;
  return (
    <div draggable onDragStart={onDragStart}
      style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 9px', borderRadius: 8, cursor: 'grab',
        background: tint !== 'transparent' ? tint : T.surface2, border: `1px solid ${T.hair}` }}>
      <Dot status={st} />
      <Avatar p={p} size={26} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          {p.captainPref && <Tag>C</Tag>}
        </div>
      </div>
      <RoleChips roles={p.roles} muted />
    </div>
  );
}

function BulkAddModal({ squad, onAdd, onClose }) {
  const T = window.BST;
  const candidates = BS_PLAYERS.filter(p => squadOf(p) !== squad);
  const [sel, setSel] = React.useState(() => new Set());
  const [q, setQ] = React.useState('');
  const list = candidates.filter(p => !q.trim() || p.name.toLowerCase().includes(q.toLowerCase()));
  const toggle = (id) => setSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(4,6,11,0.62)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(2px)' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 460, maxHeight: '84%', display: 'flex', flexDirection: 'column', background: T.surface, borderRadius: 14, border: `1px solid ${T.hair2}`, overflow: 'hidden', boxShadow: '0 24px 70px rgba(0,0,0,0.55)' }}>
        <div style={{ padding: '16px 18px', borderBottom: `1px solid ${T.hair}`, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ width: 9, height: 9, borderRadius: 3, background: SQUAD_TINT[squad] }} />
          <div style={{ flex: 1 }}>
            <div className="eyebrow" style={{ color: T.accent }}>Add players to</div>
            <div style={{ fontFamily: T.display, fontWeight: 700, fontSize: 18, marginTop: 2 }}>{squad}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: T.faint, cursor: 'pointer', display: 'flex', padding: 4 }}><Icon name="close" size={18} /></button>
        </div>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.hair}` }}><Search value={q} onChange={setQ} placeholder="Search players…" /></div>
        <div className="bs-scroll" style={{ overflow: 'auto', flex: 1 }}>
          {list.map(p => {
            const on = sel.has(p.id);
            return (
              <label key={p.id} className="pb-hair-b" style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 16px', borderBottom: `1px solid ${T.hair}`, cursor: 'pointer', background: on ? 'rgba(22,199,132,0.06)' : 'transparent' }}>
                <input type="checkbox" checked={on} onChange={() => toggle(p.id)} style={{ accentColor: T.accent, width: 15, height: 15 }} />
                <Dot status={availOf(p)} />
                <Avatar p={p} size={26} />
                <span style={{ flex: 1, fontSize: 13.5, fontWeight: 500 }}>{p.name}</span>
                <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.faint, background: T.surface2, padding: '2px 7px', borderRadius: 4 }}>{squadOf(p)}</span>
                <RoleChips roles={p.roles} muted />
              </label>
            );
          })}
          {list.length === 0 && <Empty>No players to add.</Empty>}
        </div>
        <div style={{ padding: 14, borderTop: `1px solid ${T.hair}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: T.mono, fontSize: 12, color: sel.size ? T.accent : T.faint }}>{sel.size} selected</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 9 }}>
            <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" sm icon="plus" disabled={!sel.size} onClick={() => { onAdd([...sel]); onClose(); }}>Add {sel.size || ''} to {squad}</Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

function TeamsScreen({ onNav }) {
  const T = window.BST;
  useAvailVersion();
  const [over, setOver] = React.useState(null);
  const [addTo, setAddTo] = React.useState(null);
  const dragId = React.useRef(null);
  const members = (sq) => BS_PLAYERS.filter(p => squadOf(p) === sq)
    .sort((a, b) => (BS_AVAIL[availOf(a)].rank - BS_AVAIL[availOf(b)].rank) || a.name.localeCompare(b.name));

  return (
    <BSShell active="teams" title="Squads" subtitle="Selection pools — a player's squad drives who's suggested first when picking. Drag to move, or bulk-add." onNav={onNav}
      actions={<Btn variant="ghost" sm icon="plus">New squad</Btn>}
      overlay={addTo && <BulkAddModal squad={addTo} onClose={() => setAddTo(null)} onAdd={(ids) => ids.forEach(id => setSquadOverride(id, addTo))} />}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, color: T.faint, fontSize: 12.5 }}>
          <span><b className="num" style={{ color: T.text }}>{BS_PLAYERS.length}</b> players</span>
          <span><b className="num" style={{ color: T.text }}>{BS_SQUADS.length}</b> squads</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 14 }}>
            {BS_AVAIL_ORDER.map(s => <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: T.faint }}><Dot status={s} /> {BS_AVAIL[s].label.toLowerCase()}</span>)}
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${BS_SQUADS.length}, 1fr)`, gap: 12, flex: 1, minHeight: 0 }}>
          {BS_SQUADS.map(sq => {
            const m = members(sq);
            const hasKeeper = m.some(p => p.roles.includes('WKT'));
            const nAvail = m.filter(p => availOf(p) === 'AVAILABLE').length;
            const isOver = over === sq;
            return (
              <div key={sq} onDragOver={e => { e.preventDefault(); setOver(sq); }} onDragLeave={() => setOver(o => o === sq ? null : o)}
                onDrop={() => { if (dragId.current) setSquadOverride(dragId.current, sq); dragId.current = null; setOver(null); }}
                className="pb-card" style={{ display: 'flex', flexDirection: 'column', minHeight: 0,
                  background: isOver ? 'rgba(22,199,132,0.05)' : T.surface, border: `1px solid ${isOver ? T.accent : T.hair}`, transition: 'all .12s' }}>
                <div className="pb-hair-b" style={{ padding: '11px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 3, background: SQUAD_TINT[sq] }} />
                    <span style={{ fontFamily: T.display, fontWeight: 700, fontSize: 14.5 }}>{sq}</span>
                    <span className="num" style={{ marginLeft: 'auto', fontSize: 12, color: T.faint }}>{m.length}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                    <span className="eyebrow">{SQUAD_GRADE[sq]}</span>
                    {m.length > 0 && !hasKeeper && <span style={{ fontSize: 10, color: T.amber }}>· no keeper</span>}
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: T.accent }}><Dot status="AVAILABLE" /> <b className="num" style={{ fontWeight: 600 }}>{nAvail}</b></span>
                  </div>
                </div>
                <div className="bs-scroll" style={{ overflow: 'auto', flex: 1, padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {m.map(p => <SquadCard key={p.id} p={p} onDragStart={() => dragId.current = p.id} />)}
                  {m.length === 0 && <div style={{ padding: '20px 10px', textAlign: 'center', color: T.faintest, fontSize: 11.5, border: `1.5px dashed ${T.hair2}`, borderRadius: 8 }}>Empty — drag or add players</div>}
                </div>
                <div className="pb-hair-t" style={{ padding: 8 }}>
                  <button onClick={() => setAddTo(sq)} style={{ width: '100%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    background: 'transparent', border: `1px dashed ${T.hair2}`, color: T.faint, borderRadius: 8, padding: '7px 0', fontFamily: T.body, fontSize: 12, cursor: 'pointer' }}
                    onMouseEnter={e => { e.currentTarget.style.color = T.accent; e.currentTarget.style.borderColor = 'rgba(22,199,132,0.4)'; }}
                    onMouseLeave={e => { e.currentTarget.style.color = T.faint; e.currentTarget.style.borderColor = T.hair2; }}>
                    <Icon name="plus" size={14} /> Add players
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </BSShell>
  );
}

Object.assign(window, { TeamsScreen });
