import { useState, useMemo, useRef, useCallback } from 'react'
import { api } from '../../lib/api'

// The scorecard CSV import, with the review step the historical-stats wizard
// has. The strict endpoint underneath refuses a row naming a season, grade or
// player the club does not already hold — which for a club bringing in a whole
// history is every row — so this is where the admin says what to create.
//
// Seasons and grades default to being created: an exact name matches or it
// does not, and there is no identity question to get wrong. A PLAYER never
// does. Two people can share a name, and this app already carries the scars of
// a matcher putting a father and son on one record, so an unmatched name is
// proposed and waits for an answer.

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'
const BTN_PRIMARY = 'inline-flex items-center px-4 py-2 bg-pb-accent text-pb-on-accent text-sm font-semibold rounded hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed'
const BTN_SECONDARY = 'inline-flex items-center px-3 py-1.5 border pb-hairline text-pb-text text-xs rounded hover:bg-pb-surface2 disabled:opacity-40'
const CAP = 'font-mono text-[10px] uppercase tracking-wide text-pb-dim'

const TONE = {
  exact: 'text-pb-positive',
  manual: 'text-pb-positive',
  matched: 'text-pb-positive',
  fuzzy: 'text-amber-400',
  new: 'text-pb-accent-ink',
  skip: 'text-pb-dim',
  ambiguous: 'text-red-400',
  none: 'text-red-400',
  ungraded: 'text-pb-dim',
}

// Every state is a word as well as a colour — a verdict told apart by colour
// alone is unreadable for a good share of readers.
const WORD = {
  exact: 'MATCHED', manual: 'CHOSEN', matched: 'MATCHED', fuzzy: 'CHECK THIS',
  new: 'WILL BE CREATED', skip: 'LEFT OUT', ambiguous: 'TWO PLAYERS SHARE THIS NAME',
  none: 'NEEDS AN ANSWER', ungraded: 'NO GRADE',
}

function Tag({ status }) {
  return <span className={`font-mono text-[10px] ${TONE[status] || 'text-pb-dim'}`}>{WORD[status] || (status || '').toUpperCase()}</span>
}

function Figure({ label, value, tone }) {
  return (
    <div className="px-3 py-2 rounded bg-pb-surface2 border pb-hairline">
      <div className={CAP}>{label}</div>
      <div className={`text-xl font-semibold ${tone || 'text-pb-text'}`}>{value}</div>
    </div>
  )
}

function SheetNote({ sheet }) {
  if (!sheet) return null
  const era = sheet.first_year
    ? (sheet.first_year === sheet.last_year ? `${sheet.first_year}` : `${sheet.first_year}–${sheet.last_year}`)
    : null
  return (
    <span className="text-[11px] text-pb-dim">
      {sheet.games} in the sheet · {sheet.runs} runs · {sheet.wickets} wkts{era ? ` · ${era}` : ''}
    </span>
  )
}

// The overwrite / discard choice, made before the import runs — the same call
// the CricketStatz importer offers for a synced season, made here per match.
// The projection under each option is worked out from the review's own
// duplicate split, so changing the choice costs no server round trip.
function DuplicatePolicy({ dupMode, setDupMode, duplicates }) {
  const dup = duplicates || { total: 0, manual: 0, synced: 0 }
  const none = !dup.total

  let projection
  if (none) {
    projection = 'None of these matches are already in BetterCricket, so this makes no difference to this import.'
  } else if (dupMode === 'skip') {
    projection = `${dup.total} match${dup.total === 1 ? '' : 'es'} already in BetterCricket will be left as ${dup.total === 1 ? 'it is' : 'they are'} and skipped.`
  } else {
    const bits = []
    if (dup.manual) bits.push(`${dup.manual} existing match${dup.manual === 1 ? ' will be' : 'es will be'} overwritten`)
    if (dup.synced) bits.push(`${dup.synced} already synced from Cricket Australia can’t be overwritten and will be skipped`)
    projection = bits.join('; ') + '.'
  }

  const Option = ({ value, title, body }) => (
    <label className={`flex gap-2.5 items-start p-3 rounded border cursor-pointer ${dupMode === value ? 'border-pb-accent bg-pb-accent/5' : 'pb-hairline hover:bg-pb-surface2'}`}>
      <input type="radio" name="dup-mode" className="mt-0.5 accent-pb-accent" checked={dupMode === value} onChange={() => setDupMode(value)} />
      <span>
        <span className="block text-sm font-medium text-pb-text">{title}</span>
        <span className="block text-[11px] text-pb-dim mt-0.5">{body}</span>
      </span>
    </label>
  )

  return (
    <section className="border pb-hairline rounded-lg bg-pb-surface p-4 space-y-2.5">
      <div>
        <h3 className="text-sm font-semibold text-pb-text">Matches already in BetterCricket</h3>
        <p className="text-[11px] text-pb-dim mt-0.5">
          A match is recognised as one you already have when it shares a date and opponent with an
          existing record — a match with no date or opponent in the sheet is always brought in as new.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Option
          value="skip"
          title="Only import new matches"
          body="Any match already in BetterCricket is never overwritten — duplicates in the sheet are discarded, and only matches you don’t already have are brought in."
        />
        <Option
          value="overwrite"
          title="Overwrite existing matches"
          body="A match already in BetterCricket is replaced by the sheet’s version. Synced Cricket Australia matches can’t be overwritten and are skipped. Undo the whole import from Audit & Undo."
        />
      </div>
      <p className={`text-xs ${none ? 'text-pb-dim' : 'text-pb-accent-ink'}`}>{projection}</p>
    </section>
  )
}

