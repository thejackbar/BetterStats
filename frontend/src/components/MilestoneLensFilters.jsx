// The "who" filters shared by the club's Milestones screen and the public
// Records > Milestones tab: age group (Seniors, Juniors...) and "Since last
// played", which takes players who have gone quiet off the list.
//
// Controlled: the screen owns `ageGroup` and `since` and passes them in, so the
// rows it filters and the buttons it draws cannot disagree. Pure helpers live
// in lib/milestoneLens.js.

import { AGE_GROUP_LABELS, SINCE_OPTIONS, seasonLabel } from '../lib/milestoneLens'

export default function MilestoneLensFilters({ lens, ageGroup, onAgeGroup, since, onSince }) {
  // Only the groups that exist in this club's data get a button; a club with
  // no juniors never sees a Juniors button that leads nowhere. One group on
  // its own is nothing to filter between.
  const groups = Array.isArray(lens?.age_groups) ? lens.age_groups : []
  const showGroups = groups.length > 1
  const current = lens?.current_season
  return (
    <>
      {showGroups && (
        <div className="flex border pb-hairline rounded overflow-hidden" role="group" aria-label="Age group">
          {[['all', 'All'], ...groups.map(g => [g, AGE_GROUP_LABELS[g] || g])].map(([val, label]) => (
            <button
              key={val}
              type="button"
              onClick={() => onAgeGroup(val)}
              aria-pressed={ageGroup === val}
              className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                ageGroup === val ? 'bg-pb-surface2' : 'text-pb-faint hover:text-pb-text'
              }`}
              style={ageGroup === val ? { color: 'var(--pb-accent)' } : {}}
            >
              {label.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      <label className="flex items-center gap-2">
        <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Last played</span>
        <select
          value={since}
          onChange={e => onSince(e.target.value)}
          aria-label="Since last played"
          title={current != null ? `Counted back from the ${seasonLabel(current)} season` : undefined}
          className="px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50"
        >
          {SINCE_OPTIONS.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
        </select>
      </label>
    </>
  )
}
