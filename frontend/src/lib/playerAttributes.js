// Single source of truth for a player's descriptive cricket attributes — the
// option sets used by the admin editor (BetterSelect Players + Admin → Players)
// and the human-readable labels used to render them on the public profile.
// Keeping these here means the editor and the public profile never drift.

export const ROLE_OPTS = ['', 'Batter', 'Bowler', 'All Rounder', 'Wicketkeeper', 'Wicketkeeper-Batter']

// Canonical role → skill codes the selection/availability filters + role chips
// key on. Role is the single source of truth; skill_positions are derived from
// it on save so the facets never drift.
export const ROLE_TO_SKILLS = {
  'Batter': ['BAT'],
  'Bowler': ['BWL'],
  'All Rounder': ['ALL'],
  'Wicketkeeper': ['WKT'],
  'Wicketkeeper-Batter': ['WKT', 'BAT'],
}

export const BAT_HANDS = [['', '—'], ['RIGHT', 'Right handed'], ['LEFT', 'Left handed']]

export const GENDER_OPTS = [['', '—'], ['male', 'Male'], ['female', 'Female']]

// Bowling action + type merged into one human-readable field. Each entry maps a
// label to the (bowling_action, bowling_type) pair persisted on the player.
export const BOWLING_OPTS = [
  ['—', null, null],
  ['Right-arm fast', 'RIGHT_ARM', 'FAST'],
  ['Right-arm fast-medium', 'RIGHT_ARM', 'FAST_MEDIUM'],
  ['Right-arm medium', 'RIGHT_ARM', 'MEDIUM'],
  ['Off spin', 'RIGHT_ARM', 'FINGER_SPIN'],
  ['Leg spin', 'RIGHT_ARM', 'WRIST_SPIN'],
  ['Left-arm fast', 'LEFT_ARM', 'FAST'],
  ['Left-arm medium', 'LEFT_ARM', 'MEDIUM'],
  ['Left-arm orthodox', 'LEFT_ARM', 'FINGER_SPIN'],
  ['Left-arm wrist spin', 'LEFT_ARM', 'WRIST_SPIN'],
]

// (action, type) → label, for deriving the current selection / display string.
export function bowlingLabel(action, type) {
  const hit = BOWLING_OPTS.find((o) => o[1] === (action || null) && o[2] === (type || null))
  return hit ? hit[0] : '—'
}
export function bowlingFromLabel(label) {
  const hit = BOWLING_OPTS.find((o) => o[0] === label)
  return hit ? { bowling_action: hit[1], bowling_type: hit[2] } : { bowling_action: null, bowling_type: null }
}
export function bowls(action, type) {
  return !!(action || type)
}

export function battingHandLabel(hand) {
  if (hand === 'LEFT') return 'Left handed'
  if (hand === 'RIGHT') return 'Right handed'
  return null
}
// Short form for compact strips (RHB / LHB).
export function battingHandShort(hand) {
  if (hand === 'LEFT') return 'LHB'
  if (hand === 'RIGHT') return 'RHB'
  return null
}

// Gender has historically been stored mixed-case ("Male" from the old admin
// modal, "male" from BetterSelect). Normalise for editing/comparison and
// present a tidy label everywhere.
export function normalizeGender(g) {
  return (g || '').toString().trim().toLowerCase()
}
export function genderLabel(g) {
  const v = normalizeGender(g)
  if (v === 'male') return 'Male'
  if (v === 'female') return 'Female'
  return g || null
}
