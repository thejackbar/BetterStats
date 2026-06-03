/* BetterIQ — module chrome: sidebar + header. Renders all 8 nav items (the real
   IA); the two hero screens navigate, the rest are shown as part of the tier
   but marked as not in this preview. */
const { useState: useStateL } = React;

const IQ_NAV = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { group: 'Scout the opposition' },
  { id: 'preview', label: 'Match preview', icon: 'fixtures' },
  { id: 'opposition', label: 'Opposition club', icon: 'search' },
  { id: 'opposition-player', label: 'Opposition player', icon: 'player' },
  { group: 'Know your club' },
  { id: 'selection', label: 'Selection', icon: 'selection' },
  { id: 'trends', label: 'Player trends', icon: 'trend' },
  { id: 'team', label: 'Team analysis', icon: 'teams' },
  { id: 'review', label: 'Match review', icon: 'overview' },
];

function NavList({ route, onNavigate }) {
  return (
    <nav className="flex flex-col gap-0.5 px-3 py-3">
      {IQ_NAV.map((item, idx) => {
        if (item.group) return (
          <div key={'g' + idx} className="iq-eyebrow px-3 pt-4 pb-1.5" style={{ fontSize: 9, color: 'var(--pb-faintest)' }}>{item.group}</div>
        );
        const active = route === item.id;
        return (
          <button key={item.id}
            onClick={() => onNavigate(item.id)}
            title={item.label}
            className="group relative flex items-center gap-3 transition-colors text-left"
            style={{
              padding: '9px 12px', borderRadius: 10, fontSize: 13.5,
              color: active ? 'var(--pb-accent)' : 'var(--pb-dim)',
              background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent',
              cursor: 'pointer',
              fontWeight: active ? 600 : 500,
            }}
            onMouseEnter={e => { if (!active) { e.currentTarget.style.color = 'var(--pb-text)'; e.currentTarget.style.background = 'var(--pb-surface2)'; } }}
            onMouseLeave={e => { if (!active) { e.currentTarget.style.color = 'var(--pb-dim)'; e.currentTarget.style.background = 'transparent'; } }}>
            {active && <span className="absolute left-0 top-1/2 -translate-y-1/2" style={{ width: 3, height: 18, borderRadius: 99, background: 'var(--pb-accent)' }} />}
            <Icon name={item.icon} size={17} className="shrink-0" />
            <span className="iq-display flex-1">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center shrink-0 iq-display font-bold"
          style={{ width: 38, height: 38, borderRadius: 11, fontSize: 16,
            background: 'linear-gradient(150deg, var(--iq-violet-bright), var(--iq-violet-deep))',
            color: '#fff', boxShadow: '0 6px 18px -8px var(--pb-accent)' }}>A</div>
        <div className="min-w-0">
          <div className="iq-display font-bold text-[15px] leading-none truncate">Applecross</div>
          <div className="iq-mono mt-1" style={{ fontSize: 11, letterSpacing: '0.04em', color: 'var(--pb-faint)' }}>
            Better<span style={{ color: 'var(--pb-accent)', fontWeight: 700 }}>IQ</span>
          </div>
        </div>
      </div>
      <button className="mt-3 iq-mono text-left whitespace-nowrap transition-colors hover:text-pb-faint" style={{ fontSize: 11, color: 'var(--pb-faintest)' }}>← Back to admin</button>
    </div>
  );
}

function ThemeToggle({ theme, onToggle }) {
  const dark = theme === 'dark';
  return (
    <button onClick={onToggle} title="Toggle theme"
      className="flex items-center justify-center transition hover:brightness-125"
      style={{ width: 34, height: 34, borderRadius: 9, border: '1px solid var(--pb-hairline2)', background: 'var(--pb-surface2)', color: 'var(--pb-dim)' }}>
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
      )}
    </button>
  );
}

function IQLayout({ title, eyebrow, actions, route, onNavigate, theme, onToggleTheme, contextBar, children }) {
  const [mobileOpen, setMobileOpen] = useStateL(false);
  const SIDEBAR_W = 248;
  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col sticky top-0 shrink-0"
        style={{ width: SIDEBAR_W, height: '100vh', background: 'var(--pb-surface)', borderRight: '1px solid var(--pb-hairline)' }}>
        <Brand />
        <div className="flex-1 overflow-y-auto iq-scroll"><NavList route={route} onNavigate={onNavigate} /></div>
        <div className="px-5 py-4 iq-mono" style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--pb-faintest)', borderTop: '1px solid var(--pb-hairline)', textTransform: 'uppercase' }}>
          Best tier · Analytics
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 flex flex-col" style={{ width: SIDEBAR_W, background: 'var(--pb-surface)', borderRight: '1px solid var(--pb-hairline)' }}>
            <Brand />
            <div className="flex-1 overflow-y-auto iq-scroll"><NavList route={route} onNavigate={(r) => { onNavigate(r); setMobileOpen(false); }} /></div>
          </aside>
        </div>
      )}

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-4 px-5 md:px-8"
          style={{ height: 64, background: 'color-mix(in srgb, var(--pb-surface) 80%, transparent)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', borderBottom: '1px solid var(--pb-hairline)' }}>
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setMobileOpen(true)} className="md:hidden text-pb-dim" style={{ fontSize: 20 }}>☰</button>
            <div className="min-w-0">
              {eyebrow && <div className="iq-eyebrow leading-none" style={{ fontSize: 9 }}>{eyebrow}</div>}
              <h1 className="iq-display font-bold text-[18px] md:text-[20px] leading-tight truncate" style={{ letterSpacing: '-0.01em', marginTop: eyebrow ? 3 : 0 }}>{title}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2.5 shrink-0">
            {actions}
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
            <div className="hidden sm:flex items-center gap-2.5 pl-2.5" style={{ borderLeft: '1px solid var(--pb-hairline)' }}>
              <div className="text-right leading-tight whitespace-nowrap">
                <div className="text-[12.5px] font-medium">M. Drummond</div>
                <div className="iq-mono" style={{ fontSize: 9.5, color: 'var(--pb-faint)' }}>Selector</div>
              </div>
              <div className="flex items-center justify-center iq-display font-bold" style={{ width: 32, height: 32, borderRadius: 9, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)', fontSize: 12, color: 'var(--pb-dim)' }}>MD</div>
            </div>
          </div>
        </header>
        {contextBar}
        <main className="flex-1 px-5 md:px-8 py-7 md:py-9 w-full mx-auto" style={{ maxWidth: 1320 }}>{children}</main>
      </div>
    </div>
  );
}

Object.assign(window, { IQLayout });
