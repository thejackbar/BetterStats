import { CORE_MARKETING, MODULES_MARKETING } from '../data/modules-marketing'

/**
 * Resolves the module a video is filed under to the marketing page a viewer
 * should be sent to afterwards.
 *
 * A walkthrough of team selection that ends by pitching BetterStats is sending
 * an interested visitor to the wrong page, so the "Want this for your club?"
 * call to action follows the video's own module.
 *
 * `module_label` is free text in the database, and the four videos uploaded
 * before the picker existed were typed by hand, so matching is deliberately
 * forgiving: case and spacing are ignored, and "Better Select" resolves the
 * same as "betterselect". A label that matches nothing is not guessed at — the
 * caller falls back to the generic BetterCricket pitch.
 */

// BetterStats keeps /features rather than /modules/betterstats: it is the Core
// feature page, richer than the module card, and it is where the button
// already pointed.
const CORE = {
  slug: CORE_MARKETING.slug,
  name: CORE_MARKETING.name,
  to: '/features',
  heading: 'Get automated stats for your cricket club.',
  cta: 'SEE FEATURES',
}

const HEADINGS = {
  betterselect: 'Sort availability and selection for your club.',
  bettersocials: "Run your club's website and match-day posts.",
  betteradmin: "Run your club's back office in one place.",
  betteriq: 'Scout the opposition using your own match data.',
  betterfantasy: "Run a fantasy comp off your club's own games.",
}

const MODULES = [
  CORE,
  ...MODULES_MARKETING.map((m) => ({
    slug: m.slug,
    name: m.name,
    to: `/modules/${m.slug}`,
    heading: HEADINGS[m.slug] || `Bring ${m.name} to your cricket club.`,
    cta: `SEE ${m.name.toUpperCase()}`,
  })),
]

/** The options the Super Admin picker offers, in the site's own module order. */
export const VIDEO_MODULE_OPTIONS = MODULES.map((m) => ({ slug: m.slug, name: m.name }))

const key = (value) => String(value || '').toLowerCase().replace(/[^a-z]/g, '')
const BY_KEY = new Map(MODULES.flatMap((m) => [[key(m.slug), m], [key(m.name), m]]))

/** The generic pitch, for a video filed under nothing or under something we
 *  do not recognise. Never a guess at which module was meant. */
export const GENERIC_CTA = {
  heading: 'Get your cricket club on BetterCricket.',
  to: '/modules',
  cta: 'SEE THE MODULES',
}

export function videoModuleCta(label) {
  return BY_KEY.get(key(label)) || GENERIC_CTA
}
