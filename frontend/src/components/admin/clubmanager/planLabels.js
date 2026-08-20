// How an objective is named wherever it is referred to from somewhere else.
//
// A club's plan is three tiers — PLAN › THEME › OBJECTIVE — and an objective's
// own title is usually a whole sentence ("Appoint accredited, high-quality
// coaches for all senior and junior squads."). Naming it without its theme
// loses the half of the breadcrumb that actually groups the work, so both the
// picker's label and the written-out breadcrumb are built from ONE function
// here; two copies is how a dropdown and the card beside it start disagreeing
// about what an action serves.
//
// Its own tiny module rather than a corner of governance.jsx, because the
// screens that only NAME an objective (the Committee actions list, a board
// card) must not pull the whole governance bundle in to do it.

// The tiers an objective sits under, outermost first, skipping the ones it has
// no answer for — an objective on no plan, or under no theme, is ordinary.
export function objectiveTiers(o) {
  if (!o) return []
  return [
    o.plan_name ? { key: 'PLAN', value: o.plan_name } : null,
    o.pillar_name ? { key: 'THEME', value: o.pillar_name } : null,
    { key: 'OBJECTIVE', value: o.title },
  ].filter(Boolean)
}

// The one-line form: "Strategic Plan 2026 › Participation › Grow junior numbers".
export const objectiveLabel = o => objectiveTiers(o).map(t => t.value).join(' › ')
