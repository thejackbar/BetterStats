// One game: who's on the ballot, the week's count, paper-vote entry, the
// ballots cast, and lock/reopen. Adds a ballot-progress header, the
// outstanding-voter chase panel, and per-fixture sharing over the original.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../../../contexts/ToastContext'
import { api } from '../../../../lib/api'
import { PbSpinner } from '../../../../lib/presskit'
import { Btn, Icon } from '../ui'
import BallotProgress from './BallotProgress'
import VoteStateBadge from './VoteStateBadge'
import ShareVotePanel from './ShareVotePanel'
import OutstandingVoters from './OutstandingVoters'
import { fmtDate } from './votesTokens'

const SOURCES = [
  { value: 'scorecard', label: 'Match scorecard' },
  { value: 'lineup', label: 'BetterSelect XI' },
  { value: 'playhq', label: 'Play.Cricket team list' },
]
const sourceLabel = (v) => SOURCES.find((s) => s.value === v)?.label || v

function BallotEntryForm({ detail, medalId, onSaved }) {
  const toast = useToast()
  const eligible = detail.eligible || []
  const values = detail.settings?.ballot_values || [3, 2, 1]
  const captainOnly = detail.settings?.voter_mode === 'captain'
  const captains = eligible.filter((p) => p.is_captain)
  const [showAllVoters, setShowAllVoters] = useState(!captainOnly)
  const voterOptions = (captainOnly && !showAllVoters && captains.length > 0) ? captains : eligible
  const [voterId, setVoterId] = useState('')
  const [voterName, setVoterName] = useState('')
  const [picks, setPicks] = useState(values.map(() => ''))
  const [saving, setSaving] = useState(false)

  useEffect(() => { setPicks(values.map(() => '')) }, [detail.fixture?.id, values.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    const chosen = picks.filter(Boolean)
    if (!chosen.length) { toast.error('Pick at least one player'); return }
    setSaving(true)
    try {
      await api.votesAdminBallot(detail.fixture.id, medalId, {
        voter_player_id: voterId === '__other__' ? null : voterId || null,
        voter_name: voterId === '__other__' ? voterName : null,
        picks: chosen,
      })
      toast.success('Ballot saved')
      setVoterId(''); setVoterName(''); setPicks(values.map(() => ''))
      onSaved()
    } catch (e) { toast.error(e.message) }
    finally { setSaving(false) }
  }

  const voterOk = voterId && (voterId !== '__other__' || voterName.trim().length >= 2)
  return (
    <div className="pb-card px-4 py-4">
      <div className="font-display font-bold text-[15px] mb-1">Enter a ballot</div>
      <p className="text-xs text-pb-faint mb-3">
        Paper votes, or the captain texting theirs in. Entering again for the same voter replaces their ballot.
        {captainOnly && " This club only counts the captain's votes."}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Voter</label>
          <select value={voterId} onChange={(e) => setVoterId(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm min-w-[180px] focus:outline-none focus:border-pb-accent">
            <option value="">— who's voting? —</option>
            {voterOptions.map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_captain ? ' (c)' : ''}</option>)}
            <option value="__other__">Someone else (coach, supporter…)</option>
          </select>
          {captainOnly && captains.length > 0 && (
            <button type="button" onClick={() => setShowAllVoters((v) => !v)}
              className="block mt-1 font-mono text-[10px] text-pb-faint hover:text-pb-text underline">
              {showAllVoters ? 'Only show the captain' : 'Show all players'}
            </button>
          )}
        </div>
        {voterId === '__other__' && (
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Their name</label>
            <input value={voterName} onChange={(e) => setVoterName(e.target.value)} placeholder="e.g. Coach Dave"
              className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pb-accent" />
          </div>
        )}
        {values.map((v, i) => (
          <div key={i}>
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">{v} vote{v === 1 ? '' : 's'}</label>
            <select value={picks[i] || ''} onChange={(e) => setPicks((ps) => ps.map((p, j) => (j === i ? e.target.value : p)))}
              className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm min-w-[160px] focus:outline-none focus:border-pb-accent">
              <option value="">—</option>
              {eligible.filter((p) => p.id === picks[i] || !picks.includes(p.id))
                .map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        ))}
        <Btn variant="primary" sm onClick={submit} disabled={!voterOk || saving}>{saving ? 'Saving…' : 'Save ballot'}</Btn>
      </div>
    </div>
  )
}

function EligibilityPanel({ detail, medalId, onChanged }) {
  const toast = useToast()
  const e = detail.eligibility
  const [busy, setBusy] = useState(false)
  if (!e) return null

  const setSource = async (value) => {
    setBusy(true)
    try {
      await api.votesSetFixtureSource(detail.fixture.id, value, medalId)
      toast.success(value ? `Voting on the ${sourceLabel(value).toLowerCase()}` : 'Back to the club default')
      onChanged()
    } catch (err) { toast.error(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="pb-card px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <div className="font-display font-bold text-[15px]">Who can be voted for</div>
        <div className="text-xs text-pb-faint">
          {e.used ? <>Using the <b className="text-pb-text">{sourceLabel(e.used)}</b></> : 'No team list yet'}
        </div>
      </div>
      {e.fell_back && (
        <div className="text-[12.5px] mb-2" style={{ color: 'var(--pb-amber)' }}>
          The {sourceLabel(e.requested).toLowerCase()} is empty for this game, so the {sourceLabel(e.used).toLowerCase()} is being used instead.
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 mt-2">
        {SOURCES.map((s) => {
          const n = e.counts?.[s.value]
          const active = (e.override || e.requested) === s.value
          return (
            <button key={s.value} onClick={() => setSource(s.value)} disabled={busy || active}
              className={`px-3 py-1.5 rounded-lg text-[12.5px] border transition-colors ${active
                ? 'border-pb-accent text-pb-accent bg-pb-accent/10'
                : 'pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-50'}`}>
              {s.label}
              <span className="font-mono text-[10px] text-pb-faint ml-1.5">{n == null ? '—' : n}</span>
            </button>
          )
        })}
      </div>
      {e.unmatched?.length > 0 && (
        <div className="mt-2.5 text-xs rounded-lg px-3 py-2"
          style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
          Not on the ballot (no player record at your club): {e.unmatched.join(', ')}.
          Claim them from the match scorecard to make them votable.
        </div>
      )}
    </div>
  )
}

export default function FixtureDetail({ fixtureId, medalId, onBack }) {
  const toast = useToast()
  const [detail, setDetail] = useState(null)

  const load = useCallback(() => {
    api.votesFixtureDetail(fixtureId, medalId).then(setDetail).catch((e) => toast.error(e.message))
  }, [fixtureId, medalId, toast])
  useEffect(() => { load() }, [load])

  if (!detail) return <PbSpinner message="Loading ballots…" />
  const fx = detail.fixture
  const values = detail.settings?.ballot_values || [3, 2, 1]

  const setLock = async (lock) => {
    try {
      await (lock ? api.votesLockFixture(fx.id, medalId) : api.votesReopenFixture(fx.id, medalId))
      toast.success(lock ? 'Voting locked' : 'Voting reopened')
      load()
    } catch (e) { toast.error(e.message) }
  }

  const removeBallot = async (b) => {
    if (!window.confirm(`Delete ${b.voter || 'this voter'}'s ballot?`)) return
    try { await api.votesDeleteBallot(b.id); toast.success('Ballot deleted'); load() }
    catch (e) { toast.error(e.message) }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Btn sm variant="ghost" icon="back" onClick={onBack}>All games</Btn>
        <div className="font-display font-bold text-lg">{fx.round} · vs {fx.opponent || 'TBC'}</div>
        <span className="text-pb-faint text-sm">{fmtDate(fx.date, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
        <VoteStateBadge state={fx.state} />
        <BallotProgress count={detail.ballots.length} expected={fx.voters_expected} className="w-[180px]" />
        <div className="ml-auto flex gap-2">
          {fx.state === 'open'
            ? <Btn sm variant="ghost" onClick={() => setLock(true)}>Lock voting</Btn>
            : (fx.state === 'locked' || fx.state === 'closed') &&
              <Btn sm variant="ghost" onClick={() => setLock(false)}>Reopen voting</Btn>}
        </div>
      </div>

      {fx.state === 'awaiting_team' && (
        <div className="rounded-lg px-4 py-3 text-sm bg-pb-amber/10 border border-pb-amber/30 text-pb-amber">
          No team list for this game yet, so there's nobody to vote for.
          Save an XI on the <Link to="/admin/betterselect/selection" className="underline">Selection</Link> page,
          publish the side on Play.Cricket, or run <Link to="/admin/sync" className="underline">Sync Now</Link> once
          the weekend's results are in.
        </div>
      )}

      {(fx.state === 'closed' || fx.state === 'locked') && (
        <div className="rounded-lg px-4 py-3 text-sm bg-pb-surface2 border pb-hairline text-pb-dim">
          Voting {fx.state === 'locked' ? 'is locked' : 'has closed'} for this game, but you can still enter
          ballots below without reopening it — handy for catching up at the end of a season.
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <EligibilityPanel detail={detail} medalId={medalId} onChanged={load} />

          <div className="pb-card px-4 py-4">
            <div className="font-display font-bold text-[15px] mb-2.5">This week's count</div>
            {detail.results.length === 0 ? (
              <div className="text-pb-faint text-sm">No votes yet.</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">
                    <th className="py-1.5 pr-3">Player</th>
                    <th className="py-1.5 pr-3 text-right">Season points</th>
                    <th className="py-1.5 pr-3 text-right">Raw votes</th>
                    {values.map((v) => <th key={v} className="py-1.5 pr-3 text-right">{v}s</th>)}
                  </tr>
                </thead>
                <tbody>
                  {detail.results.map((r) => (
                    <tr key={r.player_id} className="border-t pb-hairline">
                      <td className="py-2 pr-3 font-medium">{r.name}</td>
                      <td className="py-2 pr-3 text-right font-mono font-bold" style={{ color: r.points > 0 ? 'var(--pb-accent)' : undefined }}>{r.points || '—'}</td>
                      <td className="py-2 pr-3 text-right font-mono">{r.raw}</td>
                      {r.counts.map((n, i) => <td key={i} className="py-2 pr-3 text-right font-mono text-pb-faint">{n || '·'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {detail.eligible.length > 0 && <BallotEntryForm detail={detail} medalId={medalId} onSaved={load} />}

          <div className="pb-card px-4 py-4">
            <div className="font-display font-bold text-[15px] mb-2.5">
              Ballots <span className="font-mono text-[11px] text-pb-faint">({detail.ballots.length})</span>
            </div>
            {detail.ballots.length === 0 ? (
              <div className="text-pb-faint text-sm">Nobody has voted yet.</div>
            ) : (
              <div className="divide-y divide-pb-hairline">
                {detail.ballots.map((b) => (
                  <div key={b.id} className="py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium text-sm min-w-[140px]">{b.voter || 'Unknown'}</span>
                    {b.voter_kind === 'non_player' && (
                      <span className="font-mono text-[9px] px-1.5 py-0.5 rounded-full bg-pb-amber/15 text-pb-amber">NON-PLAYER</span>
                    )}
                    {b.source === 'admin' && (
                      <span className="font-mono text-[9px] px-1.5 py-0.5 rounded-full bg-pb-surface2 text-pb-faintest">ADMIN-ENTERED</span>
                    )}
                    <span className="text-[13px] text-pb-dim flex-1">
                      {b.picks.map((p, i) => (
                        <span key={p.position}>{i > 0 && ' · '}<b className="font-mono">{values[p.position - 1] ?? '?'}</b> {p.name}</span>
                      ))}
                    </span>
                    <button onClick={() => removeBallot(b)} className="text-pb-faintest hover:text-pb-red" title="Delete ballot">
                      <Icon name="trash" size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="w-full lg:w-[320px] shrink-0 flex flex-col gap-4">
          <ShareVotePanel settings={detail.settings} fixtures={[fx]}
            scope={{ fixtureId: fx.id, label: `${fx.round} v ${fx.opponent || 'TBC'}` }} />
          <OutstandingVoters fixture={{ ...fx, outstanding: detail.outstanding }} medalId={medalId} onNudged={load} />
        </div>
      </div>
    </div>
  )
}
