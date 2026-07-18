import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import { MODULE_TOGGLES, SUBSCRIPTION_STATUSES, BILLING_CYCLES, statusLabel, statusIsLive } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import AdminLayout from '../../components/admin/AdminLayout'
import Dropdown from '../../components/Dropdown'
import ClubPaymentMethodsModal from '../../components/admin/ClubPaymentMethodsModal'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

// Mirrors SuperMarketing.jsx's own STATES list (Club Directory).
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']
const norm = (s) => (s || '').toString().toLowerCase()
// "On trial/subscribed" = the module's subscription row is currently trial or active
// (mirrors SUBSCRIPTION_STATUSES' own `live` statuses, minus past_due/paused/cancelled).
const clubHasLiveModule = (club, key) =>
  (club.module_subscriptions || []).some((s) => s.module === key && (s.status === 'trial' || s.status === 'active'))

// Local (browser) calendar-day comparisons for the "newly registered" / "full
// sync activity" date filters — coarse day granularity, so a local slice is fine.
const dateOnly = (iso) => (iso ? new Date(iso).toLocaleDateString('en-CA') : null)
const todayStr = () => new Date().toLocaleDateString('en-CA')
const isToday = (iso) => dateOnly(iso) === todayStr()
const inDateRange = (iso, from, to) => {
  const d = dateOnly(iso)
  if (!d) return false
  if (from && d < from) return false
  if (to && d > to) return false
  return true
}

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-AU') : '—')

// datetime-local helpers (local wall-clock, "YYYY-MM-DDTHH:mm").
const _pad = (n) => String(n).padStart(2, '0')
const toLocalInput = (d) => `${d.getFullYear()}-${_pad(d.getMonth() + 1)}-${_pad(d.getDate())}T${_pad(d.getHours())}:${_pad(d.getMinutes())}`
const isoToLocalInput = (iso) => (iso ? toLocalInput(new Date(iso)) : '')

const EMPTY_FORM = { org_id: '', name: '', slug: '', short_name: '', contact_email: '' }

// Pause Sync / Cancel Sync / Continue Sync (migration 160) response status -> toast text.
const SYNC_CONTROL_MSG = {
  pause_requested: (club) => `Pause requested for ${club.name}. It'll stop at the next safe checkpoint.`,
  cancel_requested: (club) => `Cancel requested for ${club.name}. It'll stop at the next safe checkpoint.`,
  cancelled: (club) => `Sync cancelled for ${club.name}`,
  sync_started: (club) => `Sync continued for ${club.name}`,
  already_running: (club) => `${club.name} already has a sync running`,
}

