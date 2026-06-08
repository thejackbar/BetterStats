/* BetterSelect — Selection redesign · shared kit
 * Atoms ported from the real pb-* atom kit + a pointer-based drag engine that
 * works with mouse AND touch, + the shared selection-state hook used by all
 * three directions so the same XI renders three ways.
 */
const { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } = React;
const BS = window.BS;

/* ── Icons (geometric line glyphs) ──────────────────────────────────────── */
const ICONS = {
  search:   <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>,
  filter:   <><path d="M4 6h16M7 12h10M10 18h4" /></>,
  close:    <><path d="M6 6l12 12M18 6L6 18" /></>,
  plus:     <><path d="M12 5v14M5 12h14" /></>,
  check:    <><path d="M5 12.5l4.5 4.5L19 7" /></>,
  bolt:     <><path d="M13 3L5 13h6l-1 8 8-10h-6z" /></>,
  share:    <><circle cx="6" cy="12" r="2.4" /><circle cx="17" cy="6" r="2.4" /><circle cx="17" cy="18" r="2.4" /><path d="M8.1 11l6.8-3.9M8.1 13l6.8 3.9" /></>,
  grip:     <><circle cx="9" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="18" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="18" r="1.1" fill="currentColor" stroke="none" /></>,
  arrow:    <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  arrowL:   <><path d="M19 12H5M11 6l-6 6 6 6" /></>,
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  player:   <><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></>,
  fixtures: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9h18M8 3v3M16 3v3" /></>,
  teams:    <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9" /></>,
  availability: <><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 4.5-5" /></>,
  selection: <><path d="M12 3l2.4 5.3L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-.7z" /></>,
  ladders:  <><path d="M5 21V9M12 21V4M19 21v-8" /></>,
  nets:     <><path d="M4 4v16M20 4v16M4 4h16M4 9h16M4 14h16M4 19h16M9 4v16M14 4v16" /></>,
  sun:      <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4" /></>,
  moon:     <><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></>,
  info:     <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  chevron:  <><path d="M6 9l6 6 6-6" /></>,
  undo:     <><path d="M9 14 4 9l5-5" /><path d="M4 9h11a5 5 0 0 1 0 10h-1" /></>,
  cols:     <><rect x="3.5" y="4" width="7" height="16" rx="1.6" /><rect x="13.5" y="4" width="7" height="16" rx="1.6" /></>,
  sheet:    <><rect x="4" y="3.5" width="16" height="17" rx="2" /><path d="M8 8.5h8M8 12h8M8 15.5h5" /></>,
};
function Icon({ name, size = 18, sw = 1.7, style, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">
      {ICONS[name] || null}
    </svg>
  );
}

/* ── Availability dot (hollow ring for no-response) ─────────────────────── */
function Dot({ status, size = 9, glow, style }) {
  const m = BS.AVAIL[status] || BS.AVAIL.NO_RESPONSE;
  const hollow = status === 'NO_RESPONSE';
  return (
    <span style={{
      display: 'inline-block', width: size, height: size, minWidth: size, borderRadius: '50%',
      background: hollow ? 'transparent' : m.token,
      border: hollow ? `1.5px solid ${m.token}` : 'none',
      boxShadow: glow ? `0 0 0 3px color-mix(in srgb, ${m.token} 26%, transparent)` : 'none',
      ...style,
    }} />
  );
}

/* ── Avatar (initials; keeper gets an amber ring) ───────────────────────── */
function Avatar({ p, size = 30, style }) {
  const keeper = (p?.skills || []).includes('WKT');
  const ring = keeper ? 'color-mix(in srgb, var(--pb-amber) 55%, transparent)' : 'var(--pb-hairline2)';
  const common = { width: size, height: size, minWidth: size, borderRadius: '50%', border: `1.5px solid ${ring}`, ...style };
  if (p?.photo) return <img src={p.photo} alt="" style={{ ...common, objectFit: 'cover' }} />;
  return (
    <span style={{ ...common, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--pb-surface2)', color: 'var(--pb-dim)', fontFamily: 'var(--mono)', fontWeight: 600, fontSize: Math.round(size * 0.34) }}>
      {BS.initials(p?.name || '?')}
    </span>
  );
}

/* ── Role chips (BAT/BWL/ALL/WK) ────────────────────────────────────────── */
function RoleChips({ skills, muted }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      {(skills || []).map((r) => {
        const wk = r === 'WKT';
        return (
          <span key={r} style={{
            fontFamily: 'var(--mono)', fontSize: 9.5, fontWeight: 600, letterSpacing: '.04em',
            padding: '1px 5px', borderRadius: 4,
            background: wk ? 'color-mix(in srgb, var(--pb-amber) 12%, transparent)' : 'var(--pb-surface2)',
            color: wk ? 'var(--pb-amber)' : (muted ? 'var(--pb-faint)' : 'var(--pb-dim)'),
          }}>{BS.SKILL_SHORT[r] || r}</span>
        );
      })}
    </span>
  );
}

