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

  const canDelete = !season.synced && season.grades === 0 && season.synced_games === 0 && season.imported_games === 0

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
        <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.synced_games + season.imported_games}</td>
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
      <td className="py-2 pr-2 text-right font-mono text-[10px] text-pb-faint">{season.synced_games + season.imported_games}</td>
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
      )}
    </div>
  )
}
