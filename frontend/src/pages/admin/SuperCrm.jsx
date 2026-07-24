import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import PipelineBoard, { TIER_TONE } from '../../components/admin/crm/PipelineBoard'
import DealDetailModal from '../../components/admin/crm/DealDetailModal'
import ManageStagesModal from '../../components/admin/crm/ManageStagesModal'
import { Modal, Field, TextInput, NumberInput, Select, Btn, Pill, money, MODULE_ORDER, moduleLabel } from '../../components/admin/crm/ui'

const superClient = {
  getDeal: api.superCrmGetDeal,
  updateDeal: api.superCrmUpdateDeal,
  moveStage: api.superCrmMoveDealStage,
  closeDeal: api.superCrmCloseDeal,
  archiveDeal: api.superCrmArchiveDeal,
  listActivities: api.superCrmListActivities,
  addActivity: api.superCrmAddActivity,
  listContacts: api.superCrmListDealContacts,
  linkContact: api.superCrmLinkContact,
  unlinkContact: api.superCrmUnlinkContact,
  setPointOfContact: api.superCrmSetPointOfContact,
  updatePerson: api.superCrmUpdatePerson,
  deletePermanent: api.superCrmDeleteDealPermanent,
  addStage: api.superCrmAddStage,
  updateStage: api.superCrmUpdateStage,
  deleteStage: api.superCrmDeleteStage,
}

// Sentence-Case, fixed-order module vocabulary (Stats/Select/Socials/Admin/
// IQ/Fantasy) shared everywhere a deal's Product Interest is shown/edited.
const MODULE_OPTIONS = MODULE_ORDER.map(key => ({ key, label: moduleLabel(key) }))

// Known acquisition_channel raw values (services/crm.py::acquisition_channels_by_club)
// — anything else (e.g. a raw utm_source like "google"/"facebook") is shown verbatim.
const CHANNEL_LABELS = {
  contact_form: 'Contact us (form)',
  cta_quick_form: 'Contact us (quick modal)',
  self_serve_ad: 'Self-serve (ad)',
  self_serve_organic: 'Self-serve (organic)',
  manual: 'Manual',
  auto_enquiry: 'Auto (enquiry)',
  auto_trial: 'Auto (trial)',
  twenty_import: 'Twenty import',
}
const channelLabel = (v) => CHANNEL_LABELS[v] || v

const EMPTY_FILTERS = {
  q: '', ownerId: '', modules: [], minValue: '', maxValue: '',
  minScore: '', maxScore: '', state: '', association: '', channel: '',
  onboarding: '', minTrialDays: '', maxTrialDays: '',
}

const ONBOARDING_OPTIONS = [
  { value: '', label: 'Any onboarding' },
  { value: 'self_serve', label: 'Self-Serve' },
  { value: 'not_self_serve', label: 'Not Self-Serve' },
  { value: 'customer', label: 'Customer' },
  { value: 'not_onboarded', label: 'Not Onboarded' },
]

// Sort-within-stage: a horizontal row of mutually exclusive buttons, each
// cycling not-selected -> asc -> desc, instead of a dropdown + direction
// toggle pair.
const SORT_OPTIONS = [
  { key: '', label: 'Recent' },
  { key: 'club', label: 'Club name' },
  { key: 'value', label: 'Dollar value' },
  { key: 'engagement', label: 'Engagement score' },
]

function SortButtons({ sortBy, sortDir, onChange }) {
  const click = (key) => {
    if (key === '') { onChange('', 'asc'); return }
    if (sortBy !== key) { onChange(key, 'asc'); return }
    onChange(key, sortDir === 'asc' ? 'desc' : 'asc')
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] text-pb-faint mr-1">Sort by</span>
      {SORT_OPTIONS.map(o => {
        const selected = o.key === '' ? sortBy === '' : sortBy === o.key
        const arrow = o.key === '' ? '' : (selected ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '')
        return (
          <button key={o.key || 'recent'} type="button" onClick={() => click(o.key)}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
              selected ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
            {o.label}{arrow}
          </button>
        )
      })}
    </div>
  )
}

