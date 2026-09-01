import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { PbSpinner } from '../../lib/presskit'

function GradePicker({ grades, value, onChange, placeholder, exclude }) {
  return (
    <select
      value={value || ''}
      onChange={e => onChange(e.target.value || null)}
      className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
    >
      <option value="">{placeholder}</option>
      {grades
        .filter(g => g.grade_name !== exclude)
        .map(g => (
          <option key={g.grade_name} value={g.grade_name}>
            {g.display_name} ({g.games} games · {g.runs} runs)
          </option>
        ))}
    </select>
  )
}

function MergeBuilder({ orgId, grades, onMerged }) {
  const [alias, setAlias] = useState(null)
  const [canonical, setCanonical] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const canMerge = alias && canonical && alias !== canonical

  async function handleMerge() {
    if (!canMerge) return
    setBusy(true)
    setError(null)
    try {
      await api.mergeGrades(orgId, alias, canonical)
      setAlias(null)
      setCanonical(null)
      onMerged()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-5 mb-8">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge Grades</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Use this when one grade is sponsored or renamed across seasons (e.g. "One Day Grade 3" and "One Day Grade 3 - East" are actually the same).
        Stats will be combined in the player by-grade view.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Variant to merge</label>
          <GradePicker grades={grades} value={alias} onChange={setAlias} placeholder="— Select grade —" exclude={canonical} />
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Merge into (keep this name)</label>
          <GradePicker grades={grades} value={canonical} onChange={setCanonical} placeholder="— Select canonical grade —" exclude={alias} />
        </div>
      </div>
      {alias && canonical && alias === canonical && (
        <p className="font-mono text-[11px] text-pb-amber mb-3">Pick two different grades.</p>
      )}
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <button
        onClick={handleMerge}
        disabled={!canMerge || busy}
        className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
        style={{ background: 'var(--pb-accent)' }}
      >
        {busy ? 'Merging…' : `Merge ${alias || '…'} into ${canonical || '…'}`}
      </button>
    </div>
  )
}

const GRADE_CATEGORIES = [
  ['senior', "Men's"],
  ['junior', 'Juniors'],
  ['womens', "Women's"],
  ['masters', 'Masters'],
  ['mixed', 'Mixed / Other'],
]

const MATCH_FORMATS = [
  ['two_day', 'Two Day'],
  ['one_day', 'One Day'],
  ['t20', 'T20'],
]

// A grade is several things at once — "Women's T20 Grade 2" is a women's grade
// AND a T20 grade — so each axis is a set of toggles rather than a dropdown.
// Clearing every chip puts the row back on its suggestion, which is why the
// empty state reads as a suggestion rather than as "none".
function TagPicker({ options, value, suggested, confirmed, disabled, onChange, emptyHint }) {
  const picked = value || []
  const shown = confirmed ? picked : (suggested || [])
  function flip(key) {
    const next = shown.includes(key)
      ? shown.filter(k => k !== key)
      : [...shown, key]
    onChange(options.map(([k]) => k).filter(k => next.includes(k)))
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {options.map(([key, label]) => {
        const on = shown.includes(key)
        return (
          <button
            key={key}
            onClick={() => flip(key)}
            disabled={disabled}
            aria-pressed={on}
            className={`font-mono text-[10px] tracking-wide2 rounded px-2 py-1 border transition-colors disabled:opacity-50 ${
              on
                ? 'text-pb-accent border-pb-accent/40 bg-pb-accent/10'
                : 'text-pb-faint pb-hairline hover:text-pb-text'
            }`}
          >
            {label}
          </button>
        )
      })}
      {!confirmed && (
        <span
          className="font-mono text-[9px] text-pb-amber uppercase tracking-wide ml-1"
          title="Worked out from the grade name and the matches played — click to confirm or change"
        >
          suggested
        </span>
      )}
      {!confirmed && shown.length === 0 && emptyHint && (
        <span className="font-mono text-[9px] text-pb-faintest ml-1">{emptyHint}</span>
      )}
    </div>
  )
}

function GradeList({ grades, onChanged }) {
  const [savingName, setSavingName] = useState(null)
  const [applyingAll, setApplyingAll] = useState(false)
  const [error, setError] = useState(null)
  // Reordering is a local draft saved on a button. The arrows move a row
  // between neighbours, which is enough for a list of a dozen or so grades and
  // — per the note in CLAUDE.md about Chromium's native drag loop — is far
  // easier to verify than HTML5 drag-and-drop.
  const [draft, setDraft] = useState(null) // string[] of grade_name, or null when clean
  const [savingOrder, setSavingOrder] = useState(false)

  // The list the table renders: the local draft while one is in flight, else
  // whatever order the server sent (which is already the club's own).
  const shown = draft
    ? draft.map(n => grades.find(g => g.grade_name === n)).filter(Boolean)
    : grades

  function move(index, delta) {
    const names = shown.map(g => g.grade_name)
    const target = index + delta
    if (target < 0 || target >= names.length) return
    const next = [...names]
    ;[next[index], next[target]] = [next[target], next[index]]
    setDraft(next)
  }

  async function saveOrder() {
    if (!draft) return
    setSavingOrder(true)
    setError(null)
    try {
      await api.reorderGrades(draft)
      setDraft(null)
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingOrder(false)
    }
  }

  async function clearOrder() {
    setSavingOrder(true)
    setError(null)
    try {
      await api.clearGradeOrder()
      setDraft(null)
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingOrder(false)
    }
  }

  async function save(gradeName, patch) {
    setSavingName(gradeName)
    setError(null)
    try {
      await api.classifyGrade(gradeName, patch)
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingName(null)
    }
  }

  async function applyAll() {
    setApplyingAll(true)
    setError(null)
    try {
      await api.applyGradeSuggestions()
      onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setApplyingAll(false)
    }
  }

  if (!grades.length) return <p className="font-mono text-[11px] text-pb-faint">No grades found for this club.</p>

  const anyUnconfirmed = grades.some(g => !g.category_confirmed || !g.formats_confirmed)

  return (
    <div>
      <p className="text-pb-dim text-sm mb-3 leading-relaxed">
        Label each grade so the club dashboard and public site can split them, and choose which ones to
        share. A grade can be more than one of each: "Women's T20 Grade 2" is a women's grade and a T20
        grade, and an Under 14 girls' side is both juniors and women's. A hidden grade drops off the public
        grade filters, ladders and per-grade breakdowns; your admin views and whole-club career totals are
        unchanged.
      </p>
      <p className="text-pb-dim text-sm mb-3 leading-relaxed">
        Match type here is a fallback, not the filter itself. Leaderboards and the dashboard read each
        match's own recorded format, because a grade often plays more than one — a 1st Grade season is
        usually a mix of one-day and two-day games. What you tick here only fills in for older matches
        synced before we started recording the format, and only when a grade plays a single format, since
        a mixed grade says nothing useful about one unlabelled game.
      </p>
      <p className="text-pb-dim text-sm mb-3 leading-relaxed">
        The order here is also the order BetterPosts uses for a Fixtures or Results roundup post — move a
        grade with the arrows, then save. Anything you haven't ordered sits below the ones you have.
      </p>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {anyUnconfirmed && (
          <button
            onClick={applyAll}
            disabled={applyingAll}
            className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50"
          >
            {applyingAll ? 'Applying…' : 'Confirm all suggestions'}
          </button>
        )}
        {draft && (
          <button
            onClick={saveOrder}
            disabled={savingOrder}
            className="font-mono text-[10px] tracking-wide2 rounded px-3 py-1.5 text-pb-bg disabled:opacity-50"
            style={{ background: 'var(--pb-accent)' }}
          >
            {savingOrder ? 'Saving…' : 'Save order'}
          </button>
        )}
        {draft && (
          <button
            onClick={() => setDraft(null)}
            disabled={savingOrder}
            className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text disabled:opacity-50"
          >
            Discard
          </button>
        )}
        {!draft && grades.some(g => g.display_order != null) && (
          <button
            onClick={clearOrder}
            disabled={savingOrder}
            className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-red disabled:opacity-50"
          >
            Clear order
          </button>
        )}
      </div>
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <div className="pb-card overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-2.5 pl-5 w-16">ORDER</th>
              <th className="font-medium py-2.5">GRADE</th>
              <th className="font-medium py-2.5">GRADE TYPE</th>
              <th className="font-medium py-2.5">MATCH TYPE</th>
              <th className="font-medium py-2.5 text-center">PUBLIC</th>
              <th className="font-medium py-2.5 text-right">GAMES</th>
              <th className="font-medium py-2.5 pr-5 text-right">RUNS</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((g, i) => {
              const busy = savingName === g.grade_name
              return (
                <tr key={g.grade_name} className={`${i ? 'pb-hairline-t' : ''} align-top hover:bg-pb-surface2 ${g.is_public ? '' : 'opacity-60'}`}>
                  <td className="py-2.5 pl-5">
                    <div className="flex items-center gap-1">
                      <span className="font-mono text-[11px] text-pb-faint w-5">
                        {/* The position it WILL hold once saved — the server
                            numbers 1..N from this order, so showing the stored
                            number instead would disagree with a pending move. */}
                        {i + 1}
                      </span>
                      <div className="flex flex-col">
                        <button
                          onClick={() => move(i, -1)}
                          disabled={i === 0 || savingOrder}
                          aria-label={`Move ${g.display_name} up`}
                          className="font-mono text-[9px] leading-none px-1 py-0.5 text-pb-faint hover:text-pb-text disabled:opacity-25"
                        >▲</button>
                        <button
                          onClick={() => move(i, 1)}
                          disabled={i === shown.length - 1 || savingOrder}
                          aria-label={`Move ${g.display_name} down`}
                          className="font-mono text-[9px] leading-none px-1 py-0.5 text-pb-faint hover:text-pb-text disabled:opacity-25"
                        >▼</button>
                      </div>
                    </div>
                  </td>
                  <td className="py-2.5">
                    <div className="text-pb-text">{g.display_name}</div>
                    {g.display_name !== g.grade_name && (
                      <div className="font-mono text-[10px] text-pb-faintest mt-0.5">raw: {g.grade_name}</div>
                    )}
                    {g.aliases?.length > 0 && (
                      <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                        Includes: {g.aliases.join(', ')}
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <TagPicker
                      options={GRADE_CATEGORIES}
                      value={g.categories}
                      suggested={g.suggested_categories}
                      confirmed={g.categories_confirmed}
                      disabled={busy}
                      onChange={categories => save(g.grade_name, { categories })}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <TagPicker
                      options={MATCH_FORMATS}
                      value={g.match_formats}
                      suggested={g.suggested_formats}
                      confirmed={g.formats_confirmed}
                      disabled={busy}
                      onChange={match_formats => save(g.grade_name, { match_formats })}
                      emptyHint="not known"
                    />
                  </td>
                  <td className="py-2.5 text-center">
                    <button
                      onClick={() => save(g.grade_name, { is_public: !g.is_public })}
                      disabled={busy}
                      className={`font-mono text-[10px] tracking-wide2 rounded px-2.5 py-1 border transition-colors disabled:opacity-50 ${
                        g.is_public
                          ? 'text-pb-positive border-pb-positive/40 hover:bg-pb-positive/10'
                          : 'text-pb-faint pb-hairline hover:text-pb-text'
                      }`}
                    >
                      {g.is_public ? 'Public' : 'Hidden'}
                    </button>
                  </td>
                  <td className="py-2.5 font-mono text-pb-dim text-right">{g.games}</td>
                  <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{g.runs}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MergeHistory({ orgId, refreshKey, onChanged }) {
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getGradeMergeHistory(orgId).then(setHistory).catch(() => {})
  }, [orgId, refreshKey])

  async function handleUndo(entry) {
    setUndoing(entry.id)
    setError(null)
    try {
      await api.undoGradeMerge(entry.id, orgId)
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setUndoing(null)
    }
  }

  if (history.length === 0) return null

  return (
    <div className="mt-10">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Merge History</p>
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <div className="flex flex-col gap-2">
        {history.map(entry => (
          <div
            key={entry.id}
            className={`flex items-center gap-3 rounded border px-4 py-3 text-sm pb-hairline ${entry.undone ? 'opacity-40' : 'bg-pb-surface'}`}
          >
            <div className="flex-1 min-w-0">
              <span className="text-pb-text font-medium">{entry.canonical_name}</span>
              <span className="text-pb-faint mx-2">←</span>
              <span className="text-pb-amber">{entry.alias_name}</span>
              <span className="font-mono text-[10px] text-pb-faintest ml-3">{new Date(entry.merged_at).toLocaleDateString()}</span>
            </div>
            {entry.undone ? (
              <span className="font-mono text-[10px] text-pb-faintest shrink-0">Undone</span>
            ) : (
              <button
                onClick={() => handleUndo(entry)}
                disabled={undoing === entry.id}
                className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-faint hover:text-pb-text transition-colors shrink-0 disabled:opacity-50"
              >
                {undoing === entry.id ? 'Undoing…' : 'Undo'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function RenameGrades() {
  const [grades, setGrades] = useState(null)
  const [editing, setEditing] = useState(null) // { original_name, value }
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function load() {
    api.adminListGrades().then(setGrades).catch(() => setGrades([]))
  }

  useEffect(() => { load() }, [])

  async function saveRename() {
    if (!editing) return
    setSaving(true)
    setError(null)
    try {
      await api.adminRenameGrade(editing.original_name, editing.value || null)
      setEditing(null)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function clearOverride(originalName) {
    setSaving(true)
    setError(null)
    try {
      await api.adminRenameGrade(originalName, null)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!grades) return <PbSpinner message="Loading grades…" />

  return (
    <div className="mt-10">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">Rename Grades</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Set a display name for a grade. The display name is shown everywhere instead of the original sync'd name.
        Useful for shortening sponsor-suffixed names like "One Day Grade 5 - Black" → "One Day Grade 5".
      </p>
      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      <div className="pb-card overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-2.5 pl-5">ORIGINAL NAME</th>
              <th className="font-medium py-2.5">DISPLAY NAME</th>
              <th className="font-medium py-2.5 pr-5 text-right">GAMES</th>
            </tr>
          </thead>
          <tbody>
            {grades.map((g, i) => (
              <tr key={g.original_name} className={`${i ? 'pb-hairline-t' : ''} align-middle`}>
                <td className="py-2.5 pl-5 text-pb-dim font-mono text-[11px] max-w-[220px] truncate">{g.original_name}</td>
                <td className="py-2 pr-3">
                  {editing?.original_name === g.original_name ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        type="text"
                        value={editing.value}
                        onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                        placeholder="Blank to clear override"
                        className="flex-1 bg-pb-surface2 border rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none"
                        style={{ borderColor: 'var(--pb-accent)' }}
                        onKeyDown={e => { if (e.key === 'Enter') saveRename(); if (e.key === 'Escape') setEditing(null) }}
                      />
                      <button
                        onClick={saveRename}
                        disabled={saving}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 shrink-0"
                        style={{ background: 'var(--pb-accent)' }}
                      >
                        SAVE
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors shrink-0"
                      >
                        CANCEL
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span
                        className={`flex-1 text-sm ${g.display_name_override ? 'text-pb-text font-medium' : 'text-pb-faintest italic'}`}
                      >
                        {g.display_name_override || 'no override'}
                      </span>
                      <button
                        onClick={() => setEditing({ original_name: g.original_name, value: g.display_name_override || '' })}
                        className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-faint hover:text-pb-text transition-colors shrink-0"
                      >
                        Edit
                      </button>
                      {g.display_name_override && (
                        <button
                          onClick={() => clearOverride(g.original_name)}
                          disabled={saving}
                          className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-red/60 hover:text-pb-red transition-colors shrink-0 disabled:opacity-50"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  )}
                </td>
                <td className="py-2.5 pr-5 font-mono text-pb-dim text-right text-[11px]">{g.games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

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
function CompetitionManager() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  function load() {
    setLoading(true)
    api.adminCompetitions()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

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

  return (
    <div className="mb-10">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
        Competitions <span className="text-pb-faintest">({competitions.length})</span>
      </p>
      <p className="text-pb-faint text-sm mb-4 leading-relaxed">
        Which competition each grade was played in. Grades are grouped
        automatically by the association that runs them, which is right for most
        clubs. Split one here when an association runs several competitions you
        want to read separately — a cup alongside the regular season, say.
      </p>

      {error && <p className="text-pb-red text-sm mb-3">{error}</p>}

      {!competitions.length && (
        <div className="border pb-hairline rounded p-4 mb-4">
          <p className="text-sm text-pb-dim mb-3">
            {associations.length
              ? `Nothing grouped yet. Your grades come from ${associations.length} ${associations.length === 1 ? 'association' : 'associations'}.`
              : 'No association recorded on your grades yet. A sync fills this in; the seasons before that need the association backfill run.'}
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

      {competitions.map(c => {
        const held = grades.filter(g => g.competition_id === c.id)
        return (
          <div key={c.id} className="border pb-hairline rounded p-4 mb-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
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

export default function AdminGrades() {
  const { user } = useAuth()
  const [orgId, setOrgId] = useState(null)
  const [grades, setGrades] = useState(null)
  const [loading, setLoading] = useState(true)
  const [historyKey, setHistoryKey] = useState(0)

  useEffect(() => {
    if (user?.club_id) {
      setOrgId(user.club_id)
    } else {
      api.adminGetSettings().then(s => setOrgId(s.id)).catch(() => {})
    }
  }, [user])

  function load() {
    if (!orgId) return
    setLoading(true)
    api.listGradesWithStats(orgId)
      .then(setGrades)
      .catch(() => setGrades([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [orgId])

  function refresh() {
    setHistoryKey(k => k + 1)
    load()
  }

  if (!orgId || loading) {
    return (
      <BetterStatsLayout>
        <PbSpinner message="Loading grades…" />
      </BetterStatsLayout>
    )
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Grades</h1>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Group grades into the competitions they were played in, label them by type, choose which to
          share publicly, merge grades that are the same competition under different names, or set
          display name overrides.
        </p>

        <CompetitionManager />

        <MergeBuilder orgId={orgId} grades={grades || []} onMerged={refresh} />

        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
          Labels &amp; Visibility <span className="text-pb-faintest">({(grades || []).length})</span>
        </p>
        <GradeList grades={grades || []} onChanged={refresh} />

        <MergeHistory orgId={orgId} refreshKey={historyKey} onChanged={refresh} />

        <RenameGrades />
      </div>
    </BetterStatsLayout>
  )
}
