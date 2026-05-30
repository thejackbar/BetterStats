/* bs-app.jsx — assembles the cleaned module + 3 selection directions + mobile
   onto the design canvas. */

/* ── Light module placeholders (Fixtures / Teams / Ladders) ─────────────── */
const CLUB_FIXTURES = [
  { date: '6 Jun', round: 9, current: true, games: [
    { team: '1st XI', grade: 'A-Grade', opp: 'Nedlands', ha: 'H', venue: 'Tompkins Park', time: '12:30 PM' },
    { team: '2nd XI', grade: 'B-Grade', opp: 'Nedlands', ha: 'A', venue: 'College Park', time: '12:30 PM' },
    { team: '3rd XI', grade: 'C-Grade', opp: 'Melville', ha: 'H', venue: 'Heathcote Res', time: '1:00 PM' },
    { team: '4th XI', grade: 'D-Grade', opp: 'Willetton', ha: 'A', venue: 'Burrendah Res', time: '1:00 PM' },
  ] },
  { date: '13 Jun', round: 10, games: [
    { team: '1st XI', grade: 'A-Grade', opp: 'Fremantle', ha: 'A', venue: 'Stevens Res', time: '12:30 PM' },
    { team: '2nd XI', grade: 'B-Grade', opp: 'Fremantle', ha: 'H', venue: 'Tompkins Park', time: '12:30 PM' },
    { team: '3rd XI', grade: 'C-Grade', opp: 'Cottesloe', ha: 'A', venue: 'Peters Place', time: '1:00 PM' },
    { team: '4th XI', grade: 'D-Grade', opp: 'Bicton', ha: 'H', venue: 'Heathcote Res', time: '1:00 PM' },
  ] },
  { date: '20 Jun', round: 11, games: [
    { team: '1st XI', grade: 'A-Grade', opp: 'Melville', ha: 'H', venue: 'Tompkins Park', time: '12:30 PM' },
    { team: '2nd XI', grade: 'B-Grade', opp: 'Melville', ha: 'A', venue: 'Tomato Lake', time: '12:30 PM' },
    { team: '3rd XI', grade: 'C-Grade', opp: 'BYE', ha: 'BYE', venue: '', time: '' },
    { team: '4th XI', grade: 'D-Grade', opp: 'Attadale', ha: 'H', venue: 'Heathcote Res', time: '1:00 PM' },
  ] },
  { date: '27 Jun', round: 12, games: [
    { team: '1st XI', grade: 'A-Grade', opp: 'Willetton', ha: 'A', venue: 'Burrendah Res', time: '12:30 PM' },
    { team: '2nd XI', grade: 'B-Grade', opp: 'Willetton', ha: 'H', venue: 'Tompkins Park', time: '12:30 PM' },
    { team: '3rd XI', grade: 'C-Grade', opp: 'UWA', ha: 'H', venue: 'Heathcote Res', time: '1:00 PM' },
    { team: '4th XI', grade: 'D-Grade', opp: 'Mt Pleasant', ha: 'A', venue: 'Wireless Hill', time: '1:00 PM' },
  ] },
];
const TEAM_TINT = { '1st XI': '#16c784', '2nd XI': '#3b82f6', '3rd XI': '#a855f7', '4th XI': '#f5b542' };

function FixtureRow({ g, current, onNav, top }) {
  const T = window.BST;
  const bye = g.ha === 'BYE';
  const tint = TEAM_TINT[g.team] || T.dim;
  return (
    <div className={top ? '' : 'pb-hair-t'} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '13px 18px' }}>
      <span style={{ width: 58, fontFamily: T.display, fontWeight: 700, fontSize: 13.5, color: tint }}>{g.team}</span>
      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.faint, width: 56 }}>{g.grade}</span>
      <div style={{ width: 1, height: 26, background: T.hair }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {bye ? (
          <span style={{ fontSize: 14, color: T.faint, fontStyle: 'italic' }}>Bye</span>
        ) : (
          <>
            <span style={{ fontSize: 14.5, fontWeight: 500 }}>
              <span style={{ color: T.faint, fontWeight: 400 }}>{g.ha === 'AWAY' || g.ha === 'A' ? '@ ' : 'vs '}</span>{g.opp}
            </span>
            <span style={{ fontSize: 12.5, color: T.faint, marginLeft: 10 }}>{g.venue} ({g.ha}) · {g.time}</span>
          </>
        )}
      </div>
      {!bye && (current && g.team === '1st XI'
        ? <Btn variant="primary" sm icon="selection" onClick={() => onNav('selection')}>Pick team</Btn>
        : <Btn variant="ghost" sm icon="selection" onClick={() => onNav('selection')}>Select</Btn>)}
    </div>
  );
}

