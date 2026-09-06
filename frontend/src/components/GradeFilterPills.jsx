import {
  CATEGORY_LABELS, FORMAT_LABELS, GRADE_CATEGORIES, MATCH_FORMATS,
} from '../lib/gradeCategories'

// One pill row: All, plus one option each. The shape both grade axes use —
// "show me the women's grades", "show me the T20s" — as opposed to the older
// additive Include row, which asked the same question a less direct way.
//
// Shared by SeasonSelector (the club dashboard, Leaderboard, Records, Players,
// Games) and the player profile, which draws its own filter bar. One component
// so the two cannot drift into looking or behaving differently.
export function FilterPillRow({ label, options, value, onChange, title, labelClass }) {
  if (!options.length) return null
  return (
    <div className="flex items-center gap-2">
      <label className={labelClass || 'font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block'}>
        {label}
      </label>
      <div className="flex items-center border pb-hairline rounded overflow-hidden">
        {[{ key: '', label: 'All' }, ...options].map(opt => (
          <button
            key={opt.key || 'all'}
            onClick={() => onChange(opt.key || null)}
            aria-pressed={(value || '') === opt.key}
            title={opt.key ? title?.(opt) : `Every ${label.toLowerCase()}`}
            className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
              (value || '') === opt.key
                ? 'bg-pb-accent/15 text-pb-accent'
                : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

// The options a club's own grades justify offering. A club with no junior
// programme is never shown a Juniors pill, which is also exactly when the
// filter would do nothing.
export function gradeTypeOptions(availableCategories = []) {
  return GRADE_CATEGORIES
    .filter(c => availableCategories.includes(c))
    .map(c => ({ key: c, label: CATEGORY_LABELS[c] || c }))
}

export function matchFormatOptions(availableFormats = []) {
  return MATCH_FORMATS
    .filter(f => availableFormats.includes(f))
    .map(f => ({ key: f, label: FORMAT_LABELS[f] || f }))
}

// The club's own competitions, in the order it reads them.
//
// A club with FEWER THAN TWO is offered none at all, and that is deliberate:
// filtering to your only competition is a control that can only ever answer
// "everything", which is the same call ageFilterOptions and the Fees/Training
// source notes make. It is also exactly the club for whom this whole feature
// is a no-op, so the row correctly disappears for most of the platform.
export function competitionOptions(availableCompetitions = []) {
  if (!availableCompetitions || availableCompetitions.length < 2) return []
  return availableCompetitions.map(c => ({ key: String(c.id), label: c.name }))
}

// The two rows together, for a screen that just wants both.
export function GradeFilterPills({
  gradeType, setGradeType, matchFormat, setMatchFormat,
  competition, setCompetition,
  availableCategories = [], availableFormats = [], availableCompetitions = [],
  labelClass,
}) {
  return (
    <>
      <FilterPillRow
        label="Competition"
        options={competitionOptions(availableCompetitions)}
        value={competition}
        onChange={setCompetition}
        title={opt => `Only ${opt.label}`}
        labelClass={labelClass}
      />
      <FilterPillRow
        label="Grade Type"
        options={gradeTypeOptions(availableCategories)}
        value={gradeType}
        onChange={setGradeType}
        title={opt => `Only ${opt.label} grades`}
        labelClass={labelClass}
      />
      <FilterPillRow
        label="Match Type"
        options={matchFormatOptions(availableFormats)}
        value={matchFormat}
        onChange={setMatchFormat}
        title={opt => `Only ${opt.label} matches`}
        labelClass={labelClass}
      />
    </>
  )
}
