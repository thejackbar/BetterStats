import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import EmailEditorTabs from '../../components/admin/EmailEditorTabs'
import { Modal, Field, TextInput, NumberInput, Select, TextArea, Btn, Pill, moduleLabel, MODULE_ORDER } from '../../components/admin/crm/ui'
import SalesEventsView from '../../components/admin/crm/SalesEventsView'
import { groupedOutcomes, outcomeLabel } from '../../lib/salesOutcomes'

const CARD = 'pb-card p-3'

// Mirrors services/sales_workspace.py's _ASSIGNABLE_EVENT_OUTCOMES — these
// three specifically ask to speak with "someone" about pricing/info/a demo,
// so the resulting follow-up Event can be handed to a named staff member
// instead of defaulting to whoever logged the call.
const ASSIGNABLE_EVENT_OUTCOMES = ['wants_pricing', 'wants_more_info', 'wants_demo']

// The Follow up field's default value — "now", in the local-time string a
// <input type="datetime-local"> needs (YYYY-MM-DDTHH:mm, no timezone) — so
// the picker opens on today/now instead of blank, and a rep only has to
// adjust it rather than fill in every field from scratch.
function nowLocalDatetimeValue() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const emptyCallForm = () => ({ contactKey: '', outcome: '', notes: '', followUpAt: nowLocalDatetimeValue(), eventOwnerUserId: '' })

// Close-on-outside-click + Escape, for the Stage multi-select popover below.
function useDismiss(open, onClose) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  return ref
}

// Stage is a multi-select: narrowing to "Target, Contacted" is an OR within
// the field (a club at either stage matches), same convention BetterIQ's
// TeamPicker uses for a multi-grade filter.
// The single real 'trial' stage reads as two things to a salesperson —
// still running, or lapsed and worth a different kind of call — so the
// picker splits it into two synthetic keys the backend interprets specially
// (services/sales_workspace.py never stores these; they only ever mean
// "stage=trial AND expired/not"). Every other stage passes through as-is.
function displayStages(stages) {
  const out = []
  for (const s of stages || []) {
    if (s.key === 'trial') {
      out.push({ id: 'trial_current', key: 'trial_current', name: 'Trial (Current)' })
      out.push({ id: 'trial_expired', key: 'trial_expired', name: 'Trial (Expired)' })
    } else {
      out.push(s)
    }
  }
  return out
}

