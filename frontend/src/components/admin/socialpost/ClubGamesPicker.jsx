import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../lib/api'

// The club's own list of played games: the same rows the public Games page
// (/{club}/games) draws, from the same endpoint. A post is built from one of
// them without pasting a link. Game ids are the Cricket Australia match GUIDs
// the scorecard import already takes, so a pick goes straight to `onPick(id)`.
//
// The list is only fetched once it is opened, so a tab that never uses it costs
// nothing. Called-off games are left out: they have no scores to post.

const CALLED_OFF = ['ABANDONED', 'CANCELLED']

const RESULT_TONE = {
  WIN: 'bg-green-500/15 text-green-400',
  LOSS: 'bg-red-500/15 text-red-400',
}

function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function ClubGamesPicker({ orgId, onPick, busy = false }) {
  const [open, setOpen] = useState(false)
  const [seasons, setSeasons] = useState(null)
  const [seasonId, setSeasonId] = useState('')
  const [games, setGames] = useState(null)
  const [error, setError] = useState('')
  const [grade, setGrade] = useState('')

  useEffect(() => {
    if (!open || !orgId || seasons !== null) return undefined
    let live = true
    api.getOrgSeasons(orgId)
      .then((list) => {
        if (!live) return
        const rows = Array.isArray(list) ? list : []
        setSeasons(rows)
        if (rows[0]) setSeasonId(rows[0].id)
        else setGames([])
      })
      .catch(() => { if (live) { setSeasons([]); setGames([]); setError('Could not load your games.') } })
    return () => { live = false }
  }, [open, orgId, seasons])

  useEffect(() => {
    if (!open || !orgId || !seasonId) return undefined
    let live = true
    setGames(null)
    setError('')
    setGrade('')
    api.getOrgResults(orgId, { seasonId })
      .then((rows) => { if (live) setGames(Array.isArray(rows) ? rows : []) })
      .catch(() => { if (live) { setGames([]); setError('Could not load your games.') } })
    return () => { live = false }
  }, [open, orgId, seasonId])

  const played = useMemo(
    () => (games || []).filter((g) => !CALLED_OFF.includes((g.status || '').toUpperCase())),
    [games],
  )
  const grades = useMemo(
    () => [...new Set(played.map((g) => g.grade_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    [played],
  )
  const shown = useMemo(
    () => played
      .filter((g) => !grade || g.grade_name === grade)
      .sort((a, b) => (b.played_at || '').localeCompare(a.played_at || '')),
    [played, grade],
  )

  if (!orgId) return null

  return (
    <div className="mt-3 pt-3 border-t pb-hairline" data-testid="club-games-picker">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="w-full flex items-center justify-between text-left font-mono text-[9px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text">
        <span>Or pick from your Games</span>
        <span>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="mt-2">
          <p className="text-pb-faintest text-[10px] leading-relaxed mb-2">
            The same games your public Games page lists. Pick one and the score, result, top performers and player of the match fill in.
          </p>

          {seasons && seasons.length > 0 && (
            <div className="flex gap-2 mb-2">
              <select value={seasonId} onChange={(e) => setSeasonId(e.target.value)} aria-label="Season"
                className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text">
                {seasons.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {grades.length > 1 && (
                <select value={grade} onChange={(e) => setGrade(e.target.value)} aria-label="Grade"
                  className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text">
                  <option value="">All grades</option>
                  {grades.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              )}
            </div>
          )}

          {games === null && !error && <p className="font-mono text-[10px] text-pb-faintest">Loading your games…</p>}
          {error && <p className="font-mono text-[10px] text-red-400">{error}</p>}
          {games !== null && !error && shown.length === 0 && (
            <p className="text-pb-faintest text-[11px] leading-relaxed">
              {seasons && seasons.length === 0 ? 'No seasons are synced yet.' : 'No played games for that selection.'}
            </p>
          )}

          {shown.length > 0 && (
            <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
              {shown.map((g) => (
                <button key={g.id} type="button" onClick={() => onPick(g.id)} disabled={busy}
                  className="text-left px-2 py-1.5 rounded border pb-hairline bg-pb-surface2 hover:border-pb-accent transition-colors disabled:opacity-50">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="flex-1 min-w-0 truncate text-pb-text text-[12px]">{g.home_team || '—'} v {g.away_team || '—'}</span>
                    {g.result && (
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold ${RESULT_TONE[g.result] || 'bg-pb-surface text-pb-dim'}`}>{g.result}</span>
                    )}
                  </div>
                  <div className="font-mono text-[9px] text-pb-faint truncate">
                    {[shortDate(g.played_at), g.grade_name].filter(Boolean).join(' · ')}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
