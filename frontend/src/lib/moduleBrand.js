// Per-module brand — the single source of truth for each Better Cricket
// module's accent colour and logo mark. Imported by the marketing site, the
// admin dashboard tiles, the sidebar and the per-module layouts so the colour
// and mark never drift between them.
//
// The colours are drawn from the BetterSports palette (see styles/theme.css /
// tailwind.config.js): green is the house brand (--pb-brand), blue is the
// chart "wickets" series, amber is amber.cricket, violet is chart-4. Magenta
// extends the same vivid chart family for BetterSocials.
import statsLogo from '../assets/modules/betterstats.svg'
import selectLogo from '../assets/modules/betterselect.svg'
import socialsLogo from '../assets/modules/bettersocials.svg'
import adminLogo from '../assets/modules/betteradmin.svg'
import iqLogo from '../assets/modules/betteriq.svg'
import fantasyLogo from '../assets/modules/betterfantasy.svg'

// accent     — the named brand colour, legible on the dark navy UI
// accentRgb  — space-separated channels for the layouts' --pb-accent-rgb
//              (mirrors how the module layouts already set it)
// logo       — the module mark (a self-contained coloured tile)
export const MODULE_BRAND = {
  stats:   { name: 'BetterStats',   accent: '#16C784', accentRgb: '22 199 132', logo: statsLogo },
  select:  { name: 'BetterSelect',  accent: '#3B82F6', accentRgb: '59 130 246', logo: selectLogo },
  socials: { name: 'BetterSocials', accent: '#EC4899', accentRgb: '236 72 153', logo: socialsLogo },
  admin:   { name: 'BetterAdmin',   accent: '#F59E0B', accentRgb: '245 158 11', logo: adminLogo },
  iq:      { name: 'BetterIQ',      accent: '#A855F7', accentRgb: '168 85 247', logo: iqLogo },
  fantasy: { name: 'BetterFantasyCricket', accent: '#8C82F0', accentRgb: '140 130 240', logo: fantasyLogo },
}

// The various registries key modules differently (marketing uses slugs, the
// dashboard-tile keys use the umbrella group names). Map them all onto one set.
const ALIAS = {
  betterstats: 'stats', core: 'stats',
  betterselect: 'select',
  bettersocials: 'socials', socials: 'socials',
  betteradmin: 'admin', fees: 'admin', comms: 'admin', merch: 'admin',
  betteriq: 'iq',
  betterfantasy: 'fantasy', betterfantasycricket: 'fantasy', fantasycricket: 'fantasy',
}

// Resolve a module key/slug to its brand. Falls back to the Core (green) so a
// caller never has to null-check.
export function moduleBrand(key) {
  const k = ALIAS[key] || key
  return MODULE_BRAND[k] || MODULE_BRAND.stats
}
