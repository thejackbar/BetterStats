import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { nameMatchesSearch, formatPlayerName, joinDisplayName, nameSortKey } from '../../lib/nameFormat'
import { ALPHABET, RANGES, letterOfName, rangeOfName, groupByLetter } from '../../lib/playerAlphabet'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { PbSpinner } from '../../lib/presskit'
import { bowls, bowlingLabel } from '../../lib/playerAttributes'
import { Profile, draftFromProfile, patchFromDraft } from '../../components/player/PlayerProfilePanel'
import { Avatar, RoleChips, Icon, QuickAvailModal } from './betterselect/ui'
import PlayerMerchPanel from './bettermerch/PlayerMerchPanel'
import '../../styles/players-list.css'

// ---------------------------------------------------------------------------
// Meta line — the useful role / batting-hand / bowling summary that REPLACES
// the old raw-UUID + "PHQ: …" clutter on every row.
// ---------------------------------------------------------------------------
const ROLE_NOUN = {
  'Batter': 'Batter', 'Bowler': 'Bowler', 'All Rounder': 'All-rounder',
  'Allrounder': 'All-rounder', 'All-Rounder': 'All-rounder',
  'Wicketkeeper': 'Keeper', 'Wicketkeeper-Batter': 'Keeper-bat', 'Keeper': 'Keeper',
}
function roleNoun(p) {
  if (p.is_opening_batsman) return 'Opening bat'
  return ROLE_NOUN[p.player_role] || p.player_role || ''
}
function metaLine(p) {
  const bits = []
  const r = roleNoun(p)
  if (r) bits.push(r)
  if (p.batting_hand === 'LEFT') bits.push('LHB')
  else if (p.batting_hand === 'RIGHT') bits.push('RHB')
  if (bowls(p.bowling_action, p.bowling_type)) bits.push(bowlingLabel(p.bowling_action, p.bowling_type))
  return bits.join(' · ')
}

const nameOf = (p) => p.display_name || p.display_name_override || p.name || ''

