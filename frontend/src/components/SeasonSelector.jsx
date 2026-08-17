import { formatSeason } from '../lib/cricketFormat'
import { CATEGORY_LABELS, TOGGLEABLE_CATEGORIES, scopeNote } from '../lib/gradeCategories'
import {
  FilterPillRow, gradeTypeOptions, matchFormatOptions,
} from './GradeFilterPills'

export default function SeasonSelector({
  seasons = [],
  grades = [],
  selectedSeason,
  setSelectedSeason,
  selectedGrade,
  setSelectedGrade,
  finalsOnly = false,
  setFinalsOnly = () => {},
  captainOnly = false,
  setCaptainOnly = () => {},
  gender = null,
  setGender = () => {},
  overseas = null,
  setOverseas = () => {},
  showOverseasFilter = false,
  showGenderFilter = true,
  showFinalsFilter = true,
  showCaptainFilter = true,
  // Which grade categories count. `categories` is the array currently counted;
  // `availableCategories` is what this club's grades actually justify offering,
  // so a club with no junior programme never sees a Juniors toggle at all.
  categories = null,
  setCategories = () => {},
  availableCategories = [],
  showCategoryFilter = true,
  // The two grade axes, as pick-one filters. `gradeType` is a single category
  // key (or null for "whatever the club counts by default"); `matchFormat` is a
  // single format key (or null for every format). Both are what a club actually
  // asks the dashboard — "show me the women's grades", "show me the T20s" —
  // whereas the additive `categories` Include row above answers a different
  // question and stays where it is for the Leaderboard and Records pages.
  gradeType = null,
  setGradeType = () => {},
  matchFormat = null,
  setMatchFormat = () => {},
  availableFormats = [],
  // What the club counts when no grade type is picked, so "All" can say what it
  // actually leaves out instead of quietly dropping a club's juniors.
  defaultCategories = null,
  showGradeTypeFilter = false,
  showMatchFormatFilter = false,
}) {
  // Senior is not offered as a toggle: it is the baseline every other category
  // is added to, and letting someone switch it off would mostly produce an
  // empty page. Turning a category ON adds those grades' games to the figures.
  const toggleable = TOGGLEABLE_CATEGORIES.filter(c => availableCategories.includes(c))
  const counted = categories || []
  const flip = (key) => {
    const next = counted.includes(key)
      ? counted.filter(c => c !== key)
      : [...counted, key]
    setCategories(next)
  }

  // Derived from the props already here rather than threaded down from a
  // response: what is left out is exactly the club's categories minus the ones
  // currently ticked, and the leaderboard endpoints return bare arrays with no
  // scope of their own to read.
  const excluded = availableCategories.filter(c => !counted.includes(c))
  const note = categories
    ? scopeNote({ active: excluded.length > 0, excluded_categories: excluded })
    : null

  const typeOptions = gradeTypeOptions(availableCategories)
  const formatOptions = matchFormatOptions(availableFormats)

  // "All" means the club's own default, which normally leaves juniors out. Say
  // so, and only while it is actually true — a club with no junior programme
  // never reads about a filter that is doing nothing.
  const defaultNote = (showGradeTypeFilter && !gradeType && defaultCategories)
    ? scopeNote(
        {
          active: true,
          excluded_categories: availableCategories.filter(c => !defaultCategories.includes(c)),
        },
        'Grade Type',
      )
    : null

  return (
    <div className="space-y-1.5">
    <div className="flex flex-wrap gap-2 items-center">
      {/* Season - always shown */}
      {seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Season</label>
          <select
            value={selectedSeason || ''}
            onChange={e => setSelectedSeason(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All seasons</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
          </select>
        </div>
      )}

      {/* Visual divider when there are secondary filters */}
      {(grades.length > 0 || seasons.length > 0) && (
        <div className="h-5 w-px bg-pb-hairline mx-1 hidden sm:block" />
      )}

      {/* Grade */}
      {grades.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Grade</label>
          <select
            value={selectedGrade || ''}
            onChange={e => setSelectedGrade(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All grades</option>
            {grades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </div>
      )}

      {/* Grade categories - one on/off pill each, added on top of a baseline.
          Hidden when the pick-one Grade Type row below is shown: the two answer
          the same question in two different ways, and a screen offering both
          just invites them to disagree. */}
      {showCategoryFilter && !showGradeTypeFilter && toggleable.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Include</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {toggleable.map(key => (
              <button
                key={key}
                onClick={() => flip(key)}
                aria-pressed={counted.includes(key)}
                title={counted.includes(key)
                  ? `${CATEGORY_LABELS[key]} grades are counted — click to leave them out`
                  : `${CATEGORY_LABELS[key]} grades are left out — click to count them`}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  counted.includes(key)
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {CATEGORY_LABELS[key]}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Grade type — how the GRADE is classified (men's / juniors / women's /
          masters), not a player attribute. This is what replaced the Gender
          pills on the club dashboard: a woman playing in a men's grade was
          being counted as women's cricket, and a men's grade with a
          mis-recorded player gender vanished from the men's figures. */}
      {showGradeTypeFilter && (
        <FilterPillRow
          label="Grade Type"
          options={typeOptions}
          value={gradeType}
          onChange={setGradeType}
          title={opt => `Only ${opt.label} grades`}
        />
      )}

      {/* Match type — read from each FIXTURE's own recorded format, not from the
          grade: a 1st Grade season routinely mixes one-day and two-day games,
          so a grade-level answer would be wrong for most of them. Renders only
          for a club whose matches can actually be told apart. */}
      {showMatchFormatFilter && (
        <FilterPillRow
          label="Match Type"
          options={formatOptions}
          value={matchFormat}
          onChange={setMatchFormat}
          title={opt => `Only ${opt.label} matches`}
        />
      )}

      {/* Gender filter - pill toggle */}
      {showGenderFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Gender</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: null, label: 'All' },
              { value: 'Male', label: 'Men' },
              { value: 'Female', label: 'Women' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setGender(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  gender === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Games - pill toggle */}
      {showFinalsFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Games</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: false, label: 'All' },
              { value: true, label: 'Finals' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setFinalsOnly(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  finalsOnly === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Overseas filter - pill toggle */}
      {showOverseasFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Overseas</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: null, label: 'All' },
              { value: 'exclude', label: 'Local' },
              { value: 'only', label: 'Overseas' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setOverseas(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  overseas === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Captain filter - pill toggle */}
      {showCaptainFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Captain</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: false, label: 'All' },
              { value: true, label: 'Captain' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setCaptainOnly(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  captainOnly === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
    {/* Says what the figures currently leave out, and where to change it. Only
        renders while something is actually excluded, so a club with only senior
        grades never reads about a filter that is doing nothing. */}
    {(note || defaultNote) && <p className="text-[11px] text-pb-faint">{note || defaultNote}</p>}
    </div>
  )
}
