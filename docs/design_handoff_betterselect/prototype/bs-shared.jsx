/* bs-shared.jsx — shared UI kit for the BetterSelect redesign.
   The cleaned module chrome + small presentational atoms. Everything reads
   from the pb-* CSS variables so it stays on-theme. */

const T = {
  bg: 'var(--pb-bg)', surface: 'var(--pb-surface)', surface2: 'var(--pb-surface2)',
  hair: 'var(--pb-hairline)', hair2: 'var(--pb-hairline2)', text: 'var(--pb-text)',
  dim: 'var(--pb-dim)', faint: 'var(--pb-faint)', faintest: 'var(--pb-faintest)',
  accent: 'var(--pb-accent)', red: 'var(--pb-red)', amber: 'var(--pb-amber)',
  mono: 'var(--font-mono)', display: 'var(--font-display)',
};

/* ── Icons — simple geometric line glyphs ───────────────────────────────── */
function Icon({ name, size = 18, stroke = 1.6, style }) {
  const c = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: stroke, strokeLinecap: 'round', strokeLinejoin: 'round', style };
  const P = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    fixtures: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9h18M8 3v3M16 3v3" /></>,
    teams: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9" /></>,
    player: <><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></>,
    availability: <><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 4.5-5" /></>,
    selection: <><path d="M12 3l2.4 5.3L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-.7z" /></>,
    ladders: <><path d="M5 21V9M12 21V4M19 21v-8" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>,
    filter: <><path d="M4 6h16M7 12h10M10 18h4" /></>,
    close: <><path d="M6 6l12 12M18 6L6 18" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    minus: <><path d="M5 12h14" /></>,
    grip: <><circle cx="9" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="18" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="18" r="1.1" fill="currentColor" stroke="none" /></>,
    chevron: <><path d="M9 6l6 6-6 6" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    check: <><path d="M5 12.5l4.5 4.5L19 7" /></>,
    share: <><circle cx="6" cy="12" r="2.4" /><circle cx="17" cy="6" r="2.4" /><circle cx="17" cy="18" r="2.4" /><path d="M8.1 11l6.8-3.9M8.1 13l6.8 3.9" /></>,
    bolt: <><path d="M13 3L5 13h6l-1 8 8-10h-6z" /></>,
    back: <><path d="M19 12H5M11 6l-6 6 6 6" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  };
  return <svg {...c}>{P[name] || null}</svg>;
}

/* ── Player avatar (initials, no photos in the mock) ────────────────────── */
function Avatar({ p, size = 30 }) {
  const initials = p.name.split(/\s+/).slice(0, 2).map(s => s[0]).join('').toUpperCase();
  const role = p.roles[0];
  const ring = role === 'WKT' ? 'rgba(245,181,66,0.5)' : 'rgba(255,255,255,0.06)';
  return (
    <span style={{
      width: size, height: size, minWidth: size, borderRadius: '50%',
      background: T.surface2, border: `1.5px solid ${ring}`,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: T.mono, fontSize: size * 0.34, fontWeight: 600, color: T.dim,
    }}>{initials}</span>
  );
}

/* ── Availability dot + label ───────────────────────────────────────────── */
function Dot({ status, size = 9, glow }) {
  const a = BS_AVAIL[status] || BS_AVAIL.NO_RESPONSE;
  const ring = status === 'NO_RESPONSE'
    ? { background: 'transparent', border: `1.5px solid ${a.dot}` }
    : { background: a.dot, boxShadow: glow ? `0 0 0 3px ${a.tint}` : 'none' };
  return <span style={{ width: size, height: size, minWidth: size, borderRadius: '50%', display: 'inline-block', ...ring }} />;
}

function AvailLabel({ status, size = 12 }) {
  const a = BS_AVAIL[status] || BS_AVAIL.NO_RESPONSE;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: a.text, fontSize: size, fontWeight: 500 }}>
      <Dot status={status} /> {a.label}
    </span>
  );
}

