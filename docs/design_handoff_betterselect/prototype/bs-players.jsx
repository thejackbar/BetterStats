/* bs-players.jsx — Players directory + profile. Cleaner than the old modal:
   a list with rich at-a-glance columns, a profile that pairs management fields
   with a selection snapshot, bulk actions, and two layouts (split + full page). */

const ROLE_OPTS = ['Batter', 'Bowler', 'All Rounder', 'Wicketkeeper', 'Wicketkeeper-Batter'];
const BAT_HANDS = [['RIGHT', 'Right handed'], ['LEFT', 'Left handed']];
// Bowling action + type rolled into one field.
const BOWLING_OPTS = [['NONE', '—'], ['RIGHT_FAST', 'Right-arm fast'], ['RIGHT_FAST_MEDIUM', 'Right-arm fast-medium'],
  ['RIGHT_MEDIUM', 'Right-arm medium'], ['RIGHT_OFF_SPIN', 'Off spin'], ['RIGHT_LEG_SPIN', 'Leg spin'],
  ['LEFT_FAST', 'Left-arm fast'], ['LEFT_MEDIUM', 'Left-arm medium'], ['LEFT_ORTHODOX', 'Left-arm orthodox'], ['LEFT_WRIST', 'Left-arm wrist spin']];
const BOWLING_LABEL = Object.fromEntries(BOWLING_OPTS);
const PL_OVERSEAS = { p7: 'England' };
const PL_NOCONTACT = new Set(['p16', 'p22', 'p23']);

function deriveBowling(p) {
  if (!p.bowl || p.bowl === 'NONE') return 'NONE';
  const left = p.bat === 'LHB' || p.bowl === 'LEFT_ARM_ORTHODOX';
  switch (p.bowl) {
    case 'FAST': return left ? 'LEFT_FAST' : 'RIGHT_FAST';
    case 'FAST_MEDIUM': return left ? 'LEFT_FAST' : 'RIGHT_FAST_MEDIUM';
    case 'MEDIUM': return left ? 'LEFT_MEDIUM' : 'RIGHT_MEDIUM';
    case 'OFF_SPIN': return 'RIGHT_OFF_SPIN';
    case 'LEG_SPIN': return 'RIGHT_LEG_SPIN';
    case 'LEFT_ARM_ORTHODOX': return 'LEFT_ORTHODOX';
    default: return 'NONE';
  }
}
// Deterministic mock career snapshot: last 5 innings, last 5 bowling figures, catches.
function plStats(p) {
  const idx = BS_PLAYERS.indexOf(p);
  const bat = p.form || Array.from({ length: 5 }).map((_, i) => (idx * 13 + i * 29) % 84);
  const bowls = deriveBowling(p) !== 'NONE';
  const bowl = bowls ? Array.from({ length: 5 }).map((_, i) => `${(idx + i) % 4}/${12 + ((idx * 7 + i * 9) % 38)}`) : null;
  const catches = (idx * 3 + 2) % 9;
  return { bat, bowl, catches };
}

function roleLabel(roles) {
  const s = new Set(roles);
  if (s.has('WKT') && s.has('BAT')) return 'Wicketkeeper-Batter';
  if (s.has('WKT')) return 'Wicketkeeper';
  if (s.has('ALL')) return 'All Rounder';
  if (s.has('BWL')) return 'Bowler';
  return 'Batter';
}
function plWeekAvail(p, i) {
  return BS_DATES.map((d, j) => j === 0 ? availOf(p) : ['AVAILABLE', 'NO_RESPONSE', 'AVAILABLE', 'MAYBE'][(i + j) % 4]);
}
function buildProfile(p) {
  const [first, last] = p.name.split(' ');
  return {
    role: roleLabel(p.roles),
    gender: 'Male',
    batting_hand: p.bat === 'LHB' ? 'LEFT' : 'RIGHT',
    bowling: deriveBowling(p),
    is_opening_batsman: !!p.captainPref || ['p2', 'p16', 'p15'].includes(p.id),
    overseas: PL_OVERSEAS[p.id] || '',
    email: PL_NOCONTACT.has(p.id) ? '' : `${first}.${last}@gmail.com`.toLowerCase(),
    phone: PL_NOCONTACT.has(p.id) ? '' : '04' + (10 + p.id.charCodeAt(1)) + ' ' + (100 + p.id.length) + ' ' + (200 + p.id.charCodeAt(1)),
    status: p.dormant ? 'inactive' : 'active',
    is_player: true,
    playhq_id: `4215a8fd-bfcf-4f2c-9234-1ab3999${p.id}`,
    lastPicked: p.dormant ? null : 'R8 · vs Cottesloe',
  };
}