// ---------------------------------------------------------------------------
// ProfileModal — the canonical player profile (shared with BetterSelect), shown
// in a modal with prev/next player navigation so you can flip through the list
// without closing. The detail panel itself is unchanged.
// ---------------------------------------------------------------------------
function ProfileModal({ playerId, teams, canEdit, index, total, onPrev, onNext, onClose, onSaved }) {
  const { hasModule, hasCapability } = useAuth()
  const showMerch = hasModule('merch') && hasCapability(CAP.MANAGE_MERCH)
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState('')
  const [availEdit, setAvailEdit] = useState(null) // { player, date }

  // Esc closes; ← / → flip players (ignored while typing in a field).
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') { onClose(); return }
      const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)
      if (typing) return
      if (e.key === 'ArrowLeft') onPrev?.()
      else if (e.key === 'ArrowRight') onNext?.()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, onPrev, onNext])

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

  // The action shot never appears on a list row — only the headshot does — so
  // this reflects into the open panel alone.
  const onHeroPhotoChange = useCallback((url) => {
    setProfile((p) => p ? { ...p, hero_photo_url: url } : p)
  }, [])

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
        <div className="pl-root pb-card bg-pb-surface w-full max-w-5xl mt-8 mb-8 max-h-[88vh] overflow-hidden flex flex-col">
          {total > 1 && (
            <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-pb-hairline shrink-0">
              <div className="pm-nav">
                <button onClick={onPrev} title="Previous player (←)" disabled={total < 2}>
                  <Icon name="chevron" size={16} style={{ transform: 'rotate(180deg)' }} />
                </button>
                <span>{index + 1} <i>/ {total}</i></span>
                <button onClick={onNext} title="Next player (→)" disabled={total < 2}>
                  <Icon name="chevron" size={16} />
                </button>
              </div>
              <span className="font-mono text-[10px] text-pb-faint tracking-wide2">← → TO FLIP · ESC TO CLOSE</span>
            </div>
          )}
          {err && <div className="px-5 py-2 font-mono text-[11px] text-pb-red border-b border-pb-hairline shrink-0">{err.toUpperCase()}</div>}
          {!profileForView || !draft
            ? <div className="p-10"><PbSpinner message="Loading profile…" /></div>
            : <Profile profile={profileForView} draft={draft} setDraft={setDraft}
                dirty={dirty} saved={saved} onSave={onSave} canEdit={canEdit}
                canEditAvail={canEdit} onEditAvail={(pl, date) => setAvailEdit({ player: pl, date })}
                onClose={onClose} onPhotoChange={onPhotoChange} onHeroPhotoChange={onHeroPhotoChange}
                footer={showMerch ? <PlayerMerchPanel playerId={playerId} /> : null} />}
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
// Row
// ---------------------------------------------------------------------------
function PlayerRow({ p, squadName, canEdit, fmt, onOpen }) {
  const inactive = p.status === 'inactive'
  const meta = metaLine(p)
  return (
    <div className="pl-row" style={{ opacity: inactive ? 0.62 : 1 }} onClick={onOpen}>
      <Avatar player={p} size={40} noLink />
      <div className="pl-row-main">
        <div className="pl-row-top">
          <span className="pl-row-name">{fmt(p.display_name_override || p.name)}</span>
          <RoleChips roles={p.skill_positions || []} muted />
          {p.is_overseas && (
            <span className="pl-badge globe" title={p.overseas_country ? `Overseas — ${p.overseas_country}` : 'Overseas'}>
              <Icon name="info" size={11} /> Overseas
            </span>
          )}
          {inactive && <span className="pl-badge mute">Inactive</span>}
          {p.is_public === false && (
            <span className="pl-badge mute" title="Kept off the club's public website">Hidden</span>
          )}
        </div>
        {meta && <div className="pl-row-meta">{meta}</div>}
      </div>
      {squadName && <span className="pl-squad">{squadName}</span>}
      <button className="pl-edit" onClick={(e) => { e.stopPropagation(); onOpen() }}>
        <Icon name="player" size={13} /> {canEdit ? 'Edit' : 'View'}
      </button>
    </div>
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
  const [scope, setScope] = useState('all') // all | local | overseas | hidden
  const [range, setRange] = useState('ALL')
  const [msg, setMsg] = useState('')
  const [nameFormat, setNameFormat] = useState('last_first')
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ first_name: '', last_name: '', playhq_id: '', display_first: '', display_last: '' })
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState('')
  const [editingId, setEditingId] = useState(null) // player id or null

  const scrollRef = useRef(null)
  const headerRefs = useRef({})
  const pendingJump = useRef(null)

  useEffect(() => {
    api.adminListPlayers().then(setPlayers).catch(() => {})
    api.adminGetSettings().then(s => setNameFormat(s.player_name_format || 'last_first')).catch(() => {})
    api.bsListTeams().then(t => setTeams(t || [])).catch(() => setTeams([]))
  }, [])

  const searching = filter.trim().length > 0
  const teamNameById = useMemo(() => Object.fromEntries(teams.map((t) => [t.id, t.name])), [teams])
  const squadNameOf = useCallback((p) => (p.squad_team_id ? teamNameById[p.squad_team_id] : null), [teamNameById])

  // Base set: scope + search, surname-sorted. Range filtering happens after.
  const base = useMemo(() => {
    const out = players.filter((p) => {
      if (scope === 'local' && p.is_overseas) return false
      if (scope === 'overseas' && !p.is_overseas) return false
      // "Hidden" is the club's own list of who it keeps off the public site
      // — the one place those players are easy to find and put back.
      if (scope === 'hidden' && p.is_public !== false) return false
      const q = filter.trim()
      if (!q) return true
      return (
        nameMatchesSearch(p.name, q) ||
        nameMatchesSearch(p.display_name_override, q) ||
        (p.playhq_id || '').toLowerCase().includes(q.toLowerCase())
      )
    })
    return out.sort((a, b) => nameSortKey(nameOf(a)).localeCompare(nameSortKey(nameOf(b))))
  }, [players, scope, filter])

  // Counts per range over the base set (drives the tab labels).
  const rangeCounts = useMemo(() => {
    const m = {}; RANGES.forEach((r) => (m[r.key] = 0))
    base.forEach((p) => { const k = rangeOfName(nameOf(p)); m[k] = (m[k] || 0) + 1 })
    return m
  }, [base])

  // What's actually shown — range slice unless searching (then all matches).
  const shown = useMemo(() => {
    if (searching || range === 'ALL') return base
    return base.filter((p) => rangeOfName(nameOf(p)) === range)
  }, [base, searching, range])

  const groups = useMemo(() => groupByLetter(shown, nameOf), [shown])
  const letterSet = useMemo(() => new Set(base.map((p) => letterOfName(nameOf(p)))), [base])
  const fmt = useCallback((name) => formatPlayerName(name, nameFormat), [nameFormat])

  const scrollToLetter = useCallback((letter) => {
    const el = headerRefs.current[letter]; const sc = scrollRef.current
    if (el && sc) sc.scrollTop = Math.max(0, el.offsetTop - 4)
  }, [])

  // Finish a cross-range jump once the new range has rendered its headers.
  useEffect(() => {
    if (pendingJump.current) { scrollToLetter(pendingJump.current); pendingJump.current = null }
  }, [range, shown, scrollToLetter])

  const jumpTo = useCallback((letter) => {
    if (!searching && range !== 'ALL') {
      const r = RANGES.find((rg) => letter >= rg.from && letter <= rg.to)
      if (r && r.key !== range) { pendingJump.current = letter; setRange(r.key); return }
    }
    scrollToLetter(letter)
  }, [searching, range, scrollToLetter])

  // Modal navigation flips through the shown list, wrapping.
  const shownIds = useMemo(() => shown.map((p) => p.id), [shown])
  const editingIndex = editingId ? shownIds.indexOf(editingId) : -1
  const moveModal = useCallback((d) => {
    if (!shownIds.length) return
    const i = shownIds.indexOf(editingId)
    const next = ((i < 0 ? 0 : i) + d + shownIds.length) % shownIds.length
    setEditingId(shownIds[next])
  }, [shownIds, editingId])

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
        display_name_override: joinDisplayName(createForm.display_first, createForm.display_last) || null,
      }
      const created = await api.adminCreatePlayer(payload)
      setPlayers(ps => [...ps, created])
      setCreateForm({ first_name: '', last_name: '', playhq_id: '', display_first: '', display_last: '' })
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
    <BetterStatsLayout>
      {editingId && (
        <ProfileModal
          playerId={editingId}
          teams={teams}
          canEdit={canEdit}
          index={editingIndex}
          total={shownIds.length}
          onPrev={() => moveModal(-1)}
          onNext={() => moveModal(1)}
          onClose={() => setEditingId(null)}
          onSaved={handleModalSaved}
        />
      )}

      <div className="pl-root max-w-[1100px] mx-auto">
        {/* Page head */}
        <div className="pl-pagehead">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text">Players</h1>
            <div className="pl-sub">{base.length.toLocaleString()} players{scope !== 'all' ? ` · ${scope}` : ''}</div>
          </div>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px] tracking-wide2" style={{ color: 'var(--pb-accent)' }}>{msg.toUpperCase()}</span>}
            {canEdit && (
              <Link
                to="/admin/players/import"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-display font-semibold text-[13.5px] text-pb-text border border-pb-hairline hover:border-pb-accent"
                title="Bulk-fill emails, phones and more from a spreadsheet"
              >
                <Icon name="sheet" size={16} /> Import CSV
              </Link>
            )}
            <button
              onClick={() => { setShowCreate(v => !v); setCreateMsg('') }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-display font-semibold text-[13.5px] text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'Cancel' : <><Icon name="plus" size={16} /> Add player</>}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={submitCreate} className="pb-card px-5 py-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">New Player</p>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">First Name *</label>
                <input autoFocus type="text" value={createForm.first_name} required
                  onChange={e => setCreateForm(f => ({ ...f, first_name: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. John" />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">Last Name *</label>
                <input type="text" value={createForm.last_name} required
                  onChange={e => setCreateForm(f => ({ ...f, last_name: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. Smith" />
              </div>
            </div>
            <div className="mb-3">
              <label className="font-mono text-[10px] text-pb-faintest block mb-1">Player ID (optional)</label>
              <input type="text" value={createForm.playhq_id}
                onChange={e => setCreateForm(f => ({ ...f, playhq_id: e.target.value }))}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-amber"
                placeholder="e.g. a1b2c3d4-e5f6-…" />
            </div>
            <div className="mb-3">
              <label className="font-mono text-[10px] text-pb-faintest block mb-1">Display name override (optional)</label>
              <div className="grid grid-cols-2 gap-3">
                <input type="text" value={createForm.display_first}
                  onChange={e => setCreateForm(f => ({ ...f, display_first: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="Display first name" />
                <input type="text" value={createForm.display_last}
                  onChange={e => setCreateForm(f => ({ ...f, display_last: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="Display last name" />
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mt-1">Leave blank to show the synced name. Sorted by surname.</p>
            </div>
            <div className="flex items-center gap-3">
              <button type="submit" disabled={creating}
                className="px-4 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}>
                {creating ? 'CREATING…' : 'CREATE PLAYER'}
              </button>
              {createMsg && <span className="font-mono text-[11px] text-pb-red">{createMsg}</span>}
            </div>
          </form>
        )}

        {/* Search */}
        <div className="pl-search">
          <Icon name="search" size={18} style={{ color: 'var(--pb-faint)' }} />
          <input value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="Search by name (first or last, any order)…" />
          {filter && <button className="pl-clear" onClick={() => setFilter('')}><Icon name="close" size={15} /></button>}
        </div>

        {/* Controls: scope + alphabet ranges */}
        <div className="pl-controls">
          <div className="inline-flex flex-wrap p-[3px] gap-0.5 bg-pb-surface2 rounded-lg border border-pb-hairline">
            {[{ value: 'all', label: 'All' }, { value: 'local', label: 'Local' }, { value: 'overseas', label: 'Overseas' }, { value: 'hidden', label: 'Hidden' }].map((o) => {
              const active = o.value === scope
              return (
                <button key={o.value} type="button" onClick={() => setScope(o.value)}
                  className={`rounded-md font-display font-semibold text-[13px] px-3 py-1.5 transition ${active ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>
                  {o.label}
                </button>
              )
            })}
          </div>
          {!searching && (
            <div className="pl-ranges">
              <button
                className={`pl-rangetab${range === 'ALL' ? ' on' : ''}`}
                onClick={() => { setRange('ALL'); if (scrollRef.current) scrollRef.current.scrollTop = 0 }}>
                All<i>{base.length}</i>
              </button>
              {RANGES.map((r) => (
                <button key={r.key}
                  className={`pl-rangetab${range === r.key ? ' on' : ''}${!rangeCounts[r.key] ? ' empty' : ''}`}
                  onClick={() => { setRange(r.key); if (scrollRef.current) scrollRef.current.scrollTop = 0 }}>
                  {r.label}<i>{rangeCounts[r.key] || 0}</i>
                </button>
              ))}
            </div>
          )}
          <div className="pl-shown">{searching ? `${shown.length} match${shown.length === 1 ? '' : 'es'}` : `${shown.length} shown`}</div>
        </div>

        {/* List + jump rail */}
        <div className="pl-listwrap" style={{ height: 'calc(100vh - 320px)', minHeight: 360 }}>
          <div ref={scrollRef} className="pl-scroll bs-scroll sb-prominent">
            {groups.length === 0 && (
              <div className="pl-empty">{searching ? `No players match “${filter}”.` : 'No players in this range.'}</div>
            )}
            {groups.map(([L, list]) => (
              <section key={L}>
                <div className="pl-letterhead" ref={(el) => { headerRefs.current[L] = el }}>
                  <span>{L}</span><i>{list.length}</i>
                </div>
                {list.map((p) => (
                  <PlayerRow key={p.id} p={p} squadName={squadNameOf(p)} canEdit={canEdit} fmt={fmt} onOpen={() => setEditingId(p.id)} />
                ))}
              </section>
            ))}
          </div>

          {!searching && (
            <div className="pl-rail">
              {ALPHABET.map((L) => {
                const has = letterSet.has(L)
                const here = groups.some(([g]) => g === L)
                return (
                  <button key={L} className={`pl-rail-l${here ? ' here' : ''}${has ? '' : ' off'}`}
                    disabled={!has} onClick={() => jumpTo(L)}>{L}</button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </BetterStatsLayout>
  )
}
