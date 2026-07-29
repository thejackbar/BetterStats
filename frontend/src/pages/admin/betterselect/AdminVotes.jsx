// BetterSelect → Votes — Brownlow-style best-player vote collection.
//
// Three tabs:
//   Fixtures    — every played game with its voting state; managers open one to
//                 see ballots, enter paper votes, moderate spoof voters and
//                 lock/reopen the round.
//   Leaderboard — the season count, club-wide or per grade, replayable "as at"
//                 any round (for clubs that read the count night-of like the
//                 Brownlow). Visible to MANAGE_VOTES or VIEW_VOTE_RESULTS.
//   Settings    — who votes, the ballot shape, how votes convert to season
//                 points, tie policy, self-vote + non-participant toggles, and
//                 the public voting link (same magic-link + PIN pattern as
//                 self-service availability).
import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import QRCode from 'qrcode'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Btn, Icon, Segmented } from './ui'

const STATE_META = {
  open: { label: 'OPEN', color: 'var(--pb-positive)' },
  closed: { label: 'CLOSED', color: 'var(--pb-faintest)' },
  locked: { label: 'LOCKED', color: 'var(--pb-red)' },
  awaiting_team: { label: 'NEEDS TEAM LIST', color: 'var(--pb-amber)' },
  upcoming: { label: 'UPCOMING', color: 'var(--pb-faintest)' },
}

// Where the votable list comes from. Mirrors ELIGIBILITY_SOURCES in
// backend/app/services/votes.py.
const SOURCES = [
  { value: 'scorecard', label: 'Match scorecard', hint: 'Who actually played. The most accurate, but only once the weekly sync lands.' },
  { value: 'lineup', label: 'BetterSelect XI', hint: 'The side you picked in Selection. Ready as soon as you save it.' },
  { value: 'playhq', label: 'Play.Cricket team list', hint: 'The side your club published on Play.Cricket. Ready on match day.' },
]
const sourceLabel = (v) => SOURCES.find((s) => s.value === v)?.label || v

function StateBadge({ state }) {
  const m = STATE_META[state] || STATE_META.upcoming
  return (
    <span className="font-mono text-[10px] px-2 py-0.5 rounded-full shrink-0"
      style={{ background: `color-mix(in srgb, ${m.color} 14%, transparent)`, color: m.color }}>
      {m.label}
    </span>
  )
}

function fmtDate(d) {
  if (!d) return ''
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  } catch { return d }
}

const seasonLabel = (y) => `${y}/${String((y + 1) % 100).padStart(2, '0')}`
const ballotLabel = (values) => (values || []).join('-')

/* ── Settings tab ────────────────────────────────────────────────────────── */