/* ── List row ───────────────────────────────────────────────────────────── */
function PlayerRow({ p, prof, active, selected, onSelect, onOpenProfile, onToggleSel, wide }) {
  const T = window.BST;
  const av = availOf(p);
  const inactive = prof.status === 'inactive';
  return (
    <div onClick={onSelect} className="pb-hair-b" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      borderBottom: `1px solid ${T.hair}`, cursor: 'pointer', background: active ? 'rgba(22,199,132,0.07)' : 'transparent', opacity: inactive ? 0.6 : 1 }}>
      <input type="checkbox" checked={selected} onClick={e => e.stopPropagation()} onChange={onToggleSel} style={{ accentColor: T.accent, width: 15, height: 15 }} />
      <span onClick={e => { e.stopPropagation(); onOpenProfile && onOpenProfile(); }} title="Open profile"
        style={{ display: 'inline-flex', cursor: 'pointer', borderRadius: '50%', boxShadow: `0 0 0 2px ${active ? T.accent : 'transparent'}` }}>
        <Avatar p={p} size={32} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          {p.captainPref && <Tag>C</Tag>}
          {prof.overseas && <span title={`Overseas — ${prof.overseas}`} style={{ fontFamily: T.mono, fontSize: 8.5, color: T.amber, background: 'rgba(245,181,66,0.12)', padding: '1px 5px', borderRadius: 4 }}>OS</span>}
        </div>
        <div style={{ fontSize: 11, color: T.faint, marginTop: 1 }}>{p.bat}{prof.bowling !== 'NONE' ? ` · ${BOWLING_LABEL[prof.bowling]}` : ''}</div>
      </div>
      {wide && <span style={{ width: 116, fontSize: 12, color: T.dim }}>{prof.role}</span>}
      {wide && <span style={{ width: 120 }}><span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.dim, background: T.surface2, border: `1px solid ${T.hair}`, padding: '3px 9px', borderRadius: 999 }}>{squadOf(p)}</span></span>}
      {!wide && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.faint, background: T.surface2, padding: '2px 6px', borderRadius: 4 }}>{squadOf(p)}</span>}
      {!wide && <RoleChips roles={p.roles} muted />}
      <span style={{ width: wide ? 120 : 'auto', display: 'flex', alignItems: 'center', gap: 6, justifyContent: wide ? 'flex-start' : 'flex-end' }}>
        <Dot status={av} />{wide && <span style={{ fontSize: 12, color: BS_AVAIL[av].text }}>{BS_AVAIL[av].label}</span>}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, width: wide ? 100 : 'auto', justifyContent: 'flex-end' }}>
        <span title={prof.email ? 'Contact on file' : 'No contact'} style={{ color: prof.email ? T.dim : T.faintest, display: 'flex' }}><Icon name={prof.email ? 'check' : 'close'} size={13} /></span>
        {inactive
          ? <span style={{ fontFamily: T.mono, fontSize: 9, color: T.faint, border: `1px solid ${T.hair2}`, padding: '1px 5px', borderRadius: 4 }}>INACTIVE</span>
          : <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.accent }} title="Active" />}
      </span>
    </div>
  );
}

