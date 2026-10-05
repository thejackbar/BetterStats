import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

const pts = (n) => (Number.isInteger(n) ? n : Number(n).toFixed(1))

// Better HQ view of every club running a BetterFantasyCricket competition: where
// its rounds are up to and the top of its ladder. "Open" switches into the club
// (same as the club switcher) and lands on its Fantasy admin.
export default function SuperFantasyCompetitions() {
  const { switchClub } = useAuth()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api.superFantasyCompetitions()
      .then(d => setRows(d.competitions || []))
      .catch(e => { setError(e.message || 'Could not load competitions.'); setRows([]) })
  }, [])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!rows) return []
    return q ? rows.filter(r => (r.club_name || '').toLowerCase().includes(q) || (r.club_slug || '').toLowerCase().includes(q)) : rows
  }, [rows, query])

  const open = async (clubId) => {
    setBusy(clubId); setError('')
    try { await switchClub(clubId, 'admin/fantasy') } // hard-reloads on success
    catch (e) { setError(e.message || 'Could not switch club.'); setBusy('') }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Fantasy competitions</h1>
          <p className="text-sm text-pb-dim mt-1">
            Every club with a BetterFantasyCricket season, with its round progress and the top of its
            ladder. A round still being played counts its points so far. Open a club to see its
            rounds, settle or unsettle them, and use its admin pages.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 mb-4">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search clubs…" className={INPUT_CLS} />
          <div className="text-xs text-pb-faint ml-auto">{shown.length} club{shown.length === 1 ? '' : 's'}</div>
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>}

        {rows === null ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : shown.length === 0 ? (
          <div className="pb-card p-8 text-center text-sm text-pb-faint">No club has a fantasy season yet.</div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {shown.map(c => (
              <div key={c.season_id} className="pb-card p-4 min-w-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-display font-bold text-pb-text truncate">{c.club_name}</div>
                    <div className="text-xs text-pb-faint">
                      {c.season_name || c.season_year} · {c.status} · {c.managers} manager{c.managers === 1 ? '' : 's'}
                    </div>
                  </div>
                  <button onClick={() => open(c.club_id)} disabled={busy === c.club_id}
                    className="shrink-0 px-3 py-1.5 rounded border border-pb-hairline text-sm text-pb-text hover:border-pb-accent disabled:opacity-50">
                    {busy === c.club_id ? 'Opening…' : 'Open'}
                  </button>
                </div>
                <div className="text-xs text-pb-faint mt-2">
                  {c.rounds_scored}/{c.rounds_total} rounds scored
                  {c.next_round ? ` · round ${c.next_round} is next to settle` : ''}
                </div>
                {c.top.length === 0 ? (
                  <p className="text-xs text-pb-faint mt-3">No squads yet.</p>
                ) : (
                  <ol className="mt-3 space-y-1 text-sm">
                    {c.top.map(t => (
                      <li key={`${t.rank}-${t.team_name}`} className="flex items-center gap-2 min-w-0">
                        <span className="w-5 text-pb-faint shrink-0">{t.rank}</span>
                        <span className="min-w-0 flex-1 truncate text-pb-text">{t.team_name} <span className="text-pb-faint">({t.manager})</span></span>
                        <span className="tabular-nums text-pb-text shrink-0">{pts(t.points)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
