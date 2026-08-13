// Watchlist card option lists — mirrors backend/app/services/scout_watchlist.py's
// REGION_OPTS/LEVEL_OPTS exactly (keep both in sync by hand, same as any
// other option-list pair in this codebase). Role/batting-hand/bowling type
// are NOT redefined here — they're re-exported from the same single source
// of truth every other player editor in the app already uses, so a
// watchlist card's dropdowns are byte-identical to a real player profile's.
export { ROLE_OPTS, BAT_HANDS, BOWLING_OPTS, bowlingLabel, bowlingFromLabel } from '../../lib/playerAttributes'

export const REGION_OPTS = [
  '', 'WA', 'NSW', 'VIC', 'QLD', 'SA', 'TAS', 'NT', 'ACT',
  'North England', 'South England', 'Midlands', 'Scotland', 'Wales',
  'Other/International',
]

export const LEVEL_OPTS = ['', 'Premier Cricket', 'Grade Cricket', 'Community Cricket', 'Junior/Colts', 'Other']