/* ── Mono pill tag ──────────────────────────────────────────────────────── */
const TAG_TONE = {
  accent: ['color-mix(in srgb, var(--pb-accent) 15%, transparent)', 'var(--pb-accent)'],
  amber:  ['color-mix(in srgb, var(--pb-amber) 15%, transparent)', 'var(--pb-amber)'],
  faint:  ['var(--pb-surface2)', 'var(--pb-faint)'],
};
function Tag({ children, tone = 'accent', style }) {
  const [bg, fg] = TAG_TONE[tone] || TAG_TONE.accent;
  return <span style={{ display: 'inline-flex', alignItems: 'center', fontFamily: 'var(--mono)', fontSize: 9.5, fontWeight: 700, letterSpacing: '.06em', padding: '1px 5px', borderRadius: 4, background: bg, color: fg, ...style }}>{children}</span>;
}

/* ── Form indicator — quiet last-4 sparkline + label ────────────────────── */
function FormBars({ p, h = 14, w = 3, gap = 2 }) {
  const bars = BS.spark(p);
  const tok = BS.formOf(p).token;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap, height: h }} title={`Recent: ${(p.recent || []).join(', ')}`}>
      {bars.map((v, i) => (
        <span key={i} style={{ width: w, height: Math.round(h * v), borderRadius: 1, background: tok, opacity: 0.4 + 0.6 * (i / (bars.length - 1)) }} />
      ))}
    </span>
  );
}
function FormChip({ p, withBars = true }) {
  const f = BS.formOf(p);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      {withBars && <FormBars p={p} />}
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 600, letterSpacing: '.04em', color: f.token }}>{f.label}</span>
    </span>
  );
}

/* ── Button ─────────────────────────────────────────────────────────────── */
const BTN = {
  primary: { background: 'var(--pb-accent)', color: '#08110b', border: '1px solid transparent', fontWeight: 600 },
  ghost:   { background: 'transparent', color: 'var(--pb-dim)', border: '1px solid var(--pb-hairline2)' },
  soft:    { background: 'var(--pb-surface2)', color: 'var(--pb-text)', border: '1px solid var(--pb-hairline)' },
};
function Btn({ children, variant = 'ghost', sm, icon, onClick, disabled, title, style, className = '' }) {
  const pad = sm ? '6px 10px' : '8px 14px';
  const fs = sm ? 12.5 : 13.5;
  return (
    <button type="button" title={title} onClick={disabled ? undefined : onClick} disabled={disabled} className={className}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: sm ? 6 : 8,
        padding: pad, borderRadius: 9, fontFamily: 'var(--display)', fontSize: fs, lineHeight: 1, whiteSpace: 'nowrap',
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.4 : 1, transition: 'opacity .15s, border-color .15s, background .15s',
        ...BTN[variant], ...style }}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}
    </button>
  );
}