function FixturesScreen({ onNav }) {
  const T = window.BST;
  const [grade, setGrade] = React.useState('all');
  const filterGames = (games) => grade === 'all' ? games : games.filter(g => g.team === grade);
  return (
    <BSShell active="fixtures" title="Fixtures" subtitle="The whole club's weekend — every grade, by round. Filter to one team when you need to." onNav={onNav}
      actions={<><Btn variant="ghost" sm icon="fixtures">Add fixture</Btn><Btn variant="soft" sm icon="bolt">Sync</Btn></>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Segmented value={grade} onChange={setGrade} options={[
            { value: 'all', label: 'Whole club' }, { value: '1st XI', label: '1st XI' }, { value: '2nd XI', label: '2nd XI' },
            { value: '3rd XI', label: '3rd XI' }, { value: '4th XI', label: '4th XI' },
          ]} />
          <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11.5, color: T.faint }}>{CLUB_FIXTURES.length} rounds · 4 teams</span>
        </div>
        <div className="bs-scroll" style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {CLUB_FIXTURES.map((wk, wi) => {
            const games = filterGames(wk.games);
            if (!games.length) return null;
            return (
              <div key={wi} className="pb-card" style={{ flexShrink: 0, overflow: 'hidden', background: T.surface,
                border: wk.current ? '1px solid rgba(22,199,132,0.3)' : `1px solid ${T.hair}` }}>
                <div className="pb-hair-b" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 18px',
                  background: wk.current ? 'rgba(22,199,132,0.05)' : T.surface2 }}>
                  <span style={{ fontFamily: T.display, fontWeight: 700, fontSize: 16 }}>Sat {wk.date}</span>
                  <span className="eyebrow">Round {wk.round}</span>
                  {wk.current && <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.accent, background: 'rgba(22,199,132,0.12)', padding: '2px 8px', borderRadius: 999 }}>THIS WEEKEND</span>}
                  <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.faint }}>{games.filter(g => g.ha !== 'BYE').length} games</span>
                </div>
                {games.map((g, gi) => <FixtureRow key={gi} g={g} current={wk.current} onNav={onNav} top={gi === 0} />)}
              </div>
            );
          })}
        </div>
      </div>
    </BSShell>
  );
}

/* ── The live module (nav swaps screens; flow runs av → selection) ──────── */
function BSModule() {
  const [tab, setTab] = React.useState('overview');
  const screens = {
    overview: (p) => <OverviewScreen {...p} />,
    players: (p) => <PlayersScreen {...p} layout="split" />,
    fixtures: (p) => <FixturesScreen {...p} />,
    teams: (p) => <TeamsScreen {...p} />,
    availability: (p) => <AvailabilityScreen {...p} />,
    selection: (p) => <SelectionC {...p} subtitle="Pick your XI for Saturday" />,
    ladders: (p) => <LaddersScreen {...p} />,
  };
  return screens[tab]({ onNav: setTab });
}