/* ── Role chips — small, calm, sentence-ish ─────────────────────────────── */
function RoleChips({ roles, muted }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      {roles.map(r => {
        const role = BS_ROLES[r];
        const isWk = r === 'WKT';
        return (
          <span key={r} style={{
            fontFamily: T.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.04em',
            padding: '2px 5px', borderRadius: 4,
            color: isWk ? T.amber : muted ? T.faint : T.dim,
            background: isWk ? 'rgba(245,181,66,0.10)' : 'rgba(255,255,255,0.04)',
          }}>{role.short}</span>
        );
      })}
    </span>
  );
}

/* ── Availability summary bar — read the squad's state at a glance ──────── */
function AvailSummary({ players, compact, hideTotal }) {
  const t = bsTally(players);
  const total = players.length;
  const segs = BS_AVAIL_ORDER.map(s => ({ s, n: t[s], a: BS_AVAIL[s] })).filter(x => x.n > 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 6 : 8 }}>
      <div style={{ display: 'flex', height: compact ? 6 : 8, borderRadius: 999, overflow: 'hidden', background: T.surface2 }}>
        {segs.map(({ s, n, a }) => (
          <div key={s} title={`${n} ${a.label.toLowerCase()}`} style={{
            flex: n, background: s === 'NO_RESPONSE' ? T.faintest : a.dot, opacity: s === 'NO_RESPONSE' ? 0.5 : 1,
          }} />
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: compact ? 10 : 14 }}>
        {BS_AVAIL_ORDER.map(s => (
          <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: compact ? 11 : 12, color: T.dim }}>
            <Dot status={s} /> <b className="num" style={{ color: T.text, fontWeight: 600 }}>{t[s]}</b>
            <span style={{ color: T.faint }}>{BS_AVAIL[s].label.toLowerCase()}</span>
          </span>
        ))}
        {!hideTotal && <span style={{ marginLeft: 'auto', fontSize: compact ? 11 : 12, color: T.faint }} className="num">{total} in squad</span>}
      </div>
    </div>
  );
}

/* ── Buttons ────────────────────────────────────────────────────────────── */
function Btn({ children, variant = 'ghost', sm, onClick, disabled, icon, style, title }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
    fontFamily: T.display, fontWeight: 600, fontSize: sm ? 12.5 : 13.5,
    padding: sm ? '6px 11px' : '9px 15px', borderRadius: 8, cursor: disabled ? 'default' : 'pointer',
    border: '1px solid transparent', transition: 'all .14s', whiteSpace: 'nowrap',
    opacity: disabled ? 0.45 : 1, lineHeight: 1,
  };
  const variants = {
    primary: { background: T.accent, color: '#04130c', borderColor: T.accent },
    ghost:   { background: 'transparent', color: T.dim, borderColor: T.hair2 },
    soft:    { background: T.surface2, color: T.text, borderColor: T.hair },
    danger:  { background: 'transparent', color: T.red, borderColor: 'rgba(239,91,91,0.3)' },
  };
  return (
    <button title={title} onClick={disabled ? undefined : onClick}
      onMouseEnter={e => { if (!disabled && variant === 'ghost') e.currentTarget.style.color = T.text; }}
      onMouseLeave={e => { if (!disabled && variant === 'ghost') e.currentTarget.style.color = T.dim; }}
      style={{ ...base, ...variants[variant], ...style }}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}
    </button>
  );
}

/* ── Segmented control (replaces fiddly selects) ────────────────────────── */
function Segmented({ options, value, onChange, sm }) {
  return (
    <div style={{ display: 'inline-flex', padding: 3, gap: 2, background: T.surface2, borderRadius: 9, border: `1px solid ${T.hair}` }}>
      {options.map(o => {
        const active = o.value === value;
        return (
          <button key={o.value} onClick={() => onChange(o.value)} style={{
            border: 'none', cursor: 'pointer', borderRadius: 6,
            padding: sm ? '4px 10px' : '6px 13px', fontSize: sm ? 12 : 13, fontWeight: 600, fontFamily: T.display,
            background: active ? 'rgba(22,199,132,0.14)' : 'transparent',
            color: active ? T.accent : T.faint, transition: 'all .14s',
          }}>{o.label}</button>
        );
      })}
    </div>
  );
}

