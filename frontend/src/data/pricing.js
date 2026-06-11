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
  price: 399,
  icon: '◆',
  accent: BRAND.stats.accent,
  logo: BRAND.stats.logo,
  blurb: 'Reconciled stats and your public club site',
}

// The bolt-on modules and their annual price. Logos/accents come from the shared
// brand registry so the calculator looks like the dashboard.
export const PRICED_MODULES = [
  { key: 'select',  name: 'BetterSelect',  price: 149, icon: '◎', accent: BRAND.select.accent,  logo: BRAND.select.logo,  blurb: 'Player availability, team selection and net manager' },
  { key: 'socials', name: 'BetterSocials', price: 149, icon: '◈', accent: BRAND.socials.accent, logo: BRAND.socials.logo, blurb: 'Social-post generation and a CRM for your club website' },
  { key: 'admin',   name: 'BetterAdmin',   price: 149, icon: '⬢', accent: BRAND.admin.accent,   logo: BRAND.admin.logo,   blurb: 'Member fees, bulk emailing and merch (coming soon)' },
  { key: 'iq',      name: 'BetterIQ',      price: 249, icon: '◇', accent: BRAND.iq.accent,      logo: BRAND.iq.logo,      blurb: 'Deep analytics and opposition scouting' },
]

// Bundle discount in whole dollars, keyed on how many modules you add (not a
// percentage). It lines up with the published bundle prices: add two modules
// and you save $48, three saves $97, all four saves $146. So every bundle lands
// on a tidy price and the full set (Core + all four) comes to $949.
export const BUNDLE_DISCOUNT = { 0: 0, 1: 0, 2: 48, 3: 97, 4: 146 }

export function bundleDiscount(moduleCount) {
  return BUNDLE_DISCOUNT[moduleCount] ?? 0
}

// Price a selection of module keys. Returns the subtotal, the discount and the
// total, all in whole AUD.
export function priceFor(selectedKeys = []) {
  const mods = PRICED_MODULES.filter((m) => selectedKeys.includes(m.key))
  const subtotal = CORE.price + mods.reduce((sum, m) => sum + m.price, 0)
  const discount = bundleDiscount(mods.length)
  return { subtotal, discount, total: subtotal - discount, moduleCount: mods.length, modules: mods }
}

// The full-set saving (Core + every module) and the everything price, for copy.
export const MAX_BUNDLE_SAVING = bundleDiscount(PRICED_MODULES.length)             // 146
export const ALL_IN = priceFor(PRICED_MODULES.map((m) => m.key)).total            // 949

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
export const SAVING = COMPETITOR_TOTAL - ALL_IN                                       // 955

// Better Cricket loads your full history at no extra cost. The closest cricket
// rival (ClubStats) charges a one-off historical-import fee on top of the
// subscription, from $499 up to about $1,000 for big clubs. CricketStatz, the
// desktop stats package, is another stats option at $199 to $798 a year.
export const IMPORT_NOTE = 'from $499, up to about $1,000 for big clubs'
