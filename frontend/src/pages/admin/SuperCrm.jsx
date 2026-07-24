import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import PipelineBoard, { TIER_TONE } from '../../components/admin/crm/PipelineBoard'
import DealDetailModal from '../../components/admin/crm/DealDetailModal'
import ManageStagesModal from '../../components/admin/crm/ManageStagesModal'
import {
  Modal, Field, TextInput, NumberInput, Select, Btn, Pill, money, MODULE_ORDER, moduleLabel, sortModuleKeys,
} from '../../components/admin/crm/ui'

const CHART_TOOLTIP_STYLE = { background: 'var(--pb-surface, #0b1220)', border: '1px solid var(--pb-hairline, #1a2540)', fontSize: 12 }
const AXIS_TICK = { fill: 'var(--pb-faint, #64748b)', fontSize: 10 }

// Read-only analysis over the SAME deal list Board/List already have loaded —
// no separate fetch. "Trial conversions" and "pipeline by stage" are current
// snapshots, not historical trends (no stage-transition history is kept —
// see services/crm_targets.py's own docstring for the same caveat).
function CrmDashboard({ deals, stages }) {
  const stageData = useMemo(() => {
    const openDeals = deals.filter(d => d.status === 'open')
    return stages.map(s => {
      const inStage = openDeals.filter(d => d.stage_id === s.id)
      const value = inStage.reduce((sum, d) => sum + (d.effective_value_cents ?? d.value_cents ?? 0), 0)
      const weighted = inStage.reduce((sum, d) => sum + (d.weighted_value_cents ?? 0), 0)
      return { name: s.name, count: inStage.length, value: Math.round(value / 100), weighted: Math.round(weighted / 100) }
    })
  }, [deals, stages])

  const leadSourceData = useMemo(() => {
    const counts = {}
    for (const d of deals) {
      const key = d.lead_source || d.acquisition_channel || 'unknown'
      counts[key] = (counts[key] || 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([name, count]) => ({ name, count }))
  }, [deals])

  const moduleData = useMemo(() => {
    const counts = {}
    for (const d of deals) for (const k of (d.module_keys || [])) counts[k] = (counts[k] || 0) + 1
    return sortModuleKeys(Object.keys(counts)).map(k => ({ name: moduleLabel(k), count: counts[k] }))
  }, [deals])

  const trialStats = useMemo(() => {
    const trialOnboarded = deals.filter(d => ['self_serve_trial', 'super_admin_trial'].includes(d.onboarding_method))
    const won = trialOnboarded.filter(d => d.status === 'won')
    const lost = trialOnboarded.filter(d => d.status === 'lost')
    const open = trialOnboarded.filter(d => d.status === 'open')
    return {
      total: trialOnboarded.length, won: won.length, open: open.length,
      rate: (won.length + lost.length) ? Math.round(100 * won.length / (won.length + lost.length)) : null,
    }
  }, [deals])

  return (
    <div className="space-y-5">
      <div className="pb-card px-4 py-3">
        <h3 className="font-display font-bold text-[13px] mb-2">Clubs by stage</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={stageData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={55} />
            <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
            <Bar dataKey="count" name="Clubs" fill="var(--pb-accent, #16c784)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="pb-card px-4 py-3">
        <h3 className="font-display font-bold text-[13px] mb-2">Pipeline value by stage ($, weighted vs unweighted)</h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={stageData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={55} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
            <Tooltip formatter={v => `$${Number(v).toLocaleString()}`} contentStyle={CHART_TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="value" name="Unweighted" fill="var(--pb-accent, #16c784)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="weighted" name="Weighted" fill="var(--pb-amber, #f5a623)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="pb-card px-4 py-3">
          <h3 className="font-display font-bold text-[13px] mb-2">Lead source</h3>
          <ResponsiveContainer width="100%" height={Math.max(160, leadSourceData.length * 28)}>
            <BarChart data={leadSourceData} layout="vertical" margin={{ left: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis type="number" allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={110} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Bar dataKey="count" fill="var(--pb-accent, #16c784)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="pb-card px-4 py-3">
          <h3 className="font-display font-bold text-[13px] mb-2">Module interest</h3>
          <ResponsiveContainer width="100%" height={Math.max(160, moduleData.length * 28)}>
            <BarChart data={moduleData} layout="vertical" margin={{ left: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis type="number" allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={80} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Bar dataKey="count" fill="var(--pb-accent, #16c784)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="pb-card px-4 py-3">
        <h3 className="font-display font-bold text-[13px] mb-2">Trial conversions</h3>
        <p className="text-[12px] text-pb-faint mb-2">
          Deals onboarded via a trial (Self-Serve or Super Admin) — a current snapshot, not a
          historical trend (no stage-history table is kept).
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
          <div><div className="text-pb-faint text-[10.5px] uppercase">Total ever trialled</div><div className="font-display font-bold text-[16px]">{trialStats.total}</div></div>
          <div><div className="text-pb-faint text-[10.5px] uppercase">Still trialling</div><div className="font-display font-bold text-[16px]">{trialStats.open}</div></div>
          <div><div className="text-pb-faint text-[10.5px] uppercase">Converted (Won)</div><div className="font-display font-bold text-[16px] text-emerald-300">{trialStats.won}</div></div>
          <div><div className="text-pb-faint text-[10.5px] uppercase">Conversion rate</div><div className="font-display font-bold text-[16px]">{trialStats.rate != null ? `${trialStats.rate}%` : '—'}</div></div>
        </div>
      </div>

      <div className="pb-card px-4 py-3 flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-display font-bold text-[13px]">Targets &amp; projections</h3>
          <p className="text-[12px] text-pb-faint">Define targets by month/quarter/FY, track progress and a run-rate forecast.</p>
        </div>
        <Link to="/admin/super/crm/targets"
          className="px-3 py-1.5 rounded-lg text-[12.5px] border border-pb-hairline2 text-pb-text hover:border-pb-accent">
          Open Sales Targets →
        </Link>
      </div>
    </div>
  )
}

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
  recalcProductInterest: api.superCrmRecalcProductInterest,
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
  onboarding: '', minTrialDays: '', maxTrialDays: '', trialExpired: false, customersOnly: false,
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

// Fixed pixel widths, not Tailwind width classes — the shared TextInput/
// Select/NumberInput components hardcode `w-full` in their inputCls, and a
// same-specificity Tailwind utility class can't reliably win against it
// (stylesheet order decides, not JSX prop order). An inline style always
// wins, which is what actually lets this bar fit two compact rows instead of
// one control per line.
// State pinned to the same width as Owner (was narrower); Association
// doubled — both per direct instruction.
const FBW = { search: '210px', owner: '120px', state: '120px', assoc: '240px', source: '130px', onboarding: '140px', num: '64px' }

function FilterBar({ filters, setFilters, owners, stateOptions, associationOptions, channelOptions, resultCount, sortBy, sortDir, onSortChange }) {
  // Open by default — a filter bar that starts collapsed hides the very
  // controls someone opened this page to use (per direct instruction).
  const [open, setOpen] = useState(true)
  const set = (key) => (e) => setFilters(f => ({ ...f, [key]: e.target.value }))
  const toggleModule = (key) => setFilters(f => ({
    ...f, modules: f.modules.includes(key) ? f.modules.filter(k => k !== key) : [...f.modules, key],
  }))
  const toggleBool = (key) => setFilters(f => ({ ...f, [key]: !f[key] }))
  const active = Object.entries(filters).some(([k, v]) =>
    typeof v === 'boolean' ? v : Array.isArray(v) ? v.length > 0 : v !== '')

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
        <div className="mt-3 space-y-2.5">
          {/* Row 1: search + owner/state/association/source/onboarding — all
              on one row where space allows (wraps to a 2nd row on narrow
              screens), each pinned to a compact width instead of stretching. */}
          <div className="flex flex-wrap gap-2">
            <TextInput placeholder="Club name or point of contact" value={filters.q} onChange={set('q')} style={{ width: FBW.search }} />
            <Select value={filters.ownerId} onChange={set('ownerId')} style={{ width: FBW.owner }}>
              <option value="">Any owner</option>
              <option value="__unassigned__">Unassigned</option>
              {owners.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            <Select value={filters.state} onChange={set('state')} style={{ width: FBW.state }}>
              <option value="">Any state</option>
              {stateOptions.map(s => <option key={s} value={s}>{s}</option>)}
            </Select>
            <TextInput list="crm-associations" placeholder="Association" value={filters.association} onChange={set('association')} style={{ width: FBW.assoc }} />
            <datalist id="crm-associations">{associationOptions.map(a => <option key={a} value={a} />)}</datalist>
            <Select value={filters.channel} onChange={set('channel')} style={{ width: FBW.source }}>
              <option value="">Any source</option>
              {channelOptions.map(c => <option key={c} value={c}>{channelLabel(c)}</option>)}
            </Select>
            <Select value={filters.onboarding} onChange={set('onboarding')} style={{ width: FBW.onboarding }}>
              {ONBOARDING_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          {/* Row 2: Value $ / Engagement / Trial-expiring-days — one row. */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint">Value $</span>
              <NumberInput min={0} placeholder="min" value={filters.minValue} onChange={set('minValue')} style={{ width: FBW.num }} />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} placeholder="max" value={filters.maxValue} onChange={set('maxValue')} style={{ width: FBW.num }} />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint">Engagement</span>
              <NumberInput min={0} max={100} placeholder="min" value={filters.minScore} onChange={set('minScore')} style={{ width: FBW.num }} />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} max={100} placeholder="max" value={filters.maxScore} onChange={set('maxScore')} style={{ width: FBW.num }} />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-pb-faint" title="Only clubs with a tracked module trial (i.e. already onboarded)">Trial expiring in (days)</span>
              <NumberInput min={0} placeholder="min" value={filters.minTrialDays} onChange={set('minTrialDays')} style={{ width: FBW.num }} />
              <span className="text-[11px] text-pb-faint">to</span>
              <NumberInput min={0} placeholder="max" value={filters.maxTrialDays} onChange={set('maxTrialDays')} style={{ width: FBW.num }} />
            </div>
            <button type="button" onClick={() => toggleBool('trialExpired')}
              title="At least one module's trial has run out"
              className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                filters.trialExpired ? 'bg-pb-amber/15 border-pb-amber/50 text-pb-amber' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
              Trial expired
            </button>
            <button type="button" onClick={() => toggleBool('customersOnly')}
              title="Club is a paying subscriber for at least one module"
              className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                filters.customersOnly ? 'bg-emerald-500/15 border-emerald-500/50 text-emerald-300' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
              Customers
            </button>
          </div>
          {/* Row 3: Product Interest chips + Sort-by, together on one line. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-0.5">
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
            {onSortChange && <span className="w-px self-stretch bg-pb-hairline2" />}
            {onSortChange && <SortButtons sortBy={sortBy} sortDir={sortDir} onChange={onSortChange} />}
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
      // trial_days_remaining_by_club clamps at 0 (never negative), so a 0
      // reads as "ends today or already ended" — the closest this data lets
      // us get to "expired" without a day of slack either way.
      if (filters.trialExpired && d.min_trial_days_remaining !== 0) return false
      if (filters.customersOnly && !(d.subscribed_modules && d.subscribed_modules.length > 0)) return false
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
          <button onClick={() => setView('dashboard')}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${view === 'dashboard' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint'}`}>Dashboard</button>
          <Btn variant="ghost" sm onClick={() => setShowStages(true)}>Manage stages</Btn>
          <Btn variant="primary" sm onClick={() => setShowNew(true)}>New deal</Btn>
        </div>
      </div>

      {loading ? <PbSpinner message="Loading pipeline…" /> : view === 'dashboard' ? (
        <CrmDashboard deals={deals} stages={stages} />
      ) : (
        <>
          <FilterBar filters={filters} setFilters={setFilters} owners={owners} stateOptions={stateOptions}
            associationOptions={associationOptions} channelOptions={channelOptions} resultCount={filteredDeals.length}
            sortBy={sortBy} sortDir={sortDir} onSortChange={(key, dir) => { setSortBy(key); setSortDir(dir) }} />

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
                      <tr key={d.id} onClick={() => setOpenDealId(d.id)}
                        className={`border-b border-pb-hairline last:border-0 hover:bg-pb-surface2 cursor-pointer ${
                          d.is_customer ? 'border-l-2 border-l-emerald-500/70' : ''}`}>
                        <td className="px-3 py-2.5" title={d.is_customer ? 'Already a BetterCricket subscriber' : undefined}>
                          {d.title}
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
