// ─────────────────────────────────────────────────────────────────────────────
// BetterSocials — shared visual primitives, palettes & sample data
// Ported from the BetterStats cricket-templates design system.
// Display font var: --social-display-font (default Anton). Mono: JetBrains Mono.
// All posts render at exactly 1080×1080.
// ─────────────────────────────────────────────────────────────────────────────

const DISPLAY = "var(--social-display-font, 'Anton', sans-serif)";
const MONO = "'JetBrains Mono', monospace";
const BODY = "'Inter', sans-serif";

// ── Palettes (BetterStats built-ins) + win/loss coding ───────────────────────
const PALETTES = {
  midnight: { name: 'Midnight', primary: '#0b1530', secondary: '#1a2647', accent: '#ffc233', ink: '#ffffff' },
  crimson:  { name: 'Crimson',  primary: '#2a0a0e', secondary: '#5a0f1a', accent: '#ff3344', ink: '#fff4e6' },
  forest:   { name: 'Forest',   primary: '#0c2418', secondary: '#163828', accent: '#c4ff4d', ink: '#f4fbe8' },
  cobalt:   { name: 'Cobalt',   primary: '#0b1f4a', secondary: '#17336b', accent: '#00c2ff', ink: '#ffffff' },
  rust:     { name: 'Rust',     primary: '#1e0f08', secondary: '#3a1a0a', accent: '#ff7a1a', ink: '#fff1e3' },
  graphite: { name: 'Graphite', primary: '#101113', secondary: '#1d1f23', accent: '#e8ff00', ink: '#ffffff' },
};
const WIN = '#2fd07a';
const LOSS = '#ff5d6c';
const TIE = '#9aa0b4';

// ── Texture primitives ───────────────────────────────────────────────────────
function Grain({ opacity = 0.32, id = 'grain' }) {
  return (
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', mixBlendMode: 'overlay', opacity }}>
      <filter id={id}>
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.55 0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#${id})`} />
    </svg>
  );
}

function Halftone({ color = '#fff', size = 12, opacity = 0.07, angle = 0, style = {} }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
      backgroundImage: `radial-gradient(${color} 1.2px, transparent 1.6px)`,
      backgroundSize: `${size}px ${size}px`,
      transform: `rotate(${angle}deg) scale(1.4)`, transformOrigin: 'center',
      ...style,
    }} />
  );
}

function Stripes({ color = '#fff', angle = -45, gap = 14, opacity = 0.05, style = {} }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
      backgroundImage: `repeating-linear-gradient(${angle}deg, ${color} 0 1px, transparent 1px ${gap}px)`,
      ...style,
    }} />
  );
}

// ── Club shield with monogram (logo fallback) ────────────────────────────────
function Shield({ monogram = 'NG', color = '#fff', bg = 'transparent', size = 120 }) {
  const fontSize = size * 0.34;
  return (
    <svg width={size} height={size * 1.08} viewBox="0 0 100 108" style={{ display: 'block', flexShrink: 0 }}>
      <path d="M5 8 L50 0 L95 8 L92 60 Q88 88 50 104 Q12 88 8 60 Z"
        fill={bg === 'transparent' ? 'none' : bg} stroke={color} strokeWidth="3" />
      <text x="50" y="64" textAnchor="middle" fontFamily="'Anton', sans-serif"
        fontSize={fontSize} fill={color} letterSpacing="0.5">{monogram}</text>
    </svg>
  );
}

// Circular monogram chip — compact identity mark for list rows.
function Monogram({ text = '?', size = 56, fg, bg, ring }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: bg, border: ring ? `2px solid ${ring}` : 'none',
      display: 'grid', placeItems: 'center', color: fg,
      fontFamily: DISPLAY, fontSize: size * 0.4, letterSpacing: 0.5, lineHeight: 1,
    }}>{text}</div>
  );
}

// ── Accent slab label ─────────────────────────────────────────────────────────
function Slab({ children, bg, fg, size = 20, style = {} }) {
  return (
    <span style={{
      display: 'inline-block', padding: '7px 15px', background: bg, color: fg,
      fontFamily: DISPLAY, fontSize: size, letterSpacing: 3, lineHeight: 1, whiteSpace: 'nowrap', ...style,
    }}>{children}</span>
  );
}

