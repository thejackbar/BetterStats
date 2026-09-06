import { useState } from 'react'

/**
 * Why a career total and the per-competition figures do not add up.
 *
 * A career carries two match counts and a filter switches between them: with
 * no filter the figure is Cricket Australia's own season totals, and the
 * moment any filter is picked it has to be counted from the scorecards we
 * hold, because a grade — and so a competition, a grade type or a format — is
 * only recorded on a match.
 *
 * SAID BEFORE ANYONE HAS TO NOTICE, which is the whole point. The note draws
 * on the UNFILTERED view too, not only once a filter is on, so nobody works
 * out for themselves that the competitions do not sum to the career total and
 * reads it as a mistake.
 *
 * IT RUNS BOTH WAYS. We hold more scorecards than CA counts about as often as
 * we hold fewer (20% of players against 39%, measured across the platform), so
 * every line here has to read correctly when the filtered figure is the LARGER
 * one — "337 of 333" is the shape of a bug, not an explanation.
 *
 * Drawn only where the two genuinely differ (the backend sends the block only
 * then). A note on every player is noise that teaches people to stop reading
 * notes — the same rule RateCoverage keeps for a strike rate.
 */
export function MatchCoverageNote({ coverage, filtered = false, className = '' }) {
  const [open, setOpen] = useState(false)
  if (!coverage) return null
  const { career_matches, breakdown_matches, without_scorecard, extra_scorecards } = coverage
  const short = without_scorecard > 0

  // THE FILTERED LINE MUST NOT CLAIM TO BE THE HEADLINE. A club with junior
  // grades has a DEFAULT scope active with nobody having touched a control, so
  // the figure above this note is already a filtered one — neither of the two
  // career figures here. Saying "counted from the N matches we hold a
  // scorecard for" beside a headline that reads something else is the same
  // class of mistake this note exists to prevent, one level down.
  const headline = filtered
    ? `Filtered figures are counted from the ${breakdown_matches} matches we hold `
      + `a scorecard for, not the ${career_matches} in Cricket Australia's season totals.`
    : short
      ? `${breakdown_matches} of these ${career_matches} matches can be broken down by competition, grade or format.`
      : `Filtering counts ${breakdown_matches} matches, ${extra_scorecards} more than the ${career_matches} in the season totals.`

  return (
    <div className={`mt-2 ${className}`}>
      <p className="font-mono text-[10px] text-pb-dim flex items-center gap-1.5 flex-wrap">
        <span>{headline}</span>
        <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
          className="w-4 h-4 rounded-full border border-pb-dim/50 text-[9px] leading-none
                     text-pb-dim hover:text-pb-text hover:border-pb-text shrink-0"
          aria-label="Why these figures differ">i</button>
      </p>
      {open && (
        <div className="mt-2 p-3 rounded-lg text-[12px] leading-relaxed text-pb-dim"
             style={{ background: 'var(--pb-surface2)' }}>
          <p className="mb-2">
            <strong className="text-pb-text">Two records of the same career.</strong>{' '}
            Cricket Australia's own season figures count {career_matches} matches in
            this career. They do not say which grade a match was played in, so they
            cannot be split by competition, grade type or format.
          </p>
          <p className="mb-2">
            Anything you filter — a competition, a grade type, a format — is counted from
            the {breakdown_matches} matches we hold a scorecard for, not from Cricket
            Australia's count. That is why the parts do not add up to {career_matches}.
          </p>
          {short && (
            <p className="mb-2">
              The other {without_scorecard} {without_scorecard === 1 ? 'match is' : 'matches are'}{' '}
              counted in the career total and appear under no competition, because we hold no
              scorecard for {without_scorecard === 1 ? 'it' : 'them'} at all. There is nothing
              waiting to be filed — the {without_scorecard === 1 ? 'match is' : 'matches are'}{' '}
              not in the records as {without_scorecard === 1 ? 'a game' : 'games'}, only in
              Cricket Australia's season count.
            </p>
          )}
          {extra_scorecards > 0 && (
            <p className="mb-2">
              Here it runs the other way: we hold {extra_scorecards} more{' '}
              {extra_scorecards === 1 ? 'scorecard' : 'scorecards'} than the season totals
              count, so a filtered figure can be higher than the career total rather than
              lower.
            </p>
          )}
          <p className="mb-0">
            Both figures are real. Neither is adjusted to match the other.
          </p>
        </div>
      )}
    </div>
  )
}

export default MatchCoverageNote

/**
 * Why the by-grade grid's TOTAL is a third number again.
 *
 * The grid is neither of the two figures on the header, and by construction it
 * cannot be. It reconciles PER SEASON AND GRADE, taking whichever is higher —
 * the scorecards we hold for that grade, or Cricket Australia's own per-grade
 * figure — and adds a season's unplaceable shortfall on the end. That is the
 * right rule for a grade breakdown (it is the most complete per-grade picture
 * available, and `max` is what stops a shared fixture the other club synced
 * first vanishing off a row), and it is the reason the total sits above both.
 *
 * EVERY FIGURE HERE IS DERIVED FROM THE GRID'S OWN ROWS, never asserted: the
 * scorecard column is what the rows carry, the added column is the sum of the
 * asterisks, and the two add up to the printed total. A sentence that merely
 * claimed the total was "worked out differently" would tell a reader nothing
 * they could check.
 */
export function GradeTotalNote({ rows = [], unattributed = 0, coverage = null,
                                 scoped = false, className = '' }) {
  const held = rows.reduce((n, r) => n + (r.scorecard_matches || 0), 0)
  const added = rows.reduce((n, r) => n + (r.attributed_unknown || 0), 0)
  const total = held + added + unattributed
  // Matches we hold a scorecard for that carry no grade — an uploaded card with
  // the grade left blank. They belong to no row here at all, so without this
  // line the grid quietly holds fewer scorecards than the header says we have.
  // Only comparable while the grid is showing the whole career. `coverage` is
  // deliberately scope-independent — it is a fact about the career, not the
  // view — so subtracting a FILTERED `held` from it would report every match
  // the filter just excluded as one with no grade, which is the opposite of
  // true.
  const noGrade = coverage && !scoped
    ? Math.max((coverage.breakdown_matches || 0) - held, 0)
    : 0
  if (!added && !unattributed && !noGrade) return null

  return (
    <div className={`font-mono text-[10px] text-pb-dim tracking-wide2 space-y-1 ${className}`}>
      <p>
        This total is worked out season by season and grade by grade, taking
        whichever is higher: the scorecards we hold, or Cricket Australia's own
        figure for that grade.{!scoped && ' It is its own number, and does not '
          + 'have to match the career total above.'}
      </p>
      <p>
        {held.toLocaleString()} we hold a scorecard for
        {added > 0 && <> {' '}+ {added.toLocaleString()} Cricket Australia counts in
          a grade we hold no scorecard for (marked *)</>}
        {unattributed > 0 && <> {' '}+ {unattributed.toLocaleString()} it counts in
          a season we cannot place in one grade</>}
        {' '}= {total.toLocaleString()}.
      </p>
      {noGrade > 0 && (
        <p>
          A further {noGrade.toLocaleString()}{' '}
          {noGrade === 1 ? 'match has' : 'matches have'} a scorecard but no grade
          recorded, so {noGrade === 1 ? 'it appears' : 'they appear'} on no row
          here. {noGrade === 1 ? 'It is' : 'They are'} still counted in the
          career figures above.
        </p>
      )}
    </div>
  )
}
