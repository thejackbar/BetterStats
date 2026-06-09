/* BetterStats — Players admin · main app
 * The redesigned Players list: alphabet range tabs (A–E, F–J…), sticky letter
 * headers, an A–Z jump rail, a prominent scrollbar, and no PHQ/UUID clutter.
 */
const { useState, useEffect, useRef, useMemo, useCallback } = React;
const { Icon, Avatar, Btn, RoleChip, Seg, PlayerModal } = window;
const {
  useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect,
} = window;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "nav": "both",
  "density": "regular",
  "scrollbar": "prominent",
  "showMeta": true,
  "showSquad": true
}/*EDITMODE-END*/;

/* ── sidebar nav model (mirrors the live admin) ─────────────────────────── */
const NAV = [
  { label: 'Better HQ', items: ['Platform Overview', 'All Clubs', 'Users', 'Usage', 'KlubPro Migration'] },
  { label: 'Modules', items: ['BetterSelect', 'BetterSocials', 'BetterAdmin', 'BetterIQ'], bold: true },
  { label: 'Cricket Data', items: ['Dashboard', 'Matches', 'Players', 'Seasons'] },
  { label: 'Content', items: ['Award Types', 'Awards', 'Sponsors', 'Yearbooks'] },
];

function Sidebar({ open, onClose }) {
  return (
    <>
      <div className={'pl-scrim' + (open ? ' show' : '')} onClick={onClose} />
      <aside className={'pl-side' + (open ? ' open' : '')}>
        <div className="pl-side-brand">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="pl-logo">BS</span>
            <div>
              <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 15, letterSpacing: '.06em' }}>BETTERSTATS</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--pb-faint)', letterSpacing: '.1em' }}>APPLECROSS · v8.8</div>
            </div>
          </div>
        </div>
        <nav className="pl-side-nav bs-scroll">
          {NAV.map((g) => (
            <div className="pl-side-group" key={g.label}>
              <div className="pl-side-label">{g.label}</div>
              {g.items.map((it) => (
                <div key={it} className={'pl-navitem' + (it === 'Players' ? ' active' : '') + (g.bold ? ' strong' : '')}>{it}</div>
              ))}
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}

function Topbar({ theme, setTheme, onBurger }) {
  return (
    <header className="pl-topbar">
      <button className="pl-burger" onClick={onBurger}><Icon name="list" size={20} /></button>
      <div className="pl-club">
        <Icon name="users" size={15} style={{ color: 'var(--pb-faint)' }} />
        <span>Applecross Cricket Club</span>
        <Icon name="chevron" size={14} style={{ color: 'var(--pb-faint)' }} />
      </div>
      <div style={{ flex: 1 }} />
      <button className="pl-tb-btn pl-hide-sm"><Icon name="ext" size={14} /> View public page</button>
      <button className="pl-tb-icon" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} title="Toggle theme">
        <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={17} />
      </button>
      <button className="pl-tb-icon pl-hide-sm" style={{ position: 'relative' }}>
        <Icon name="bell" size={17} /><span className="pl-dot">5</span>
      </button>
      <div className="pl-user pl-hide-sm">Jack <b>(SUPER)</b></div>
    </header>
  );
}

/* ── a single player row ─────────────────────────────────────────────────── */
function Row({ p, density, showMeta, showSquad, onEdit }) {
  const av = density === 'compact' ? 34 : density === 'comfy' ? 46 : 40;
  return (
    <div className={'pl-row d-' + density} onClick={() => onEdit(p)}>
      <Avatar p={p} size={av} />
      <div className="pl-row-main">
        <div className="pl-row-top">
          <span className="pl-row-name">{p.name}</span>
          {(p.skills || []).map((s) => <RoleChip key={s} skill={s} />)}
          {p.overseas && <span className="pl-badge globe"><Icon name="globe" size={11} /> Overseas</span>}
          {p.inactive && <span className="pl-badge mute">Inactive</span>}
        </div>
        {showMeta && <div className="pl-row-meta">{PD.metaLine(p)}</div>}
      </div>
      {showSquad && <span className="pl-squad">{p.squadShort}</span>}
      <button className="pl-edit" onClick={(e) => { e.stopPropagation(); onEdit(p); }}><Icon name="edit" size={13} /> Edit</button>
    </div>
  );
}

function PlayersApp() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const theme = t.theme;
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); }, [theme]);

  const [q, setQ] = useState('');
  const [scope, setScope] = useState('all');          // all | local | overseas
  const [range, setRange] = useState('A-E');           // active alphabet bucket
  const [navOpen, setNavOpen] = useState(false);
  const [active, setActive] = useState(null);          // index into `shown` for the modal
  const scrollRef = useRef(null);
  const headerRefs = useRef({});

  const usesRanges = t.nav === 'both' || t.nav === 'ranges';
  const usesRail = t.nav === 'both' || t.nav === 'rail';
  const searching = q.trim().length > 0;

  // base filter (scope + search) — search & scope always apply across the whole roster
  const base = useMemo(() => {
    let list = PD.ROSTER;
    if (scope === 'local') list = list.filter((p) => !p.overseas);
    if (scope === 'overseas') list = list.filter((p) => p.overseas);
    if (searching) {
      const s = q.trim().toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(s) || p.sortName.toLowerCase().includes(s));
    }
    return list;
  }, [scope, q, searching]);

  // counts per range (for the tab labels)
  const rangeCounts = useMemo(() => {
    const m = { all: base.length }; PD.RANGES.forEach((r) => (m[r.key] = 0));
    base.forEach((p) => { const r = PD.rangeOf(p); m[r] = (m[r] || 0) + 1; });
    return m;
  }, [base]);

  // which players are actually shown (range filter only when ranges on & not searching)
  const shown = useMemo(() => {
    if (!usesRanges || searching) return base;
    return base.filter((p) => PD.rangeOf(p) === range);
  }, [base, usesRanges, searching, range]);

  // group into letters for headers/rail
  const groups = useMemo(() => {
    const m = new Map();
    shown.forEach((p) => { const L = PD.letterOf(p); if (!m.has(L)) m.set(L, []); m.get(L).push(p); });
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [shown]);

  const letterSet = useMemo(() => new Set(base.map((p) => PD.letterOf(p))), [base]);
  const showHeaders = t.nav !== 'flat';

  const pendingJump = useRef(null);
  const scrollToLetter = (letter) => {
    const el = headerRefs.current[letter]; const sc = scrollRef.current;
    if (el && sc) sc.scrollTop = Math.max(0, el.offsetTop - 4);
  };
  // after a range switch, finish the jump once the new group has rendered
  useEffect(() => {
    if (pendingJump.current) { scrollToLetter(pendingJump.current); pendingJump.current = null; }
  }, [range, shown]);

  const jumpTo = useCallback((letter) => {
    if (usesRanges && !searching) {
      const r = PD.RANGES.find((rg) => letter >= rg.from && letter <= rg.to);
      if (r && r.key !== range) { pendingJump.current = letter; setRange(r.key); return; }
    }
    scrollToLetter(letter);
  }, [usesRanges, searching, range]);

  // modal navigation across the full shown list
  const openPlayer = (p) => setActive(shown.findIndex((x) => x.id === p.id));
  const move = (d) => setActive((i) => (i + d + shown.length) % shown.length);

  const railLetters = PD.ALPHABET;

  return (
    <div className="pl-shell">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="pl-main">
        <Topbar theme={theme} setTheme={(v) => setTweak('theme', v)} onBurger={() => setNavOpen(true)} />
        <div className="pl-content">
          {/* page head */}
          <div className="pl-pagehead">
            <div>
              <h1 className="pl-h1">Players</h1>
              <div className="pl-sub">{base.length.toLocaleString()} players{scope !== 'all' && ` · ${scope}`}</div>
            </div>
            <Btn variant="primary" icon="plus">Add player</Btn>
          </div>

          {/* search */}
          <div className="pl-search">
            <Icon name="search" size={18} style={{ color: 'var(--pb-faint)' }} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name (first or last, any order)…" />
            {q && <button className="pl-clear" onClick={() => setQ('')}><Icon name="close" size={15} /></button>}
          </div>

          {/* controls: scope + range tabs */}
          <div className="pl-controls">
            <Seg value={scope} onChange={setScope} options={[
              { value: 'all', label: 'All' }, { value: 'local', label: 'Local' }, { value: 'overseas', label: 'Overseas' },
            ]} />
            {usesRanges && !searching && (
              <div className="pl-ranges">
                {PD.RANGES.map((r) => (
                  <button key={r.key} className={'pl-rangetab' + (range === r.key ? ' on' : '') + (!rangeCounts[r.key] ? ' empty' : '')}
                    onClick={() => { setRange(r.key); if (scrollRef.current) scrollRef.current.scrollTop = 0; }}>
                    {r.key}<i>{rangeCounts[r.key] || 0}</i>
                  </button>
                ))}
              </div>
            )}
            <div className="pl-shown">{searching ? `${shown.length} match${shown.length === 1 ? '' : 'es'}` : `${shown.length} shown`}</div>
          </div>

          {/* list + jump rail */}
          <div className="pl-listwrap">
            <div ref={scrollRef} className={'pl-scroll bs-scroll sb-' + t.scrollbar}>
              {groups.length === 0 && <div className="pl-empty">No players match “{q}”.</div>}
              {groups.map(([L, list]) => (
                <section key={L} className="pl-group">
                  {showHeaders && (
                    <div className="pl-letterhead" ref={(el) => (headerRefs.current[L] = el)}>
                      <span>{L}</span><i>{list.length}</i>
                    </div>
                  )}
                  {list.map((p) => (
                    <Row key={p.id} p={p} density={t.density} showMeta={t.showMeta} showSquad={t.showSquad} onEdit={openPlayer} />
                  ))}
                </section>
              ))}
            </div>

            {usesRail && !searching && (
              <div className="pl-rail">
                {railLetters.map((L) => {
                  const has = letterSet.has(L);
                  const here = groups.some(([g]) => g === L);
                  return (
                    <button key={L} className={'pl-rail-l' + (here ? ' here' : '') + (has ? '' : ' off')}
                      disabled={!has} onClick={() => jumpTo(L)}>{L}</button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {active != null && shown[active] && (
        <PlayerModal player={shown[active]} index={active} total={shown.length}
          onClose={() => setActive(null)} onPrev={() => move(-1)} onNext={() => move(1)} />
      )}

      <TweaksPanel>
        <TweakSection label="Navigation" />
        <TweakRadio label="Group by" value={t.nav}
          options={[{ value: 'both', label: 'Tabs + rail' }, { value: 'ranges', label: 'Range tabs' }, { value: 'rail', label: 'A–Z rail' }, { value: 'flat', label: 'Flat' }]}
          onChange={(v) => setTweak('nav', v)} />
        <TweakSection label="List" />
        <TweakRadio label="Density" value={t.density}
          options={['compact', 'regular', 'comfy']} onChange={(v) => setTweak('density', v)} />
        <TweakRadio label="Scrollbar" value={t.scrollbar}
          options={['prominent', 'subtle']} onChange={(v) => setTweak('scrollbar', v)} />
        <TweakToggle label="Show role / style line" value={t.showMeta} onChange={(v) => setTweak('showMeta', v)} />
        <TweakToggle label="Show squad tag" value={t.showSquad} onChange={(v) => setTweak('showSquad', v)} />
        <TweakSection label="Theme" />
        <TweakRadio label="Mode" value={t.theme} options={['dark', 'light']} onChange={(v) => setTweak('theme', v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<PlayersApp />);