/* ── Search input ───────────────────────────────────────────────────────── */
function Search({ value, onChange, placeholder, width }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.surface2, border: `1px solid ${T.hair}`,
      borderRadius: 8, padding: '0 11px', height: 38, width: width || 'auto', color: T.faint }}>
      <Icon name="search" size={16} />
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder || 'Search…'}
        style={{ background: 'transparent', border: 'none', outline: 'none', color: T.text, fontFamily: T.body,
          fontSize: 14, width: '100%' }} />
    </div>
  );
}

/* ── Filter chip (toggleable, replaces checkbox walls) ──────────────────── */
function Chip({ label, active, onClick, dot }) {
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
      padding: '6px 11px', borderRadius: 999, fontSize: 12.5, fontWeight: 500, fontFamily: T.body,
      border: `1px solid ${active ? 'rgba(22,199,132,0.4)' : T.hair2}`,
      background: active ? 'rgba(22,199,132,0.12)' : 'transparent',
      color: active ? T.accent : T.dim, transition: 'all .14s', whiteSpace: 'nowrap',
    }}>
      {dot && <span style={{ width: 7, height: 7, borderRadius: '50%', background: dot }} />}
      {label}
    </button>
  );
}

/* ── Shared availability-override store (lets selection boards edit avail
   live without a backend) ───────────────────────────────────────────────── */
const _availOverrides = {};
const _availListeners = new Set();
function setAvailOverride(id, status) { _availOverrides[id] = status; _availListeners.forEach(l => l()); }
function availOf(p) { return _availOverrides[p.id] || p.avail; }
function useAvailVersion() {
  const [, force] = React.useState(0);
  React.useEffect(() => { const l = () => force(v => v + 1); _availListeners.add(l); return () => _availListeners.delete(l); }, []);
}

/* ── Shared squad-assignment store (which selection pool a player sits in) ── */
const _squadOverrides = {};
function setSquadOverride(id, squad) { _squadOverrides[id] = squad; _availListeners.forEach(l => l()); }
function squadOf(p) { return _squadOverrides[p.id] || p.squads[0]; }

/* ── Quick-update availability modal ────────────────────────────────────── */
function QuickAvailModal({ player, dateLabel, current, onPick, onClose }) {
  const T = window.BST;
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(4,6,11,0.62)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(2px)' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 380, background: T.surface, borderRadius: 14,
        border: `1px solid ${T.hair2}`, overflow: 'hidden', boxShadow: '0 24px 70px rgba(0,0,0,0.55)' }}>
        <div style={{ padding: '16px 18px', borderBottom: `1px solid ${T.hair}`, display: 'flex', alignItems: 'center', gap: 12 }}>
          {player && <Avatar p={player} size={38} />}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="eyebrow" style={{ color: T.accent }}>Update availability{dateLabel ? ` · ${dateLabel}` : ''}</div>
            <div style={{ fontFamily: T.display, fontWeight: 700, fontSize: 17, marginTop: 3 }}>{player ? player.name : 'Player'}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: T.faint, cursor: 'pointer', display: 'flex', padding: 4 }}><Icon name="close" size={18} /></button>
        </div>
        <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {BS_AVAIL_ORDER.map(s => {
            const a = BS_AVAIL[s];
            const on = current === s;
            return (
              <button key={s} onClick={() => onPick(s)} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
                padding: '13px 14px', borderRadius: 10, fontFamily: T.display, fontWeight: 600, fontSize: 14.5, transition: 'all .12s',
                border: `1.5px solid ${on ? a.text : T.hair2}`, background: on ? a.tint : 'transparent', color: on ? a.text : T.dim, textAlign: 'left' }}>
                <span style={{ width: 24, height: 24, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: T.mono, fontSize: 13, fontWeight: 700, background: s === 'NO_RESPONSE' ? 'transparent' : a.dot,
                  border: s === 'NO_RESPONSE' ? `1.5px solid ${a.dot}` : 'none', color: s === 'NO_RESPONSE' ? a.text : '#04130c' }}>{a.glyph}</span>
                {a.label}
              </button>
            );
          })}
        </div>
        <div style={{ padding: '0 16px 16px', fontSize: 11.5, color: T.faint, display: 'flex', alignItems: 'center', gap: 7 }}>
          <Icon name="info" size={13} /> Tap a status — saves instantly.
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { setAvailOverride, availOf, useAvailVersion, QuickAvailModal, setSquadOverride, squadOf });

