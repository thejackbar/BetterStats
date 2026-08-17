import { ProgressBar } from '../ProgressBar'

// One sync_runs row rendered as a card — extracted from AdminSync.jsx's Sync
// History list so the club admin home page can show the exact same detail
// for the club's current/most recent sync without duplicating this block.

export function fmtDuration(startedAt, completedAt) {
  if (!startedAt || !completedAt) return null
  const ms = new Date(completedAt) - new Date(startedAt)
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

/* Phase + counters reported by the backend mid-run (sync.py merges
   progress_* keys into the run's stats every few seconds of work). */
export function syncProgressLabel(s) {
  const phase = s.progress_phase || 'Starting'
  if (s.progress_done != null && s.progress_total != null) {
    return `${phase} · ${Number(s.progress_done).toLocaleString()} / ${Number(s.progress_total).toLocaleString()}`
  }
  return phase
}

// A sync_runs.kind is a stored value, not copy — give it a readable label
// here rather than showing an admin the raw key.
const KIND_LABEL = {
  org_full: 'sync now',
  org_recent: 'results sync',
  org_hard_refresh: 'full rebuild',
  player_deep: 'player deep sync',
}

export function StatPill({ label, value, highlight }) {
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] px-2 py-0.5 rounded border ${
      highlight
        ? 'border-pb-accent/30 text-pb-accent bg-pb-accent/10'
        : 'border-pb-hairline text-pb-faint bg-pb-surface2'
    }`}>
      <span className="font-bold">{value}</span>
      <span>{label}</span>
    </span>
  )
}

export default function SyncRunCard({ entry, isLatest = false }) {
  const s = entry.stats || {}
  const dur = fmtDuration(entry.started_at, entry.completed_at)
  const isRunning = entry.status === 'running'
  const isError = entry.status === 'error' || !!entry.error
  // Pause Sync / Cancel Sync (migration 160) — a paused run isn't finished
  // (no completed_at, resumable via Continue Sync) and a cancelled one is a
  // deliberate stop, not a failure — neither should read as ERROR or a plain
  // OK success.
  const isPaused = entry.status === 'paused'
  const isCancelled = entry.status === 'cancelled'

  return (
    <div
      className={`pb-card p-4 ${
        isError ? 'border-pb-red/40'
          : isRunning || isPaused ? 'border-pb-amber/40'
          : isCancelled ? 'border-pb-hairline'
          : isLatest ? 'border-pb-accent/30'
          : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-pb-text text-sm font-medium">{fmtTime(entry.started_at)}</p>
            {entry.kind && (
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">
                {KIND_LABEL[entry.kind] || entry.kind}
              </span>
            )}
          </div>
          {dur && !isRunning && !isPaused && <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Completed in {dur}</p>}
          {isRunning && <p className="font-mono text-[10px] text-pb-amber mt-0.5">Running…</p>}
          {isPaused && <p className="font-mono text-[10px] text-pb-amber mt-0.5">Paused, use Continue Sync on All Clubs to resume</p>}
        </div>
        <span className={`font-mono text-[10px] px-2 py-0.5 rounded border shrink-0 ${
          isError
            ? 'border-pb-red/30 text-pb-red'
            : isRunning || isPaused
            ? 'border-pb-amber/30 text-pb-amber'
            : isCancelled
            ? 'border-pb-hairline text-pb-faint'
            : 'border-pb-accent/30 text-pb-accent'
        }`}>
          {isError ? 'ERROR' : isRunning ? 'RUNNING' : isPaused ? 'PAUSED' : isCancelled ? 'CANCELLED' : 'OK'}
        </span>
      </div>

      {isRunning && (
        <ProgressBar
          pct={s.progress_pct ?? 0}
          label={syncProgressLabel(s)}
          labelClassName="font-mono text-[10px] text-pb-faint"
          className="mb-3"
        />
      )}

      {/* The run finished and its season totals landed, but the scorecard
          pass blew up, so it pulled no match results. Shown on its own
          because an OK badge over a row of zeroed pills reads as "nothing
          happened this week" rather than "this did not work". The next run
          re-covers the period by itself — see services/auto_sync.py. */}
      {!isError && s.match_pull_failed && (
        <p className="font-mono text-[10px] text-pb-amber mb-1.5">
          Match results could not be pulled this run. The next sync will cover this period again.
        </p>
      )}

      {isError ? (
        <p className="font-mono text-[10px] text-pb-red">{entry.error}</p>
      ) : s.no_fixtures_in_window ? (
        /* The scheduled run checked the club's card, found nothing played
           since last time, and pulled nothing. Worth showing as its own line
           rather than an empty row of zeroed pills. */
        <p className="font-mono text-[10px] text-pb-faint">
          No fixtures played since {s.incremental_since || 'the last sync'}, nothing to pull
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {s.seasons != null && <StatPill label="seasons" value={s.seasons} />}
          {s.player_seasons != null && <StatPill label="player seasons" value={s.player_seasons} />}
          {s.season_stats != null && <StatPill label="stat rows" value={s.season_stats} />}
          {s.playhq_games_found != null && <StatPill label="phq games" value={s.playhq_games_found} highlight={s.playhq_games_found > 0} />}
          {s.playhq_games_final != null && <StatPill label="phq final" value={s.playhq_games_final} highlight={s.playhq_games_final > 0} />}
          {s.games_new != null && <StatPill label="new games" value={s.games_new} highlight={s.games_new > 0} />}
          {s.games_topped_up != null && <StatPill label="topped up" value={s.games_topped_up} highlight={s.games_topped_up > 0} />}
          {s.batting != null && <StatPill label="batting rows" value={s.batting} highlight={s.batting > 0} />}
          {s.bowling != null && <StatPill label="bowling rows" value={s.bowling} highlight={s.bowling > 0} />}
          {s.partnerships != null && <StatPill label="partnerships" value={s.partnerships} highlight={s.partnerships > 0} />}
          {s.games_skipped_done != null && <StatPill label="already done" value={s.games_skipped_done} />}
          {s.games_skipped_season != null && <StatPill label="no season match" value={s.games_skipped_season} highlight={s.games_skipped_season > 0} />}
          {s.games_skipped_no_stats != null && <StatPill label="no stats" value={s.games_skipped_no_stats} highlight={s.games_skipped_no_stats > 0} />}
          {s.gr_matches_seen != null && <StatPill label="GR matches" value={s.gr_matches_seen} highlight={s.gr_matches_seen > 0} />}
          {s.gr_games_new != null && <StatPill label="GR new games" value={s.gr_games_new} highlight={s.gr_games_new > 0} />}
          {s.gr_batting != null && <StatPill label="GR batting" value={s.gr_batting} highlight={s.gr_batting > 0} />}
          {s.gr_bowling != null && <StatPill label="GR bowling" value={s.gr_bowling} highlight={s.gr_bowling > 0} />}
          {s.gr_fielding != null && <StatPill label="GR fielding" value={s.gr_fielding} highlight={s.gr_fielding > 0} />}
          {s.gr_partnerships != null && <StatPill label="GR partnerships" value={s.gr_partnerships} highlight={s.gr_partnerships > 0} />}
        </div>
      )}
    </div>
  )
}