// ── Mono kicker (// LABEL) ──────────────────────────────────────────────────────
function Kicker({ children, color, size = 13, style = {} }) {
  return (
    <div style={{ fontFamily: MONO, fontSize: size, letterSpacing: 2, color, ...style }}>{children}</div>
  );
}

// ── BetterStats bug ────────────────────────────────────────────────────────────
function Bug({ ink }) {
  return (
    <div style={{
      padding: '6px 12px', border: `1.5px solid ${ink}55`, fontFamily: DISPLAY,
      fontSize: 12, letterSpacing: 2, color: ink, opacity: 0.82,
    }}>BETTERSTATS</div>
  );
}

// ── Sponsor footer (PRESENTED BY + placeholder slots) ────────────────────────
function SponsorFooter({ palette, sponsors, showBug = true }) {
  const { ink, accent } = palette;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 22, width: '100%',
    }}>
      <div style={{ fontFamily: BODY, fontSize: 11, letterSpacing: 2.5, color: ink, opacity: 0.55, fontWeight: 600, flexShrink: 0 }}>PRESENTED BY</div>
      <div style={{ flex: 1, display: 'flex', gap: 14, alignItems: 'center' }}>
        {sponsors.map((s, i) => (
          <div key={i} style={{
            flex: 1, height: 50, display: 'grid', placeItems: 'center',
            border: `1px dashed ${ink}33`, borderRadius: 6, background: `${ink}08`,
            fontFamily: DISPLAY, fontSize: 18, letterSpacing: 1.5, color: ink, opacity: 0.78,
            overflow: 'hidden', whiteSpace: 'nowrap', padding: '0 10px',
          }}>{s}</div>
        ))}
      </div>
      {showBug && <Bug ink={ink} />}
    </div>
  );
}

// ── Auto-fit headline (shrink to single line) ────────────────────────────────
function AutoFit({ children, max, min = 24, style = {}, deps = [] }) {
  const ref = React.useRef(null);
  const [size, setSize] = React.useState(max);
  React.useLayoutEffect(() => {
    const node = ref.current; const parent = node && node.parentElement;
    if (!node || !parent) return;
    let next = max; node.style.fontSize = next + 'px';
    let guard = 0;
    while (guard++ < 400 && next > min && node.scrollWidth > parent.clientWidth + 0.5) {
      next -= 1; node.style.fontSize = next + 'px';
    }
    setSize(next);
    if (document.fonts && document.fonts.status !== 'loaded') {
      document.fonts.ready.then(() => {
        let n = max; node.style.fontSize = n + 'px'; let g = 0;
        while (g++ < 400 && n > min && node.scrollWidth > parent.clientWidth + 0.5) { n -= 1; node.style.fontSize = n + 'px'; }
        setSize(n);
      });
    }
  }, [max, min, ...deps]);
  return <div ref={ref} style={{ fontSize: size, whiteSpace: 'nowrap', ...style }}>{children}</div>;
}

// ── Post frame (1080×1080 base) ───────────────────────────────────────────────
function Post({ palette, font = "'Anton', sans-serif", children, style = {} }) {
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: BODY,
      '--social-display-font': font, ...style,
    }}>{children}</div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SAMPLE DATA — fictional WA grade-cricket club "Brookdale CC"
// ─────────────────────────────────────────────────────────────────────────────
const CLUB = { name: 'BROOKDALE', full: 'BROOKDALE CRICKET CLUB', mono: 'BRK', short: 'BRK' };
const SPONSORS = ['THE GRANARY TAVERN', 'PEEL CIVIL'];
const SPONSORS3 = ['GRANARY TAVERN', 'PEEL CIVIL', 'COASTAL TOYOTA'];

