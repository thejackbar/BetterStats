/* BetterSelect — Selection INDEX (landing) redesign · v2 "matchday board"
 * A weekend can run 15 teams at once — so this is a dense, scannable list, not
 * a wall of tall cards. Compact rows grouped by matchday, search + status
 * filters, click-to-open, chevron-to-peek. Same pb-* tokens + atom kit.
 */
const { useState, useEffect, useMemo, useCallback } = React;
const BS = window.BS;

const TODAY = new Date('2026-07-02T09:00:00');

/* ── Detailed rosters for the two flagship teams (reuse the rich pool) ───── */
const sP = (() => { let i = 0; return (o) => Object.assign({ id: 's' + (++i), tier: 2, squad: 'Applecross 2nd XI', photo: null, recent: [] }, o); })();
const SECOND_XI = [
  sP({ name: 'Birbeck, James',      player_role: 'Batter',      skills: ['BAT'], batting_hand: 'RIGHT', bowl: null,                    opener: true,  availability: 'AVAILABLE',   form: 'warm'   }),
  sP({ name: 'Ahmed, Shaban',       player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Off spin',              opener: false, availability: 'AVAILABLE',   form: 'steady' }),
  sP({ name: 'Akram, Furqan',       player_role: 'Bowler',      skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast',        opener: false, availability: 'AVAILABLE',   form: 'hot'    }),
  sP({ name: 'Afridi, Saad',        player_role: 'Batter',      skills: ['BAT'], batting_hand: 'RIGHT', bowl: null,                    opener: false, availability: 'AVAILABLE',   form: 'warm'   }),
  sP({ name: 'Alborn, Sam',         player_role: 'Batter',      skills: ['BAT'], batting_hand: 'LEFT',  bowl: null,                    opener: false, availability: 'AVAILABLE',   form: 'steady' }),
  sP({ name: 'Kumar, Amit Verma',   player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Right-arm medium',      opener: false, availability: 'AVAILABLE',   form: 'warm'   }),
  sP({ name: 'Ammar, Muhammad',     player_role: 'Bowler',      skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Leg spin',              opener: false, availability: 'AVAILABLE',   form: 'steady' }),
  sP({ name: 'Anandagoda, Pubudu',  player_role: 'Wicketkeeper-Batter', skills: ['WKT','BAT'], batting_hand: 'RIGHT', bowl: null,      opener: false, availability: 'AVAILABLE',   form: 'warm'   }),
  sP({ name: 'Aplin, Sam',          player_role: 'Bowler',      skills: ['BWL'], batting_hand: 'LEFT',  bowl: 'Left-arm orthodox',     opener: false, availability: 'MAYBE', availability_reason: 'Tentative — work', form: 'steady' }),
  sP({ name: 'Appleyard, Ashleigh', player_role: 'Batter',      skills: ['BAT'], batting_hand: 'RIGHT', bowl: null,                    opener: false, availability: 'AVAILABLE',   form: 'hot'    }),
  sP({ name: 'Appuhamy, Dilash',    player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Off spin',              opener: false, availability: 'AVAILABLE',   form: 'warm'   }),
  sP({ name: 'Aren, Puru',          player_role: 'Bowler',      skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast-medium', opener: false, availability: 'NO_RESPONSE', form: 'steady' }),
  sP({ name: 'Affleck, Rob',        player_role: 'Batter',      skills: ['BAT'], batting_hand: 'RIGHT', bowl: null,                    opener: false, availability: 'AVAILABLE',   form: 'quiet'  }),
];
const FIRST_XI = BS.STARTING_XI.map((id) => BS.byId[id]);

/* ── The weekend's fixtures ─────────────────────────────────────────────────
 * Two carry full rosters (`players`); the rest carry a compact selection
 * summary (`sum`) — enough to scan & triage without fabricating 12 line-ups. */
const FIXTURES = [
  // ——— Saturday 4 July — seniors ———
  { key:'1st',  squad:'1st XI',  grade:'A', day:'Sat 4 Jul', iso:'2026-07-04', time:'13:00', opponent:'Wembley Districts', homeAway:'AWAY', venue:'Wembley Sports Park', target:11, capName:'Verdonk', wkName:'Baker', editedAgo:'edited yesterday', players:FIRST_XI, capId:'p8', wkId:'p7' },
  { key:'2nd',  squad:'2nd XI',  grade:'B', day:'Sat 4 Jul', iso:'2026-07-04', time:'13:00', opponent:'Melville',          homeAway:'HOME', venue:'Tompkins Park · No.2', target:11, capName:'Birbeck', wkName:'Anandagoda', editedAgo:'edited 2h ago', players:SECOND_XI, capId:'s1', wkId:'s8' },
  { key:'3rd',  squad:'3rd XI',  grade:'C', day:'Sat 4 Jul', iso:'2026-07-04', time:'12:30', opponent:'Fremantle',         homeAway:'AWAY', venue:'Stevens Reserve',     target:11, capName:'Mathers', wkName:'Tran', editedAgo:'edited 4h ago',
    sum:{ picked:9,  bal:{BAT:5,ALL:2,BWL:3,WKT:1}, avail:{AVAILABLE:7,MAYBE:1,NO_RESPONSE:1,UNAVAILABLE:0} } },
  { key:'4th',  squad:'4th XI',  grade:'D', day:'Sat 4 Jul', iso:'2026-07-04', time:'13:00', opponent:'Scarborough',       homeAway:'HOME', venue:'Tompkins Park · No.3', target:11, capName:'Hollis', wkName:'Webb', editedAgo:'edited 1d ago',
    sum:{ picked:11, bal:{BAT:6,ALL:2,BWL:3,WKT:1}, avail:{AVAILABLE:11,MAYBE:0,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'5th',  squad:'5th XI',  grade:'E', day:'Sat 4 Jul', iso:'2026-07-04', time:'12:30', opponent:'Gosnells',          homeAway:'AWAY', venue:'Sutherland Park',     target:11, capName:null, wkName:null, editedAgo:'started 1d ago',
    sum:{ picked:6,  bal:{BAT:4,ALL:1,BWL:1,WKT:0}, avail:{AVAILABLE:5,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'t20',  squad:'T20 Cup', grade:'T20', day:'Sat 4 Jul', iso:'2026-07-04', time:'18:00', opponent:'UWA',            homeAway:'HOME', venue:'Tompkins Park · No.1', target:11, capName:null, wkName:null, editedAgo:'not started',
    sum:{ picked:0,  bal:{BAT:0,ALL:0,BWL:0,WKT:0}, avail:{AVAILABLE:0,MAYBE:0,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'w1',   squad:"Women's 1st XI", grade:'W1', day:'Sat 4 Jul', iso:'2026-07-04', time:'10:00', opponent:'Willetton', homeAway:'HOME', venue:'Tompkins Park · No.2', target:11, capName:'Okafor', wkName:null, editedAgo:'edited 6h ago',
    sum:{ picked:10, bal:{BAT:6,ALL:2,BWL:2,WKT:0}, avail:{AVAILABLE:9,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'w2',   squad:"Women's 2nd XI", grade:'W2', day:'Sat 4 Jul', iso:'2026-07-04', time:'10:00', opponent:'Bayswater', homeAway:'AWAY', venue:'Crimea Park',         target:11, capName:'Marsh', wkName:'Ferreira', editedAgo:'edited 1d ago',
    sum:{ picked:11, bal:{BAT:5,ALL:3,BWL:2,WKT:1}, avail:{AVAILABLE:10,MAYBE:0,NO_RESPONSE:1,UNAVAILABLE:0} } },
  // ——— Sunday 5 July — juniors & masters ———
  { key:'u17',  squad:'Under 17s', grade:'U17', day:'Sun 5 Jul', iso:'2026-07-05', time:'09:00', opponent:'Rockingham',   homeAway:'HOME', venue:'Tompkins Park · No.3', target:11, capName:'Bell', wkName:'Baines', editedAgo:'edited 3h ago',
    sum:{ picked:11, bal:{BAT:6,ALL:2,BWL:2,WKT:1}, avail:{AVAILABLE:9,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:1} } },
  { key:'u15b', squad:'Under 15 Blue', grade:'U15', day:'Sun 5 Jul', iso:'2026-07-05', time:'08:30', opponent:'Kalamunda', homeAway:'AWAY', venue:'Stirk Park',         target:11, capName:'Woods', wkName:'Dagg', editedAgo:'edited 1d ago',
    sum:{ picked:11, bal:{BAT:5,ALL:3,BWL:3,WKT:1}, avail:{AVAILABLE:11,MAYBE:0,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'u15g', squad:'Under 15 Gold', grade:'U15', day:'Sun 5 Jul', iso:'2026-07-05', time:'08:30', opponent:'Midland-Guildford', homeAway:'HOME', venue:'Tompkins Park · No.4', target:11, capName:'Khan', wkName:'Perera', editedAgo:'edited 5h ago',
    sum:{ picked:9,  bal:{BAT:5,ALL:2,BWL:3,WKT:1}, avail:{AVAILABLE:8,MAYBE:0,NO_RESPONSE:1,UNAVAILABLE:0} } },
  { key:'u13',  squad:'Under 13s', grade:'U13', day:'Sun 5 Jul', iso:'2026-07-05', time:'08:00', opponent:'Joondalup',     homeAway:'HOME', venue:'Tompkins Park · No.5', target:11, capName:'Edwards', wkName:'Tan', editedAgo:'edited 1d ago',
    sum:{ picked:11, bal:{BAT:6,ALL:2,BWL:2,WKT:1}, avail:{AVAILABLE:10,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'vets', squad:'Veterans XI', grade:'VET', day:'Sun 5 Jul', iso:'2026-07-05', time:'13:00', opponent:'Subiaco-Floreat', homeAway:'AWAY', venue:'Rosalie Park',    target:11, capName:'Cooper', wkName:'Stopforth', editedAgo:'edited 2d ago',
    sum:{ picked:8,  bal:{BAT:5,ALL:2,BWL:2,WKT:1}, avail:{AVAILABLE:7,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:0} } },
  { key:'o50',  squad:'Masters O50', grade:'O50', day:'Sun 5 Jul', iso:'2026-07-05', time:'13:00', opponent:'Perth',       homeAway:'HOME', venue:'Tompkins Park · No.1', target:11, capName:'Berry', wkName:'Webb', editedAgo:'edited 1d ago',
    sum:{ picked:11, bal:{BAT:6,ALL:3,BWL:2,WKT:1}, avail:{AVAILABLE:10,MAYBE:1,NO_RESPONSE:0,UNAVAILABLE:0} } },
];

/* ── Derive count / balance / leadership / flags / status for a fixture ──── */
function summarize(fx) {
  let count, bal, avail, unavailableNames = [], keeperPresent, capName, wkName, wkOut = false;
  if (fx.players) {
    const has = (p, c) => (p.skills || []).includes(c);
    count = fx.players.length;
    bal = { BAT: 0, ALL: 0, BWL: 0, WKT: 0 };
    avail = { AVAILABLE: 0, MAYBE: 0, NO_RESPONSE: 0, UNAVAILABLE: 0 };
    fx.players.forEach((p) => {
      ['BAT', 'ALL', 'BWL', 'WKT'].forEach((c) => { if (has(p, c)) bal[c]++; });
      avail[p.availability] = (avail[p.availability] || 0) + 1;
      if (p.availability === 'UNAVAILABLE') unavailableNames.push(p.name.split(',')[0]);
    });
    const keeper = fx.players.find((p) => has(p, 'WKT'));
    keeperPresent = !!keeper;
    const cap = fx.players.find((p) => p.id === fx.capId);
    const wk = fx.players.find((p) => p.id === fx.wkId);
    capName = cap ? cap.name.split(',')[0] : null;
    wkName = wk ? wk.name.split(',')[0] : null;
    wkOut = wk && wk.availability === 'UNAVAILABLE';
  } else {
    const s = fx.sum;
    count = s.picked; bal = s.bal; avail = s.avail;
    keeperPresent = bal.WKT > 0;
    capName = fx.capName; wkName = fx.wkName;
    unavailableNames = avail.UNAVAILABLE > 0 ? [`${avail.UNAVAILABLE}`] : [];
  }
  const bowlers = bal.ALL + bal.BWL;

  const flags = [];
  if (count > 0 && count < fx.target) flags.push({ tone: 'amber', text: `${fx.target - count} short of XI` });
  if (wkOut) flags.push({ tone: 'red', text: 'Keeper out' });
  if (fx.players) unavailableNames.forEach((n, i) => { if (!(wkOut && i === unavailableNames.indexOf(wkName))) flags.push({ tone: 'red', text: `${n} unavailable` }); });
  else if (avail.UNAVAILABLE > 0) flags.push({ tone: 'red', text: `${avail.UNAVAILABLE} unavailable` });
  if (count >= 8 && !keeperPresent) flags.push({ tone: 'amber', text: 'No keeper named' });
  if (count >= 8 && bowlers < 5) flags.push({ tone: 'amber', text: 'Light on bowling' });
  if (count >= 8 && !capName) flags.push({ tone: 'amber', text: 'No captain named' });

  let status, statusLabel;
  if (count === 0) { status = 'progress'; statusLabel = 'Not started'; }
  else if (flags.some((f) => f.tone === 'red')) { status = 'attention'; statusLabel = 'Needs attention'; }
  else if (count >= fx.target && flags.length === 0) { status = 'ready'; statusLabel = 'Squad set'; }
  else if (count >= fx.target) { status = 'review'; statusLabel = 'Ready to review'; }
  else { status = 'progress'; statusLabel = 'In progress'; }

  return { count, target: fx.target, bal, bowlers, avail, keeperPresent, capName, wkName, wkOut, flags, status, statusLabel };
}

function daysUntil(iso) {
  const d = new Date(iso + 'T12:00:00');
  const diff = Math.round((d - TODAY) / 86400000);
  if (diff <= 0) return 'today'; if (diff === 1) return 'tomorrow'; return `in ${diff}d`;
}

const STATUS_TONE = { ready: 'accent', review: 'accent', attention: 'red', progress: 'amber' };

/* ── Filters config ─────────────────────────────────────────────────────── */
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'attention', label: 'Needs attention', tone: 'red' },
  { id: 'progress', label: 'In progress', tone: 'amber' },
  { id: 'ready', label: 'Ready' },
];

/* ── Selected player row (used in the expand peek where a roster exists) ──── */
function PlayerRow({ p, n, fx }) {
  const m = BS.AVAIL[p.availability];
  const out = p.availability === 'UNAVAILABLE';
  const concern = out || p.availability === 'MAYBE';
  return (
    <div className={'idx-prow' + (out ? ' out' : '')}>
      <span className="idx-pnum">{n}</span>
      <span className="idx-edge" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : m.token }} />
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <Avatar p={p} size={26} />
        <span style={{ position: 'absolute', right: -2, bottom: -2 }}><Dot status={p.availability} size={9} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
      </div>
      <div className="idx-pmid">
        <div className="idx-pname-row">
          <span className="idx-pname">{p.name}</span>
          {p.id === fx.capId && <Tag>C</Tag>}
          {p.id === fx.wkId && <Tag tone="amber">WK</Tag>}
        </div>
      </div>
      <div className="idx-pavail">
        {concern
          ? <span className="idx-availtag" style={{ color: m.token }}>{p.availability === 'MAYBE' ? 'Maybe' : 'Out'}</span>
          : <FormChip p={p} withBars={false} />}
      </div>
    </div>
  );
}

function AvailBar({ avail }) {
  const segs = BS.AVAIL_ORDER.filter((s) => avail[s]);
  return (
    <div className="idx-availbar" title={segs.map((s) => `${avail[s]} ${BS.AVAIL[s].label.toLowerCase()}`).join(' · ')}>
      {segs.map((s) => <span key={s} style={{ flexGrow: avail[s], background: BS.AVAIL[s].token, opacity: s === 'NO_RESPONSE' ? 0.45 : 1 }} />)}
    </div>
  );
}

/* ── One fixture (compact row + expandable peek) ────────────────────────── */
function FixtureItem({ fx, open, onToggle, onOpen }) {
  const a = useMemo(() => summarize(fx), [fx]);
  const matchup = (fx.homeAway === 'HOME' ? 'vs ' : '@ ') + fx.opponent;
  const ha = fx.homeAway === 'HOME' ? 'H' : 'A';
  const worst = a.flags.find((f) => f.tone === 'red') || a.flags.find((f) => f.tone === 'amber');
  const extra = a.flags.length - (worst ? 1 : 0);
  const complete = a.count >= a.target;
  const cta = a.count === 0 ? 'Build XI' : a.status === 'attention' ? 'Review XI' : 'Edit XI';

  return (
    <div className={'idx-item status-' + a.status + (open ? ' open' : '')}>
      <div className="idx-row2" onClick={() => onOpen(fx)}>
        <span className="idx-gradechip">{fx.grade}</span>
        <div className="idx-r2info">
          <div className="idx-r2squad">
            <span className="idx-r2name">{fx.squad}</span>
            <span className="idx-r2match">{matchup}</span>
          </div>
          <div className="idx-r2sub">
            <span>{fx.time}</span><i /><span className="idx-r2venue">{fx.venue} ({ha})</span><i /><span>{daysUntil(fx.iso)}</span>
          </div>
        </div>
        <div className="idx-r2right">
          {worst && <span className={'idx-r2flag ' + worst.tone}>{worst.text}{extra > 0 && <em>+{extra}</em>}</span>}
          <span className="idx-r2count" style={{ color: a.count === 0 ? 'var(--pb-faint)' : complete ? 'var(--pb-accent)' : 'var(--pb-amber)' }}>
            {a.count}<span>/{a.target}</span>
          </span>
          <span className={'idx-status idx-status-' + STATUS_TONE[a.status]}><span className="idx-statusdot" />{a.statusLabel}</span>
          <button className="idx-chevbtn" title={open ? 'Collapse' : 'Peek'} onClick={(e) => { e.stopPropagation(); onToggle(fx.key); }}>
            <Icon name="chevron" size={16} className="idx-chev" />
          </button>
        </div>
      </div>

      {open && (
        <div className="idx-expandbody">
          {/* Balance + leadership */}
          <div className="idx-meta">
            <div className="idx-balance">
              {['BAT', 'ALL', 'BWL', 'WKT'].map((c) => {
                const low = (c === 'BWL' && a.count >= 8 && a.bowlers < 5) || (c === 'WKT' && a.count >= 8 && !a.keeperPresent);
                return <span key={c} className="idx-bcell"><i style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{c === 'WKT' ? 'WK' : c}</i><b style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{a.bal[c]}</b></span>;
              })}
            </div>
            <div className="idx-lead">
              <span className="idx-leadcell" style={{ color: a.capName ? 'var(--pb-dim)' : 'var(--pb-amber)' }}><Tag tone={a.capName ? 'accent' : 'faint'}>C</Tag>{a.capName || 'None'}</span>
              <span className="idx-leadcell" style={{ color: a.wkName ? (a.wkOut ? 'var(--pb-red)' : 'var(--pb-dim)') : 'var(--pb-amber)' }}><Tag tone={a.wkName && !a.wkOut ? 'amber' : 'faint'}>WK</Tag>{a.wkName || 'None'}</span>
            </div>
          </div>

          {/* Flags */}
          <div className="idx-flags">
            {a.flags.length > 0
              ? a.flags.map((f, i) => <span key={i} className={'idx-flag idx-flag-' + f.tone}><Icon name={f.tone === 'red' ? 'close' : 'info'} size={12} />{f.text}</span>)
              : <span className="idx-flag idx-flag-ok"><Icon name="check" size={12} />Balanced · keeper & captain named · all available</span>}
          </div>

          {/* Availability breakdown */}
          <div className="idx-availbreak">
            {BS.AVAIL_ORDER.map((s) => (
              <span key={s} className="idx-abcell"><Dot status={s} size={8} /><b>{a.avail[s] || 0}</b>{BS.AVAIL[s].label}</span>
            ))}
          </div>

          {/* XI peek where a roster exists */}
          {fx.players && (
            <div className="idx-peekgrid">
              {fx.players.map((p, i) => <PlayerRow key={p.id} p={p} n={i + 1} fx={fx} />)}
            </div>
          )}

          <footer className="idx-foot">
            <div className="idx-foot-l">
              <AvailBar avail={a.avail} />
              <span className="idx-foot-count">{a.count} selected{a.count > a.target ? ` · ${a.count - a.target} in reserve` : ''}</span>
            </div>
            <div className="idx-foot-r">
              <span className="idx-edited">{fx.editedAgo}</span>
              <button className="idx-cta" onClick={() => onOpen(fx)}>{cta}<Icon name="arrow" size={16} /></button>
            </div>
          </footer>
        </div>
      )}
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="bs-sidebar">
      <div className="bs-brand">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 32, height: 32, borderRadius: 7, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)', fontFamily: 'var(--display)', fontWeight: 700 }}>A</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 13.5, lineHeight: 1.15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Applecross Cricket Cl…</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--pb-faint)' }}>Better<span style={{ color: 'var(--pb-brand)' }}>Select</span></div>
          </div>
        </div>
        <a className="bs-back">← Back to admin</a>
      </div>
      <nav className="bs-nav">
        {[
          { icon: 'overview', label: 'Overview' }, { icon: 'player', label: 'Players' },
          { icon: 'fixtures', label: 'Fixtures' }, { icon: 'teams', label: 'Squads' },
          { icon: 'availability', label: 'Availability' }, { icon: 'selection', label: 'Selection', active: true },
          { icon: 'nets', label: 'Nets' }, { icon: 'ladders', label: 'Ladders' },
        ].map((n) => (
          <a key={n.label} className={'bs-navitem' + (n.active ? ' active' : '')}><Icon name={n.icon} size={18} /><span>{n.label}</span></a>
        ))}
      </nav>
    </aside>
  );
}

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('bs-theme') || 'light');
  const [navOpen, setNavOpen] = useState(false);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [openKeys, setOpenKeys] = useState(() => new Set());
  const [toast, setToast] = useState(null);

  useEffect(() => { localStorage.setItem('bs-theme', theme); }, [theme]);
  const flash = useCallback((msg) => { setToast(msg); clearTimeout(window.__t); window.__t = setTimeout(() => setToast(null), 1800); }, []);
  const onOpen = useCallback((fx) => flash(`Opening ${fx.squad} — ${fx.opponent}…`), [flash]);
  const toggle = useCallback((key) => setOpenKeys((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; }), []);

  // status of each fixture (memoised once)
  const withStatus = useMemo(() => FIXTURES.map((fx) => ({ fx, status: summarize(fx).status })), []);
  const counts = useMemo(() => {
    const c = { all: withStatus.length, attention: 0, progress: 0, ready: 0 };
    withStatus.forEach(({ status }) => {
      if (status === 'attention') c.attention++;
      else if (status === 'progress') c.progress++;
      else c.ready++; // ready + review
    });
    return c;
  }, [withStatus]);

  const visible = useMemo(() => {
    const s = q.trim().toLowerCase();
    return withStatus.filter(({ fx, status }) => {
      if (filter === 'ready' && !(status === 'ready' || status === 'review')) return false;
      if (filter !== 'all' && filter !== 'ready' && status !== filter) return false;
      if (s && !(fx.squad.toLowerCase().includes(s) || fx.opponent.toLowerCase().includes(s) || fx.grade.toLowerCase().includes(s))) return false;
      return true;
    });
  }, [withStatus, filter, q]);

  // group by matchday preserving order
  const groups = useMemo(() => {
    const map = new Map();
    visible.forEach((v) => { if (!map.has(v.fx.day)) map.set(v.fx.day, []); map.get(v.fx.day).push(v); });
    return [...map.entries()].map(([day, items]) => ({
      day, items, attention: items.filter((i) => i.status === 'attention').length,
    }));
  }, [visible]);

  const allOpen = visible.length > 0 && visible.every((v) => openKeys.has(v.fx.key));
  const toggleAll = () => setOpenKeys(allOpen ? new Set() : new Set(visible.map((v) => v.fx.key)));

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
            <span className="idx-season">Season 2025/26</span>
          </div>
          <button className="bs-themebtn" onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))} title="Toggle theme">
            <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
          </button>
        </header>

        <main className="bs-content">
          <div className="idx-intro">
            <div>
              <h2 className="idx-introtitle">Upcoming selections</h2>
              <p className="idx-introsub">{counts.all} teams across this weekend. Find a team, open it to build or edit its XI.</p>
            </div>
            <div className="idx-summary">
              {counts.attention > 0 && <span className="idx-sumcell idx-sum-amber"><span className="idx-statusdot" style={{ background: 'var(--pb-red)' }} /><b>{counts.attention}</b> need attention</span>}
              <span className="idx-sumcell"><span className="idx-statusdot" style={{ background: 'var(--pb-accent)' }} /><b>{counts.ready}</b> ready</span>
            </div>
          </div>

          {/* Toolbar */}
          <div className="idx-toolbar">
            <div className="idx-search">
              <Icon name="search" size={16} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a team or opponent…" />
            </div>
            <div className="idx-statusfilter">
              {FILTERS.map((fl) => {
                const n = fl.id === 'all' ? counts.all : counts[fl.id];
                return (
                  <button key={fl.id} className={'idx-sfchip' + (filter === fl.id ? ' on ' + (fl.tone || '') : '')} onClick={() => setFilter(fl.id)}>
                    {fl.label}<span className="idx-sfn">{n}</span>
                  </button>
                );
              })}
            </div>
            <span className="idx-spacer" />
            <button className="idx-expandall" onClick={toggleAll}>
              <Icon name={allOpen ? 'cols' : 'sheet'} size={14} />{allOpen ? 'Collapse all' : 'Expand all'}
            </button>
            <span className="idx-showing">{visible.length} of {counts.all}</span>
          </div>

          {/* Grouped list */}
          {groups.length === 0 ? (
            <div className="idx-empty"><b>No teams match</b>Try a different search or filter.</div>
          ) : groups.map((g) => (
            <section className="idx-group" key={g.day}>
              <div className="idx-grouphead">
                <span className="idx-groupday">{g.day}</span>
                <span className="idx-grouptag">{g.items.length} {g.items.length === 1 ? 'team' : 'teams'}</span>
                {g.attention > 0 && <span className="idx-groupwarn"><span className="idx-statusdot" />{g.attention} need attention</span>}
                <span className="idx-groupline" />
              </div>
              <div className="idx-items">
                {g.items.map(({ fx }) => (
                  <FixtureItem key={fx.key} fx={fx} open={openKeys.has(fx.key)} onToggle={toggle} onOpen={onOpen} />
                ))}
              </div>
            </section>
          ))}
        </main>
      </div>

      {toast && <div className="bs-toast">{toast}</div>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
