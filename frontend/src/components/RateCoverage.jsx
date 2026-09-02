import { useEffect, useState } from 'react'

/**
 * How a strike rate or an economy says which innings answered it.
 *
 * A season scored partly on an iPad and partly in a written book gives us
 * every run and only some of the ball counts. The figure is worked out from
 * the innings that carry a ball count (see backend/app/services/rate_coverage.py),
 * and these draw the sentence that says so.
 *
 * Nothing renders when the figure covers everything. A note on every rate in
 * the app is noise that trains people to stop reading it, so silence is the
 * default and the note means something when it does appear.
 */

export function isPartial(cov) {
  return !!cov && !cov.complete && (cov.counted > 0 || cov.basis === 'aggregate')
}

/** "3 of 10 innings", or the aggregate wording when there is nothing to count. */
export function coverageText(cov, unit = 'innings') {
  if (!cov) return ''
  if (cov.basis === 'aggregate' || !cov.counted) {
    return 'worked out from season totals'
  }
  const one = unit === 'innings' ? 'innings' : 'spell'
  const many = unit === 'innings' ? 'innings' : 'spells'
  return `from ${cov.counted} of ${cov.of} ${cov.of === 1 ? one : many}`
}

const EXPLAINER = {
  innings: {
    title: 'Why this strike rate may be incomplete',
    body: [
      'A strike rate is runs divided by balls faced, and both halves have to come from the same innings for the answer to mean anything.',
      'Plenty of cricket is still scored in a written book, and older records rarely recorded balls faced at all. So a season can hold every run a batter made and a ball count for only some of those innings.',
      'Rather than dividing all the runs by some of the balls, which gives a figure far too high, this is worked out from the innings that recorded both. Runs, average and every other figure on the page still count every innings.',
    ],
  },
  spells: {
    title: 'Why this economy may be incomplete',
    body: [
      'An economy is runs conceded divided by overs bowled, and both halves have to come from the same spell.',
      'Overs are almost always written down, so this is usually complete. Where a spell reached us without one, it is left out of the rate rather than having its runs counted against somebody else’s overs.',
      'Wickets, runs conceded and every other figure still count every spell.',
    ],
  },
}

/** The (i) that opens the explainer. */
export function RateInfo({ unit = 'innings', className = '' }) {
  const [open, setOpen] = useState(false)
  const copy = EXPLAINER[unit === 'innings' ? 'innings' : 'spells']
  // Escape closes it, the way any popover should. The backdrop below catches a
  // click anywhere else; without a keyboard route out, a reader on a keyboard
  // has to tab back to the button that opened it.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  return (
    <span className={`relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-label={copy.title}
        aria-expanded={open}
        className="inline-flex h-[15px] w-[15px] items-center justify-center rounded-full pb-hairline-b border border-pb-hairline text-[9px] font-mono leading-none text-pb-dim hover:text-pb-text hover:border-pb-dim align-middle"
      >
        i
      </button>
      {open && (
        <>
          {/* Click anywhere to close, the way the rest of the app's popovers do. */}
          <span className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <span className="absolute left-0 top-6 z-50 block w-[min(320px,80vw)] pb-card p-3 text-left shadow-lg">
            <span className="block font-mono text-[10px] tracking-wide3 uppercase text-pb-dim mb-1.5">
              {copy.title}
            </span>
            {copy.body.map((para, i) => (
              <span key={i} className="block text-[12px] leading-relaxed text-pb-dim mb-1.5 last:mb-0">
                {para}
              </span>
            ))}
          </span>
        </>
      )}
    </span>
  )
}

/** The line under a figure, or under a table. Draws nothing when complete. */
export function RateNote({ coverage, unit = 'innings', className = '' }) {
  if (!isPartial(coverage)) return null
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-[10px] text-pb-dim ${className}`}>
      <span>Data may be incomplete &middot; {coverageText(coverage, unit)}</span>
      <RateInfo unit={unit} />
    </span>
  )
}

/**
 * The marker beside one figure in a table.
 *
 * A dagger rather than an asterisk: an asterisk already means "not out" on
 * every cricket scorecard in the world, and a batting table is the last place
 * to reuse it.
 */
export function RateMark({ coverage, unit = 'innings' }) {
  if (!isPartial(coverage)) return null
  return (
    <span
      className="text-pb-faint cursor-help"
      title={`Data may be incomplete — ${coverageText(coverage, unit)}`}
      aria-label={`Data may be incomplete, ${coverageText(coverage, unit)}`}
    >
      &nbsp;&dagger;
    </span>
  )
}

/** One footnote under a table where any row is marked. */
export function RateFootnote({ rows, field = 'strike_rate_coverage', unit = 'innings', when = true, className = '' }) {
  // `when` is what stops a note appearing over a table that is not showing the
  // marked figure at all. A leaderboard sorted by runs carries the coverage on
  // every row and draws no strike rate, and a footnote about a mark nobody can
  // see is worse than no footnote.
  const any = when && (rows || []).some(r => isPartial(r?.[field]))
  if (!any) return null
  return (
    <p className={`px-5 py-2.5 font-mono text-[10px] text-pb-dim flex items-center gap-1.5 ${className}`}>
      <span>&dagger; Data may be incomplete for these rows &mdash; not every innings recorded a ball count.</span>
      <RateInfo unit={unit} />
    </p>
  )
}