function SettingsTab({ canManage }) {
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState(null)
  const [ballotDraft, setBallotDraft] = useState(null) // local editor state

  const load = useCallback(() => {
    api.votesGetSettings().then(setCfg).catch((e) => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  const fullUrl = cfg?.token && cfg?.enabled ? `${window.location.origin}/vote/${cfg.token}` : ''
  useEffect(() => {
    if (!fullUrl) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(fullUrl, { margin: 1, width: 240, errorCorrectionLevel: 'M' })
      .then((u) => { if (alive) setQr(u) })
      .catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [fullUrl])

  const update = async (patch) => {
    if (!canManage) return
    setBusy(true)
    try {
      setCfg(await api.votesSetSettings(patch))
      setBallotDraft(null)
    } catch (e) { toast.error(e.message || 'Update failed') }
    finally { setBusy(false) }
  }

  const regenerate = async () => {
    if (!window.confirm('Generate a new voting link? The old link and QR code stop working immediately.')) return
    setBusy(true)
    try {
      setCfg(await api.votesRegenerateLink())
      toast.success('New link generated. Reshare it with your players.')
    } catch (e) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  const copy = async (text, what) => {
    try { await navigator.clipboard.writeText(text); toast.success(`${what} copied`) }
    catch { toast.error('Copy failed. Select and copy manually.') }
  }

  if (!cfg) return <PbSpinner message="Loading settings…" />

  const ballot = ballotDraft || (cfg.ballot_values || []).map(String)
  const setPos = (i, v) => {
    const next = [...ballot]
    next[i] = v.replace(/\D/g, '').slice(0, 3)
    setBallotDraft(next)
  }
  const saveBallot = () => {
    const values = ballot.map((v) => parseInt(v, 10)).filter((n) => n > 0)
    if (!values.length) { toast.error('The ballot needs at least one position'); return }
    update({ ballot_values: values })
  }

  const Row = ({ label, hint, children }) => (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-1.5 py-3.5 border-t pb-hairline first:border-0">
      <div className="w-56 shrink-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="text-[12px] text-pb-faint mt-0.5">{hint}</div>}
      </div>
      <div className="flex-1 min-w-[240px]">{children}</div>
    </div>
  )

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      {/* Public link */}
      <div className="pb-card px-4 py-4">
        <div className="font-display font-bold text-[15px] mb-1 flex items-center gap-2">
          Voting link
          <span className="font-mono text-[10px] px-2 py-0.5 rounded-full" style={cfg.enabled
            ? { background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }
            : { background: 'var(--pb-surface2)', color: 'var(--pb-faintest)' }}>
            {cfg.enabled ? 'ON' : 'OFF'}
          </span>
        </div>
        <p className="text-[12.5px] text-pb-faint mb-3">
          Players open the link, verify with the last 4 digits of their mobile, and cast their votes, without logging in.
        </p>
        <div className="flex items-center gap-2.5 mb-3">
          <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Status</span>
          <Segmented sm value={cfg.enabled ? 'on' : 'off'} onChange={(v) => update({ enabled: v === 'on' })}
            options={[{ value: 'on', label: 'Enabled' }, { value: 'off', label: 'Off' }]} />
          {cfg.enabled && (
            <>
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint ml-3">PIN</span>
              <Segmented sm value={cfg.require_pin ? 'pin' : 'nopin'} onChange={(v) => update({ require_pin: v === 'pin' })}
                options={[{ value: 'pin', label: 'Last-4 PIN' }, { value: 'nopin', label: 'No PIN' }]} />
            </>
          )}
        </div>
        {fullUrl && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <input readOnly value={fullUrl} onFocus={(e) => e.target.select()}
                className="flex-1 min-w-[220px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
              <Btn sm onClick={() => copy(fullUrl, 'Link')}>Copy link</Btn>
              <Btn sm onClick={() => copy(`🏏 Cast your votes: ${fullUrl}`, 'Message')}>Copy message</Btn>
              <Btn sm variant="ghost" onClick={regenerate} disabled={busy}>Regenerate</Btn>
            </div>
            {qr && (
              <div className="mt-3 text-center inline-block">
                <img src={qr} alt="Voting link QR code" className="w-36 h-36 rounded-lg bg-white p-2" />
                <div className="font-mono text-[10px] text-pb-faintest mt-1.5">Scan to open</div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Voting rules */}
      <div className="pb-card px-4 py-1">
        <Row label="Who votes" hint="Every player in the game, or just the captain.">
          <Segmented sm value={cfg.voter_mode} onChange={(v) => update({ voter_mode: v })}
            options={[{ value: 'players', label: 'All players' }, { value: 'captain', label: 'Captain only' }]} />
        </Row>
        <Row label="Non-playing voters" hint="Let the coach, president or supporters vote too. They enter their name on the voting page; you can delete any ballot you don't recognise.">
          <Segmented sm value={cfg.allow_non_participants ? 'yes' : 'no'} onChange={(v) => update({ allow_non_participants: v === 'yes' })}
            options={[{ value: 'no', label: 'Players only' }, { value: 'yes', label: 'Allowed' }]} />
        </Row>
        <Row label="Voting for yourself" hint="Whether a voter can include themselves in their picks.">
          <Segmented sm value={cfg.allow_self_vote ? 'yes' : 'no'} onChange={(v) => update({ allow_self_vote: v === 'yes' })}
            options={[{ value: 'no', label: 'Not allowed' }, { value: 'yes', label: 'Allowed' }]} />
        </Row>
        <Row label="Ballot" hint="Best player first. Default 3-2-1; make it 5-4-3-2-1, a single best-player vote, or anything else.">
          <div className="flex flex-wrap items-center gap-2">
            {ballot.map((v, i) => (
              <div key={i} className="flex items-center gap-1">
                <input value={v} onChange={(e) => setPos(i, e.target.value)} inputMode="numeric" disabled={!canManage}
                  className="w-14 text-center bg-pb-surface2 border pb-hairline rounded-lg px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-pb-accent" />
                {ballot.length > 1 && canManage && (
                  <button onClick={() => setBallotDraft(ballot.filter((_, j) => j !== i))}
                    className="text-pb-faintest hover:text-pb-red text-xs" title="Remove position">✕</button>
                )}
              </div>
            ))}
            {canManage && ballot.length < 10 && (
              <Btn sm variant="ghost" onClick={() => setBallotDraft([...ballot, '1'])}>+ Position</Btn>
            )}
            {canManage && ballotDraft && <Btn sm variant="primary" onClick={saveBallot} disabled={busy}>Save ballot</Btn>}
          </div>
          <div className="text-[11px] text-pb-faintest mt-1.5">Currently: {ballotLabel(cfg.ballot_values)} (highest value = best player). Values are sorted highest-first when saved.</div>
        </Row>
        <Row label="Season points" hint="How a week's votes convert to leaderboard points.">
          <Segmented sm value={cfg.counting_method} onChange={(v) => update({ counting_method: v })}
            options={[{ value: 'rank', label: `Weekly ${ballotLabel(cfg.ballot_values)}` }, { value: 'tally', label: 'Full tally' }]} />
          <div className="text-[11px] text-pb-faintest mt-1.5">
            {cfg.counting_method === 'rank'
              ? `The week's top vote-getter earns ${cfg.ballot_values[0]} points, next ${cfg.ballot_values[1] ?? 0}, and so on.`
              : 'Every vote counts at face value: 10 players all giving someone their 3 adds 30 to their season total.'}
          </div>
        </Row>
        {cfg.counting_method === 'rank' && (
          <Row label="Ties" hint="What happens when two players finish the week level.">
            <Segmented sm value={cfg.tie_policy} onChange={(v) => update({ tie_policy: v })}
              options={[{ value: 'share', label: 'Allow ties' }, { value: 'countback', label: 'Countback' }]} />
            <div className="text-[11px] text-pb-faintest mt-1.5">
              {cfg.tie_policy === 'share'
                ? 'Tied players share the position and both take the higher points.'
                : `Ties break on who received more ${cfg.ballot_values[0]}s, then ${cfg.ballot_values[1] ?? '—'}s, and so on. A dead heat after every countback still shares.`}
            </div>
          </Row>
        )}
        <Row label="Who can be voted for" hint="Which team list decides who's on the ballot. You can override this on any single game.">
          <select value={cfg.eligibility_source} onChange={(e) => update({ eligibility_source: e.target.value })} disabled={!canManage}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
            {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <div className="text-[11px] text-pb-faintest mt-1.5">
            {SOURCES.find((s) => s.value === cfg.eligibility_source)?.hint}
            {' '}If it's empty when voting opens, the next list that has players is used instead.
          </div>
        </Row>
        <Row label="Voting closes" hint="Days after the match before voting closes automatically. You can also lock or reopen any game yourself.">
          <select value={cfg.auto_close_days} onChange={(e) => update({ auto_close_days: parseInt(e.target.value, 10) })} disabled={!canManage}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
            {[2, 3, 4, 5, 6, 7, 10, 14, 21, 30].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </Row>
      </div>

      {/* Leaderboard access */}
      <div className="pb-card px-4 py-4">
        <div className="font-display font-bold text-[15px] mb-1">Who can see the leaderboard</div>
        <p className="text-[12.5px] text-pb-faint">
          The count stays inside the admin app. Nothing on the voting page or public site shows tallies.
          Club admins always see it; to give (or take away) access for other users, grant the{' '}
          <b className="text-pb-text">View vote results</b> capability on the{' '}
          <Link to="/admin/users" className="text-pb-accent underline">Users</Link> page.
          <b className="text-pb-text"> Manage votes</b> controls who runs the vote itself.
        </p>
      </div>
    </div>
  )
}

/* ── Fixture detail (ballots + entry + lock) ─────────────────────────────── */

function BallotEntryForm({ detail, onSaved }) {
  const toast = useToast()
  const eligible = detail.eligible || []
  const values = detail.settings?.ballot_values || [3, 2, 1]
  const captainOnly = detail.settings?.voter_mode === 'captain'
  const captains = eligible.filter((p) => p.is_captain)
  // "Who votes: Captain only" means only the captain's ballot should count —
  // default the voter picker to just them so a paper-vote transcription can't
  // accidentally record a non-captain's votes. Escape hatch for the genuine
  // edge case (vice-captain filled in, the captain flag missed a sync).
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
      await api.votesAdminBallot(detail.fixture.id, {
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
      <p className="text-[12px] text-pb-faint mb-3">
        Paper votes, or the captain texting theirs in. Entering again for the same voter replaces their ballot.
        {captainOnly && ' This club only counts the captain\'s votes.'}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Voter</label>
          <select value={voterId} onChange={(e) => setVoterId(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pb-accent min-w-[180px]">
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
              className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pb-accent min-w-[160px]">
              <option value="">—</option>
              {eligible
                .filter((p) => p.id === picks[i] || !picks.includes(p.id))
                .map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        ))}
        <Btn variant="primary" sm onClick={submit} disabled={!voterOk || saving}>{saving ? 'Saving…' : 'Save ballot'}</Btn>
      </div>
    </div>
  )
}

// Which team list this fixture's ballot is built from, what each of the other
// lists would give, and a per-fixture override.
function EligibilityPanel({ detail, onChanged }) {
  const toast = useToast()
  const e = detail.eligibility
  const [busy, setBusy] = useState(false)
  if (!e) return null

  const setSource = async (value) => {
    setBusy(true)
    try {
      await api.votesSetFixtureSource(detail.fixture.id, value)
      toast.success(value ? `Voting on the ${sourceLabel(value).toLowerCase()}` : 'Back to the club default')
      onChanged()
    } catch (err) { toast.error(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="pb-card px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <div className="font-display font-bold text-[15px]">Who can be voted for</div>
        <div className="text-[12px] text-pb-faint">
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
              <span className="font-mono text-[10px] text-pb-faint ml-1.5">
                {n == null ? '—' : `${n}`}
              </span>
            </button>
          )
        })}
        {e.override && (
          <button onClick={() => setSource('')} disabled={busy}
            className="text-[11.5px] text-pb-faint hover:text-pb-text underline">
            Use the club default ({sourceLabel(e.requested === e.override ? 'scorecard' : e.requested)})
          </button>
        )}
      </div>

      <div className="text-[11px] text-pb-faintest mt-2">
        The number is how many players each list would put on the ballot.
        {e.override ? ' This game overrides the club default.' : ' Changing it here only affects this game.'}
      </div>

      {e.unmatched?.length > 0 && (
        <div className="mt-2.5 text-[12px] rounded-lg px-3 py-2"
          style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
          Not on the ballot (no player record at your club): {e.unmatched.join(', ')}.
          Claim them from the match scorecard to make them votable.
        </div>
      )}
    </div>
  )
}

function FixtureDetail({ fixtureId, onBack }) {
  const toast = useToast()
  const [detail, setDetail] = useState(null)

  const load = useCallback(() => {
    api.votesFixtureDetail(fixtureId).then(setDetail).catch((e) => toast.error(e.message))
  }, [fixtureId, toast])
  useEffect(() => { load() }, [load])

  if (!detail) return <PbSpinner message="Loading ballots…" />
  const fx = detail.fixture
  const values = detail.settings?.ballot_values || [3, 2, 1]

  const setLock = async (lock) => {
    try {
      await (lock ? api.votesLockFixture(fx.id) : api.votesReopenFixture(fx.id))
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
        <Btn sm variant="ghost" icon="back" onClick={onBack}>All fixtures</Btn>
        <div className="font-display font-bold text-lg">{fx.round} · vs {fx.opponent || 'TBC'}</div>
        <span className="text-pb-faint text-sm">{fmtDate(fx.date)}</span>
        <StateBadge state={fx.state} />
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

      <EligibilityPanel detail={detail} onChanged={load} />

      {/* Weekly result */}
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
                {values.map((v, i) => <th key={i} className="py-1.5 pr-3 text-right">{v}s</th>)}
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

      {detail.eligible.length > 0 && <BallotEntryForm detail={detail} onSaved={load} />}

      {/* Ballots */}
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
  )
}

/* ── Fixtures tab ────────────────────────────────────────────────────────── */

function FixturesTab({ canManage, openFixture, setOpenFixture }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [year, setYear] = useState(null)
  const [gradeId, setGradeId] = useState('')
  const [roundKey, setRoundKey] = useState('')
  const [q, setQ] = useState('')

  const load = useCallback(() => {
    api.votesFixtures({ year, grade_id: gradeId || undefined, round_key: roundKey || undefined, q: q || undefined })
      .then(setData).catch((e) => toast.error(e.message))
  }, [year, gradeId, roundKey, q, toast])
  useEffect(() => { load() }, [load])

  const changeGrade = (v) => { setGradeId(v); setRoundKey('') } // rounds are scoped to the grade

  if (openFixture) return <FixtureDetail fixtureId={openFixture} onBack={() => { setOpenFixture(null); load() }} />
  if (!data) return <PbSpinner message="Loading fixtures…" />

  const filtered = gradeId || roundKey || q

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2.5 mb-4">
        <select value={data.year} onChange={(e) => { setYear(parseInt(e.target.value, 10)); setRoundKey('') }}
          className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
          {data.years.map((y) => <option key={y} value={y}>Season {seasonLabel(y)}</option>)}
        </select>
        {(data.grades || []).length > 0 && (
          <select value={gradeId} onChange={(e) => changeGrade(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
            <option value="">All teams / grades</option>
            {data.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}
        {(data.rounds || []).length > 0 && (
          <select value={roundKey} onChange={(e) => setRoundKey(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
            <option value="">All rounds</option>
            {data.rounds.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        )}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search opponent…"
          className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:border-pb-accent" />
        {!data.settings?.enabled && (
          <span className="text-[12.5px] text-pb-amber">
            The voting link is off, so players can't vote yet. Turn it on under Settings (admins can still enter ballots here).
          </span>
        )}
      </div>
      {data.fixtures.length === 0 ? (
        <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
          {filtered ? 'No fixtures match these filters.' : 'No played fixtures this season yet.'}
        </div>
      ) : (
        <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline">
          {data.fixtures.map((f) => {
            const inner = (
              <>
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-sm truncate">
                    {f.round} · {f.home_away === 'AWAY' ? '@' : 'vs'} {f.opponent || 'TBC'}
                  </div>
                  <div className="text-[12px] text-pb-faint mt-0.5">
                    {fmtDate(f.date)}{f.grade ? ` · ${f.grade}` : ''}
                    {f.closes_on ? ` · voting closes ${fmtDate(f.closes_on)}` : ''}
                  </div>
                </div>
                <span className="font-mono text-[11px] text-pb-faint shrink-0">
                  {f.ballots} ballot{f.ballots === 1 ? '' : 's'}
                </span>
                <StateBadge state={f.state} />
                {canManage && <span className="text-pb-faintest shrink-0">→</span>}
              </>
            )
            return canManage ? (
              <button key={f.id} onClick={() => setOpenFixture(f.id)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors">
                {inner}
              </button>
            ) : (
              <div key={f.id} className="flex items-center gap-3 px-4 py-3">{inner}</div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ── Leaderboard tab ─────────────────────────────────────────────────────── */

function LeaderboardTab() {
  const toast = useToast()
  const [board, setBoard] = useState(null)
  const [year, setYear] = useState(null)
  const [gradeId, setGradeId] = useState('')
  const [throughRound, setThroughRound] = useState('')
  const [showRounds, setShowRounds] = useState(false)

  useEffect(() => {
    let alive = true
    api.votesLeaderboard({ year, grade_id: gradeId || undefined, through_round: throughRound || undefined })
      .then((d) => { if (alive) setBoard(d) })
      .catch((e) => toast.error(e.message))
    return () => { alive = false }
  }, [year, gradeId, throughRound, toast])

  if (!board) return <PbSpinner message="Counting the votes…" />
  const values = board.ballot_values || [3, 2, 1]
  const counted = board.rounds.filter((r) => r.counted)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <select value={board.year} onChange={(e) => { setYear(parseInt(e.target.value, 10)); setThroughRound('') }}
          className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
          {[board.year, board.year - 1, board.year - 2].map((y) => <option key={y} value={y}>Season {seasonLabel(y)}</option>)}
        </select>
        <select value={gradeId} onChange={(e) => setGradeId(e.target.value)}
          className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
          <option value="">Whole club</option>
          {(board.grades || []).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
        <select value={throughRound} onChange={(e) => setThroughRound(e.target.value)}
          className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
          <option value="">Full season to date</option>
          {board.rounds.map((r) => <option key={r.key} value={r.key}>As at {r.label}</option>)}
        </select>
        <span className="text-[11.5px] text-pb-faintest">
          {board.counting_method === 'rank' ? `Weekly ${values.join('-')} conversion` : 'Full tally'} · ties {board.tie_policy === 'countback' ? 'broken on countback' : 'shared'}
        </span>
      </div>

      {board.standings.length === 0 ? (
        <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
          No votes counted yet{gradeId ? ' for this grade' : ''}. Ballots appear here as soon as they're cast.
        </div>
      ) : (
        <div className="pb-card px-4 py-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">
                <th className="py-1.5 pr-3 w-8">#</th>
                <th className="py-1.5 pr-3">Player</th>
                <th className="py-1.5 pr-3 text-right">Points</th>
                <th className="py-1.5 pr-3 text-right">Raw votes</th>
                {values.map((v, i) => <th key={i} className="py-1.5 pr-3 text-right hidden sm:table-cell">{v}s</th>)}
                <th className="py-1.5 text-right hidden sm:table-cell">Rounds</th>
              </tr>
            </thead>
            <tbody>
              {board.standings.map((s, i) => {
                const rank = i > 0 && s.points === board.standings[i - 1].points && s.raw === board.standings[i - 1].raw ? '=' : i + 1
                return (
                  <tr key={s.player_id} className="border-t pb-hairline">
                    <td className="py-2 pr-3 font-mono text-pb-faint">{rank}</td>
                    <td className="py-2 pr-3 font-medium">{s.name}</td>
                    <td className="py-2 pr-3 text-right font-mono font-bold" style={i === 0 ? { color: 'var(--pb-accent)' } : undefined}>{s.points}</td>
                    <td className="py-2 pr-3 text-right font-mono text-pb-dim">{s.raw}</td>
                    {s.counts.map((n, j) => <td key={j} className="py-2 pr-3 text-right font-mono text-pb-faint hidden sm:table-cell">{n || '·'}</td>)}
                    <td className="py-2 text-right font-mono text-pb-faint hidden sm:table-cell">{s.rounds}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {board.through_round && (
            <div className="text-[11.5px] text-pb-faintest mt-2.5">
              Standings as at {board.rounds.find((r) => r.key === board.through_round)?.label}. Later rounds are listed below but not counted.
            </div>
          )}
        </div>
      )}

      {/* Round by round */}
      {board.rounds.length > 0 && (
        <div className="pb-card px-4 py-4">
          <button onClick={() => setShowRounds((s) => !s)} className="w-full flex items-center justify-between">
            <span className="font-display font-bold text-[15px]">Round by round</span>
            <span className="text-pb-faint text-sm">{showRounds ? '▲' : '▼'}</span>
          </button>
          {showRounds && (
            <div className="mt-3 flex flex-col gap-4">
              {board.rounds.map((rd) => (
                <div key={rd.key} className={rd.counted ? '' : 'opacity-45'}>
                  <div className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint mb-1.5">
                    {rd.label} · {fmtDate(rd.date)}{rd.counted ? '' : ' · not counted'}
                  </div>
                  {rd.fixtures.map((f) => (
                    <div key={f.id} className="mb-1.5">
                      <span className="text-[13px] text-pb-dim">
                        vs {f.opponent || 'TBC'}{f.grade ? ` (${f.grade})` : ''}:{' '}
                        {f.results.filter((r) => r.points > 0).map((r, i) => {
                          const s = board.standings.find((x) => x.player_id === r.player_id)
                          return <span key={r.player_id}>{i > 0 && ', '}<b className="text-pb-text">{s?.name || 'Unknown'}</b> <span className="font-mono">{r.points}</span></span>
                        })}
                        {f.results.every((r) => !r.points) && <span className="text-pb-faintest">no votes</span>}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
              <div className="text-[11px] text-pb-faintest">{counted.length} of {board.rounds.length} round{board.rounds.length === 1 ? '' : 's'} counted.</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function AdminVotes() {
  const { hasCapability } = useAuth()
  const canManage = hasCapability(CAP.MANAGE_VOTES)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'fixtures'
  const [openFixture, setOpenFixture] = useState(null)

  const setTab = (t) => { setOpenFixture(null); setParams(t === 'fixtures' ? {} : { tab: t }, { replace: true }) }

  const tabs = useMemo(() => [
    { key: 'fixtures', label: 'Fixtures' },
    { key: 'leaderboard', label: 'Leaderboard' },
    ...(canManage ? [{ key: 'settings', label: 'Settings' }] : []),
  ], [canManage])

  return (
    <BetterSelectLayout title="Votes">
      <div className="flex items-center gap-1.5 mb-5 border-b pb-hairline">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3.5 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${tab === t.key
              ? 'border-pb-accent text-pb-accent'
              : 'border-transparent text-pb-faint hover:text-pb-text'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'fixtures' && <FixturesTab canManage={canManage} openFixture={openFixture} setOpenFixture={setOpenFixture} />}
      {tab === 'leaderboard' && <LeaderboardTab />}
      {tab === 'settings' && canManage && <SettingsTab canManage={canManage} />}
    </BetterSelectLayout>
  )
}
