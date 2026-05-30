/* bs-overview.jsx — cleaned module landing. Centres on "this weekend" and
   threads straight into availability → selection. */

function fxSquad() {
  // Players eligible for the 1st XI fixture: 1st XI squad + anyone not clashing.
  return BS_PLAYERS.filter(p => (p.squads.includes('1st XI')) && !p.dormant);
}

function OvStat({ value, label, accent }) {
  const T = window.BST;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span className="num" style={{ fontFamily: T.display, fontSize: 26, fontWeight: 700, lineHeight: 1, color: accent || T.text }}>{value}</span>
      <span style={{ fontSize: 12, color: T.faint }}>{label}</span>
    </div>
  );
}

function AttnRow({ tone, text, action, onClick, last }) {
  const T = window.BST;
  const c = tone === 'risk' ? T.red : tone === 'warn' ? T.amber : T.dim;
  return (
    <button onClick={onClick} className={last ? '' : 'pb-hair-b'} style={{ width: '100%', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 11,
      padding: '11px 16px', background: 'transparent', border: 'none', borderBottom: last ? 'none' : `1px solid ${T.hair}`, cursor: 'pointer' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }} />
      <span style={{ flex: 1, fontSize: 13.5, color: T.text }}>{text}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: T.accent, fontWeight: 500 }}>{action} <Icon name="chevron" size={13} /></span>
    </button>
  );
}

