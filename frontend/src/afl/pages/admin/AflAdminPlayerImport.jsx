import { useRef, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

const STATUS_LABEL = {
  exact: 'Matched', auto: 'Matched (close)', suggest: 'Needs review', ambiguous: 'Ambiguous', none: 'No match',
}

export default function AflAdminPlayerImport() {
  const [rows, setRows] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const fileRef = useRef(null)

  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await aflApi.playerImportPreview(file)
      setRows(res.rows.map(r => ({ ...r, chosen_player_id: r.status === 'exact' || r.status === 'auto' ? r.player_id : null })))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const setChoice = (idx, playerId) => {
    setRows(rs => rs.map((r, i) => i === idx ? { ...r, chosen_player_id: playerId || null } : r))
  }

  const commit = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = rows.map(r => ({
        name: r.name, email: r.email, phone: r.phone, gender: r.gender, player_id: r.chosen_player_id,
      }))
      const res = await aflApi.playerImportCommit(payload)
      setResult(res)
      setRows(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <SectionTitle>Import Players</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">
        Upload a CSV of names, emails and phone numbers. Each row is matched by
        name to a player already in the system, and only email/phone/gender are
        filled in (never overwriting a value the player already has). PlayHQ sync
        already discovers every player automatically, so this is just for
        bringing in contact details you hold separately.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <a href={aflApi.playerImportTemplateUrl()} className="text-sm text-pb-dim underline hover:text-pb-text">
          Download CSV template
        </a>
        <label className="px-4 py-2 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black cursor-pointer">
          {busy ? 'Working…' : 'Choose CSV file'}
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} disabled={busy} className="hidden" />
        </label>
      </div>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}
      {result && (
        <p className="pb-card p-3 text-sm text-[var(--pb-positive)]">
          Done: {result.updated} player{result.updated === 1 ? '' : 's'} updated, {result.skipped} skipped.
        </p>
      )}

      {rows && (
        <div className="space-y-3">
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="pb-hairline-b">
                <tr>
                  {['Row name', 'Email', 'Phone', 'Match'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={idx} className="pb-hairline-b last:border-0">
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="px-3 py-2 text-pb-faint">{r.email || '—'}</td>
                    <td className="px-3 py-2 text-pb-faint">{r.phone || '—'}</td>
                    <td className="px-3 py-2">
                      {r.candidates?.length ? (
                        <select value={r.chosen_player_id || ''} onChange={e => setChoice(idx, e.target.value)}
                                className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                          <option value="">Skip this row</option>
                          {r.candidates.map(c => (
                            <option key={c.player_id} value={c.player_id}>{c.name}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={r.chosen_player_id ? 'text-[var(--pb-positive)]' : 'text-pb-faint'}>
                          {r.chosen_player_id ? `${STATUS_LABEL[r.status]}. ${r.matched_name}` : STATUS_LABEL[r.status] || 'No match'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button disabled={busy} onClick={commit}
                  className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Saving…' : `Apply to ${rows.filter(r => r.chosen_player_id).length} matched players`}
          </button>
        </div>
      )}
    </div>
  )
}
