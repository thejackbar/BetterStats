import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import EmailEditorTabs from '../../components/admin/EmailEditorTabs'
import { Modal, Field, TextInput, NumberInput, Select, TextArea, Btn, Pill, moduleLabel, MODULE_ORDER, TOWN_STATE_COLOR } from '../../components/admin/crm/ui'
import { TrialHourglassIcon, TRIAL_AMBER } from '../../components/admin/crm/PipelineBoard'
import SalesEventsView from '../../components/admin/crm/SalesEventsView'
import ClubLocationMap from '../../components/admin/ClubLocationMap'
import { groupedOutcomes, outcomeLabel, isGeneralOutcome } from '../../lib/salesOutcomes'

const CARD = 'pb-card p-3'

// Mirrors services/sales_workspace.py's _EVENT_WORTHY_OUTCOMES — any outcome
// worth a real calendar reminder can have its follow-up Event handed to a
// named staff member instead of defaulting to whoever logged the call; the
// rep picks "who's responsible" every time they set a follow-up date, not
// just for a chosen few outcomes.
const ASSIGNABLE_EVENT_OUTCOMES = [
  'wants_to_subscribe', 'interested', 'wants_more_info', 'wants_trial', 'wants_trial_extension',
  'wants_demo', 'wants_pricing', 'wants_committee_discussion', 'asked_callback',
  'referred_to_other', 'requested_information',
]

// Call status — everything the queue's own filter can ask about a club,
// mirroring services/sales_workspace.py's CALL_STATUS_KEYS.
//
// These OVERLAP. What has happened to a club accumulates: ring them, leave a
// voicemail, set a follow-up, email a contact, and all four are still true
// afterwards — so that club shows under Called and VM and Followup and Sent
// Email, and unticking any one of them hides it. Only Not Called is exclusive
// with the rest.
//
// The queue ROW still picks a single highlight colour by precedence (see its
// className below), because a row can only be one colour. The swatches here
// are that colour where there is one, so a filter and the rows it lets
// through still read as related — but they are no longer the same thing, and
// Sent Email has no row colour of its own at all.
const CALL_STATUS = [
  // The keys stay `not_called`/`called` — they are what the server, a shared
  // link and a saved preference are all written in, and only the wording on
  // screen changed. Both read as a CALL, which is what the tooltips say: a
  // club nobody has rung but somebody has emailed is Not Contacted with Sent
  // Email ticked.
  { key: 'not_called', label: 'Not Contacted', swatch: 'bg-pb-hairline2',
    title: 'Clubs with no call logged against them yet' },
  { key: 'called', label: 'Contacted', swatch: 'bg-orange-500',
    title: 'Every club that has ever been called — voicemails and follow-ups included' },
  { key: 'followup', label: 'Followup', swatch: 'bg-blue-500',
    title: 'Clubs with a follow-up now due or overdue' },
  { key: 'voicemail', label: 'VM', swatch: 'bg-purple-500',
    title: 'Clubs whose most recent call went to voicemail — i.e. nobody has picked up since' },
  { key: 'sent_email', label: 'Sent Email', swatch: 'bg-teal-400',
    title: 'Clubs a rep has sent an email to from this screen' },
]

// First load for a user who has never touched these boxes shows everything —
// nothing is hidden until they say so.
const ALL_CALL_STATUS = Object.fromEntries(CALL_STATUS.map(s => [s.key, true]))

// The namespace this user's last selection is saved under, on their own
// account (GET/PATCH /club-admin/account/ui-prefs) rather than in
// localStorage — a rep moving between machines keeps their queue.
const CALL_STATUS_PREF = 'sales_call_status_filters'

// `followup` was saved as `callback` before the box was relabelled. Read the
// old name through, so a rep who had it unticked doesn't have it silently
// tick itself back on the first time they open the screen after the rename.
const CALL_STATUS_ALIASES = { callback: 'followup' }

// Keeps only the known keys, as real booleans, so a stored bag written by an
// older (or newer) build can never feed the filter something it can't read. A
// key the saved bag simply doesn't have — a box that did not exist when it
// was written — defaults to TICKED, since a filter nobody has had the chance
// to turn off should not start out hiding clubs.
function cleanCallStatus(saved) {
  if (!saved || typeof saved !== 'object') return null
  const out = {}
  for (const { key } of CALL_STATUS) {
    const alias = Object.keys(CALL_STATUS_ALIASES).find(a => CALL_STATUS_ALIASES[a] === key)
    const stored = key in saved ? saved[key] : (alias && alias in saved ? saved[alias] : undefined)
    out[key] = stored === undefined ? true : stored === true
  }
  return out
}

// The wire form: one comma-list, because the api helper drops false values
// and the server must be able to tell "unticked" from "not sent" (an absent
// param still means the legacy never-called default). 'none' is a value no
// bucket answers to, so every box unticked genuinely returns nothing.
function callStatusParam(bag) {
  const on = CALL_STATUS.filter(s => bag?.[s.key]).map(s => s.key)
  return on.length ? on.join(',') : 'none'
}

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

// One labelled group of filter controls — sits side by side with its
// siblings in a flex-wrap row (a vertical hairline separates one group from
// the next), only dropping to its own line once the row genuinely runs out
// of width. That's what keeps the whole bar to one or two lines instead of
// one full-width row per group stacked all the way down the page.
// `stack` puts the group's controls in a column instead of a wrapping row —
// for Call status, where five checkboxes side by side read as a sentence and
// have to be scanned left to right to see what is actually filtered. Stacked,
// the ticks line up and the state of the queue is one glance down a column.
//
// The groups no longer carry a divider each. With eight of them wrapping onto
// two or three lines, every wrapped line opened on a vertical rule with
// nothing to its left, which read as a mistake; spacing separates them just
// as well. The one rule left is the split between the filters and the Call
// status column, which is a real boundary.
function FilterGroup({ label, children, className = '', stack = false }) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase">{label}</p>
      <div className={stack ? 'flex flex-col gap-0.5' : 'flex flex-wrap items-end gap-2'}>{children}</div>
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
// Start trial now requires picking a real club contact with a valid email as
// the primary admin (see the contact-picker in the Start trial modal below),
// rather than a rep hand-typing a name and address. Hidden entirely while
// that's under consideration — flip back to true to restore the button; the
// rest of the flow is left fully wired so this is a one-line toggle.
const START_TRIAL_ENABLED = false
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const splitFullName = (fullName) => {
  const parts = (fullName || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return { first: '', last: '' }
  if (parts.length === 1) return { first: parts[0], last: parts[0] }
  return { first: parts[0], last: parts.slice(1).join(' ') }
}
// min_trial_days_remaining is SIGNED (see crm.trial_days_remaining_by_club) —
// negative means the trial's own end date has already passed, which is what
// tells "13 days left" apart from "expired 3 days ago" instead of both
// reading as a plain countdown. Shared by the queue card and the drawer's
// own ClubSummaryCard so the two never phrase this differently.
const trialDaysLabel = (days) => {
  const n = Math.abs(days)
  const unit = `day${n === 1 ? '' : 's'}`
  return days >= 0 ? `${n} ${unit} left` : `EXPIRED (${n} ${unit} ago)`
}
// "Geelong, VIC" — state is already stored abbreviated (see the STATES
// filter list above, same field). Either half can be missing on its own
// (a club with no crawled address, or one outside AU with no state code),
// so this degrades to whichever one is present rather than showing a bare
// comma or nothing at all. Shared by the queue card and the drawer header.
const townStateLabel = (suburb, state) => [suburb, state].filter(Boolean).join(', ') || null

// Every association a club plays in — Club Directory's own PlayHQ crawl,
// marketing_clubs.associations (`[{id, name, competition}, …]`). NULL = not
// yet crawled, [] = crawled, none found — both render nothing, same as a
// missing town/state above. Shared by the queue card and the drawer header.
const associationNames = (associations) => (associations || []).map(a => a?.name).filter(Boolean)

// Small wrapped chip row for the associations a club competes in — reused by
// the queue card and the drawer header so the two never disagree on style.
function AssociationChips({ associations, className = '' }) {
  const names = associationNames(associations)
  if (!names.length) return null
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {names.map(n => (
        // 5px is half the radius a pill actually renders at here: the chip is
        // 20.25px tall, so rounded-full caps at 10.125px however large the
        // value. The border was `border-pb-line`, which is not a token this
        // Tailwind config defines (see tailwind.config.js) — with no valid
        // colour class the border fell back to preflight's own #e5e7eb and
        // read far brighter than the name inside it. It matches the text now.
        <span key={n} className="px-1.5 py-0.5 rounded-[5px] text-[9.5px] bg-pb-surface2 text-pb-faint border border-pb-faint">
          {n}
        </span>
      ))}
    </div>
  )
}

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
    stats && stats.active_since && `active since ${new Date(stats.active_since).toLocaleDateString('en-AU')}`,
  ].filter(Boolean).join(' · ')
}