// Groups a flat deal list by stage into the same shape services/crm.py's
// pipeline_board() returns, so PipelineBoard renders unchanged whether it's
// fed the server's board or (here) a client-filtered one. Done client-side
// so Board and List share one filtered data source — see the filter bar
// below, which otherwise only ever touched the List view's table.
function buildBoard(stages, deals) {
  const byStage = {}
  for (const d of deals) (byStage[d.stage_id] ||= []).push(d)
  let totalOpenValue = 0, totalWeighted = 0, totalOpenCount = 0
  const stagesOut = (stages || []).map(stage => {
    const stageDeals = byStage[stage.id] || []
    let stageValue = 0, stageWeighted = 0
    for (const d of stageDeals) {
      if (d.status === 'open') {
        const eff = d.effective_probability ?? 0
        const effectiveValue = d.effective_value_cents ?? d.value_cents
        stageValue += effectiveValue
        stageWeighted += Math.round(effectiveValue * eff / 100)
        totalOpenCount += 1
      }
    }
    totalOpenValue += stageValue
    totalWeighted += stageWeighted
    return {
      id: stage.id, key: stage.key, name: stage.name, position: stage.position,
      default_probability: stage.default_probability, is_won: stage.is_won, is_lost: stage.is_lost,
      hidden_from_board: stage.hidden_from_board,
      deal_count: stageDeals.length, value_cents: stageValue, weighted_value_cents: stageWeighted,
      deals: stageDeals,
    }
  })
  return {
    pipeline: { name: 'BetterCricket Sales' },
    stages: stagesOut,
    totals: { open_value_cents: totalOpenValue, weighted_value_cents: totalWeighted, open_count: totalOpenCount },
  }
}

// A clickable column heading for the List view — the sort arrow sits right
// next to the label (not off in its own column), cycling asc/desc on click.
function SortableTh({ label, sortKey, align, sortBy, sortDir, onSort }) {
  const active = sortBy === sortKey
  return (
    <th className={`px-3 py-2 font-normal cursor-pointer select-none hover:text-pb-text ${align === 'right' ? 'text-right' : 'text-left'}`}
      onClick={() => onSort(sortKey)}>
      <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
        <span>{label}</span>
        <span className="text-[9px] w-2.5 inline-block text-center text-pb-accent">
          {active ? (sortDir === 'asc' ? '▲' : '▼') : ''}
        </span>
      </span>
    </th>
  )
}

function NewDealModal({ open, onClose, stages, onCreated }) {
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [valueDollars, setValueDollars] = useState('')
  const [stageId, setStageId] = useState(stages?.[0]?.id || '')
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setTitle(''); setValueDollars(''); setStageId(stages?.[0]?.id || '') } }, [open, stages])

  const submit = async (e) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.superCrmCreateDeal({
        title: title.trim(), stage_id: stageId || undefined,
        value_cents: Math.round(Number(valueDollars || 0) * 100),
      })
      onCreated()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not create deal') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New deal">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Title"><TextInput autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Applecross Cricket Club" /></Field>
        <Field label="Value ($)"><NumberInput min={0} value={valueDollars} onChange={e => setValueDollars(e.target.value)} /></Field>
        <Field label="Stage">
          <Select value={stageId} onChange={e => setStageId(e.target.value)}>
            {(stages || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Create deal</Btn></div>
      </form>
    </Modal>
  )
}

