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

  const headline = short
    ? (filtered
        ? `Counted from the ${breakdown_matches} of ${career_matches} matches we hold a scorecard for.`
        : `${breakdown_matches} of these ${career_matches} matches can be broken down by competition, grade or format.`)
    : (filtered
        ? `Counted from the ${breakdown_matches} matches we hold a scorecard for, ${extra_scorecards} more than the season totals count.`
        : `Filtering counts ${breakdown_matches} matches, ${extra_scorecards} more than the ${career_matches} in the season totals.`)

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
            The career total, {career_matches} matches, comes from Cricket Australia's
            own season figures. Those figures do not say which grade a match was played
            in, so they cannot be split by competition, grade type or format.
          </p>
          <p className="mb-2">
            Anything you filter — a competition, a grade type, a format — is counted from
            the {breakdown_matches} matches we hold a scorecard for, not from the career
            total. That is why the parts do not add up to {career_matches}.
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
