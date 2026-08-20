// The club's association rules, as the screens read them.
//
// Every judgement is the server's (services/selection_rules.py) — a pool player
// arrives carrying `rule_flags`, `rule_notes` and `rule_state`, and this module
// only decides how they are drawn. The one exception is the overseas cap, which
// depends on who ELSE is in the side: the board counts it live so a selector
// watches it fill up, and the save path re-counts it for real.
//
// A club with no rules gets empty arrays from all of this, which is what keeps
// every screen looking exactly as it did before rules existed.

// Two letters doing a lot of work, so every badge carries hover text. The
// codes for fees and training are the ones the board already used, so a rule
// on either recolours the badge that was there rather than adding a second.
export const RULE_BADGE = {
  age: 'AGE',
  overseas: 'OS',
  finals_qualification: 'QF',
  grade_cap: 'GR',
  fees: '$',
  training: 'NT',
  registration: 'REG',
  rest: 'REST',
  custom: '!',
}

export const SEVERITY_TONE = { block: 'red', warn: 'amber', info: 'faint' }

/** Badges for one pool player: one per rule they fall foul of. */
export function ruleBadges(player) {
  return (player?.rule_flags || []).map((f) => ({
    key: f.rule_id,
    kind: f.kind,
    tone: SEVERITY_TONE[f.severity] || 'amber',
    label: RULE_BADGE[f.kind] || '!',
    title: `${f.name}: ${f.detail}`,
  }))
}

/** True when a rule of this kind already speaks for the player, so the board's
 *  own plain badge for the same fact shouldn't be drawn twice. */
export function hasRuleFlag(player, kind) {
  return (player?.rule_flags || []).some((f) => f.kind === kind)
}

export function isBlocked(player) {
  return player?.rule_state === 'block'
}

/** The workload note and any permit, as plain lines under the name. */
export function ruleNotes(player) {
  return (player?.rule_notes || []).map((n) => n.detail).filter(Boolean)
}

/**
 * The XI-level rules, counted against the side as it stands.
 * Returns one entry per rule that is over its cap.
 */
export function evaluateXI(rules, playerIds) {
  const picked = new Set((playerIds || []).filter(Boolean).map(String))
  const out = []
  for (const rule of rules?.team || []) {
    if (rule.kind !== 'overseas') continue
    const inXI = (rule.player_ids || []).filter((id) => picked.has(String(id)))
    const cap = rule.config?.max_in_xi ?? 1
    out.push({
      rule_id: rule.id,
      kind: rule.kind,
      name: rule.name,
      severity: rule.severity,
      count: inXI.length,
      cap,
      over: inXI.length > cap,
      detail: cap === 0
        ? `${inXI.length} overseas player${inXI.length === 1 ? '' : 's'} named, none allowed`
        : `${inXI.length} of ${cap} overseas player${cap === 1 ? '' : 's'}`,
    })
  }
  return out
}

/**
 * Everything wrong with the side as it stands: the players who break a rule,
 * and the XI-level caps that are over. Split by severity, because a warning is
 * the selector's to weigh and a block will refuse the save.
 */
export function xiCompliance(rules, poolById, playerIds) {
  const blocking = []
  const warnings = []
  for (const id of (playerIds || []).filter(Boolean)) {
    const p = poolById[id]
    for (const f of p?.rule_flags || []) {
      const line = { player: p.display_name, name: f.name, detail: f.detail, kind: f.kind }
      if (f.severity === 'block') blocking.push(line)
      else if (f.severity === 'warn') warnings.push(line)
    }
  }
  for (const t of evaluateXI(rules, playerIds)) {
    if (!t.over) continue
    const line = { player: null, name: t.name, detail: t.detail, kind: t.kind }
    if (t.severity === 'block') blocking.push(line)
    else warnings.push(line)
  }
  return { blocking, warnings, ok: !blocking.length && !warnings.length }
}

/* ── The pool filter ─────────────────────────────────────────────────────────
 * Only offered when the club has a rule bearing on this fixture — a control
 * that can only ever answer "everyone is fine" is worse than no control, the
 * same call the Fees and Training filters already make. */
export const RULE_FILTERS = [
  { value: '', label: 'All' },
  { value: 'problem', label: 'Has a problem' },
  { value: 'block', label: 'Ineligible' },
  { value: 'ok', label: 'Clear' },
]

export function matchesRuleFilter(player, value) {
  if (!value) return true
  const state = player?.rule_state || 'ok'
  if (value === 'problem') return state !== 'ok'
  if (value === 'block') return state === 'block'
  return state === 'ok'
}
