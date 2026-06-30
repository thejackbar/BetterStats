import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import { MODULE_TOGGLES, MODULE_INFO, SUBSCRIPTION_STATUSES, BILLING_CYCLES, statusLabel, statusIsLive } from '../../lib/modules'
import AdminLayout from '../../components/admin/AdminLayout'
import Dropdown from '../../components/Dropdown'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

// module key -> display name (e.g. 'iq' -> 'BetterIQ')
const MODULE_NAME = Object.fromEntries(MODULE_INFO.map(m => [m.key, m.name]))
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-AU') : '—')

const EMPTY_FORM = { org_id: '', name: '', slug: '', short_name: '', contact_email: '' }

export default function SuperClubs() {
  const [clubs, setClubs] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({
    name: '', slug: '', short_name: '', contact_email: '',
    module_overrides: [], subscription_status: 'active', renewal_date: '', billing_cycle: '',
    default_trial_days: 14,
  })
  const [moduleBusy, setModuleBusy] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [syncing, setSyncing] = useState(null)

  // Club search (same source as the public onboarding flow)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef(null)
  const searchWrapRef = useRef(null)

  const load = () => api.superListClubs().then(setClubs).catch(() => {})
  useEffect(() => { load() }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (form.org_id) return
    if (!query || query.trim().length < 2) {
      setResults([])
      setShowResults(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await api.searchOrgs(query.trim())
        setResults(Array.isArray(data) ? data : [])
        setShowResults(true)
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [query, form.org_id])

  const orgName = (org) => org.name || org.shortName || org.organisationName || org.id || ''

  const selectOrg = (org) => {
    const name = orgName(org)
    setForm(f => ({
      ...f,
      org_id: org.id,
      name,
      slug: f.slug || name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''),
      short_name: f.short_name || org.shortName || '',
    }))
    setQuery(name)
    setShowResults(false)
    setResults([])
  }

  const handleQueryChange = (e) => {
    setForm(f => ({ ...f, org_id: '' }))
    setQuery(e.target.value)
  }

  const resetCreate = () => {
    setForm(EMPTY_FORM)
    setQuery('')
    setResults([])
    setShowResults(false)
  }

  const toggleActive = async (club) => {
    try {
      await api.superPatchClub(club.id, { is_active: !club.is_active })
      load()
    } catch (err) {
      setMsg(err.message)
    }
  }

  const createClub = async (e) => {
    e.preventDefault()
    if (!form.org_id) {
      setMsg('Select a club from the search results first')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      await api.superCreateClub(form)
      setMsg('Club created')
      setShowCreate(false)
      resetCreate()
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const startEdit = (club) => {
    setConfirmDelete(null)
    setEditId(club.id)
    setEditForm({
      name: club.name || '',
      slug: club.slug || '',
      short_name: club.short_name || '',
      contact_email: club.contact_email || '',
      module_overrides: [...(club.module_overrides || [])],
      subscription_status: club.subscription_status || 'active',
      renewal_date: club.renewal_date || '',
      billing_cycle: club.billing_cycle || '',
      default_trial_days: club.default_trial_days || 14,
    })
  }

  // Per-module actions apply immediately (their own endpoints), then reload so the
  // club's module_subscriptions refresh in place.
  const runModuleAction = async (key, fn) => {
    setModuleBusy(key)
    setMsg('')
    try {
      await fn()
      await load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setModuleBusy('')
    }
  }
  const startModuleTrial = (clubId, key, days) =>
    runModuleAction(key, () => api.superStartModuleTrial(clubId, key, days ? { days } : {}))
  const setModuleStatus = (clubId, key, status) =>
    runModuleAction(key, () => api.superPatchModule(clubId, key, { status }))
  const setModuleRenewal = (clubId, key, date) =>
    runModuleAction(key, () => api.superPatchModule(clubId, key, { renewal_date: date || null }))
  const removeModule = (clubId, key) =>
    runModuleAction(key, () => api.superRemoveModule(clubId, key))

  const syncClub = async (club) => {
    setSyncing(club.id)
    setMsg('')
    try {
      await api.triggerSync(club.id)
      setMsg(`Sync started for ${club.name}`)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSyncing(null)
    }
  }

  const saveEdit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      // Empty date / cycle must go as null, not '' (the API validates them).
      const payload = {
        ...editForm,
        renewal_date: editForm.renewal_date || null,
        billing_cycle: editForm.billing_cycle || null,
        default_trial_days: Number(editForm.default_trial_days) || 14,
      }
      await api.superPatchClub(editId, payload)
      setMsg('Club updated')
      setEditId(null)
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteClub = async (club) => {
    setSaving(true)
    setMsg('')
    try {
      await api.superDeleteClub(club.id)
      setMsg(`Deleted ${club.name}`)
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
          <h1 className="font-display font-bold text-2xl text-pb-text">All Clubs</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <button
              onClick={() => { setShowCreate(s => !s); resetCreate(); setMsg('') }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ NEW CLUB'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createClub} className="pb-card p-4 mb-5 space-y-3">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Create New Club</p>

            <div ref={searchWrapRef} className="relative">
              <label className="font-mono text-[10px] text-pb-faint block mb-1">
                Search for a club *
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={handleQueryChange}
                  onFocus={() => results.length > 0 && setShowResults(true)}
                  placeholder="e.g. Portland Tigers Cricket Club"
                  className={INPUT_CLS + ' pr-8'}
                  autoComplete="off"
                />
                {searching && (
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 border-2 border-pb-accent/40 border-t-pb-accent rounded-full animate-spin" />
                )}
                {form.org_id && !searching && (
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--pb-accent)' }}>✓</span>
                )}
              </div>
              <Dropdown
                anchorRef={searchWrapRef}
                open={showResults && results.length > 0}
                onClose={() => setShowResults(false)}
                maxHeight={224}
                className="bg-pb-surface border pb-hairline rounded shadow-xl"
              >
                <ul>
                  {results.map(org => (
                    <li key={org.id}>
                      <button
                        type="button"
                        onClick={() => selectOrg(org)}
                        className="w-full text-left px-3 py-2 text-sm text-pb-text hover:bg-pb-surface2 transition-colors pb-hairline-b last:border-0"
                      >
                        <div className="font-medium">{orgName(org)}</div>
                        {org.shortName && org.shortName !== org.name && (
                          <div className="text-pb-faint text-xs mt-0.5">{org.shortName}</div>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </Dropdown>
              <Dropdown
                anchorRef={searchWrapRef}
                open={showResults && !searching && results.length === 0 && query.trim().length >= 2}
                onClose={() => setShowResults(false)}
                className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-sm text-pb-faint"
              >
                No clubs found for "{query}"
              </Dropdown>
              <p className="font-mono text-[10px] text-pb-faintest mt-1">
                A club must be picked from search so its data syncs correctly.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Club name *</label>
                <input required type="text" value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Slug * (URL identifier)</label>
                <input required type="text" value={form.slug}
                  onChange={e => setForm(f => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                  placeholder="e.g. applecross"
                  className={INPUT_CLS + ' font-mono'} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Short name</label>
                <input type="text" value={form.short_name}
                  onChange={e => setForm(f => ({ ...f, short_name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Contact email</label>
                <input type="email" value={form.contact_email}
                  onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
            </div>
            <button
              type="submit"
              disabled={saving || !form.org_id}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Creating…' : 'CREATE CLUB'}
            </button>
          </form>
        )}

        <div className="pb-card overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto_auto] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
            <span>CLUB</span>
            <span className="mr-8">STATUS</span>
            <span className="mr-8">CREATED</span>
            <span>ACTIONS</span>
          </div>
          {clubs.length === 0 && (
            <div className="px-5 py-6 text-center font-mono text-[11px] text-pb-faint">No clubs yet</div>
          )}
          {clubs.map((club, i) => (
            <div key={club.id} className={i > 0 ? 'pb-hairline-t' : ''}>
              <div className="grid grid-cols-[1fr_auto_auto_auto] items-center px-5 py-3 hover:bg-pb-surface2">
                <div>
                  <div>
                    <span className="text-pb-text text-sm">{club.name}</span>
                    <span className="font-mono text-[10px] text-pb-faintest ml-2">/{club.slug}</span>
                    <span
                      className="font-mono text-[9px] uppercase tracking-wide2 ml-2 px-1.5 py-0.5 rounded border pb-hairline text-pb-faint"
                      title={club.modules?.length ? `Modules: ${club.modules.join(', ')}` : 'Core only'}
                    >
                      {club.modules?.length ? `Core +${club.modules.length}` : 'Core'}
                    </span>
                  </div>
                  <div className={`font-mono text-[10px] mt-0.5 ${statusIsLive(club.subscription_status) ? 'text-pb-faintest' : 'text-pb-red'}`}>
                    {[
                      club.billing_cycle && (BILLING_CYCLES.find(c => c.key === club.billing_cycle)?.label || club.billing_cycle),
                      club.renewal_date && `renews ${new Date(club.renewal_date).toLocaleDateString('en-AU')}`,
                      statusLabel(club.subscription_status),
                    ].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <button
                  onClick={() => toggleActive(club)}
                  className={`font-mono text-[10px] px-2 py-1 rounded mr-8 border transition-colors ${
                    club.is_active
                      ? 'border-pb-accent/30 text-pb-accent bg-pb-accent/10'
                      : 'border-pb-hairline text-pb-faint bg-pb-surface2'
                  }`}
                  style={club.is_active ? { color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : {}}
                >
                  {club.is_active ? 'Active' : 'Inactive'}
                </button>
                <span className="font-mono text-[10px] text-pb-faintest mr-8">
                  {club.created_at ? new Date(club.created_at).toLocaleDateString('en-AU') : '—'}
                </span>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => syncClub(club)}
                    disabled={syncing === club.id}
                    className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50"
                    title="Pull latest games & stats"
                  >
                    {syncing === club.id ? 'Syncing…' : 'Sync'}
                  </button>
                  <button
                    onClick={() => (editId === club.id ? setEditId(null) : startEdit(club))}
                    className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                  >
                    {editId === club.id ? 'Close' : 'Edit'}
                  </button>
                  <button
                    onClick={() => { setConfirmDelete(club.id); setEditId(null) }}
                    className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {editId === club.id && (
                <form onSubmit={saveEdit} className="px-5 py-4 bg-pb-surface2/40 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Club name</label>
                      <input type="text" value={editForm.name}
                        onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                        className={INPUT_CLS} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Slug</label>
                      <input type="text" value={editForm.slug}
                        onChange={e => setEditForm(f => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                        className={INPUT_CLS + ' font-mono'} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Short name</label>
                      <input type="text" value={editForm.short_name}
                        onChange={e => setEditForm(f => ({ ...f, short_name: e.target.value }))}
                        className={INPUT_CLS} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Contact email</label>
                      <input type="email" value={editForm.contact_email}
                        onChange={e => setEditForm(f => ({ ...f, contact_email: e.target.value }))}
                        className={INPUT_CLS} />
                    </div>
                    <div className="col-span-2">
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Modules (entitlements)</label>
                      <div className="flex flex-wrap gap-2">
                        {MODULE_TOGGLES.map(tog => {
                          const on = tog.modules.every(m => editForm.module_overrides.includes(m))
                          return (
                            <button
                              key={tog.key}
                              type="button"
                              onClick={() => setEditForm(f => {
                                const set = new Set(f.module_overrides)
                                tog.modules.forEach(m => (on ? set.delete(m) : set.add(m)))
                                return { ...f, module_overrides: [...set] }
                              })}
                              className={`font-mono text-[11px] px-2.5 py-1.5 rounded border transition-colors ${on ? 'border-pb-accent/50 bg-pb-accent/10' : 'border-pb-hairline text-pb-faint bg-pb-surface2'}`}
                              style={on ? { color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 50%, transparent)' } : {}}
                            >
                              {on ? '✓ ' : '+ '}{tog.label}
                            </button>
                          )
                        })}
                      </div>
                    </div>

                    {/* Per-module subscription detail — status / renewal / trial,
                        each applied immediately via its own endpoint. */}
                    {(club.module_subscriptions?.length > 0) && (
                      <div className="col-span-2">
                        <label className="font-mono text-[10px] text-pb-faint block mb-1.5">Per-module status</label>
                        <div className="space-y-1.5">
                          {club.module_subscriptions.map(sub => {
                            const busy = moduleBusy === sub.module
                            const isTrial = sub.status === 'trial'
                            return (
                              <div key={sub.module} className="flex flex-wrap items-center gap-2 bg-pb-surface2/60 border pb-hairline rounded px-2.5 py-1.5">
                                <span className="text-pb-text text-xs font-medium w-28 shrink-0">{MODULE_NAME[sub.module] || sub.module}</span>
                                <select
                                  value={sub.status}
                                  disabled={busy}
                                  onChange={e => setModuleStatus(club.id, sub.module, e.target.value)}
                                  className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50"
                                >
                                  {SUBSCRIPTION_STATUSES.map(s => (
                                    <option key={s.key} value={s.key}>{s.label}</option>
                                  ))}
                                </select>
                                <input
                                  type="date"
                                  value={sub.renewal_date || ''}
                                  disabled={busy}
                                  onChange={e => setModuleRenewal(club.id, sub.module, e.target.value)}
                                  title="Renewal date"
                                  className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50"
                                />
                                {isTrial && (
                                  <span className={`font-mono text-[10px] ${sub.is_trial_expired ? 'text-pb-red' : 'text-pb-faint'}`}>
                                    trial {sub.is_trial_expired ? 'expired' : 'ends'} {fmtDate(sub.trial_ends_at)}
                                  </span>
                                )}
                                <div className="ml-auto flex items-center gap-2">
                                  {!isTrial && (
                                    <button type="button" disabled={busy}
                                      onClick={() => startModuleTrial(club.id, sub.module, club.default_trial_days)}
                                      className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50">
                                      Start trial
                                    </button>
                                  )}
                                  <button type="button" disabled={busy}
                                    onClick={() => removeModule(club.id, sub.module)}
                                    className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors disabled:opacity-50">
                                    Remove
                                  </button>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Subscription status (master switch)</label>
                      <select value={editForm.subscription_status}
                        onChange={e => setEditForm(f => ({ ...f, subscription_status: e.target.value }))}
                        className={INPUT_CLS}>
                        {SUBSCRIPTION_STATUSES.map(s => (
                          <option key={s.key} value={s.key}>{s.label}{s.live ? '' : ' (locks modules)'}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Billing cycle</label>
                      <select value={editForm.billing_cycle}
                        onChange={e => setEditForm(f => ({ ...f, billing_cycle: e.target.value }))}
                        className={INPUT_CLS}>
                        {BILLING_CYCLES.map(c => (
                          <option key={c.key} value={c.key}>{c.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Renewal date (default)</label>
                      <input type="date" value={editForm.renewal_date}
                        onChange={e => setEditForm(f => ({ ...f, renewal_date: e.target.value }))}
                        className={INPUT_CLS} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Default trial days</label>
                      <input type="number" min="1" value={editForm.default_trial_days}
                        onChange={e => setEditForm(f => ({ ...f, default_trial_days: e.target.value }))}
                        className={INPUT_CLS} />
                    </div>
                  </div>
                  <p className="font-mono text-[10px] text-pb-faintest">
                    Core (BetterStats) is always on. Tick a module to grant it (or remove it). Each held module
                    carries its own status, renewal date and trial above. Subscription status is the whole-account
                    master switch — Paused / Cancelled fall back to Core only regardless of modules. A trial ends on
                    its end date automatically. Default trial days seeds new trials (Club General Settings).
                  </p>
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

              {confirmDelete === club.id && (
                <div className="px-5 py-4 bg-pb-red/5 border-t border-pb-red/30 space-y-2">
                  <p className="font-mono text-[11px] text-pb-red">
                    Delete <strong>{club.name}</strong>? This permanently removes every season,
                    grade, game, player and user for this club. This cannot be undone.
                  </p>
                  <div className="flex gap-2">
                    <button onClick={() => deleteClub(club)} disabled={saving}
                      className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-white bg-pb-red">
                      {saving ? 'Deleting…' : 'DELETE PERMANENTLY'}
                    </button>
                    <button onClick={() => setConfirmDelete(null)}
                      className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