function FilterBar({ filters, setFilters, owners, stateOptions, associationOptions, channelOptions, resultCount }) {
  // Open by default — a filter bar that starts collapsed hides the very
  // controls someone opened this page to use (per direct instruction).
  const [open, setOpen] = useState(true)
  const set = (key) => (e) => setFilters(f => ({ ...f, [key]: e.target.value }))
  const toggleModule = (key) => setFilters(f => ({
    ...f, modules: f.modules.includes(key) ? f.modules.filter(k => k !== key) : [...f.modules, key],
  }))
  const active = Object.entries(filters).some(([k, v]) => Array.isArray(v) ? v.length > 0 : v !== '')

  return (
    <div className="pb-card px-4 py-3 mb-4">
      <div className="flex items-center justify-between gap-2">
        <button onClick={() => setOpen(v => !v)} className="flex items-center gap-2 text-[12.5px] font-display font-bold">
          <span>{open ? '▾' : '▸'}</span> Filters
          {active && <Pill tone="accent">{resultCount} match{resultCount === 1 ? '' : 'es'}</Pill>}
        </button>
        {active && <button onClick={() => setFilters(EMPTY_FILTERS)} className="text-[11.5px] text-pb-faint hover:text-pb-red">Clear all</button>}
      </div>
      {open && (
        <div className="mt-3 space-y-3">
          {/* One row: club/contact search, owner, state, association, source —
              kept narrow per direct instruction rather than each on its own line. */}
          <div className="flex flex-wrap gap-2">
            <TextInput placeholder="Club name or point of contact" value={filters.q} onChange={set('q')} className="flex-1 min-w-[220px]" />
            <Select value={filters.ownerId} onChange={set('ownerId')} className="w-36">
              <option value="">Any owner</option>
              <option value="__unassigned__">Unassigned</option>
              {owners.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            <Select value={filters.state} onChange={set('state')} className="w-28">
              <option value="">Any state</option>
              {stateOptions.map(s => <option key={s} value={s}>{s}</option>)}
            </Select>
            <TextInput list="crm-associations" placeholder="Association" value={filters.association} onChange={set('association')} className="w-36" />
            <datalist id="crm-associations">{associationOptions.map(a => <option key={a} value={a} />)}</datalist>
            <Select value={filters.channel} onChange={set('channel')} className="w-36">
              <option value="">Any source</option>
              {channelOptions.map(c => <option key={c} value={c}>{channelLabel(c)}</option>)}
            </Select>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Select value={filters.onboarding} onChange={set('onboarding')} className="w-40">
              {ONBOARDING_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint">Value $</span>
              <NumberInput min={0} placeholder="min" value={filters.minValue} onChange={set('minValue')} className="w-24" />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} placeholder="max" value={filters.maxValue} onChange={set('maxValue')} className="w-24" />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint">Engagement</span>
              <NumberInput min={0} max={100} placeholder="min" value={filters.minScore} onChange={set('minScore')} className="w-20" />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} max={100} placeholder="max" value={filters.maxScore} onChange={set('maxScore')} className="w-20" />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint" title="Only clubs with a tracked module trial (i.e. already onboarded)">Trial expiring in (days)</span>
              <NumberInput min={0} placeholder="min" value={filters.minTrialDays} onChange={set('minTrialDays')} className="w-20" />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} placeholder="max" value={filters.maxTrialDays} onChange={set('maxTrialDays')} className="w-20" />
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {MODULE_OPTIONS.map(m => (
              <button key={m.key} type="button" onClick={() => toggleModule(m.key)}
                className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                  filters.modules.includes(m.key)
                    ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                    : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                {m.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function SuperCrm() {
  const toast = useToast()
  const [view, setView] = useState('board')
  const [deals, setDeals] = useState([])
  const [stages, setStages] = useState([])
  const [status, setStatus] = useState('open')
  const [loading, setLoading] = useState(true)
  const [openDealId, setOpenDealId] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [showStages, setShowStages] = useState(false)
  const [owners, setOwners] = useState([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sortBy, setSortBy] = useState('')
  const [sortDir, setSortDir] = useState('asc')

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.superCrmStages(),
      api.superCrmListDeals({ status: status || undefined }),
    ])
      .then(([s, d]) => { setStages(s.stages || []); setDeals(d.deals || []) })
      .catch(e => toast.error(e.message || 'Could not load the sales pipeline'))
      .finally(() => setLoading(false))
  }, [status, toast])

  useEffect(() => { load() }, [load])
  useEffect(() => { api.superCrmOwners().then(r => setOwners(r.owners || [])).catch(() => {}) }, [])

  const stateOptions = useMemo(() => [...new Set(deals.map(d => d.marketing_club_state).filter(Boolean))].sort(), [deals])
  const associationOptions = useMemo(() => [...new Set(deals.map(d => d.marketing_club_association).filter(Boolean))].sort(), [deals])
  const channelOptions = useMemo(() => [...new Set(deals.map(d => d.acquisition_channel).filter(Boolean))].sort(), [deals])

  const filteredDeals = useMemo(() => {
    // One search box matches EITHER the club/deal name or its point of
    // contact — per direct instruction, rather than two separate fields.
    const needle = filters.q.trim().toLowerCase()
    const assocNeedle = filters.association.trim().toLowerCase()
    const minValueCents = filters.minValue !== '' ? Math.round(Number(filters.minValue) * 100) : null
    const maxValueCents = filters.maxValue !== '' ? Math.round(Number(filters.maxValue) * 100) : null
    const minScore = filters.minScore !== '' ? Number(filters.minScore) : null
    const maxScore = filters.maxScore !== '' ? Number(filters.maxScore) : null
    const minTrialDays = filters.minTrialDays !== '' ? Number(filters.minTrialDays) : null
    const maxTrialDays = filters.maxTrialDays !== '' ? Number(filters.maxTrialDays) : null
    return deals.filter(d => {
      if (needle && !`${d.title} ${d.marketing_club_name || ''} ${d.point_of_contact_name || ''}`
        .toLowerCase().includes(needle)) return false
      if (filters.ownerId === '__unassigned__' ? d.owner_user_id : (filters.ownerId && d.owner_user_id !== filters.ownerId)) return false
      if (filters.modules.length && !filters.modules.some(m => (d.module_keys || []).includes(m))) return false
      if (minValueCents != null && (d.effective_value_cents ?? d.value_cents) < minValueCents) return false
      if (maxValueCents != null && (d.effective_value_cents ?? d.value_cents) > maxValueCents) return false
      if (minScore != null && (d.engagement_score == null || d.engagement_score < minScore)) return false
      if (maxScore != null && (d.engagement_score == null || d.engagement_score > maxScore)) return false
      if (filters.state && d.marketing_club_state !== filters.state) return false
      if (assocNeedle && !(d.marketing_club_association || '').toLowerCase().includes(assocNeedle)) return false
      if (filters.channel && d.acquisition_channel !== filters.channel) return false
      if (filters.onboarding === 'self_serve' && d.onboarding_method !== 'self_serve_trial') return false
      if (filters.onboarding === 'not_self_serve' && d.onboarding_method === 'self_serve_trial') return false
      if (filters.onboarding === 'customer' && !d.is_customer) return false
      if (filters.onboarding === 'not_onboarded' && (d.is_customer || (d.onboarding_method && d.onboarding_method !== 'none'))) return false
      if ((minTrialDays != null || maxTrialDays != null)
        && (d.min_trial_days_remaining == null
          || (minTrialDays != null && d.min_trial_days_remaining < minTrialDays)
          || (maxTrialDays != null && d.min_trial_days_remaining > maxTrialDays))) return false
      return true
    })
  }, [deals, filters])

  // Sorts WITHIN each stage — buildBoard groups by stage in whatever order
  // it's handed, so sorting the flat list first sorts each resulting column.
  const sortedDeals = useMemo(() => {
    if (!sortBy) return filteredDeals
    const dir = sortDir === 'desc' ? -1 : 1
    const key = sortBy === 'club' ? (d => (d.marketing_club_name || d.title || '').toLowerCase())
      : sortBy === 'value' ? (d => d.effective_value_cents ?? d.value_cents ?? 0)
      : (d => d.engagement_score ?? -1)
    return [...filteredDeals].sort((a, b) => {
      const av = key(a), bv = key(b)
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
  }, [filteredDeals, sortBy, sortDir])

  const board = useMemo(() => buildBoard(stages, sortedDeals), [stages, sortedDeals])
  const stageName = (id) => stages.find(s => s.id === id)?.name || '—'

  // The List view sorts independently of the Board's "sort within stage"
  // control — every visible column, not just the four the Board exposes.
  const [listSortBy, setListSortBy] = useState('')
  const [listSortDir, setListSortDir] = useState('asc')
  const listSortedDeals = useMemo(() => {
    if (!listSortBy) return filteredDeals
    const dir = listSortDir === 'desc' ? -1 : 1
    const keyFns = {
      club: d => (d.marketing_club_name || d.title || '').toLowerCase(),
      poc: d => (d.point_of_contact_name || '').toLowerCase(),
      stage: d => stageName(d.stage_id).toLowerCase(),
      value: d => d.effective_value_cents ?? d.value_cents ?? 0,
      weighted: d => d.weighted_value_cents ?? 0,
      engagement: d => d.engagement_score ?? -1,
      source: d => (channelLabel(d.acquisition_channel) || '').toLowerCase(),
      status: d => d.status || '',
    }
    const key = keyFns[listSortBy] || (() => 0)
    return [...filteredDeals].sort((a, b) => {
      const av = key(a), bv = key(b)
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
  }, [filteredDeals, listSortBy, listSortDir, stages])

  const clickListSort = (key) => {
    if (listSortBy !== key) { setListSortBy(key); setListSortDir('asc'); return }
    setListSortDir(d => d === 'asc' ? 'desc' : 'asc')
  }

  return (
    <AdminLayout>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h1 className="font-display font-bold text-xl">BetterCRM — Sales Pipeline</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setView('board')}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${view === 'board' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint'}`}>Board</button>
          <button onClick={() => setView('list')}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${view === 'list' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint'}`}>List</button>
          <Btn variant="ghost" sm onClick={() => setShowStages(true)}>Manage stages</Btn>
          <Btn variant="primary" sm onClick={() => setShowNew(true)}>New deal</Btn>
        </div>
      </div>

      {loading ? <PbSpinner message="Loading pipeline…" /> : (
        <>
          <FilterBar filters={filters} setFilters={setFilters} owners={owners} stateOptions={stateOptions}
            associationOptions={associationOptions} channelOptions={channelOptions} resultCount={filteredDeals.length} />

          <div className="mb-4 -mt-2">
            <SortButtons sortBy={sortBy} sortDir={sortDir}
              onChange={(key, dir) => { setSortBy(key); setSortDir(dir) }} />
          </div>

          {view === 'board' && (
            <PipelineBoard board={board} onOpenDeal={setOpenDealId} onMoved={load} client={superClient} />
          )}
          {view === 'list' && (
            <>
              <div className="flex items-center gap-2 mb-4">
                {['open', 'won', 'lost', ''].map(s => (
                  <button key={s || 'all'} onClick={() => setStatus(s)}
                    className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                      status === s ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                    {s ? s[0].toUpperCase() + s.slice(1) : 'All'}
                  </button>
                ))}
              </div>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-pb-faint border-b border-pb-hairline">
                      <SortableTh label="Club" sortKey="club" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Point of contact" sortKey="poc" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Stage" sortKey="stage" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Value" sortKey="value" align="right" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Weighted" sortKey="weighted" align="right" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Engagement" sortKey="engagement" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Source" sortKey="source" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                      <SortableTh label="Status" sortKey="status" sortBy={listSortBy} sortDir={listSortDir} onSort={clickListSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {listSortedDeals.length === 0 && (
                      <tr><td colSpan={8} className="px-3 py-6 text-center text-pb-faintest">
                        {deals.length === 0 ? 'No deals yet.' : 'No deals match these filters.'}
                      </td></tr>
                    )}
                    {listSortedDeals.map(d => (
                      <tr key={d.id} onClick={() => setOpenDealId(d.id)} className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2 cursor-pointer">
                        <td className="px-3 py-2.5">
                          {d.title}
                          {d.is_customer && (
                            <span className="ml-1.5 text-[9px] font-mono uppercase tracking-wide px-1 py-px rounded bg-emerald-500/12 text-emerald-300">customer</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-pb-faint">{d.point_of_contact_name || '—'}</td>
                        <td className="px-3 py-2.5 text-pb-faint">{stageName(d.stage_id)}</td>
                        <td className="px-3 py-2.5 text-right">{money(d.effective_value_cents ?? d.value_cents)}</td>
                        <td className="px-3 py-2.5 text-right text-pb-faint">{money(d.weighted_value_cents)}</td>
                        <td className="px-3 py-2.5">
                          {d.engagement_score != null && <Pill tone={TIER_TONE[d.engagement_tier] || 'faint'}>{d.engagement_score}</Pill>}
                        </td>
                        <td className="px-3 py-2.5 text-pb-faint">{channelLabel(d.acquisition_channel) || '—'}</td>
                        <td className="px-3 py-2.5">
                          {d.status === 'won' && <Pill tone="green">Won</Pill>}
                          {d.status === 'lost' && <Pill tone="red">Lost</Pill>}
                          {d.status === 'open' && <Pill>Open</Pill>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      <NewDealModal open={showNew} onClose={() => setShowNew(false)} stages={stages} onCreated={load} />
      <ManageStagesModal open={showStages} onClose={() => setShowStages(false)} stages={stages} onChanged={load} client={superClient} />
      <DealDetailModal
        dealId={openDealId} open={!!openDealId} onClose={() => setOpenDealId(null)}
        stages={stages} client={superClient} onChanged={load} moduleOptions={MODULE_OPTIONS}
        ownerOptions={owners}
      />
    </AdminLayout>
  )
}
