/* BetterStats — Players admin · mock data + helpers
 * A large, realistic club roster spanning A–Z so the alphabet grouping,
 * jump rail and sticky letter headers have something to chew on.
 * Everything hangs off window.PD so the Babel view scripts share one source.
 */
(function () {
  // ── deterministic PRNG so the roster is stable across reloads ───────────
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rand = mulberry32(20260609);
  const pick = (arr) => arr[Math.floor(rand() * arr.length)];
  const chance = (p) => rand() < p;
  const intIn = (lo, hi) => lo + Math.floor(rand() * (hi - lo + 1));

  // ── name banks (multicultural, club-cricket flavoured) ──────────────────
  const SURNAMES = [
    'Abbas','Abbott','Abdullah','Abeygunasekara','Abeyrathna','Abraham','Adair','Ahmed','Akram','Ali','Anderson','Arnold','Atapattu',
    'Bailey','Baker','Bandara','Bell','Bhave','Brar','Brown','Butt',
    'Carter','Chandimal','Clarke','Cooper','Cox','Cummins',
    'Dawson','De Silva','Dias','Dixon','Dunn',
    'Edwards','Ellis','Evans',
    'Farooq','Fernando','Finch','Fletcher','Ford',
    'Gardner','George','Gill','Green','Gunaratne',
    'Hafeez','Hall','Hardie','Harris','Hayes','Hughes','Hussain',
    'Iqbal','Irfan','Ishaq',
    'Jackson','Jayasuriya','Jenkins','Johnson','Jones',
    'Kamal','Kelly','Khan','King','Kumar',
    'Lakmal','Lawson','Lee','Lewis','Lloyd',
    'Mahmood','Marsh','Mathews','McKay','Mendis','Mitchell','Morgan','Murphy',
    'Nawaz','Naylor','Nelson','Nguyen','Nicholls',
    "O'Brien","O'Connor",'Oliver','Owen',
    'Patel','Perera','Phillips','Pieris','Powell','Pratt',
    'Qadir','Quinn',
    'Rahman','Reed','Richards','Roberts','Russell','Ryan',
    'Samaraweera','Sandhu','Scott','Sharma','Singh','Smith','Stewart','Sullivan',
    'Tariq','Taylor','Thompson','Turner',
    'Ud-din','Umar','Usman',
    'Vaas','Vandersay','Vaughan','Verma',
    'Walker','Wasim','Watson','White','Williams','Wilson','Wright',
    'Xavier',
    'Yasir','Young','Yousuf',
    'Zaheer','Zaman','Zoysa',
  ];
  const MALE_FIRST = ['Aamir','Adam','Ahsan','Ali','Anushka','Asanka','Ben','Brad','Callum','Chris','Daniel','Dasun','Dean','Dimuth','Ethan','Faisal','Gihan','Hamza','Harry','Imran','Jack','James','Josh','Kamal','Kasun','Liam','Luke','Mahela','Mark','Mitchell','Muhammad','Nuwan','Oliver','Owen','Pratik','Rahul','Rob','Ryan','Sahan','Sam','Scott','Shane','Tariq','Thilan','Tom','Usman','Vernon','Wasim','Will','Zane'];
  const FEMALE_FIRST = ['Alice','Amelia','Ava','Chamari','Ella','Emma','Grace','Hannah','Harshitha','Isla','Jess','Lara','Maya','Mia','Nilakshi','Olivia','Priya','Sara','Sophie','Tara','Zoe'];

  const ROLES = ['Batter','Bowler','All Rounder','Wicketkeeper','Wicketkeeper-Batter'];
  const ROLE_W = ['Batter','Batter','Batter','Bowler','Bowler','All Rounder','All Rounder','All Rounder','Wicketkeeper','Wicketkeeper-Batter'];
  const BAT_HANDS = ['Right handed','Right handed','Right handed','Left handed'];
  const PACE = ['Right-arm fast','Right-arm fast-medium','Right-arm medium','Left-arm fast-medium','Left-arm medium'];
  const SPIN = ['Right-arm off spin','Right-arm leg spin','Left-arm orthodox','Left-arm wrist spin'];
  const SQUADS = ['Applecross 1st XI','Applecross 2nd XI','Applecross 3rd XI','Applecross 4th XI','Applecross 5th XI','Applecross 6th XI','Applecross 7th XI','Applecross 8th XI'];
  const SQUAD_SHORT = (s) => s.replace('Applecross ', '');
  const VENUES = ['Kardinya','Melville','Willetton','Fremantle','Bull Creek','Rossmoyne','Booragoon','Attadale','Bicton','Mt Pleasant'];

  // ── role → skills + bowling style ───────────────────────────────────────
  function skillsFor(role) {
    if (role === 'Batter') return ['BAT'];
    if (role === 'Bowler') return ['BWL'];
    if (role === 'All Rounder') return ['ALL'];
    if (role === 'Wicketkeeper') return ['WKT'];
    if (role === 'Wicketkeeper-Batter') return ['WKT', 'BAT'];
    return ['BAT'];
  }
  function bowlFor(role) {
    if (role === 'Batter') return chance(0.25) ? pick([...PACE, ...SPIN]) : null;
    if (role === 'Wicketkeeper') return null;
    if (role === 'Wicketkeeper-Batter') return chance(0.15) ? pick(SPIN) : null;
    return chance(0.55) ? pick(PACE) : pick(SPIN);
  }
  const slug = (s) => s.toLowerCase().replace(/[^a-z]+/g, '');

  // ── build the roster ────────────────────────────────────────────────────
  let _id = 0;
  const ROSTER = [];
  const seen = new Set();
  SURNAMES.forEach((sur) => {
    const n = intIn(1, 3); // a few first names per surname
    for (let k = 0; k < n; k++) {
      const female = chance(0.16);
      const first = female ? pick(FEMALE_FIRST) : pick(MALE_FIRST);
      const key = first + ' ' + sur;
      if (seen.has(key)) continue;
      seen.add(key);
      const role = pick(ROLE_W);
      const overseas = chance(0.07);
      const inactive = chance(0.06);
      const squad = SQUADS[Math.min(SQUADS.length - 1, Math.floor(Math.pow(rand(), 1.4) * SQUADS.length))];
      const opener = role === 'Batter' && chance(0.3);
      const id = 'pl' + (++_id);
      ROSTER.push({
        id,
        first, last: sur,
        name: first + ' ' + sur,        // "First Last"
        sortName: sur + ', ' + first,   // "Last, First"
        player_role: role,
        skills: skillsFor(role),
        batting_hand: pick(BAT_HANDS),
        bowl: bowlFor(role),
        gender: female ? 'Female' : 'Male',
        overseas, inactive, opener,
        squad,
        squadShort: SQUAD_SHORT(squad),
        email: slug(first) + (intIn(1, 89)) + '@' + pick(['gmail.com','yahoo.com','outlook.com','bigpond.com']),
        phone: '+61 4' + intIn(10, 89) + ' ' + intIn(100, 999) + ' ' + intIn(100, 999),
        photo: null,
        recentBat: Array.from({ length: 5 }, () => intIn(0, 92)),
        recentBowl: Array.from({ length: 5 }, () => `${intIn(0, 4)}/${intIn(0, 38)}`),
        catches: intIn(0, 14),
        lastPlayed: chance(0.12) ? null : 'vs ' + pick(VENUES),
        avail: [chance(0.7), chance(0.6), chance(0.55), chance(0.5)], // next 4 weeks
        netSessions: intIn(0, 9),
        netBatted: intIn(0, 6),
      });
    }
  });

  // sort by surname then first (the natural admin order)
  ROSTER.sort((a, b) => a.sortName.localeCompare(b.sortName));

  // ── helpers ─────────────────────────────────────────────────────────────
  const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
  // user-requested A–E / F–J style ranges
  const RANGES = [
    { key: 'A-E', from: 'A', to: 'E' },
    { key: 'F-J', from: 'F', to: 'J' },
    { key: 'K-O', from: 'K', to: 'O' },
    { key: 'P-T', from: 'P', to: 'T' },
    { key: 'U-Z', from: 'U', to: 'Z' },
  ];
  function letterOf(p) {
    const c = (p.last[0] || '#').toUpperCase();
    return /[A-Z]/.test(c) ? c : '#';
  }
  function rangeOf(p) {
    const L = letterOf(p);
    const r = RANGES.find((rg) => L >= rg.from && L <= rg.to);
    return r ? r.key : 'A-E';
  }
  function roleNoun(p) {
    const M = { 'Batter': 'Batter', 'Bowler': 'Bowler', 'All Rounder': 'All-rounder', 'Wicketkeeper': 'Keeper', 'Wicketkeeper-Batter': 'Keeper-bat' };
    if (p.opener) return 'Opening bat';
    return M[p.player_role] || p.player_role;
  }
  // useful one-liner that REPLACES the old uuid + PHQ clutter
  function metaLine(p) {
    const bits = [roleNoun(p)];
    if (p.batting_hand) bits.push(p.batting_hand === 'Right handed' ? 'RHB' : 'LHB');
    if (p.bowl) bits.push(p.bowl);
    return bits.join(' · ');
  }
  function initials(name) {
    return name.split(/[ ,]+/).filter(Boolean).slice(0, 2).map((s) => s[0]).join('').toUpperCase();
  }
  // a stable, pleasant avatar tint per player
  function tintOf(p) {
    const hues = [150, 150, 190, 210, 35, 280, 330, 12];
    let h = 0; for (const c of p.id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return hues[h % hues.length];
  }
  const SKILL_SHORT = { BAT: 'BAT', BWL: 'BWL', ALL: 'ALL', WKT: 'WK' };

  window.PD = {
    ROSTER, ALPHABET, RANGES, SQUADS, ROLES,
    letterOf, rangeOf, roleNoun, metaLine, initials, tintOf, SKILL_SHORT,
  };
})();
