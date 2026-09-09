import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../lib/api'
import {
  Button, TextInput, Field, Note, Caption, StatCard, TableWrap, TableHead,
  TableRow, Cell, Badge, SegButtons, Empty,
} from './ui'
import { useToast } from '../../contexts/ToastContext'

const HISTORY_COLS = 'minmax(160px,1fr) 180px 110px 90px 90px'
const HISTORY_MIN_W = 660

const PHASES = {
  starting: 'Getting started',
  seasons: 'Checking which seasons you played',
  planned: 'Ready to pull',
  matches: 'Bringing your matches across',
  records: 'Copying your record book',
  notes: 'Reading your honour board',
  done: 'Finished',
}

function pct(done, total) {
  if (!total) return 0
  return Math.min(100, Math.round((done / total) * 100))
}

function Bar({ value }) {
  return (
    <div className="h-2 w-full rounded-full overflow-hidden"
         style={{ background: 'var(--pb-surface2)' }}>
      <div className="h-full rounded-full transition-all"
           style={{ width: `${value}%`, background: 'var(--pb-accent)' }} />
    </div>
  )
}

export default function CricketStatzImport() {
  const toast = useToast()
  const [url, setUrl] = useState('')
  const [checking, setChecking] = useState(false)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)
  const [imports, setImports] = useState([])
  const [records, setRecords] = useState([])
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState('import')
  // A club that already syncs from Cricket Australia holds those seasons once.
  // Bringing them in again does not correct anything — it counts the same
  // cricket twice on every career total — so it is opt-in.
  // What to do with the seasons the club already syncs from Cricket
  // Australia: leave them to the sync, or make CricketStatz the record for
  // them. There is no third option that keeps both — that is the double count.
  const [syncedYears, setSyncedYears] = useState('skip')
  const [undoing, setUndoing] = useState(null)
  const [pairing, setPairing] = useState(false)
  const [readingNotes, setReadingNotes] = useState(false)
  const pollRef = useRef(null)

  const running = status?.import?.status === 'running'

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.csStatus()
      setStatus(s)
      if (s?.club_id && !url) setUrl(`https://www2.cricketstatz.com/ss/w?club=${s.club_id}`)
      return s
    } catch { return null }
  }, [url])

  const loadRest = useCallback(async () => {
    try { setImports((await api.csImports()).imports || []) } catch { /* listed on next load */ }
    try { setRecords((await api.csRecords()).records || []) } catch { /* ditto */ }
  }, [])

  useEffect(() => { loadStatus(); loadRest() }, [])   // eslint-disable-line

  // While an import runs, poll it — it can be several thousand matches, so the
  // request that starts it returns immediately and progress is read from here.
  useEffect(() => {
    if (!running) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return undefined
    }
    pollRef.current = setInterval(async () => {
      const s = await loadStatus()
      if (s?.import?.status !== 'running') loadRest()
    }, 2500)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [running, loadStatus, loadRest])

  async function check() {
    setChecking(true); setError(''); setPreview(null)
    try {
      setPreview(await api.csInspect(url))
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not read that address.')
    } finally { setChecking(false) }
  }

  async function start() {
    setStarting(true); setError('')
    try {
      await api.csStartImport(url, syncedYears)
      toast?.success?.('Import started — this page will keep you posted.')
      await loadStatus()
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not start the import.')
    } finally { setStarting(false) }
  }

  async function readNotes() {
    setReadingNotes(true)
    setError('')
    try {
      await api.csReadNotes()
      await loadStatus()
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not read the player notes.')
    } finally { setReadingNotes(false) }
  }

  // Runs by itself after an import and after a full sync; this is the escape
  // hatch for a club that has just had matches arrive on one side and would
  // rather not wait. Re-derives from scratch, so pressing it twice is
  // pressing it once.
  async function rebuildPairing() {
    setPairing(true)
    try {
      const r = await api.csRebuildPairing()
      toast?.success?.(
        `${r.paired} imported match(es) matched to a synced one, `
        + `${r.only_cricketstatz} only CricketStatz has.`)
      setPreview(await api.csInspect(url))
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not check for duplicates.')
    } finally { setPairing(false) }
  }

  async function stop(id) {
    if (!window.confirm(
      'Stop this import?\n\nWhat it has already brought across is kept — you '
      + 'can start it again and it will pick the rest up without doubling '
      + 'anything.')) return
    try {
      await api.csStop(id)
      toast?.success?.('Import stopped.')
      await loadStatus(); await loadRest()
    } catch (e) {
      toast?.error?.(e?.detail || 'Could not stop that import.')
    }
  }

  async function undo(id) {
    if (!window.confirm(
      'Remove every match and record this import brought across?\n\n'
      + 'Players and seasons are kept — only the imported matches and record '
      + 'boards go. Your Cricket Australia matches are untouched.')) return
    setUndoing(id)
    try {
      const r = await api.csUndo(id)
      toast?.success?.(
        `Removed ${r.matches_removed} matches, ${r.records_removed} record `
        + `boards and ${r.awards_removed || 0} honours.`)
      await loadStatus(); await loadRest()
    } catch (e) {
      toast?.error?.(e?.detail || 'Could not undo that import.')
    } finally { setUndoing(null) }
  }

  const p = status?.import?.progress || {}
  const done = status?.import?.status === 'complete'
  const stalled = !!status?.import?.stalled
  // The first pass reads every candidate season to find the real total, so
  // until it lands there is no meaningful matches figure to draw against.
  const planning = running && ['starting', 'seasons'].includes(
    p.phase || status?.import?.phase)
  // The honour-board pass counts players, not matches, so it draws against its
  // own total rather than sitting at whatever the match bar last read.
  const reading = running && (p.phase || status?.import?.phase) === 'notes'
  const plan = p.plan
  const since = status?.import?.seconds_since_progress
  // The one thing that separates a long import from a dead one. A full
  // history is thousands of matches, so the same figures sitting there for a
  // minute is ordinary — how long since it last moved is not.
  const heartbeat = running && since != null
    ? (since < 90 ? ' · still going' : ` · last moved ${Math.round(since / 60)} min ago`)
    : ''

  return (
    <div className="pb-card p-5 mb-8" id="cricketstatz">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 uppercase">
        Import from CricketStatz
      </p>
      <p className="text-[13px] text-pb-dim mb-4 max-w-2xl">
        If your club keeps its records on CricketStatz, paste the address of your
        own stats page and we will bring the lot across — every season, every
        match, every scorecard, and your record book.
      </p>
      <div className="space-y-4">
        <SegButtons
          value={tab}
          onChange={setTab}
          tabs={[
            { key: 'import', label: 'Import' },
            { key: 'records', label: `Record book${records.length ? ` (${records.length})` : ''}` },
            { key: 'history', label: `Past imports${imports.length ? ` (${imports.length})` : ''}` },
          ]}
        />

        {tab === 'import' && (
          <>
            <div className="pb-card p-4 space-y-3">
              <Field label="Your CricketStatz stats page">
                <TextInput
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www2.cricketstatz.com/ss/w?mode=104&club=93931"
                  disabled={running}
                />
              </Field>
              <Caption>
                Open your club's stats page on CricketStatz and copy the address
                from your browser. It carries your club number, which is all we
                need.
              </Caption>
              <div className="flex flex-wrap gap-2">
                <Button onClick={check} disabled={!url || checking || running}>
                  {checking ? 'Checking…' : 'Check this site'}
                </Button>
                {preview && (
                  <Button variant="primary" onClick={start} disabled={starting || running}>
                    {starting ? 'Starting…' : 'Import everything'}
                  </Button>
                )}
              </div>
              {error && <Note toneKey="block">{error}</Note>}
            </div>

            {preview && (
              <div className="pb-card p-4 space-y-3">
                <div className="font-semibold">{preview.club_name || 'That club'}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="Matches found" value={
                    preview.truncated ? `${preview.matches_found}+` : preview.matches_found} />
                  <StatCard
                    label={preview.earliest_at_least ? 'Back to at least' : 'Earliest'}
                    value={preview.earliest || '—'} />
                  <StatCard label="Latest" value={preview.latest || '—'} />
                  <StatCard label="Record boards" value={preview.record_reports} />
                </div>
                {preview.truncated && (
                  <Note>
                    CricketStatz caps one list at 999 matches, so there are more
                    than this — and that list only reaches back as far as those
                    999 go. Your record boards show cricket back to at least{' '}
                    {preview.earliest}. The import checks every season first and
                    will tell you exactly what it found before it pulls anything.
                  </Note>
                )}
                {!!preview.teams?.length && (
                  <Caption>Teams: {preview.teams.slice(0, 8).join(', ')}
                    {preview.teams.length > 8 ? ` and ${preview.teams.length - 8} more` : ''}
                  </Caption>
                )}
                {preview.synced_games > 0 && (
                  <Note toneKey="warn">
                    <div className="font-semibold">
                      You already sync {preview.synced_games.toLocaleString()} matches
                      from Cricket Australia
                      {preview.synced_years?.length
                        ? `, covering ${preview.synced_years[0]}\u2013${preview.synced_years[preview.synced_years.length - 1]}`
                        : ''}.
                    </div>
                    <div className="mt-1">
                      One match must only be counted once, so pick which source
                      is the record for those seasons. Everything before them
                      comes across either way.
                    </div>
                    <div className="mt-2 space-y-2">
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input type="radio" name="cs-synced" className="mt-1"
                               checked={syncedYears === 'skip'}
                               onChange={() => setSyncedYears('skip')} />
                        <span>
                          <b>Leave those seasons to Cricket Australia.</b>{' '}
                          They stay as they are and the import brings across the
                          history your sync cannot reach.
                        </span>
                      </label>
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input type="radio" name="cs-synced" className="mt-1"
                               checked={syncedYears === 'cricketstatz'}
                               onChange={() => setSyncedYears('cricketstatz')} />
                        <span>
                          <b>Bring those seasons across as well.</b>{' '}
                          Any match your sync already holds is matched up and
                          counted once; the rest fill the gaps your sync has.
                          Nothing is deleted either way.
                        </span>
                      </label>
                    </div>
                  </Note>
                )}
                {!!preview.pairing?.imported && (
                  <Note>
                    {`You have already imported ${preview.pairing.imported} match(es). `}
                    {preview.pairing.paired > 0
                      ? `${preview.pairing.paired} of them are the same match as `
                        + `one your Cricket Australia sync holds, so each is `
                        + `counted once, and ${preview.pairing.only_cricketstatz} `
                        + `are matches only CricketStatz has.`
                      : `None of them has been matched to a synced game yet.`}
                    <div className="mt-2">
                      <Button variant="quiet" size="sm" onClick={rebuildPairing}
                              disabled={pairing}>
                        {pairing ? 'Checking…' : 'Check again for duplicates'}
                      </Button>
                    </div>
                  </Note>
                )}
                <Note>
                  A full history can take a while — it reads every match's
                  scorecard one at a time, gently, so we are not hammering
                  someone else's server. You can leave this page; it keeps
                  running.
                </Note>
              </div>
            )}

            {status?.import && (
              <div className="pb-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">
                    {status.import.club_name || 'Import'}
                  </div>
                  <Badge toneKey={
                    status.import.status === 'complete' ? 'ok'
                      : status.import.status === 'error' ? 'block' : 'accent'}>
                    {status.import.status === 'running'
                      ? (PHASES[p.phase || status.import.phase] || 'Working')
                      : status.import.status}
                  </Badge>
                </div>

                {running && (
                  <>
                    <Bar value={planning
                      ? pct(p.candidates_done, p.candidates_total)
                      : reading
                        ? pct(p.notes_done, p.notes_total)
                        : pct(p.matches_done, p.matches_total)} />
                    <Caption>
                      {planning
                        ? `Checking season ${p.candidates_done} of ${p.candidates_total}`
                          + (p.seasons_total ? ` · ${p.seasons_total} played so far` : '')
                        : reading
                          ? `Player ${p.notes_done} of ${p.notes_total}`
                            + (p.awards ? ` · ${p.awards} honours found` : '')
                          : `Season ${p.seasons_done} of ${p.seasons_total}`
                            + (p.current_season ? ` (${p.current_season})` : '')}
                      {!planning && !reading && p.matches_total
                        ? ` · ${p.matches_done} of ${p.matches_total} matches`
                        : ''}
                      {heartbeat}
                    </Caption>
                    {stalled && (
                      <Note toneKey="block">
                        This import has not moved for {Math.round(
                          (status.import.seconds_since_progress || 0) / 60)} minutes,
                        so it has most likely stopped. Everything it brought
                        across before then has been kept. Stop it and start
                        again — the matches already in are recognised, so it
                        will not double anything.
                      </Note>
                    )}
                  </>
                )}

                {!!p.replaced_synced_years?.length && (
                  <Caption>
                    {/* A season is matched up as its own matches land, not at
                        the end of the run, so while it is going this says how
                        far through that it is — a club watching a record board
                        can see which years have been checked. */}
                    {`${p.replaced_synced_years.length} season(s) you also sync `}
                    {running
                      ? `checked for duplicates as they come across (${p.replaced_done || 0} of ${p.replaced_synced_years.length} so far) `
                      : `checked for duplicates `}
                    {`(${p.replaced_synced_years[0]}\u2013${p.replaced_synced_years[p.replaced_synced_years.length - 1]}). `}
                    {`${p.paired || 0} matched a synced game and are counted once; `}
                    {`${p.only_cricketstatz || 0} are matches only CricketStatz has.`}
                  </Caption>
                )}
                {!!p.skipped_synced_years?.length && (
                  <Caption>
                    {`${p.skipped_synced_years.length} season(s) already covered by `}
                    {`your Cricket Australia sync were left out `}
                    {`(${p.skipped_synced_years[0]}\u2013${p.skipped_synced_years[p.skipped_synced_years.length - 1]}), `}
                    {`so those matches are not counted twice.`}
                  </Caption>
                )}
                {plan && (
                  <Caption>
                    {`Found ${plan.season_count} seasons you played`}
                    {plan.earliest ? `, ${plan.earliest} to ${plan.latest}` : ''}
                    {` · ${plan.match_count} matches`}
                    {running ? ` · about ${plan.estimated_minutes} minutes` : ''}
                  </Caption>
                )}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <StatCard label="Matches" value={p.matches_done || 0} />
                  <StatCard label="Scorecards" value={p.scorecards || 0} />
                  <StatCard label="Players" value={p.players || 0} />
                  <StatCard label="Record boards" value={p.records || 0} />
                  <StatCard label="Honours" value={p.awards || 0} />
                </div>

                {running && (
                  <div>
                    <Button variant="quiet-danger" size="sm"
                            onClick={() => stop(status.import.id)}>
                      Stop this import
                    </Button>
                  </div>
                )}
                {/* The honour board is the LAST phase of an import, so it is
                    the first thing lost when a run is cut off. Offered on its
                    own rather than making a club re-pull every scorecard for a
                    pass that needs none of them. */}
                {!running && !p.awards && (
                  <div>
                    <Button variant="quiet" size="sm" onClick={readNotes}
                            disabled={readingNotes}>
                      {readingNotes ? 'Reading…' : 'Read player notes for awards'}
                    </Button>
                    <Caption>
                      {'Reads each player\u2019s CricketStatz notes and files '}
                      {'what they say \u2014 life membership, caps, trophies, '}
                      {'captaincies \u2014 onto their honour board. No matches '}
                      {'are re-pulled.'}
                    </Caption>
                  </div>
                )}
                {status.import.error && <Note toneKey="block">{status.import.error}</Note>}
                {done && (
                  <Note toneKey="ok">
                    Your history is in. It now shows on your players' profiles,
                    your records and everywhere else the rest of your stats do.
                  </Note>
                )}
                {!!p.notes?.length && (
                  <details>
                    <summary className="cursor-pointer text-sm">
                      {p.notes.length} thing{p.notes.length === 1 ? '' : 's'} we
                      could not read
                    </summary>
                    <ul className="mt-2 text-sm space-y-1">
                      {p.notes.slice(0, 50).map((n, i) => <li key={i}>{n}</li>)}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </>
        )}

        {tab === 'records' && (
          records.length === 0
            ? <Empty>Your record book arrives with your first import.</Empty>
            : <RecordBook records={records} />
        )}

        {tab === 'history' && (
          imports.length === 0
            ? <Empty>Nothing imported yet.</Empty>
            : (
              <TableWrap>
                <TableHead cols={HISTORY_COLS} minWidth={HISTORY_MIN_W}>
                  <Cell head first>Club</Cell>
                  <Cell head>Started</Cell>
                  <Cell head>Status</Cell>
                  <Cell head num>Matches</Cell>
                  <Cell head last />
                </TableHead>
                {imports.map((i) => (
                  <TableRow key={i.id} cols={HISTORY_COLS} minWidth={HISTORY_MIN_W}>
                    <Cell first>{i.club_name || i.club_id}</Cell>
                    <Cell>{i.started_at ? new Date(i.started_at).toLocaleDateString() : '—'}</Cell>
                    <Cell>
                      <Badge toneKey={
                        i.undone_at ? 'calm'
                          : i.status === 'complete' ? 'ok'
                            : i.status === 'error' ? 'block' : 'accent'}>
                        {i.undone_at ? 'undone' : i.status}
                      </Badge>
                    </Cell>
                    <Cell num>{i.matches}</Cell>
                    <Cell last>
                      {!i.undone_at && i.status !== 'running' && (
                        <Button variant="quiet-danger" size="sm" onClick={() => undo(i.id)}
                                disabled={undoing === i.id}>
                          {undoing === i.id ? 'Removing…' : 'Undo'}
                        </Button>
                      )}
                    </Cell>
                  </TableRow>
                ))}
              </TableWrap>
            )
        )}
      </div>
    </div>
  )
}

function RecordBook({ records }) {
  const sections = [...new Set(records.map((r) => r.section || 'other'))]
  const [open, setOpen] = useState(records[0]?.mode ?? null)
  return (
    <div className="space-y-4">
      <Note>
        These are your records as CricketStatz worked them out, kept as they
        were. BetterCricket also works out its own from the scorecards it now
        holds, so the two can be compared rather than silently blended.
      </Note>
      {sections.map((section) => (
        <div key={section} className="space-y-2">
          <div className="text-xs uppercase tracking-wide opacity-70">{section}</div>
          {records.filter((r) => (r.section || 'other') === section).map((r) => (
            <div key={r.mode} className="pb-card p-3">
              <button
                type="button"
                className="w-full text-left flex items-center justify-between gap-2"
                onClick={() => setOpen(open === r.mode ? null : r.mode)}
                aria-expanded={open === r.mode}
              >
                <span className="font-medium">{r.title}</span>
                <span className="text-sm opacity-70">{r.row_count}</span>
              </button>
              {open === r.mode && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr>
                        {(r.headers || []).map((h, i) => (
                          <th key={i} className="text-left pr-3 pb-1 font-medium opacity-70">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(r.rows || []).slice(0, 50).map((row, i) => (
                        <tr key={i}>
                          {(row.values || []).map((v, j) => (
                            <td key={j} className="pr-3 py-1 whitespace-nowrap">{v}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
