/* BetterIQ — root: in-app router + theme + tweaks */
const { useState: useStateA } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "displayFont": "Archivo",
  "cardStyle": "hairline"
}/*EDITMODE-END*/;

const FONT_STACK = {
  'Archivo': "'Archivo', system-ui, sans-serif",
  'Space Grotesk': "'Space Grotesk', system-ui, sans-serif",
  'Saira': "'Saira', system-ui, sans-serif",
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [route, setRoute] = useStateA('overview');
  const [selection, setSelection] = useStateA(null);
  const [cheat, setCheat] = useStateA(false);
  const [ctx, setCtx] = useStateA(DEFAULT_CTX);

  const goScout = (fx) => { setSelection(fx ? { opponent: fx.opp_key, name: fx.opponent_name, fixtureId: fx.fixture_id } : null); setRoute('opposition'); window.scrollTo(0, 0); };
  const navigate = (r) => { if (r === 'opposition') setSelection(null); setRoute(r); window.scrollTo(0, 0); };

  const titles = {
    overview: { title: 'Overview', eyebrow: 'BetterIQ' },
    preview: { title: 'Match preview', eyebrow: 'Scout the opposition' },
    opposition: { title: 'Opposition analysis', eyebrow: 'Scout the opposition' },
    'opposition-player': { title: 'Opposition player', eyebrow: 'Scout the opposition' },
    selection: { title: 'Selection analysis', eyebrow: 'Know your club' },
    trends: { title: 'Player trends', eyebrow: 'Know your club' },
    team: { title: 'Team analysis', eyebrow: 'Know your club' },
    review: { title: 'Match review', eyebrow: 'Know your club' },
  };
  const head = titles[route] || titles.overview;

  const screen = () => {
    switch (route) {
      case 'overview': return <Overview onScout={goScout} onNavigate={navigate} ctx={ctx} />;
      case 'preview': return <Preview onScout={goScout} onNavigate={navigate} onCheatSheet={() => setCheat(true)} ctx={ctx} />;
      case 'opposition': return <Scout selection={selection} onClearSelection={() => setSelection(null)} onCheatSheet={() => setCheat(true)} ctx={ctx} />;
      case 'opposition-player': return <OppPlayer onScout={goScout} onNavigate={navigate} ctx={ctx} />;
      case 'selection': return <Selection onNavigate={navigate} ctx={ctx} />;
      case 'trends': return <Trends onNavigate={navigate} ctx={ctx} />;
      case 'team': return <TeamAnalysis ctx={ctx} />;
      case 'review': return <Review onScout={goScout} ctx={ctx} />;
      default: return <Overview onScout={goScout} onNavigate={navigate} ctx={ctx} />;
    }
  };

  return (
    <div className="iq-root" data-theme={t.theme} data-card={t.cardStyle}
      style={{ '--iq-font-display': FONT_STACK[t.displayFont] || FONT_STACK.Archivo }}>
      <IQLayout
        title={head.title} eyebrow={head.eyebrow} route={route} onNavigate={navigate}
        theme={t.theme} onToggleTheme={() => setTweak('theme', t.theme === 'dark' ? 'light' : 'dark')}
        contextBar={<ContextBar ctx={ctx} onChange={setCtx} filters={ROUTE_FILTERS[route]} />}>
        {screen()}
      </IQLayout>

      {cheat && <CheatSheet onClose={() => setCheat(false)} />}

      <TweaksPanel>
        <TweakSection label="Appearance" />
        <TweakRadio label="Theme" value={t.theme} options={['dark', 'light']} onChange={v => setTweak('theme', v)} />
        <TweakRadio label="Cards" value={t.cardStyle} options={['hairline', 'glass']} onChange={v => setTweak('cardStyle', v)} />
        <TweakSection label="Typography" />
        <TweakSelect label="Display font" value={t.displayFont} options={['Archivo', 'Space Grotesk', 'Saira']} onChange={v => setTweak('displayFont', v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
