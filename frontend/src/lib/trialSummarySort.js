// How the Trial Summary (Better HQ > Reporting) orders its rows. Pure functions, so the screen and
// its checks read the same code.
//
// THE RULE: a trial sort follows the date the "Trial ends" column SHOWS, never a date the column
// does not show. That column reads
//   * a running trial (on trial, or paying with a running add-on trial): `trial_ends_at`;
//   * an ended trial: `trial_ended_at` (the latest module trial to lapse);
//   * anything else (no trial, open-ended, paused): a dash.
// Before, only a running trial carried a sort key and every other row tied, so ended trials sat in
// the order the server sent them (newest sign-up), not in order of when their trial ended.

const ms = (iso) => {
  const t = iso ? Date.parse(iso) : NaN
  return Number.isNaN(t) ? null : t
}

/** The date the Trial ends column shows for a club, and whether that trial is still running.
 *  `ms` is null when the column shows no date (dash, or "No end date set"). */
export function trialEndOf(c) {
  if (c.status === 'on_trial' || (c.status === 'paying' && c.trial_ends_at)) return { ms: ms(c.trial_ends_at), running: true }
  if (c.status === 'trial_ended' && c.trial_ended_at) return { ms: ms(c.trial_ended_at), running: false }
  return { ms: null, running: false }
}

const newestSignup = (a, b) => (b.signed_up_at || '').localeCompare(a.signed_up_at || '')

// 0 running trials, 1 ended trials, 2 no date to sort on (always last, whichever way round).
const group = (t) => (t.ms == null ? 2 : t.running ? 0 : 1)

export const SORTS = {
  signed_up: { label: 'Newest sign-up', fn: newestSignup },
  trial_end: {
    // Nearest to today first: running trials by the date they end (soonest first), then ended trials
    // by when they ended (most recently ended first), then clubs with no trial date.
    label: 'Trial ends soonest',
    fn: (a, b) => {
      const x = trialEndOf(a), y = trialEndOf(b)
      const gx = group(x), gy = group(y)
      if (gx !== gy) return gx - gy
      if (gx === 0 && x.ms !== y.ms) return x.ms - y.ms
      if (gx === 1 && x.ms !== y.ms) return y.ms - x.ms
      return newestSignup(a, b)
    },
  },
  trial_end_latest: {
    // The Trial ends column, latest date first, running and ended trials in one run.
    label: 'Trial end date, latest first',
    fn: (a, b) => {
      const x = trialEndOf(a), y = trialEndOf(b)
      if ((x.ms == null) !== (y.ms == null)) return x.ms == null ? 1 : -1
      if (x.ms != null && x.ms !== y.ms) return y.ms - x.ms
      return newestSignup(a, b)
    },
  },
  activity: {
    // Fewest active days first; clubs level on days, the fewer page views first.
    label: 'Least active first',
    fn: (a, b) => ((a.activity?.active_days || 0) - (b.activity?.active_days || 0))
      || ((a.activity?.views || 0) - (b.activity?.views || 0))
      || newestSignup(a, b),
  },
}
