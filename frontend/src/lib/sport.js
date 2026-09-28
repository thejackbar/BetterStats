// Which sport this build serves. The AFL silo is the same codebase built with
// VITE_SPORT=afl (see docs/afl-betterstats-plan.md); import.meta.env is replaced
// at build time, so the cricket bundle carries none of the football branches.
//
// Shared module screens (BetterAdmin, BetterSocials) read this where they would
// otherwise link to a cricket-only surface: the module switcher, the trial
// banner, bookmarks and the setup wizard don't exist in the football app.
export const IS_AFL = import.meta.env.VITE_SPORT === 'afl'

// The sport's house name, for copy that names the platform.
export const PLATFORM_NAME = IS_AFL ? 'BetterFootball' : 'BetterCricket'