// How much of the Setup Wizard an onboarded club has actually worked through.
// `setup_total` is the number of steps that apply to THIS club (the wizard
// filters its groups by what the club is entitled to, so a Core-only club has
// far fewer than one holding every module) — which is why it is shown as
// "N of M" rather than against a fixed number that would be wrong for most
// clubs. It used to be one item in the dense facts line above; a half-finished
// setup is the most callable thing on the whole card, so it gets its own row.
function SetupProgress({ stats }) {
  const total = stats?.setup_total || 0
  if (!total) return null
  const done = stats.setup_done || 0
  const pct = Math.round((done / total) * 100)
  const complete = done >= total
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest">Setup wizard</span>
        <span className={`text-[12px] font-medium ${complete ? 'text-pb-positive' : done ? 'text-pb-text' : 'text-pb-amber'}`}>
          {done} of {total} step{total === 1 ? '' : 's'}
          {complete ? ' — done' : done === 0 ? ' — not started' : ''}
        </span>
      </div>
      <div className="h-1.5 rounded-sm mt-1 overflow-hidden" style={{ background: 'var(--pb-hairline2)' }}>
        <div className="h-full rounded-sm" style={{
          width: `${pct}%`,
          background: complete ? 'var(--pb-positive)' : 'var(--pb-accent)',
        }} />
      </div>
    </div>
  )
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
      <SetupProgress stats={stats} />
      {days != null && (
        <p className={`text-[12.5px] ${days >= 0 ? 'text-pb-text' : 'text-pb-red'}`}>
          Trial: <span className="font-medium">{trialDaysLabel(days)}</span>
        </p>
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
  both: 'Searched for and picked this club on /trial',
  selected: 'Picked this club on /trial',
  searched: 'Searched for this club on /trial',
}

const shortDate = (iso) => (iso ? new Date(iso).toLocaleDateString('en-AU') : null)

// A small "step 4 of 8" rail. Filled to where they actually got, so how far
// short they stopped is the thing you see rather than a number to read. An
// unfinished run fills AMBER, matching its own headline — green would read as
// "all good" about the exact case worth ringing them over.
function StepRail({ position, total, done }) {
  return (
    <div className="flex items-center gap-0.5 mt-1.5" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className="h-1.5 flex-1 rounded-sm"
          style={{ background: i < position
            ? (done ? 'var(--pb-positive)' : 'var(--pb-amber)')
            : 'var(--pb-hairline2)' }} />
      ))}
    </div>
  )
}

// Where this club came from: the /trial page pick, how far the registration
// actually got, and the ad behind it. Fetched separately from the rest of the
// drawer (see api.salesWorkspaceClubSignals) because every part reads a beacon
// table — so this card fills in a moment after the pane rather than holding it
// up. Renders nothing at all for a club none of it applies to.
function OriginCard({ signals, loading }) {
  const wizard = signals?.wizard
  const reg = signals?.registration
  if (loading && !signals) {
    return <div className={CARD}><p className="text-[12px] text-pb-faintest">Looking up where this club came from…</p></div>
  }
  if (!wizard && !reg) return null
  const queries = (wizard?.queries || []).filter(Boolean)
  const viaMeta = wizard?.via_meta
  return (
    <div className={CARD}>
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <h3 className="font-display font-bold text-[13px]">
          {WIZARD_SOURCE_LABEL[wizard?.source] || 'Trial signup activity'}
        </h3>
        {viaMeta && <Pill tone="accent">META AD</Pill>}
      </div>

      {queries.length > 0 && (
        <p className="text-[12px] text-pb-faint">
          Searched: {queries.map((q, i) => (
            <span key={q}>{i > 0 && ' · '}<span className="text-pb-text">&ldquo;{q}&rdquo;</span></span>
          ))}
        </p>
      )}

      {reg ? (
        <div className="mt-2">
          <p className="text-[12.5px]">
            {reg.completed ? (
              <span className="text-pb-positive font-medium">Registration completed</span>
            ) : (
              <>
                <span className="text-pb-amber font-medium">Gave up at {reg.furthest.label.toLowerCase()}</span>
                <span className="text-pb-faint"> — step {reg.furthest.position} of {reg.total_steps}</span>
              </>
            )}
          </p>
          <StepRail position={reg.furthest.position} total={reg.total_steps} done={reg.completed} />
          {reg.last_at && (
            <p className="text-[11px] text-pb-faintest mt-1">
              {reg.completed ? 'Finished' : 'Last step'} {shortDate(reg.last_at)}
              {reg.visitors > 1 ? ` · ${reg.visitors} people tried` : ''}
            </p>
          )}
        </div>
      ) : (
        // A club picked on /trial with no beacon trail behind it never started
        // the form — worth saying, since "no registration" and "we can't tell"
        // read the same on an empty card.
        <p className="text-[12px] text-pb-faint mt-1">Never started the registration form.</p>
      )}

      {!reg && wizard?.last_at && (
        <p className="text-[11px] text-pb-faintest mt-1">Last seen {shortDate(wizard.last_at)}</p>
      )}
    </div>
  )
}