// Shared popover multi-select — Stage and State pickers are both this with a
// different option list, rather than two near-identical popovers.
function MultiSelectPicker({ options, value, onChange, allLabel, noun }) {
  const [open, setOpen] = useState(false)
  const ref = useDismiss(open, () => setOpen(false))
  const picked = new Set(value)
  const toggle = (key) => {
    const next = new Set(picked)
    if (next.has(key)) next.delete(key); else next.add(key)
    onChange([...next])
  }
  const label = picked.size === 0 ? allLabel
    : picked.size === 1 ? options.find(o => o.key === value[0])?.name || value[0]
    : `${picked.size} ${noun}`
  return (
    <div className="relative" ref={ref}>
      <button
        type="button" onClick={() => setOpen(o => !o)}
        className="w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px] outline-none focus:border-pb-accent text-left flex items-center justify-between gap-2"
      >
        <span className={picked.size === 0 ? 'text-pb-faint' : ''}>{label}</span>
        <span className="text-pb-faintest text-[10px]">▾</span>
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-lg border border-pb-hairline2 bg-pb-surface shadow-lg py-1 max-h-64 overflow-y-auto">
          <button type="button" onClick={() => onChange([])}
            className={`w-full text-left px-2.5 py-1.5 text-[12.5px] hover:bg-pb-surface2 ${picked.size === 0 ? 'text-pb-accent' : 'text-pb-text'}`}>
            {allLabel}
          </button>
          {options.map(o => (
            <label key={o.key} className="flex items-center gap-2 px-2.5 py-1.5 text-[12.5px] text-pb-text hover:bg-pb-surface2 cursor-pointer select-none">
              <input type="checkbox" checked={picked.has(o.key)} onChange={() => toggle(o.key)} />
              {o.name}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
function StagePicker({ stages, value, onChange }) {
  const options = useMemo(() => displayStages(stages), [stages])
  return <MultiSelectPicker options={options} value={value} onChange={onChange} allLabel="All stages" noun="stages" />
}

// The state abbreviations PlayHQ stores on a club (mirrors SuperMarketing.jsx's
// own STATES list — kept local rather than shared, since it's an 8-item const).
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']
const STATE_OPTIONS = STATES.map(s => ({ key: s, name: s }))
function StatePicker({ value, onChange }) {
  return <MultiSelectPicker options={STATE_OPTIONS} value={value} onChange={onChange} allLabel="All states" noun="states" />
}

// One labelled row of filter controls inside the filter card — a small mono
// caption above a flex-wrap row, separated from the row before it by a
// hairline. Keeps "what filters what" legible as the control count grows,
// instead of one long unbroken row.
function FilterSection({ label, children, first = false }) {
  return (
    <div className={first ? '' : 'pt-3 mt-3 border-t border-pb-hairline'}>
      <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase mb-2">{label}</p>
      <div className="flex flex-wrap items-end gap-3">{children}</div>
    </div>
  )
}

const SORT_OPTIONS = [
  { key: '', name: 'Recommended' },
  { key: 'recent', name: 'Recent' },
  { key: 'club_name', name: 'Club name' },
  { key: 'engagement_score', name: 'Engagement score' },
  { key: 'trial_days', name: 'Trial days' },
]
// Mirrors services/sales_workspace.py's _SORT_DEFAULT_DIR — each field's
// sensible default direction, so the ▲/▼ toggle knows which way is "back to
// default" without a round trip to the server.
const _SORT_DEFAULT_DIR_FE = { recent: 'desc', club_name: 'asc', engagement_score: 'desc', trial_days: 'asc' }
const contactKey = (c) => c.directory_contact_id || c.crm_person_id
const NEW_CONTACT_VALUE = '__new__'

// Inline "not in the list" contact entry, shared by both the Log a Call and
// Send an Email contact pickers — a rep shouldn't have to leave the form
// they're in to add someone first. Writes straight to the canonical Club
// Directory (routers/sales_workspace.py's add_contact, same table the
// dedicated Contacts tab's own "+ Add contact" form uses), and hands the
// created contact back so the caller can both select it immediately and
// merge it into drawer.contacts for the OTHER picker too.
function InlineNewContact({ dealId, onCreated, onCancel, toast }) {
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', mobile: '' })
  const [saving, setSaving] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    const full_name = `${form.firstName.trim()} ${form.lastName.trim()}`.trim()
    if (!full_name) { toast?.error('First and last name are required'); return }
    if (!form.email.trim() && !form.mobile.trim()) { toast?.error('An email or mobile number is required'); return }
    setSaving(true)
    try {
      const res = await api.salesWorkspaceAddContact(dealId, {
        full_name, email: form.email.trim() || null, mobile: form.mobile.trim() || null,
      })
      if (res.contact) onCreated(res.contact)
      else toast?.error('Contact saved, but could not be added to this list yet — reopen the club to see it')
    } catch (err) {
      toast?.error(err.message || 'Could not add contact')
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="grid grid-cols-2 gap-1.5 p-2 rounded-lg border border-pb-hairline2 bg-pb-surface2">
      <TextInput placeholder="First name" value={form.firstName} onChange={e => setForm(f => ({ ...f, firstName: e.target.value }))} />
      <TextInput placeholder="Last name" value={form.lastName} onChange={e => setForm(f => ({ ...f, lastName: e.target.value }))} />
      <TextInput placeholder="Email" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
      <TextInput placeholder="Mobile" value={form.mobile} onChange={e => setForm(f => ({ ...f, mobile: e.target.value }))} />
      <div className="col-span-2 flex justify-end gap-2">
        <Btn type="button" sm variant="ghost" onClick={onCancel}>Cancel</Btn>
        <Btn type="button" sm variant="primary" disabled={saving} onClick={submit}>{saving ? 'Adding…' : 'Add contact'}</Btn>
      </div>
    </div>
  )
}

function ScorePill({ score, tier }) {
  if (score == null) return <span className="text-pb-faintest text-[11px]">Not scored</span>
  const tone = { HOT: 'red', WARM: 'amber' }[tier] || 'faint'
  return (
    <span className="inline-flex items-center gap-1">
      <span className="font-display font-bold text-[13px]">{score}</span>
      <Pill tone={tone}>{(tier || '').replace(/_/g, ' ') || 'COLD'}</Pill>
    </span>
  )
}

function PriorityBadge({ score }) {
  const tone = score >= 80 ? 'red' : score >= 50 ? 'amber' : 'faint'
  return <Pill tone={tone}>P{score}</Pill>
}

function timeAgo(iso) {
  if (!iso) return null
  const d = Math.round((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d <= 0) return 'today'
  if (d === 1) return 'yesterday'
  return `${d}d ago`
}

const ONBOARDING_METHOD_LABELS = {
  self_serve_trial: 'Self-Serve Trial',
  super_admin_trial: 'Super Admin Trial',
  direct_subscriber: 'Direct Subscriber',
  none: 'Not onboarded',
}

// The onboarded-club facts line (state/seasons/grades/players/setup/active
// since) — mirrors the Sales Pipeline card's own `stateLine` construction in
// components/admin/crm/PipelineBoard.jsx so the two surfaces never disagree
// about what these numbers mean. `stats` is `deal.club_stats`, absent for a
// bare prospect that's never been onboarded.
function clubStatsLine(state, stats) {
  return [
    state,
    stats && `${stats.seasons_count ?? 0} season${(stats.seasons_count ?? 0) === 1 ? '' : 's'}`,
    stats && `${stats.grades_count ?? 0} grade${(stats.grades_count ?? 0) === 1 ? '' : 's'}`,
    stats && `${stats.players_count ?? 0} player${(stats.players_count ?? 0) === 1 ? '' : 's'}`,
    stats && stats.setup_total > 0 && `setup ${stats.setup_done}/${stats.setup_total}`,
    stats && stats.active_since && `active since ${new Date(stats.active_since).toLocaleDateString('en-AU')}`,
  ].filter(Boolean).join(' · ')
}

// This club's trial and registration story — only rendered once a club is
// actually onboarded (subscriber or trialing); a bare prospect has neither a
// trial countdown nor a registrant. `min_trial_days_remaining` is SIGNED
// (see crm.trial_days_remaining_by_club) — negative means the trial's own
// end date has already passed, which is what tells "13 days left" apart
// from "expired 3 days ago" instead of both reading as a plain countdown.
function ClubSummaryCard({ deal }) {
  const stats = deal.club_stats
  const hasFacts = deal.is_customer || deal.min_trial_days_remaining != null || stats
  if (!hasFacts && !deal.registrant) return null
  const line = clubStatsLine(deal.marketing_club_state, stats)
  const days = deal.min_trial_days_remaining
  return (
    <div className="space-y-1.5 mt-2 pt-2 border-t border-pb-hairline">
      {line && <p className="text-[12px] text-pb-faint">{line}</p>}
      {days != null && (
        days >= 0
          ? <p className="text-[12.5px] text-pb-text">Trial: <span className="font-medium">{days} day{days === 1 ? '' : 's'} left</span></p>
          : <p className="text-[12.5px] text-pb-red">Trial: <span className="font-medium">EXPIRED ({Math.abs(days)} day{Math.abs(days) === 1 ? '' : 's'} ago)</span></p>
      )}
      {deal.registrant?.name && (
        <p className="text-[12px] text-pb-faint">
          Registered by <span className="text-pb-text">{deal.registrant.name}</span>
          {deal.registrant.role ? <span className="text-pb-faintest"> ({deal.registrant.role})</span> : ''}
        </p>
      )}
    </div>
  )
}

const WIZARD_SOURCE_LABEL = {
  both: 'Searched & selected in the trial wizard',
  selected: 'Selected itself in the trial wizard',
  searched: 'Searched for itself in the trial wizard',
}

// Someone from this club typed its name into the trial signup search, or
// picked it — a real buying signal worth a rep seeing even before anything
// else has happened. Same data (and the same guid-first, name-fallback
// match) the Wizard Clubs page itself reads, narrowed to this one club.
function WizardSignalCard({ signal }) {
  if (!signal) return null
  const queries = (signal.queries || []).filter(Boolean)
  return (
    <div className={CARD}>
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <h3 className="font-display font-bold text-[13px]">{WIZARD_SOURCE_LABEL[signal.source] || 'Trial wizard activity'}</h3>
        {signal.via_meta && <Pill tone="accent">META AD</Pill>}
      </div>
      {queries.length > 0 && (
        <p className="text-[12px] text-pb-faint">
          Searched: {queries.map((q, i) => (
            <span key={q}>{i > 0 && ' · '}<span className="text-pb-text">&ldquo;{q}&rdquo;</span></span>
          ))}
        </p>
      )}
      {signal.furthest_step && (
        <p className="text-[12px] text-pb-faint mt-0.5">Progress: <span className="text-pb-text">{signal.furthest_step}</span></p>
      )}
      {signal.last_at && (
        <p className="text-[11px] text-pb-faintest mt-0.5">Last seen {new Date(signal.last_at).toLocaleDateString('en-AU')}</p>
      )}
    </div>
  )
}

// Stage / onboarding method / call status — the three things a rep asks
// first before reading the engagement breakdown below it.
// Stage / Onboarding / Called / Engagement — the four things a rep reads
// first, together at the top of the drawer rather than the score being
// buried in its own card further down.
function DealSummaryStrip({ deal }) {
  const called = deal.ever_called
    ? `Yes — ${timeAgo(deal.last_call?.occurred_at) || 'logged'}`
    : 'Never called'
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest mb-0.5">Stage</div>
        <div className="text-[13px] text-pb-text font-medium">{deal.stage_name || '—'}</div>
      </div>
      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest mb-0.5">Onboarding</div>
        <div className="text-[13px] text-pb-text font-medium">
          {ONBOARDING_METHOD_LABELS[deal.onboarding_method] || deal.onboarding_method || '—'}
        </div>
      </div>
      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest mb-0.5">Called</div>
        <div className={`text-[13px] font-medium ${deal.ever_called ? 'text-pb-text' : 'text-pb-amber'}`}>{called}</div>
      </div>
      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest mb-0.5">Engagement</div>
        <div className="flex items-center justify-center">
          <ScorePill score={deal.engagement_score} tier={deal.engagement_tier} />
        </div>
      </div>
    </div>
  )
}

// ─── Engagement panel (sourced from the drawer's own already-fetched
// `engagement` field, NOT a second fetch — club_engagement_breakdown is
// super-admin-only server-side, so a 'sales' role must never call it
// directly; the Workspace's own GET /clubs/{id} already embeds it). ───────────
function EngagementPanel({ engagement }) {
  if (!engagement) {
    return <p className="text-[12px] text-pb-faintest">No engagement data for this club yet.</p>
  }
  const contribs = engagement.contributions || []
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <ScorePill score={engagement.score} tier={engagement.tier} />
        {engagement.is_customer && <span className="text-[11px] text-pb-faint">already linked to a real club</span>}
      </div>
      {engagement.explanation && <p className="text-[11.5px] text-pb-faint italic">{engagement.explanation}</p>}
      {contribs.length > 0 ? (
        <div className="space-y-1">
          {contribs.map((c, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2 text-[12px] border-b border-pb-hairline/50 pb-1">
              <div>
                <span className="text-pb-text">{c.label}</span>
                {c.detail && <div className="text-pb-faintest text-[10.5px]">{c.detail}</div>}
              </div>
              <span className="font-display font-bold whitespace-nowrap" style={{ color: 'var(--pb-accent)' }}>+{c.points}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-pb-faintest">No tracked signals yet.</p>
      )}
      {engagement.signals && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          {[
            ['Visitors 30d', engagement.signals.sessions_30d],
            ['Email opens', engagement.signals.email_opens],
            ['Email clicks', engagement.signals.email_clicks],
            ['Ad clicks', engagement.signals.ad_clicks],
          ].map(([label, val]) => (
            <div key={label} className="pb-card px-2.5 py-2">
              <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">{label}</div>
              <div className="font-display font-bold text-[15px]">{val ?? 0}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Same panel the Sales Pipeline card shows (components/admin/crm/ui.jsx's
// WebsiteAnalyticsPanel) but reading off the drawer's own already-fetched
// `website_visits` field instead of fetching it itself — that component's
// own fetch (api.mktClubVisits) hits a super-admin-only endpoint a 'sales'
// caller can't reach, so the Sales Workspace drawer embeds the same data
// server-side instead (see routers/sales_workspace.py::get_club).
function WebsiteAnalyticsCard({ data }) {
  if (!data?.views) {
    return <p className="text-[12px] text-pb-faintest">No tracked site visits for this club yet.</p>
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
      <div className="pb-card px-2.5 py-2">
        <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Page views</div>
        <div className="font-display font-bold text-[15px]">{data.views}</div>
      </div>
      <div className="pb-card px-2.5 py-2">
        <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Days visited</div>
        <div className="font-display font-bold text-[15px]">{data.distinct_days}</div>
      </div>
      <div className="pb-card px-2.5 py-2">
        <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Unique IPs</div>
        <div className="font-display font-bold text-[15px]">{data.unique_ips}</div>
        {data.visits_per_ip != null && <div className="text-pb-faintest text-[10.5px]">{data.visits_per_ip}/IP avg</div>}
      </div>
      <div className="pb-card px-2.5 py-2">
        <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Contact page</div>
        <div className="font-display font-bold text-[15px]">{data.contact_page_visited ? 'Visited' : 'No'}</div>
      </div>
      {data.inferred_modules?.length > 0 && (
        <div className="col-span-2 sm:col-span-4 pb-card px-2.5 py-2">
          <div className="text-pb-faint text-[10.5px] uppercase tracking-wide mb-1">Analytics-derived product interest</div>
          <div className="flex flex-wrap gap-1">
            {data.inferred_modules.map(k => <Pill key={k} tone="accent">{moduleLabel(k)}</Pill>)}
          </div>
        </div>
      )}
    </div>
  )
}

function ActivityRow({ a }) {
  const kindLabel = a.type === 'call' ? (a.outcome ? outcomeLabel(a.outcome) : 'Call') : a.type === 'system' ? 'System' : a.meta?.pinned ? 'Pinned note' : 'Note'
  const tone = a.type === 'call' ? 'accent' : a.type === 'system' ? 'faint' : a.meta?.pinned ? 'amber' : 'faint'
  return (
    <div className="border-b border-pb-hairline/50 pb-2 mb-2 text-[12px]">
      <div className="flex items-center justify-between gap-2">
        <Pill tone={tone}>{kindLabel}</Pill>
        <span className="text-pb-faintest text-[10.5px]">{new Date(a.occurred_at).toLocaleString('en-AU')}</span>
      </div>
      {a.body && <p className="mt-1 text-pb-text whitespace-pre-wrap">{a.body}</p>}
      {a.next_follow_up_at && (
        <p className="mt-1 text-[10.5px] text-pb-amber">Follow up {new Date(a.next_follow_up_at).toLocaleString('en-AU')}</p>
      )}
    </div>
  )
}

export default function SalesWorkspace() {
  const { user, logout } = useAuth()
  const toast = useToast()
  const isSuper = user?.role === 'super_admin'
  const [searchParams, setSearchParams] = useSearchParams()

  // Queue (the daily calling list + drawer) vs Events (List/Calendar of
  // every event a call outcome created plus anything added by hand).
  const [tab, setTab] = useState('queue')
  // Every club currently in scope for THIS user (unfiltered by the Queue
  // tab's own search/stage/owner filters) — just the "which club is this
  // event about" picker in the New Event form, so narrowing the queue view
  // doesn't also narrow what a rep can link a new event to.
  const [dealOptions, setDealOptions] = useState([])
  useEffect(() => {
    api.salesWorkspaceClubs({}).then(d => setDealOptions(
      (d.clubs || []).map(c => ({ id: c.id, name: c.marketing_club_name || c.title }))
    )).catch(() => {})
  }, [])

  const [filters, setFilters] = useState({
    q: '', stage_key: [], owner_user_id: '', called_clubs: false, callback_due: false, list_id: '',
    min_score: '', max_score: '', meta_selected: false, meta_searched: false, modules: [],
    states: [], sort: '', sort_dir: '',
  })
  const [clubs, setClubs] = useState([])
  const [stages, setStages] = useState([])
  const [team, setTeam] = useState([])
  const [staff, setStaff] = useState([])
  const [loadingList, setLoadingList] = useState(true)
  const [selectedId, setSelectedId] = useState(null)
  const [drawer, setDrawer] = useState(null)
  const [loadingDrawer, setLoadingDrawer] = useState(false)
  // Kept in sync with selectedId below, but read from inside loadClubs'/
  // refreshBoth's async callbacks — a plain closure over `selectedId` there
  // would see whatever it was when the callback was CREATED, not the latest
  // value, which is exactly the kind of stale-read that let the drawer keep
  // showing a club that had just dropped out of the filtered queue.
  const selectedIdRef = useRef(null)
  useEffect(() => { selectedIdRef.current = selectedId }, [selectedId])

  // Bulk assignment (super admin only) — checked deal ids from the CURRENT
  // filtered queue, and which reps are ticked in the bulk-assign panel: one
  // rep checked = assign everything to them, several = split evenly.
  const [checkedIds, setCheckedIds] = useState(() => new Set())
  const [bulkReps, setBulkReps] = useState(() => new Set())
  const [bulkAssigning, setBulkAssigning] = useState(false)

  const [callForm, setCallForm] = useState(emptyCallForm)
  const [savingCall, setSavingCall] = useState(false)
  // Merges a freshly-added contact into the shared drawer.contacts list (so
  // it's immediately selectable from BOTH the Log a Call and Send an Email
  // pickers, not just the one it was added from) and returns its key.
  const mergeNewContact = (contact) => {
    setDrawer(d => d ? { ...d, contacts: [...(d.contacts || []), contact] } : d)
    return contactKey(contact)
  }
  const [noteForm, setNoteForm] = useState({ body: '', pinned: false })
  const [savingNote, setSavingNote] = useState(false)
  const [showAddContact, setShowAddContact] = useState(false)
  const [contactForm, setContactForm] = useState({ full_name: '', role: '', email: '', mobile: '' })
  const [savingContact, setSavingContact] = useState(false)
  const [showStartTrial, setShowStartTrial] = useState(false)
  const [trialForm, setTrialForm] = useState({
    admin_first_name: '', admin_last_name: '', admin_display_name: '',
    admin_username: '', admin_email: '', admin_mobile_number: '',
  })
  const [savingTrial, setSavingTrial] = useState(false)

  const [emailTemplates, setEmailTemplates] = useState({ templates: [], demo_link_configured: false })
  const [emailForm, setEmailForm] = useState({ contactKey: '', template: '', subject: '', body: '' })
  const [savingEmail, setSavingEmail] = useState(false)
  const [showNewCallContact, setShowNewCallContact] = useState(false)
  const [showNewEmailContact, setShowNewEmailContact] = useState(false)
  // Design-mode editor for a BUILT-IN template's body (see BUILT_IN template
  // keys below) — 'custom' keeps the old plain Subject/Body text fields.
  // Bumped whenever a freshly-picked template's preview lands, since
  // EmailEditorTabs seeds its Design iframe once on mount (same reason
  // CommsTemplates.jsx bumps its own editorKey).
  const emailEditorRef = useRef(null)
  const [emailEditorKey, setEmailEditorKey] = useState(0)
  const [loadingEmailPreview, setLoadingEmailPreview] = useState(false)
  const BUILT_IN_EMAIL_TEMPLATES = ['information', 'trial_information', 'demo']

  useEffect(() => {
    api.salesWorkspaceEmailTemplates().then(setEmailTemplates).catch(() => {})
  }, [])

  const loadClubs = useCallback(() => {
    setLoadingList(true)
    return api.salesWorkspaceClubs(filters).then((d) => {
      const rows = d.clubs || []
      setClubs(rows)
      setStages(d.stages || [])
      // The currently-open drawer belongs to a club that just dropped out of
      // the filtered queue (a filter changed, or the club itself was
      // reassigned/updated out of the current filter) — clear it rather than
      // leave a deal detail on screen for something no longer in the list.
      if (selectedIdRef.current && !rows.some(c => c.id === selectedIdRef.current)) {
        selectedIdRef.current = null
        setSelectedId(null)
        setDrawer(null)
        setSearchParams((p) => { const n = new URLSearchParams(p); n.delete('club'); return n }, { replace: true })
      }
      return rows
    }).catch(() => { toast?.error('Could not load the club queue'); return [] })
      .finally(() => setLoadingList(false))
  }, [filters, toast, setSearchParams])

  useEffect(() => { loadClubs() }, [loadClubs])
  useEffect(() => {
    if (isSuper) api.salesWorkspaceTeam().then((d) => setTeam(d.team || [])).catch(() => {})
  }, [isSuper])
  // Every caller (sales included) needs the staff list — it's who a "wants
  // pricing/more info/a demo" follow-up can be handed off to, not a
  // super-admin-only assignment tool.
  useEffect(() => {
    api.salesWorkspaceStaff().then((d) => setStaff(d.staff || [])).catch(() => {})
  }, [])

  const loadDrawer = useCallback((dealId) => {
    setLoadingDrawer(true)
    api.salesWorkspaceClub(dealId).then((d) => {
      setDrawer(d)
      setCallForm(emptyCallForm())
    }).catch(() => toast?.error('Could not load this club')).finally(() => setLoadingDrawer(false))
  }, [toast])

  const selectClub = (dealId) => {
    selectedIdRef.current = dealId
    setSelectedId(dealId)
    loadDrawer(dealId)
    setSearchParams((p) => { const n = new URLSearchParams(p); n.set('club', dealId); return n }, { replace: true })
  }
  // Awaits the queue reload FIRST — loadClubs itself clears the selection
  // when the club no longer matches the current filter, and reading the ref
  // only after that settles is what stops the drawer briefly refetching a
  // club it's about to (or already did) drop.
  const refreshBoth = async () => {
    await loadClubs()
    if (selectedIdRef.current) loadDrawer(selectedIdRef.current)
  }

  // Deep link (e.g. from Sales Follow-ups: /admin/super/crm/workspace?club=<dealId>)
  useEffect(() => {
    const clubParam = searchParams.get('club')
    if (clubParam && clubParam !== selectedId) selectClub(clubParam)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Deep link from Sales Lists: /admin/super/crm/workspace?list_id=<id>&list_name=<name>
  const listParam = searchParams.get('list_id')
  const listNameParam = searchParams.get('list_name')
  useEffect(() => {
    if (listParam && listParam !== filters.list_id) setFilters(f => ({ ...f, list_id: listParam }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listParam])
  const clearListFilter = () => {
    setFilters(f => ({ ...f, list_id: '' }))
    setSearchParams((p) => { const n = new URLSearchParams(p); n.delete('list_id'); n.delete('list_name'); return n }, { replace: true })
  }

  // Current Trials / Expired Trials are their own checkboxes (matching the
  // Called clubs / Callback due treatment) even though under the hood
  // they're just the trial_current/trial_expired synthetic stage keys the
  // Stage picker already understands — toggles one entry in stage_key
  // without disturbing whatever real stages are also picked there.
  const toggleTrialFilter = (key) => setFilters(f => ({
    ...f, stage_key: f.stage_key.includes(key) ? f.stage_key.filter(k => k !== key) : [...f.stage_key, key],
  }))

  const toggleDoNotContact = async (contact) => {
    const next = !contact.do_not_contact
    let reason = null
    if (next) {
      reason = window.prompt('Reason (optional) — e.g. "Asked not to be called again"') || null
    }
    try {
      await api.salesWorkspaceSetDoNotContact(drawer.deal.id, contact.directory_contact_id, next, reason)
      loadDrawer(drawer.deal.id)
    } catch (err) {
      toast?.error(err.message)
    }
  }

  const pinnedNotes = useMemo(
    () => (drawer?.activities || []).filter(a => a.type === 'note' && a.meta?.pinned),
    [drawer]
  )
  const timeline = useMemo(
    () => (drawer?.activities || []).filter(a => !(a.type === 'note' && a.meta?.pinned)),
    [drawer]
  )

  // Saved immediately on click (not batched with Save Call) — the same
  // module_keys/product_interest_source fields the CRM Pipeline board's own
  // Product Interest chips write (DealDetailModal.jsx's toggleModule), so a
  // pick made here shows up there too.
  const toggleInterest = async (key) => {
    if (!drawer?.deal) return
    const cur = drawer.deal.module_keys || []
    const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
    try {
      const d = await api.salesWorkspaceSetInterest(drawer.deal.id, next)
      setDrawer(d)
      loadClubs()
    } catch (e) { toast?.error(e.message || 'Could not save module interest') }
  }

  const submitCall = async (e) => {
    e.preventDefault()
    if (!callForm.outcome) { toast?.error('Pick an outcome'); return }
    setSavingCall(true)
    try {
      const chosen = (drawer.contacts || []).find(c => contactKey(c) === callForm.contactKey)
      const payload = {
        outcome: callForm.outcome,
        notes: callForm.notes || null,
        next_follow_up_at: callForm.followUpAt ? new Date(callForm.followUpAt).toISOString() : null,
      }
      if (chosen?.directory_contact_id) payload.directory_contact_id = chosen.directory_contact_id
      else if (chosen?.crm_person_id) payload.crm_person_id = chosen.crm_person_id
      if (ASSIGNABLE_EVENT_OUTCOMES.includes(callForm.outcome) && callForm.eventOwnerUserId) {
        payload.event_owner_user_id = callForm.eventOwnerUserId
      }
      const d = await api.salesWorkspaceLogCall(drawer.deal.id, payload)
      setDrawer(d)
      setCallForm(emptyCallForm())
      toast?.success('Call logged')
      loadClubs()
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingCall(false)
    }
  }

  const submitNote = async (e) => {
    e.preventDefault()
    if (!noteForm.body.trim()) return
    setSavingNote(true)
    try {
      await api.salesWorkspaceAddNote(drawer.deal.id, noteForm)
      setNoteForm({ body: '', pinned: false })
      loadDrawer(drawer.deal.id)
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingNote(false)
    }
  }

  const submitContact = async (e) => {
    e.preventDefault()
    if (!contactForm.full_name.trim() || !(contactForm.email.trim() || contactForm.mobile.trim())) {
      toast?.error('Name plus an email or mobile is required')
      return
    }
    setSavingContact(true)
    try {
      await api.salesWorkspaceAddContact(drawer.deal.id, contactForm)
      setContactForm({ full_name: '', role: '', email: '', mobile: '' })
      setShowAddContact(false)
      loadDrawer(drawer.deal.id)
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingContact(false)
    }
  }

  const submitAssign = async (ownerUserId) => {
    try {
      await api.salesWorkspaceAssign(drawer.deal.id, ownerUserId)
      toast?.success('Reassigned')
      refreshBoth()
    } catch (err) {
      toast?.error(err.message)
    }
  }

  const toggleChecked = (id) => setCheckedIds(s => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const totalContacts = useMemo(() => clubs.reduce((n, c) => n + (c.contact_count || 0), 0), [clubs])
  const allChecked = clubs.length > 0 && clubs.every(c => checkedIds.has(c.id))
  const toggleSelectAllVisible = () => setCheckedIds(allChecked ? new Set() : new Set(clubs.map(c => c.id)))
  const toggleBulkRep = (id) => setBulkReps(s => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  const submitBulkAssign = async () => {
    if (checkedIds.size === 0) { toast?.error('Select at least one club'); return }
    if (bulkReps.size === 0) { toast?.error('Pick at least one salesperson'); return }
    setBulkAssigning(true)
    try {
      const result = await api.salesWorkspaceBulkAssign([...checkedIds], [...bulkReps])
      const summary = Object.entries(result.by_rep).map(([name, n]) => `${name}: ${n}`).join(', ')
      toast?.success(`Assigned ${result.assigned} club${result.assigned === 1 ? '' : 's'} — ${summary}`)
      setCheckedIds(new Set())
      setBulkReps(new Set())
      loadClubs()
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setBulkAssigning(false)
    }
  }

  const submitStartTrial = async (e) => {
    e.preventDefault()
    setSavingTrial(true)
    try {
      const result = await api.salesWorkspaceStartTrial(drawer.deal.id, trialForm)
      toast?.success(`Trial started for ${result.name}`)
      setShowStartTrial(false)
      refreshBoth()
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingTrial(false)
    }
  }

  // Fired when the Template picker lands on a built-in key — fetches the
  // real, already-merged content (contact's name, club name, the rep's own
  // Calendly link) so the rep edits real text in Design mode rather than raw
  // {{tokens}}. Deliberately NOT re-run on a later contact change, so
  // switching contacts can't silently wipe an edit the rep has already made.
  const loadEmailPreview = async (templateKey, contactKeyValue) => {
    setLoadingEmailPreview(true)
    try {
      const chosen = (drawer.contacts || []).find(c => contactKey(c) === contactKeyValue)
      const payload = { template: templateKey }
      if (chosen?.directory_contact_id) payload.directory_contact_id = chosen.directory_contact_id
      else if (chosen?.crm_person_id) payload.crm_person_id = chosen.crm_person_id
      const r = await api.salesWorkspaceEmailPreview(drawer.deal.id, payload)
      setEmailForm(f => ({ ...f, subject: r.subject, body: r.body }))
      setEmailEditorKey(k => k + 1)
    } catch (err) {
      toast?.error(err.message || 'Could not load that template')
    } finally {
      setLoadingEmailPreview(false)
    }
  }

  const submitEmail = async (e) => {
    e.preventDefault()
    if (!emailForm.contactKey) { toast?.error('Pick a contact to email'); return }
    if (!emailForm.template) { toast?.error('Pick a template'); return }
    const chosen = (drawer.contacts || []).find(c => contactKey(c) === emailForm.contactKey)
    if (!chosen?.email) { toast?.error('That contact has no email address on file'); return }
    setSavingEmail(true)
    try {
      const payload = { template: emailForm.template }
      if (chosen.directory_contact_id) payload.directory_contact_id = chosen.directory_contact_id
      else if (chosen.crm_person_id) payload.crm_person_id = chosen.crm_person_id
      if (emailForm.template === 'custom') {
        payload.subject = emailForm.subject
        payload.body = emailForm.body
      } else {
        // The rep's (possibly edited) Design-mode content — flush() reads
        // the iframe's current state synchronously, since onChange's state
        // update may not have landed yet.
        payload.subject = emailForm.subject
        payload.body = emailEditorRef.current?.flush() ?? emailForm.body
      }
      await api.salesWorkspaceSendEmail(drawer.deal.id, payload)
      toast?.success(`Email sent to ${chosen.full_name}`)
      setEmailForm({ contactKey: '', template: '', subject: '', body: '' })
      loadDrawer(drawer.deal.id)
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingEmail(false)
    }
  }

  const content = (
    <div className="max-w-7xl">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl text-pb-text">Sales Workspace</h1>
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
            {isSuper ? 'Every assigned club' : 'Clubs assigned to you'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setTab('queue')}
            className={`px-3 py-1.5 rounded-full text-[12px] border transition ${
              tab === 'queue' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
            Queue
          </button>
          <button type="button" onClick={() => setTab('events')}
            className={`px-3 py-1.5 rounded-full text-[12px] border transition ${
              tab === 'events' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
            Events
          </button>
        </div>
      </div>

      {tab === 'events' ? (
        <SalesEventsView dealOptions={dealOptions} staffOptions={staff} />
      ) : (
      <>
      {filters.list_id && (
        <div className="mb-3 flex items-center gap-2 text-[12px]">
          <span className="text-pb-faint">Filtered to list:</span>
          <span className="text-pb-text font-medium">{listNameParam || filters.list_id}</span>
          <button type="button" onClick={clearListFilter} className="text-pb-faintest hover:text-pb-text underline">clear</button>
        </div>
      )}

      <div className={`${CARD} mb-3`}>
        <FilterSection label="Search" first>
          <Field label="Club or contact" width="320px">
            <TextInput value={filters.q} onChange={e => setFilters(f => ({ ...f, q: e.target.value }))}
              placeholder="Club name, or a contact's name…" />
          </Field>
        </FilterSection>

        <FilterSection label="Pipeline">
          <Field label="Stage" width="180px">
            <StagePicker stages={stages} value={filters.stage_key} onChange={v => setFilters(f => ({ ...f, stage_key: v }))} />
          </Field>
          <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none pb-1.5">
            <input type="checkbox" checked={filters.stage_key.includes('trial_current')}
              onChange={() => toggleTrialFilter('trial_current')} />
            Current trials
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none pb-1.5">
            <input type="checkbox" checked={filters.stage_key.includes('trial_expired')}
              onChange={() => toggleTrialFilter('trial_expired')} />
            Expired trials
          </label>
          <Field label="Owner" width="180px">
            {isSuper ? (
              <Select value={filters.owner_user_id} onChange={e => setFilters(f => ({ ...f, owner_user_id: e.target.value }))}>
                <option value="">Everyone</option>
                <option value="__unassigned__" disabled>— pick a rep —</option>
                {team.map(u => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
              </Select>
            ) : (
              // The server already restricts a sales caller to their own deals
              // regardless of what's sent here — this is a locked display, not
              // a real filter control, so there's nothing else it could show.
              <TextInput value={user?.display_name || user?.username || ''} disabled readOnly />
            )}
          </Field>
        </FilterSection>

        <FilterSection label="Call status">
          <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none pb-1.5"
            title="By default the queue only shows clubs that have never been called — tick this to see clubs that have">
            <input type="checkbox" checked={filters.called_clubs}
              onChange={e => setFilters(f => ({ ...f, called_clubs: e.target.checked }))} />
            <span className="w-2.5 h-2.5 rounded-sm bg-orange-500 inline-block" />
            Called clubs
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none pb-1.5">
            <input type="checkbox" checked={filters.callback_due}
              onChange={e => setFilters(f => ({ ...f, callback_due: e.target.checked }))} />
            <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block" />
            Callback due
          </label>
        </FilterSection>

        <FilterSection label="Engagement & location">
          <Field label="Engagement score" width="150px">
            <div className="flex items-center gap-1.5">
              <NumberInput min={0} max={100} placeholder="min" value={filters.min_score}
                onChange={e => setFilters(f => ({ ...f, min_score: e.target.value }))} style={{ width: 64 }} />
              <span className="text-pb-faintest">–</span>
              <NumberInput min={0} max={100} placeholder="max" value={filters.max_score}
                onChange={e => setFilters(f => ({ ...f, max_score: e.target.value }))} style={{ width: 64 }} />
            </div>
          </Field>
          <Field label="State" width="160px">
            <StatePicker value={filters.states} onChange={v => setFilters(f => ({ ...f, states: v }))} />
          </Field>
        </FilterSection>

        <FilterSection label="Interested in">
          <div className="flex flex-wrap gap-1.5">
            {MODULE_ORDER.map(key => {
              const on = filters.modules.includes(key)
              return (
                <button key={key} type="button"
                  onClick={() => setFilters(f => ({
                    ...f, modules: f.modules.includes(key) ? f.modules.filter(k => k !== key) : [...f.modules, key],
                  }))}
                  className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                    on ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                       : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                  {moduleLabel(key)}
                </button>
              )
            })}
          </div>
        </FilterSection>

        <FilterSection label="Source">
          <div className="flex items-center gap-3" title="From the trial signup wizard — tick both to match either">
            <span className="text-[11px] text-pb-faintest">Meta Ad:</span>
            <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none">
              <input type="checkbox" checked={filters.meta_selected}
                onChange={e => setFilters(f => ({ ...f, meta_selected: e.target.checked }))} />
              Selected
            </label>
            <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none">
              <input type="checkbox" checked={filters.meta_searched}
                onChange={e => setFilters(f => ({ ...f, meta_searched: e.target.checked }))} />
              Searched
            </label>
          </div>
        </FilterSection>
      </div>

      {isSuper && checkedIds.size > 0 && (
        <div className={`${CARD} mb-3 flex flex-wrap items-center gap-3`}>
          <span className="text-[12px] text-pb-text font-medium">{checkedIds.size} selected</span>
          <div className="flex flex-wrap gap-1.5">
            {team.map(u => (
              <button
                key={u.id}
                type="button"
                onClick={() => toggleBulkRep(u.id)}
                className={`px-2 py-1 rounded font-mono text-[10px] border transition-colors ${
                  bulkReps.has(u.id) ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
                }`}
              >
                {u.display_name || u.username}
              </button>
            ))}
          </div>
          <span className="text-[10.5px] text-pb-faintest">
            {bulkReps.size > 1 ? 'Splits evenly, round-robin' : bulkReps.size === 1 ? 'Assigns everyone selected to them' : ''}
          </span>
          <Btn sm variant="primary" onClick={submitBulkAssign} disabled={bulkAssigning}>
            {bulkAssigning ? 'Assigning…' : 'Assign selected'}
          </Btn>
          <Btn sm variant="subtle" onClick={() => { setCheckedIds(new Set()); setBulkReps(new Set()) }}>Clear</Btn>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-4 items-start">
        {/* Queue */}
        <div className={CARD}>
          <div className="flex items-center gap-1.5 pb-2 mb-1.5">
            <span className="text-[10.5px] text-pb-faintest">Sort</span>
            <Select value={filters.sort} onChange={e => setFilters(f => ({ ...f, sort: e.target.value, sort_dir: '' }))}
              className="!w-auto !py-1 !text-[12px]">
              {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.name}</option>)}
            </Select>
            {filters.sort && (
              <button type="button"
                onClick={() => setFilters(f => ({
                  ...f, sort_dir: f.sort_dir === 'asc' ? 'desc' : f.sort_dir === 'desc' ? 'asc'
                    : (_SORT_DEFAULT_DIR_FE[f.sort] === 'asc' ? 'desc' : 'asc'),
                }))}
                title={`Sorted ${((filters.sort_dir || _SORT_DEFAULT_DIR_FE[filters.sort]) === 'asc') ? 'ascending' : 'descending'} — click to reverse`}
                className="px-1.5 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text text-[11px] leading-none">
                {(filters.sort_dir || _SORT_DEFAULT_DIR_FE[filters.sort]) === 'asc' ? '▲' : '▼'}
              </button>
            )}
          </div>
          {!loadingList && (
            <div className="flex items-center justify-between px-1 pb-2 mb-1.5 border-b border-pb-hairline text-[11px] text-pb-faint">
              <span>
                <span className="text-pb-text font-medium">{clubs.length}</span> club{clubs.length === 1 ? '' : 's'}
              </span>
              <span>
                <span className="text-pb-text font-medium">{totalContacts}</span> contact{totalContacts === 1 ? '' : 's'}
              </span>
            </div>
          )}
          {loadingList ? (
            <p className="text-[12px] text-pb-faintest px-1 py-2">Loading…</p>
          ) : clubs.length === 0 ? (
            <p className="text-[12px] text-pb-faintest px-1 py-2">No clubs match these filters.</p>
          ) : (
            <div className="space-y-1.5 max-h-[75vh] overflow-y-auto">
              {isSuper && (
                <label className="flex items-center gap-1.5 px-2.5 py-1 text-[10.5px] text-pb-faint cursor-pointer select-none">
                  <input type="checkbox" checked={allChecked} onChange={toggleSelectAllVisible} />
                  Select all filtered
                </label>
              )}
              {clubs.map(c => (
                <div key={c.id} className="flex items-start gap-1.5">
                  {isSuper && (
                    <input
                      type="checkbox"
                      checked={checkedIds.has(c.id)}
                      onChange={() => toggleChecked(c.id)}
                      onClick={e => e.stopPropagation()}
                      className="mt-3"
                    />
                  )}
                  <button
                    onClick={() => selectClub(c.id)}
                    className={`flex-1 min-w-0 text-left rounded-lg px-2.5 py-2 border transition-colors ${
                      selectedId === c.id ? 'border-pb-accent bg-pb-surface2'
                      : c.callback_due ? 'border-blue-500/60 hover:bg-pb-surface2'
                      : c.ever_called ? 'border-orange-500/60 hover:bg-pb-surface2'
                      : 'border-transparent hover:bg-pb-surface2'
                    }`}
                  >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-pb-text text-[13px] font-medium truncate">{c.marketing_club_name || c.title}</span>
                    <PriorityBadge score={c.priority_score} />
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1">
                    <span className="text-[10.5px] text-pb-faint">{c.stage_name}{isSuper && c.owner_name ? ` · ${c.owner_name}` : ''}</span>
                    <ScorePill score={c.engagement_score} tier={c.engagement_tier} />
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1 text-[10.5px] text-pb-faintest">
                    <span>{c.contact_count} contact{c.contact_count === 1 ? '' : 's'}</span>
                    <span>
                      {!c.ever_called ? 'Never called' : `Last call ${timeAgo(c.last_call?.occurred_at)}`}
                      {c.next_follow_up_at && <span className="text-pb-amber"> · follow-up {timeAgo(c.next_follow_up_at) || 'due'}</span>}
                    </span>
                  </div>
                  {(c.module_keys || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {c.module_keys.map(k => (
                        <span key={k} className="px-1.5 py-0.5 rounded-full text-[9.5px] bg-pb-accent/10 text-pb-accent">
                          {moduleLabel(k)}
                        </span>
                      ))}
                    </div>
                  )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Drawer */}
        <div className="space-y-3">
          {!selectedId ? (
            <div className={CARD}><p className="text-[12px] text-pb-faintest">Pick a club from the queue to get started.</p></div>
          ) : loadingDrawer || !drawer ? (
            <div className={CARD}><p className="text-[12px] text-pb-faintest">Loading…</p></div>
          ) : (
            <>
              <div className={CARD}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <h2 className="font-display font-bold text-lg">{drawer.deal.marketing_club_name || drawer.deal.title}</h2>
                  <div className="flex items-center gap-2">
                    {drawer.can_assign && (
                      <Select value={drawer.deal.owner_user_id || ''} onChange={e => submitAssign(e.target.value || null)} className="!w-auto">
                        <option value="">Unassigned</option>
                        {team.map(u => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
                      </Select>
                    )}
                    {!drawer.deal.is_customer && drawer.deal.marketing_club_id && (
                      <Btn variant="primary" sm onClick={() => setShowStartTrial(true)}>Start trial</Btn>
                    )}
                  </div>
                </div>
                <div className="mt-3">
                  <DealSummaryStrip deal={drawer.deal} />
                </div>
                {drawer.deal.not_interested && (
                  <p className="mt-3 text-[11.5px] text-pb-red">
                    Marked not interested — flagged from Sales, or from the Club Directory. Clear it from the Club Directory if this club should be worked again.
                  </p>
                )}
                <ClubSummaryCard deal={drawer.deal} />
              </div>

              <WizardSignalCard signal={drawer.deal.wizard_signal} />

              <div className={CARD}>
                <h3 className="font-display font-bold text-[13px] mb-2">Engagement</h3>
                <EngagementPanel engagement={drawer.engagement} />
              </div>

              {drawer.deal.marketing_club_id && (
                <div className={CARD}>
                  <h3 className="font-display font-bold text-[13px] mb-2">Website analytics</h3>
                  <WebsiteAnalyticsCard data={drawer.website_visits} />
                </div>
              )}

              <div className={CARD}>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-display font-bold text-[13px]">Contacts</h3>
                  <Btn sm variant="subtle" onClick={() => setShowAddContact(s => !s)}>{showAddContact ? 'Cancel' : '+ Add contact'}</Btn>
                </div>
                {showAddContact && (
                  <form onSubmit={submitContact} className="grid grid-cols-2 gap-2 mb-3 pb-3 border-b border-pb-hairline">
                    <Field label="Name"><TextInput value={contactForm.full_name} onChange={e => setContactForm(f => ({ ...f, full_name: e.target.value }))} /></Field>
                    <Field label="Role"><TextInput value={contactForm.role} onChange={e => setContactForm(f => ({ ...f, role: e.target.value }))} placeholder="e.g. Secretary" /></Field>
                    <Field label="Email"><TextInput type="email" value={contactForm.email} onChange={e => setContactForm(f => ({ ...f, email: e.target.value }))} /></Field>
                    <Field label="Mobile"><TextInput value={contactForm.mobile} onChange={e => setContactForm(f => ({ ...f, mobile: e.target.value }))} /></Field>
                    <div className="col-span-2"><Btn type="submit" variant="primary" sm disabled={savingContact}>{savingContact ? 'Saving…' : 'Save contact'}</Btn></div>
                  </form>
                )}
                {(drawer.contacts || []).length === 0 ? (
                  <p className="text-[12px] text-pb-faintest">No contacts on file for this club yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {drawer.contacts.map(c => (
                      <div key={contactKey(c) || c.full_name} className="flex items-center justify-between gap-2 text-[12px] border-b border-pb-hairline/50 pb-1.5">
                        <div className="min-w-0">
                          <span className="text-pb-text">{c.full_name}</span>
                          {c.role && <span className="text-pb-faint ml-1.5">{c.role}</span>}
                          {c.do_not_email && <Pill tone="red">opted out</Pill>}
                          {c.do_not_contact && <Pill tone="red">do not contact{c.do_not_contact_reason ? ` — ${c.do_not_contact_reason}` : ''}</Pill>}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <div className="text-right">
                            {c.email && <div className="text-pb-faintest text-[10.5px] truncate max-w-[220px]">{c.email}</div>}
                            {c.mobile && <div className="text-pb-text text-[12px]">{c.mobile}</div>}
                          </div>
                          {c.directory_contact_id && (
                            <button
                              onClick={() => toggleDoNotContact(c)}
                              className="font-mono text-[9.5px] text-pb-faint hover:text-pb-red transition-colors whitespace-nowrap"
                            >
                              {c.do_not_contact ? 'Clear' : 'Do not contact'}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className={CARD}>
                <h3 className="font-display font-bold text-[13px] mb-2">Log a call</h3>
                <form onSubmit={submitCall} className="space-y-2">
                  <Field label="Contact">
                    <Select value={showNewCallContact ? NEW_CONTACT_VALUE : callForm.contactKey}
                      onChange={e => {
                        if (e.target.value === NEW_CONTACT_VALUE) { setShowNewCallContact(true); return }
                        setCallForm(f => ({ ...f, contactKey: e.target.value }))
                      }}>
                      <option value="">— no specific contact —</option>
                      {(drawer.contacts || []).map(c => (
                        <option key={contactKey(c)} value={contactKey(c)}>
                          {c.full_name}{c.role ? ` (${c.role})` : ''}{c.do_not_contact ? ' — DO NOT CONTACT' : ''}
                        </option>
                      ))}
                      <option value={NEW_CONTACT_VALUE}>+ New contact…</option>
                    </Select>
                    {showNewCallContact && (
                      <div className="mt-1.5">
                        <InlineNewContact dealId={drawer.deal.id} toast={toast}
                          onCancel={() => setShowNewCallContact(false)}
                          onCreated={(contact) => {
                            const key = mergeNewContact(contact)
                            setCallForm(f => ({ ...f, contactKey: key }))
                            setShowNewCallContact(false)
                          }} />
                      </div>
                    )}
                  </Field>
                  <Field label="Outcome">
                    <Select value={callForm.outcome} onChange={e => setCallForm(f => ({ ...f, outcome: e.target.value }))} required>
                      <option value="">Pick an outcome…</option>
                      {groupedOutcomes().map(g => (
                        <optgroup key={g.category} label={g.label}>
                          {g.options.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                        </optgroup>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Interested in">
                    <div className="flex flex-wrap gap-1.5">
                      {MODULE_ORDER.map(key => {
                        const on = (drawer.deal.module_keys || []).includes(key)
                        return (
                          <button key={key} type="button" onClick={() => toggleInterest(key)}
                            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                              on ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                                 : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                            {moduleLabel(key)}
                          </button>
                        )
                      })}
                    </div>
                  </Field>
                  <Field label="Notes"><TextArea value={callForm.notes} onChange={e => setCallForm(f => ({ ...f, notes: e.target.value }))} /></Field>
                  <Field label="Follow up (optional)">
                    <TextInput type="datetime-local" value={callForm.followUpAt} onChange={e => setCallForm(f => ({ ...f, followUpAt: e.target.value }))} />
                  </Field>
                  {ASSIGNABLE_EVENT_OUTCOMES.includes(callForm.outcome) && callForm.followUpAt && (
                    <Field label="Hand this follow-up to" hint="Leave as 'Me' to keep it on your own calendar">
                      <Select value={callForm.eventOwnerUserId} onChange={e => setCallForm(f => ({ ...f, eventOwnerUserId: e.target.value }))}>
                        <option value="">Me</option>
                        {staff.map(u => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
                      </Select>
                    </Field>
                  )}
                  <Btn type="submit" variant="primary" disabled={savingCall}>{savingCall ? 'Saving…' : 'Save call'}</Btn>
                </form>
              </div>

              <div className={CARD}>
                <h3 className="font-display font-bold text-[13px] mb-2">Notes</h3>
                <form onSubmit={submitNote} className="flex items-start gap-2 mb-3">
                  <TextInput value={noteForm.body} onChange={e => setNoteForm(f => ({ ...f, body: e.target.value }))}
                    placeholder="e.g. Secretary is best contact, prefers mobile after 5pm" className="flex-1" />
                  <label className="flex items-center gap-1 text-[11px] text-pb-faint whitespace-nowrap pt-2">
                    <input type="checkbox" checked={noteForm.pinned} onChange={e => setNoteForm(f => ({ ...f, pinned: e.target.checked }))} /> Pin
                  </label>
                  <Btn type="submit" sm disabled={savingNote}>Add</Btn>
                </form>
                {pinnedNotes.length > 0 && (
                  <div className="mb-3 space-y-1.5">
                    {pinnedNotes.map(a => (
                      <div key={a.id} className="text-[12px] bg-pb-amber/10 border border-pb-amber/30 rounded px-2 py-1.5">{a.body}</div>
                    ))}
                  </div>
                )}
                <h4 className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1.5">History</h4>
                {timeline.length === 0 ? (
                  <p className="text-[12px] text-pb-faintest">No activity yet.</p>
                ) : timeline.map(a => <ActivityRow key={a.id} a={a} />)}
              </div>

              <div className={CARD}>
                <h3 className="font-display font-bold text-[13px] mb-2">Send an email</h3>
                <form onSubmit={submitEmail} className="space-y-2">
                  <Field label="Contact">
                    <Select value={showNewEmailContact ? NEW_CONTACT_VALUE : emailForm.contactKey}
                      onChange={e => {
                        if (e.target.value === NEW_CONTACT_VALUE) { setShowNewEmailContact(true); return }
                        setEmailForm(f => ({ ...f, contactKey: e.target.value }))
                      }}>
                      <option value="">Pick a contact…</option>
                      {(drawer.contacts || []).filter(c => c.email).map(c => (
                        <option key={contactKey(c)} value={contactKey(c)}>
                          {c.full_name}{c.role ? ` (${c.role})` : ''}{c.do_not_contact ? ' — DO NOT CONTACT' : ''}
                        </option>
                      ))}
                      <option value={NEW_CONTACT_VALUE}>+ New contact…</option>
                    </Select>
                    {showNewEmailContact && (
                      <div className="mt-1.5">
                        <InlineNewContact dealId={drawer.deal.id} toast={toast}
                          onCancel={() => setShowNewEmailContact(false)}
                          onCreated={(contact) => {
                            if (!contact.email) { toast?.error('That contact has no email address — add one to email them'); return }
                            const key = mergeNewContact(contact)
                            setEmailForm(f => ({ ...f, contactKey: key }))
                            setShowNewEmailContact(false)
                          }} />
                      </div>
                    )}
                  </Field>
                  <Field label="Template">
                    <Select value={emailForm.template} onChange={e => {
                      const key = e.target.value
                      setEmailForm(f => ({ ...f, template: key, subject: '', body: '' }))
                      if (BUILT_IN_EMAIL_TEMPLATES.includes(key)) loadEmailPreview(key, emailForm.contactKey)
                    }}>
                      <option value="">Pick a template…</option>
                      {emailTemplates.templates.map(t => (
                        <option key={t.key} value={t.key}>
                          {t.label}{t.key === 'demo' && !emailTemplates.demo_link_configured ? ' (no booking link set — will ask them to reply)' : ''}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  {emailForm.template === 'custom' && (
                    <>
                      <Field label="Subject"><TextInput value={emailForm.subject} onChange={e => setEmailForm(f => ({ ...f, subject: e.target.value }))} /></Field>
                      <Field label="Body"><TextArea value={emailForm.body} onChange={e => setEmailForm(f => ({ ...f, body: e.target.value }))} /></Field>
                    </>
                  )}
                  {BUILT_IN_EMAIL_TEMPLATES.includes(emailForm.template) && (
                    loadingEmailPreview ? (
                      <p className="text-[12px] text-pb-faintest py-2">Loading template…</p>
                    ) : (
                      <Field label="Subject">
                        <TextInput value={emailForm.subject} onChange={e => setEmailForm(f => ({ ...f, subject: e.target.value }))} />
                      </Field>
                    )
                  )}
                  {BUILT_IN_EMAIL_TEMPLATES.includes(emailForm.template) && !loadingEmailPreview && (
                    <EmailEditorTabs key={emailEditorKey} ref={emailEditorRef} html={emailForm.body}
                      onChange={v => setEmailForm(f => ({ ...f, body: v }))} height={380} simple
                      // The body here is already a finished email (contact/
                      // club names substituted server-side by /email-preview)
                      // — Preview just shows exactly what's about to be
                      // sent, no second server round trip needed.
                      onEnterPreview={async ({ html }) => ({ html, total: 1, index: 0 })} />
                  )}
                  <Btn type="submit" variant="primary" disabled={savingEmail || loadingEmailPreview}>{savingEmail ? 'Sending…' : 'Send email'}</Btn>
                </form>
              </div>
            </>
          )}
        </div>
      </div>

      {drawer && (
        <Modal open={showStartTrial} onClose={() => setShowStartTrial(false)} title={`Start a trial for ${drawer.deal.marketing_club_name}`}>
          <form onSubmit={submitStartTrial} className="space-y-2">
            <p className="text-[11.5px] text-pb-faint">
              Sets this club up exactly like Super Admin's New Club — a trial of every module starts immediately,
              and the person below is emailed an invite link to set their own password.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Field label="First name"><TextInput value={trialForm.admin_first_name} onChange={e => setTrialForm(f => ({ ...f, admin_first_name: e.target.value }))} required /></Field>
              <Field label="Last name"><TextInput value={trialForm.admin_last_name} onChange={e => setTrialForm(f => ({ ...f, admin_last_name: e.target.value }))} required /></Field>
            </div>
            <Field label="Display name" hint="Defaults to first + last if left blank"><TextInput value={trialForm.admin_display_name} onChange={e => setTrialForm(f => ({ ...f, admin_display_name: e.target.value }))} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Username"><TextInput value={trialForm.admin_username} onChange={e => setTrialForm(f => ({ ...f, admin_username: e.target.value }))} required /></Field>
              <Field label="Mobile (optional)"><TextInput value={trialForm.admin_mobile_number} onChange={e => setTrialForm(f => ({ ...f, admin_mobile_number: e.target.value }))} /></Field>
            </div>
            <Field label="Email"><TextInput type="email" value={trialForm.admin_email} onChange={e => setTrialForm(f => ({ ...f, admin_email: e.target.value }))} required /></Field>
            <Btn type="submit" variant="primary" disabled={savingTrial}>{savingTrial ? 'Starting…' : 'Start trial'}</Btn>
          </form>
        </Modal>
      )}
      </>
      )}
    </div>
  )

  // A 'sales' role user doesn't get the Better HQ chrome (most of it is
  // super-admin-only and hidden from their sidebar anyway) — a lean shell
  // with just a logout keeps this usable without touching AdminLayout's
  // shared, super_admin-gated sidebar rendering. A super admin gets the
  // normal chrome, matching every other Sales section screen.
  if (!isSuper) {
    return (
      <div className="min-h-screen bg-pb-bg">
        <header className="flex items-center justify-between px-4 py-3 border-b pb-hairline-b">
          <span className="font-display font-bold text-pb-text">BetterCricket Sales</span>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] text-pb-faint">{user?.display_name || user?.username}</span>
            <button onClick={logout} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-3 py-1.5">
              LOG OUT
            </button>
          </div>
        </header>
        <main className="p-4">{content}</main>
      </div>
    )
  }
  return <AdminLayout>{content}</AdminLayout>
}