// Upcoming fixtures — Round 9
const FIXTURES = [
  { grade: '1ST XI',   opp: 'SUBIACO-FLOREAT', oppMono: 'SUB', ha: 'H', time: '12:30 PM', venue: 'TOMPKINS PARK' },
  { grade: '2ND XI',   opp: 'WILLETTON',       oppMono: 'WIL', ha: 'A', time: '12:30 PM', venue: 'BURRENDAH RES' },
  { grade: '3RD XI',   opp: 'GOSNELLS',        oppMono: 'GOS', ha: 'H', time: '1:00 PM',  venue: 'BROOKDALE OVAL 2' },
  { grade: '4TH XI',   opp: 'MELVILLE',        oppMono: 'MEL', ha: 'A', time: '1:00 PM',  venue: 'TOMATO LAKE' },
  { grade: 'T20',      opp: 'BAYSWATER-MORLEY', oppMono: 'BAY', ha: 'H', time: '5:30 PM', venue: 'TOMPKINS PARK' },
  { grade: "WOMEN'S 1ST", opp: 'FREMANTLE',    oppMono: 'FRE', ha: 'H', time: '11:00 AM', venue: 'STEVENS RES' },
];

// Round 8 results
const RESULTS = [
  { grade: '1ST XI', opp: 'SUBIACO-FLOREAT', oppMono: 'SUB', us: '6/188', usOv: '38.2', them: '184', themOv: '49.1', outcome: 'W', margin: 'BY 4 WICKETS' },
  { grade: '2ND XI', opp: 'WILLETTON',        oppMono: 'WIL', us: '176',   usOv: '47.0', them: '9/201', themOv: '50.0', outcome: 'L', margin: 'BY 25 RUNS' },
  { grade: '3RD XI', opp: 'GOSNELLS',         oppMono: 'GOS', us: '3/142', usOv: '28.4', them: '139', themOv: '41.2', outcome: 'W', margin: 'BY 7 WICKETS' },
  { grade: '4TH XI', opp: 'MELVILLE',         oppMono: 'MEL', us: '154',   usOv: '44.5', them: '4/192', themOv: '40.0', outcome: 'L', margin: 'BY 38 RUNS' },
  { grade: 'T20',    opp: 'BAYSWATER-MORLEY', oppMono: 'BAY', us: '5/176', usOv: '20.0', them: '8/164', themOv: '20.0', outcome: 'W', margin: 'BY 12 RUNS' },
  { grade: "WOMEN'S 1ST", opp: 'FREMANTLE',   oppMono: 'FRE', us: '4/138', usOv: '32.1', them: '135', themOv: '39.4', outcome: 'W', margin: 'BY 6 WICKETS' },
];

// Single 1st XI result for the standalone result posts
const RESULT1 = {
  comp: 'PREMIER GRADE', round: 'ROUND 8', date: 'SAT 7 JUN', season: '2025–26',
  venue: 'TOMPKINS PARK',
  us: { name: 'BROOKDALE', mono: 'BRK', score: '6/188', overs: '38.2' },
  them: { name: 'SUBIACO-FLOREAT', mono: 'SUB', score: '184', overs: '49.1' },
  winner: 'us', margin: 'BY 4 WICKETS',
  potm: { first: 'JAMES', last: 'OKAFOR', line: '94* (71) · 2/24', bat: '94* (71)', bowl: '2/24', role: 'ALL-ROUNDER' },
  topBat: { us: [{ n: 'OKAFOR', l: '94* (71)' }, { n: 'PATTERSON', l: '41 (52)' }], them: [{ n: 'NGUYEN', l: '67 (88)' }, { n: 'DELLA', l: '38 (45)' }] },
  topBowl: { us: [{ n: 'HARWOOD', l: '4/31 (10)' }, { n: 'OKAFOR', l: '2/24 (8)' }], them: [{ n: 'SINGH', l: '3/40 (10)' }, { n: 'COSTA', l: '2/35 (9)' }] },
};

const ROUND_META = { round: 'ROUND 9', date: 'SAT 14 JUN', season: '2025–26', comp: 'METRO PREMIER' };
const RESULTS_META = { round: 'ROUND 8', date: 'SAT 7 JUN', season: '2025–26' };

Object.assign(window, {
  DISPLAY, MONO, BODY, PALETTES, WIN, LOSS, TIE,
  Grain, Halftone, Stripes, Shield, Monogram, Slab, Kicker, Bug, SponsorFooter, AutoFit, Post,
  CLUB, SPONSORS, SPONSORS3, FIXTURES, RESULTS, RESULT1, ROUND_META, RESULTS_META,
});
