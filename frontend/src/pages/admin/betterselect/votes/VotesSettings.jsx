// Settings tab — ONE medal's setup. The public-link block lives in
// ShareVotePanel (one sharing surface); everything else (name, grades,
// voter_mode, allow_non_participants, allow_self_vote, ballot_values,
// counting_method, tie_policy, eligibility_source, auto_close_days) patches
// the medal.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../../../contexts/ToastContext'
import { api } from '../../../../lib/api'
import { PbSpinner } from '../../../../lib/presskit'
import { Btn, Segmented } from '../ui'
import ShareVotePanel from './ShareVotePanel'

const SOURCES = [
  { value: 'scorecard', label: 'Match scorecard', hint: 'Who actually played. The most accurate, but only once the weekly sync lands.' },
  { value: 'lineup', label: 'BetterSelect XI', hint: 'The side you picked in Selection. Ready as soon as you save it.' },
  { value: 'playhq', label: 'Play.Cricket team list', hint: 'The side your club published on Play.Cricket. Ready on match day.' },
]
const ballotLabel = (v) => (v || []).join('-')

function Row({ label, hint, children }) {
  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-1.5 py-3.5 border-t pb-hairline first:border-0">
      <div className="w-56 shrink-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="text-xs text-pb-faint mt-0.5">{hint}</div>}
      </div>
      <div className="flex-1 min-w-[240px]">{children}</div>
    </div>
  )
}

export default function VotesSettings({
  canManage, medalId, gradeOptions = [], medalCount = 1, onChanged, onDeleted,
}) {
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [ballotDraft, setBallotDraft] = useState(null)
  const [nameDraft, setNameDraft] = useState(null)

  const load = useCallback(() => {
    setCfg(null)
    api.votesGetSettings(medalId).then(setCfg).catch((e) => toast.error(e.message))
  }, [toast, medalId])
  useEffect(() => { load() }, [load])

  const update = async (patch) => {
    if (!canManage) return
    setBusy(true)
    try {
      setCfg(await api.votesSetSettings(patch, medalId))
      setBallotDraft(null)
      setNameDraft(null)
      // The medal bar above shows the name, its on/off state and its grades,
      // so any of those changing has to refresh it too.
      onChanged?.()
    } catch (e) { toast.error(e.message || 'Update failed') }
    finally { setBusy(false) }
  }

  const removeMedal = async () => {
    const hasVotes = window.confirm(
      `Delete "${cfg.medal_name}"? Every ballot cast towards it is deleted too, and that can't be undone.`,
    )
    if (!hasVotes) return
    try {
      await api.votesDeleteMedal(medalId, { confirm: true })
      toast.success('Medal deleted')
      onDeleted?.()
    } catch (e) { toast.error(e.message || 'Could not delete the medal') }
  }

  // The picker works on grade NAMES, not the ids it sends: grades are per-season
  // rows, so a medal's stored id often belongs to an older season than the one
  // the picker offers. The server expands names back out when it counts.
  const toggleGrade = (option) => {
    const chosen = new Set(cfg.grade_names || [])
    if (chosen.has(option.name)) chosen.delete(option.name)
    else chosen.add(option.name)
    update({
      grade_ids: gradeOptions.filter((g) => chosen.has(g.name)).map((g) => g.id),
    })
  }

  if (!cfg) return <PbSpinner message="Loading settings…" />

  const chosenGrades = new Set(cfg.grade_names || [])

  const ballot = ballotDraft || (cfg.ballot_values || []).map(String)
  const setPos = (i, v) => setBallotDraft(ballot.map((x, j) => (j === i ? v.replace(/\D/g, '').slice(0, 3) : x)))
  const saveBallot = () => {
    const values = ballot.map((v) => parseInt(v, 10)).filter((n) => n > 0)
    if (!values.length) { toast.error('The ballot needs at least one position'); return }
    update({ ballot_values: values })
  }

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <ShareVotePanel settings={cfg} scope={{ label: cfg.medal_name }} />

      <div className="pb-card px-4 py-1">
        <Row label="Medal name" hint="What the club calls this award. It's what players see on the voting page.">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={nameDraft ?? cfg.medal_name} disabled={!canManage}
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && nameDraft?.trim()) update({ name: nameDraft.trim() }) }}
              className="flex-1 min-w-[200px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent" />
            {canManage && nameDraft !== null && nameDraft.trim() && nameDraft !== cfg.medal_name && (
              <Btn sm variant="primary" onClick={() => update({ name: nameDraft.trim() })} disabled={busy}>Save name</Btn>
            )}
          </div>
        </Row>
        <Row label="Grades it counts" hint="Leave every grade unticked to count the whole club. Ticking a grade counts it in every season, so you don't have to redo this each year.">
          {gradeOptions.length === 0 ? (
            <div className="text-[12.5px] text-pb-faint">
              No grades yet. This medal counts every game the club plays.
            </div>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5">
                {gradeOptions.map((g) => {
                  const on = chosenGrades.has(g.name)
                  return (
                    <button key={g.id} onClick={() => toggleGrade(g)} disabled={!canManage || busy}
                      className={`px-2.5 py-1 rounded-full text-[12.5px] border pb-hairline transition-colors ${
                        on ? 'bg-pb-accent text-pb-on-accent border-transparent'
                           : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}>
                      {g.name}
                    </button>
                  )
                })}
              </div>
              <div className="text-[11px] text-pb-faintest mt-1.5">
                {chosenGrades.size === 0
                  ? 'Counting every grade.'
                  : `Counting ${[...chosenGrades].join(', ')}. Games in any other grade are left off this medal entirely.`}
              </div>
            </>
          )}
        </Row>
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
          <div className="text-[11px] text-pb-faintest mt-1.5">
            Currently: {ballotLabel(cfg.ballot_values)} (highest value = best player). Values are sorted highest-first when saved.
          </div>
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
            {SOURCES.find((s) => s.value === cfg.eligibility_source)?.hint}{' '}
            If it's empty when voting opens, the next list that has players is used instead.
          </div>
        </Row>
        <Row label="Voting closes" hint="Days after the match before voting closes automatically. You can also lock or reopen any game yourself.">
          <select value={cfg.auto_close_days} onChange={(e) => update({ auto_close_days: parseInt(e.target.value, 10) })} disabled={!canManage}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
            {[2, 3, 4, 5, 6, 7, 10, 14, 21, 30].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </Row>
      </div>

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

      {canManage && medalCount > 1 && (
        <div className="pb-card px-4 py-4">
          <div className="font-display font-bold text-[15px] mb-1">Delete this medal</div>
          <p className="text-[12.5px] text-pb-faint mb-3">
            Every ballot cast towards <b className="text-pb-text">{cfg.medal_name}</b> goes with it, and
            there's no undo. Your other medals and their counts are untouched.
          </p>
          <Btn sm variant="danger" onClick={removeMedal}>Delete {cfg.medal_name}</Btn>
        </div>
      )}
    </div>
  )
}