function NeedsAttention({ squad, onNav }) {
  const T = window.BST;
  const noResp = squad.filter(p => p.avail === 'NO_RESPONSE').length;
  const keeperRisk = squad.find(p => p.roles.includes('WKT') && p.avail !== 'AVAILABLE');
  const items = [];
  if (keeperRisk) items.push({ tone: 'risk', text: <>Your likely keeper <b style={{ fontWeight: 600 }}>{keeperRisk.name}</b> hasn't confirmed for Saturday</>, action: 'Chase', go: 'availability' });
  if (noResp > 0) items.push({ tone: 'warn', text: <><b style={{ fontWeight: 600 }}>{noResp} players</b> haven't set their availability</>, action: 'Open availability', go: 'availability' });
  items.push({ tone: 'info', text: <><b style={{ fontWeight: 600 }}>3 of 4</b> weekend teams still need an XI named</>, action: 'View fixtures', go: 'fixtures' });

  return (
    <div className="pb-card" style={{ overflow: 'hidden', background: T.surface }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '11px 16px', borderBottom: `1px solid ${T.hair}` }}>
        <Icon name="info" size={15} style={{ color: T.amber }} />
        <span style={{ fontFamily: T.display, fontWeight: 700, fontSize: 14 }}>Needs attention</span>
        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.amber, background: 'rgba(245,181,66,0.12)', padding: '2px 7px', borderRadius: 999 }}>{items.length}</span>
      </div>
      {items.map((it, i) => (
        <AttnRow key={i} tone={it.tone} text={it.text} action={it.action} last={i === items.length - 1} onClick={() => onNav && onNav(it.go)} />
      ))}
    </div>
  );
}

function UpcomingCard({ fx, players, selected, onNav }) {
  const T = window.BST;
  const t = bsTally(players);
  const total = players.length;
  const segs = BS_AVAIL_ORDER.map(s => ({ s, n: t[s] })).filter(x => x.n > 0);
  return (
    <button onClick={() => onNav && onNav('selection')} className="pb-card" style={{
      textAlign: 'left', cursor: 'pointer', padding: 0, overflow: 'hidden', background: T.surface, color: T.text,
      border: `1px solid ${fx.current ? 'rgba(22,199,132,0.35)' : T.hair}`, display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '13px 15px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
          <span className="eyebrow" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fx.sub.split(' · ')[0]} · {fx.label.replace('Sat ', '')}</span>
          {fx.current && <span style={{ flexShrink: 0, fontFamily: T.mono, fontSize: 9, color: T.accent, background: 'rgba(22,199,132,0.12)', padding: '2px 7px', borderRadius: 999 }}>THIS WK</span>}
        </div>
        <div style={{ fontFamily: T.display, fontWeight: 700, fontSize: 17, marginTop: 8 }}>{fx.sub.split(' · ')[1]}</div>
        <div style={{ display: 'flex', height: 6, borderRadius: 999, overflow: 'hidden', background: T.surface2, marginTop: 12 }}>
          {segs.map(({ s, n }) => <div key={s} style={{ flex: n, background: s === 'NO_RESPONSE' ? T.faintest : BS_AVAIL[s].dot, opacity: s === 'NO_RESPONSE' ? 0.5 : 1 }} />)}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 9, fontSize: 11.5 }}>
          <span style={{ color: T.dim }} className="num"><b style={{ color: T.accent }}>{t.AVAILABLE}</b> / {total} available</span>
          <span style={{ color: selected ? T.accent : T.faint }} className="num">{selected ? `${selected} named` : 'Not picked'}</span>
        </div>
      </div>
      <div className="pb-hair-t" style={{ padding: '9px 15px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: T.faint }}>
        <span style={{ fontSize: 11.5 }}>{selected === 11 ? 'XI confirmed' : selected ? 'In progress' : 'Pick a side'}</span>
        <Icon name="arrow" size={15} style={{ color: T.dim }} />
      </div>
    </button>
  );
}

function OverviewScreen({ onNav, chrome = true }) {
  const T = window.BST;
  const squad = fxSquad();
  const t = bsTally(squad);
  const responded = squad.length - t.NO_RESPONSE;

  const content = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, height: '100%' }}>
      {/* This-weekend hero */}
      <div className="pb-card" style={{ overflow: 'hidden', position: 'relative',
        background: 'linear-gradient(120deg, rgba(22,199,132,0.10), rgba(16,20,29,0) 55%), var(--pb-surface)',
        border: '1px solid rgba(22,199,132,0.25)' }}>
        <div style={{ display: 'flex', gap: 28, padding: '22px 24px', alignItems: 'stretch', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 340px', minWidth: 300 }}>
            <span className="eyebrow" style={{ color: T.accent }}>This weekend · Round {BS_FIXTURE.round}</span>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
              <h2 style={{ margin: 0, fontFamily: T.display, fontWeight: 800, fontSize: 30, letterSpacing: '-0.02em' }}>
                {BS_FIXTURE.team} <span style={{ color: T.faint, fontWeight: 600 }}>vs</span> {BS_FIXTURE.opponent}
              </h2>
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 12, color: T.dim, fontSize: 13.5, flexWrap: 'wrap' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><Icon name="fixtures" size={15} style={{ color: T.faint }} /> {BS_FIXTURE.date_label}, {BS_FIXTURE.start_time}</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><Icon name="teams" size={15} style={{ color: T.faint }} /> {BS_FIXTURE.venue} (H)</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>{BS_FIXTURE.grade}</span>
            </div>
            <div style={{ marginTop: 20, maxWidth: 460 }}>
              <AvailSummary players={squad} hideTotal />
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10, minWidth: 200 }}>
            <Btn variant="primary" icon="selection" onClick={() => onNav && onNav('selection')} style={{ fontSize: 15, padding: '13px 20px' }}>Pick this team</Btn>
            <Btn variant="soft" icon="availability" onClick={() => onNav && onNav('availability')}>Review availability</Btn>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: T.faint, fontSize: 11.5, marginTop: 2, justifyContent: 'center' }}>
              <Icon name="info" size={13} /> {squad.length - responded} still to respond
            </div>
          </div>
        </div>
      </div>

      {/* Pulse stats */}
      <div className="pb-card" style={{ display: 'flex', gap: 0, padding: '4px 0' }}>
        {[
          { v: `${responded}/${squad.length}`, l: 'Responded', a: null },
          { v: t.AVAILABLE, l: 'Available', a: T.accent },
          { v: t.MAYBE, l: 'Maybe', a: T.amber },
          { v: t.UNAVAILABLE, l: 'Unavailable', a: T.red },
          { v: '11', l: 'To select', a: null },
        ].map((s, i) => (
          <div key={i} style={{ flex: 1, padding: '14px 22px', borderLeft: i ? `1px solid ${T.hair}` : 'none' }}>
            <OvStat value={s.v} label={s.l} accent={s.a} />
          </div>
        ))}
      </div>

      {/* Needs attention */}
      <NeedsAttention squad={squad} onNav={onNav} />

      {/* Upcoming */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontFamily: T.display, fontWeight: 700, fontSize: 16 }}>Upcoming fixtures</h3>
          <Btn variant="ghost" sm onClick={() => onNav && onNav('fixtures')}>All fixtures</Btn>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
          <UpcomingCard fx={BS_DATES[0]} players={squad} selected={11} onNav={onNav} />
          <UpcomingCard fx={BS_DATES[1]} players={squad.slice(0, 20)} selected={0} onNav={onNav} />
          <UpcomingCard fx={BS_DATES[2]} players={squad.slice(2, 21)} selected={0} onNav={onNav} />
          <UpcomingCard fx={BS_DATES[3]} players={squad.slice(1, 18)} selected={0} onNav={onNav} />
        </div>
      </div>
    </div>
  );

  if (!chrome) return content;
  return (
    <BSShell active="overview" title="Overview" subtitle="Your week at a glance" onNav={onNav}
      actions={<Btn variant="ghost" sm icon="share">Share</Btn>}>
      {content}
    </BSShell>
  );
}

Object.assign(window, { OverviewScreen, fxSquad });
