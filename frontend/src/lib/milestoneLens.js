// The two filters on the Milestones screens that read per-player facts the
// server derives (services/milestone_activity.annotate_players): the kind of
// cricket a player plays, and how recently they last played.
//
// Each item carries `age_groups` (the grade categories of the grades the
// player turned out in during their newest season) and `last_played_season`
// (the starting year of that season). `lens.current_season` is the club's
// newest season. A player the server could not place keeps their rows under
// every setting: hiding someone on a guess is the worse mistake.

export const AGE_GROUP_LABELS = {
  senior: 'Seniors',
  junior: 'Juniors',
  womens: "Women's",
  masters: 'Masters',
  mixed: 'Mixed',
}

// [value, label]. A value is the number of seasons counted back from the
// club's current one, "any" turns the filter off.
export const SINCE_OPTIONS = [
  ['any', 'Any time'],
  ['1', 'This season'],
  ['2', 'Last 2 seasons'],
  ['3', 'Last 3 seasons'],
  ['5', 'Last 5 seasons'],
  ['10', 'Last 10 seasons'],
]

export function ageGroupMatch(item, ageGroup) {
  if (!ageGroup || ageGroup === 'all') return true
  const groups = item.age_groups
  // Not placed by the server: leave the row in.
  if (!Array.isArray(groups) || groups.length === 0) return true
  return groups.includes(ageGroup)
}

export function sinceMatch(item, since, currentSeason) {
  if (!since || since === 'any') return true
  const seasons = Number(since)
  if (!Number.isFinite(seasons) || currentSeason == null) return true
  const last = item.last_played_season
  if (last == null) return true
  return last >= currentSeason - (seasons - 1)
}

export function lensMatch(item, { ageGroup, since }, currentSeason) {
  return ageGroupMatch(item, ageGroup) && sinceMatch(item, since, currentSeason)
}

// "2026/27" for a season that starts in 2026. Used in the screen's own note.
export function seasonLabel(start) {
  if (start == null) return ''
  return `${start}/${String((start + 1) % 100).padStart(2, '0')}`
}
