import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'

const TABS = [
  { key: 'pending', label: 'To review' },
  { key: 'approved', label: 'Approved' },
  { key: 'ignored', label: 'Ignored' },
]

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function RoundBadge({ candidate }) {
  // A "Grand Final" needs no second-guessing. A bare "Final" is usually a
  // one-day or T20 decider, but some associations label a semi that way, so
  // it says so rather than looking equally certain.
  const review = candidate.confidence === 'review'
  return (
    <span
      className={`inline-block font-mono text-[9px] tracking-wide3 px-1.5 py-0.5 rounded border ${
        review
          ? 'text-amber-400 bg-amber-400/10 border-amber-400/20'
          : 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
      }`}
    >
      {(candidate.round_name || candidate.round_label || '').toUpperCase()}
    </span>
  )
}

function PlayerChips({ players, excluded, onToggle, editable }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {players.map((p) => {
        const off = excluded.has(p.player_id)
        return (
          <button
            key={p.player_id}
            type="button"
            disabled={!editable}
            onClick={() => onToggle(p.player_id)}
            title={editable ? (off ? 'Include in this premiership' : 'Leave this player out') : undefined}
            className={`text-xs px-2 py-1 rounded border transition ${
              off
                ? 'line-through text-pb-faint bg-pb-surface2 border-pb-hairline opacity-60'
                : 'text-pb-text bg-pb-surface2 border-pb-hairline'
            } ${editable ? 'hover:border-pb-accent cursor-pointer' : 'cursor-default'}`}
          >
            {p.name}
            {p.is_captain && (
              <span className="ml-1 font-mono text-[9px] text-pb-accent-ink">(C)</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

function Candidate({ candidate, onApprove, onIgnore, onReset, busy }) {
  const [excluded, setExcluded] = useState(() => new Set())
  const pending = candidate.status === 'pending'

  const toggle = (id) =>
    setExcluded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const included = candidate.players.filter((p) => !excluded.has(p.player_id))

  return (
    <div className="pb-card p-4 mb-3">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <RoundBadge candidate={candidate} />
            <span className="font-display font-bold text-pb-text">
              {candidate.grade_name}
            </span>
          </div>
          <div className="text-sm text-pb-faint">
            {candidate.season_name}
            {candidate.opponent ? ` · beat ${candidate.opponent}` : ''}
            {candidate.played_at ? ` · ${fmtDate(candidate.played_at)}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {pending ? (
            <>
              <button
                type="button"
                disabled={busy || included.length === 0}
                onClick={() => onApprove(candidate, included.map((p) => p.player_id))}
                className="text-xs px-3 py-1.5 rounded bg-pb-accent text-pb-on-accent font-medium disabled:opacity-50"
              >
                Add to honour board ({included.length})
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onIgnore(candidate)}
                className="text-xs px-3 py-1.5 rounded border border-pb-hairline text-pb-faint disabled:opacity-50"
              >
                Ignore
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => onReset(candidate)}
              className="text-xs px-3 py-1.5 rounded border border-pb-hairline text-pb-faint disabled:opacity-50"
            >
              {candidate.status === 'approved' ? 'Undo' : 'Move back to review'}
            </button>
          )}
        </div>
      </div>

      {candidate.confidence === 'review' && pending && (
        <p className="text-xs text-amber-400/90 mb-3">
          The competition called this round “{candidate.round_name}”, not a grand final.
          That is usually the decider of a one-day or T20 competition, but some
          associations label a semi that way. Worth a look before you approve it.
        </p>
      )}
      {candidate.outcome_basis === 'weak' && pending && (
        <p className="text-xs text-amber-400/90 mb-3">
          This result predates the per-side club tagging, so the win is read from
          the stored result rather than confirmed from both sides. Check the
          scoreline before approving.
        </p>
      )}

      <div className="text-[10px] font-mono tracking-wide3 text-pb-faint mb-1.5">
        {candidate.status === 'approved'
          ? `${candidate.awards_created} PLAYERS ON THE HONOUR BOARD`
          : `${included.length} OF ${candidate.players.length} PLAYERS`}
      </div>
      <PlayerChips
        players={candidate.players}
        excluded={excluded}
        onToggle={toggle}
        editable={pending && !busy}
      />
      {pending && (
        <p className="text-xs text-pb-faint mt-2">
          Click a name to leave them out. The twelfth man and anyone else off the
          field won’t be here — add them from{' '}
          <Link to="/admin/awards" className="text-pb-accent-ink underline">Awards</Link>.
        </p>
      )}
    </div>
  )
}

export default function AdminPremierships() {
  const [tab, setTab] = useState('pending')
  const [data, setData] = useState({ candidates: [], counts: {} })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const load = useCallback(async (status) => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.listDetectedPremierships(status))
    } catch (e) {
      setError(e?.message || 'Could not load premierships.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(tab) }, [tab, load])

  const act = async (fn, msg) => {
    setBusy(true)
    setNotice(null)
    try {
      const res = await fn()
      setNotice(typeof msg === 'function' ? msg(res) : msg)
      await load(tab)
    } catch (e) {
      setError(e?.message || 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  const counts = data.counts || {}

  return (
    <BetterStatsLayout>
      <div className="max-w-5xl">
        <div className="mb-6">
          <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Premierships</h1>
          <p className="text-pb-faint text-sm">
            Finals your club won, picked up from your results. Nothing reaches the
            honour board until you approve it.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 mb-5">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`text-xs px-3 py-1.5 rounded border transition ${
                tab === t.key
                  ? 'border-pb-accent text-pb-accent-ink bg-pb-surface2'
                  : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}
            >
              {t.label}
              {counts[t.key] ? (
                <span className="ml-1.5 font-mono text-[10px]">{counts[t.key]}</span>
              ) : null}
            </button>
          ))}
        </div>

        {notice && (
          <div className="pb-card p-3 mb-4 text-sm text-pb-text border-l-2 border-pb-accent">
            {notice}
          </div>
        )}
        {error && (
          <div className="pb-card p-3 mb-4 text-sm text-red-400">{error}</div>
        )}

        {loading ? (
          <p className="text-pb-faint text-sm">Loading…</p>
        ) : data.candidates.length === 0 ? (
          <div className="pb-card p-6 text-center">
            <p className="text-pb-text mb-1">
              {tab === 'pending' ? 'Nothing waiting on you.' : `No ${tab} premierships.`}
            </p>
            <p className="text-pb-faint text-sm">
              {tab === 'pending'
                ? 'A won grand final shows up here after your next sync.'
                : 'Approved and ignored premierships are kept here.'}
            </p>
          </div>
        ) : (
          data.candidates.map((c) => (
            <Candidate
              key={c.game_id}
              candidate={c}
              busy={busy}
              onApprove={(cand, ids) =>
                act(
                  () => api.approvePremiership(cand.game_id, ids),
                  (res) =>
                    `${cand.grade_name} ${cand.season_name}: ${res.awards_created} players added to the honour board.` +
                    (res.already_held ? ` ${res.already_held} already had it.` : ''),
                )
              }
              onIgnore={(cand) =>
                act(() => api.ignorePremiership(cand.game_id), `${cand.grade_name} ignored.`)
              }
              onReset={(cand) =>
                act(
                  () => api.resetPremiership(cand.game_id),
                  (res) =>
                    res.awards_removed
                      ? `Removed ${res.awards_removed} awards and moved it back to review.`
                      : 'Moved back to review.',
                )
              }
            />
          ))
        )}

        <p className="text-xs text-pb-faint mt-6">
          A final decided on a washout or higher position won’t appear, because the
          scorecard records no winner. Add those from{' '}
          <Link to="/admin/awards" className="text-pb-accent-ink underline">Awards</Link>.
        </p>
      </div>
    </BetterStatsLayout>
  )
}
