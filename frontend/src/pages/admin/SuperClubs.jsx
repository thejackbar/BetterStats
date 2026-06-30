import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import { MODULE_TOGGLES, SUBSCRIPTION_STATUSES, BILLING_CYCLES, statusLabel, statusIsLive } from '../../lib/modules'
import AdminLayout from '../../components/admin/AdminLayout'
import Dropdown from '../../components/Dropdown'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-AU') : '—')

// datetime-local helpers (local wall-clock, "YYYY-MM-DDTHH:mm").
const _pad = (n) => String(n).padStart(2, '0')
const toLocalInput = (d) => `${d.getFullYear()}-${_pad(d.getMonth() + 1)}-${_pad(d.getDate())}T${_pad(d.getHours())}:${_pad(d.getMinutes())}`
const isoToLocalInput = (iso) => (iso ? toLocalInput(new Date(iso)) : '')

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
    subscription_status: 'active', renewal_date: '', billing_cycle: '',
  })
  const [moduleBusy, setModuleBusy] = useState('')
  const [clubAdmins, setClubAdmins] = useState([])
  // Default trial length (global General Settings) — prefills new trial end dates.
  const [defaultTrialDays, setDefaultTrialDays] = useState(14)
  // In-progress trial start/end edits per module key, before Apply.
  const [trialEdit, setTrialEdit] = useState({})
  // Global platform General Settings (currently just the default trial length).
  const [showSettings, setShowSettings] = useState(false)
  const [settingsForm, setSettingsForm] = useState({ default_trial_days: 14 })
  const [settingsSaving, setSettingsSaving] = useState(false)
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

  const openSettings = async () => {
    setMsg('')
    try {
      const s = await api.superGetGeneralSettings()
      setSettingsForm({ default_trial_days: s?.default_trial_days ?? 14 })
    } catch { /* fall back to the default shown */ }
    setShowSettings(true)
  }

  const saveSettings = async (e) => {
    e.preventDefault()
    setSettingsSaving(true)
    setMsg('')
    try {
      await api.superUpdateGeneralSettings({ default_trial_days: Number(settingsForm.default_trial_days) || 14 })
      setMsg('General settings saved')
      setShowSettings(false)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSettingsSaving(false)
    }
  }
  useEffect(() => {
    load()
    api.superGetGeneralSettings().then(s => setDefaultTrialDays(s?.default_trial_days || 14)).catch(() => {})
  }, [])

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
      subscription_status: club.subscription_status || 'active',
      renewal_date: club.renewal_date || '',
      billing_cycle: club.billing_cycle || '',
    })
    setClubAdmins([])
    api.superListClubAdmins(club.id).then(d => setClubAdmins(Array.isArray(d) ? d : [])).catch(() => {})
  }

  const setPrimaryAdmin = async (clubId, userId) => {
    setMsg('')
    try {
      await api.superSetPrimaryAdmin(clubId, userId)
      const d = await api.superListClubAdmins(clubId)
      setClubAdmins(Array.isArray(d) ? d : [])
    } catch (err) {
      setMsg(err.message)
    }
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
  // The trial start/end shown for a module: the in-progress edit if any, else the
  // saved trial dates, else prefilled now → now + the default trial length.
  const trialDraft = (sub) => {
    const key = sub?.module
    if (key && trialEdit[key]) return trialEdit[key]
    const now = new Date()
    return {
      start: isoToLocalInput(sub?.trial_started_at) || toLocalInput(now),
      end: isoToLocalInput(sub?.trial_ends_at) || toLocalInput(new Date(now.getTime() + defaultTrialDays * 86400000)),
    }
  }
  const clearTrialEdit = (key) => setTrialEdit(t => { const n = { ...t }; delete n[key]; return n })

  const grantModule = (clubId, key) =>
    runModuleAction(key, () => api.superPatchModule(clubId, key, { status: 'active' }))
  const removeModule = (clubId, key) =>
    runModuleAction(key, () => { clearTrialEdit(key); return api.superRemoveModule(clubId, key) })
  const setModuleRenewal = (clubId, key, date) =>
    runModuleAction(key, () => api.superPatchModule(clubId, key, { renewal_date: date || null }))
  // Status select: 'trial' opens the inline date editor (persisted on Apply) seeded
  // from the row's draft; any other status applies immediately.
  const onModuleStatus = (clubId, key, status, seedDraft) => {
    if (status === 'trial') {
      setTrialEdit(t => ({ ...t, [key]: seedDraft }))
      return
    }
    clearTrialEdit(key)
    runModuleAction(key, () => api.superPatchModule(clubId, key, { status }))
  }
  const applyTrial = (clubId, key, draft) => {
    if (draft.start && draft.end && new Date(draft.end) <= new Date(draft.start)) {
      setMsg('Trial end must be after the start')
      return
    }
    runModuleAction(key, async () => {
      await api.superStartModuleTrial(clubId, key, {
        start: new Date(draft.start).toISOString(),
        end: new Date(draft.end).toISOString(),
      })
      clearTrialEdit(key)
    })
  }

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
              onClick={openSettings}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-faint bg-pb-surface2"
            >
              GENERAL SETTINGS
            </button>
            <button
              onClick={() => { setShowCreate(s => !s); resetCreate(); setMsg('') }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ NEW CLUB'}
            </button>
          </div>
        </div>

        {showSettings && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowSettings(false)}>
            <form onSubmit={saveSettings} onClick={e => e.stopPropagation()}
              className="pb-card p-5 w-full max-w-sm space-y-4 bg-pb-surface">
              <div>
                <h2 className="font-display font-bold text-lg text-pb-text">General Settings</h2>
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  Platform-wide defaults, applied across all clubs.
                </p>
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Default trial days</label>
                <input type="number" min="1" value={settingsForm.default_trial_days}
                  onChange={e => setSettingsForm(f => ({ ...f, default_trial_days: e.target.value }))}
                  className={INPUT_CLS} autoFocus />
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  The trial length used when a module trial is created for a club.
                </p>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={settingsSaving}
                  className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}>
                  {settingsSaving ? 'Saving…' : 'SAVE'}
                </button>
                <button type="button" onClick={() => setShowSettings(false)}
                  className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

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
                      <p className="font-mono text-[10px] text-pb-faintest mb-2">
                        Add a module to grant it, then set its status. Choosing Trial lets you set the start
                        and end date &amp; time — prefilled from now and the default trial length. Changes apply immediately.
                      </p>
                      <div className="space-y-1.5">
                        {MODULE_TOGGLES.map(tog => {
                          const key = tog.key
                          const sub = (club.module_subscriptions || []).find(s => s.module === key)
                          const granted = !!sub
                          const busy = moduleBusy === key
                          const editingTrial = !!trialEdit[key]
                          const trialView = editingTrial || sub?.status === 'trial'
                          const draft = trialDraft(sub || { module: key })
                          return (
                            <div key={key} className="flex flex-wrap items-center gap-2 bg-pb-surface2/40 border pb-hairline rounded px-2.5 py-1.5">
                              <button type="button" disabled={busy}
                                onClick={() => (granted ? removeModule(club.id, key) : grantModule(club.id, key))}
                                className={`font-mono text-[11px] px-2.5 py-1 rounded border transition-colors disabled:opacity-50 w-40 shrink-0 text-left ${granted ? 'bg-pb-accent/10' : 'border-pb-hairline text-pb-faint bg-pb-surface2'}`}
                                style={granted ? { color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 50%, transparent)' } : {}}
                                title={granted ? 'Click to remove' : 'Click to grant'}>
                                {granted ? '✓ ' : '+ '}{tog.label}
                              </button>
                              {granted && (
                                <>
                                  <select value={editingTrial ? 'trial' : sub.status} disabled={busy}
                                    onChange={e => onModuleStatus(club.id, key, e.target.value, draft)}
                                    className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50">
                                    {SUBSCRIPTION_STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                                  </select>
                                  {trialView ? (
                                    <>
                                      <label className="font-mono text-[10px] text-pb-faint flex items-center gap-1">Start
                                        <input type="datetime-local" value={draft.start} disabled={busy}
                                          onChange={e => setTrialEdit(t => ({ ...t, [key]: { ...draft, start: e.target.value } }))}
                                          className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50" />
                                      </label>
                                      <label className="font-mono text-[10px] text-pb-faint flex items-center gap-1">End
                                        <input type="datetime-local" value={draft.end} disabled={busy}
                                          onChange={e => setTrialEdit(t => ({ ...t, [key]: { ...draft, end: e.target.value } }))}
                                          className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50" />
                                      </label>
                                      <button type="button" disabled={busy}
                                        onClick={() => applyTrial(club.id, key, draft)}
                                        className="font-mono text-[10px] px-2 py-1 rounded border transition-colors disabled:opacity-50"
                                        style={{ color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' }}>
                                        {editingTrial ? 'Apply trial' : 'Update'}
                                      </button>
                                      {sub?.status === 'trial' && sub?.is_trial_expired && (
                                        <span className="font-mono text-[10px] text-pb-red">expired</span>
                                      )}
                                    </>
                                  ) : (
                                    <label className="font-mono text-[10px] text-pb-faint flex items-center gap-1">Renews
                                      <input type="date" value={sub.renewal_date || ''} disabled={busy}
                                        onChange={e => setModuleRenewal(club.id, key, e.target.value)}
                                        className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50" />
                                    </label>
                                  )}
                                </>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>

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
                    {clubAdmins.length > 0 && (
                      <div className="col-span-2">
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">Primary / owner admin</label>
                        <select
                          value={clubAdmins.find(a => a.is_primary_admin)?.user_id || ''}
                          onChange={e => setPrimaryAdmin(club.id, e.target.value)}
                          className={INPUT_CLS}>
                          <option value="" disabled>— none —</option>
                          {clubAdmins.map(a => (
                            <option key={a.user_id} value={a.user_id}>
                              {a.display_name || a.username}{a.is_primary_admin ? ' (primary)' : ''}
                            </option>
                          ))}
                        </select>
                        <p className="font-mono text-[10px] text-pb-faintest mt-1">
                          Only the primary admin can request a paid subscription. Applied immediately.
                        </p>
                      </div>
                    )}
                  </div>
                  <p className="font-mono text-[10px] text-pb-faintest">
                    Core (BetterStats) is always on. Tick a module to grant it (or remove it). Each held module
                    carries its own status, renewal date and trial above. Subscription status is the whole-account
                    master switch — Paused / Cancelled fall back to Core only regardless of modules. A trial ends on
                    its end date automatically; its length comes from General Settings (top of this page).
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
