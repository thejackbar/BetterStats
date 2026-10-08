import { useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Super Admin tool: handle a person's privacy request. Find the person across
// every club, then download a PDF of the personal information BetterCricket holds
// about them (backend: services/player_data_report.py). The PDF holds contact
// details, so it is only ever fetched on a click and saved to this computer.

const STATUS = {
  public: { label: 'On the public site', tone: 'text-pb-faint' },
  hidden_by_club: { label: 'Hidden by the club', tone: 'text-pb-faint' },
  removed_at_request: { label: 'Removed at their request', tone: 'text-pb-accent' },
  name_match_hold: { label: 'Held: same name as a removed person', tone: 'text-amber-400' },
}

function saveBlob({ blob, filename }) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export default function SuperPrivacyRequests() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [note, setNote] = useState('')
  const [searching, setSearching] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const search = async (e) => {
    e.preventDefault()
    setError(''); setDone(''); setNote('')
    setSearching(true)
    try {
      const out = await api.superFindPrivacyPlayers(q.trim())
      setResults(Array.isArray(out?.players) ? out.players : [])
      setNote(out?.note || '')
    } catch (err) {
      setError(err.message || 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  const download = async (p) => {
    setBusyId(p.id); setError(''); setDone('')
    try {
      const file = await api.superPlayerDataReport(p.id)
      saveBlob(file)
      setDone(`Saved ${file.filename}. Check who is asking before you send it.`)
    } catch (err) {
      setError(err.message || 'Could not create the report')
    } finally {
      setBusyId('')
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-2xl mx-auto p-4 sm:p-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-pb-text">Privacy requests</h1>
          <p className="text-sm text-pb-dim mt-1 leading-relaxed">
            Find a person, then download a PDF of the personal information BetterCricket holds about them. It covers
            every club's record for that person: their details, membership, email list entries, sign-in account and the
            matches they are recorded in. Fee and payment records are counted, not itemised, and free-text notes are not
            printed.
          </p>
          <p className="text-[12px] text-amber-400 mt-2 leading-relaxed">
            The PDF holds contact details. Confirm who is asking before you send it, and read it first. Every download
            is recorded in the club's activity log.
          </p>
        </div>

        <form onSubmit={search} className="pb-card p-5 mb-6">
          <label htmlFor="privacy-q" className="font-mono text-[10px] text-pb-faint block mb-1">Name or player id</label>
          <div className="flex gap-2">
            <input
              id="privacy-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Alex Sample"
              className="min-w-0 flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text"
            />
            <button
              type="submit"
              disabled={searching || q.trim().length < 3}
              className="shrink-0 px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40"
              style={{ background: 'var(--pb-accent)' }}
            >
              {searching ? 'SEARCHING…' : 'SEARCH'}
            </button>
          </div>
          {error && <p className="mt-3 text-[12px] text-pb-red" role="alert">{error}</p>}
          {done && <p className="mt-3 text-[12px] text-pb-dim" role="status">{done}</p>}
        </form>

        {note && <p className="text-sm text-pb-faint mb-3">{note}</p>}
        {results && results.length === 0 && !note && (
          <p className="text-sm text-pb-faint">No player matches that. Try the surname and first name, or paste the player id.</p>
        )}
        <ul className="space-y-2">
          {(results || []).map((p) => {
            const st = STATUS[p.status] || STATUS.public
            return (
              <li key={p.id} className="pb-card p-4 flex items-center justify-between gap-3" data-testid="privacy-player">
                <span className="min-w-0">
                  <span className="block text-sm text-pb-text truncate">{p.name}</span>
                  <span className="block font-mono text-[10px] text-pb-faintest truncate">{p.club || 'No club'}</span>
                  <span className={`block font-mono text-[10px] ${st.tone}`}>
                    {st.label}
                    {!p.has_participant_id && <span className="text-pb-faintest">{' · no Cricket Australia id'}</span>}
                  </span>
                </span>
                <button
                  onClick={() => download(p)}
                  disabled={busyId === p.id}
                  className="shrink-0 font-mono text-[10px] tracking-wide2 px-3 py-2 rounded border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-40"
                >
                  {busyId === p.id ? 'PREPARING…' : 'DOWNLOAD PDF'}
                </button>
              </li>
            )
          })}
        </ul>

        <p className="mt-8 text-[12px] text-pb-faint leading-relaxed">
          To remove a person from the public site at their request, run{' '}
          <span className="font-mono text-pb-dim">python -m app.scripts.hide_player_at_request</span> on the server.
          It is not a button here yet.
        </p>
      </div>
    </AdminLayout>
  )
}