/* ── Field controls ─────────────────────────────────────────────────────── */
function Field({ label, children, half }) {
  const T = window.BST;
  return (
    <div style={{ flex: half ? '1 1 calc(50% - 6px)' : '1 1 100%', minWidth: 0 }}>
      <label style={{ display: 'block', fontSize: 11.5, color: T.faint, marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );
}
function PSelect({ value, onChange, options }) {
  const T = window.BST;
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{ width: '100%', background: T.surface2, color: T.text,
      border: `1px solid ${T.hair2}`, borderRadius: 8, padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: 13.5, cursor: 'pointer' }}>
      {options.map(o => Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o} value={o}>{o}</option>)}
    </select>
  );
}
function PInput({ value, onChange, placeholder, type }) {
  const T = window.BST;
  return <input type={type || 'text'} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
    style={{ width: '100%', background: T.surface2, color: T.text, border: `1px solid ${T.hair2}`, borderRadius: 8, padding: '8px 10px',
      fontFamily: 'var(--font-body)', fontSize: 13.5, outline: 'none' }} />;
}
function PToggle({ on, onChange, label }) {
  const T = window.BST;
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', padding: '8px 0' }}>
      <span onClick={() => onChange(!on)} style={{ width: 38, height: 22, borderRadius: 999, background: on ? T.accent : T.surface2,
        border: `1px solid ${on ? T.accent : T.hair2}`, position: 'relative', transition: 'all .15s', flexShrink: 0 }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 18 : 2, width: 16, height: 16, borderRadius: '50%', background: on ? '#04130c' : T.faint, transition: 'all .15s' }} />
      </span>
      <span style={{ fontSize: 13.5, color: T.text }}>{label}</span>
    </label>
  );
}