/* Clickable status dot — opens the quick-update modal via onEdit(player) */
function AvailDot({ p, onEdit, glow, size }) {
  return (
    <span onClick={e => { if (onEdit) { e.stopPropagation(); onEdit(p); } }} title={onEdit ? 'Update availability' : undefined}
      style={{ display: 'inline-flex', alignItems: 'center', cursor: onEdit ? 'pointer' : 'default', padding: 3, margin: -3, borderRadius: 999 }}>
      <Dot status={availOf(p)} glow={glow} size={size} />
    </span>
  );
}
Object.assign(window, { AvailDot });

/* ── The cleaned module chrome: sidebar + header ────────────────────────── */
const BS_NAV = [
  { key: 'overview', label: 'Overview', icon: 'overview' },
  { key: 'players', label: 'Players', icon: 'player' },
  { key: 'fixtures', label: 'Fixtures', icon: 'fixtures' },
  { key: 'teams', label: 'Squads', icon: 'teams' },
  { key: 'availability', label: 'Availability', icon: 'availability' },
  { key: 'selection', label: 'Selection', icon: 'selection' },
  { key: 'ladders', label: 'Ladders', icon: 'ladders' },
];

function BSShell({ active, title, subtitle, actions, children, onNav, overlay, width = 1360, height = 860 }) {
  return (
    <div style={{ position: 'relative', display: 'flex', width, height, minHeight: height, background: T.bg, color: T.text,
      fontFamily: T.body, borderRadius: 12, overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{ width: 212, minWidth: 212, background: T.surface, borderRight: `1px solid ${T.hair}`,
        display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '18px 16px 16px', borderBottom: `1px solid ${T.hair}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 34, height: 34, borderRadius: 9, background: 'rgba(22,199,132,0.14)',
              color: T.accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: T.display, fontWeight: 800, fontSize: 16 }}>A</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: T.display, fontWeight: 700, fontSize: 14, lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{BS_CLUB.name}</div>
              <div style={{ fontFamily: T.mono, fontSize: 10.5, color: T.faint, marginTop: 2 }}>
                Better<span style={{ color: T.accent }}>Select</span>
              </div>
            </div>
          </div>
        </div>
        <nav style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
          {BS_NAV.map(item => {
            const on = item.key === active;
            return (
              <button key={item.key} onClick={() => onNav && onNav(item.key)} style={{
                display: 'flex', alignItems: 'center', gap: 11, padding: '9px 11px', borderRadius: 8,
                border: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: T.body, fontSize: 13.5,
                fontWeight: on ? 600 : 500, transition: 'all .14s',
                background: on ? 'rgba(22,199,132,0.12)' : 'transparent',
                color: on ? T.accent : T.dim,
              }}
                onMouseEnter={e => { if (!on) { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.text; } }}
                onMouseLeave={e => { if (!on) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.dim; } }}>
                <Icon name={item.icon} size={17} />{item.label}
              </button>
            );
          })}
        </nav>
        <div style={{ padding: 14, borderTop: `1px solid ${T.hair}` }}>
          <button style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none',
            color: T.faint, fontFamily: T.mono, fontSize: 11, cursor: 'pointer' }}>
            <Icon name="back" size={14} /> Back to admin
          </button>
        </div>
      </aside>

      {/* Main column */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
          padding: '16px 24px', borderBottom: `1px solid ${T.hair}`, background: T.surface }}>
          <div>
            <h1 style={{ margin: 0, fontFamily: T.display, fontWeight: 700, fontSize: 21, letterSpacing: '-0.01em' }}>{title}</h1>
            {subtitle && <div style={{ color: T.faint, fontSize: 13, marginTop: 3 }}>{subtitle}</div>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>{actions}</div>
        </header>
        <main style={{ flex: 1, padding: 24, overflow: 'hidden' }}>{children}</main>
      </div>
      {overlay}
    </div>
  );
}

Object.assign(window, {
  BST: T, Icon, Avatar, Dot, AvailLabel, RoleChips, AvailSummary,
  Btn, Segmented, Search, Chip, BSShell, BS_NAV,
});
