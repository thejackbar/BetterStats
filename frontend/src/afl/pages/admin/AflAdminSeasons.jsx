import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'

// Seasons had no admin surface of their own before this — only indirectly,
// through whichever picker happened to need one (the Import Stats wizard,
// the leaderboard's season filter). This is just list + rename + a safe
// delete for a season that turned out to be a mistake and has nothing
// recorded against it yet.
function SeasonRow({ season, onSaved, onDeleted }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(season.name || '')
  const [year, setYear] = useState(season.year != null ? String(season.year) : '')
  const [busy, setBusy] = useState(false)

  // Mirrors _season_in_use server-side: an adjustment typed against a season
  // counts as data recorded against it, same as a synced or imported game.
  const canDelete = !season.synced && season.grades === 0 && season.synced_games === 0
    && season.imported_games === 0 && !season.adjustments

  async function save() {
    const n = name.trim()
    if (!n) { toast.error('Season name is required'); return }
    setBusy(true)
    try {
      await aflApi.adminRenameSeason(season.id, { name: n, year: year ? parseInt(year, 10) : null })
      onSaved()
      setEditing(false)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function del() {
    if (!window.confirm(`Delete season "${season.name}"? This can't be undone.`)) return
    setBusy(true)
    try {
      await aflApi.adminDeleteSeason(season.id)
      toast.success(`Deleted "${season.name}"`)
      onDeleted()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (editing) {
    return (
      <tr className="pb-hairline-t align-middle">
        <td className="py-2 pr-2" colSpan={2}>
          <div className="flex flex-wrap items-center gap-1.5">
            <input autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') save() }}
              className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
            <input value={year} onChange={e => setYear(e.target.value.replace(/\D/g, '').slice(0, 4))}
              placeholder="Year" onKeyDown={e => { if (e.key === 'Enter') save() }}
              className="w-16 shrink-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
          </div>
        </td>
        <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.grades}</td>
        <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.synced_games + season.imported_games + (season.adjustment_games || 0)}</td>
        <td className="py-2 pr-2 text-right">
          <button onClick={save} disabled={busy}
            className="font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1 text-black bg-[var(--pb-accent)] disabled:opacity-50 mr-2">
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
          <button onClick={() => setEditing(false)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Cancel</button>
        </td>
      </tr>
    )
  }

  return (
    <tr className="pb-hairline-t align-middle">
      <td className="py-2 pr-2 text-pb-text">{season.name}</td>
      <td className="py-2 pr-2 font-mono text-[11px] text-pb-faint">{season.year || '—'}</td>
      <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.grades}</td>
      <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.synced_games + season.imported_games + (season.adjustment_games || 0)}</td>
      <td className="py-2 pr-2 text-right whitespace-nowrap">
        {season.synced && (
          <span className="font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 text-green-300 border-green-300/30 mr-2">SYNCED</span>
        )}
        <button onClick={() => setEditing(true)} className="font-mono text-[10px] text-pb-dim hover:text-pb-text underline mr-3">Rename</button>
        {canDelete && (
          <button onClick={del} disabled={busy} className="font-mono text-[10px] text-pb-red/70 hover:text-pb-red underline disabled:opacity-50">
            Delete
          </button>
        )}
      </td>
    </tr>
  )
}

// PlayHQ's "teams in this season" answer only ever carries a team's CURRENT
// grade — there's no grade history in it. A team that gets re-graded into a
// different division mid-season (a round-robin split, promotion/relegation
// after the first few rounds) drops its OLD grade out of every later sync's
// discovery, so that grade's rounds can go permanently missing from Results.
// This panel is the way back in: paste a PlayHQ link to any one match from
// the missing grade (any round works) and the whole grade gets pulled in.
function LinkGradePanel({ seasons, onLinked }) {
  const toast = useToast()
  const [seasonId, setSeasonId] = useState('')
  const [ref, setRef] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!seasonId && seasons?.length) setSeasonId(seasons[0].id)
  }, [seasons, seasonId])

  async function findGrade() {
    if (!ref.trim()) { toast.error('Paste a PlayHQ match link first'); return }
    setBusy(true)
    setPreview(null)
    try {
      const info = await aflApi.linkGradePreview(ref.trim())
      setPreview(info)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function linkIt() {
    if (!seasonId) { toast.error('Pick which season this grade belongs to'); return }
    setBusy(true)
    try {
      const result = await aflApi.linkGrade(seasonId, ref.trim())
      toast.success(`Linked "${result.grade_name}" — ${result.games_discovered} game(s) found, ${result.games_stats_synced} synced`)
      setRef('')
      setPreview(null)
      onLinked()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const ourSide = preview?.matched_side
  const ourTeamName = ourSide === 'home' ? preview?.home_team : ourSide === 'away' ? preview?.away_team : null

  return (
    <div className="pb-card p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-pb-text">Missing a grade?</h3>
        <p className="text-[12px] text-pb-dim mt-0.5 max-w-2xl">
          If your team changed divisions partway through a season (a round-robin split,
          promotion/relegation), PlayHQ stops showing us the old division — its rounds
          never get discovered. Paste a match link from any round of the missing grade
          (from PlayHQ's website — a club's own page or the ladder) and we'll pull the
          whole grade in.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <select value={seasonId} onChange={e => setSeasonId(e.target.value)}
          className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[12px] text-pb-text">
          {(seasons || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <input value={ref} onChange={e => setRef(e.target.value)}
          placeholder="https://www.playhq.com/.../game-centre/…  (or just the code)"
          onKeyDown={e => { if (e.key === 'Enter') findGrade() }}
          className="flex-1 min-w-[260px] bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
        <button onClick={findGrade} disabled={busy}
          className="font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1.5 bg-pb-surface2 border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-50">
          {busy ? 'LOOKING…' : 'FIND GRADE'}
        </button>
      </div>

      {preview && (
        <div className="border pb-hairline rounded p-3 text-[12px] space-y-1.5">
          <div className="text-pb-text font-medium">
            {preview.grade_name}
            {preview.competition_name && <span className="text-pb-faint"> · {preview.competition_name}</span>}
            {preview.playhq_season_name && <span className="text-pb-faint"> · {preview.playhq_season_name}</span>}
          </div>
          <div className="text-pb-dim">{preview.home_team} <span className="text-pb-faint">({preview.home_club})</span> vs {preview.away_team} <span className="text-pb-faint">({preview.away_club})</span></div>
          {ourSide ? (
            <div className="text-green-300">✓ Matches this club — {ourTeamName}</div>
          ) : (
            <div className="text-amber-400">Couldn't confirm this club is playing in that match — double-check the link before linking.</div>
          )}
          <button onClick={linkIt} disabled={busy}
            className="font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1.5 text-black bg-[var(--pb-accent)] disabled:opacity-50 mt-1">
            {busy ? 'LINKING…' : 'LINK THIS GRADE'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function AflAdminSeasons() {
  const toast = useToast()
  const [seasons, setSeasons] = useState(null)

  const load = () => aflApi.adminListSeasons().then(setSeasons).catch(e => toast.error(e.message))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4 max-w-4xl">
      <SectionTitle>Seasons</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl -mt-2">
        Every season your club holds — synced from PlayHQ or created by hand (via Import
        Stats, or here). Rename any of them; a season with no grades or games recorded
        against it yet can also be deleted.
      </p>

      {seasons === null ? (
        <LoadingSpinner message="Loading seasons…" />
      ) : (
        <>
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                  <th className="py-2 pr-2">NAME</th>
                  <th className="py-2 pr-2">YEAR</th>
                  <th className="py-2 pr-2 text-right">GRADES</th>
                  <th className="py-2 pr-2 text-right">GAMES</th>
                  <th className="py-2 pr-2 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {seasons.map(s => (
                  <SeasonRow key={s.id} season={s} onSaved={load} onDeleted={load} />
                ))}
                {seasons.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-center text-pb-dim text-[12px]">No seasons yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {seasons.length > 0 && <LinkGradePanel seasons={seasons} onLinked={load} />}
        </>
      )}
    </div>
  )
}