// Rows shown in the General Settings bundle-discount editor. Only 1-4 have a
// live effect today (there are 4 priced bolt-on modules); 5/6 are pre-wired
// so a future 5th/6th priced module needs no code change here, just a value
// typed into an already-existing row.
const BUNDLE_DISCOUNT_ROWS = [1, 2, 3, 4, 5, 6]
const normalizeBundleSchedule = (raw) => {
  const out = {}
  for (const n of BUNDLE_DISCOUNT_ROWS) out[n] = Number(raw?.[n] ?? raw?.[String(n)] ?? 0)
  return out
}

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
    billing_checkout_override: '',
    comms_tier: 'sandbox', comms_sandbox_cap: '', comms_production_cap: '', comms_monthly_cap: '',
  })
  const [moduleBusy, setModuleBusy] = useState('')
  const [pmModalClub, setPmModalClub] = useState(null) // club object | null
  // In-progress "Renews" date edits per module key, before blur — keeps the native
  // date input's own mid-typing state from being clobbered by an autosave+reload
  // on every keystroke (see setModuleRenewal).
  const [renewalEdit, setRenewalEdit] = useState({})
  const [clubAdmins, setClubAdmins] = useState([])
  // Default trial length (global General Settings) — prefills new trial end dates.
  const [defaultTrialDays, setDefaultTrialDays] = useState(14)
  // In-progress trial start/end edits per module key, before Apply.
  const [trialEdit, setTrialEdit] = useState({})
  // Global platform General Settings (trial length + the Marketing section).
  const [showSettings, setShowSettings] = useState(false)
  const [settingsForm, setSettingsForm] = useState({
    default_trial_days: 14, direct_enquiry_hot_days: 30,
    self_serve_registration_enabled: false, onboarding_wizard_enabled: false,
    trial_nudges_enabled: false, billing_checkout_enabled: false,
    bundle_discount_schedule: { 1: 0, 2: 48, 3: 97, 4: 146, 5: 0, 6: 0 },
  })
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [archiveConfirmText, setArchiveConfirmText] = useState('')
  const [syncing, setSyncing] = useState(null)
  // Club id currently mid-request for Pause/Cancel/Continue Sync (migration 160).
  const [syncControlBusy, setSyncControlBusy] = useState(null)
  const [showArchived, setShowArchived] = useState(false)
  // Phase 21 — trial view filter: all / trialing / ending soon (<=7d) / expired.
  const [trialFilter, setTrialFilter] = useState('all')

  // Club Directory-style search + filters (client-side — the full club list is
  // already fetched, same as the existing trialFilter above).
  const [search, setSearch] = useState('')
  const [filterState, setFilterState] = useState('')
  const [filterAssociation, setFilterAssociation] = useState('')
  const [filterPrimaryAdmin, setFilterPrimaryAdmin] = useState('')
  const [filterModules, setFilterModules] = useState([])
  // "Newly registered" (organisations.created_at) and "full sync activity"
  // (sync_runs, kind org_full/org_hard_refresh) — each a quick mode plus an
  // optional custom date range.
  const [registeredMode, setRegisteredMode] = useState('any')
  const [registeredFrom, setRegisteredFrom] = useState('')
  const [registeredTo, setRegisteredTo] = useState('')
  const [syncMode, setSyncMode] = useState('any')
  const [syncFrom, setSyncFrom] = useState('')
  const [syncTo, setSyncTo] = useState('')
  const toggleFilterModule = (key) =>
    setFilterModules((m) => (m.includes(key) ? m.filter((k) => k !== key) : [...m, key]))
  const clearFilters = () => {
    setSearch(''); setFilterState(''); setFilterAssociation(''); setFilterPrimaryAdmin(''); setFilterModules([])
    setRegisteredMode('any'); setRegisteredFrom(''); setRegisteredTo('')
    setSyncMode('any'); setSyncFrom(''); setSyncTo('')
  }
  const filtersActive = !!(
    search || filterState || filterAssociation || filterPrimaryAdmin || filterModules.length
    || registeredMode !== 'any' || syncMode !== 'any'
  )

  // Club search (same source as the public onboarding flow)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef(null)
  const searchWrapRef = useRef(null)

  const load = (includeArchived = showArchived) =>
    api.superListClubs(includeArchived).then(setClubs).catch(() => {})

  const openSettings = async () => {
    setMsg('')
    try {
      const s = await api.superGetGeneralSettings()
      setSettingsForm({
        default_trial_days: s?.default_trial_days ?? 14,
        direct_enquiry_hot_days: s?.direct_enquiry_hot_days ?? 30,
        self_serve_registration_enabled: !!s?.self_serve_registration_enabled,
        onboarding_wizard_enabled: !!s?.onboarding_wizard_enabled,
        trial_nudges_enabled: !!s?.trial_nudges_enabled,
        billing_checkout_enabled: !!s?.billing_checkout_enabled,
        bundle_discount_schedule: normalizeBundleSchedule(s?.bundle_discount_schedule),
      })
    } catch { /* fall back to the defaults shown */ }
    setShowSettings(true)
  }

  const saveSettings = async (e) => {
    e.preventDefault()
    setSettingsSaving(true)
    setMsg('')
    try {
      await api.superUpdateGeneralSettings({
        default_trial_days: Number(settingsForm.default_trial_days) || 14,
        direct_enquiry_hot_days: Number(settingsForm.direct_enquiry_hot_days) || 30,
        self_serve_registration_enabled: !!settingsForm.self_serve_registration_enabled,
        onboarding_wizard_enabled: !!settingsForm.onboarding_wizard_enabled,
        trial_nudges_enabled: !!settingsForm.trial_nudges_enabled,
        billing_checkout_enabled: !!settingsForm.billing_checkout_enabled,
        bundle_discount_schedule: Object.fromEntries(
          BUNDLE_DISCOUNT_ROWS.map((n) => [n, Math.max(0, Number(settingsForm.bundle_discount_schedule[n]) || 0)])
        ),
      })
      setMsg('General settings saved')
      setShowSettings(false)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSettingsSaving(false)
    }
  }
  useEffect(() => {
    api.superGetGeneralSettings().then(s => setDefaultTrialDays(s?.default_trial_days || 14)).catch(() => {})
  }, [])

  useEffect(() => {
    load(showArchived)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showArchived])

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
      billing_checkout_override:
        club.billing_checkout_override === true ? 'true'
        : club.billing_checkout_override === false ? 'false'
        : '',
      comms_tier: club.comms_tier || 'sandbox',
      comms_sandbox_cap: club.comms_sandbox_cap ?? '',
      comms_production_cap: club.comms_production_cap ?? '',
      comms_monthly_cap: club.comms_monthly_cap ?? '',
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
  // The renewal date shown for a module: the in-progress (not yet blurred) edit if
  // any, else the saved value.
  const renewalDraft = (sub) => {
    const key = sub?.module
    if (key && renewalEdit[key] !== undefined) return renewalEdit[key]
    return sub?.renewal_date || ''
  }

  const removeModule = (clubId, key) =>
    runModuleAction(key, () => { clearTrialEdit(key); return api.superRemoveModule(clubId, key) })
  const setModuleRenewal = (clubId, key, date) =>
    runModuleAction(key, () => api.superPatchModule(clubId, key, { renewal_date: date || null }))
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
  // Granting a module (the "+ ModuleName" chip, only reachable while the module has
  // no subscription row at all — un-granting/Reset deletes the row outright, which is
  // what actually clears trial history, so "ungranted" always means genuinely never
  // trialled or subscribed) starts a trial instead of jumping straight to Active. A
  // super admin who really means to grant a live paid module bumps it from the status
  // dropdown right after — that still applies immediately (see onModuleStatus below).
  const grantModule = (clubId, key) => applyTrial(clubId, key, trialDraft({ module: key }))
  // Status select applies immediately for every choice, including 'trial' — it's
  // persisted straight away with the seeded start/end (now → now + the default
  // trial length), and those dates stay editable afterwards via the "Update"
  // control. Previously 'trial' only opened the inline date editor without saving,
  // requiring a separate "Apply trial" click to actually persist it — an easy step
  // to miss that left the module's stored status unchanged (still "active") while
  // a super admin believed they'd moved it to Trial, so the club's own Account page
  // kept reading the module as Subscribed with no way to tick it for the real
  // Stripe checkout flow. 'reset' isn't a real persisted status — it wipes the
  // module's subscription row(s) entirely (same as un-granting via the chip
  // button), which is what actually clears trial_started_at and makes the
  // module trial_eligible again for the club's own self-service Start Trial /
  // Subscribe (account_plan_status reads "never held a row" as never_trialed).
  const onModuleStatus = (clubId, key, status, seedDraft) => {
    if (status === 'trial') {
      applyTrial(clubId, key, seedDraft)
      return
    }
    if (status === 'reset') {
      clearTrialEdit(key)
      removeModule(clubId, key)
      return
    }
    clearTrialEdit(key)
    runModuleAction(key, () => api.superPatchModule(clubId, key, { status }))
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

  // Pause Sync / Cancel Sync / Continue Sync (migration 160) — a running
  // Full Sync is stopped cooperatively at its own next checkpoint (a season
  // or a few dozen games), not instantly; Continue starts a fresh
  // incremental sync from wherever the paused one left off.
  const syncControl = async (club, action) => {
    setSyncControlBusy(club.id)
    setMsg('')
    try {
      const res = await api.superClubSyncControl(club.id, action)
      const describe = SYNC_CONTROL_MSG[res?.status]
      setMsg(describe ? describe(club) : `Sync ${action} for ${club.name}`)
      await load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSyncControlBusy(null)
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
        billing_checkout_override:
          editForm.billing_checkout_override === 'true' ? true
          : editForm.billing_checkout_override === 'false' ? false
          : null,
        comms_sandbox_cap: editForm.comms_sandbox_cap === '' ? null : Number(editForm.comms_sandbox_cap),
        comms_production_cap: editForm.comms_production_cap === '' ? null : Number(editForm.comms_production_cap),
        comms_monthly_cap: editForm.comms_monthly_cap === '' ? null : Number(editForm.comms_monthly_cap),
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

  const archiveClub = async (club) => {
    setSaving(true)
    setMsg('')
    try {
      await api.superArchiveClub(club.id)
      setMsg(`Archived ${club.name} — restore it any time from All Clubs.`)
      setConfirmDelete(null)
      setArchiveConfirmText('')
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const restoreClub = async (club) => {
    setSaving(true)
    setMsg('')
    try {
      await api.superRestoreClub(club.id)
      setMsg(`Restored ${club.name}`)
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Phase 21 (docs/self-serve-trial-onboarding-plan.md) — trial-only reporting,
  // computed client-side off module_subscriptions the club list already returns
  // (no new endpoint). "Ending soon" mirrors the trial-lifecycle nudge's own
  // TRIAL_ENDING_SOON_DAYS window so the two surfaces read consistently.
  const TRIAL_ENDING_SOON_DAYS = 3
  const clubTrialInfo = (club) => {
    const subs = club.module_subscriptions || []
    const live = subs.filter((s) => s.status === 'trial' && !s.is_trial_expired)
    const expired = subs.filter((s) => s.status === 'trial' && s.is_trial_expired)
    if (live.length) {
      const soonest = live.reduce((a, b) => (new Date(a.trial_ends_at) < new Date(b.trial_ends_at) ? a : b))
      const days = Math.ceil((new Date(soonest.trial_ends_at).getTime() - Date.now()) / 86400000)
      return { kind: days <= TRIAL_ENDING_SOON_DAYS ? 'ending_soon' : 'trialing', days, count: live.length }
    }
    if (expired.length) return { kind: 'expired', count: expired.length }
    return null
  }

  const trialStats = clubs.reduce((acc, c) => {
    const info = clubTrialInfo(c)
    if (info?.kind === 'trialing') acc.trialing++
    if (info?.kind === 'ending_soon') acc.endingSoon++
    if (info?.kind === 'expired') acc.expired++
    return acc
  }, { trialing: 0, endingSoon: 0, expired: 0 })

  const visibleClubs = clubs.filter((c) => {
    if (trialFilter !== 'all') {
      const info = clubTrialInfo(c)
      const matchesTrial = trialFilter === 'trialing'
        ? (info?.kind === 'trialing' || info?.kind === 'ending_soon')
        : info?.kind === trialFilter
      if (!matchesTrial) return false
    }
    if (search) {
      const hay = `${c.name} ${c.short_name || ''} ${c.slug || ''}`
      if (!norm(hay).includes(norm(search))) return false
    }
    if (filterState && norm(c.state) !== norm(filterState)) return false
    if (filterAssociation && !norm(c.association_name).includes(norm(filterAssociation))) return false
    if (filterPrimaryAdmin && !norm(c.primary_admin_name).includes(norm(filterPrimaryAdmin))) return false
    if (filterModules.length && !filterModules.some((k) => clubHasLiveModule(c, k))) return false
    if (registeredMode === 'today' && !isToday(c.created_at)) return false
    if (registeredMode === 'range' && !inDateRange(c.created_at, registeredFrom, registeredTo)) return false
    if (syncMode === 'running' && !c.full_sync_running) return false
    if (syncMode === 'today' && !isToday(c.last_full_sync_at)) return false
    if (syncMode === 'range' && !inDateRange(c.last_full_sync_at, syncFrom, syncTo)) return false
    return true
  })

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">All Clubs</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <label className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Show archived
            </label>
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
          <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={() => setShowSettings(false)}>
            <form onSubmit={saveSettings} onClick={e => e.stopPropagation()}
              className="pb-card w-full max-w-sm bg-pb-surface mt-16 max-h-[80vh] overflow-hidden flex flex-col">
              <div className="p-5 pb-0 shrink-0">
                <h2 className="font-display font-bold text-lg text-pb-text">General Settings</h2>
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  Platform-wide defaults, applied across all clubs.
                </p>
              </div>
              <div className="p-5 overflow-y-auto space-y-4">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Default trial days</label>
                <input type="number" min="1" value={settingsForm.default_trial_days}
                  onChange={e => setSettingsForm(f => ({ ...f, default_trial_days: e.target.value }))}
                  className={INPUT_CLS} autoFocus />
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  The trial length used when a module trial is created for a club.
                </p>
              </div>

              <div className="pt-3 border-t pb-hairline">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Marketing</p>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Direct enquiry hot days</label>
                <input type="number" min="1" value={settingsForm.direct_enquiry_hot_days}
                  onChange={e => setSettingsForm(f => ({ ...f, direct_enquiry_hot_days: e.target.value }))}
                  className={INPUT_CLS} />
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  How many days a direct "onboard my club" website enquiry holds a prospect at a
                  flat 100/Hot engagement score in Twenty, before it decays back to the ordinary
                  recency/frequency score. Ends early if the club becomes a paying customer or is
                  marked Not Interested.
                </p>
              </div>

              <div className="pt-3 border-t pb-hairline space-y-2">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  Self-Serve Trials
                </p>
                <p className="font-mono text-[10px] text-pb-faintest">
                  Gates the public self-serve wizard: when this is ON, /trial and the website's
                  "Get your club on BetterCricket" and "Request access" buttons open the
                  registration flow directly. When it's OFF, those buttons send people to the
                  contact form instead. Either way, the Super Admin "Self-Serve Trial (Internal)"
                  menu item always works, for internal testing.
                </p>
                <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                  <input type="checkbox" checked={!!settingsForm.self_serve_registration_enabled}
                    onChange={e => setSettingsForm(f => ({ ...f, self_serve_registration_enabled: e.target.checked }))} />
                  Self-serve trials enabled
                </label>
              </div>

              <div className="pt-3 border-t pb-hairline space-y-2">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  Setup Guide
                </p>
                <p className="font-mono text-[10px] text-pb-faintest">
                  The "Get your club set up" checklist shown to Club Admins. When on, it opens
                  automatically the first time an admin logs in (and again once a club's first
                  sync finishes) until every step is done or dismissed. Turn off to stop it
                  popping up for every club platform-wide — this doesn't touch a club's own
                  saved progress, so re-enabling it later picks up right where it left off.
                </p>
                <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                  <input type="checkbox" checked={!!settingsForm.onboarding_wizard_enabled}
                    onChange={e => setSettingsForm(f => ({ ...f, onboarding_wizard_enabled: e.target.checked }))} />
                  Setup Guide enabled for Club Admins
                </label>
              </div>

              <div className="pt-3 border-t pb-hairline space-y-2">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  Trial nudges
                </p>
                <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                  <input type="checkbox" checked={!!settingsForm.trial_nudges_enabled}
                    onChange={e => setSettingsForm(f => ({ ...f, trial_nudges_enabled: e.target.checked }))} />
                  Trial lifecycle nudge emails enabled
                </label>
                <p className="font-mono text-[10px] text-pb-faintest">
                  Daily scan (08:00 UTC) that emails a trialling club's own admin when a
                  module trial starts, is about to end, has ended, or converts, plus onboarding
                  nudges (no historical data imported, a trialled module never opened).
                </p>
              </div>

              <div className="pt-3 border-t pb-hairline space-y-2">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  Billing (in progress)
                </p>
                <p className="font-mono text-[10px] text-pb-faintest">
                  Off keeps every club's Account page SUBSCRIBE button on the "not
                  connected yet" stub, no matter how much of the invoicing / Stripe
                  checkout build has landed. Only switch this on once that flow has
                  been tested and is ready for a real Primary Admin to pay through it.
                </p>
                <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                  <input type="checkbox" checked={!!settingsForm.billing_checkout_enabled}
                    onChange={e => setSettingsForm(f => ({ ...f, billing_checkout_enabled: e.target.checked }))} />
                  Online billing checkout enabled
                </label>
              </div>

              <div className="pt-3 border-t pb-hairline space-y-2">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  Bundle discount schedule
                </p>
                <p className="font-mono text-[10px] text-pb-faintest">
                  Whole-dollar discount off the annual total, by how many priced modules a club
                  selects in ONE initial subscribe (BetterSelect/BetterSocials/BetterAdmin/BetterIQ —
                  BetterFantasyCricket is priced separately and never discounted). Never applies to a
                  module added later to an already-live subscription. Rows 5-6 are here for a future
                  5th/6th priced module — harmless to leave at $0 until then.
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                  {BUNDLE_DISCOUNT_ROWS.map((n) => (
                    <label key={n} className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                      <span className="w-20 shrink-0">{n} module{n === 1 ? '' : 's'}</span>
                      <span className="text-pb-faintest">$</span>
                      <input
                        type="number" min="0"
                        value={settingsForm.bundle_discount_schedule[n] ?? 0}
                        onChange={e => setSettingsForm(f => ({
                          ...f,
                          bundle_discount_schedule: { ...f.bundle_discount_schedule, [n]: e.target.value },
                        }))}
                        className={INPUT_CLS}
                      />
                    </label>
                  ))}
                </div>
              </div>
              </div>

              <div className="flex gap-2 p-5 pt-3 border-t pb-hairline shrink-0">
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

        <div className="pb-card p-3 mb-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Search</label>
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Club name…" className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">State</label>
              <select value={filterState} onChange={(e) => setFilterState(e.target.value)} className={INPUT_CLS}>
                <option value="">All states</option>
                {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Association</label>
              <input type="text" value={filterAssociation} onChange={(e) => setFilterAssociation(e.target.value)}
                placeholder="Name or short code…" className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Primary admin</label>
              <input type="text" value={filterPrimaryAdmin} onChange={(e) => setFilterPrimaryAdmin(e.target.value)}
                placeholder="Admin name…" className={INPUT_CLS} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Newly registered</label>
              <select value={registeredMode} onChange={(e) => setRegisteredMode(e.target.value)} className={INPUT_CLS}>
                <option value="any">Any time</option>
                <option value="today">Today</option>
                <option value="range">Date range…</option>
              </select>
              {registeredMode === 'range' && (
                <div className="flex gap-2 mt-1.5">
                  <input type="date" value={registeredFrom} onChange={(e) => setRegisteredFrom(e.target.value)} className={INPUT_CLS} />
                  <input type="date" value={registeredTo} onChange={(e) => setRegisteredTo(e.target.value)} className={INPUT_CLS} />
                </div>
              )}
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Full sync activity</label>
              <select value={syncMode} onChange={(e) => setSyncMode(e.target.value)} className={INPUT_CLS}>
                <option value="any">Any time</option>
                <option value="running">Running now</option>
                <option value="today">Ran today</option>
                <option value="range">Date range…</option>
              </select>
              {syncMode === 'range' && (
                <div className="flex gap-2 mt-1.5">
                  <input type="date" value={syncFrom} onChange={(e) => setSyncFrom(e.target.value)} className={INPUT_CLS} />
                  <input type="date" value={syncTo} onChange={(e) => setSyncTo(e.target.value)} className={INPUT_CLS} />
                </div>
              )}
            </div>
          </div>
          <div className="mt-3">
            <label className="font-mono text-[10px] text-pb-faint block mb-1">On trial / subscribed to</label>
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

        <div className="flex flex-wrap gap-2 mb-3">
          {[
            { key: 'all', label: `All (${clubs.length})` },
            { key: 'trialing', label: `Trialing (${trialStats.trialing + trialStats.endingSoon})` },
            { key: 'ending_soon', label: `Ending soon (${trialStats.endingSoon})` },
            { key: 'expired', label: `Trial expired (${trialStats.expired})` },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setTrialFilter(f.key)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border transition-colors ${
                trialFilter === f.key
                  ? 'border-pb-accent text-pb-text'
                  : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="pb-card overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto_auto] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
            <span>CLUB</span>
            <span className="mr-8">STATUS</span>
            <span className="mr-8">CREATED</span>
            <span>ACTIONS</span>
          </div>
          {visibleClubs.length === 0 && (
            <div className="px-5 py-6 text-center font-mono text-[11px] text-pb-faint">
              {clubs.length === 0 ? 'No clubs yet' : 'No clubs match these filters'}
            </div>
          )}
          {visibleClubs.map((club, i) => (
            <div key={club.id} className={i > 0 ? 'pb-hairline-t' : ''}>
              <div className="grid grid-cols-[1fr_auto_auto_auto] items-center px-5 py-3 hover:bg-pb-surface2">
                <div>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-pb-text text-sm whitespace-nowrap">{club.name}</span>
                    <span className="font-mono text-[10px] text-pb-faintest whitespace-nowrap">/{club.slug}</span>
                    <span
                      className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border pb-hairline text-pb-faint whitespace-nowrap"
                      title={club.modules?.length ? `Modules: ${club.modules.join(', ')}` : 'Core only'}
                    >
                      {club.modules?.length ? `Core +${club.modules.length}` : 'Core'}
                    </span>
                    {club.archived_at && (
                      <span
                        className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border border-pb-red/30 text-pb-red whitespace-nowrap"
                        title={`Archived ${new Date(club.archived_at).toLocaleDateString('en-AU')}`}
                      >
                        Archived
                      </span>
                    )}
                    {club.full_sync_running && (
                      <span
                        className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border border-sky-500/40 text-sky-300 whitespace-nowrap"
                        title="A full sync (Sync Now / Full Rebuild) is running right now"
                      >
                        Syncing
                      </span>
                    )}
                    {club.full_sync_paused && (
                      <span
                        className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-300 whitespace-nowrap"
                        title="A full sync was paused. Continue Sync resumes it as a fresh incremental sync."
                      >
                        Sync paused
                      </span>
                    )}
                    {(() => {
                      const info = clubTrialInfo(club)
                      if (!info) return null
                      const urgent = info.kind === 'ending_soon' || info.kind === 'expired'
                      return (
                        <span
                          className={`font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border whitespace-nowrap ${
                            urgent ? 'border-amber-500/40 text-amber-300' : 'border-pb-hairline text-pb-faint'
                          }`}
                        >
                          {info.kind === 'expired'
                            ? `Trial expired × ${info.count}`
                            : `Trial ${info.days}d × ${info.count}`}
                        </span>
                      )
                    })()}
                  </div>
                  <div className={`font-mono text-[10px] mt-0.5 ${statusIsLive(club.subscription_status) ? 'text-pb-faintest' : 'text-pb-red'}`}>
                    {[
                      club.billing_cycle && (BILLING_CYCLES.find(c => c.key === club.billing_cycle)?.label || club.billing_cycle),
                      club.renewal_date && `renews ${new Date(club.renewal_date).toLocaleDateString('en-AU')}`,
                      statusLabel(club.subscription_status),
                    ].filter(Boolean).join(' · ')}
                  </div>
                  {(club.state || club.association_name || club.primary_admin_name) && (
                    <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                      {[
                        club.state,
                        club.association_name,
                        club.primary_admin_name && `admin: ${club.primary_admin_name}`,
                      ].filter(Boolean).join(' · ')}
                    </div>
                  )}
                  <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                    {[
                      `${club.seasons_count ?? 0} season${(club.seasons_count ?? 0) === 1 ? '' : 's'}`,
                      `${club.grades_count ?? 0} grade${(club.grades_count ?? 0) === 1 ? '' : 's'}`,
                      `${club.players_count ?? 0} player${(club.players_count ?? 0) === 1 ? '' : 's'}`,
                      club.onboarding_total > 0 && `setup ${club.onboarding_done}/${club.onboarding_total}`,
                      !club.full_sync_running && !club.full_sync_paused && club.last_full_sync_at
                        && `last synced ${new Date(club.last_full_sync_at).toLocaleDateString('en-AU')}`,
                      club.last_active_at
                        ? `active ${new Date(club.last_active_at).toLocaleDateString('en-AU')}`
                        : 'no recent activity',
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
                  {club.archived_at ? (
                    <button
                      onClick={() => restoreClub(club)}
                      disabled={saving}
                      className="font-mono text-[10px] text-pb-accent hover:underline transition-colors disabled:opacity-50"
                    >
                      Restore
                    </button>
                  ) : (
                    <>
                      {club.full_sync_running ? (
                        <>
                          <button
                            onClick={() => syncControl(club, 'pause')}
                            disabled={syncControlBusy === club.id}
                            className="font-mono text-[10px] text-amber-400 hover:text-amber-300 transition-colors disabled:opacity-50"
                            title="Stop this sync at its next safe checkpoint. Continue Sync picks up from there."
                          >
                            Pause Sync
                          </button>
                          <button
                            onClick={() => syncControl(club, 'cancel')}
                            disabled={syncControlBusy === club.id}
                            className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors disabled:opacity-50"
                            title="Stop this sync for good at its next safe checkpoint"
                          >
                            Cancel Sync
                          </button>
                        </>
                      ) : club.full_sync_paused ? (
                        <>
                          <button
                            onClick={() => syncControl(club, 'continue')}
                            disabled={syncControlBusy === club.id}
                            className="font-mono text-[10px] text-pb-accent hover:underline transition-colors disabled:opacity-50"
                            title="Resume with a fresh incremental sync, safe even after a paused Full Rebuild"
                          >
                            Continue Sync
                          </button>
                          <button
                            onClick={() => syncControl(club, 'cancel')}
                            disabled={syncControlBusy === club.id}
                            className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors disabled:opacity-50"
                            title="Abandon this paused sync"
                          >
                            Cancel Sync
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => syncClub(club)}
                          disabled={syncing === club.id}
                          className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50"
                          title="Pull latest games & stats"
                        >
                          {syncing === club.id ? 'Syncing…' : 'Sync'}
                        </button>
                      )}
                      <button
                        onClick={() => (editId === club.id ? setEditId(null) : startEdit(club))}
                        className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                      >
                        {editId === club.id ? 'Close' : 'Edit'}
                      </button>
                      <button
                        onClick={() => setPmModalClub(club)}
                        className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                        title="Manage this club's saved payment methods"
                      >
                        Billing
                      </button>
                      <button
                        onClick={() => { setConfirmDelete(club.id); setArchiveConfirmText(''); setEditId(null) }}
                        className="font-mono text-[10px] text-pb-red/80 hover:text-pb-red transition-colors"
                      >
                        Archive
                      </button>
                    </>
                  )}
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
                        Add a module to grant it, then set its status. Every choice applies immediately,
                        including Trial — it starts a trial prefilled from now and the default trial length,
                        which you can then adjust with the Start/End fields and Update.
                      </p>
                      <div className="space-y-1.5">
                        {MODULE_TOGGLES.map(tog => {
                          const key = tog.key
                          const isCore = key === 'core'
                          const sub = (club.module_subscriptions || []).find(s => s.module === key)
                          const granted = !!sub
                          const busy = moduleBusy === key
                          const editingTrial = !!trialEdit[key]
                          const trialView = editingTrial || sub?.status === 'trial'
                          const draft = trialDraft(sub || { module: key })
                          // Each granted chip wears its module's own brand colour
                          // (the shared moduleBrand source of truth), not the page accent.
                          const brand = moduleBrand(key).accent
                          return (
                            <div key={key} className="flex flex-wrap items-center gap-2 bg-pb-surface2/40 border pb-hairline rounded px-2.5 py-1.5">
                              {/* Core is the base — it can't be removed; disable it via its
                                  status (Cancelled / Paused), not by un-granting. Core's button is
                                  permanently disabled, so dim only while busy (not for Core itself). */}
                              <button type="button" disabled={busy || isCore}
                                onClick={() => { if (isCore) return; granted ? removeModule(club.id, key) : grantModule(club.id, key) }}
                                className={`font-mono text-[11px] px-2.5 py-1 rounded border transition-colors w-48 shrink-0 text-left whitespace-nowrap ${busy ? 'opacity-50' : ''} ${granted ? '' : 'border-pb-hairline text-pb-faint bg-pb-surface2'}`}
                                style={granted ? { color: brand, borderColor: `color-mix(in srgb, ${brand} 50%, transparent)`, backgroundColor: `color-mix(in srgb, ${brand} 12%, transparent)` } : {}}
                                title={isCore ? 'BetterStats is the base — set status to disable' : (granted ? 'Click to remove' : 'Click to grant')}>
                                {granted ? '✓ ' : '+ '}{tog.label}
                              </button>
                              {granted && (
                                <>
                                  <select value={editingTrial ? 'trial' : sub.status} disabled={busy}
                                    onChange={e => onModuleStatus(club.id, key, e.target.value, draft)}
                                    title="Reset wipes the module's trial/subscription history so the club can start a fresh trial or subscribe again"
                                    className="bg-pb-surface border pb-hairline rounded px-1.5 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent disabled:opacity-50">
                                    {SUBSCRIPTION_STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                                    <option value="reset">Reset (make eligible again)</option>
                                  </select>
                                  {trialView ? (
                                    // Keep Start / End / Apply together on one line: they're one
                                    // nowrap flex group, so they wrap as a unit within the row, never split.
                                    <div className="flex items-center gap-2">
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
                                        className="font-mono text-[10px] px-2 py-1 rounded border transition-colors disabled:opacity-50 shrink-0"
                                        style={{ color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' }}>
                                        {editingTrial ? 'Apply trial' : 'Update'}
                                      </button>
                                      {sub?.status === 'trial' && sub?.is_trial_expired && (
                                        <span className="font-mono text-[10px] text-pb-red">expired</span>
                                      )}
                                    </div>
                                  ) : (
                                    <label className="font-mono text-[10px] text-pb-faint flex items-center gap-1">Renews
                                      <input type="date" value={renewalDraft(sub)} disabled={busy}
                                        onChange={e => setRenewalEdit(r => ({ ...r, [key]: e.target.value }))}
                                        onBlur={e => {
                                          const val = e.target.value
                                          setRenewalEdit(r => { const n = { ...r }; delete n[key]; return n })
                                          if (val !== (sub.renewal_date || '')) setModuleRenewal(club.id, key, val)
                                        }}
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
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Stripe checkout (this club)</label>
                      <select value={editForm.billing_checkout_override}
                        onChange={e => setEditForm(f => ({ ...f, billing_checkout_override: e.target.value }))}
                        className={INPUT_CLS}>
                        <option value="">Platform default</option>
                        <option value="true">Force ON — let this club through (testing)</option>
                        <option value="false">Force OFF — block even if the platform default is on</option>
                      </select>
                      <p className="font-mono text-[10px] text-pb-faintest mt-1">
                        Overrides General Settings → Billing for this one club — lets you test the
                        real Stripe flow on a single club before switching it on for everyone.
                      </p>
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">BetterComms sending tier</label>
                      <select value={editForm.comms_tier}
                        onChange={e => setEditForm(f => ({ ...f, comms_tier: e.target.value }))}
                        className={INPUT_CLS}>
                        <option value="sandbox">Sandbox (low daily cap)</option>
                        <option value="production">Production</option>
                        <option value="suspended">Suspended (blocked)</option>
                      </select>
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Sandbox daily cap (blank = default)</label>
                      <input type="number" min="0" value={editForm.comms_sandbox_cap}
                        onChange={e => setEditForm(f => ({ ...f, comms_sandbox_cap: e.target.value }))}
                        placeholder="global default" className={INPUT_CLS} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Production daily cap (blank = default)</label>
                      <input type="number" min="0" value={editForm.comms_production_cap}
                        onChange={e => setEditForm(f => ({ ...f, comms_production_cap: e.target.value }))}
                        placeholder="global default" className={INPUT_CLS} />
                    </div>
                    <div>
                      <label className="font-mono text-[10px] text-pb-faint block mb-1">Monthly cap (blank = default, 0 = none)</label>
                      <input type="number" min="0" value={editForm.comms_monthly_cap}
                        onChange={e => setEditForm(f => ({ ...f, comms_monthly_cap: e.target.value }))}
                        placeholder="global default" className={INPUT_CLS} />
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
                    Archive <strong>{club.name}</strong>? It disappears from this list (unless
                    "Show archived" is on) and its data is left untouched, restore it any time.
                  </p>
                  <label className="block">
                    <span className="block mb-2 font-mono text-[10px] text-pb-faint">
                      Type <strong className="text-pb-red">confirm</strong> to continue
                    </span>
                    <input type="text" value={archiveConfirmText}
                      onChange={e => setArchiveConfirmText(e.target.value)}
                      autoComplete="off"
                      className="w-full max-w-xs bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-red" />
                  </label>
                  <div className="flex gap-2">
                    <button onClick={() => archiveClub(club)}
                      disabled={saving || archiveConfirmText.trim().toLowerCase() !== 'confirm'}
                      className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-white bg-pb-red">
                      {saving ? 'Archiving…' : 'ARCHIVE'}
                    </button>
                    <button onClick={() => { setConfirmDelete(null); setArchiveConfirmText('') }}
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
      {pmModalClub && (
        <ClubPaymentMethodsModal club={pmModalClub} onClose={() => setPmModalClub(null)} />
      )}
    </AdminLayout>
  )
}