/* ── Profile view (selection snapshot + editable management fields) ─────── */
function Profile({ p, form, setForm, onBack, dirty, onSave, saved }) {
  const T = window.BST;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const weeks = plWeekAvail(p, BS_PLAYERS.indexOf(p));

  return (
    <div className="bs-scroll" style={{ overflow: 'auto', height: '100%' }}>
      {/* header */}
      <div style={{ padding: '18px 20px', borderBottom: `1px solid ${T.hair}`,
        background: 'linear-gradient(140deg, rgba(22,199,132,0.08), transparent 55%)' }}>
        {onBack && <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: T.faint, cursor: 'pointer', fontSize: 12.5, marginBottom: 12, padding: 0 }}><Icon name="back" size={14} /> All players</button>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Avatar p={p} size={56} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <h2 style={{ margin: 0, fontFamily: T.display, fontWeight: 800, fontSize: 24 }}>{p.name}</h2>
              {p.captainPref && <Tag>C</Tag>}
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.accent, background: 'rgba(22,199,132,0.12)', border: '1px solid rgba(22,199,132,0.3)', padding: '2px 9px', borderRadius: 999 }}>{squadOf(p)} squad</span>
              {form.overseas && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.amber, background: 'rgba(245,181,66,0.12)', padding: '2px 7px', borderRadius: 999 }}>Overseas · {form.overseas}</span>}
              {form.status === 'inactive' && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.faint, border: `1px solid ${T.hair2}`, padding: '2px 7px', borderRadius: 999 }}>Inactive</span>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6, color: T.dim, fontSize: 13 }}>
              <span>{form.role}</span><span style={{ color: T.faintest }}>·</span>
              <span>{BAT_HANDS.find(b => b[0] === form.batting_hand)?.[1]}</span>
              {form.bowling !== 'NONE' && <><span style={{ color: T.faintest }}>·</span><span>{BOWLING_LABEL[form.bowling]}</span></>}
              {form.is_opening_batsman && <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.accent, background: 'rgba(22,199,132,0.1)', padding: '1px 6px', borderRadius: 4 }}>OPENER</span>}
            </div>
          </div>
          <Btn variant="primary" sm icon={saved ? 'check' : undefined} disabled={!dirty} onClick={onSave}>{saved ? 'Saved' : 'Save changes'}</Btn>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        {/* Selection snapshot */}
        <div style={{ padding: '18px 20px', borderRight: `1px solid ${T.hair}` }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>Selection snapshot</div>

          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, color: T.faint, marginBottom: 8 }}>Availability — next 4 weeks</div>
            <div style={{ display: 'flex', gap: 8 }}>
              {BS_DATES.map((d, j) => (
                <div key={d.date} style={{ flex: 1, textAlign: 'center', padding: '9px 4px', borderRadius: 8,
                  background: j === 0 ? 'rgba(22,199,132,0.05)' : T.surface2, border: `1px solid ${j === 0 ? 'rgba(22,199,132,0.25)' : T.hair}` }}>
                  <div style={{ fontFamily: T.mono, fontSize: 9.5, color: T.faint }}>{d.label.replace('Sat ', '')}</div>
                  <div style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }}><Dot status={weeks[j]} size={11} /></div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, color: T.faint, marginBottom: 8 }}>Squad &amp; eligibility</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.accent, background: 'rgba(22,199,132,0.12)', border: '1px solid rgba(22,199,132,0.3)', padding: '4px 11px', borderRadius: 999 }}>{squadOf(p)}</span>
              <span style={{ fontSize: 11.5, color: T.faintest }}>assigned · suggested first for {squadOf(p)} fixtures</span>
            </div>
          </div>

          {(() => {
            const st = plStats(p);
            return (
              <div style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 12, color: T.faint, marginBottom: 8 }}>Recent form</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.faint, width: 56 }}>BATTING</span>
                    <div style={{ display: 'flex', gap: 5 }}>
                      {st.bat.map((s, i) => <span key={i} className="num" style={{ minWidth: 28, textAlign: 'center', padding: '5px 0', borderRadius: 6, fontSize: 12.5, fontWeight: 600,
                        background: s >= 50 ? 'rgba(22,199,132,0.14)' : T.surface2, color: s >= 50 ? T.accent : s === 0 ? T.red : T.dim, border: `1px solid ${T.hair}` }}>{s}</span>)}
                    </div>
                  </div>
                  {st.bowl && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.faint, width: 56 }}>BOWLING</span>
                      <div style={{ display: 'flex', gap: 5 }}>
                        {st.bowl.map((f, i) => { const w = parseInt(f); return <span key={i} className="num" style={{ minWidth: 38, textAlign: 'center', padding: '5px 0', borderRadius: 6, fontSize: 12.5, fontWeight: 600,
                          background: w >= 3 ? 'rgba(59,130,246,0.14)' : T.surface2, color: w >= 3 ? '#5b9bf5' : T.dim, border: `1px solid ${T.hair}` }}>{f}</span>; })}
                      </div>
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.faint, width: 56 }}>CATCHES</span>
                    <span className="num" style={{ fontFamily: T.display, fontWeight: 700, fontSize: 16, color: T.text }}>{st.catches}</span>
                    <span style={{ fontSize: 11.5, color: T.faintest }}>this season</span>
                  </div>
                </div>
              </div>
            );
          })()}

          <div style={{ display: 'flex', gap: 22 }}>
            <div>
              <div style={{ fontSize: 12, color: T.faint, marginBottom: 4 }}>Last picked</div>
              <div style={{ fontSize: 13.5, color: form.lastPicked ? T.text : T.faint }}>{form.lastPicked || 'Not recently'}</div>
            </div>
          </div>
        </div>

        {/* Management fields — inline editable */}
        <div style={{ padding: '18px 20px' }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>Details</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <Field label="Squad (selection pool)" half><PSelect value={squadOf(p)} onChange={v => setSquadOverride(p.id, v)} options={BS_SQUADS} /></Field>
            <Field label="Role" half><PSelect value={form.role} onChange={v => set('role', v)} options={ROLE_OPTS} /></Field>
            <Field label="Batting hand" half><PSelect value={form.batting_hand} onChange={v => set('batting_hand', v)} options={BAT_HANDS} /></Field>
            <Field label="Bowling" half><PSelect value={form.bowling} onChange={v => set('bowling', v)} options={BOWLING_OPTS} /></Field>
            <Field label="Gender" half><PSelect value={form.gender} onChange={v => set('gender', v)} options={[['Male', 'Male'], ['Female', 'Female']]} /></Field>
            <Field label="Email" half><PInput value={form.email} onChange={v => set('email', v)} type="email" placeholder="—" /></Field>
            <Field label="Phone" half><PInput value={form.phone} onChange={v => set('phone', v)} placeholder="—" /></Field>
          </div>
          <div style={{ marginTop: 6, borderTop: `1px solid ${T.hair}`, paddingTop: 6 }}>
            <PToggle on={form.is_opening_batsman} onChange={v => set('is_opening_batsman', v)} label="Opening batsman" />
            <PToggle on={!!form.overseas} onChange={v => set('overseas', v ? 'England' : '')} label="Overseas player" />
            {form.overseas && <div style={{ paddingLeft: 47, paddingBottom: 6 }}><PInput value={form.overseas} onChange={v => set('overseas', v)} placeholder="Country" /></div>}
            <PToggle on={form.status === 'inactive'} onChange={v => set('status', v ? 'inactive' : 'active')} label="Inactive — hide from availability & selection" />
          </div>
          {/* tucked away */}
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.hair}`, display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center' }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.faintest }}>PlayHQ ID: {form.playhq_id.slice(0, 18)}…</span>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: T.faintest, cursor: 'pointer' }}>
              <input type="checkbox" checked={!form.is_player} onChange={e => set('is_player', !e.target.checked)} style={{ accentColor: T.faint }} /> Non-player (coach/scorer)
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── List panel (search, filters, bulk) ─────────────────────────────────── */
function PlayerList({ wide, selectedId, onSelect, onOpenProfile, profileOf }) {
  const T = window.BST;
  const [q, setQ] = React.useState('');
  const [role, setRole] = React.useState(null);
  const [inactiveOverrides] = React.useState(() => ({}));
  const [showInactive, setShowInactive] = React.useState(false);
  const [sel, setSel] = React.useState(() => new Set());
  const [bulkSquad, setBulkSquad] = React.useState('1st XI');

  const roleChips = [['Batter', 'BAT'], ['Bowler', 'BWL'], ['All Rounder', 'ALL'], ['Wicketkeeper', 'WKT']];
  const list = BS_PLAYERS.filter(p => {
    const prof = profileOf(p);
    if (!showInactive && prof.status === 'inactive') return false;
    if (q.trim() && !p.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (role && roleLabel(p.roles) !== role) return false;
    return true;
  });
  const toggleSel = (id) => setSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="pb-card" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: T.surface, height: '100%' }}>
      <div className="pb-hair-b" style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <Search value={q} onChange={setQ} placeholder="Search players…" width={wide ? 240 : 200} />
          <div style={{ display: 'flex', gap: 6 }}>
            {roleChips.map(([label]) => <Chip key={label} label={label.replace(' Rounder', '-R')} active={role === label} onClick={() => setRole(role === label ? null : label)} />)}
          </div>
          <Chip label="Show inactive" active={showInactive} onClick={() => setShowInactive(v => !v)} />
          <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.faint }}>{list.length} players</span>
        </div>
        {wide && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 0 0 2px' }}>
            <span style={{ width: 15 }} /><span style={{ width: 32 }} />
            <span className="eyebrow" style={{ flex: 1 }}>Player</span>
            <span className="eyebrow" style={{ width: 116 }}>Role</span>
            <span className="eyebrow" style={{ width: 120 }}>Squads</span>
            <span className="eyebrow" style={{ width: 120 }}>This weekend</span>
            <span className="eyebrow" style={{ width: 100, textAlign: 'right' }}>Contact · status</span>
          </div>
        )}
      </div>
      <div className="bs-scroll" style={{ overflow: 'auto', flex: 1 }}>
        {list.map(p => (
          <PlayerRow key={p.id} p={p} prof={profileOf(p)} wide={wide}
            active={p.id === selectedId} selected={sel.has(p.id)}
            onSelect={() => onSelect(p.id)} onOpenProfile={() => onOpenProfile(p.id)} onToggleSel={() => toggleSel(p.id)} />
        ))}
      </div>
      {sel.size > 0 && (
        <div className="pb-hair-t" style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12, background: 'rgba(22,199,132,0.05)' }}>
          <span style={{ fontFamily: T.mono, fontSize: 12, color: T.accent }}>{sel.size} selected</span>
          <span style={{ fontSize: 12.5, color: T.dim }}>set squad</span>
          <PSelectInline value={bulkSquad} onChange={setBulkSquad} options={['1st XI', '2nd XI', 'Veterans']} />
          <Btn variant="soft" sm onClick={() => setSel(new Set())}>Apply</Btn>
          <Btn variant="ghost" sm onClick={() => setSel(new Set())}>Mark inactive</Btn>
          <Btn variant="ghost" sm onClick={() => setSel(new Set())}>Clear</Btn>
        </div>
      )}
    </div>
  );
}
function PSelectInline({ value, onChange, options }) {
  const T = window.BST;
  return <select value={value} onChange={e => onChange(e.target.value)} style={{ background: T.surface2, color: T.text, border: `1px solid ${T.hair2}`,
    borderRadius: 8, padding: '6px 9px', fontFamily: 'var(--font-body)', fontSize: 12.5, cursor: 'pointer' }}>{options.map(o => <option key={o} value={o}>{o}</option>)}</select>;
}

/* ── Screen (layout: 'split' | 'page') ──────────────────────────────────── */
function PlayersScreen({ onNav, layout = 'split', subtitle }) {
  const T = window.BST;
  useAvailVersion();
  const [forms, setForms] = React.useState({});
  const profileOf = (p) => forms[p.id] || buildProfile(p);
  const setFormFor = (id) => (updater) => setForms(fs => ({ ...fs, [id]: updater(fs[id] || buildProfile(BS_PLAYERS.find(x => x.id === id))) }));
  const [savedId, setSavedId] = React.useState(null);
  const [dirtyIds, setDirtyIds] = React.useState(() => new Set());

  // split: a player is always selected. page: null = list, id = profile.
  const [selId, setSelId] = React.useState(layout === 'split' ? 'p1' : null);

  const wrapSetForm = (id) => (updater) => { setFormFor(id)(updater); setDirtyIds(s => new Set(s).add(id)); setSavedId(null); };
  const save = (id) => { setDirtyIds(s => { const n = new Set(s); n.delete(id); return n; }); setSavedId(id); setTimeout(() => setSavedId(c => c === id ? null : c), 1800); };

  const selectedPlayer = selId && BS_PLAYERS.find(p => p.id === selId);

  let body;
  if (layout === 'split') {
    body = (
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(420px, 1fr) 1.35fr', gap: 16, height: '100%' }}>
        <PlayerList wide={false} selectedId={selId} onSelect={setSelId} onOpenProfile={setSelId} profileOf={profileOf} />
        <div className="pb-card" style={{ background: T.surface, minHeight: 0, overflow: 'hidden' }}>
          {selectedPlayer
            ? <Profile p={selectedPlayer} form={profileOf(selectedPlayer)} setForm={wrapSetForm(selId)} dirty={dirtyIds.has(selId)} saved={savedId === selId} onSave={() => save(selId)} />
            : <Empty>Select a player</Empty>}
        </div>
      </div>
    );
  } else {
    body = selectedPlayer ? (
      <div className="pb-card" style={{ background: T.surface, height: '100%', minHeight: 0, overflow: 'hidden' }}>
        <Profile p={selectedPlayer} form={profileOf(selectedPlayer)} setForm={wrapSetForm(selId)} dirty={dirtyIds.has(selId)} saved={savedId === selId} onSave={() => save(selId)} onBack={() => setSelId(null)} />
      </div>
    ) : (
      <PlayerList wide={true} selectedId={null} onSelect={setSelId} onOpenProfile={setSelId} profileOf={profileOf} />
    );
  }

  return (
    <BSShell active="players" title="Players" subtitle={subtitle || "Your club's roster — manage details and read availability at a glance"} onNav={onNav}
      actions={<Btn variant="ghost" sm icon="plus">Add player</Btn>}>
      {body}
    </BSShell>
  );
}

Object.assign(window, { PlayersScreen, buildProfile });
