// Settings tab — ONE medal's setup. The public-link block lives in
// ShareVotePanel (one sharing surface); everything else (name, grades,
// voter_mode (plus grade_voter_modes and grade_vote_counters, one override per team; a team on
// 'chosen' lists the people who vote for it), allow_non_participants, allow_self_vote, ballot_values,
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
const MODE_LABEL = { players: 'All players', captain: 'Captain only', chosen: 'Chosen people' }
const MAX_CHOSEN = 12

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

const WEIGHT_MODES = [
  { value: 'off', label: 'Same for every grade' },
  { value: 'auto', label: 'Auto-weight' },
  { value: 'manual', label: 'Manual' },
]
const fmtWeight = (w) => `×${Number(w).toFixed(2).replace(/\.?0+$/, '')}`

// Grade weighting: grades play different numbers of games, so a vote in a
// 12 game season is not the same effort as one in an 18 game season. A module
// level component (not declared inside the settings render) so the manual
// inputs keep their caret while the parent re-renders.
function GradeWeighting({ cfg, medalId, canManage, busy, update }) {
  const toast = useToast()
  const [info, setInfo] = useState(null)
  const [draft, setDraft] = useState({})
  const mode = cfg.grade_weighting?.mode || 'off'
  // Anything that changes a row (which grades, the ballot, the weighting
  // itself) re-reads the table from the server.
  const key = JSON.stringify([cfg.grade_ids, cfg.ballot_values, cfg.grade_weighting])

  useEffect(() => {
    let live = true
    api.votesGetWeighting(medalId)
      .then((d) => { if (live) { setInfo(d); setDraft({}) } })
      .catch((e) => toast.error(e.message))
    return () => { live = false }
  }, [medalId, key, toast])

  if (!info) return <div className="text-[12.5px] text-pb-faint">Loading grades…</div>

  const rows = info.rows || []
  const anyGames = rows.some((r) => r.games > 0)

  const pickMode = (next) => {
    if (next === mode) return
    if (next === 'manual') {
      // Start from what's in force, so switching doesn't reset every grade to 1.
      const saved = cfg.grade_weighting?.manual || {}
      const start = Object.keys(saved).length
        ? saved
        : Object.fromEntries(rows.map((r) => [r.name, r.auto_weight ?? 1]))
      update({ grade_weighting: { mode: 'manual', manual: start } })
    } else if (next === 'auto') update({ grade_weighting: { mode: 'auto' } })
    else update({ grade_weighting: {} })
  }

  const dirty = Object.keys(draft).length > 0
  const saveManual = () => {
    const manual = { ...(cfg.grade_weighting?.manual || {}) }
    for (const [name, raw] of Object.entries(draft)) {
      const n = parseFloat(raw)
      if (!(n >= 0.01 && n <= 10)) { toast.error(`${name}: the weight has to be between 0.01 and 10`); return }
      manual[name] = Math.round(n * 100) / 100
    }
    update({ grade_weighting: { mode: 'manual', manual } })
  }

  return (
    <>
      <Segmented sm value={mode} onChange={pickMode}
        options={WEIGHT_MODES} />
      <div className="text-[11px] text-pb-faintest mt-1.5">
        {mode === 'off' && 'Every vote counts the same, whatever the grade. A 3-2-1 is 3-2-1 everywhere.'}
        {mode === 'auto' && (info.top_grade
          ? `Measured against ${info.top_grade}, your top grade. A vote in a grade with fewer games counts for more, so 3-2-1 is worth the same per game played.`
          : 'There are no fixtures for these grades yet, so every grade counts the same until there are.')}
        {mode === 'manual' && 'Type how much a vote is worth in each grade. 1 is the normal 3-2-1, 1.5 makes it 4.5-3-1.5.'}
      </div>

      {rows.length > 0 && (
        <div className="mt-3 text-sm">
          <div className="grid grid-cols-[minmax(0,1fr)_56px_96px_64px] items-center gap-x-3 pb-1 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">
            <div>Grade · {info.season_label}</div><div className="text-right">Games</div>
            <div className="text-right">Votes ×</div><div className="text-right">Top vote</div>
          </div>
          {rows.map((r) => (
            <div key={r.name} className="grid grid-cols-[minmax(0,1fr)_56px_96px_64px] items-center gap-x-3 py-1.5 border-t pb-hairline">
              <div className="min-w-0 break-words">
                {r.name}
                {mode === 'auto' && r.is_top && (
                  <span title="Top grade: every other grade is measured against its season length"
                    className="ml-1.5 align-middle font-mono text-[9.5px] uppercase tracking-wide2 px-1.5 py-0.5 rounded bg-pb-accent/15 text-pb-accent">Top</span>
                )}
              </div>
              <div className="text-right font-mono">{r.games > 0 ? r.games : <span className="text-pb-faintest">none</span>}</div>
              <div className="text-right">
                {mode === 'manual' ? (
                  <input value={draft[r.name] ?? String(r.weight)} disabled={!canManage || busy}
                    inputMode="decimal" aria-label={`Vote weight for ${r.name}`}
                    onChange={(e) => setDraft({ ...draft, [r.name]: e.target.value.replace(/[^0-9.]/g, '').slice(0, 5) })}
                    onKeyDown={(e) => { if (e.key === 'Enter' && dirty) saveManual() }}
                    className="w-20 text-center bg-pb-surface2 border pb-hairline rounded-lg px-2 py-1 text-sm font-mono focus:outline-none focus:border-pb-accent" />
                ) : (
                  <span className={`font-mono ${mode === 'off' ? 'text-pb-faint' : 'font-bold'}`}>{fmtWeight(r.weight)}</span>
                )}
                {mode !== 'auto' && r.auto_weight != null && Math.abs(r.auto_weight - r.weight) > 0.004 && (
                  <div className="text-[10.5px] text-pb-faintest">auto {fmtWeight(r.auto_weight)}</div>
                )}
              </div>
              <div className="text-right font-mono text-pb-faint">{r.top_vote}</div>
            </div>
          ))}
        </div>
      )}
      {mode === 'manual' && canManage && dirty && (
        <div className="mt-2.5"><Btn sm variant="primary" onClick={saveManual} disabled={busy}>Save weights</Btn></div>
      )}
      {!anyGames && rows.length > 0 && (
        <div className="text-[11px] text-pb-faintest mt-2">
          No fixtures found for this season yet. Games are counted from your Fixtures, byes and cancelled rounds left out.
        </div>
      )}
    </>
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
  // Who a team can choose to vote for it. Loaded once; they do not have to be
  // in the side.
  const [people, setPeople] = useState([])

  const load = useCallback(() => {
    setCfg(null)
    api.votesGetSettings(medalId).then(setCfg).catch((e) => toast.error(e.message))
  }, [toast, medalId])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    let live = true
    api.votesVoterOptions().then((d) => { if (live) setPeople(d.players || []) }).catch(() => {})
    return () => { live = false }
  }, [])

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
  // A ticked grade that is no longer played is not offered by the picker but
  // is still counted, so its id rides along until the club unticks it below.
  const toggleGrade = (option) => {
    const chosen = new Set(cfg.grade_names || [])
    if (chosen.has(option.name)) chosen.delete(option.name)
    else chosen.add(option.name)
    update({
      grade_ids: [
        ...gradeOptions.filter((g) => chosen.has(g.name)).map((g) => g.id),
        ...(cfg.inactive_grades || []).map((g) => g.id),
      ],
    })
  }
  const dropInactiveGrade = (grade) => {
    const ids = [
      ...gradeOptions.filter((g) => (cfg.grade_names || []).includes(g.name)).map((g) => g.id),
      ...(cfg.inactive_grades || []).filter((g) => g.id !== grade.id).map((g) => g.id),
    ]
    // No grades ticked means every grade, so removing the last one widens the medal.
    if (!ids.length && !window.confirm(
      `${grade.name} is the only grade ticked. Removing it makes this medal count every grade. Continue?`,
    )) return
    update({ grade_ids: ids })
  }
  const setTeamMode = (name, mode) => {
    const next = { ...(cfg.grade_voter_modes || {}) }
    if (mode === 'default') delete next[name]
    else next[name] = mode
    update({ grade_voter_modes: next })
  }

  // The team's list is sent whole, so the server keeps exactly what is on screen.
  const setChosen = (name, ids) => {
    const next = { ...(cfg.grade_vote_counters || {}) }
    if (ids.length) next[name] = ids
    else delete next[name]
    update({ grade_vote_counters: next })
  }

  if (!cfg) return <PbSpinner message="Loading settings…" />

  const chosenGrades = new Set(cfg.grade_names || [])
  const inactiveGrades = cfg.inactive_grades || []
  const teamModes = cfg.grade_voter_modes || {}
  const teamChosen = cfg.vote_chosen || {}
  // The teams this medal counts: the ticked ones, or every active team when
  // none is ticked. The server lists a grade once per team when two of the club's
  // teams play it, and each is stored under its own key (see team_options).
  const teamOptions = cfg.team_options || gradeOptions.map((g) => ({ key: g.name, grade_name: g.name, name: g.name }))
  const scopeTeams = teamOptions.filter((t) => chosenGrades.size === 0 || chosenGrades.has(t.grade_name))

  const ballot = ballotDraft || (cfg.ballot_values || []).map(String)
  const setPos = (i, v) => setBallotDraft(ballot.map((x, j) => (j === i ? v.replace(/\D/g, '').slice(0, 3) : x)))
  const saveBallot = () => {
    const values = ballot.map((v) => parseInt(v, 10)).filter((n) => n > 0)
    if (!values.length) { toast.error('The ballot needs at least one position'); return }
    update({ ballot_values: values })
  }

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <ShareVotePanel settings={cfg} scope={{ label: cfg.medal_name }}
        onEnable={canManage ? () => update({ enabled: true }) : undefined} busy={busy} />

      <div className="pb-card px-4 py-1">
        <Row label="Voting link" hint="Players can only vote while this is on. A new medal starts off. Turning it off keeps every ballot already cast.">
          <Segmented sm value={cfg.enabled ? 'on' : 'off'} onChange={(v) => update({ enabled: v === 'on' })}
            options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]} />
        </Row>
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
        <Row label="Grades it counts" hint="Only the grades your club is playing this season are listed. Leave every grade unticked to count the whole club. Ticking a grade counts it in every season, so you don't have to redo this each year.">
          {gradeOptions.length === 0 && inactiveGrades.length === 0 ? (
            <div className="text-[12.5px] text-pb-faint">
              No grades yet — this medal counts every game the club plays.
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
              {inactiveGrades.length > 0 && (
                <div className="mt-2.5">
                  <div className="text-[11px] text-pb-faintest mb-1">
                    Still ticked, but not played this season. Untick to stop counting them.
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {inactiveGrades.map((g) => (
                      <button key={g.id} onClick={() => dropInactiveGrade(g)} disabled={!canManage || busy}
                        title="Stop counting this grade"
                        className="px-2.5 py-1 rounded-full text-[12.5px] border pb-hairline bg-pb-surface2 text-pb-faint hover:text-pb-text">
                        {g.name} ✕
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-[11px] text-pb-faintest mt-1.5">
                {chosenGrades.size === 0
                  ? 'Counting every grade.'
                  : `Counting ${[...chosenGrades].join(', ')}. Games in any other grade are left off this medal entirely.`}
              </div>
            </>
          )}
        </Row>
        <Row label="Who votes" hint="Every player in the game, or just the captain. This is the default for every team; set a team below to do it differently.">
          <Segmented sm value={cfg.voter_mode} onChange={(v) => update({ voter_mode: v })}
            options={[{ value: 'players', label: 'All players' }, { value: 'captain', label: 'Captain only' }]} />
        </Row>
        {scopeTeams.length > 0 && (
          <Row label="Who votes, by team" hint="Some teams count every player's vote, others only the captain's. Pick per team, or leave a team on the default above. Choose people to have a few named people decide a team's votes (say the captain and two selectors). They don't have to be in the side, and each submits their own ballot.">
            <div className="flex flex-col gap-1.5">
              {scopeTeams.map((g) => {
                const chosen = teamChosen[g.key] || []
                const chosenIds = new Set(chosen.map((x) => x.id))
                const addable = people.filter((x) => !chosenIds.has(x.id))
                return (
                  <div key={g.key} className="flex flex-col gap-1.5">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="text-sm min-w-0 break-words">{g.name}</span>
                      <select value={teamModes[g.key] || 'default'} onChange={(e) => setTeamMode(g.key, e.target.value)}
                        disabled={!canManage || busy}
                        className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-pb-accent">
                        <option value="default">Default ({MODE_LABEL[cfg.voter_mode]})</option>
                        <option value="players">{MODE_LABEL.players}</option>
                        <option value="captain">{MODE_LABEL.captain}</option>
                        <option value="chosen">{MODE_LABEL.chosen}</option>
                      </select>
                    </div>
                    {teamModes[g.key] === 'chosen' && (
                      <div className="pl-3 flex flex-col gap-1.5" data-testid={`chosen-${g.key}`}>
                        {chosen.length === 0 ? (
                          <div className="text-[12px] text-pb-amber">
                            Nobody is chosen yet, so nobody can vote for this team.
                          </div>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {chosen.map((x) => (
                              <span key={x.id} className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-full text-[12.5px] bg-pb-surface2 border pb-hairline">
                                <span className="min-w-0 break-words">{x.name}</span>
                                {canManage && (
                                  <button type="button" disabled={busy} title={`Remove ${x.name}`} aria-label={`Remove ${x.name} from ${g.name}`}
                                    onClick={() => setChosen(g.key, chosen.filter((y) => y.id !== x.id).map((y) => y.id))}
                                    className="text-pb-faintest hover:text-pb-red text-xs px-1">✕</button>
                                )}
                              </span>
                            ))}
                          </div>
                        )}
                        {canManage && (
                          <select value="" disabled={busy || chosen.length >= MAX_CHOSEN}
                            aria-label={`Add a person to vote for ${g.name}`}
                            onChange={(e) => e.target.value && setChosen(g.key, [...chosen.map((y) => y.id), e.target.value])}
                            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm max-w-full focus:outline-none focus:border-pb-accent">
                            <option value="">{chosen.length >= MAX_CHOSEN ? `Up to ${MAX_CHOSEN} people` : 'Add a person…'}</option>
                            {addable.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                          </select>
                        )}
                        <div className="text-[11px] text-pb-faintest">
                          Only these people can vote for {g.name}, and each one submits their own ballot. Their votes add up and are turned into the game's {ballotLabel(cfg.ballot_values)} the same way as when every player votes.
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </Row>
        )}
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
                ? 'Tied players share the position and both take the higher points, so a game can hand out more points than the ballot holds.'
                : `Ties break on who received more ${cfg.ballot_values[0]}s, then ${cfg.ballot_values[1] ?? '—'}s, and so on. A dead heat after every countback still shares.`}
            </div>
          </Row>
        )}
        <Row label="Weight by grade" hint="Grades that play more games give a player more chances to collect votes. Weighting makes a vote in a shorter season count for more, so the grades are fair against each other.">
          <GradeWeighting cfg={cfg} medalId={medalId} canManage={canManage} busy={busy} update={update} />
        </Row>
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