/* ── Segmented control ──────────────────────────────────────────────────── */
function Segmented({ options, value, onChange, sm }) {
  return (
    <div style={{ display: 'inline-flex', flexWrap: 'nowrap', whiteSpace: 'nowrap', padding: 3, gap: 2, background: 'var(--pb-surface2)', borderRadius: 9, border: '1px solid var(--pb-hairline)' }}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
            style={{ borderRadius: 6, fontFamily: 'var(--display)', fontWeight: 600, border: 'none', cursor: 'pointer',
              fontSize: sm ? 12 : 13, padding: sm ? '4px 10px' : '6px 12px', transition: 'all .15s',
              background: active ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : 'transparent',
              color: active ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ── Search input ───────────────────────────────────────────────────────── */
function Search({ value, onChange, placeholder = 'Search…', style }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 9, padding: '0 12px', height: 38, color: 'var(--pb-faint)', ...style }}>
      <Icon name="search" size={16} />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        style={{ background: 'transparent', border: 0, outline: 'none', color: 'var(--pb-text)', fontSize: 14, width: '100%' }} />
    </div>
  );
}

/* ══ Pointer drag engine (mouse + touch) ════════════════════════════════════
 * <DnD onDrop={(target,item)=>...}> exposes a context. Draggables spread
 * useDrag().bind(item). Drop zones add data-drop-kind / data-drop-idx and read
 * ctx.hover for highlight. A floating ghost follows the pointer. */
const DnDCtx = createContext(null);
function DnD({ onDrop, children }) {
  const [drag, setDrag] = useState(null);     // { item, x, y, renderGhost }
  const [hover, setHover] = useState(null);    // 'slot:3' | 'pool' | null
  const ref = useRef({ item: null, startX: 0, startY: 0, active: false, didDrag: false });

  const hit = (x, y) => {
    const el = document.elementFromPoint(x, y);
    const z = el && el.closest('[data-drop-kind]');
    if (!z) return null;
    const kind = z.getAttribute('data-drop-kind');
    const idx = z.getAttribute('data-drop-idx');
    return { kind, idx: idx == null ? null : Number(idx), key: kind + (idx == null ? '' : ':' + idx) };
  };

  useEffect(() => {
    const move = (e) => {
      const r = ref.current;
      if (!r.item) return;
      const pt = e.touches ? e.touches[0] : e;
      const dx = pt.clientX - r.startX, dy = pt.clientY - r.startY;
      if (!r.active && Math.hypot(dx, dy) < 6) return;
      if (!r.active) { r.active = true; r.didDrag = true; }
      if (e.cancelable) e.preventDefault();
      const t = hit(pt.clientX, pt.clientY);
      setHover(t ? t.key : null);
      setDrag({ item: r.item, x: pt.clientX, y: pt.clientY });
    };
    const up = (e) => {
      const r = ref.current;
      if (!r.item) return;
      const pt = e.changedTouches ? e.changedTouches[0] : e;
      if (r.active) { const t = hit(pt.clientX, pt.clientY); if (t) onDrop(t, r.item); }
      r.item = null; r.active = false;
      setDrag(null); setHover(null);
    };
    window.addEventListener('pointermove', move, { passive: false });
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up); };
  }, [onDrop]);

  const begin = useCallback((item, e) => {
    const pt = e.touches ? e.touches[0] : e;
    ref.current = { item, startX: pt.clientX, startY: pt.clientY, active: false, didDrag: false };
    setDrag(null);
  }, []);
  const consumedClick = useCallback(() => { const d = ref.current.didDrag; ref.current.didDrag = false; return d; }, []);

  return (
    <DnDCtx.Provider value={{ begin, consumedClick, hover, dragItem: drag?.item || null }}>
      {children}
      {drag && <DragGhost drag={drag} />}
    </DnDCtx.Provider>
  );
}
function DragGhost({ drag }) {
  const p = drag.item.player;
  return ReactDOM.createPortal(
    <div style={{ position: 'fixed', left: drag.x, top: drag.y, transform: 'translate(-50%,-130%) rotate(-2deg)', zIndex: 9999, pointerEvents: 'none',
      display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px 7px 8px', borderRadius: 10,
      background: 'var(--pb-surface)', border: '1px solid var(--pb-accent)', boxShadow: '0 16px 40px -8px rgba(0,0,0,.45)', opacity: 0.96 }}>
      <Avatar p={p} size={26} />
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--pb-text)' }}>{p?.name}</span>
    </div>, document.body);
}
function useDrag() {
  const ctx = useContext(DnDCtx);
  return {
    bind: (item) => ({ onPointerDown: (e) => ctx.begin(item, e) }),
    clickGuard: (fn) => (e) => { if (ctx.consumedClick()) return; fn && fn(e); },
    hover: ctx.hover,
    dragItem: ctx.dragItem,
  };
}

