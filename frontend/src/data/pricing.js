// Modular Better Cricket pricing for the public marketing pages.
//
// Decoupled on purpose from the in-app entitlement registry (src/lib/modules.js,
// which still describes the Good/Better/Best tiers the backend enforces). The
// public model the club sees is simpler: one Core plus the modules you choose,
// billed as an annual licence. Edit the numbers here.

export const CORE = {
  key: 'core',
  name: 'BetterStats',
  label: 'Core',
  price: 400,
  icon: '◆',
  accent: '#34d399',
  blurb: 'Reconciled stats and your public club site',
}

// The bolt-on modules and their annual price. Icons/accents mirror the in-app
// module tiles so the calculator looks like the dashboard.
export const PRICED_MODULES = [
  { key: 'select',  name: 'BetterSelect',  price: 100, icon: '◎', accent: '#34d399', blurb: 'Player availability, team selection and net manager' },
  { key: 'socials', name: 'BetterSocials', price: 100, icon: '◈', accent: '#38bdf8', blurb: 'Social-post generation and a CRM for your club website' },
  { key: 'admin',   name: 'BetterAdmin',   price: 100, icon: '⬢', accent: '#f59e0b', blurb: 'Member fees, bulk emailing and merch (coming soon)' },
  { key: 'iq',      name: 'BetterIQ',      price: 200, icon: '◇', accent: '#a78bfa', blurb: 'Deep analytics and opposition scouting' },
]

// Bundle discount on the whole price: pick any 2 or 3 modules for 10% off, all 4
// for 15%. (The brief sets 2 -> 10% and 4 -> 15%; 3 modules takes the 10% band.)
export function discountRate(moduleCount) {
  if (moduleCount >= 4) return 0.15
  if (moduleCount >= 2) return 0.10
  return 0
}

// Price a selection of module keys. Returns the subtotal, the discount and the
// total, all in whole AUD.
export function priceFor(selectedKeys = []) {
  const mods = PRICED_MODULES.filter((m) => selectedKeys.includes(m.key))
  const subtotal = CORE.price + mods.reduce((sum, m) => sum + m.price, 0)
  const rate = discountRate(mods.length)
  const discount = Math.round(subtotal * rate)
  return { subtotal, rate, discount, total: subtotal - discount, moduleCount: mods.length, modules: mods }
}

// The everything price (Core + every module), for headline copy.
export const ALL_IN = priceFor(PRICED_MODULES.map((m) => m.key)).total  // 765

// ── Competitor stack ─────────────────────────────────────────────────────────
// What a club would otherwise pay to match Better Cricket's scope, using each
// tool's own published price (AUD; Pitchero converted from GBP) on a
// representative plan. Conservative plans are used, so a busy multi-team club
// pays more on the competitors and the gap only widens. Better Cricket replaces
// the lot for one flat ALL_IN price, so the saving is the difference.
export const COMPETITOR_STACK = [
  { tool: 'ClubStats', plan: 'Medium', forJob: 'Cricket stats & public site', replacedBy: 'BetterStats', cost: 399, note: '$299 to $599 by team count' },
  { tool: 'Pitchero', plan: 'Standard', forJob: 'Website, app, membership & payments', replacedBy: 'BetterAdmin & BetterSelect', cost: 800, note: '£418 a year, converted to AUD' },
  { tool: 'Canva Pro', forJob: 'Match-day social graphics', replacedBy: 'BetterSocials', cost: 165 },
]

export const COMPETITOR_TOTAL = COMPETITOR_STACK.reduce((sum, c) => sum + c.cost, 0)  // 1364
export const SAVING = COMPETITOR_TOTAL - ALL_IN                                       // 599

// Better Cricket loads your full history at no extra cost. The closest cricket
// rival (ClubStats) charges a one-off historical-import fee on top of the
// subscription, from $499 up to about $1,000 for big clubs. CricketStatz, the
// desktop stats package, is another stats option at $199 to $798 a year.
export const IMPORT_NOTE = 'from $499, up to about $1,000 for big clubs'