/* ── Mobile quick-task frames ───────────────────────────────────────────── */
function MobileFrame({ children }) {
  const T = window.BST;
  return (
    <div style={{ width: 390, height: 844, borderRadius: 44, padding: 11, background: '#05070c',
      boxShadow: '0 0 0 2px #1d2331, 0 30px 60px -20px rgba(0,0,0,0.7)' }}>
      <div style={{ width: '100%', height: '100%', borderRadius: 34, overflow: 'hidden', background: T.bg, position: 'relative', display: 'flex', flexDirection: 'column' }}>
        <div style={{ height: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 26px', flexShrink: 0 }}>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600 }}>9:41</span>
          <span style={{ display: 'flex', gap: 5, color: T.dim, fontSize: 11 }}>●●● ▮</span>
        </div>
        {children}
      </div>
    </div>
  );
}

function MobileAvailability() {
  const T = window.BST;
  const squad = BS_PLAYERS.filter(p => p.squads.includes('1st XI') && !p.dormant);
  const [av, setAv] = React.useState(() => Object.fromEntries(squad.map(p => [p.id, p.avail])));
  const set3 = (id, s) => setAv(a => ({ ...a, [id]: s }));
  const responded = squad.filter(p => av[p.id] !== 'NO_RESPONSE').length;
  return (
    <MobileFrame>
      <div style={{ padding: '6px 18px 14px', borderBottom: `1px solid ${T.hair}` }}>
        <div className="eyebrow" style={{ color: T.accent }}>Availability · Sat 6 Jun</div>
        <div style={{ fontFamily: T.display, fontWeight: 800, fontSize: 22, marginTop: 5 }}>1st XI vs Nedlands</div>
        <div style={{ marginTop: 12 }}><AvailSummary players={squad.map(p => ({ ...p, avail: av[p.id] }))} compact /></div>
      </div>
      <div className="bs-scroll" style={{ flex: 1, overflow: 'auto', padding: '6px 0' }}>
        {squad.map(p => (
          <div key={p.id} style={{ display: 'flex', flexDirection: 'column', gap: 9, padding: '11px 18px', borderBottom: `1px solid ${T.hair}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
              <Avatar p={p} size={32} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 500 }}>{p.name}</div>
                <div style={{ marginTop: 2 }}><RoleChips roles={p.roles} muted /></div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 7 }}>
              {[['AVAILABLE', 'In'], ['MAYBE', 'Maybe'], ['UNAVAILABLE', 'Out']].map(([s, l]) => {
                const on = av[p.id] === s;
                const a = BS_AVAIL[s];
                return (
                  <button key={s} onClick={() => set3(p.id, s)} style={{ flex: 1, height: 44, borderRadius: 10, cursor: 'pointer',
                    fontFamily: T.display, fontWeight: 600, fontSize: 14, transition: 'all .12s',
                    border: `1.5px solid ${on ? a.text : T.hair2}`, background: on ? a.tint : 'transparent', color: on ? a.text : T.faint }}>{l}</button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div style={{ padding: 16, borderTop: `1px solid ${T.hair}`, display: 'flex', alignItems: 'center', gap: 12, background: T.surface }}>
        <div style={{ flex: 1 }}>
          <div className="num" style={{ fontFamily: T.display, fontWeight: 700, fontSize: 16 }}>{responded}/{squad.length}</div>
          <div style={{ fontSize: 11.5, color: T.faint }}>responded</div>
        </div>
        <Btn variant="primary" icon="selection" style={{ flex: 2, justifyContent: 'center' }}>Pick team</Btn>
      </div>
    </MobileFrame>
  );
}

function MobileTeamSheet() {
  const T = window.BST;
  const xi = BS_DEFAULT_XI.map((id, i) => ({ p: byId(id), isCaptain: id === 'p1', isKeeper: id === 'p10', n: i + 1 }));
  return (
    <MobileFrame>
      <div style={{ padding: '6px 18px 14px', borderBottom: `1px solid ${T.hair}`, background: 'linear-gradient(160deg, rgba(22,199,132,0.10), transparent 60%)' }}>
        <div className="eyebrow" style={{ color: T.accent }}>Team named · Round 9</div>
        <div style={{ fontFamily: T.display, fontWeight: 800, fontSize: 22, marginTop: 5 }}>1st XI vs Nedlands</div>
        <div style={{ fontSize: 12.5, color: T.dim, marginTop: 4 }}>Sat 6 Jun · Tompkins Park · 12:30 PM</div>
      </div>
      <div className="bs-scroll" style={{ flex: 1, overflow: 'auto' }}>
        {xi.map(e => (
          <div key={e.p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 18px', borderBottom: `1px solid ${T.hair}` }}>
            <span className="num" style={{ width: 20, textAlign: 'right', color: T.faint, fontSize: 14 }}>{e.n}</span>
            <Dot status={e.p.avail} />
            <Avatar p={e.p} size={32} />
            <span style={{ flex: 1, fontSize: 15, fontWeight: 500 }}>{e.p.name} {e.isCaptain && <Tag>C</Tag>} {e.isKeeper && <Tag>WK</Tag>}</span>
            <RoleChips roles={e.p.roles} muted />
          </div>
        ))}
      </div>
      <div style={{ padding: 16, borderTop: `1px solid ${T.hair}`, display: 'flex', gap: 10, background: T.surface }}>
        <Btn variant="soft" icon="share" style={{ flex: 1, justifyContent: 'center' }}>Share</Btn>
        <Btn variant="primary" icon="check" style={{ flex: 1, justifyContent: 'center' }}>Confirm XI</Btn>
      </div>
    </MobileFrame>
  );
}

/* ── Canvas ─────────────────────────────────────────────────────────────── */
function Note({ children }) {
  return <div style={{ fontSize: 13.5, lineHeight: 1.55, color: '#5a4a2a' }}>{children}</div>;
}

function App() {
  return (
    <DesignCanvas>
      <DCSection id="module" title="BetterSelect — the module, cleaned up"
        subtitle="One calm surface. Sentence-case labels, more breathing room, and a 'this weekend' overview that flows straight into picking. The sidebar nav is live — click around.">
        <DCArtboard id="live" label="Live module · click around" width={1360} height={860}>
          <BSModule />
        </DCArtboard>
      </DCSection>

      <DCSection id="players" title="Players"
        subtitle="A cleaner home for player profiles (no more cramped modal). Management fields sit beside a selection snapshot — availability, assigned squad, recent form (batting, bowling, catches). Click an avatar anywhere to jump into a profile.">
        <DCArtboard id="pl-split" label="Master–detail (list + profile)" width={1360} height={860}>
          <PlayersScreen layout="split" />
        </DCArtboard>
      </DCSection>

      <DCSection id="selection-c" title="Selection — Option C"
        subtitle="The chosen direction: pool on the left, the batting-order slots on the right. Focus a slot, tap a player (or drag). Click any availability dot to update it on the spot. Same here as in the live module — this frame is for close-up review.">
        <DCArtboard id="dirC" label="Option C · batting-order slots" width={1360} height={860}>
          <SelectionC subtitle="Pick your XI for Saturday" />
        </DCArtboard>
      </DCSection>

      <DCSection id="mobile" title="Mobile — quick tasks"
        subtitle="The two things people do on a phone: mark availability fast, and read/share the named side.">
        <DCArtboard id="mob-av" label="Quick-mark availability" width={390} height={844}>
          <MobileAvailability />
        </DCArtboard>
        <DCArtboard id="mob-sheet" label="Named team sheet" width={390} height={844}>
          <MobileTeamSheet />
        </DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
