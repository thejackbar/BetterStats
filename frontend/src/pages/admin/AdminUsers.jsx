import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { useAuth } from '../../contexts/AuthContext'

// A new user starts with access to everything. A Primary Admin can lock someone to
// one module (a club_member row with access.mode === 'module'). super_admin is
// managed from the Super Admin console, not here.
function roleLabel(u) {
  if (u.role === 'super_admin') return 'Super Admin'
  if (u.is_primary_admin) return 'Primary Admin'
  if (u.access && u.access.mode !== 'full') return 'Limited access'
  return 'Admin' // includes legacy club_member rows from before the lock existed
}

// What a person can open, in the words the Users screen uses.
function accessLabel(u) {
  if (u.access?.mode === 'module') return `${u.access.module_name || 'One module'} only`
  if (u.access?.mode === 'items') {
    const n = u.access.item_count ?? Object.keys(u.access.grants || {}).length
    return `${n} menu item${n === 1 ? '' : 's'}`
  }
  return 'Everything'
}

const NO_LOCK = { mode: 'full', module_key: '', grants: {} }
const asPicker = (access) => {
  if (access?.mode === 'module') return { mode: 'module', module_key: access.module_key || '', grants: {} }
  if (access?.mode === 'items') return { mode: 'items', module_key: '', grants: { ...(access.grants || {}) } }
  return NO_LOCK
}
const asPayload = (v) => {
  if (v.mode === 'module') return { mode: 'module', module_key: v.module_key }
  if (v.mode === 'items') return { mode: 'items', grants: v.grants }
  return { mode: 'full' }
}
const sameGrants = (a, b) => {
  const ka = Object.keys(a || {}).sort()
  const kb = Object.keys(b || {}).sort()
  return ka.length === kb.length && ka.every((k, i) => k === kb[i] && a[k] === b[k])
}
const accessChangedFrom = (start, now) =>
  now.mode !== start.mode ||
  (now.mode === 'module' && now.module_key !== start.module_key) ||
  (now.mode === 'items' && !sameGrants(now.grants, start.grants))

// Switching an item on also switches on what it needs, as the server does when it saves
// (services/access.resolve_grants). Returns the grants and what was added, so the screen
// can say so before anyone saves.
function withNeeds(grants, catalogue) {
  const byId = {}
  for (const m of catalogue) for (const i of m.items) byId[i.id] = i
  const out = { ...grants }
  const added = []
  let changed = true
  while (changed) {
    changed = false
    for (const id of Object.keys(out)) {
      for (const need of byId[id]?.needs || []) {
        const have = out[need.item]
        if (!have || (have === 'view' && need.level === 'manage')) {
          out[need.item] = need.level
          added.push({ item: need.item, name: need.name, level: need.level, because: byId[id].name })
          changed = true
        }
      }
    }
  }
  return { grants: out, added }
}

const LEVELS = [['off', 'Off'], ['view', 'View'], ['manage', 'Manage']]