// The ad traffic behind whatever the engagement score credited to Meta. The
// breakdown below already says how many POINTS those clicks were worth; this
// says which ad, how many landings and when, which is what a rep opens with.
function MetaAdsCard({ meta }) {
  if (!meta) return null
  return (
    <div className={CARD}>
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <h3 className="font-display font-bold text-[13px]">Came through a Meta ad</h3>
        <Pill tone="accent">{meta.clicks} landing{meta.clicks === 1 ? '' : 's'}</Pill>
      </div>
      {meta.ads.length > 0 && (
        <div className="space-y-0.5">
          {meta.ads.map(a => (
            <div key={a.tag} className="flex items-baseline justify-between gap-2 text-[12px]">
              <span className="text-pb-text truncate">{a.name}</span>
              <span className="text-pb-faint whitespace-nowrap">{a.clicks}</span>
            </div>
          ))}
        </div>
      )}
      {meta.campaigns.length > 0 && (
        <p className="text-[11.5px] text-pb-faint mt-1">
          {meta.campaigns.map(c => c.name).join(' · ')}
        </p>
      )}
      {/* The raw landing paths (deliberately not shown — each click carries
          its own fbclid query string, so the same page reads as several
          different "URLs"; the landing count + date range above already say
          everything a rep needs). */}
      <p className="text-[11px] text-pb-faintest mt-1">
        {meta.first_at === meta.last_at
          ? shortDate(meta.last_at)
          : `${shortDate(meta.first_at)} to ${shortDate(meta.last_at)}`}
      </p>
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
        {/* Only while a trial is live or has expired — a subscriber or bare
            prospect shows no primary admin line here. */}
        {deal.min_trial_days_remaining != null && deal.primary_admin_name && (
          <div className="text-[11px] text-pb-faint mt-0.5">{deal.primary_admin_name}</div>
        )}
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

// A row carries its own email content whenever it actually sent one —
// email-type sends always do (meta.html); Extend Trial's own log stays
// type='system' (the headline fact is the extension, not the email) but
// still attaches meta.html when the confirmation email rendered, so the
// SAME "View email" affordance below works off meta.html alone, whatever
// `type` the row is.
// Shared by the pinned-notes block and ActivityRow below — a note is a
// rep's own free-text record and the only activity kind this drawer ever
// lets anyone rewrite (a call/email/system entry is a log of something
// that actually happened, not an editable draft).
function NoteEditForm({ value, onChange, onSave, onCancel, saving }) {
  return (
    <div className="space-y-1.5">
      <TextArea value={value.body} onChange={e => onChange(f => ({ ...f, body: e.target.value }))} autoFocus />
      <div className="flex items-center justify-between gap-2">
        <label className="flex items-center gap-1 text-[11px] text-pb-faint">
          <input type="checkbox" checked={value.pinned} onChange={e => onChange(f => ({ ...f, pinned: e.target.checked }))} /> Pin
        </label>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onCancel} className="text-[11px] text-pb-faint hover:underline">Cancel</button>
          <Btn type="button" sm disabled={saving} onClick={onSave}>{saving ? 'Saving…' : 'Save'}</Btn>
        </div>
      </div>
    </div>
  )
}

function ActivityRow({ a, onViewEmail, editing, editValue, onChangeEdit, onStartEdit, onSaveEdit, onCancelEdit, savingEdit }) {
  // The outcome names the row whenever there is one, whatever type it was
  // filed under: a General Note is stored as a NOTE (it claims nothing about
  // the club, so it must not read as a call anywhere) and would otherwise
  // lose the label the person actually picked.
  const kindLabel = a.outcome ? outcomeLabel(a.outcome)
    : a.type === 'call' ? 'Call'
      : a.type === 'email' ? 'Email' : a.type === 'system' ? 'System' : a.meta?.pinned ? 'Pinned note' : 'Note'
  const tone = a.type === 'call' ? 'accent' : a.type === 'email' ? 'accent' : a.type === 'system' ? 'faint' : a.meta?.pinned ? 'amber' : 'faint'
  // Who logged this — a call, note, email, assign or extend-trial all stamp
  // created_by_user_id, and the drawer resolves it to a name in one batched
  // lookup (routers/sales_workspace.py::get_club). Absent only for an entry
  // written before this shipped, or a system action with no attributable
  // actor.
  const byLine = a.occurred_at
    ? `${new Date(a.occurred_at).toLocaleString('en-AU')}${a.created_by_name ? ` · ${a.created_by_name}` : ''}`
    : (a.created_by_name || '')
  if (a.type === 'note' && editing) {
    return (
      <div className="border-b border-pb-hairline/50 pb-2 mb-2 text-[12px]">
        <div className="flex items-center justify-between gap-2 mb-1">
          <Pill tone={tone}>{kindLabel}</Pill>
          <span className="text-pb-faintest text-[10.5px]">{byLine}</span>
        </div>
        <NoteEditForm value={editValue} onChange={onChangeEdit} onSave={onSaveEdit} onCancel={onCancelEdit} saving={savingEdit} />
      </div>
    )
  }
  return (
    <div className="border-b border-pb-hairline/50 pb-2 mb-2 text-[12px]">
      <div className="flex items-center justify-between gap-2">
        <Pill tone={tone}>{kindLabel}</Pill>
        <span className="text-pb-faintest text-[10.5px]">{byLine}</span>
      </div>
      {a.body && <p className="mt-1 text-pb-text whitespace-pre-wrap">{a.body}</p>}
      {a.type === 'note' && (
        <div className="mt-1 flex items-center gap-2">
          <button type="button" onClick={() => onStartEdit?.(a)} className="text-[10.5px] text-pb-accent hover:underline">Edit</button>
          {a.meta?.edited_at && <span className="text-[10.5px] text-pb-faintest">(edited)</span>}
        </div>
      )}
      {a.meta?.html && (
        <button type="button" onClick={() => onViewEmail?.(a)}
          className="mt-1 text-[11px] text-pb-accent hover:underline">
          View email →
        </button>
      )}
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
  // react-router hands back a NEW setSearchParams identity on every URL
  // change (it's memoized on the current searchParams object, which is
  // itself rebuilt whenever location.search changes) — so a plain click on
  // a club, which sets ?club=<id>, was recreating setSearchParams on every
  // single select. loadClubs listed it as a dependency, which recreated
  // loadClubs, which reran the effect below and reloaded the whole queue —
  // the list flashing to "Loading…" and back on EVERY click, not just after
  // a Save Call/Send Email. Routed through a ref so loadClubs never depends
  // on this identity churn; the ref is always kept current.
  const setSearchParamsRef = useRef(setSearchParams)
  useEffect(() => { setSearchParamsRef.current = setSearchParams }, [setSearchParams])

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
    // ASSIGNED (who holds the club) and ATTRIBUTED (which rep earned it)
    // are separate questions and separate filters — both take several
    // people at once, ORed, and both are super-admin only.
    q: '', stage_key: [], owner_user_ids: [], attributed_user_ids: [],
    // Call status is one bag of four booleans, not four loose filter keys —
    // it saves and restores as a unit (see CALL_STATUS_PREF below).
    call_status: ALL_CALL_STATUS, list_id: '',
    min_score: '', max_score: '', meta_selected: false, meta_searched: false, modules: [],
    states: [], sort: '', sort_dir: '',
  })
  const [clubs, setClubs] = useState([])
  const [stages, setStages] = useState([])
  const [team, setTeam] = useState([])
  // Every sales rep, plus a "nobody" row. Both pickers offer the same
  // people; only that first row's wording differs, since under Assigned it
  // means nobody holds the club and under Attributed it means no rep has
  // earned it. The VALUE is the same either way — 'unassigned' is the
  // server's own sentinel (routers/sales_workspace.UNASSIGNED_PICK), and a
  // UUID can never spell it, so it rides in the same comma-list as the real
  // ids.
  const repOptions = useMemo(
    () => team.map(u => ({ key: u.id, name: u.display_name || u.username })), [team])
  const assignedOptions = useMemo(
    () => [{ key: 'unassigned', name: 'Unassigned' }, ...repOptions], [repOptions])
  const attributedOptions = useMemo(
    () => [{ key: 'unassigned', name: 'Unattributed' }, ...repOptions], [repOptions])
  const [staff, setStaff] = useState([])
  const [eventOwners, setEventOwners] = useState([])
  const [loadingList, setLoadingList] = useState(true)
  // Call status is restored from the user's account before the queue is
  // fetched at all; lastSavedCallStatusRef holds what the server already has,
  // so hydration and a no-op re-tick don't write.
  const [callStatusLoaded, setCallStatusLoaded] = useState(false)
  const lastSavedCallStatusRef = useRef(JSON.stringify(ALL_CALL_STATUS))
  const [selectedId, setSelectedId] = useState(null)
  const [drawer, setDrawer] = useState(null)
  const [loadingDrawer, setLoadingDrawer] = useState(false)
  // The origin cards' own payload. signalsForRef guards against a slow lookup
  // for one club landing after the rep has already clicked on to the next.
  const [signals, setSignals] = useState(null)
  const [signalsLoading, setSignalsLoading] = useState(false)
  const signalsForRef = useRef(null)
  // Kept in sync with selectedId below, but read from inside loadClubs'/
  // refreshBoth's async callbacks — a plain closure over `selectedId` there
  // would see whatever it was when the callback was CREATED, not the latest
  // value, which is exactly the kind of stale-read that let the drawer keep
  // showing a club that had just dropped out of the filtered queue.
  const selectedIdRef = useRef(null)
  // A plain click never needs the list to move — the card someone just
  // clicked is by definition already on screen, so selecting it must leave
  // the queue's scroll position exactly as it was. rowRefs backs the two
  // cases that DO need a deliberate scroll (a ?club= deep link landing on a
  // row that's off-screen, and auto-advancing to the next club below) —
  // both call selectClub(id, { scroll: true }) explicitly rather than any
  // selection whatsoever triggering a scroll.
  const rowRefs = useRef({})
  useEffect(() => { selectedIdRef.current = selectedId }, [selectedId])
  // Mirrors selectedIdRef's own reasoning: loadClubs' async .then() needs the
  // queue as it stood just before THIS reload (to find what came after the
  // club that just dropped out), and a plain closure over `clubs` would see
  // whatever it was when loadClubs was last memoized, not the latest list.
  const clubsRef = useRef([])
  useEffect(() => { clubsRef.current = clubs }, [clubs])
  // Set true the first time loadClubs' reload handler runs to completion —
  // whether it landed on a ?club= deep link, kept an existing selection, or
  // fell through to the "land on the top of the queue" default below. Once
  // true, that default never fires again for the rest of the session, so
  // tweaking a filter mid-call can't rip the rep away from whoever they're
  // looking at.
  const initialPositionDoneRef = useRef(false)

  // Bulk assignment (super admin only) — checked deal ids from the CURRENT
  // filtered queue, and which reps are ticked in the bulk-assign panel: one
  // rep checked = assign everything to them, several = split evenly.
  const [checkedIds, setCheckedIds] = useState(() => new Set())
  const [bulkReps, setBulkReps] = useState(() => new Set())
  // Unassign is mutually exclusive with picking reps — it sends the
  // selection back into the shared pool instead of onto anyone's queue.
  const [bulkUnassign, setBulkUnassign] = useState(false)
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
  const [editingNoteId, setEditingNoteId] = useState(null)
  const [editNoteForm, setEditNoteForm] = useState({ body: '', pinned: false })
  const [savingNoteEdit, setSavingNoteEdit] = useState(false)
  const [mapOpen, setMapOpen] = useState(true)
  const [showAddContact, setShowAddContact] = useState(false)
  const [contactForm, setContactForm] = useState({ full_name: '', role: '', email: '', mobile: '' })
  const [savingContact, setSavingContact] = useState(false)
  const [showStartTrial, setShowStartTrial] = useState(false)
  const blankTrialForm = {
    contactKey: '', admin_first_name: '', admin_last_name: '', admin_display_name: '',
    admin_username: '', admin_email: '', admin_mobile_number: '',
  }
  const [trialForm, setTrialForm] = useState(blankTrialForm)
  const [savingTrial, setSavingTrial] = useState(false)
  // Only a club contact carrying a real email address can be handed the
  // Primary Admin invite — a rep can no longer type an arbitrary name/email.
  const trialEligibleContacts = (drawer?.contacts || []).filter(c => EMAIL_RE.test(c.email || ''))
  const pickTrialContact = (key) => {
    const picked = trialEligibleContacts.find(c => contactKey(c) === key)
    if (!picked) { setTrialForm(f => ({ ...f, contactKey: key })); return }
    const { first, last } = splitFullName(picked.full_name)
    setTrialForm(f => ({
      ...f, contactKey: key,
      admin_first_name: first, admin_last_name: last, admin_display_name: picked.full_name,
      admin_email: picked.email, admin_mobile_number: picked.mobile || '',
    }))
  }

  // The activity currently open in the "View email" modal (holds meta.html/
  // subject/to_email/to_name) — null when the modal is closed.
  const [viewingEmail, setViewingEmail] = useState(null)
  const [showExtendTrial, setShowExtendTrial] = useState(false)
  const blankExtendTrialForm = {
    days: 14, contactKey: '', newFullName: '', newEmail: '', newMobile: '', nominate: false,
  }
  const [extendTrialForm, setExtendTrialForm] = useState(blankExtendTrialForm)
  const [showExtendNewContact, setShowExtendNewContact] = useState(false)
  const [savingExtendTrial, setSavingExtendTrial] = useState(false)
  // Same rule as the Start trial contact picker — an email is the one thing
  // this action can't do without (it's how the confirmation lands, and how
  // a nominated Primary Admin is invited).
  const extendTrialEligibleContacts = (drawer?.contacts || []).filter(c => EMAIL_RE.test(c.email || ''))

  const submitExtendTrial = async (e) => {
    e.preventDefault()
    const body = { days: Number(extendTrialForm.days) || 14, nominate_primary_admin: extendTrialForm.nominate }
    if (showExtendNewContact) {
      if (!extendTrialForm.newFullName.trim()) { toast?.error('A name is required'); return }
      if (!EMAIL_RE.test(extendTrialForm.newEmail.trim())) { toast?.error('A valid email address is required'); return }
      body.new_contact = {
        full_name: extendTrialForm.newFullName.trim(), email: extendTrialForm.newEmail.trim(),
        mobile: extendTrialForm.newMobile.trim() || null,
      }
    } else {
      const picked = extendTrialEligibleContacts.find(c => contactKey(c) === extendTrialForm.contactKey)
      if (!picked) { toast?.error('Pick a contact, or add a new one'); return }
      if (picked.directory_contact_id) body.directory_contact_id = picked.directory_contact_id
      else if (picked.crm_person_id) body.crm_person_id = picked.crm_person_id
    }
    setSavingExtendTrial(true)
    try {
      const result = await api.salesWorkspaceExtendTrial(drawer.deal.id, body)
      const newEnd = new Date(result.new_trial_end).toLocaleDateString('en-AU')
      let msg = `Trial extended by ${result.days} day${result.days === 1 ? '' : 's'} to ${newEnd}. `
      msg += result.email_sent
        ? `A confirmation email was sent to ${result.contact_email}.`
        : `The confirmation email could not be sent — let them know another way.`
      if (result.nominated_primary_admin) {
        msg += result.primary_admin_invited
          ? ' An invite email was also sent so they can set up their Primary Admin account.'
          : ' They are now this club’s Primary Admin.'
      }
      toast?.success(msg)
      setShowExtendTrial(false)
      setShowExtendNewContact(false)
      setExtendTrialForm(blankExtendTrialForm)
      refreshBoth()
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingExtendTrial(false)
    }
  }

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
  // Which templates pre-fill from their own editable copy in Comms ->
  // Templates rather than opening a blank form ('custom' is one of them now).
  // Read off the payload, NOT a list kept here: a hand-kept mirror is how a
  // newly-added template ends up in the dropdown while silently loading no
  // preview. The literal is the fallback for a server that predates the flag.
  const BUILT_IN_EMAIL_TEMPLATES = useMemo(() => {
    const flagged = emailTemplates.templates.filter(t => t.built_in).map(t => t.key)
    return flagged.length ? flagged : ['information', 'voicemail_followup',
      'voicemail_followup_trial_offer', 'voicemail_followup_extend_trial_soon',
      'voicemail_followup_extend_trial', 'trial_information', 'trial_extension',
      'demo', 'subscribe', 'custom']
  }, [emailTemplates])

  useEffect(() => {
    api.salesWorkspaceEmailTemplates().then(setEmailTemplates).catch(() => {})
  }, [])

  const noCallStatus = CALL_STATUS.every(s => !filters.call_status?.[s.key])

  // `anchor` (default true) re-scrolls the open club's row back into view once
  // the reload lands, for the cases that can genuinely move it: a call/email/
  // assign/interest action re-sorts or re-scopes the queue. A reload fired by
  // nothing more than a filter tweak (the effect below) passes `false` — the
  // row the rep is looking at may now sit further down the SAME filtered
  // list, and jumping the viewport to chase it there is not something a
  // filter checkbox should ever do (reported live against the Call status
  // boxes, but the same effect drives every filter, so the fix is general).
  const loadClubs = useCallback((opts) => {
    const anchor = opts?.anchor !== false
    setLoadingList(true)
    // call_status rides as a comma-list, never as the four booleans the
    // screen holds — see callStatusParam.
    return api.salesWorkspaceClubs({ ...filters, call_status: callStatusParam(filters.call_status) }).then((d) => {
      const rows = d.clubs || []
      setClubs(rows)
      setStages(d.stages || [])
      // The currently-open drawer belongs to a club that just dropped out of
      // the filtered queue — most often a call outcome moving it to a stage
      // (or "called"/callback state) the active filters no longer include,
      // but the same thing happens if a filter itself changed underneath it.
      // Rather than leave a blank "pick a club" pane, advance straight to
      // whichever club now sits where the dropped one used to — i.e. the
      // next one down in the list as the rep was last looking at it, walking
      // upward instead if it was the last row, so the rep lands next to
      // where they were rather than being bounced to an unrelated club.
      if (selectedIdRef.current && !rows.some(c => c.id === selectedIdRef.current)) {
        const prevRows = clubsRef.current
        const prevIdx = prevRows.findIndex(c => c.id === selectedIdRef.current)
        let next = null
        if (prevIdx !== -1) {
          for (let i = prevIdx + 1; i < prevRows.length && !next; i++) {
            next = rows.find(c => c.id === prevRows[i].id) || null
          }
          for (let i = prevIdx - 1; i >= 0 && !next; i--) {
            next = rows.find(c => c.id === prevRows[i].id) || null
          }
        }
        if (!next) next = rows[0] || null
        if (next) {
          selectClub(next.id, { scroll: true })
        } else {
          selectedIdRef.current = null
          setSelectedId(null)
          setDrawer(null)
          setSearchParamsRef.current((p) => { const n = new URLSearchParams(p); n.delete('club'); return n }, { replace: true })
        }
      } else if (selectedIdRef.current && anchor) {
        // Still selected and still in the filtered list, but a resort (a
        // call/email action moves priority_score, updated_at, etc.) can
        // relocate its row well outside the current viewport with nothing
        // else bringing it back — the open club's row must always stay on
        // display, so re-anchor to it every time an ACTION reloads the queue
        // while it's still selected. Skipped entirely for a plain filter
        // change (anchor === false, see loadClubs' own note above) — a
        // filter tweak must never move the viewport, however far the row
        // happens to sit within the newly-filtered list.
        const id = selectedIdRef.current
        setTimeout(() => {
          rowRefs.current[id]?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
        }, 60)
      } else if (!initialPositionDoneRef.current && rows[0]) {
        // The very first load of this screen, nothing selected yet (no
        // ?club= deep link either — that branch, above, would already have
        // set selectedIdRef.current by the time this runs). Land on the top
        // of the queue exactly as it stands under the current filters/sort
        // — it's already row one, so no scroll is needed to get there.
        selectClub(rows[0].id)
      }
      initialPositionDoneRef.current = true
      return rows
    }).catch(() => { toast?.error('Could not load the club queue'); return [] })
      .finally(() => setLoadingList(false))
  }, [filters, toast])

  // Restore this user's own last Call status selection (per account, so it
  // follows a rep or a super admin between browsers and machines). A user
  // who has never touched the boxes — or whose saved value is unreadable —
  // gets everything ticked, which hides nothing.
  useEffect(() => {
    let alive = true
    api.getUiPrefs().then(r => {
      if (!alive) return
      const saved = cleanCallStatus(r?.prefs?.[CALL_STATUS_PREF])
      if (saved) {
        lastSavedCallStatusRef.current = JSON.stringify(saved)
        setFilters(f => ({ ...f, call_status: saved }))
      }
    }).catch(() => {})
      .finally(() => { if (alive) setCallStatusLoaded(true) })
    return () => { alive = false }
  }, [])

  // Persist a change back to the account, debounced. Compares against the
  // last-saved snapshot so hydration itself never writes, and the initial
  // all-ticked default is only stored once the user actually changes it.
  useEffect(() => {
    if (!callStatusLoaded) return
    const cur = JSON.stringify(filters.call_status || {})
    if (cur === lastSavedCallStatusRef.current) return
    lastSavedCallStatusRef.current = cur
    const t = setTimeout(() => {
      api.setUiPrefs({ [CALL_STATUS_PREF]: filters.call_status || {} }).catch(() => {})
    }, 500)
    return () => clearTimeout(t)
  }, [filters.call_status, callStatusLoaded])

  // Held back until this user's saved Call status selection has been read,
  // so the queue is fetched ONCE, already scoped the way they left it —
  // loading first and re-fetching on hydration would flash a queue they
  // didn't ask for and, worse, land the drawer on a club that is about to
  // drop out of it.
  useEffect(() => { if (callStatusLoaded) loadClubs({ anchor: false }) }, [loadClubs, callStatusLoaded])
  useEffect(() => {
    if (isSuper) api.salesWorkspaceTeam().then((d) => setTeam(d.team || [])).catch(() => {})
  }, [isSuper])
  // Every caller (sales included) needs the staff list — it's who a "wants
  // pricing/more info/a demo" follow-up can be handed off to, not a
  // super-admin-only assignment tool.
  useEffect(() => {
    api.salesWorkspaceStaff().then((d) => setStaff(d.staff || [])).catch(() => {})
    api.salesWorkspaceEventOwners().then((d) => setEventOwners(d.owners || [])).catch(() => {})
  }, [])

  const loadDrawer = useCallback((dealId) => {
    setLoadingDrawer(true)
    // Where this club came from (the /trial pick, how far registration got,
    // the ad behind it) rides on its own request, fired alongside rather than
    // inside the drawer's — every part of it reads a beacon table, and the
    // wizard rollup in particular is a whole-platform rebuild whenever its
    // own short cache has lapsed. The pane no longer waits on any of it.
    setSignals(null)
    setSignalsLoading(true)
    signalsForRef.current = dealId
    api.salesWorkspaceClubSignals(dealId)
      .then((d) => { if (signalsForRef.current === dealId) setSignals(d) })
      .catch(() => {})
      .finally(() => { if (signalsForRef.current === dealId) setSignalsLoading(false) })
    api.salesWorkspaceClub(dealId).then((d) => {
      setDrawer(d)
      setCallForm(emptyCallForm())
      // A club switch must not carry over the previous club's loaded email —
      // template, subject, body and the "+ New contact…" inline forms all
      // reset, and the editor remounts (key bump) so its iframe doesn't
      // keep showing the old club's content under a blank state.
      setEmailForm({ contactKey: '', template: '', subject: '', body: '' })
      setShowNewCallContact(false)
      setShowNewEmailContact(false)
      setEmailEditorKey(k => k + 1)
      // A club switch must not leave a stale edit form open against the
      // PREVIOUS club's note — its activity id means nothing once the
      // drawer has moved on.
      setEditingNoteId(null)
    }).catch(() => toast?.error('Could not load this club')).finally(() => setLoadingDrawer(false))
  }, [toast])

  // { scroll: true } is only for a programmatic jump the rep didn't click
  // themselves (a ?club= deep link, or auto-advancing past a club that just
  // dropped out of the filter below) — an ordinary click never passes it, so
  // the queue's own scroll position is left exactly as the rep had it.
  const selectClub = (dealId, { scroll = false } = {}) => {
    selectedIdRef.current = dealId
    setSelectedId(dealId)
    loadDrawer(dealId)
    setSearchParams((p) => { const n = new URLSearchParams(p); n.set('club', dealId); return n }, { replace: true })
    if (scroll) {
      // Deferred a tick so a row that only just entered the list (e.g. the
      // new next-club after a reload) has actually mounted before we look
      // for its ref — same pattern AreaEditor.jsx uses for the same reason.
      // 'instant', not 'smooth' — a programmatic jump (a deep link, or
      // auto-advancing past a dropped-out club) should land the rep exactly
      // where the system decided to put them, not visibly travel there row
      // by row. index.css sets `scroll-behavior: smooth` globally (on
      // <html>, and that's an inherited CSS property), so 'auto' here would
      // still animate — 'instant' is the one value that overrides it.
      setTimeout(() => rowRefs.current[dealId]?.scrollIntoView({ block: 'nearest', behavior: 'instant' }), 60)
    }
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
    if (clubParam && clubParam !== selectedId) selectClub(clubParam, { scroll: true })
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
      const wasNote = isGeneralOutcome(callForm.outcome)
      setCallForm(emptyCallForm())
      // A General Note is not a call and does not mark the club as called,
      // so it must not report itself as one either.
      toast?.success(wasNote ? 'Note saved' : 'Call logged')
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

  const startEditNote = (a) => {
    setEditingNoteId(a.id)
    setEditNoteForm({ body: a.body || '', pinned: !!a.meta?.pinned })
  }
  const cancelEditNote = () => setEditingNoteId(null)
  const saveEditNote = async () => {
    if (!editNoteForm.body.trim()) { toast?.error("Note can't be empty"); return }
    setSavingNoteEdit(true)
    try {
      await api.salesWorkspaceEditNote(drawer.deal.id, editingNoteId, editNoteForm)
      setEditingNoteId(null)
      loadDrawer(drawer.deal.id)
    } catch (err) {
      toast?.error(err.message)
    } finally {
      setSavingNoteEdit(false)
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

  // Assignment and commission attribution are different things: a super
  // admin may move a club whenever they like, but if a rep has already
  // EARNED it (logged a real call outcome or emailed a contact) the server
  // refuses with a 409 until this asks. Confirm re-sends the same request
  // with the flag; Cancel leaves the assignment exactly as it was.
  const assignWithConfirm = async (send) => {
    try {
      return await send(false)
    } catch (err) {
      if (err?.detail?.code !== 'commission_attributed') throw err
      if (!window.confirm(err.message)) return null
      return await send(true)
    }
  }

  const submitAssign = async (ownerUserId) => {
    try {
      const res = await assignWithConfirm(
        (confirm) => api.salesWorkspaceAssign(drawer.deal.id, ownerUserId, confirm))
      if (res === null) { refreshBoth(); return }   // cancelled — put the picker back
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
  const toggleBulkRep = (id) => {
    setBulkUnassign(false)
    setBulkReps(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const toggleBulkUnassign = () => {
    setBulkReps(new Set())
    setBulkUnassign(u => !u)
  }

  const submitBulkAssign = async () => {
    if (checkedIds.size === 0) { toast?.error('Select at least one club'); return }
    if (!bulkUnassign && bulkReps.size === 0) { toast?.error('Pick at least one salesperson, or Unassigned'); return }
    setBulkAssigning(true)
    try {
      const result = await assignWithConfirm((confirm) => api.salesWorkspaceBulkAssign(
        [...checkedIds], bulkUnassign ? [] : [...bulkReps], bulkUnassign, confirm))
      if (result === null) return   // cancelled — the selection stays as it was
      const summary = Object.entries(result.by_rep).map(([name, n]) => `${name}: ${n}`).join(', ')
      const verb = bulkUnassign ? 'Unassigned' : 'Assigned'
      toast?.success(`${verb} ${result.assigned} club${result.assigned === 1 ? '' : 's'}${summary ? ` — ${summary}` : ''}`)
      setCheckedIds(new Set())
      setBulkReps(new Set())
      setBulkUnassign(false)
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
      // Every template (including Custom, which now also opens pre-filled in
      // the Design editor) sends the rep's possibly-edited copy — flush()
      // reads the iframe's current state synchronously, since onChange's
      // state update may not have landed yet.
      payload.subject = emailForm.subject
      payload.body = emailEditorRef.current?.flush() ?? emailForm.body
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
        <SalesEventsView dealOptions={dealOptions} staffOptions={staff} ownerOptions={eventOwners} />
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
        {/* Two columns, not one wrapping row. Call status is five stacked
            checkboxes and so the tallest thing here by some way — left in the
            wrap it pushed everything else around and sat on a line of its own
            with a gap beside it. As its own column it reads as the panel it
            is, and the filters wrap freely in what is left. */}
        <div className="flex flex-col lg:flex-row gap-4">
          {/* A grid rather than a wrap: with eight groups of different widths
              the wrap left "Meta ad" alone on a line with half the card empty
              beside it, and put two pickers that belong together on different
              rows. Twelve columns rather than auto-fill, because the spans
              have to ADD UP — an auto-fill track count moves with the width,
              so the same spans made two square rows at one size and a ragged
              three at another. Here each row is 3+4+2+3 and 2+2+3+5, always.
              Below lg the whole thing drops to a plain two-up and every span
              switches off, which is the only shape that fits a phone. */}
          <div className="flex-1 min-w-0 grid grid-cols-2 lg:grid-cols-12 gap-x-5 gap-y-3 items-start">
          <FilterGroup label="Search" className="col-span-2 lg:col-span-3">
            <TextInput value={filters.q} onChange={e => setFilters(f => ({ ...f, q: e.target.value }))}
              placeholder="Club or contact name…" className="w-full" />
          </FilterGroup>

          <FilterGroup label="Stage" className="col-span-2 lg:col-span-5">
            <div className="min-w-[130px] flex-1">
              <StagePicker stages={stages} value={filters.stage_key} onChange={v => setFilters(f => ({ ...f, stage_key: v }))} />
            </div>
            <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-2">
              <input type="checkbox" checked={filters.stage_key.includes('trial_current')}
                onChange={() => toggleTrialFilter('trial_current')} />
              Current trials
            </label>
            <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-2">
              <input type="checkbox" checked={filters.stage_key.includes('trial_expired')}
                onChange={() => toggleTrialFilter('trial_expired')} />
              Expired trials
            </label>
          </FilterGroup>

          {isSuper && (
            <FilterGroup label="Assigned" className="lg:col-span-2">
              <div className="w-full">
                <MultiSelectPicker options={assignedOptions} value={filters.owner_user_ids}
                  onChange={v => setFilters(f => ({ ...f, owner_user_ids: v }))}
                  allLabel="Everyone" noun="people" />
              </div>
            </FilterGroup>
          )}

          {/* Who EARNED each club, which a reassignment never moves — so this
              answers "what has Kate actually won" rather than "what is on
              Kate's list today". Same control and same option list as
              Assigned; the two compose, since a club can be worked by one rep
              and earned by another. */}
          {isSuper && (
            <FilterGroup label="Attributed" className="lg:col-span-2">
              <div className="w-full">
                <MultiSelectPicker options={attributedOptions} value={filters.attributed_user_ids}
                  onChange={v => setFilters(f => ({ ...f, attributed_user_ids: v }))}
                  allLabel="Everyone" noun="people" />
              </div>
            </FilterGroup>
          )}

          <FilterGroup label="Engagement score" className="lg:col-span-3">
            <div className="flex items-center gap-1.5">
              <NumberInput min={0} max={100} placeholder="min" value={filters.min_score}
                onChange={e => setFilters(f => ({ ...f, min_score: e.target.value }))} className="w-full min-w-0" />
              <span className="text-pb-faintest">–</span>
              <NumberInput min={0} max={100} placeholder="max" value={filters.max_score}
                onChange={e => setFilters(f => ({ ...f, max_score: e.target.value }))} className="w-full min-w-0" />
            </div>
          </FilterGroup>

          <FilterGroup label="State" className="lg:col-span-2">
            <div className="w-full">
              <StatePicker value={filters.states} onChange={v => setFilters(f => ({ ...f, states: v }))} />
            </div>
          </FilterGroup>

          <FilterGroup label="Interested in" className="col-span-2 lg:col-span-5">
            <div className="flex flex-wrap gap-1.5">
              {MODULE_ORDER.map(key => {
                const on = filters.modules.includes(key)
                return (
                  <button key={key} type="button"
                    onClick={() => setFilters(f => ({
                      ...f, modules: f.modules.includes(key) ? f.modules.filter(k => k !== key) : [...f.modules, key],
                    }))}
                    className={`px-2 py-1 rounded-full text-[11.5px] border transition ${
                      on ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                         : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                    {moduleLabel(key)}
                  </button>
                )
              })}
            </div>
          </FilterGroup>

          <FilterGroup label="Meta ad" className="lg:col-span-2">
            <div className="flex flex-wrap items-center gap-x-3" title="From the trial signup wizard — tick both to match either">
              <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-2">
                <input type="checkbox" checked={filters.meta_selected}
                  onChange={e => setFilters(f => ({ ...f, meta_selected: e.target.checked }))} />
                Selected
              </label>
              <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-2">
                <input type="checkbox" checked={filters.meta_searched}
                  onChange={e => setFilters(f => ({ ...f, meta_searched: e.target.checked }))} />
                Searched
              </label>
            </div>
          </FilterGroup>

          </div>

          <FilterGroup label="Call status" stack
            className="shrink-0 lg:pl-4 lg:border-l border-pb-hairline pt-3 border-t lg:pt-0 lg:border-t-0">
            {CALL_STATUS.map(s => (
              <label key={s.key} title={s.title}
                className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-0.5">
                <input type="checkbox" checked={!!filters.call_status?.[s.key]}
                  onChange={e => setFilters(f => ({
                    ...f, call_status: { ...f.call_status, [s.key]: e.target.checked },
                  }))} />
                <span className={`w-2.5 h-2.5 rounded-sm inline-block shrink-0 ${s.swatch}`} />
                {s.label}
              </label>
            ))}
          </FilterGroup>
        </div>
      </div>

      {isSuper && checkedIds.size > 0 && (
        <div className={`${CARD} mb-3 flex flex-wrap items-center gap-3`}>
          <span className="text-[12px] text-pb-text font-medium">{checkedIds.size} selected</span>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={toggleBulkUnassign}
              title="Send the selected clubs back into the shared pool, unassigned"
              className={`px-2 py-1 rounded font-mono text-[10px] border transition-colors ${
                bulkUnassign ? 'border-pb-red text-pb-red' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}
            >
              Unassigned
            </button>
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
            {bulkUnassign ? 'Sends every selected club back into the pool'
              : bulkReps.size > 1 ? 'Splits evenly, round-robin'
              : bulkReps.size === 1 ? 'Assigns everyone selected to them' : ''}
          </span>
          <Btn sm variant="primary" onClick={submitBulkAssign} disabled={bulkAssigning}>
            {bulkAssigning ? (bulkUnassign ? 'Unassigning…' : 'Assigning…') : (bulkUnassign ? 'Unassign selected' : 'Assign selected')}
          </Btn>
          <Btn sm variant="subtle" onClick={() => { setCheckedIds(new Set()); setBulkReps(new Set()); setBulkUnassign(false) }}>Clear</Btn>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-4 items-start">
        {/* Queue */}
        <div className={CARD}>
          {/* Sort and the counts share one line. They were two stacked rows
              of chrome above the list plus the select-all row under them,
              which pushed the first club a long way down a column whose whole
              job is to be scanned. */}
          <div className="flex items-center gap-1.5 pb-2 mb-1.5 border-b border-pb-hairline">
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
            {clubs.length > 0 && (
              <span className="ml-auto text-[11px] text-pb-faint whitespace-nowrap">
                <span className="text-pb-text font-medium">{clubs.length}</span> club{clubs.length === 1 ? '' : 's'}
                <span className="text-pb-faintest"> · </span>
                <span className="text-pb-text font-medium">{totalContacts}</span> contact{totalContacts === 1 ? '' : 's'}
              </span>
            )}
          </div>
          {/* A background reload (Save Call, Send Email, toggling module
              interest — anything that calls loadClubs() while a club is
              already open) should never collapse this list down to a bare
              "Loading…" line and regrow it a moment later — that's needless
              flicker for a refresh nobody asked to see. loadClubs() never
              clears `clubs` before re-fetching, so simply not gating the
              row list on `loadingList` keeps the STALE rows on screen the
              whole time; React reconciles them against the fresh set once
              it lands, keyed on id, with no interim empty state. The
              "Loading…" placeholder is reserved for the one case with
              nothing to show yet: a genuine first load. */}
          {loadingList && clubs.length === 0 ? (
            <p className="text-[12px] text-pb-faintest px-1 py-2">Loading…</p>
          ) : clubs.length === 0 ? (
            <p className="text-[12px] text-pb-faintest px-1 py-2">
              {/* An empty queue with every Call status box unticked is
                  self-inflicted, and reads as broken unless it says so. */}
              {noCallStatus ? 'No Call status is ticked, so nothing can match. Tick at least one above.'
                : 'No clubs match these filters.'}
            </p>
          ) : (
            <div className="space-y-1.5 max-h-[75vh] overflow-y-auto">
              {isSuper && (
                <label className="flex items-center gap-1.5 px-2.5 py-1 text-[10.5px] text-pb-faint cursor-pointer select-none">
                  <input type="checkbox" checked={allChecked} onChange={toggleSelectAllVisible} />
                  Select all filtered
                </label>
              )}
              {clubs.map(c => (
                <div key={c.id} ref={el => { rowRefs.current[c.id] = el }} className="flex items-start gap-1.5">
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
                      : c.last_call?.outcome === 'voicemail' ? 'border-purple-500/60 hover:bg-pb-surface2'
                      : c.ever_called ? 'border-orange-500/60 hover:bg-pb-surface2'
                      : 'border-transparent hover:bg-pb-surface2'
                    }`}
                  >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-pb-text text-[13px] font-medium truncate">{c.marketing_club_name || c.title}</span>
                    <PriorityBadge score={c.priority_score} />
                  </div>
                  {townStateLabel(c.marketing_club_suburb, c.marketing_club_state) && (
                    <div className="text-[10.5px] mt-0.5" style={{ color: TOWN_STATE_COLOR }}>
                      {townStateLabel(c.marketing_club_suburb, c.marketing_club_state)}
                    </div>
                  )}
                  <AssociationChips associations={c.marketing_club_associations} className="mt-1" />
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
                  {c.min_trial_days_remaining != null && (
                    <div className={`flex items-center gap-1 mt-1 text-[10.5px] ${
                      c.min_trial_days_remaining >= 0 ? 'text-pb-text' : 'text-pb-red'}`}>
                      <TrialHourglassIcon className="w-3 h-3 shrink-0"
                        color={c.min_trial_days_remaining >= 0 ? TRIAL_AMBER : '#ef4444'} />
                      <span>Trial: <span className="font-medium">{trialDaysLabel(c.min_trial_days_remaining)}</span></span>
                    </div>
                  )}
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
                  <div className="min-w-0">
                    <h2 className="font-display font-bold text-lg">{drawer.deal.marketing_club_name || drawer.deal.title}</h2>
                    {townStateLabel(drawer.deal.marketing_club_suburb, drawer.deal.marketing_club_state) && (
                      <p className="text-[12px] text-pb-faint mt-0.5">
                        {townStateLabel(drawer.deal.marketing_club_suburb, drawer.deal.marketing_club_state)}
                      </p>
                    )}
                    <AssociationChips associations={drawer.deal.marketing_club_associations} className="mt-1.5" />
                  </div>
                  {/* ml-auto pins this group to the right edge whether it fits
                      beside the title or, on a narrow drawer, wraps onto its
                      own line below it — without it, `justify-between` only
                      right-aligns a SECOND item on the SAME row, so a wrapped
                      single-item second row (this whole group, once the club
                      name/town/associations push past the available width)
                      fell back to flex-start and rendered on the left, which
                      is the reported "wraps to the left" bug. shrink-0 stops
                      the Select + buttons themselves being squeezed. */}
                  <div className="flex items-center gap-2 ml-auto shrink-0">
                    {drawer.can_assign && (
                      <div>
                        <Select value={drawer.deal.owner_user_id || ''} onChange={e => submitAssign(e.target.value || null)} className="!w-auto">
                          <option value="">Unassigned</option>
                          {team.map(u => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
                        </Select>
                        {/* Who EARNED the club, which is not the same as who
                            holds it — shown here so a super admin sees whose
                            work they are about to move before they touch the
                            picker, not only in the confirm that follows. */}
                        {drawer.deal.commission_rep_name && (
                          <span className="block text-[10.5px] text-pb-faintest mt-1 text-right">
                            Contacted by {drawer.deal.commission_rep_name}
                          </span>
                        )}
                      </div>
                    )}
                    {START_TRIAL_ENABLED && !drawer.deal.is_customer && drawer.deal.marketing_club_id && (
                      <Btn variant="primary" sm onClick={() => { setTrialForm(blankTrialForm); setShowStartTrial(true) }}>Start trial</Btn>
                    )}
                    <Btn variant="subtle" sm disabled={drawer.deal.min_trial_days_remaining == null}
                      title={drawer.deal.min_trial_days_remaining == null ? 'This club has no trial to extend' : undefined}
                      onClick={() => {
                        setExtendTrialForm(blankExtendTrialForm)
                        setShowExtendNewContact(false)
                        setShowExtendTrial(true)
                      }}>
                      Extend Trial
                    </Btn>
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

              <MetaAdsCard meta={signals?.meta_ads} />

              <OriginCard signals={signals} loading={signalsLoading} />

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

              {drawer.deal.marketing_club_id && (
                <div className={CARD}>
                  <button type="button" onClick={() => setMapOpen(o => !o)}
                    className="flex items-center justify-between w-full text-left">
                    <h3 className="font-display font-bold text-[13px]">Location</h3>
                    <span className="text-pb-faintest text-[10px]">{mapOpen ? '▾' : '▸'}</span>
                  </button>
                  {mapOpen && (
                    <div className="mt-2">
                      <ClubLocationMap
                        clubId={drawer.deal.marketing_club_id}
                        latitude={drawer.deal.marketing_club_latitude}
                        longitude={drawer.deal.marketing_club_longitude}
                        postcode={drawer.deal.marketing_club_postcode}
                        state={drawer.deal.marketing_club_state}
                        fetchBoundary={() => api.salesWorkspaceClubBoundary(drawer.deal.id)}
                      />
                    </div>
                  )}
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
                  <Field label="Contact" composite>
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
                  <Field label="Interested in" composite>
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
                  {ASSIGNABLE_EVENT_OUTCOMES.includes(callForm.outcome) && callForm.followUpAt && (
                    <Field label="Hand this follow-up to" hint="Leave as 'Me' to keep it on your own calendar">
                      <Select value={callForm.eventOwnerUserId} onChange={e => setCallForm(f => ({ ...f, eventOwnerUserId: e.target.value }))}>
                        <option value="">Me</option>
                        {staff.map(u => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
                      </Select>
                    </Field>
                  )}
                  <Field label="Follow up (optional)">
                    <TextInput type="datetime-local" value={callForm.followUpAt} onChange={e => setCallForm(f => ({ ...f, followUpAt: e.target.value }))} />
                  </Field>
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
                      editingNoteId === a.id ? (
                        <div key={a.id} className="bg-pb-amber/10 border border-pb-amber/30 rounded px-2 py-1.5">
                          <NoteEditForm value={editNoteForm} onChange={setEditNoteForm} onSave={saveEditNote} onCancel={cancelEditNote} saving={savingNoteEdit} />
                        </div>
                      ) : (
                        <div key={a.id} className="text-[12px] bg-pb-amber/10 border border-pb-amber/30 rounded px-2 py-1.5 flex items-start justify-between gap-2">
                          <span className="whitespace-pre-wrap">{a.body}</span>
                          <span className="flex items-center gap-1.5 shrink-0">
                            {a.meta?.edited_at && <span className="text-[10.5px] text-pb-faintest">(edited)</span>}
                            <button type="button" onClick={() => startEditNote(a)}
                              className="text-[10.5px] text-pb-accent hover:underline">Edit</button>
                          </span>
                        </div>
                      )
                    ))}
                  </div>
                )}
                <h4 className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1.5">History</h4>
                {timeline.length === 0 ? (
                  <p className="text-[12px] text-pb-faintest">No activity yet.</p>
                ) : timeline.map(a => (
                  <ActivityRow key={a.id} a={a} onViewEmail={setViewingEmail}
                    editing={editingNoteId === a.id} editValue={editNoteForm} onChangeEdit={setEditNoteForm}
                    onStartEdit={startEditNote} onSaveEdit={saveEditNote} onCancelEdit={cancelEditNote} savingEdit={savingNoteEdit} />
                ))}
              </div>

              <div className={CARD}>
                <h3 className="font-display font-bold text-[13px] mb-2">Send an email</h3>
                <form onSubmit={submitEmail} className="space-y-2">
                  <Field label="Contact" composite>
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
                        <option key={t.key} value={t.key}>{t.label}</option>
                      ))}
                    </Select>
                  </Field>
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
        <>
        <Modal open={showStartTrial} onClose={() => setShowStartTrial(false)} title={`Start a trial for ${drawer.deal.marketing_club_name}`}>
          <form onSubmit={submitStartTrial} className="space-y-2">
            <p className="text-[11.5px] text-pb-faint">
              Sets this club up exactly like Super Admin's New Club — a trial of every module starts immediately,
              and the contact picked below is emailed an invite link to set their own password as this club's
              Primary Admin.
            </p>
            <Field label="Primary admin contact" hint="Only contacts with a valid email address on file are listed">
              <Select value={trialForm.contactKey} onChange={e => pickTrialContact(e.target.value)} required>
                <option value="" disabled>— select a contact —</option>
                {trialEligibleContacts.map(c => (
                  <option key={contactKey(c)} value={contactKey(c)}>
                    {c.full_name}{c.role ? ` (${c.role})` : ''}
                  </option>
                ))}
              </Select>
            </Field>
            {trialEligibleContacts.length === 0 && (
              <p className="text-[11.5px] text-pb-red">
                No contact with a valid email address is on file for this club yet — add one under Contacts above
                before starting a trial.
              </p>
            )}
            {trialForm.contactKey && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="First name"><TextInput value={trialForm.admin_first_name} onChange={e => setTrialForm(f => ({ ...f, admin_first_name: e.target.value }))} required /></Field>
                  <Field label="Last name"><TextInput value={trialForm.admin_last_name} onChange={e => setTrialForm(f => ({ ...f, admin_last_name: e.target.value }))} required /></Field>
                </div>
                <Field label="Display name" hint="Defaults to first + last if left blank"><TextInput value={trialForm.admin_display_name} onChange={e => setTrialForm(f => ({ ...f, admin_display_name: e.target.value }))} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Username"><TextInput value={trialForm.admin_username} onChange={e => setTrialForm(f => ({ ...f, admin_username: e.target.value }))} required /></Field>
                  <Field label="Mobile (optional)"><TextInput value={trialForm.admin_mobile_number} onChange={e => setTrialForm(f => ({ ...f, admin_mobile_number: e.target.value }))} /></Field>
                </div>
                <Field label="Email" hint="From the contact picked above"><TextInput type="email" value={trialForm.admin_email} readOnly disabled /></Field>
              </>
            )}
            <Btn type="submit" variant="primary" disabled={savingTrial || !trialForm.contactKey}>{savingTrial ? 'Starting…' : 'Start trial'}</Btn>
          </form>
        </Modal>

        <Modal open={showExtendTrial} onClose={() => setShowExtendTrial(false)} title={`Extend trial for ${drawer.deal.marketing_club_name}`}>
          <form onSubmit={submitExtendTrial} className="space-y-2">
            <p className="text-[11.5px] text-pb-faint">
              {drawer.deal.min_trial_days_remaining != null && drawer.deal.min_trial_days_remaining < 0
                ? `Are you sure you want to extend the trial for ${drawer.deal.marketing_club_name}?`
                : `There ${drawer.deal.min_trial_days_remaining === 1 ? 'is' : 'are'} still ${drawer.deal.min_trial_days_remaining} day${drawer.deal.min_trial_days_remaining === 1 ? '' : 's'} remaining on the trial for ${drawer.deal.marketing_club_name}. Are you sure you want to extend the trial?`}
            </p>
            <Field label="Number of days extension">
              <NumberInput min={1} max={14} value={extendTrialForm.days}
                onChange={e => setExtendTrialForm(f => ({ ...f, days: e.target.value }))} style={{ width: 90 }} />
            </Field>
            <Field label="Send confirmation to" hint="Only contacts with a valid email address on file are listed">
              <Select value={showExtendNewContact ? NEW_CONTACT_VALUE : extendTrialForm.contactKey}
                onChange={e => {
                  if (e.target.value === NEW_CONTACT_VALUE) { setShowExtendNewContact(true); return }
                  setShowExtendNewContact(false)
                  setExtendTrialForm(f => ({ ...f, contactKey: e.target.value }))
                }}>
                <option value="" disabled>— select a contact —</option>
                {extendTrialEligibleContacts.map(c => (
                  <option key={contactKey(c)} value={contactKey(c)}>
                    {c.full_name}{c.role ? ` (${c.role})` : ''}
                  </option>
                ))}
                <option value={NEW_CONTACT_VALUE}>+ New contact…</option>
              </Select>
            </Field>
            {showExtendNewContact && (
              <div className="grid grid-cols-2 gap-2 p-2 rounded-lg border border-pb-hairline2 bg-pb-surface2">
                <Field label="Name"><TextInput value={extendTrialForm.newFullName} onChange={e => setExtendTrialForm(f => ({ ...f, newFullName: e.target.value }))} required /></Field>
                <Field label="Email"><TextInput type="email" value={extendTrialForm.newEmail} onChange={e => setExtendTrialForm(f => ({ ...f, newEmail: e.target.value }))} required /></Field>
                <Field label="Mobile (optional)"><TextInput value={extendTrialForm.newMobile} onChange={e => setExtendTrialForm(f => ({ ...f, newMobile: e.target.value }))} /></Field>
              </div>
            )}
            {!drawer.deal.primary_admin_name && (
              <label className="flex items-center gap-1.5 text-[12px] text-pb-faint cursor-pointer select-none py-1">
                <input type="checkbox" checked={extendTrialForm.nominate}
                  onChange={e => setExtendTrialForm(f => ({ ...f, nominate: e.target.checked }))} />
                Also make this contact the club's Primary Admin
              </label>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Btn type="button" variant="ghost" sm onClick={() => setShowExtendTrial(false)}>Cancel</Btn>
              <Btn type="submit" variant="primary" sm disabled={savingExtendTrial}>{savingExtendTrial ? 'Extending…' : 'Confirm'}</Btn>
            </div>
          </form>
        </Modal>

        <Modal open={!!viewingEmail} onClose={() => setViewingEmail(null)} title={viewingEmail?.meta?.subject || 'Email'}
          maxWidth="max-w-[40rem]">
          <div className="space-y-2">
            <div className="text-[11.5px] text-pb-faint">
              <div>To: {viewingEmail?.meta?.to_name}{viewingEmail?.meta?.to_email ? ` <${viewingEmail.meta.to_email}>` : ''}</div>
              <div>Sent: {viewingEmail && new Date(viewingEmail.occurred_at).toLocaleString('en-AU')}</div>
            </div>
            <iframe title="email preview" srcDoc={viewingEmail?.meta?.html || ''}
              className="w-full rounded border pb-hairline bg-white" style={{ height: 480 }} />
          </div>
        </Modal>
        </>
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
