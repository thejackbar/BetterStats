/* BetterStats — Players admin · shared atoms (Press Box kit)
 * Self-contained so it doesn't depend on the Selection prototype's BS globals.
 */
const { useState, useEffect, useRef, useMemo, useCallback, useLayoutEffect } = React;
const PD = window.PD;

const ICONS = {
  search:  <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>,
  plus:    <><path d="M12 5v14M5 12h14" /></>,
  edit:    <><path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M13.5 6.5l4 4" /></>,
  close:   <><path d="M6 6l12 12M18 6L6 18" /></>,
  chevron: <><path d="M6 9l6 6 6-6" /></>,
  chevR:   <><path d="M9 6l6 6-6 6" /></>,
  chevL:   <><path d="M15 6l-6 6 6 6" /></>,
  arrowR:  <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  user:    <><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></>,
  users:   <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9" /></>,
  mail:    <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M4 7l8 6 8-6" /></>,
  phone:   <><path d="M5 4h4l2 5-3 2a12 12 0 0 0 5 5l2-3 5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" /></>,
  check:   <><path d="M5 12.5l4.5 4.5L19 7" /></>,
  list:    <><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></>,
  grid:    <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
  bell:    <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>,
  sun:     <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4" /></>,
  moon:    <><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></>,
  ext:     <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" /></>,
  filter:  <><path d="M4 6h16M7 12h10M10 18h4" /></>,
  globe:   <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.6 2.4 2.6 15.6 0 18M12 3c-2.6 2.4-2.6 15.6 0 18" /></>,
  alert:   <><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17h.01" /></>,
  star:    <><path d="M12 3l2.4 5.3L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-.7z" /></>,
};
function Icon({ name, size = 18, sw = 1.7, style, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">
      {ICONS[name] || null}
    </svg>
  );
}

function Avatar({ p, size = 38, ring, style }) {
  const keeper = (p?.skills || []).includes('WKT');
  const hue = PD.tintOf(p);
  const border = ring || (keeper ? 'color-mix(in srgb, var(--pb-amber) 55%, transparent)' : 'var(--pb-hairline2)');
  const common = { width: size, height: size, minWidth: size, borderRadius: '50%', border: `1.5px solid ${border}`, ...style };
  if (p?.photo) return <img src={p.photo} alt="" style={{ ...common, objectFit: 'cover' }} />;
  return (
    <span style={{ ...common, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: `oklch(0.34 0.06 ${hue})`, color: `oklch(0.9 0.07 ${hue})`,
      fontFamily: 'var(--mono)', fontWeight: 600, fontSize: Math.round(size * 0.34), letterSpacing: '.02em' }}>
      {PD.initials(p?.name || '?')}
    </span>
  );
}

const BTN = {
  primary: { background: 'var(--pb-accent)', color: '#06120c', border: '1px solid transparent', fontWeight: 600 },
  ghost:   { background: 'transparent', color: 'var(--pb-dim)', border: '1px solid var(--pb-hairline2)' },
  soft:    { background: 'var(--pb-surface2)', color: 'var(--pb-text)', border: '1px solid var(--pb-hairline)' },
};
function Btn({ children, variant = 'ghost', sm, icon, iconR, onClick, disabled, title, style, className = '' }) {
  const pad = sm ? '6px 11px' : '9px 15px';
  const fs = sm ? 12.5 : 13.5;
  return (
    <button type="button" title={title} onClick={disabled ? undefined : onClick} disabled={disabled} className={className}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: sm ? 6 : 8,
        padding: pad, borderRadius: 9, fontFamily: 'var(--display)', fontSize: fs, lineHeight: 1, whiteSpace: 'nowrap',
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.45 : 1, transition: 'opacity .15s, border-color .15s, background .15s',
        ...BTN[variant], ...style }}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}{iconR && <Icon name={iconR} size={sm ? 14 : 16} />}
    </button>
  );
}

const SKILL_TONE = { WKT: ['var(--pb-amber)', 12], ALL: ['var(--pb-accent)', 12] };
function RoleChip({ skill }) {
  const wk = skill === 'WKT';
  const [c] = SKILL_TONE[skill] || ['var(--pb-faint)', 0];
  return (
    <span style={{ flexShrink: 0, fontFamily: 'var(--mono)', fontSize: 9.5, fontWeight: 700, letterSpacing: '.05em', padding: '2px 5px', borderRadius: 4,
      background: SKILL_TONE[skill] ? `color-mix(in srgb, ${c} 13%, transparent)` : 'var(--pb-surface2)',
      color: SKILL_TONE[skill] ? c : 'var(--pb-faint)' }}>{PD.SKILL_SHORT[skill] || skill}</span>
  );
}

function Seg({ options, value, onChange, sm }) {
  return (
    <div style={{ display: 'inline-flex', flexWrap: 'nowrap', whiteSpace: 'nowrap', padding: 3, gap: 2, background: 'var(--pb-surface2)', borderRadius: 9, border: '1px solid var(--pb-hairline)' }}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
            style={{ borderRadius: 6, fontFamily: 'var(--display)', fontWeight: 600, border: 'none', cursor: 'pointer',
              fontSize: sm ? 12 : 12.5, padding: sm ? '5px 10px' : '6px 13px', transition: 'all .15s', whiteSpace: 'nowrap',
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'transparent',
              color: active ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
            {o.icon && <Icon name={o.icon} size={14} />}{o.label}
          </button>
        );
      })}
    </div>
  );
}

/* form atoms used in the modal */
function Field({ label, hint, children, span }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 7, gridColumn: span ? `span ${span}` : 'auto', minWidth: 0 }}>
      <span style={{ fontSize: 12, color: 'var(--pb-faint)' }}>{label}{hint && <span style={{ color: 'var(--pb-faintest)' }}> {hint}</span>}</span>
      {children}
    </label>
  );
}
const inputStyle = {
  height: 44, padding: '0 14px', borderRadius: 10, border: '1px solid var(--pb-hairline2)',
  background: 'var(--pb-surface2)', color: 'var(--pb-text)', fontSize: 15, fontFamily: 'var(--body)', width: '100%', outline: 'none',
};
function TextInput(props) {
  return <input {...props} style={{ ...inputStyle, ...(props.style || {}) }} />;
}
function SelectInput({ value, onChange, options }) {
  return (
    <div style={{ position: 'relative' }}>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        style={{ ...inputStyle, appearance: 'none', paddingRight: 38, cursor: 'pointer' }}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <Icon name="chevron" size={16} style={{ position: 'absolute', right: 13, top: '50%', transform: 'translateY(-50%)', color: 'var(--pb-faint)', pointerEvents: 'none' }} />
    </div>
  );
}
function Toggle({ on, onChange, label }) {
  return (
    <button type="button" onClick={() => onChange(!on)} style={{ display: 'flex', alignItems: 'center', gap: 14, background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0', textAlign: 'left' }}>
      <span style={{ width: 46, height: 27, borderRadius: 999, flexShrink: 0, position: 'relative', transition: 'background .18s',
        background: on ? 'var(--pb-accent)' : 'var(--pb-hairline2)' }}>
        <span style={{ position: 'absolute', top: 3, left: on ? 22 : 3, width: 21, height: 21, borderRadius: '50%',
          background: on ? '#06120c' : 'var(--pb-faint)', transition: 'left .18s' }} />
      </span>
      <span style={{ fontSize: 15, color: 'var(--pb-text)' }}>{label}</span>
    </button>
  );
}

Object.assign(window, { Icon, Avatar, Btn, RoleChip, Seg, Field, TextInput, SelectInput, Toggle });