// One switch per menu item, grouped by module: Off, View or Manage. A module's own
// buttons set every item in it at once. Buttons, not a select, so a row stays one tap
// at phone width, and nothing composite sits inside a <label>.
function ItemSwitches({ catalogue, grants, onChange, disabled }) {
  const [notice, setNotice] = useState('')
  const setLevel = (ids, level) => {
    const next = { ...grants }
    for (const id of ids) {
      if (level === 'off') delete next[id]
      else next[id] = level
    }
    const { grants: full, added } = withNeeds(next, catalogue)
    // An item that something chosen still needs cannot be switched off.
    const kept = ids.filter(id => level === 'off' && full[id])
    const msgs = added.map(a => `${a.because} needs ${a.name}, so ${a.name} is on at ${a.level === 'manage' ? 'Manage' : 'View'}.`)
    setNotice([...new Set(msgs)].join(' ') || (kept.length ? 'Another item you chose needs that one, so it stays on.' : ''))
    onChange(full)
  }
  const count = Object.keys(grants).length
  return (
    <div className="space-y-4" data-testid="item-switches">
      {catalogue.map(m => {
        const ids = m.items.map(i => i.id)
        return (
          <div key={m.key} className="space-y-1.5" data-testid={`module-${m.key}`}>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="font-display font-bold text-sm text-pb-text">{m.name}</span>
              <div className="flex gap-1" role="group" aria-label={`Set every ${m.name} item`}>
                {LEVELS.map(([k, label]) => (
                  <button key={k} type="button" disabled={disabled} data-testid={`module-${m.key}-${k}`}
                    onClick={() => setLevel(ids, k)}
                    className="font-mono text-[9px] tracking-wide2 uppercase px-2 py-1 rounded border border-pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
                    All {label.toLowerCase()}
                  </button>
                ))}
              </div>
            </div>
            <ul className="border border-pb-hairline rounded divide-y divide-pb-hairline">
              {m.items.map(i => {
                const level = grants[i.id] || 'off'
                return (
                  <li key={i.id} className="px-3 py-2 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3" data-testid={`item-${i.id}`}>
                    <div className="min-w-0 flex-1">
                      <div className="text-pb-text text-sm">{i.name}</div>
                      <div className="font-mono text-[10px] text-pb-faintest">{i.menu}</div>
                    </div>
                    <div className="flex gap-1 shrink-0" role="group" aria-label={`${i.name} access`}>
                      {LEVELS.map(([k, label]) => (
                        <button key={k} type="button" disabled={disabled} aria-pressed={level === k}
                          data-testid={`item-${i.id}-${k}`}
                          onClick={() => setLevel([i.id], k)}
                          className={`font-mono text-[10px] tracking-wide2 uppercase px-2.5 py-1.5 rounded border border-pb-hairline disabled:opacity-50 ${level === k ? (k === 'off' ? 'bg-pb-surface2 text-pb-text' : 'bg-pb-accent text-pb-bg') : 'text-pb-faint hover:text-pb-text'}`}>
                          {label}
                        </button>
                      ))}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
      <p className="font-mono text-[10px] text-pb-faintest" data-testid="item-count">
        {count === 0 ? 'Nothing chosen yet.' : `${count} menu item${count === 1 ? '' : 's'} chosen.`}
        {' '}View lets them look but not change anything. They will not see Settings, Users or Plan & Billing.
      </p>
      {notice && <p className="font-mono text-[10px]" style={{ color: 'var(--pb-accent)' }} data-testid="item-notice">{notice}</p>}
    </div>
  )
}

// Everything, one module, or chosen menu items. A plain select for the module; the choice
// between the three is a button group, so nothing composite sits inside a <label>.
function AccessPicker({ value, onChange, modules, catalogue, disabled }) {
  const picked = modules.find(m => m.key === value.module_key)
  const choose = (k) => {
    if (k === 'full') return onChange(NO_LOCK)
    if (k === 'module') return onChange({ mode: 'module', module_key: value.module_key || modules[0]?.key || '', grants: {} })
    // Choose items: starting from a whole module, begin with all of its items on Manage.
    const seed = {}
    if (value.mode === 'module') {
      for (const m of catalogue) if (m.key === value.module_key) for (const i of m.items) seed[i.id] = 'manage'
    }
    onChange({ mode: 'items', module_key: '', grants: value.mode === 'items' ? value.grants : seed })
  }
  const options = [['full', 'Everything'], ['module', 'One module only']]
  if (catalogue.length) options.push(['items', 'Choose items'])
  return (
    <div className="space-y-2" role="group" aria-label="What can they open?" data-testid="access-picker">
      <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">What can they open?</span>
      <div className="flex flex-wrap gap-2">
        {options.map(([k, label]) => (
          <button
            key={k}
            type="button"
            disabled={disabled}
            aria-pressed={value.mode === k}
            data-testid={`access-${k}`}
            onClick={() => choose(k)}
            className={`font-mono text-[10px] tracking-wide2 uppercase px-3 py-1.5 rounded border border-pb-hairline disabled:opacity-50 ${value.mode === k ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {value.mode === 'module' && (
        <div className="space-y-1.5">
          <select
            aria-label="Module"
            data-testid="access-module-select"
            value={value.module_key}
            disabled={disabled}
            onChange={e => onChange({ mode: 'module', module_key: e.target.value, grants: {} })}
            className="w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-sm"
          >
            {modules.map(m => <option key={m.key} value={m.key}>{m.name}</option>)}
          </select>
          {picked && <p className="font-mono text-[10px] text-pb-faintest">{picked.blurb}</p>}
          <p className="font-mono text-[10px] text-pb-faintest">
            They will not see Settings, Users, Plan & Billing or any other module.
          </p>
        </div>
      )}
      {value.mode === 'items' && (
        <ItemSwitches catalogue={catalogue} grants={value.grants} onChange={g => onChange({ ...value, grants: g })} disabled={disabled} />
      )}
    </div>
  )
}

// Mirrors backend/app/routers/club_admin.py's _INVITE_EMAIL_RE / _MOBILE_DIGITS_RE
// so a bad format is caught before the round trip, not just after.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const MOBILE_STRIP_RE = /[\s\-()]/g
const MOBILE_DIGITS_RE = /^\+?\d{7,15}$/
const isValidEmail = (v) => EMAIL_RE.test((v || '').trim())
const isValidMobile = (v) => !v.trim() || MOBILE_DIGITS_RE.test(v.replace(MOBILE_STRIP_RE, ''))
// Mirrors backend/app/services/password_policy.py (MIN_LEN=10, upper/digit/special/match).
const PASSWORD_MIN_LEN = 10
const passwordChecks = (password, confirm) => ({
  length: password.length >= PASSWORD_MIN_LEN,
  upper: /[A-Z]/.test(password),
  digit: /\d/.test(password),
  special: /[^A-Za-z0-9]/.test(password),
  match: !!password && password === confirm,
})

function PasswordChecklist({ checks }) {
  return (
    <ul className="font-mono text-[10px] space-y-0.5 mt-1.5">
      <li className={checks.length ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.length ? '✓' : '·'} At least 10 characters</li>
      <li className={checks.upper ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.upper ? '✓' : '·'} One uppercase letter</li>
      <li className={checks.digit ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.digit ? '✓' : '·'} One number</li>
      <li className={checks.special ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.special ? '✓' : '·'} One special character</li>
      <li className={checks.match ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.match ? '✓' : '·'} Passwords match</li>
    </ul>
  )
}

function fmtDate(iso) {
  if (!iso) return 'never'
  const d = new Date(iso)
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function NewUserForm({ onCreated, onCancel, modules, catalogue, canSetAccess }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [mobileNumber, setMobileNumber] = useState('')
  const [access, setAccess] = useState(NO_LOCK)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!username.trim() || !email.trim()) {
      setErr('Username and email are required')
      return
    }
    if (!isValidEmail(email)) {
      setErr('Enter a valid email address')
      return
    }
    if (!isValidMobile(mobileNumber)) {
      setErr('Enter a valid mobile number')
      return
    }
    if (canSetAccess && access.mode === 'items' && !Object.keys(access.grants).length) {
      setErr('Pick at least one menu item, or choose Everything')
      return
    }
    setBusy(true)
    try {
      await api.adminCreateClubUser({
        username: username.trim(),
        display_name: displayName.trim() || null,
        email: email.trim(),
        mobile_number: mobileNumber.trim() || null,
        role: 'club_admin',
        capabilities: [],
        // Only sent when it limits them: leaving it out means full access, and only
        // the Primary Admin may send a limit.
        ...(canSetAccess && access.mode !== 'full' ? { access: asPayload(access) } : {}),
      })
      onCreated()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="pb-card p-5 space-y-4">
      <h2 className="font-display font-bold text-lg text-pb-text">Invite admin</h2>
      <p className="font-mono text-[10px] text-pb-faintest -mt-2">
        New users start with access to everything. They'll get an email with a link
        to set their own password and activate the account.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Username</span>
          <input value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Display name</span>
          <input value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Email</span>
          <input value={email} onChange={e => setEmail(e.target.value)} type="email" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Mobile number</span>
          <input value={mobileNumber} onChange={e => setMobileNumber(e.target.value)} type="tel" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
      </div>

      {canSetAccess && modules.length > 0 ? (
        <AccessPicker value={access} onChange={setAccess} modules={modules} catalogue={catalogue} disabled={busy} />
      ) : (
        <p className="font-mono text-[10px] text-pb-faintest" data-testid="access-note">
          Only the Primary Admin can limit what someone can open.
        </p>
      )}

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}

      <div className="flex gap-2 pt-2">
        <button type="submit" disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
          {busy ? 'Sending invite…' : 'Send invite'}
        </button>
        <button type="button" onClick={onCancel} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded text-pb-faint hover:text-pb-text border pb-hairline">
          Cancel
        </button>
      </div>
    </form>
  )
}

function UserEditor({ user, currentUserId, onSaved, onClose, modules, catalogue, canSetAccess }) {
  const isSelf = user.id === currentUserId
  const isSuperAdmin = user.role === 'super_admin'
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [email, setEmail] = useState(user.email || '')
  const [mobileNumber, setMobileNumber] = useState(user.mobile_number || '')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const startAccess = asPicker(user.access)
  const [access, setAccess] = useState(startAccess)
  const [busy, setBusy] = useState(false)
  const [sendingReset, setSendingReset] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  // The Primary Admin and Super Admins always have everything, so their access is never edited.
  const accessEditable = canSetAccess && !user.is_primary_admin && !isSuperAdmin && modules.length > 0
  const accessChanged = accessEditable && accessChangedFrom(startAccess, access)
  const itemsEmpty = accessEditable && access.mode === 'items' && !Object.keys(access.grants).length

  const checks = passwordChecks(newPassword, confirmPassword)
  const passwordValid = !newPassword || Object.values(checks).every(Boolean)

  const save = async () => {
    setErr(null); setMsg(null)
    if (!isValidEmail(email)) { setErr('Enter a valid email address'); return }
    if (!isValidMobile(mobileNumber)) { setErr('Enter a valid mobile number'); return }
    if (newPassword && !passwordValid) { setErr('New password does not meet the requirements below'); return }
    if (itemsEmpty) { setErr('Pick at least one menu item, or choose Everything'); return }
    setBusy(true)
    try {
      const payload = { display_name: displayName, email, mobile_number: mobileNumber }
      if (newPassword) {
        payload.password = newPassword
        payload.confirm_password = confirmPassword
      }
      // Only when it changed: an absent key leaves access alone, {mode: 'full'} clears a lock.
      if (accessChanged) payload.access = asPayload(access)
      const res = await api.adminUpdateClubUser(user.id, payload)
      // What was switched on because something chosen needs it, so nobody is surprised.
      const added = Array.isArray(res?.added) ? res.added : []
      setMsg(added.length
        ? `Saved. ${[...new Set(added.map(a => `${a.because} needs ${a.name}, so it is on at ${a.level === 'manage' ? 'Manage' : 'View'}.`))].join(' ')}`
        : 'Saved')
      setNewPassword('')
      setConfirmPassword('')
      onSaved()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const sendResetEmail = async () => {
    setErr(null); setMsg(null)
    setSendingReset(true)
    try {
      await api.adminSendPasswordReset(user.id)
      setMsg(`Password reset email sent to ${user.email || 'the user'}`)
    } catch (e) {
      setErr(e.message)
    } finally {
      setSendingReset(false)
    }
  }

  const remove = async () => {
    if (isSelf) { setErr("Can't remove yourself"); return }
    if (!confirm(`Remove ${user.username} from this club?`)) return
    setBusy(true)
    try {
      await api.adminDeleteClubUser(user.id)
      onSaved()
      onClose()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display font-bold text-lg text-pb-text">{user.display_name || user.username}</h2>
          <p className="font-mono text-[10px] text-pb-faintest">
            @{user.username} · {roleLabel(user)} · last login {fmtDate(user.last_login_at)}
          </p>
        </div>
        <button onClick={onClose} className="text-pb-faint hover:text-pb-text">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      </div>

      {isSuperAdmin && (
        <p className="font-mono text-[10px] text-pb-faintest">Super admin — manage role from the Super Admin console.</p>
      )}

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Display name</span>
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" />
      </label>

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Email</span>
        <input value={email} onChange={e => setEmail(e.target.value)} type="email" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
      </label>

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Mobile number</span>
        <input value={mobileNumber} onChange={e => setMobileNumber(e.target.value)} type="tel" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
      </label>

      <div className="pb-hairline-t pt-3 space-y-2">
        {accessEditable ? (
          <AccessPicker value={access} onChange={setAccess} modules={modules} catalogue={catalogue} disabled={busy} />
        ) : (
          <p className="font-mono text-[10px] text-pb-faintest" data-testid="access-readonly">
            Can open: {user.is_primary_admin || isSuperAdmin ? 'Everything (always)' : accessLabel(user)}
            {!canSetAccess && !user.is_primary_admin && !isSuperAdmin ? '. Only the Primary Admin can change this.' : ''}
          </p>
        )}
      </div>

      <div className="pb-hairline-t pt-3 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Reset password</span>
          <button type="button" onClick={sendResetEmail} disabled={sendingReset || busy || !user.email}
            title={user.email ? 'Email this user a link to reset their password' : 'This user has no email address on file'}
            className="font-mono text-[10px] tracking-wide2 uppercase px-2.5 py-1.5 rounded text-pb-accent hover:bg-pb-accent/10 border pb-hairline disabled:opacity-50 whitespace-nowrap">
            {sendingReset ? 'Sending…' : 'Email reset link'}
          </button>
        </div>
        <label className="block">
          <input value={newPassword} onChange={e => setNewPassword(e.target.value)} type="password" placeholder="Set new password directly (leave blank to keep current)" className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
        </label>
        {newPassword && (
          <>
            <label className="block">
              <input value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} type="password" placeholder="Confirm new password" className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
            </label>
            <PasswordChecklist checks={checks} />
          </>
        )}
      </div>

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}
      {msg && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</div>}

      <div className="flex gap-2 pt-2">
        <button onClick={save} disabled={busy || !passwordValid || itemsEmpty} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
          {busy ? 'Saving…' : 'Save'}
        </button>
        {!isSelf && !isSuperAdmin && (
          <button onClick={remove} disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded text-pb-red hover:bg-pb-red/10 border pb-hairline ml-auto">
            Remove
          </button>
        )}
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [selected, setSelected] = useState(null)
  const [creating, setCreating] = useState(false)
  const [modules, setModules] = useState([])
  const [catalogue, setCatalogue] = useState([])
  // The Primary Admin (and a Super Admin) decide what each person can open.
  const canSetAccess = !!me?.is_primary_admin

  const reload = async () => {
    setLoading(true)
    try {
      setUsers(await api.adminListClubUsers())
      setErr(null)
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { reload() }, [])
  useEffect(() => {
    api.adminListCapabilities().then(r => {
      setModules(Array.isArray(r?.modules) ? r.modules : [])
      setCatalogue(Array.isArray(r?.catalogue) ? r.catalogue : [])
    }).catch(() => { setModules([]); setCatalogue([]) })
  }, [])

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-start justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Club Users</h1>
          <button
            onClick={() => { setCreating(true); setSelected(null) }}
            className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg"
          >
            + Add user
          </button>
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          New users start with access to everything. The Primary Admin can limit someone to one
          module, such as BetterSelect only. What a club can use also depends on its plan.
        </p>

        {err && <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{err}</div>}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="pb-card overflow-hidden">
            {loading && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
            {!loading && users.map((u, i) => (
              <button
                key={u.id}
                onClick={() => { setSelected(u); setCreating(false) }}
                className={`w-full text-left px-5 py-3 flex items-center gap-3 transition ${i > 0 ? 'pb-hairline-t' : ''} ${selected?.id === u.id ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-pb-text text-sm font-medium truncate">{u.display_name || u.username}</span>
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">{roleLabel(u)}</span>
                    {u.access && u.access.mode !== 'full' && (
                      <span className="font-mono text-[9px] px-1.5 py-0.5 rounded text-pb-accent bg-pb-accent/10" data-testid="access-badge">{accessLabel(u)}</span>
                    )}
                    {u.id === me?.id && <span className="font-mono text-[9px] text-pb-faintest">(you)</span>}
                  </div>
                  <p className="font-mono text-[10px] text-pb-faintest mt-0.5">
                    @{u.username} · last login {fmtDate(u.last_login_at)}
                  </p>
                </div>
              </button>
            ))}
          </div>

          <div>
            {creating && <NewUserForm modules={modules} catalogue={catalogue} canSetAccess={canSetAccess} onCreated={() => { setCreating(false); reload() }} onCancel={() => setCreating(false)} />}
            {!creating && selected && (
              <UserEditor
                key={selected.id}
                user={selected}
                currentUserId={me?.id}
                modules={modules}
                catalogue={catalogue}
                canSetAccess={canSetAccess}
                onSaved={async () => { await reload() }}
                onClose={() => setSelected(null)}
              />
            )}
            {!creating && !selected && (
              <div className="pb-card p-8 text-center font-mono text-[11px] text-pb-faint">
                Select a user to edit, or click + Add user.
              </div>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
