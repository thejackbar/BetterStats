import { useEffect, useMemo, useState, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Super Admin tool: link clubs together. Once linked, a Club Admin of any club
// in the group can pick which of the clubs they are working in, from their admin
// dashboard (components/admin/LinkedClubSwitcher.jsx). A club that is not linked
// to another club never shows the switcher. Rules live in services/club_links.py.

const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const SELECT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'

export default function SuperClubLinks() {
  const [clubs, setClubs] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [clubA, setClubA] = useState('')
  const [clubB, setClubB] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirmUnlink, setConfirmUnlink] = useState('') // club id awaiting confirmation

  const load = useCallback(async () => {
    const [cs, gs] = await Promise.all([api.superListClubs(false), api.superListClubLinks()])
    setClubs([...(Array.isArray(cs) ? cs : [])].sort((a, b) => a.name.localeCompare(b.name)))
    setGroups(Array.isArray(gs?.groups) ? gs.groups : [])
  }, [])

  useEffect(() => {
    load().catch((e) => setError(e.message || 'Could not load clubs')).finally(() => setLoading(false))
  }, [load])

  const linkedIds = useMemo(() => {
    const m = new Map()
    groups.forEach((g) => g.clubs.forEach((c) => m.set(c.id, g)))
    return m
  }, [groups])

  const nameOf = (id) => clubs.find((c) => c.id === id)?.name || 'that club'
  const canLink = clubA && clubB && clubA !== clubB && !busy

  const doLink = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      await api.superLinkClubs(clubA, clubB)
      setNotice(`${nameOf(clubA)} and ${nameOf(clubB)} are linked. Their Club Admins can now switch between them.`)
      setClubA(''); setClubB('')
      await load()
    } catch (e) {
      setError(e.message || 'Could not link those clubs')
    } finally {
      setBusy(false)
    }
  }

  const doUnlink = async (club) => {
    setBusy(true); setError(''); setNotice('')
    try {
      await api.superUnlinkClub(club.id)
      setNotice(`${club.name} is no longer linked.`)
      setConfirmUnlink('')
      await load()
    } catch (e) {
      setError(e.message || 'Could not unlink that club')
    } finally {
      setBusy(false)
    }
  }

  const optionLabel = (c) => {
    const g = linkedIds.get(c.id)
    return g ? `${c.name} (already linked to ${g.clubs.length - 1} other${g.clubs.length - 1 === 1 ? '' : 's'})` : c.name
  }

  return (
    <AdminLayout>
      <div className="max-w-2xl mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Linked clubs</h1>
          <p className="text-sm text-pb-dim mt-1 leading-relaxed">
            Link clubs that share people, such as a senior club and its juniors. Every Club Admin of a linked club
            gets a club switcher on their dashboard and can work in any club in the group. Clubs that are not
            linked to another club never see it.
          </p>
          <p className="text-[12px] text-amber-400 mt-2 leading-relaxed">
            Linking gives each club's admins full Club Admin access to the other clubs in the group. Plan, billing
            and payment changes can still only be made by a club's own admins.
          </p>
        </div>

        <div className="pb-card p-5 mb-6">
          {loading ? (
            <p className="font-mono text-[10px] text-pb-faint">loading clubs…</p>
          ) : (
            <>
              <label htmlFor="club-link-a" className={LABEL_CLS}>Club</label>
              <select id="club-link-a" value={clubA} onChange={(e) => setClubA(e.target.value)} className={`${SELECT_CLS} mb-4`}>
                <option value="">Select a club</option>
                {clubs.map((c) => <option key={c.id} value={c.id}>{optionLabel(c)}</option>)}
              </select>

              <label htmlFor="club-link-b" className={LABEL_CLS}>Link it with</label>
              <select id="club-link-b" value={clubB} onChange={(e) => setClubB(e.target.value)} className={`${SELECT_CLS} mb-4`}>
                <option value="">Select a club</option>
                {clubs.filter((c) => c.id !== clubA).map((c) => <option key={c.id} value={c.id}>{optionLabel(c)}</option>)}
              </select>

              <button
                onClick={doLink}
                disabled={!canLink}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40"
                style={{ background: 'var(--pb-accent)' }}
              >
                {busy ? 'WORKING…' : 'LINK CLUBS'}
              </button>
            </>
          )}
          {error && <p className="mt-3 text-[12px] text-pb-red" role="alert">{error}</p>}
          {notice && <p className="mt-3 text-[12px] text-pb-dim" role="status">{notice}</p>}
        </div>

        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Linked groups</h2>
        {!loading && groups.length === 0 && (
          <p className="text-sm text-pb-faint">No clubs are linked yet.</p>
        )}
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.group_id} className="pb-card p-4" data-testid="club-link-group">
              <ul className="divide-y pb-hairline-b">
                {g.clubs.map((c) => (
                  <li key={c.id} className="py-2 flex items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block text-sm text-pb-text truncate">{c.name}</span>
                      <span className="block font-mono text-[10px] text-pb-faintest truncate">
                        /{c.slug}
                        {!c.is_active && ' · inactive, not offered in the switcher'}
                        {c.archived && ' · archived, not offered in the switcher'}
                      </span>
                    </span>
                    {confirmUnlink === c.id ? (
                      <span className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => doUnlink(c)}
                          disabled={busy}
                          className="font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border border-red-500/40 text-pb-red hover:bg-red-500/10 disabled:opacity-40"
                        >
                          CONFIRM UNLINK
                        </button>
                        <button
                          onClick={() => setConfirmUnlink('')}
                          className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text"
                        >
                          CANCEL
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmUnlink(c.id)}
                        disabled={busy}
                        className="shrink-0 font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40"
                      >
                        UNLINK
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {g.clubs.length === 2 && (
                <p className="mt-2 text-[11px] text-pb-faintest">
                  Unlinking either club ends the link for both.
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