/* ══ Shared selection state ═════════════════════════════════════════════════ */
function useSelection() {
  const SIZE = 11;
  const [slots, setSlots] = useState(() => {
    const a = Array(SIZE).fill(null);
    BS.STARTING_XI.forEach((id, i) => { if (i < SIZE) a[i] = id; });
    return a;
  });
  const [capId, setCapId] = useState(null);
  const [wkId, setWkId] = useState('p7');     // Baker, Daniel pre-set as keeper
  const [focus, setFocus] = useState(-1);

  const filled = slots.filter(Boolean);
  const count = filled.length;
  const usedIds = useMemo(() => new Set(filled), [slots]);

  const place = useCallback((idx, id) => {
    setSlots((prev) => {
      const n = [...prev];
      const ex = n.indexOf(id); if (ex !== -1) n[ex] = null;
      n[idx] = id; return n;
    });
  }, []);
  const removeAt = useCallback((idx) => {
    setSlots((prev) => { const n = [...prev]; const id = n[idx]; n[idx] = null; if (id === capId) setCapId(null); if (id === wkId) setWkId(null); return n; });
    setFocus(idx);
  }, [capId, wkId]);
  const removeId = useCallback((id) => {
    setSlots((prev) => { const i = prev.indexOf(id); if (i === -1) return prev; const n = [...prev]; n[i] = null; return n; });
    if (id === capId) setCapId(null); if (id === wkId) setWkId(null);
  }, [capId, wkId]);
  // tap a pool player → fill focused empty slot, else next empty
  const addPlayer = useCallback((p) => {
    if (p.availability === 'UNAVAILABLE') return;
    setSlots((prev) => {
      const n = [...prev];
      if (n.indexOf(p.id) !== -1) return prev;
      let t = (focus >= 0 && n[focus] == null) ? focus : n.indexOf(null);
      if (t === -1) return prev;
      n[t] = p.id;
      return n;
    });
    setFocus(-1);
  }, [focus]);
  const move = useCallback((from, to) => {
    if (from === to) return;
    setSlots((prev) => { const n = [...prev]; const m = n[from]; n[from] = n[to]; n[to] = m; return n; });
  }, []);
  // reorder (insert) — used by Team Sheet drag-to-reorder
  const reorder = useCallback((from, to) => {
    setSlots((prev) => { const n = [...prev]; const [m] = n.splice(from, 1); n.splice(to, 0, m); while (n.length < SIZE) n.push(null); return n.slice(0, SIZE); });
  }, []);
  const toggleCap = useCallback((id) => setCapId((c) => (c === id ? null : id)), []);
  const toggleWk = useCallback((id) => setWkId((c) => (c === id ? null : id)), []);
  const clearXI = useCallback(() => { setSlots(Array(SIZE).fill(null)); setCapId(null); setWkId(null); setFocus(0); }, []);

  const autofill = useCallback(() => {
    setSlots((prev) => {
      const n = [...prev];
      const taken = new Set(n.filter(Boolean));
      const elig = BS.POOL.filter((p) => p.availability !== 'UNAVAILABLE' && !taken.has(p.id))
        .sort((a, b) => (a.tier - b.tier) || (b.score - a.score));
      let k = 0;
      for (let i = 0; i < n.length; i++) { if (n[i]) continue; while (k < elig.length && taken.has(elig[k].id)) k++; if (k < elig.length) { n[i] = elig[k].id; taken.add(elig[k].id); k++; } }
      return n;
    });
  }, []);

  // team balance
  const balance = useMemo(() => {
    const has = (id, c) => (BS.byId[id]?.skills || []).includes(c);
    const b = { BAT: 0, BWL: 0, ALL: 0, WKT: 0 };
    filled.forEach((id) => ['BAT', 'BWL', 'ALL', 'WKT'].forEach((c) => { if (has(id, c)) b[c]++; }));
    const bowlers = filled.filter((id) => has(id, 'BWL') || has(id, 'ALL')).length;
    return { ...b, bowlers, lightBowling: count >= 8 && bowlers < 5, hasKeeper: filled.some((id) => has(id, 'WKT')) };
  }, [slots]);

  return { slots, setSlots, capId, wkId, focus, setFocus, filled, count, usedIds, SIZE,
    place, removeAt, removeId, addPlayer, move, reorder, toggleCap, toggleWk, clearXI, autofill, balance };
}

