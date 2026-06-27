// Modular Better Cricket pricing for the public marketing pages.
//
// Decoupled on purpose from the in-app entitlement registry (src/lib/modules.js,
// which still describes the Good/Better/Best tiers the backend enforces). The
// public model the club sees is simpler: one Core plus the modules you choose,
// billed as an annual licence. Edit the numbers here.
//
// Colours + logos come from the shared module-brand registry so the calculator
// matches the dashboard tiles and the rest of the marketing site.
import { MODULE_BRAND as BRAND } from '../lib/moduleBrand'

export const CORE = {
  key: 'core',
  name: 'BetterStats',
  label: 'Core',
  price: 400,
  icon: '◆',
  accent: BRAND.stats.accent,
  logo: BRAND.stats.logo,
  blurb: 'Reconciled stats and your public club site',
}

// The bolt-on modules and their annual price. Logos/accents come from the shared
// brand registry so the calculator looks like the dashboard.
export const PRICED_MODULES = [
  { key: 'select',  name: 'BetterSelect',  price: 100, icon: '◎', accent: BRAND.select.accent,  logo: BRAND.select.logo,  blurb: 'Player availability, team selection and net manager' },
  { key: 'socials', name: 'BetterSocials', price: 100, icon: '◈', accent: BRAND.socials.accent, logo: BRAND.socials.logo, blurb: 'Social-post generation and a CRM for your club website' },
  { key: 'admin',   name: 'BetterAdmin',   price: 100, icon: '⬢', accent: BRAND.admin.accent,   logo: BRAND.admin.logo,   blurb: 'Member fees, bulk emailing and merch (coming soon)' },
  { key: 'iq',      name: 'BetterIQ',      price: 200, icon: '◇', accent: BRAND.iq.accent,      logo: BRAND.iq.logo,      blurb: 'Deep analytics and opposition scouting' },
  { key: 'fantasy', name: 'BetterFantasy', price: 100, icon: '★', accent: BRAND.fantasy.accent, logo: BRAND.fantasy.logo, blurb: 'A season-long club fantasy league off your real match data' },
]

// Bundle discount on the whole price: pick any 2 or 3 modules for 5% off, four
// or more for 10%. (2 to 3 modules take the 5% band; 4+ takes 10%.)
export function discountRate(moduleCount) {
  if (moduleCount >= 4) return 0.10
  if (moduleCount >= 2) return 0.05
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
export const ALL_IN = priceFor(PRICED_MODULES.map((m) => m.key)).total  // 900

// ── Competitor stack ─────────────────────────────────────────────────────────
// What a club would otherwise pay to match Better Cricket's scope, using each
// tool's own published price (AUD; Pitchero converted from GBP) on a
// representative plan. Conservative plans are used, so a busy multi-team club
// pays more on the competitors and the gap only widens. Better Cricket replaces
// the lot for one flat ALL_IN price, so the saving is the difference.
export const COMPETITOR_STACK = [
  { tool: 'ClubStats', plan: 'Medium', forJob: 'Cricket stats & public site', replacedBy: 'BetterStats', cost: 399, note: '$299 to $599 by team count' },
  { tool: 'Squarespace', forJob: 'Club website', replacedBy: 'BetterSocials', cost: 300 },
  { tool: 'Mailchimp', forJob: 'Member emails', replacedBy: 'BetterAdmin', cost: 240 },
  { tool: 'Canva Pro', forJob: 'Match-day social graphics', replacedBy: 'BetterSocials', cost: 165 },
  { tool: 'Pitchero', plan: 'Standard', forJob: 'Membership, payments & team admin', replacedBy: 'BetterAdmin & BetterSelect', cost: 800, note: '£418 a year, converted to AUD' },
]

export const COMPETITOR_TOTAL = COMPETITOR_STACK.reduce((sum, c) => sum + c.cost, 0)  // 1904
export const SAVING = COMPETITOR_TOTAL - ALL_IN                                       // 1004

// Better Cricket loads your full history at no extra cost. The closest cricket
// rival (ClubStats) charges a one-off historical-import fee on top of the
// subscription, from $499 up to about $1,000 for big clubs. CricketStatz, the
// desktop stats package, is another stats option at $199 to $798 a year.
export const IMPORT_NOTE = 'from $499, up to about $1,000 for big clubs'
