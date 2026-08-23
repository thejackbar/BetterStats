// BetterFootball → Votes. Best-and-fairest counting.
//
// A club counts votes towards one MEDAL or several — a senior Best & Fairest
// on 3-2-1 alongside a Reserves medal on 5-4-3-2-1, a coach's award — each with
// its own ballot shape, voter mode, counting method, public link and the
// grades it counts. The medal picker sits above the tabs because every tab
// below shows exactly one medal's count.
//
// Eligibility needs no setting here: football has one team list, the one PlayHQ
// returns with the game, which the sync already stores. A game is votable once
// it has synced.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

const TABS = [
  { key: 'games', label: 'Games' },
  { key: 'count', label: 'The count' },
  { key: 'medals', label: 'Medals' },
]

const STATE_LABEL = {
  open: 'Open', closed: 'Closed', locked: 'Locked',
  awaiting_team: 'No team list', upcoming: 'Not played',
}

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-AU',
  { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

function Pill({ children, tone = 'plain' }) {
  const tones = {
    plain: 'bg-pb-surface2 text-pb-faint',
    open: 'bg-pb-positive/15 text-pb-positive',
    warn: 'bg-pb-accent/15 text-pb-accent-ink',
  }
  return <span className={`px-2 py-0.5 rounded-full text-[11px] ${tones[tone] || tones.plain}`}>{children}</span>
}

export default function AflAdminVotes() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'games'
  const medalId = params.get('medal') || ''
  const [medals, setMedals] = useState(null)
  const [grades, setGrades] = useState([])
  const [error, setError] = useState(null)

  const loadMedals = useCallback(() => aflApi.votesMedals()
    .then((d) => { setMedals(d.medals || []); setGrades(d.grades || []) })
    .catch((e) => { setError(e.message); setMedals([]) }), [])
  useEffect(() => { loadMedals() }, [loadMedals])

  // A medal named in the URL the club no longer holds falls back to the first,
  // rather than leaving an empty screen with no way out.
  const active = useMemo(() => {
    if (!medals?.length) return ''
    return medals.some((m) => m.medal_id === medalId) ? medalId : medals[0].medal_id
  }, [medals, medalId])

  const go = (next) => setParams(next, { replace: true })
  const setTab = (t) => go({ ...(t === 'games' ? {} : { tab: t }), ...(active ? { medal: active } : {}) })
  const setMedal = (id) => go({ ...(tab === 'games' ? {} : { tab }), medal: id })

  const addMedal = async () => {
    const name = window.prompt('What is this medal called?', 'Best & Fairest')
    if (!name?.trim()) return
    try {
      const created = await aflApi.votesCreateMedal({ name: name.trim() })
      await loadMedals()
      // Straight to Medals: a new one is off, ungraded and has no link, so the
      // Games tab would show it with nothing to do.
      go({ tab: 'medals', medal: created.medal_id })
    } catch (e) { setError(e.message) }
  }

  if (medals === null) return <div className="text-pb-faint text-sm">Loading votes…</div>

  return (
    <div>
      <SectionTitle>Votes</SectionTitle>
      {error && <div className="text-pb-red text-sm mb-3">{error}</div>}

      <div className="flex flex-wrap items-center gap-1.5 mb-4">
        {medals.map((m) => (
          <button key={m.medal_id} onClick={() => setMedal(m.medal_id)}
            className={`px-3 py-1.5 rounded-full text-[13px] font-medium border pb-hairline transition-colors ${
              m.medal_id === active ? 'bg-pb-accent text-pb-on-accent border-transparent'
                : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}
            title={m.grade_names?.length ? m.grade_names.join(', ') : 'Every grade'}>
            {m.medal_name}
            {!m.enabled && <span className="ml-1.5 text-[10px] opacity-70">off</span>}
          </button>
        ))}
        <button onClick={addMedal}
          className="px-3 py-1.5 rounded-full text-[13px] text-pb-faint hover:text-pb-text border pb-hairline">
          + New medal
        </button>
      </div>

      <div className="flex items-center gap-1.5 mb-5 border-b pb-hairline">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3.5 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key ? 'border-pb-accent text-pb-accent'
                : 'border-transparent text-pb-faint hover:text-pb-text'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'games' && <GamesTab medalId={active} />}
      {tab === 'count' && <CountTab medalId={active} />}
      {tab === 'medals' && (
        <MedalTab medalId={active} grades={grades} medalCount={medals.length}
          onChanged={loadMedals}
          onDeleted={() => { loadMedals(); go({ tab: 'medals' }) }} />
      )}
    </div>
  )
}


function GamesTab({ medalId }) {
  const [data, setData] = useState(null)
  const [seasonId, setSeasonId] = useState('')
  const [gradeId, setGradeId] = useState('')
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setData(null)
    aflApi.votesGames({
      medal_id: medalId || undefined,
      season_id: seasonId || undefined,
      grade_id: gradeId || undefined,
    }).then((d) => { setData(d); if (!seasonId && d.season_id) setSeasonId(d.season_id) })
      .catch((e) => setError(e.message))
  }, [medalId, seasonId, gradeId])
  useEffect(() => { load() }, [load])

  const act = async (gameId, lock) => {
    try {
      await (lock ? aflApi.votesLockGame(gameId, medalId) : aflApi.votesReopenGame(gameId, medalId))
      load()
    } catch (e) { setError(e.message) }
  }

  if (error) return <div className="text-pb-red text-sm">{error}</div>
  if (!data) return <div className="text-pb-faint text-sm">Loading games…</div>

  const s = data.summary
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {[
          ['Open now', s.open], ['No team list', s.awaiting_team],
          ['Ballots this round', `${s.ballots_in}/${s.ballots_expected || '—'}`],
          ['Rounds counted', `${s.rounds_counted}/${s.rounds_total}`],
        ].map(([label, value]) => (
          <div key={label} className="pb-card px-3 py-2.5">
            <div className="font-mono text-[10px] tracking-wide2 text-pb-faint">{label.toUpperCase()}</div>
            <div className="font-display font-bold text-lg leading-tight mt-0.5">{value}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {data.seasons?.length > 1 && (
          <select value={seasonId} onChange={(e) => setSeasonId(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm">
            {data.seasons.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        )}
        {data.grades?.length > 1 && (
          <select value={gradeId} onChange={(e) => setGradeId(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm">
            <option value="">All grades</option>
            {data.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}
      </div>

      {data.games.length === 0 ? (
        <div className="pb-card px-4 py-6 text-center text-sm text-pb-faint">
          No games this medal counts yet.
        </div>
      ) : (
        <div className="pb-card divide-y pb-hairline">
          {data.games.map((g) => (
            <div key={g.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="font-medium text-sm truncate">v {g.opponent}</div>
                <div className="text-[12px] text-pb-faint">
                  {g.round} · {fmtDate(g.date)}{g.grade ? ` · ${g.grade}` : ''}
                </div>
              </div>
              <Pill tone={g.state === 'open' ? 'open' : g.state === 'awaiting_team' ? 'warn' : 'plain'}>
                {STATE_LABEL[g.state] || g.state}
              </Pill>
              <div className="font-mono text-[11px] text-pb-faint w-20 text-right">
                {g.ballots}/{g.voters_expected || '—'}
              </div>
              {g.state !== 'awaiting_team' && g.state !== 'upcoming' && (
                <button onClick={() => act(g.id, g.state === 'open')}
                  className="text-[12px] text-pb-faint hover:text-pb-text underline">
                  {g.state === 'open' ? 'Lock' : 'Reopen'}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


function CountTab({ medalId }) {
  const [board, setBoard] = useState(null)
  const [seasonId, setSeasonId] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    setBoard(null)
    aflApi.votesLeaderboard({ medal_id: medalId || undefined, season_id: seasonId || undefined })
      .then((d) => { setBoard(d); if (!seasonId && d.season_id) setSeasonId(d.season_id) })
      .catch((e) => setError(e.message))
  }, [medalId, seasonId])

  if (error) return <div className="text-pb-red text-sm">{error}</div>
  if (!board) return <div className="text-pb-faint text-sm">Loading the count…</div>

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="font-display font-bold text-[15px]">{board.medal_name}</div>
        <span className="text-[12px] text-pb-faint">
          {board.grade_name} · {(board.ballot_values || []).join('-')}
        </span>
        {board.seasons?.length > 1 && (
          <select value={seasonId} onChange={(e) => setSeasonId(e.target.value)}
            className="ml-auto bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm">
            {board.seasons.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        )}
      </div>

      {board.standings.length === 0 ? (
        <div className="pb-card px-4 py-6 text-center text-sm text-pb-faint">
          No votes counted yet.
        </div>
      ) : (
        <div className="pb-card divide-y pb-hairline">
          {board.standings.map((row, i) => (
            <div key={row.player_id} className="flex items-center gap-3 px-4 py-2.5">
              <div className="font-mono text-[12px] text-pb-faint w-6">{row.tied ? '=' : i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{row.name}</div>
                {row.grade && <div className="text-[11px] text-pb-faint">{row.grade}</div>}
              </div>
              <div className="font-display font-bold">{row.points}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


function MedalTab({ medalId, grades, medalCount, onChanged, onDeleted }) {
  const [cfg, setCfg] = useState(null)
  const [name, setName] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setCfg(null); setName(null)
    aflApi.votesMedals()
      .then((d) => setCfg((d.medals || []).find((m) => m.medal_id === medalId) || null))
      .catch((e) => setError(e.message))
  }, [medalId])
  useEffect(() => { load() }, [load])

  const save = async (patch) => {
    try {
      const next = await aflApi.votesUpdateMedal(medalId, patch)
      setCfg(next); setName(null); onChanged?.()
    } catch (e) { setError(e.message) }
  }

  // The picker works on grade NAMES, not the ids it sends: grades are
  // per-season rows, so a medal's stored id is often an older season's than
  // the one offered here. The server expands names back out when counting.
  const toggleGrade = (g) => {
    const chosen = new Set(cfg.grade_names || [])
    chosen.has(g.name) ? chosen.delete(g.name) : chosen.add(g.name)
    save({ grade_ids: grades.filter((x) => chosen.has(x.name)).map((x) => x.id) })
  }

  const remove = async () => {
    if (!window.confirm(`Delete "${cfg.medal_name}"? Every ballot cast towards it goes too, and that can't be undone.`)) return
    try { await aflApi.votesDeleteMedal(medalId, { confirm: true }); onDeleted?.() }
    catch (e) { setError(e.message) }
  }

  if (error) return <div className="text-pb-red text-sm">{error}</div>
  if (!cfg) return <div className="text-pb-faint text-sm">Loading…</div>

  const chosen = new Set(cfg.grade_names || [])
  const voteLink = cfg.token ? `${window.location.origin}/vote/${cfg.token}` : null

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div className="pb-card px-4 py-4">
        <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">MEDAL NAME</label>
        <div className="flex flex-wrap gap-2">
          <input value={name ?? cfg.medal_name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && name?.trim()) save({ name: name.trim() }) }}
            className="flex-1 min-w-[200px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-1.5 text-sm" />
          {name !== null && name.trim() && name !== cfg.medal_name && (
            <button onClick={() => save({ name: name.trim() })}
              className="px-3 py-1.5 rounded-lg text-sm bg-pb-accent text-pb-on-accent">Save name</button>
          )}
        </div>
      </div>

      <div className="pb-card px-4 py-4">
        <div className="font-display font-bold text-[15px] mb-1">Collecting votes</div>
        <p className="text-[12.5px] text-pb-faint mb-3">
          Turning this on creates the link players use to vote. Nothing on the public site ever
          shows the count.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => save({ enabled: !cfg.enabled })}
            className={`px-3 py-1.5 rounded-lg text-sm ${cfg.enabled
              ? 'bg-pb-accent text-pb-on-accent' : 'bg-pb-surface2 text-pb-faint'}`}>
            {cfg.enabled ? 'On' : 'Off'}
          </button>
          {voteLink && (
            <button onClick={() => navigator.clipboard?.writeText(voteLink)}
              className="text-[12.5px] text-pb-accent underline">Copy voting link</button>
          )}
        </div>
      </div>

      <div className="pb-card px-4 py-4">
        <div className="font-display font-bold text-[15px] mb-1">Grades it counts</div>
        <p className="text-[12.5px] text-pb-faint mb-3">
          Leave every grade unticked to count the whole club. Ticking a grade counts it in every
          season, so you set this up once rather than redoing it each year.
        </p>
        {grades.length === 0 ? (
          <div className="text-[12.5px] text-pb-faint">No grades yet. This medal counts every game.</div>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5">
              {grades.map((g) => (
                <button key={g.id} onClick={() => toggleGrade(g)}
                  className={`px-2.5 py-1 rounded-full text-[12.5px] border pb-hairline ${
                    chosen.has(g.name) ? 'bg-pb-accent text-pb-on-accent border-transparent'
                      : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}>
                  {g.name}
                </button>
              ))}
            </div>
            <div className="text-[11px] text-pb-faintest mt-2">
              {chosen.size === 0 ? 'Counting every grade.'
                : `Counting ${[...chosen].join(', ')}. Games in any other grade are left off this medal.`}
            </div>
          </>
        )}
      </div>

      <div className="pb-card px-4 py-4">
        <div className="font-display font-bold text-[15px] mb-3">The ballot</div>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          {[[3, 2, 1], [5, 4, 3, 2, 1], [1]].map((v) => (
            <button key={v.join('-')} onClick={() => save({ ballot_values: v })}
              className={`px-2.5 py-1 rounded-full text-[12.5px] border pb-hairline ${
                (cfg.ballot_values || []).join('-') === v.join('-')
                  ? 'bg-pb-accent text-pb-on-accent border-transparent'
                  : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}>
              {v.join('-')}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-pb-faintest">
          Highest value goes to the best player. Currently {(cfg.ballot_values || []).join('-')}.
        </div>
      </div>

      {medalCount > 1 && (
        <div className="pb-card px-4 py-4">
          <div className="font-display font-bold text-[15px] mb-1">Delete this medal</div>
          <p className="text-[12.5px] text-pb-faint mb-3">
            Every ballot cast towards <b className="text-pb-text">{cfg.medal_name}</b> goes with it,
            and there's no undo. Your other medals and their counts are untouched.
          </p>
          <button onClick={remove}
            className="px-3 py-1.5 rounded-lg text-sm text-pb-red border border-pb-red/40 hover:bg-pb-red/10">
            Delete {cfg.medal_name}
          </button>
        </div>
      )}
    </div>
  )
}