/* Pool classification helpers */
function classifyBowl(p) {
  if (!p.bowl) return 'none';
  return /spin|orthodox/i.test(p.bowl) ? 'spin' : 'pace';
}
function formBucket(p) {
  if (p.form === 'hot') return 'hot';
  if (p.form === 'warm') return 'warm';
  if (p.form === 'steady') return 'steady';
  return 'quiet'; // quiet / cold
}
const FORM_BUCKETS = [
  { v: 'hot', label: 'Hot' },
  { v: 'warm', label: 'In form' },
  { v: 'steady', label: 'Steady' },
  { v: 'quiet', label: 'Out of nick' },
];
const BOWL_KINDS = [{ v: 'pace', label: 'Pace' }, { v: 'spin', label: 'Spin' }, { v: 'none', label: 'Doesn’t bowl' }];
const SORTS = [{ v: 'squad', label: 'Squad order' }, { v: 'form', label: 'Form' }, { v: 'name', label: 'Name (A–Z)' }];

/* Centralised filter state shared by the pool views */
function useFilters() {
  const [q, setQ] = useState('');
  const [roles, setRoles] = useState([]);
  const [avails, setAvails] = useState([]);
  const [bowling, setBowling] = useState([]);
  const [hands, setHands] = useState([]);
  const [squads, setSquads] = useState([]);
  const [forms, setForms] = useState([]);
  const [hideUnavail, setHideUnavail] = useState(false);
  const [sort, setSort] = useState('squad');
  const toggle = (arr, set) => (v) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const activeCount = roles.length + avails.length + bowling.length + hands.length + squads.length + forms.length + (hideUnavail ? 1 : 0);
  const clearAll = () => { setRoles([]); setAvails([]); setBowling([]); setHands([]); setSquads([]); setForms([]); setHideUnavail(false); };
  return { q, setQ, roles, setRoles, avails, setAvails, bowling, setBowling, hands, setHands, squads, setSquads,
    forms, setForms, hideUnavail, setHideUnavail, sort, setSort, toggle, activeCount, clearAll };
}

/* Pool filtering + sorting shared helper */
function usePool(sel, f) {
  return useMemo(() => {
    let list = BS.POOL.filter((p) => !sel.usedIds.has(p.id));
    if (f.q && f.q.trim()) { const s = f.q.trim().toLowerCase(); list = list.filter((p) => p.name.toLowerCase().includes(s)); }
    if (f.roles.length) list = list.filter((p) => p.skills.some((r) => f.roles.includes(r)));
    if (f.avails.length) list = list.filter((p) => f.avails.includes(p.availability));
    if (f.bowling.length) list = list.filter((p) => f.bowling.includes(classifyBowl(p)));
    if (f.hands.length) list = list.filter((p) => f.hands.includes(p.batting_hand));
    if (f.squads.length) list = list.filter((p) => f.squads.includes(p.squad));
    if (f.forms.length) list = list.filter((p) => f.forms.includes(formBucket(p)));
    if (f.hideUnavail) list = list.filter((p) => p.availability !== 'UNAVAILABLE');
    const byTier = (a, b) => (a.tier - b.tier) || (b.score - a.score) || a.name.localeCompare(b.name);
    const sorters = { squad: byTier, form: (a, b) => (b.score - a.score) || a.name.localeCompare(b.name), name: (a, b) => a.name.localeCompare(b.name) };
    return list.slice().sort(sorters[f.sort] || byTier);
  }, [sel.usedIds, f.q, f.roles, f.avails, f.bowling, f.hands, f.squads, f.forms, f.hideUnavail, f.sort]);
}

Object.assign(window, {
  Icon, Dot, Avatar, RoleChips, Tag, FormBars, FormChip, Btn, Segmented, Search,
  DnD, useDrag, useSelection, useFilters, usePool,
  classifyBowl, formBucket, FORM_BUCKETS, BOWL_KINDS, SORTS,
});
