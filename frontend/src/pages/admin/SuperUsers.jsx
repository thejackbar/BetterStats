import { useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { MODULE_TOGGLES } from '../../lib/modules'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

// Mirrors SuperMarketing.jsx's own STATES list (Club Directory).
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']
const norm = (s) => (s || '').toString().toLowerCase()
// "On trial/subscribed" = the module's subscription row is currently trial or active.
const clubHasLiveModule = (club, key) =>
  (club?.module_subscriptions || []).some((s) => s.module === key && (s.status === 'trial' || s.status === 'active'))

// Mirrors backend/app/routers/club_admin.py's _INVITE_EMAIL_RE / _MOBILE_DIGITS_RE.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const MOBILE_STRIP_RE = /[\s\-()]/g
const MOBILE_DIGITS_RE = /^\+?\d{7,15}$/
// Email/mobile are both optional here (unlike the per-club Users page —
// this create form doesn't collect an email, so some accounts have none) —
// blank is fine, but a non-blank value must be well-formed.
const isValidEmail = (v) => !(v || '').trim() || EMAIL_RE.test((v || '').trim())
const isValidMobile = (v) => !(v || '').trim() || MOBILE_DIGITS_RE.test((v || '').replace(MOBILE_STRIP_RE, ''))

export default function SuperUsers() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState([])
  const [clubs, setClubs] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ username: '', password: '', display_name: '', club_id: '', role: 'club_admin' })
  const [resetTarget, setResetTarget] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({ username: '', display_name: '', email: '', mobile_number: '', role: 'club_admin', club_id: '' })
  const [confirmDelete, setConfirmDelete] = useState(null)

  // Club Directory-style search + filters (client-side — both lists are already
  // fetched in full below, same pattern as All Clubs).
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [filterClub, setFilterClub] = useState('')
  const [filterAssociation, setFilterAssociation] = useState('')
  const [filterState, setFilterState] = useState('')
  const [filterPrimaryOnly, setFilterPrimaryOnly] = useState(false)
  const [filterModules, setFilterModules] = useState([])
  const toggleFilterModule = (key) =>
    setFilterModules((m) => (m.includes(key) ? m.filter((k) => k !== key) : [...m, key]))
  const clearFilters = () => {
    setSearch(''); setFilterRole(''); setFilterClub(''); setFilterAssociation('')
    setFilterState(''); setFilterPrimaryOnly(false); setFilterModules([])
  }
  const filtersActive = !!(search || filterRole || filterClub || filterAssociation || filterState || filterPrimaryOnly || filterModules.length)

  const load = () => {
    api.superListUsers().then(setUsers).catch(() => {})
    api.superListClubs().then(setClubs).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const clubById = useMemo(() => Object.fromEntries(clubs.map((c) => [c.id, c])), [clubs])

  const visibleUsers = users.filter((u) => {
    const club = u.club_id ? clubById[u.club_id] : null
    if (search) {
      const hay = `${u.username} ${u.display_name || ''} ${u.email || ''} ${u.mobile_number || ''}`
      if (!norm(hay).includes(norm(search))) return false
    }
    if (filterRole && u.role !== filterRole) return false
    if (filterClub && !norm(u.club_name).includes(norm(filterClub))) return false
    if (filterState && norm(club?.state) !== norm(filterState)) return false
    if (filterAssociation && !norm(club?.association_name).includes(norm(filterAssociation))) return false
    if (filterPrimaryOnly && !u.is_primary_admin) return false
    if (filterModules.length && !filterModules.some((k) => clubHasLiveModule(club, k))) return false
    return true
  })

  const createUser = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      await api.superCreateUser(form)
      setMsg('User created')
      setShowCreate(false)
      setForm({ username: '', password: '', display_name: '', club_id: '', role: 'club_admin' })
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const doResetPassword = async () => {
    if (!resetTarget || newPassword.length < 10) return
    setSaving(true)
    try {
      await api.superResetPassword(resetTarget.id, newPassword)
      setMsg(`Password reset for ${resetTarget.username}`)
      setResetTarget(null)
      setNewPassword('')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const startEdit = (u) => {
    setConfirmDelete(null)
    setResetTarget(null)
    setEditId(u.id)
    setEditForm({
      username: u.username || '',
      display_name: u.display_name || '',
      email: u.email || '',
      mobile_number: u.mobile_number || '',
      role: u.role || 'club_admin',
      club_id: u.club_id || '',
    })
  }

  const saveEdit = async (e) => {
    e.preventDefault()
    setMsg('')
    if (!isValidEmail(editForm.email)) { setMsg('Enter a valid email address'); return }
    if (!isValidMobile(editForm.mobile_number)) { setMsg('Enter a valid mobile number'); return }
    setSaving(true)
    try {
      await api.superUpdateUser(editId, editForm)
      setMsg('User updated')
      setEditId(null)
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteUser = async (u) => {
    setSaving(true)
    setMsg('')
    try {
      await api.superDeleteUser(u.id)
      setMsg(`Deleted ${u.username}`)
      setConfirmDelete(null)
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">Users</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <button
              onClick={() => setShowCreate(s => !s)}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ NEW USER'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createUser} className="pb-card p-4 mb-5 space-y-3">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Create New User</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Username *</label>
                <input required type="text" value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value.toLowerCase() }))}
                  placeholder="e.g. applecross"
                  className={INPUT_CLS + ' font-mono'} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Password * (min 10 chars)</label>
                <input required type="text" value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Display name</label>
                <input type="text" value={form.display_name}
                  onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Club {form.role !== 'sales' && '*'}</label>
                {form.role === 'sales' ? (
                  <div className={INPUT_CLS + ' text-pb-faint'}>Outreach org (automatic)</div>
                ) : (
                  <select required value={form.club_id}
                    onChange={e => setForm(f => ({ ...f, club_id: e.target.value }))}
                    className={INPUT_CLS}>
                    <option value="">Select club…</option>
                    {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                )}
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Role</label>
                <select value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                  className={INPUT_CLS}>
                  <option value="club_admin">Club Admin</option>
                  <option value="super_admin">Super Admin</option>
                  <option value="sales">Sales</option>
                </select>
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Creating…' : 'CREATE USER'}
            </button>
          </form>
        )}

        {resetTarget && (
          <div className="pb-card p-4 mb-5 space-y-3 border-pb-amber/30">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
              Reset password for <span className="text-pb-amber">{resetTarget.username}</span>
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="New password (min 10 chars)"
                className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              />
              <button
                onClick={doResetPassword}
                disabled={saving || newPassword.length < 10}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                Set
              </button>
              <button
                onClick={() => { setResetTarget(null); setNewPassword('') }}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Cancel
              </button>
            </div>
            {newPassword.length >= 10 && (
              <p className="font-mono text-[10px] text-pb-amber">Show this password to the club, then close this screen.</p>
            )}
          </div>
        )}

        <div className="pb-card p-3 mb-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Search</label>
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Name, email, mobile…" className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Role</label>
              <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)} className={INPUT_CLS}>
                <option value="">All roles</option>
                <option value="club_admin">Club Admin</option>
                <option value="super_admin">Super Admin</option>
                <option value="sales">Sales</option>
              </select>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Club</label>
              <input type="text" value={filterClub} onChange={(e) => setFilterClub(e.target.value)}
                placeholder="Club name…" className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Association</label>
              <input type="text" value={filterAssociation} onChange={(e) => setFilterAssociation(e.target.value)}
                placeholder="Name or short code…" className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">State</label>
              <select value={filterState} onChange={(e) => setFilterState(e.target.value)} className={INPUT_CLS}>
                <option value="">All states</option>
                {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex items-end pb-1.5">
              <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                <input type="checkbox" checked={filterPrimaryOnly} onChange={(e) => setFilterPrimaryOnly(e.target.checked)} />
                Primary club admins only
              </label>
            </div>
          </div>
          <div className="mt-3">
            <label className="font-mono text-[10px] text-pb-faint block mb-1">Club on trial / subscribed to</label>
            <div className="flex flex-wrap gap-1.5">
              {MODULE_TOGGLES.filter((t) => t.key !== 'core').map((tog) => {
                const active = filterModules.includes(tog.key)
                return (
                  <button key={tog.key} type="button" onClick={() => toggleFilterModule(tog.key)}
                    className={`px-2 py-1 rounded font-mono text-[10px] border transition-colors ${
                      active ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
                    }`}>
                    {tog.label}
                  </button>
                )
              })}
            </div>
          </div>
          {filtersActive && (
            <button type="button" onClick={clearFilters}
              className="mt-2 font-mono text-[10px] text-pb-faint hover:text-pb-text underline">
              Clear filters
            </button>
          )}
        </div>

        <div className="pb-card overflow-hidden">
          {visibleUsers.length === 0 && (
            <div className="px-5 py-6 text-center font-mono text-[11px] text-pb-faint">
              {users.length === 0 ? 'No users yet' : 'No users match these filters'}
            </div>
          )}
          {visibleUsers.map((u, i) => {
            const isSelf = currentUser?.id === u.id
            return (
              <div key={u.id} className={i > 0 ? 'pb-hairline-t' : ''}>
                <div className="flex items-center justify-between px-5 py-3 hover:bg-pb-surface2">
                  <div className="min-w-0">
                    <span className="text-pb-text text-sm font-mono">{u.username}</span>
                    {u.display_name && <span className="text-pb-faint text-xs ml-2">{u.display_name}</span>}
                    {isSelf && <span className="font-mono text-[9px] ml-2" style={{ color: 'var(--pb-accent)' }}>YOU</span>}
                    {u.is_primary_admin && <span className="font-mono text-[9px] ml-2 text-pb-faint">PRIMARY</span>}
                    <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                      {u.club_name || 'No club'} · {u.role}
                      {u.locked && <span className="ml-2 text-pb-red">Locked</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {u.last_login_at && (
                      <span className="font-mono text-[10px] text-pb-faintest">
                        Last login {new Date(u.last_login_at).toLocaleDateString('en-AU')}
                      </span>
                    )}
                    <button
                      onClick={() => (editId === u.id ? setEditId(null) : startEdit(u))}
                      className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                    >
                      {editId === u.id ? 'Close' : 'Edit'}
                    </button>
                    <button
                      onClick={() => { setResetTarget(u); setNewPassword(''); setEditId(null); setConfirmDelete(null) }}
                      className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                    >
                      Reset password
                    </button>
                    {!isSelf && (
                      <button
                        onClick={() => { setConfirmDelete(u.id); setEditId(null) }}
                        className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>

                {editId === u.id && (
                  <form onSubmit={saveEdit} className="px-5 py-4 bg-pb-surface2/40 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Username</label>
                        <input type="text" value={editForm.username}
                          onChange={e => setEditForm(f => ({ ...f, username: e.target.value.toLowerCase() }))}
                          className={INPUT_CLS + ' font-mono'} />
                      </div>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Display name</label>
                        <input type="text" value={editForm.display_name}
                          onChange={e => setEditForm(f => ({ ...f, display_name: e.target.value }))}
                          className={INPUT_CLS} />
                      </div>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Email</label>
                        <input type="email" value={editForm.email}
                          onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                          className={INPUT_CLS} />
                      </div>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Mobile number</label>
                        <input type="tel" value={editForm.mobile_number}
                          onChange={e => setEditForm(f => ({ ...f, mobile_number: e.target.value }))}
                          className={INPUT_CLS} />
                      </div>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Club</label>
                        {editForm.role === 'sales' ? (
                          <div className={INPUT_CLS + ' text-pb-faint'}>Outreach org (automatic)</div>
                        ) : (
                          <select value={editForm.club_id}
                            onChange={e => setEditForm(f => ({ ...f, club_id: e.target.value }))}
                            className={INPUT_CLS}>
                            <option value="">Select club…</option>
                            {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                          </select>
                        )}
                      </div>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Role</label>
                        <select value={editForm.role}
                          onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}
                          className={INPUT_CLS}>
                          <option value="club_admin">Club Admin</option>
                          <option value="super_admin">Super Admin</option>
                          <option value="sales">Sales</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button type="submit" disabled={saving}
                        className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                        style={{ background: 'var(--pb-accent)' }}>
                        {saving ? 'Saving…' : 'SAVE CHANGES'}
                      </button>
                      <button type="button" onClick={() => setEditId(null)}
                        className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                        Cancel
                      </button>
                    </div>
                  </form>
                )}

                {confirmDelete === u.id && (
                  <div className="px-5 py-4 bg-pb-red/5 border-t border-pb-red/30 space-y-2">
                    <p className="font-mono text-[11px] text-pb-red">
                      Delete user <strong>{u.username}</strong>? They will lose all access immediately.
                      This cannot be undone.
                    </p>
                    <div className="flex gap-2">
                      <button onClick={() => deleteUser(u)} disabled={saving}
                        className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-white bg-pb-red">
                        {saving ? 'Deleting…' : 'DELETE USER'}
                      </button>
                      <button onClick={() => setConfirmDelete(null)}
                        className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </AdminLayout>
  )
}
