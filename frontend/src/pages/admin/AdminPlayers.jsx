import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { nameMatchesSearch, formatPlayerName } from '../../lib/nameFormat'
import { countryFlagUrl } from '../../data/countries'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { PbSpinner } from '../../lib/presskit'
import { Profile, draftFromProfile, patchFromDraft } from '../../components/player/PlayerProfilePanel'
import { QuickAvailModal } from './betterselect/ui'

// ---------------------------------------------------------------------------
// ProfileModal — the canonical player profile (shared with BetterSelect),
// shown in a modal. Replaces the old cramped edit form so editing a player is
// the same experience everywhere.
// ---------------------------------------------------------------------------
function ProfileModal({ playerId, teams, canEdit, onClose, onSaved }) {
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState('')
  const [availEdit, setAvailEdit] = useState(null) // { player, date }

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    let live = true
    setProfile(null); setDraft(null); setErr('')
    api.bsGetPlayerProfile(playerId)
      .then((p) => { if (live) { setProfile(p); setDraft(draftFromProfile(p)) } })
      .catch((e) => { if (live) setErr(e.message || 'Could not load profile') })
    return () => { live = false }
  }, [playerId])

  const dirty = useMemo(() => {
    if (!profile || !draft) return false
    return JSON.stringify(patchFromDraft(draftFromProfile(profile))) !== JSON.stringify(patchFromDraft(draft))
  }, [profile, draft])

  const onSave = async () => {
    if (!draft || saving) return
    setSaving(true); setErr('')
    try {
      const updated = await api.bsUpdatePlayerProfile(playerId, patchFromDraft(draft))
      setProfile(updated)
      setDraft(draftFromProfile(updated))
      setSaved(true)
      setTimeout(() => setSaved(false), 1800)
      onSaved?.(updated)
    } catch (e) {
      setErr(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const onPhotoChange = useCallback((url) => {
    setProfile((p) => p ? { ...p, photo_url: url } : p)
    onSaved?.({ id: playerId, photo_url: url })
  }, [playerId, onSaved])

  // Availability editing — same quick-update flow as BetterSelect. Persists one
  // (player, date) row, then re-pulls the profile so the snapshot dot updates.
  const pickAvail = async (status) => {
    const ed = availEdit
    setAvailEdit(null)
    if (!ed?.player || !ed?.date) return
    try {
      await api.bsSetAvailability({ player_id: ed.player.id, date: ed.date, status })
      const fresh = await api.bsGetPlayerProfile(playerId)
      setProfile(fresh)
    } catch (e) {
      setErr(e.message || 'Could not update availability')
    }
  }
  const availEntry = availEdit
    ? (profile?.snapshot?.availability_next || []).find((a) => a.date === availEdit.date)
    : null

  const profileForView = profile ? { ...profile, _teams: teams } : null

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4"
        style={{ backdropFilter: 'blur(2px)' }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      >
        <div className="pb-card bg-pb-surface w-full max-w-5xl mt-8 mb-8 max-h-[88vh] overflow-hidden flex flex-col">
          {err && <div className="px-5 py-2 font-mono text-[11px] text-pb-red border-b border-pb-hairline shrink-0">{err.toUpperCase()}</div>}
          {!profileForView || !draft
            ? <div className="p-10"><PbSpinner message="Loading profile…" /></div>
            : <Profile profile={profileForView} draft={draft} setDraft={setDraft}
                dirty={dirty} saved={saved} onSave={onSave} canEdit={canEdit}
                canEditAvail={canEdit} onEditAvail={(pl, date) => setAvailEdit({ player: pl, date })}
                onClose={onClose} onPhotoChange={onPhotoChange} />}
        </div>
      </div>
      {availEdit && (
        <QuickAvailModal
          player={availEdit.player}
          dateLabel={availEntry?.label || availEdit.date}
          current={availEntry?.status || 'NO_RESPONSE'}
          onPick={pickAvail}
          onClose={() => setAvailEdit(null)} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// AdminPlayers
// ---------------------------------------------------------------------------

export default function AdminPlayers() {
  const { hasCapability } = useAuth()
  const canEdit = hasCapability(CAP.MANAGE_PLAYERS)
  const [players, setPlayers] = useState([])
  const [teams, setTeams] = useState([])
  const [filter, setFilter] = useState('')
  const [overseasFilter, setOverseasFilter] = useState('all') // 'all' | 'only' | 'exclude'
  const [msg, setMsg] = useState('')
  const [nameFormat, setNameFormat] = useState('last_first')
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ first_name: '', last_name: '', playhq_id: '', display_name_override: '' })
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState('')
  const [editingId, setEditingId] = useState(null) // player id or null

  useEffect(() => {
    api.adminListPlayers().then(setPlayers).catch(() => {})
    api.adminGetSettings().then(s => setNameFormat(s.player_name_format || 'last_first')).catch(() => {})
    api.bsListTeams().then(t => setTeams(t || [])).catch(() => setTeams([]))
  }, [])

  const fmt = (name) => formatPlayerName(name, nameFormat)

  const filtered = players.filter(p => {
    if (overseasFilter === 'only' && !p.is_overseas) return false
    if (overseasFilter === 'exclude' && p.is_overseas) return false
    const q = filter.trim()
    if (!q) return true
    return (
      nameMatchesSearch(p.name, q) ||
      nameMatchesSearch(p.display_name_override, q) ||
      (p.playhq_id || '').toLowerCase().includes(q.toLowerCase())
    )
  })

  // Merge whatever the modal sends back (a full profile on save, or a partial
  // { id, photo_url } on photo change) into the matching list row.
  const handleModalSaved = useCallback((updated) => {
    if (!updated?.id) return
    setPlayers(ps => ps.map(p => p.id === updated.id ? { ...p, ...updated } : p))
  }, [])

  const submitCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    setCreateMsg('')
    try {
      const payload = {
        first_name: createForm.first_name.trim(),
        last_name: createForm.last_name.trim(),
        playhq_id: createForm.playhq_id.trim() || null,
        display_name_override: createForm.display_name_override.trim() || null,
      }
      const created = await api.adminCreatePlayer(payload)
      setPlayers(ps => [...ps, created].sort((a, b) => a.name.localeCompare(b.name)))
      setCreateForm({ first_name: '', last_name: '', playhq_id: '', display_name_override: '' })
      setShowCreate(false)
      setMsg('Player created')
      setTimeout(() => setMsg(''), 2500)
    } catch (err) {
      setCreateMsg(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <AdminLayout>
      {editingId && (
        <ProfileModal
          playerId={editingId}
          teams={teams}
          canEdit={canEdit}
          onClose={() => setEditingId(null)}
          onSaved={handleModalSaved}
        />
      )}

      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">Players</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px] tracking-wide2" style={{ color: 'var(--pb-accent)' }}>{msg.toUpperCase()}</span>}
            <button
              onClick={() => { setShowCreate(v => !v); setCreateMsg('') }}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ ADD PLAYER'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={submitCreate} className="pb-card px-5 py-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">New Player</p>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">First Name *</label>
                <input
                  autoFocus
                  type="text"
                  value={createForm.first_name}
                  onChange={e => setCreateForm(f => ({ ...f, first_name: e.target.value }))}
                  required
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. John"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">Last Name *</label>
                <input
                  type="text"
                  value={createForm.last_name}
                  onChange={e => setCreateForm(f => ({ ...f, last_name: e.target.value }))}
                  required
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. Smith"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">PlayHQ ID (optional)</label>
                <input
                  type="text"
                  value={createForm.playhq_id}
                  onChange={e => setCreateForm(f => ({ ...f, playhq_id: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-amber"
                  style={{ '--tw-border-opacity': 1 }}
                  placeholder="e.g. a1b2c3d4-e5f6-..."
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">Display name override (optional)</label>
                <input
                  type="text"
                  value={createForm.display_name_override}
                  onChange={e => setCreateForm(f => ({ ...f, display_name_override: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="Custom display name"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={creating}
                className="px-4 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}
              >
                {creating ? 'CREATING…' : 'CREATE PLAYER'}
              </button>
              {createMsg && <span className="font-mono text-[11px] text-pb-red">{createMsg}</span>}
            </div>
          </form>
        )}

        <div className="relative mb-4">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search by name (any order), display name or PHQ ID…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="w-full bg-pb-surface border pb-hairline rounded pl-9 pr-4 py-2.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
          />
        </div>

        <div className="flex items-center gap-2 mb-4">
          <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Overseas</span>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: 'all',     label: 'All' },
              { value: 'exclude', label: 'Local' },
              { value: 'only',    label: 'Overseas' },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => setOverseasFilter(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  overseasFilter === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <span className="font-mono text-[10px] text-pb-faintest ml-1">
            Click <span style={{ color: 'var(--pb-accent)' }}>{canEdit ? 'Edit' : 'View'}</span> on any player to open their profile.
          </span>
        </div>

        <div className="pb-card overflow-hidden">
          {filtered.length === 0 && (
            <div className="px-5 py-8 text-center text-pb-faint font-mono text-[11px]">No players found</div>
          )}
          {filtered.map((p, i) => (
            <div key={p.id} className={`px-5 py-3.5 flex items-start justify-between gap-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="min-w-0 flex items-center gap-3">
                {p.photo_url && (
                  <img
                    src={p.photo_url}
                    alt=""
                    className="w-8 h-8 rounded-full object-cover shrink-0 border pb-hairline"
                  />
                )}
                <div>
                  <p className="text-pb-text text-sm font-medium">
                    {p.display_name_override || fmt(p.name)}
                    {p.display_name_override && (
                      <span className="ml-2 font-mono text-[10px] text-pb-faint">(raw: {p.name})</span>
                    )}
                  </p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                    <span className="font-mono text-[10px] text-pb-faintest">{p.id}</span>
                    {p.playhq_id ? (
                      <span className="font-mono text-[10px] text-pb-amber/70">PHQ: {p.playhq_id}</span>
                    ) : (
                      <span className="font-mono text-[10px] text-pb-faintest italic">no PHQ ID</span>
                    )}
                    {p.gender && (
                      <span className="font-mono text-[10px] text-pb-faint">{p.gender}</span>
                    )}
                    {p.player_role && (
                      <span className="font-mono text-[10px] text-pb-faint">{p.player_role}</span>
                    )}
                    {p.is_player === false && (
                      <span className="font-mono text-[10px] text-pb-faintest italic">non-player</span>
                    )}
                    {p.is_overseas && (
                      <span className="inline-flex items-center gap-1 font-mono text-[10px] text-pb-amber/80">
                        {p.overseas_country && countryFlagUrl(p.overseas_country) && (
                          <img src={countryFlagUrl(p.overseas_country)} alt="" style={{ width: 14, height: 'auto' }} />
                        )}
                        {p.overseas_country || 'Overseas'}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={() => setEditingId(p.id)}
                className="font-mono text-[10px] px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text transition-colors shrink-0"
              >
                {canEdit ? 'Edit' : 'View'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
