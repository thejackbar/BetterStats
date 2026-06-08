/* BetterSelect — Selection redesign · app shell
 * BetterStats-branded chrome (sidebar + header) + theme toggle + direction
 * switcher. Owns ONE selection state and the global drop semantics, so the
 * same XI renders three ways and you can flip between them to compare.
 */
const NAV = [
  { icon: 'overview', label: 'Overview' },
  { icon: 'player', label: 'Players' },
  { icon: 'fixtures', label: 'Fixtures' },
  { icon: 'teams', label: 'Squads' },
  { icon: 'availability', label: 'Availability' },
  { icon: 'selection', label: 'Selection', active: true },
  { icon: 'nets', label: 'Nets' },
  { icon: 'ladders', label: 'Ladders' },
];

const VIEWS = [
  { id: 'B', name: 'Dual rail', icon: 'cols' },
  { id: 'C', name: 'Team sheet', icon: 'sheet' },
];

function ViewToggle({ value, onChange }) {
  return (
    <div className="bs-viewtoggle" role="tablist" aria-label="Selection view">
      {VIEWS.map((v) => (
        <button key={v.id} type="button" role="tab" aria-selected={value === v.id}
          className={'bs-viewbtn' + (value === v.id ? ' on' : '')} title={v.name + ' view'} onClick={() => onChange(v.id)}>
          <Icon name={v.icon} size={15} /><span className="bs-viewbtn-l">{v.name}</span>
        </button>
      ))}
    </div>
  );
}

function Sidebar({ club }) {
  return (
    <aside className="bs-sidebar">
      <div className="bs-brand">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 32, height: 32, borderRadius: 7, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)', fontFamily: 'var(--display)', fontWeight: 700 }}>A</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 13.5, lineHeight: 1.15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Applecross Cricket Cl…</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--pb-faint)' }}>Better<span style={{ color: 'var(--pb-brand)' }}>Select</span></div>
          </div>
        </div>
        <a className="bs-back">← Back to admin</a>
      </div>
      <nav className="bs-nav">
        {NAV.map((n) => (
          <a key={n.label} className={'bs-navitem' + (n.active ? ' active' : '')}>
            <Icon name={n.icon} size={18} /><span>{n.label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('bs-theme') || 'light');
  const [view, setView] = useState(() => { const p = new URLSearchParams(location.search).get('view'); if (p === 'B' || p === 'C') return p; const v = localStorage.getItem('bs-view'); return (v === 'B' || v === 'C') ? v : 'B'; });
  const [navOpen, setNavOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const sel = useSelection();

  useEffect(() => { localStorage.setItem('bs-theme', theme); }, [theme]);
  useEffect(() => { localStorage.setItem('bs-view', view); }, [view]);

  const flash = useCallback((msg) => { setToast(msg); clearTimeout(window.__t); window.__t = setTimeout(() => setToast(null), 1900); }, []);

  // Global drop semantics shared by every direction.
  const onDrop = useCallback((target, item) => {
    if (target.kind === 'slot') {
      if (item.kind === 'pool') sel.place(target.idx, item.player.id);
      else if (item.kind === 'slot') sel.move(item.idx, target.idx);
    } else if (target.kind === 'pool') {
      if (item.kind === 'slot') sel.removeAt(item.idx);
    }
  }, [sel]);

  const Direction = { B: DirectionB, C: DirectionC }[view];

  return (
    <div className={'bs-root' + (navOpen ? ' navopen' : '')} data-theme={theme}>
      <Sidebar />
      {navOpen && <div className="bs-scrim show" onClick={() => setNavOpen(false)} />}

      <div className="bs-main">
        <header className="bs-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <button className="bs-burger" onClick={() => setNavOpen((o) => !o)} aria-label="Menu">☰</button>
            <h1 style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 20, margin: 0 }}>Selection</h1>
            <span className="bs-headdiv" />
            <ViewToggle value={view} onChange={setView} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button className="bs-themebtn" onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))} title="Toggle theme">
              <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
            </button>
            <Btn variant="soft" sm icon="share" className="bs-share-btn" onClick={() => flash('Share sheet opened')}><span className="bs-hide-sm">Share</span></Btn>
            <Btn variant="primary" sm icon="check" onClick={() => flash(`Saved XI · ${sel.count} players`)}>Save<span className="bs-hide-sm"> XI</span> ({sel.count})</Btn>
          </div>
        </header>

        <main className="bs-content">
          <DnD onDrop={onDrop}>
            <Direction sel={sel} flash={flash} />
          </DnD>
        </main>
      </div>

      {toast && <div className="bs-toast">{toast}</div>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
