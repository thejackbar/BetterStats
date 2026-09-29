import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner } from '../../lib/presskit'

// A club's competitions: name them, order them, and say which grade was
// played in which. Shared by BetterCricket's Grades & Competitions screen and
// BetterFootball's Merge Grades screen. Both backends serve the same
// /admin/competitions endpoints; only the copy and the grouping offer differ,
// so they come in as props.
// ── Competitions ─────────────────────────────────────────────────────────
//
// A club plays in several competitions, sometimes several run by ONE
// association. Cricket Australia publishes the ASSOCIATION on every grade and
// no competition at all (see services/competitions.py for what was checked),
// so a competition here is the club's own named group of grades, seeded one
// per association.
//
// Most clubs never need to touch this: their grades come pre-grouped by the
// association, which is already the right answer for a club that plays one
// association's competitions. It exists for the club the association alone
// cannot separate — Veterans Cricket Victoria runs the Border Cup, an Over
// 60s competition and the Echuca divisions, and reading all three as one is
// the reason this was built.
export default function CompetitionManager({ renderGrouping = null, intro = null, emptyText = null }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  // Deliberately does NOT put the panel back into its loading state. The
  // spinner belongs to the FIRST load; a refresh after an edit swaps the data
  // in place. Blanking the section would unmount the grouping panel below,
  // which is how the finished job's own result went missing the moment it
  // reported — caught by the browser suite, not by reading this.
  function load() {
    api.adminCompetitions()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])
  // A link to /admin/grades#competitions (the sidebar, the blog, a guide)
  // lands on the panel rather than the top of a long page. Waits for the data
  // so there is something to scroll to.
  const { hash } = useLocation()
  useEffect(() => {
    if (loading || hash !== '#competitions') return
    document.getElementById('competitions')?.scrollIntoView({ block: 'start' })
  }, [loading, hash])

  async function act(fn) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <PbSpinner message="Loading competitions…" />

  const competitions = data?.competitions || []
  const grades = data?.grades || []
  const associations = data?.associations || []
  const ungrouped = grades.filter(g => !g.competition_id)

  // THE ORDER HERE IS THE ORDER EVERY COMPETITION PILL READS IN. The public
  // filter row, the club's Competitions page and every player's Competitions
  // tab all read `list_competitions`, which sorts on display_order — so until
  // a club sets one, they came out in whatever order the sync first met them.
  // A swap sends the WHOLE list, the way the grade reorder and the plan tree
  // already do, so the server stamps positions over every row and a foreign
  // or stale id cannot leave a gap in the numbering.
  function move(index, delta) {
    const target = index + delta
    if (target < 0 || target >= competitions.length) return
    const ids = competitions.map(c => c.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    act(() => api.adminReorderCompetitions(ids))
  }

  return (
    <div className="mb-10" id="competitions">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
        Competitions <span className="text-pb-faintest">({competitions.length})</span>
      </p>
      <p className="text-pb-faint text-sm mb-4 leading-relaxed">
        {intro || (
          <>Which competition each grade was played in. Grades are grouped
          automatically by the association that runs them, which is right for most
          clubs. Split one here when an association runs several competitions you
          want to read separately — a cup alongside the regular season, say.</>
        )}
        {competitions.length > 1 && (
          <> The order below is the order the Competition filter lists them in, on
          every stats page and player profile. Use the arrows to change it.</>
        )}
      </p>

      {error && <p className="text-pb-red text-sm mb-3">{error}</p>}

      {renderGrouping && renderGrouping(load)}

      {!competitions.length && (
        <div className="border pb-hairline rounded p-4 mb-4">
          <p className="text-sm text-pb-dim mb-3">
            {emptyText ? emptyText(associations) : associations.length
              ? `Nothing grouped yet. Your grades come from ${associations.length} ${associations.length === 1 ? 'association' : 'associations'}.`
              : 'No association recorded on your grades yet. Your next sync fetches them and groups your grades automatically; the button above does it now.'}
          </p>
          {associations.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => api.adminSeedCompetitions())}
              className="px-3 py-2 text-xs font-mono tracking-wide2 uppercase rounded bg-pb-accent/15 text-pb-accent hover:bg-pb-accent/25 disabled:opacity-50"
            >
              Group my grades
            </button>
          )}
        </div>
      )}

      {competitions.map((c, i) => {
        const held = grades.filter(g => g.competition_id === c.id)
        return (
          <div key={c.id} className="border pb-hairline rounded p-4 mb-3" data-testid="competition-card">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              {competitions.length > 1 && (
                <div className="flex flex-col gap-0.5 shrink-0 -ml-1">
                  <button type="button" disabled={busy || i === 0}
                    onClick={() => move(i, -1)}
                    aria-label={`Move ${c.name} up`}
                    className="w-6 h-5 text-[11px] leading-none rounded text-pb-dim hover:text-pb-text hover:bg-pb-surface2 disabled:opacity-30 disabled:hover:bg-transparent"
                  >▲</button>
                  <button type="button" disabled={busy || i === competitions.length - 1}
                    onClick={() => move(i, 1)}
                    aria-label={`Move ${c.name} down`}
                    className="w-6 h-5 text-[11px] leading-none rounded text-pb-dim hover:text-pb-text hover:bg-pb-surface2 disabled:opacity-30 disabled:hover:bg-transparent"
                  >▼</button>
                </div>
              )}
              <div className="min-w-0 flex-1">
                {renaming === c.id ? (
                  <form
                    onSubmit={e => {
                      e.preventDefault()
                      act(() => api.adminRenameCompetition(c.id, renameValue))
                        .then(() => setRenaming(null))
                    }}
                    className="flex items-center gap-2"
                  >
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={e => setRenameValue(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Escape') setRenaming(null) }}
                      className="bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-2 py-1"
                    />
                    <button type="submit" disabled={busy} className="text-xs font-mono uppercase text-pb-accent">Save</button>
                    <button type="button" onClick={() => setRenaming(null)} className="text-xs font-mono uppercase text-pb-faint">Cancel</button>
                  </form>
                ) : (
                  <h3 className="text-pb-text font-semibold text-[15px]">{c.name}</h3>
                )}
                <p className="text-pb-faint text-xs mt-0.5">
                  {c.association_name ? `${c.association_name} · ` : ''}
                  {held.length} {held.length === 1 ? 'grade' : 'grades'}
                  {c.season_count ? ` · ${c.season_count} season${c.season_count === 1 ? '' : 's'}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => { setRenaming(c.id); setRenameValue(c.name) }}
                  className="text-xs font-mono uppercase tracking-wide2 text-pb-faint hover:text-pb-text"
                >
                  Rename
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    // Names what actually goes, because it is far less than a
                    // reader would fear: the grades and every game, run and
                    // wicket in them are untouched, they simply stop being
                    // grouped.
                    if (!window.confirm(
                      `Delete "${c.name}"?\n\nIts ${held.length} grade${held.length === 1 ? '' : 's'} and every game in them are kept — they just stop being grouped, and you can put them in another competition afterwards.`
                    )) return
                    act(() => api.adminDeleteCompetition(c.id))
                  }}
                  className="text-xs font-mono uppercase tracking-wide2 text-pb-faint hover:text-pb-red"
                >
                  Delete
                </button>
              </div>
            </div>
            {held.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {held.map(g => (
                  <GradeCompetitionRow
                    key={g.name}
                    grade={g}
                    competitions={competitions}
                    busy={busy}
                    onChange={id => act(() => api.adminAssignGradeToCompetition(g.name, id))}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}

      {ungrouped.length > 0 && (
        <div className="border pb-hairline rounded p-4 mb-3">
          {/* Shown, never dropped — the same rule the un-grouped row on every
              by-competition breakdown follows. A grade here still counts in
              every unfiltered figure; it just has no competition to be found
              under. */}
          <h3 className="text-pb-text font-semibold text-[15px]">Not in a competition</h3>
          <p className="text-pb-faint text-xs mt-0.5 mb-3">
            These still count in every unfiltered figure. They simply have no
            competition to be found under.
          </p>
          <div className="space-y-1.5">
            {ungrouped.map(g => (
              <GradeCompetitionRow
                key={g.name}
                grade={g}
                competitions={competitions}
                busy={busy}
                onChange={id => act(() => api.adminAssignGradeToCompetition(g.name, id))}
              />
            ))}
          </div>
        </div>
      )}

      <form
        onSubmit={e => {
          e.preventDefault()
          if (!newName.trim()) return
          act(() => api.adminCreateCompetition(newName.trim())).then(() => setNewName(''))
        }}
        className="flex items-center gap-2 mt-4"
      >
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          placeholder="New competition name"
          className="flex-1 bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
        />
        <button
          type="submit"
          disabled={busy || !newName.trim()}
          className="px-3 py-2 text-xs font-mono tracking-wide2 uppercase rounded bg-pb-accent/15 text-pb-accent hover:bg-pb-accent/25 disabled:opacity-50 shrink-0"
        >
          Add
        </button>
      </form>
    </div>
  )
}

// One grade, and which competition it is in. Assigning moves EVERY season row
// of that grade name at once — a grade is one thing to a club across every
// season it ran, the same rule the category and display-order editors above
// already follow.
function GradeCompetitionRow({ grade, competitions, busy, onChange }) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-sm text-pb-dim flex-1 min-w-0 truncate">
        {grade.name}
        {grade.association_name && (
          <span className="text-pb-faintest text-xs"> · {grade.association_name}</span>
        )}
        {/* A grade whose season rows sit in more than one competition is a real
            state (a grade that changed association), so it is reported rather
            than silently showing whichever row sorted first. */}
        {grade.mixed && (
          <span className="text-pb-faint text-xs"> · split across competitions</span>
        )}
      </span>
      <select
        value={grade.competition_id || ''}
        disabled={busy}
        onChange={e => onChange(e.target.value || null)}
        className="bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent shrink-0"
      >
        <option value="">— not in a competition —</option>
        {competitions.map(c => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>
    </div>
  )
}