export default function ManualGamesImportWizard({ onDone }) {
  // The TOKEN, not the sheet. The preview parses the file once and holds the
  // rows server-side for an hour; this screen carries a handle to them and the
  // overrides, which is a few hundred bytes however big the archive is.
  //
  // It used to hold the parsed rows and post every one of them back on BOTH
  // later steps — and `resolve` fires again on every override change below, so
  // a club's whole history went up the wire once per player matched, season
  // picked and grade named. Measured on a 33 MB, 182,154-row sheet: those rows
  // as a JSON body are 145.6 MB, because all 33 column names repeat on every
  // row. The server-side work was never the problem (the same sheet resolves
  // in 1.9s); the upload was.
  const [token, setToken] = useState(null)
  const [filename, setFilename] = useState('')
  const [unknown, setUnknown] = useState([])
  const [review, setReview] = useState(null)
  const [overrides, setOverrides] = useState({ players: {}, seasons: {}, grades: {} })
  // What to do with a match already in BetterCricket. 'skip' is the safe
  // default — it never touches what the club already has; 'overwrite' replaces
  // an existing manual match with the sheet's version (undoable). The choice is
  // local: changing it never re-hits the server, since the review already
  // reports how many matches are duplicates and the outcome is worked out from
  // that split.
  const [dupMode, setDupMode] = useState('skip')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileRef = useRef(null)

  const resolve = useCallback(async (nextOverrides, nextToken = token, nextFile = filename) => {
    setBusy('resolve'); setError('')
    try {
      const res = await api.adminResolveManualGames({
        filename: nextFile,
        token: nextToken,
        player_overrides: nextOverrides.players,
        season_overrides: nextOverrides.seasons,
        grade_overrides: nextOverrides.grades,
      })
      setReview(res)
    } catch (e) {
      setError(e.message || 'Could not read that sheet.')
    } finally { setBusy('') }
  }, [token, filename])

  async function pickFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy('preview'); setError(''); setResult(null); setReview(null)
    try {
      const prev = await api.adminPreviewManualGames(file)
      setToken(prev.token); setFilename(prev.filename || file.name); setUnknown(prev.unknown_columns || [])
      const fresh = { players: {}, seasons: {}, grades: {} }
      setOverrides(fresh)
      await resolve(fresh, prev.token, prev.filename || file.name)
    } catch (err) {
      setError(err.message || 'Could not read that file.')
      setToken(null)
    } finally { setBusy('') }
  }

  function setOverride(kind, key, value) {
    const next = { ...overrides, [kind]: { ...overrides[kind], [key]: value } }
    setOverrides(next)
    resolve(next)
  }

  // The bulk action a club importing a whole history actually needs. It is a
  // deliberate press, not a default: the screen never ticks 346 people on
  // somebody's behalf.
  function createAllUnmatched() {
    const players = { ...overrides.players }
    for (const p of review?.players || []) {
      if (!p.player_id && p.status !== 'skip' && p.status !== 'ambiguous') players[p.raw_name] = '__new__'
    }
    const next = { ...overrides, players }
    setOverrides(next)
    resolve(next)
  }

  async function commit() {
    setBusy('commit'); setError('')
    try {
      const out = await api.adminCommitManualGames({
        filename,
        token,
        player_overrides: overrides.players,
        season_overrides: overrides.seasons,
        grade_overrides: overrides.grades,
        duplicate_mode: dupMode,
      })
      // The token is spent once its sheet has landed — the server drops the
      // staged rows in the same transaction as the games, so holding on to it
      // would only offer to import the same archive twice.
      setResult(out); setToken(null); setReview(null)
      if (fileRef.current) fileRef.current.value = ''
      // Told after the result is on screen, and the parent must not remount
      // this component in response — see the stable key where it is mounted.
      onDone?.()
    } catch (e) {
      setError(e.message || 'The import did not go through.')
    } finally { setBusy('') }
  }

  const unresolved = review?.totals?.players_unresolved || 0
  const willCreate = review?.will_create || {}
  // The same rule the server uses for `players_unresolved` — a name already
  // answered as "create" or "leave out" is not still outstanding, and a button
  // offering to answer it again would never go away.
  const unmatchedCount = useMemo(
    () => (review?.players || []).filter(
      p => !p.player_id && !['new', 'skip', 'ambiguous'].includes(p.status)).length,
    [review])

  return (
    <div className="space-y-5">
      <div className="border pb-hairline rounded-lg p-4 bg-pb-surface">
        <h3 className="text-base font-semibold text-pb-text mb-1">Import scorecards from a spreadsheet</h3>
        <p className="text-sm text-pb-dim mb-3">
          One row per player per match. Seasons, grades and players the club does not
          hold yet are created as part of the import — you say which, before anything
          is written, and Audit &amp; Undo takes the whole thing back.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={pickFile}
                 className="text-sm text-pb-dim file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-pb-surface2 file:text-pb-text file:text-xs" />
          <a className={BTN_SECONDARY} href="/api/club-admin/manual-entries/games/template.csv">Download the template</a>
        </div>
        {busy === 'preview' && <p className="text-xs text-pb-dim mt-2">Reading the sheet…</p>}
        {!!unknown.length && (
          <p className="text-xs text-amber-400 mt-2">
            Ignoring {unknown.length} column(s) this import has no use for: {unknown.join(', ')}
          </p>
        )}
      </div>

      {error && <div className="border border-red-400/40 bg-red-500/10 text-red-300 text-sm rounded p-3">{error}</div>}

      {result && (
        <div className="border pb-hairline rounded-lg p-4 bg-pb-surface">
          <h3 className="text-base font-semibold text-pb-text mb-2">Imported</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Figure label="New matches" value={result.games_created} />
            <Figure label="Seasons created" value={result.seasons_created} />
            <Figure label="Grades created" value={result.grades_created} />
            <Figure label="Players created" value={result.players_created} />
          </div>
          {(result.games_overwritten > 0 || result.games_ignored > 0) && (
            <div className="grid grid-cols-2 gap-2 mt-2">
              {result.games_overwritten > 0 && (
                <Figure label="Overwritten" value={result.games_overwritten} tone="text-pb-accent-ink" />
              )}
              {result.games_ignored > 0 && (
                <Figure label="Already present — ignored" value={result.games_ignored} tone="text-pb-dim" />
              )}
            </div>
          )}
          {result.games_ignored_synced > 0 && (
            <p className="text-xs text-pb-dim mt-3">
              {result.games_ignored_synced} of the ignored match{result.games_ignored_synced === 1 ? ' is' : 'es are'} already
              synced from Cricket Australia, which a spreadsheet import can’t overwrite.
            </p>
          )}
          {result.errors > 0 && (
            <p className="text-xs text-amber-400 mt-3">
              {result.errors} row(s) could not be read and their matches were left out.
            </p>
          )}
          <p className="text-xs text-pb-dim mt-3">
            Undo the whole import — the games and everything it created — from Audit &amp; Undo.
          </p>
        </div>
      )}

      {review && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Figure label="Matches" value={review.games} />
            <Figure label="New seasons" value={willCreate.seasons || 0} tone={willCreate.seasons ? 'text-pb-accent-ink' : undefined} />
            <Figure label="New grades" value={willCreate.grades || 0} tone={willCreate.grades ? 'text-pb-accent-ink' : undefined} />
            <Figure label="New players" value={willCreate.players || 0} tone={willCreate.players ? 'text-pb-accent-ink' : undefined} />
          </div>

          {(review.warnings || []).map((w, i) => (
            <div key={i} className="border border-amber-400/40 bg-amber-400/10 text-amber-200 text-sm rounded p-3">{w}</div>
          ))}

          <section className="border pb-hairline rounded-lg bg-pb-surface">
            <header className="px-4 py-3 border-b pb-hairline-b">
              <h3 className="text-sm font-semibold text-pb-text">Seasons</h3>
            </header>
            <div className="divide-y divide-pb-hairline">
              {(review.seasons || []).map(s => (
                <div key={s.raw_label} className="px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-sm text-pb-text font-medium min-w-[10rem]">{s.raw_label}</span>
                  <Tag status={s.status} />
                  {s.matched_name && s.matched_name !== s.raw_label && (
                    <span className="text-[11px] text-pb-dim">→ {s.matched_name}</span>
                  )}
                  <select
                    className={`${INPUT_CLS} ml-auto max-w-xs`}
                    value={overrides.seasons[s.raw_label] || (s.season_id ? s.season_id : '__new__')}
                    onChange={e => setOverride('seasons', s.raw_label, e.target.value)}
                  >
                    <option value="__new__">Create “{s.raw_label}”</option>
                    {(s.candidates || []).map(c => (
                      <option key={c.season_id} value={c.season_id}>Use {c.name}</option>
                    ))}
                    {s.season_id && !(s.candidates || []).some(c => c.season_id === s.season_id) && (
                      <option value={s.season_id}>Use {s.matched_name}</option>
                    )}
                  </select>
                </div>
              ))}
            </div>
          </section>

          <section className="border pb-hairline rounded-lg bg-pb-surface">
            <header className="px-4 py-3 border-b pb-hairline-b">
              <h3 className="text-sm font-semibold text-pb-text">Grades</h3>
              <p className="text-[11px] text-pb-dim mt-0.5">
                A grade belongs to one season, so a label used across several seasons
                is created once in each of them.
              </p>
            </header>
            <div className="divide-y divide-pb-hairline">
              {(review.grades || []).map(g => (
                <div key={g.raw_label} className="px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-sm text-pb-text font-medium min-w-[10rem]">{g.raw_label}</span>
                  <Tag status={g.status} />
                  <span className="text-[11px] text-pb-dim">
                    {(g.used_in_seasons || []).length} season{(g.used_in_seasons || []).length === 1 ? '' : 's'}
                  </span>
                  <select
                    className={`${INPUT_CLS} ml-auto max-w-xs`}
                    value={overrides.grades[g.raw_label] || (g.will_create ? '__new__' : (g.grade_name || '__none__'))}
                    onChange={e => setOverride('grades', g.raw_label, e.target.value)}
                  >
                    <option value="__new__">Create “{g.raw_label}”</option>
                    {(review.grade_options || []).map(n => (
                      <option key={n} value={n}>Use {n}</option>
                    ))}
                    <option value="__none__">No grade — leave these matches ungraded</option>
                  </select>
                </div>
              ))}
              {!(review.grades || []).length && (
                <p className="px-4 py-3 text-sm text-pb-dim">The sheet names no grades.</p>
              )}
            </div>
          </section>

          <section className="border pb-hairline rounded-lg bg-pb-surface">
            <header className="px-4 py-3 border-b pb-hairline-b flex flex-wrap items-center gap-3">
              <div>
                <h3 className="text-sm font-semibold text-pb-text">Players</h3>
                <p className="text-[11px] text-pb-dim mt-0.5">
                  {review.totals.players_matched} matched · {review.totals.players_new} to create
                  {unresolved ? ` · ${unresolved} still to answer` : ''}
                </p>
              </div>
              {unmatchedCount > 0 && (
                <button className={`${BTN_SECONDARY} ml-auto`} onClick={createAllUnmatched} disabled={!!busy}>
                  Create all {unmatchedCount} as new players
                </button>
              )}
            </header>
            <div className="divide-y divide-pb-hairline max-h-[28rem] overflow-y-auto">
              {(review.players || []).map(p => (
                <div key={p.raw_name} className="px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-sm text-pb-text font-medium min-w-[10rem]">{p.raw_name}</span>
                  <Tag status={p.status} />
                  <SheetNote sheet={p.sheet} />
                  <select
                    className={`${INPUT_CLS} ml-auto max-w-xs`}
                    value={overrides.players[p.raw_name] || (p.player_id ? p.player_id : (p.status === 'new' ? '__new__' : ''))}
                    onChange={e => setOverride('players', p.raw_name, e.target.value)}
                  >
                    <option value="">— choose —</option>
                    <option value="__new__">Create “{p.raw_name}”</option>
                    {(p.candidates || []).map(c => (
                      <option key={c.player_id} value={c.player_id}>
                        Use {c.name}{c.confidence ? ` (${Math.round(c.confidence * 100)}%)` : ''}
                      </option>
                    ))}
                    {p.player_id && !(p.candidates || []).some(c => c.player_id === p.player_id) && (
                      <option value={p.player_id}>Use {p.matched_name}</option>
                    )}
                    <option value="__skip__">Leave them out</option>
                  </select>
                </div>
              ))}
            </div>
          </section>

          <DuplicatePolicy
            dupMode={dupMode}
            setDupMode={setDupMode}
            duplicates={review.duplicates}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button className={BTN_PRIMARY} onClick={commit} disabled={!!busy || unresolved > 0}>
              {busy === 'commit' ? 'Importing…' : `Import ${review.games} match${review.games === 1 ? '' : 'es'}`}
            </button>
            {unresolved > 0 && (
              <span className="text-xs text-amber-400">
                {unresolved} name{unresolved === 1 ? '' : 's'} still need an answer.
              </span>
            )}
            {busy === 'resolve' && <span className="text-xs text-pb-dim">Checking…</span>}
          </div>
        </>
      )}
    </div>
  )
}
