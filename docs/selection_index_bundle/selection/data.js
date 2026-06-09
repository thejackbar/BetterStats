/* BetterSelect — Selection redesign · mock data + domain helpers
 *
 * Field shapes mirror the real selection pool (backend/services/selection_pool.py):
 *   id, name, player_role, skills[], batting_hand, bowl(label), opener,
 *   availability, availability_reason, squad, tier, score, recent[], last_played, photo
 *
 * Everything is attached to window so the (Babel-transpiled) view scripts,
 * which each get their own scope, can share one source of truth.
 */
(function () {
  // ── Availability identity (semantic — never the club accent) ──────────────
  const AVAIL = {
    AVAILABLE:   { label: 'Available',   short: 'In',     glyph: '✓', token: 'var(--pb-positive)', rank: 0 },
    MAYBE:       { label: 'Maybe',       short: 'Maybe',  glyph: '?', token: 'var(--pb-amber)',    rank: 1 },
    NO_RESPONSE: { label: 'No response', short: 'No reply',glyph: '–', token: 'var(--pb-faintest)', rank: 2 },
    UNAVAILABLE: { label: 'Unavailable', short: 'Out',    glyph: '✕', token: 'var(--pb-red)',       rank: 3 },
  };
  const AVAIL_ORDER = ['AVAILABLE', 'MAYBE', 'NO_RESPONSE', 'UNAVAILABLE'];

  // ── Role + style → the genuinely useful one-liner that replaces "Opener" ──
  const BAT_SHORT = { RIGHT: 'RHB', LEFT: 'LHB' };
  const ROLE_NOUN = {
    'Batter': 'Batter',
    'Bowler': 'Bowler',
    'All Rounder': 'All-rounder',
    'Wicketkeeper': 'Keeper',
    'Wicketkeeper-Batter': 'Keeper-bat',
  };
  // Short skill code for chips
  const SKILL_SHORT = { BAT: 'BAT', BWL: 'BWL', ALL: 'ALL', WKT: 'WK' };

  function roleNoun(p) {
    if (p.opener && p.player_role === 'Batter') return 'Opening bat';
    return ROLE_NOUN[p.player_role] || p.player_role || 'Player';
  }
  // Full descriptive line e.g. "All-rounder · RHB · Off spin"
  function roleLine(p) {
    const bits = [roleNoun(p)];
    if (p.batting_hand) bits.push(BAT_SHORT[p.batting_hand]);
    if (p.bowl) bits.push(p.bowl);
    return bits.join(' · ');
  }
  // Compact style only (no role noun) e.g. "RHB · Off spin"
  function styleLine(p) {
    const bits = [];
    if (p.batting_hand) bits.push(BAT_SHORT[p.batting_hand]);
    if (p.bowl) bits.push(p.bowl);
    return bits.join(' · ');
  }

  // ── Form: a quiet trend derived from the last-4 `recent` series + score ───
  // tier: hot / warm / steady / quiet  →  label + token + 0..1 bar heights.
  const FORM = {
    hot:    { label: 'Hot',    token: 'var(--pb-positive)' },
    warm:   { label: 'In form',token: 'var(--pb-positive)' },
    steady: { label: 'Steady', token: 'var(--pb-dim)' },
    quiet:  { label: 'Quiet',  token: 'var(--pb-faint)' },
    cold:   { label: 'Cold',   token: 'var(--pb-faint)' },
  };
  function formOf(p) { return FORM[p.form] || FORM.steady; }
  // Normalise a recent series to 0..1 bar heights for a mini sparkline.
  function spark(p) {
    const r = p.recent || [];
    const max = Math.max(1, ...r);
    return r.map((v) => Math.max(0.14, v / max));
  }

  function initials(name) {
    return name.split(/[ ,]+/).filter(Boolean).slice(0, 2).map((s) => s[0]).join('').toUpperCase();
  }

  // ── The squad pool ─────────────────────────────────────────────────────────
  // recent = last 4 innings (runs for bat-led, wickets×scaled for bowl-led — already
  // normalised for display); score = composite form on a runs-per-innings scale.
  let _id = 0;
  const P = (o) => Object.assign({ id: 'p' + (++_id), squad: 'Applecross 1st XI', tier: 1, clash: null, photo: null }, o);

  const POOL = [
    // ——— Top order / openers ———
    P({ name: 'Bhave, Pratik',        player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: true,  availability: 'AVAILABLE', score: 52.4, form: 'hot',    recent: [88, 41, 12, 76], last_played: '2026-06-28' }),
    P({ name: 'Petersen, Josh',       player_role: 'Batter', skills: ['BAT'], batting_hand: 'LEFT',  bowl: null, opener: true,  availability: 'AVAILABLE', score: 44.1, form: 'warm',   recent: [54, 22, 61, 31], last_played: '2026-06-28' }),
    P({ name: 'Fox-Dean, Tom',        player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'AVAILABLE', score: 39.8, form: 'warm',   recent: [33, 70, 18, 40], last_played: '2026-06-28' }),
    P({ name: 'Silva, Pulith',        player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: 'Off spin',          opener: false, availability: 'AVAILABLE', score: 36.0, form: 'steady', recent: [40, 29, 35, 44], last_played: '2026-06-21' }),
    P({ name: 'Teague, Joseph',       player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'UNAVAILABLE', availability_reason: 'Away — wedding', score: 31.2, form: 'quiet', recent: [12, 8, 24, 19], last_played: '2026-06-14' }),
    // ——— Middle order ———
    P({ name: 'Birbeck, James',       player_role: 'Batter', skills: ['BAT'], batting_hand: 'LEFT',  bowl: null, opener: false, availability: 'AVAILABLE', score: 34.6, form: 'steady', recent: [27, 51, 19, 38], last_played: '2026-06-28' }),
    P({ name: 'Baker, Daniel',        player_role: 'Wicketkeeper-Batter', skills: ['WKT','BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'UNAVAILABLE', availability_reason: 'Injured — hamstring', score: 33.9, form: 'steady', recent: [41, 17, 36, 28], last_played: '2026-06-07' }),
    P({ name: 'Verdonk, Kurt',        player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast-medium', opener: false, availability: 'AVAILABLE', score: 42.0, form: 'hot', recent: [36, 3, 58, 44], last_played: '2026-06-28' }),
    // ——— Lower order / bowlers ———
    P({ name: 'Cooper, Chris',        player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Leg spin', opener: false, availability: 'AVAILABLE', score: 28.5, form: 'warm',   recent: [22, 41, 9, 33], last_played: '2026-06-28' }),
    P({ name: 'Stopforth, David',     player_role: 'Bowler', skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast', opener: false, availability: 'AVAILABLE', score: 30.1, form: 'hot',    recent: [18, 30, 26, 34], last_played: '2026-06-28' }),
    P({ name: 'Berry, Michael',       player_role: 'Bowler', skills: ['BWL'], batting_hand: 'LEFT',  bowl: 'Left-arm orthodox', opener: false, availability: 'AVAILABLE', score: 24.7, form: 'steady', recent: [20, 16, 28, 22], last_played: '2026-06-28' }),

    // ——— The rest of the pool ———
    P({ name: 'Bell, Sol',            player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: true,  availability: 'NO_RESPONSE', score: 29.4, form: 'steady', recent: [31, 20, 44, 12], last_played: '2026-06-21' }),
    P({ name: 'Baines, George',       player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'NO_RESPONSE', score: 26.8, form: 'quiet',  recent: [14, 33, 8, 21], last_played: '2026-05-31' }),
    P({ name: 'Woods, Sebastian',     player_role: 'Bowler', skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast-medium', opener: false, availability: 'AVAILABLE', score: 27.3, form: 'warm', recent: [22, 28, 19, 31], last_played: '2026-06-28' }),
    P({ name: 'Dagg, Will',           player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'LEFT', bowl: 'Left-arm medium', opener: false, availability: 'UNAVAILABLE', availability_reason: 'Work', score: 31.6, form: 'steady', recent: [29, 24, 18, 40], last_played: '2026-06-21' }),
    P({ name: 'Edwards, Matthew',     player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Off spin', opener: false, availability: 'UNAVAILABLE', availability_reason: 'Unavailable', score: 25.9, form: 'quiet', recent: [16, 11, 27, 14], last_played: '2026-06-07' }),
    P({ name: 'Byrne, Sheamus',       player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Right-arm medium', opener: false, availability: 'UNAVAILABLE', availability_reason: 'Interstate', score: 23.2, form: 'cold', recent: [9, 14, 6, 18], last_played: '2026-05-24' }),
    P({ name: 'Dissanayake, Dushmantha', player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Off spin', opener: false, availability: 'AVAILABLE', score: 35.5, form: 'warm', recent: [30, 38, 22, 41], last_played: '2026-06-28' }),
    P({ name: 'Perera, Heshan',       player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'LEFT', bowl: 'Left-arm wrist spin', opener: false, availability: 'MAYBE', availability_reason: 'Tentative — may travel', score: 32.1, form: 'steady', recent: [26, 19, 35, 28], last_played: '2026-06-21' }),
    P({ name: 'Gaudieri, Jayden',     player_role: 'Wicketkeeper-Batter', skills: ['WKT','BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'AVAILABLE', score: 30.8, form: 'warm', recent: [44, 21, 33, 27], last_played: '2026-06-28' }),
    P({ name: 'Khan, Imran',          player_role: 'Bowler', skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast', opener: false, availability: 'AVAILABLE', score: 26.0, form: 'hot', recent: [24, 31, 28, 36], last_played: '2026-06-28' }),
    P({ name: 'Okafor, Daniel',       player_role: 'Bowler', skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Leg spin', opener: false, availability: 'MAYBE', availability_reason: 'Soreness — testing Thu', score: 22.4, form: 'steady', recent: [18, 22, 16, 25], last_played: '2026-06-21' }),
    P({ name: 'Nguyen, Tay',          player_role: 'Batter', skills: ['BAT'], batting_hand: 'LEFT', bowl: null, opener: true, availability: 'AVAILABLE', score: 33.0, form: 'warm', recent: [48, 19, 27, 41], last_played: '2026-06-28', squad: 'Applecross 2nd XI', tier: 2 }),
    P({ name: 'O’Brien, Liam',        player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'RIGHT', bowl: 'Right-arm medium', opener: false, availability: 'AVAILABLE', score: 28.9, form: 'steady', recent: [25, 30, 21, 26], last_played: '2026-06-28', squad: 'Applecross 2nd XI', tier: 2 }),
    P({ name: 'Marsh, Cody',         player_role: 'Batter', skills: ['BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'NO_RESPONSE', score: 21.5, form: 'quiet', recent: [12, 28, 9, 17], last_played: '2026-06-14', squad: 'Applecross 2nd XI', tier: 2 }),
    P({ name: 'Hollis, Ben',         player_role: 'Bowler', skills: ['BWL'], batting_hand: 'RIGHT', bowl: 'Right-arm fast-medium', opener: false, availability: 'AVAILABLE', score: 23.8, form: 'warm', recent: [21, 26, 18, 30], last_played: '2026-06-28', squad: 'Applecross 3rd XI', tier: 2 }),
    P({ name: 'Tran, Vu',           player_role: 'Wicketkeeper-Batter', skills: ['WKT','BAT'], batting_hand: 'RIGHT', bowl: null, opener: false, availability: 'AVAILABLE', score: 27.7, form: 'steady', recent: [33, 18, 29, 24], last_played: '2026-06-21', squad: 'Applecross 3rd XI', tier: 2 }),
    P({ name: 'Ferreira, Diego',     player_role: 'All Rounder', skills: ['ALL'], batting_hand: 'LEFT', bowl: 'Left-arm fast', opener: false, availability: 'MAYBE', availability_reason: 'Tentative', score: 29.3, form: 'warm', recent: [27, 22, 34, 19], last_played: '2026-06-28', squad: 'Applecross A', tier: 3 }),
  ];

  // The XI that's pre-loaded (the saved lineup from the screenshot, in order).
  const STARTING_XI = ['p1','p2','p3','p4','p5','p6','p7','p8','p9','p10','p11'];

  const FIXTURE = {
    us: 'Applecross Cricket Club',
    opponent: 'Wembley Districts',
    homeAway: 'AWAY',
    date: 'Sat, Jul 4',
    time: '13:00',
    venue: 'Wembley Sports Park',
    round: 'Round 8',
  };

  window.BS = {
    AVAIL, AVAIL_ORDER, SKILL_SHORT,
    POOL, STARTING_XI, FIXTURE,
    SQUADS: [...new Set(POOL.map((p) => p.squad))],
    roleNoun, roleLine, styleLine, formOf, spark, initials,
    byId: Object.fromEntries(POOL.map((p) => [p.id, p])),
  };
})();
