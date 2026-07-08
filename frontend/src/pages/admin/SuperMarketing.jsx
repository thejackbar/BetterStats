import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// PlayHQ stores the abbreviated state on the club (e.g. "WA", "NSW"), so the
// filter value must be the abbreviation, not the full name.
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']

const SELECT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent'
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_ACCENT = 'px-3 py-1.5 rounded text-xs font-semibold bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 disabled:opacity-50'

// Shared layout primitives so the toolbar reads as tidy, labelled cards.
const CARD = 'rounded-xl border pb-hairline bg-pb-surface2/40 px-3 py-2.5 mb-2.5'
const SECTION = 'text-[11px] uppercase tracking-wide text-pb-faint font-semibold'
const FIELD_LABEL = 'block text-[10px] uppercase tracking-wide text-pb-faint mb-0.5'

// The tri-state directory filters. Each can be Off, Include (keep only matching)
// or Exclude (drop matching). Keys match the backend club_filters modes.
const MODE_FILTERS = [
  { key: 'junior', label: 'Juniors', title: 'Club name contains "junior"' },
  { key: 'carnival', label: 'Carnivals', title: 'Club name contains "carnival"' },
  { key: 'school', label: 'Schools', title: 'Club name contains "school"' },
  { key: 'rep', label: 'Rep orgs', title: 'Club name is a representative team (Rep / Representative)' },
  { key: 'cricket_au', label: 'Cricket Australia orgs', title: 'A club or officer email is on a Cricket Australia / state-body domain' },
  { key: 'emailed', label: 'Already-emailed', title: 'Club has an outreach send recorded' },
  { key: 'exported', label: 'Exported', title: 'Include = nothing left to export; Exclude = still has an emailable contact not yet in BetterComms' },
  { key: 'suppressed', label: 'Suppressed', title: 'Include = no subscribed emailable contact left; Exclude = still has a subscribed contact' },
  { key: 'excluded', label: 'Excluded', title: 'Club flagged as excluded from outreach. Include = only excluded clubs; Exclude = hide them' },
]
const MODE_CYCLE = { '': 'exclude', exclude: 'include', include: '' }
const MODE_STYLE = {
  '': 'border-pb-hairline text-pb-faint hover:text-pb-text',
  exclude: 'border-red-500/50 text-red-300 bg-red-500/10',
  include: 'border-emerald-500/50 text-emerald-300 bg-emerald-500/10',
}
const MODE_PREFIX = { '': '', exclude: '✕ ', include: '✓ ' }

// A filter chip whose click cycles Off → Exclude → Include → Off.
function FilterChip({ label, title, mode, onChange }) {
  const m = mode || ''
  return (
    <button type="button" title={title}
      onClick={() => onChange(MODE_CYCLE[m])}
      className={`px-2 py-0.5 rounded border text-xs transition ${MODE_STYLE[m]}`}>
      {MODE_PREFIX[m]}{label}
    </button>
  )
}

// Short, local date/time so a visit's recency reads at a glance.
function fmtWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

// A labelled filter cell — keeps every control on a tidy grid with its caption.
function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className={FIELD_LABEL}>{label}</label>
      {children}
    </div>
  )
}

const STATE_STYLE = {
  running:  { dot: 'bg-emerald-400 animate-pulse', text: 'text-emerald-300', label: 'Running' },
  waiting:  { dot: 'bg-sky-400',                    text: 'text-sky-300',     label: 'Waiting' },
  paused:   { dot: 'bg-amber-400',                  text: 'text-amber-300',   label: 'Paused' },
  idle:     { dot: 'bg-pb-faint',                   text: 'text-pb-dim',      label: 'Idle' },
  complete: { dot: 'bg-emerald-400',                text: 'text-emerald-300', label: 'Complete' },
  stopped:  { dot: 'bg-red-400',                    text: 'text-red-300',     label: 'Stopped' },
}

function CrawlStatus({ status }) {
  if (!status) return null
  const s = STATE_STYLE[status.state] || STATE_STYLE.idle
  return (
    <div className="flex items-center gap-2 rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2 mb-2.5">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${s.dot}`} />
      <span className={`text-xs font-semibold ${s.text}`}>{s.label}</span>
      <span className="text-xs text-pb-dim">{status.detail}</span>
      {status.continuous_enabled && (
        <span className="text-[11px] text-pb-faint ml-auto">
          continuous · {status.window.start}–{status.window.end} {status.window.tz}
          {status.in_window ? ' · in window' : ' · outside window'}
        </span>
      )}
    </div>
  )
}

// Searchable multi-select of associations. Selecting several filters clubs that
// belong to ANY of them. The ✕ on the button clears all selections.
function AssocMultiSelect({ options, selected, onChange, onSaveShort }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const ql = q.toLowerCase()
  const filtered = options
    .filter(o => o.name.toLowerCase().includes(ql) || (o.short || '').toLowerCase().includes(ql))
    .slice(0, 800)
  const toggle = (name) =>
    onChange(selected.includes(name) ? selected.filter(n => n !== name) : [...selected, name])
  return (
    <div className="relative" ref={ref}>
      <button type="button" className={SELECT_CLS + ' flex items-center gap-1.5'}
              onClick={() => setOpen(o => !o)}>
        <span>{selected.length ? `Associations (${selected.length})` : 'Associations'}</span>
        {selected.length > 0 && (
          <span role="button" title="Clear selection" className="text-pb-faint hover:text-red-300"
                onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-[40rem] max-w-[92vw] max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          <input autoFocus className={SELECT_CLS + ' w-full mb-2'} placeholder="Search associations..."
                 value={q} onChange={(e) => setQ(e.target.value)} />
          {selected.length > 0 && (
            <button type="button" className="text-[11px] text-pb-faint hover:text-pb-accent mb-1"
                    onClick={() => onChange([])}>clear selection</button>
          )}
          <div className="text-[10px] text-pb-faint px-1 mb-1">Short code is editable — type and press Enter (blank resets to default).</div>
          {!filtered.length && <div className="text-xs text-pb-faint px-1 py-2">No matches.</div>}
          {filtered.map(o => (
            <div key={o.name}
                 className="flex items-center gap-2 px-1 py-0.5 text-xs text-pb-text hover:bg-pb-surface rounded">
              <label className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                <input type="checkbox" checked={selected.includes(o.name)} onChange={() => toggle(o.name)} />
                <span className="truncate" title={o.name}>{o.name}</span>
              </label>
              {o.resolved === false
                ? <span className="text-[10px] text-pb-faint italic shrink-0" title="Roster not fetched yet — select and click Fetch full roster">not fetched</span>
                : <span className="text-pb-faint shrink-0">{o.count}</span>}
              <input
                key={`sc-${o.id}-${o.short || ''}`}
                defaultValue={o.short || ''}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onSaveShort(o.id, e.target.value); e.target.blur() } }}
                onBlur={(e) => { if ((e.target.value || '') !== (o.short || '')) onSaveShort(o.id, e.target.value) }}
                title="Short code — edit and press Enter (blank resets to default)"
                className="w-16 shrink-0 text-[10px] uppercase bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 focus:outline-none focus:border-pb-accent" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Searchable multi-select of countries. Selecting several filters clubs in ANY of
// them. Simpler than AssocMultiSelect — country is a plain column, no short code or
// roster to fetch. AU-only for now; ready for multi-country directory sources.
function CountryMultiSelect({ options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const ql = q.toLowerCase()
  const filtered = options.filter(o => o.name.toLowerCase().includes(ql)).slice(0, 800)
  const toggle = (name) =>
    onChange(selected.includes(name) ? selected.filter(n => n !== name) : [...selected, name])
  return (
    <div className="relative" ref={ref}>
      <button type="button" className={SELECT_CLS + ' flex items-center gap-1.5'}
              onClick={() => setOpen(o => !o)}>
        <span>{selected.length ? `Countries (${selected.length})` : 'Countries'}</span>
        {selected.length > 0 && (
          <span role="button" title="Clear selection" className="text-pb-faint hover:text-red-300"
                onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-72 max-w-[92vw] max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          <input autoFocus className={SELECT_CLS + ' w-full mb-2'} placeholder="Search countries..."
                 value={q} onChange={(e) => setQ(e.target.value)} />
          {selected.length > 0 && (
            <button type="button" className="text-[11px] text-pb-faint hover:text-pb-accent mb-1"
                    onClick={() => onChange([])}>clear selection</button>
          )}
          {!filtered.length && <div className="text-xs text-pb-faint px-1 py-2">No matches.</div>}
          {filtered.map(o => (
            <div key={o.name}
                 className="flex items-center gap-2 px-1 py-0.5 text-xs text-pb-text hover:bg-pb-surface rounded">
              <label className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                <input type="checkbox" checked={selected.includes(o.name)} onChange={() => toggle(o.name)} />
                <span className="truncate" title={o.name}>{o.name}</span>
              </label>
              <span className="text-pb-faint shrink-0">{o.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint">{label}</div>
      <div className="text-lg font-semibold text-pb-text">{value ?? '-'}</div>
    </div>
  )
}

function Pager({ total, page, pageSize, onPage, loading }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total ? page * pageSize + 1 : 0
  const to = Math.min((page + 1) * pageSize, total)
  const btn = 'px-2 py-0.5 rounded border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-40'
  return (
    <div className="flex items-center justify-between text-[11px] text-pb-faint my-2">
      <span>{total} matching club(s){total > 0 ? ` · showing ${from}–${to}` : ''}</span>
      {pages > 1 && (
        <span className="flex items-center gap-2">
          <button className={btn} disabled={page === 0 || loading}
                  onClick={() => onPage(p => Math.max(0, p - 1))}>Prev</button>
          <span>Page {page + 1} / {pages}</span>
          <button className={btn} disabled={page + 1 >= pages || loading}
                  onClick={() => onPage(p => p + 1)}>Next</button>
        </span>
      )}
    </div>
  )
}

// Everything collected for one club — all stored contacts, every association it
// plays in, address and ids. Driven entirely by the /clubs payload (no extra fetch).
// The six modules a prospect can trial / request (entitlement key → label).
const SALES_MODULES = [
  ['core', 'BetterStats'], ['select', 'BetterSelect'], ['socials', 'BetterSocials'],
  ['admin', 'BetterAdmin'], ['iq', 'BetterIQ'], ['fantasy', 'BetterFantasyCricket'],
]
const DEMO_OPTS = [['', 'no demo'], ['in_trial', 'demo → in a trial'],
  ['trial_expired', 'demo → trial expired'], ['customer', 'demo → now a customer']]

// Super-admin-maintained sales-pipeline state for one prospect club (no
// automated source). Feeds the directory-aware BetterComms segment filters.
function SalesEditor({ club, onSave }) {
  const [trial, setTrial] = useState(club.trial_modules || [])
  const [requested, setRequested] = useState(club.requested_trial_modules || [])
  const [demo, setDemo] = useState(club.demo_status || '')
  const [notInt, setNotInt] = useState(!!club.not_interested)
  const [busy, setBusy] = useState(false)
  const toggle = (list, set, k) => set(list.includes(k) ? list.filter(x => x !== k) : [...list, k])
  const arrEq = (a, b) => a.length === b.length && a.every(x => b.includes(x))
  const dirty = !arrEq(trial, club.trial_modules || []) ||
    !arrEq(requested, club.requested_trial_modules || []) || demo !== (club.demo_status || '') ||
    notInt !== !!club.not_interested
  const save = async () => {
    setBusy(true)
    try {
      await onSave(club.id, {
        trial_modules: trial, requested_trial_modules: requested,
        demo_status: demo || null, set_demo: true, not_interested: notInt,
      })
    } finally { setBusy(false) }
  }
  const ModuleRow = ({ label, list, set }) => (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-pb-faint mb-1">{label}</div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5">
        {SALES_MODULES.map(([k, l]) => (
          <label key={k} className="flex items-center gap-1.5 cursor-pointer text-pb-dim hover:text-pb-text">
            <input type="checkbox" className="accent-pb-accent shrink-0" checked={list.includes(k)} onChange={() => toggle(list, set, k)} />
            <span className="truncate" title={l}>{l}</span>
          </label>
        ))}
      </div>
    </div>
  )
  return (
    <div className="pt-3 mt-1 border-t pb-hairline space-y-2.5">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint font-semibold">Sales pipeline (manual)</div>
      <ModuleRow label="Trialing" list={trial} set={setTrial} />
      <ModuleRow label="Requested trial" list={requested} set={setRequested} />
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <span className="text-[10px] uppercase tracking-wide text-pb-faint">Demo</span>
        <select value={demo} onChange={e => setDemo(e.target.value)} className={SELECT_CLS}>
          {DEMO_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="flex items-center gap-1.5 cursor-pointer text-pb-dim hover:text-pb-text ml-1"
          title="Club contacted and explicitly not interested — overrides the engagement tier in the CRM">
          <input type="checkbox" className="accent-pb-accent shrink-0" checked={notInt}
            onChange={e => setNotInt(e.target.checked)} />
          <span>Not interested</span>
        </label>
        <button disabled={busy || !dirty} onClick={save}
          className="px-2 py-0.5 rounded border pb-hairline text-[11px] text-pb-text hover:border-pb-accent disabled:opacity-40">
          {busy ? '...' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// The usage breadcrumbs for one club, lazy-loaded when its row is expanded.
// Shows who visited the public site from a link tagged with the club's UTM code.
function VisitsPanel({ clubId, summary }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let alive = true
    setLoading(true)
    api.mktClubVisits(clubId)
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [clubId])

  const views = data?.views ?? summary?.views ?? 0
  return (
    <div className="pt-2 mt-1 border-t pb-hairline">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint mb-1">
        Site visits via this UTM
      </div>
      {loading && !data ? (
        <div className="text-pb-faint">Loading visits…</div>
      ) : !views ? (
        <div className="text-pb-faint">No site visits tracked from this club's UTM yet.</div>
      ) : !data ? (
        // Summary says there's traffic but the detail fetch hasn't landed (or
        // failed) — show the count without touching the missing detail fields.
        <div className="text-pb-dim">
          <span className="text-violet-300 font-medium">{views}</span> view(s) tracked.
        </div>
      ) : (
        <div className="space-y-1.5 text-pb-dim">
          <div>
            <span className="text-violet-300 font-medium">{views}</span> view(s) from{' '}
            <span className="text-violet-300 font-medium">{data.visitors ?? 0}</span> visitor(s)
            {data.last_seen && <span className="text-pb-faint"> · last {fmtWhen(data.last_seen)}</span>}
            {data.first_seen && <span className="text-pb-faint"> · first {fmtWhen(data.first_seen)}</span>}
          </div>
          {Array.isArray(data.pages) && data.pages.length > 0 && (
            <div>
              <div className="text-pb-faint text-[10px] uppercase tracking-wide mb-0.5">Pages viewed</div>
              <ul className="space-y-0.5">
                {data.pages.slice(0, 12).map((p, i) => (
                  <li key={i} className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] truncate">{p.page}</span>
                    <span className="text-pb-faint whitespace-nowrap">{p.views}×</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Visitors who browsed this club's pages then hit /login without an account
// to log into yet — lazy-loaded when the row is expanded, same pattern as
// VisitsPanel. Strongest read on this signal is a not-yet-customer club.
function LoginIntentPanel({ clubId, summary, isCustomer }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let alive = true
    setLoading(true)
    api.mktClubLoginIntent(clubId)
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [clubId])

  const visitors = data?.visitors ?? summary?.visitors ?? 0
  if (!loading && !visitors) return null
  return (
    <div className="pt-2 mt-1 border-t pb-hairline">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint mb-1">
        Browsed then hit /login
      </div>
      {loading && !data ? (
        <div className="text-pb-faint">Loading…</div>
      ) : (
        <div className="space-y-1">
          <div className="text-pb-dim">
            <span className="text-amber-300 font-medium">{visitors}</span> visitor(s)
            {data?.hits > visitors && <span className="text-pb-faint"> ({data.hits} hits)</span>}
            {data?.last_seen && <span className="text-pb-faint"> · last {fmtWhen(data.last_seen)}</span>}
          </div>
          {!isCustomer && (
            <div className="text-amber-300/90 text-[11px]">
              Not a customer yet — they have no account to log into. Likely wants to join.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ContactEditRow({ init, onSave, onCancel, busy }) {
  const [f, setF] = useState({
    role: init.role || '', full_name: init.full_name || '',
    email: init.email || '', mobile: init.mobile || '',
  })
  const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-[11px] text-pb-text focus:outline-none focus:border-pb-accent'
  return (
    <tr className="align-top">
      <td className="py-0.5 pr-2" />
      <td className="py-0.5 pr-2"><input className={inp} placeholder="Role" value={f.role}
        onChange={e => setF(s => ({ ...s, role: e.target.value }))} /></td>
      <td className="py-0.5 pr-2"><input className={inp} placeholder="Name" value={f.full_name}
        onChange={e => setF(s => ({ ...s, full_name: e.target.value }))} /></td>
      <td className="py-0.5 pr-2"><input className={inp} placeholder="email@club.com" value={f.email}
        onChange={e => setF(s => ({ ...s, email: e.target.value }))} /></td>
      <td className="py-0.5 pr-2"><input className={inp} placeholder="Mobile" value={f.mobile}
        onChange={e => setF(s => ({ ...s, mobile: e.target.value }))} /></td>
      <td className="py-0.5 whitespace-nowrap">
        <button disabled={busy} className="text-[11px] text-pb-accent hover:underline disabled:opacity-50"
          onClick={() => onSave(f)}>{busy ? '...' : 'Save'}</button>
        <button disabled={busy} className="ml-2 text-[11px] text-pb-faint hover:text-pb-text"
          onClick={onCancel}>Cancel</button>
      </td>
    </tr>
  )
}

function ClubDetail({ club, onToggleContact, onToggleEmailed, onToggleExcluded, onSaveUtm, onSaveSales, onRefresh }) {
  const contacts = club.contacts || []
  const assocs = club.associations
  const [utm, setUtm] = useState(club.utm_code || '')
  const [utmBusy, setUtmBusy] = useState(false)
  const [editId, setEditId] = useState(null)
  const [adding, setAdding] = useState(false)
  const [cbusy, setCbusy] = useState(false)
  const [cerr, setCerr] = useState('')
  const saveUtm = async () => {
    setUtmBusy(true)
    try { await onSaveUtm(club.id, utm) } finally { setUtmBusy(false) }
  }
  const saveContact = async (id, vals) => {
    setCbusy(true); setCerr('')
    try { await api.mktUpdateContact(id, vals); setEditId(null); onRefresh && onRefresh() }
    catch (e) { setCerr(e.message || 'Could not save the contact.') } finally { setCbusy(false) }
  }
  const createContact = async (vals) => {
    setCbusy(true); setCerr('')
    try { await api.mktAddContact(club.id, vals); setAdding(false); onRefresh && onRefresh() }
    catch (e) { setCerr(e.message || 'Could not add the contact.') } finally { setCbusy(false) }
  }
  const removeContact = async (id) => {
    if (!window.confirm('Remove this contact?')) return
    setCbusy(true); setCerr('')
    try { await api.mktDeleteContact(id); onRefresh && onRefresh() }
    catch (e) { setCerr(e.message || 'Could not remove the contact.') } finally { setCbusy(false) }
  }
  return (
    <div className="space-y-4">
      {/* Contacts — full width so long names/emails never collide with the facts column */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[11px] uppercase tracking-wide text-pb-faint">
            Contacts ({contacts.length}) · tick who to email
          </div>
          <button className="text-[11px] text-pb-accent hover:underline"
                  onClick={() => { setAdding(a => !a); setEditId(null) }}>
            {adding ? 'Cancel' : '+ Add contact'}
          </button>
        </div>
        {(contacts.length || adding) ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-pb-faint">
                <tr className="text-left">
                  <th className="font-normal pb-1 pr-2 w-6" />
                  <th className="font-normal pb-1 pr-3 whitespace-nowrap">Role</th>
                  <th className="font-normal pb-1 pr-3 whitespace-nowrap">Name</th>
                  <th className="font-normal pb-1 pr-3">Email</th>
                  <th className="font-normal pb-1 pr-3 whitespace-nowrap">Mobile</th>
                  <th className="font-normal pb-1 text-right whitespace-nowrap">Edit</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((ct) => {
                  if (editId === ct.id) {
                    return <ContactEditRow key={ct.id} init={ct} busy={cbusy}
                                           onCancel={() => setEditId(null)}
                                           onSave={(vals) => saveContact(ct.id, vals)} />
                  }
                  const canEmail = !!ct.email && ct.subscribed
                  return (
                    <tr key={ct.id} className="align-top border-t pb-hairline">
                      <td className="py-1 pr-2 w-6">
                        <input type="checkbox" checked={!!ct.selected} disabled={!canEmail}
                               title={canEmail ? 'Include in outreach' : 'No emailable address'}
                               onChange={(e) => onToggleContact(club.id, ct.id, e.target.checked)} />
                      </td>
                      <td className="py-1 pr-3 text-pb-faint whitespace-nowrap">{ct.role || '-'}</td>
                      <td className="py-1 pr-3 text-pb-text whitespace-nowrap">{ct.full_name || '-'}</td>
                      <td className="py-1 pr-3">
                        {ct.email
                          ? <a href={`mailto:${ct.email}`} className="text-pb-accent break-all">{ct.email}</a>
                          : <span className="text-pb-faint">-</span>}
                        {!ct.subscribed && <span className="ml-1 text-[10px] text-amber-300 whitespace-nowrap">unsub</span>}
                        {ct.exported && (
                          <span className="ml-1 text-[10px] text-sky-300 border border-sky-500/40 bg-sky-500/10 rounded px-1 whitespace-nowrap"
                                title="Already in BetterComms — a re-export will skip it (no duplicate)">
                            exported
                          </span>
                        )}
                      </td>
                      <td className="py-1 pr-3 text-pb-dim whitespace-nowrap">{ct.mobile || ''}</td>
                      <td className="py-1 text-right whitespace-nowrap">
                        <button className="text-[11px] text-pb-faint hover:text-pb-accent"
                                onClick={() => { setEditId(ct.id); setAdding(false) }}>edit</button>
                        <button className="ml-2 text-[11px] text-pb-faint hover:text-red-300"
                                title="Remove contact" onClick={() => removeContact(ct.id)}>✕</button>
                      </td>
                    </tr>
                  )
                })}
                {adding && <ContactEditRow init={{}} busy={cbusy}
                                           onCancel={() => setAdding(false)}
                                           onSave={createContact} />}
              </tbody>
            </table>
          </div>
        ) : <div className="text-pb-faint text-xs">No contacts stored.</div>}
        {cerr && <div className="text-red-300 text-[11px] mt-1">{cerr}</div>}
      </div>

      {/* Club facts (left) + sales pipeline / site visits (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs border-t pb-hairline pt-3">
        <div className="space-y-2">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-pb-faint mb-1">
              Associations {assocs === null ? '(not fetched yet)' : `(${(assocs || []).length})`}
            </div>
            {Array.isArray(assocs) && assocs.length ? (
              <ul className="text-pb-dim">
                {assocs.map((a, i) => (
                  <li key={i}>{a.name}{a.competition ? <span className="text-pb-faint"> — {a.competition}</span> : null}</li>
                ))}
              </ul>
            ) : <div className="text-pb-faint">{assocs === null ? 'Pending the association-enrichment pass.' : 'None found.'}</div>}
          </div>
          <div className="text-pb-dim space-y-1">
            <div><span className="text-pb-faint">Address: </span>
              {[club.address_line1, club.suburb, club.state, club.postcode].filter(Boolean).join(', ') || '-'}</div>
            <div><span className="text-pb-faint">Website: </span>
              {club.website_url
                ? <a href={club.website_url} target="_blank" rel="noreferrer" className="text-pb-accent break-all">{club.website_url}</a>
                : '-'}</div>
            <div className="break-all"><span className="text-pb-faint">PlayHQ code: </span>{club.playhq_id || '-'}
              <span className="text-pb-faint"> · GUID: </span><span className="font-mono text-[10px]">{club.grassroots_guid || '-'}</span></div>
            <div className="flex flex-wrap items-center gap-1 pt-1">
              <span className="text-pb-faint">UTM:</span>
              <input className={SELECT_CLS + ' w-56 font-mono'} value={utm}
                     placeholder={club.utm_code || 'utm code'}
                     onChange={(e) => setUtm(e.target.value)} />
              <button disabled={utmBusy || utm === (club.utm_code || '')}
                      className="px-2 py-0.5 rounded border pb-hairline text-[11px] text-pb-text hover:border-pb-accent disabled:opacity-40"
                      onClick={saveUtm}>{utmBusy ? '...' : 'Save'}</button>
              <span className="text-[10px] text-pb-faint" title="Blank resets to the default">(blank = default)</span>
            </div>
            <div><span className="text-pb-faint">Status: </span>{club.status || '-'}
              {club.is_customer && <span className="text-emerald-300"> · already a customer</span>}</div>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span>
                <span className="text-pb-faint">Emailed: </span>
                {club.emailed_at
                  ? <span className="text-amber-300">yes ({club.emailed_via || 'manual'})</span>
                  : <span className="text-pb-faint">no</span>}
              </span>
              <button
                className="px-2 py-0.5 rounded border pb-hairline text-[11px] text-pb-text hover:border-pb-accent"
                onClick={() => onToggleEmailed(club.id, !club.emailed_at)}>
                {club.emailed_at ? 'Unmark emailed' : 'Mark as emailed'}
              </button>
              <button
                className={'px-2 py-0.5 rounded border text-[11px] hover:opacity-80 '
                  + (club.excluded ? 'border-red-500/50 text-red-300 bg-red-500/10' : 'pb-hairline text-pb-text')}
                title="Excluded clubs are never exported, and any contacts already in BetterAdmin Comms are dropped from audiences"
                onClick={() => onToggleExcluded(club.id, !club.excluded)}>
                {club.excluded ? 'Excluded ✕ — click to include' : 'Exclude'}
              </button>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {onSaveSales && <SalesEditor key={club.id} club={club} onSave={onSaveSales} />}
          <VisitsPanel clubId={club.id} summary={club.visits} />
          <LoginIntentPanel clubId={club.id} summary={club.login_intent} isCustomer={club.is_customer} />
        </div>
      </div>
    </div>
  )
}

// Typeahead over the marketing directory, for mapping a UTM value to a club.
function ClubPicker({ onPick, placeholder = 'Search club to map…' }) {
  const [q, setQ] = useState('')
  const [opts, setOpts] = useState([])
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!q.trim()) { setOpts([]); setOpen(false); return }
    let alive = true
    const t = setTimeout(() => {
      api.mktClubs({ q, limit: 8 })
        .then(d => { if (alive) { setOpts(d.clubs || []); setOpen(true) } })
        .catch(() => {})
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [q])
  return (
    <div className="relative inline-block">
      <input className={SELECT_CLS + ' w-52'} placeholder={placeholder} value={q}
             onChange={e => setQ(e.target.value)} />
      {open && opts.length > 0 && (
        <div className="absolute z-30 mt-1 w-72 max-h-56 overflow-auto rounded border pb-hairline bg-pb-surface2 shadow-lg">
          {opts.map(o => (
            <button key={o.id}
                    className="block w-full text-left px-2 py-1 text-xs text-pb-text hover:bg-pb-accent/15"
                    onClick={() => { setOpen(false); setQ(''); onPick(o) }}>
              {o.name} <span className="text-pb-faint font-mono">{o.utm_code}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const UTM_STATUS = {
  auto:      { label: 'auto',      cls: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10' },
  mapped:    { label: 'mapped',    cls: 'text-violet-300 border-violet-500/40 bg-violet-500/10' },
  ignored:   { label: 'ignored',   cls: 'text-pb-faint border-pb-hairline' },
  unmatched: { label: 'unmatched', cls: 'text-amber-300 border-amber-500/40 bg-amber-500/10' },
}

// List every raw UTM value seen on a visit and let a super admin map the
// unmatched ones to a club (or mark noise as ignored). A campaign's utm_source
// isn't always the club's code, so exact matching can't catch everything.
function UtmMatchPanel() {
  const [rows, setRows] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('unmatched')
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api.mktUtmValues().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [])
  useEffect(() => { if (open && rows === null) load() }, [open, rows, load])

  const apply = async (utm_value, body) => {
    setBusy(utm_value)
    try {
      const res = await api.mktSetUtmAlias({ utm_value, ...body })
      setRows(rs => rs.map(r => r.utm_value === utm_value
        ? { ...r, status: res.status, club: res.club } : r))
    } catch (_) { /* ignore — row stays as-is */ } finally { setBusy('') }
  }

  const all = rows || []
  const counts = all.reduce((m, r) => ({ ...m, [r.status]: (m[r.status] || 0) + 1 }), {})
  const shown = filter === 'all' ? all : all.filter(r => r.status === filter)

  return (
    <section className={CARD}>
      <button className="flex items-center justify-between w-full"
              onClick={() => setOpen(o => !o)}>
        <span className={SECTION}>
          UTM matching{counts.unmatched ? ` · ${counts.unmatched} unmatched` : ''}
        </span>
        <span className="text-pb-faint text-xs">{open ? '▾ hide' : '▸ show'}</span>
      </button>
      {open && (
        <div className="mt-2">
          <p className="text-[11px] text-pb-faint mb-2">
            Each value a visit can be matched by — a utm_source / utm_id tag, or a
            club-looking page slug it landed on. Map the ones that belong to a club
            but don't match its code (e.g. a generic "willetton-cricket-club"), and
            ignore the noise.
          </p>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {['unmatched', 'mapped', 'ignored', 'auto', 'all'].map(k => (
              <button key={k}
                      className={'text-[11px] px-2 py-0.5 rounded border ' + (filter === k
                        ? 'border-pb-accent text-pb-accent' : 'pb-hairline text-pb-dim hover:text-pb-text')}
                      onClick={() => setFilter(k)}>
                {k}{k !== 'all' && counts[k] ? ` (${counts[k]})` : ''}
              </button>
            ))}
            <button className="text-[11px] text-pb-faint hover:text-pb-accent ml-auto" onClick={load}>
              Refresh
            </button>
          </div>
          {loading && rows === null ? (
            <div className="text-xs text-pb-dim">Loading…</div>
          ) : !shown.length ? (
            <div className="text-xs text-pb-faint">Nothing here.</div>
          ) : (
            <div className="overflow-x-auto rounded border pb-hairline">
              <table className="w-full text-xs">
                <thead className="bg-pb-surface2 text-pb-faint uppercase tracking-wide">
                  <tr>
                    <th className="text-left px-3 py-2">UTM value</th>
                    <th className="text-left px-3 py-2">Views</th>
                    <th className="text-left px-3 py-2">Status</th>
                    <th className="text-left px-3 py-2">Club / action</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map(r => {
                    const st = UTM_STATUS[r.status] || UTM_STATUS.unmatched
                    const working = busy === r.utm_value
                    return (
                      <tr key={r.utm_value} className="border-t pb-hairline align-top">
                        <td className="px-3 py-2 font-mono text-pb-text break-all">
                          {r.utm_value}
                          {r.sources?.length > 0 && (
                            <span className="ml-1.5 text-[9px] font-sans text-pb-faint uppercase tracking-wide">
                              {r.sources.join(' · ')}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-pb-dim">{r.views}</td>
                        <td className="px-3 py-2">
                          <span className={'text-[10px] border rounded px-1 ' + st.cls}>{st.label}</span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap items-center gap-2">
                            {r.club && <span className="text-pb-text">{r.club.name}</span>}
                            {working ? <span className="text-pb-faint">…</span> : (
                              <>
                                <ClubPicker onPick={(o) => apply(r.utm_value, { marketing_club_id: o.id })}
                                            placeholder={r.club ? 'Change club…' : 'Map to club…'} />
                                {r.status !== 'ignored' && (
                                  <button className="text-[11px] px-2 py-0.5 rounded border pb-hairline text-pb-dim hover:text-pb-text"
                                          onClick={() => apply(r.utm_value, { ignore: true })}>
                                    Ignore
                                  </button>
                                )}
                                {(r.status === 'mapped' || r.status === 'ignored') && (
                                  <button className="text-[11px] px-2 py-0.5 rounded border pb-hairline text-pb-dim hover:text-pb-text"
                                          onClick={() => apply(r.utm_value, {})}>
                                    Clear
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default function SuperMarketing() {
  const [stats, setStats] = useState(null)
  const [status, setStatus] = useState(null)
  const [clubs, setClubs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [page, setPage] = useState(0)
  const [assocOptions, setAssocOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState([])
  const PAGE = 100
  const [filters, setFilters] = useState({
    q: '', state: '', association: '', associations: [], countries: [],
    postcode_from: '', postcode_to: '',
    contact: '', person: '',
    // Tri-state directory filters: '' (off) | 'include' | 'exclude'.
    junior: '', carnival: '', school: '', rep: '', cricket_au: '',
    emailed: '', exported: '', suppressed: '', excluded: '',
    visited: false,
  })
  const [expanded, setExpanded] = useState(null)
  const [view, setView] = useState({ group: false, assocSort: 'asc', clubSort: 'asc' })
  // Export to BetterComms: default to the ticked ("who to email") contacts only.
  // Untick to push every subscribed, emailable contact in the filtered list.
  const [onlyTicked, setOnlyTicked] = useState(true)

  const loadStats = useCallback(() => {
    api.mktStats().then(setStats).catch(() => {})
    api.mktStatus().then(setStatus).catch(() => {})
  }, [])

  // Poll the crawl status every 12s so the page reflects running / waiting /
  // paused / complete without a manual refresh.
  useEffect(() => {
    const id = setInterval(() => { api.mktStatus().then(setStatus).catch(() => {}) }, 12000)
    return () => clearInterval(id)
  }, [])

  const loadClubs = useCallback(() => {
    setLoading(true)
    api.mktClubs({
      ...filters, limit: PAGE, offset: page * PAGE,
      group_by_association: view.group, assoc_sort: view.assocSort, club_sort: view.clubSort,
    })
      .then((d) => { setClubs(d.clubs); setTotal(d.total); setError('') })
      .catch((e) => setError(e.message || 'Could not load the directory.'))
      .finally(() => setLoading(false))
  }, [filters, page, view])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadClubs() }, [loadClubs])
  useEffect(() => { setPage(0) }, [filters, view])  // back to first page when filters or sort change
  useEffect(() => { api.mktAssociations().then(setAssocOptions).catch(() => {}) }, [])
  useEffect(() => { api.mktCountries().then(setCountryOptions).catch(() => {}) }, [])
  // Re-attach to an in-flight Twenty export if the page was reloaded mid-run.
  useEffect(() => {
    api.mktExportTwentyStatus().then((s) => {
      if (s && s.running) {
        setBusy('twenty')
        setMsg('Exporting to Twenty… this can take a few minutes for a large list. You can leave this page; the export keeps running.')
        pollTwentyExport().finally(() => setBusy(''))
      }
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runCrawl = async () => {
    setBusy('crawl'); setMsg('')
    try {
      await api.mktCrawl()
      setMsg('Crawl batch started in the background. Watch the status above — it is rate-limited, so progress is slow.')
      setTimeout(loadStats, 2000)  // let the first fetch land, then refresh the status pill
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const setCrawlPaused = async (paused) => {
    setBusy('control'); setMsg('')
    try {
      await api.mktCrawlControl(paused)
      setMsg(paused ? 'Crawler stopped. It will idle until you start it again.'
                    : 'Crawler started.')
      api.mktStatus().then(setStatus).catch(() => {})
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const exportComms = async () => {
    setBusy('export'); setMsg('')
    try {
      const r = await api.mktExportComms({ ...filters, selected_only: onlyTicked })
      let m = `Exported to ${r.org}: ${r.added} added, ${r.already_present} already there, ${r.already_suppressed} suppressed.`
      // Explain a 0-added result. Only excluded clubs are held back; otherwise
      // the eligible clubs just had no ticked, emailable contact.
      if (!r.added && r.clubs_eligible === 0 && r.clubs_matched > 0) {
        m += ` None of the ${r.clubs_matched} filtered club(s) were eligible`
        m += r.skipped_excluded ? ` (${r.skipped_excluded} excluded).` : '.'
        m += ' Excluded clubs are never exported.'
      } else if (!r.added && r.clubs_eligible > 0) {
        m += ` ${r.clubs_eligible} club(s) were eligible but had no ticked, emailable contact —`
        m += ' open a club and tick who to email.'
      }
      setMsg(m)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const formatTwentyResult = (r) => {
    const cl = (r.clubs_created || 0) + (r.clubs_updated || 0) + (r.clubs_adopted || 0)
    const pp = (r.people_created || 0) + (r.people_updated || 0) + (r.people_adopted || 0)
    let m = `Exported to Twenty: ${r.matched_clubs} club(s) matched, ${cl} club + ${pp} officer record(s) synced`
    m += (r.clubs_unchanged || r.people_unchanged) ? `, ${(r.clubs_unchanged || 0) + (r.people_unchanged || 0)} unchanged` : ''
    m += r.errors ? `. ${r.errors} club(s) errored (see logs).` : '.'
    return m
  }

  const formatEngagementResult = (r) =>
    `Refreshed engagement on ${r.refreshed || 0} club(s) in Twenty` + (r.errored ? `, ${r.errored} errored (see logs).` : '.')

  const formatLeadsTasksResult = (r) => {
    const leads = (r.leads_created || 0) + (r.leads_updated || 0) + (r.leads_adopted || 0)
    const tasks = (r.tasks_request || 0) + (r.tasks_trial_expiry || 0) + (r.tasks_renewal || 0)
    return `Twenty leads/tasks: scanned ${r.clubs_scanned || 0} exported club(s), `
      + `${r.leads_qualified || 0} qualified → ${leads} lead(s). Pending: `
      + `${r.requests_outstanding || 0} request(s), ${r.trials_in_window || 0} expiring trial(s), `
      + `${r.renewals_in_window || 0} renewal(s) → ${tasks} new task(s).`
      + ((r.leads_errored || r.tasks_errored) ? ' Some errored (see logs).' : '')
  }

  // Poll a background Twenty job's status endpoint until it finishes; surfaces
  // the result/error. Shared by export, engagement refresh and leads/tasks
  // refresh — all three run in the background (see marketing.py) since a full
  // pass over an exported-club list against Twenty's rate limit routinely
  // exceeds the nginx proxy timeout.
  const pollTwentyJob = async (statusFn, formatResult, { onDone } = {}) => {
    // ~20 min cap at 3s intervals — long jobs throttle through Twenty's rate limit.
    for (let i = 0; i < 400; i++) {
      await new Promise((res) => setTimeout(res, 3000))
      let s
      try {
        s = await statusFn()
      } catch { continue } // transient network/poll error — keep waiting
      if (s.running) continue
      if (s.error) { setError(s.error); return }
      if (s.result) { setMsg(formatResult(s.result)); onDone?.(); return }
      return // no result and not running — nothing to report
    }
    setMsg('Still running — check back shortly, then refresh the list.')
  }

  const exportTwenty = async () => {
    setBusy('twenty'); setMsg(''); setError('')
    try {
      const r = await api.mktExportTwenty({ ...filters })
      if (r.error) { setError(r.error); return }
      setMsg('Exporting to Twenty… this can take a few minutes for a large list. You can leave this page; the export keeps running.')
      await pollTwentyJob(api.mktExportTwentyStatus, formatTwentyResult, { onDone: loadClubs })
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const refreshTwentyEngagement = async () => {
    setBusy('twenty-refresh'); setMsg(''); setError('')
    try {
      const r = await api.mktRefreshTwentyEngagement()
      if (r.error) { setError(r.error); return }
      setMsg('Refreshing engagement scores in Twenty… this can take a while for a large list. You can leave this page.')
      await pollTwentyJob(api.mktRefreshTwentyEngagementStatus, formatEngagementResult)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const refreshTwentyLeadsTasks = async () => {
    setBusy('twenty-leads-tasks'); setMsg(''); setError('')
    try {
      const r = await api.mktRefreshTwentyLeadsTasks()
      if (r.error) { setError(r.error); return }
      setMsg('Refreshing Twenty leads/tasks… this can take a while for a large list. You can leave this page.')
      await pollTwentyJob(api.mktRefreshTwentyLeadsTasksStatus, formatLeadsTasksResult)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const bulkEmailed = async (value) => {
    if (!window.confirm(
      `${value ? 'Mark' : 'Unmark'} all ${total} club(s) in the current filtered list as `
      + `${value ? 'emailed' : 'not emailed'}?`)) return
    setBusy('bulk'); setMsg('')
    try {
      const r = await api.mktBulkEmailed(value, filters)
      setMsg(`${r.updated} club(s) marked ${value ? 'emailed' : 'not emailed'}.`)
      loadStats(); loadClubs()
    } catch (e) { setError(e.message || 'Could not update.') } finally { setBusy('') }
  }

  const bulkExcluded = async (value) => {
    if (!window.confirm(
      `${value ? 'Exclude' : 'Include'} all ${total} club(s) in the current filtered list`
      + `${value ? ' from outreach' : ''}?`)) return
    setBusy('bulk'); setMsg('')
    try {
      const r = await api.mktBulkExcluded(value, filters)
      setMsg(`${r.updated} club(s) ${value ? 'excluded' : 'included'}.`)
      loadStats(); loadClubs()
    } catch (e) { setError(e.message || 'Could not update.') } finally { setBusy('') }
  }

  const toggleContact = async (clubId, contactId, selected) => {
    // optimistic — update the contact in place, refresh the stat tile after
    setClubs(cs => cs.map(c => c.id !== clubId ? c : {
      ...c, contacts: c.contacts.map(ct => ct.id === contactId ? { ...ct, selected } : ct),
    }))
    try {
      await api.mktSetContactSelected(contactId, selected)
      loadStats()
    } catch (e) {
      setError(e.message || 'Could not update the selection.')
      loadClubs()  // revert to server truth
    }
  }

  const toggleEmailed = async (clubId, emailed) => {
    setClubs(cs => cs.map(c => c.id !== clubId ? c : {
      ...c, emailed_at: emailed ? new Date().toISOString() : null,
      emailed_via: emailed ? 'manual' : null,
    }))
    try {
      await api.mktSetClubEmailed(clubId, emailed)
      loadStats()
    } catch (e) {
      setError(e.message || 'Could not update.')
      loadClubs()
    }
  }

  const toggleExcluded = async (clubId, excluded) => {
    setClubs(cs => cs.map(c => c.id !== clubId ? c : { ...c, excluded }))
    try {
      await api.mktSetClubExcluded(clubId, excluded)
      loadStats()
    } catch (e) {
      setError(e.message || 'Could not update.')
      loadClubs()
    }
  }

  const resolveSelectedAssociations = async () => {
    setBusy('resolve'); setMsg('')
    const byName = Object.fromEntries(assocOptions.map(o => [o.name, o.id]))
    let done = 0
    try {
      for (const name of filters.associations) {
        const id = byName[name]
        if (!id) continue
        await api.mktResolveAssociation(id, name)
        done += 1
      }
      setMsg(`Fetching ${done} roster(s) in the background — this takes up to a minute or two each. Click Refresh to see them fill in.`)
      // Give the background resolve(s) time, then refresh the view + counts.
      setTimeout(() => { loadStats(); loadClubs(); api.mktAssociations().then(setAssocOptions).catch(() => {}) }, 60000)
    } catch (e) { setError(e.message || 'Could not start the roster fetch.') } finally { setBusy('') }
  }

  const saveAssocShort = async (id, short) => {
    try {
      const r = await api.mktSetAssocShortcode(id, short)
      setAssocOptions(opts => opts.map(o => o.id === id ? { ...o, short: r.short } : o))
    } catch (e) { setError(e.message || 'Could not update the short code.') }
  }

  const saveUtm = async (clubId, utm) => {
    try {
      const r = await api.mktSetClubUtm(clubId, utm)
      setClubs(cs => cs.map(c => c.id === clubId ? { ...c, utm_code: r.utm_code } : c))
      setMsg(`UTM updated to ${r.utm_code}`)
    } catch (e) { setError(e.message || 'Could not update the UTM.') }
  }

  const saveSales = async (clubId, body) => {
    try {
      const r = await api.mktSetClubSales(clubId, body)
      setClubs(cs => cs.map(c => c.id === clubId ? {
        ...c,
        trial_modules: r.trial_modules,
        requested_trial_modules: r.requested_trial_modules,
        demo_status: r.demo_status,
        not_interested: r.not_interested,
      } : c))
      setMsg('Sales state saved.')
    } catch (e) { setError(e.message || 'Could not save the sales state.') }
  }

  const syncSuppressions = async () => {
    setBusy('supp'); setMsg('')
    try {
      const r = await api.mktSyncSuppressions()
      let m = `Synced ${r.suppressed} suppression(s) back to the directory.`
      if (r.export_cleared) m += ` ${r.export_cleared} contact(s) deleted from BetterComms reset to not-exported.`
      setMsg(m)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-3">
          <h1 className="text-xl font-semibold text-pb-text">Club directory</h1>
          <p className="text-xs text-pb-dim mt-0.5">
            Every Australian cricket club from the PlayHQ public directory, for
            BetterCricket outreach. Click a club to see its committee and tick which
            contacts to email; "Export to BetterComms" pushes the ticked
            contacts (within the current filter) into the send pipeline.
          </p>
        </div>

        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-3">
            <Stat label="Clubs" value={stats.clubs} />
            <Stat label="Contacts" value={stats.contacts} />
            <Stat label="To email" value={stats.selected_contacts} />
            <Stat label="With email" value={stats.clubs_with_email} />
            <Stat label="Emailed" value={stats.emailed} />
            <Stat label="Visited site" value={stats.visited} />
            <Stat label="Wants in (tried login)" value={stats.login_intent_not_customer} />
            <Stat label="Assoc. linked" value={stats.associations_fetched} />
            <Stat label="Assoc. pending" value={stats.associations_pending} />
            <Stat label="Associations" value={stats.distinct_associations} />
            <Stat label="Assoc. swept"
                  value={stats.associations_registry != null
                    ? `${stats.associations_resolved ?? 0}/${stats.associations_registry}` : '-'} />
            <Stat label="Already ours" value={stats.already_customers} />
          </div>
        )}

        <CrawlStatus status={status} />

        {/* Crawler controls — sit directly under the status pill */}
        <div className="flex flex-wrap items-center gap-2 mb-2.5">
          <button className={BTN_ACCENT} disabled={busy === 'crawl' || status?.paused} onClick={runCrawl}>
            {busy === 'crawl' ? 'Starting...' : 'Run crawl batch'}
          </button>
          {status?.paused ? (
            <button className="px-3 py-1.5 rounded text-xs font-semibold border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50"
                    disabled={busy === 'control'} onClick={() => setCrawlPaused(false)}>
              {busy === 'control' ? '...' : 'Start crawling'}
            </button>
          ) : (
            <button className="px-3 py-1.5 rounded text-xs font-semibold border border-red-500/40 bg-red-500/15 text-red-300 hover:bg-red-500/25 disabled:opacity-50"
                    disabled={busy === 'control'} onClick={() => setCrawlPaused(true)}>
              {busy === 'control' ? '...' : 'Stop crawling'}
            </button>
          )}
          <button className={BTN} onClick={() => { loadStats(); loadClubs() }}>Refresh</button>
        </div>

        {/* ── Filter card ─────────────────────────────────────────────── */}
        <section className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <span className={SECTION}>Filter clubs</span>
            {(filters.q || filters.association || filters.associations.length || filters.countries.length
              || filters.state
              || filters.postcode_from || filters.postcode_to || filters.contact || filters.person
              || filters.visited || MODE_FILTERS.some(mf => filters[mf.key])) && (
              <button className="text-[11px] text-pb-faint hover:text-pb-accent"
                      onClick={() => setFilters({ q: '', state: '', association: '', associations: [],
                                                  countries: [],
                                                  postcode_from: '', postcode_to: '', contact: '',
                                                  person: '', junior: '', carnival: '', school: '',
                                                  rep: '', cricket_au: '', emailed: '', exported: '',
                                                  suppressed: '', excluded: '', visited: false })}>
                Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-3 gap-y-2">
            <Field label="Search">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Club or association..."
                value={filters.q}
                onChange={(e) => setFilters(f => ({ ...f, q: e.target.value }))}
              />
            </Field>
            <Field label="Association">
              <div className="flex items-center gap-2">
                <AssocMultiSelect
                  options={assocOptions}
                  selected={filters.associations}
                  onChange={(a) => setFilters(f => ({ ...f, associations: a }))}
                  onSaveShort={saveAssocShort}
                />
                {filters.associations.length > 0 && (
                  <button className={BTN + ' whitespace-nowrap'} disabled={busy === 'resolve'}
                          onClick={resolveSelectedAssociations}
                          title="Fetch the complete club roster for the selected association(s) from PlayHQ">
                    {busy === 'resolve' ? 'Fetching…' : `Fetch roster${filters.associations.length > 1 ? 's' : ''}`}
                  </button>
                )}
              </div>
            </Field>
            <Field label="Country">
              <CountryMultiSelect
                options={countryOptions}
                selected={filters.countries}
                onChange={(c) => setFilters(f => ({ ...f, countries: c }))}
              />
            </Field>
            <Field label="Association contains">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Name or short code..."
                value={filters.association}
                onChange={(e) => setFilters(f => ({ ...f, association: e.target.value }))}
              />
            </Field>
            <Field label="State">
              <select className={SELECT_CLS + ' w-full'} value={filters.state}
                      onChange={(e) => setFilters(f => ({ ...f, state: e.target.value }))}>
                <option value="">All states</option>
                {STATES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Postcode range">
              <div className="flex items-center gap-1">
                <input className={SELECT_CLS + ' w-full'} placeholder="from" inputMode="numeric"
                       value={filters.postcode_from}
                       onChange={(e) => setFilters(f => ({ ...f, postcode_from: e.target.value }))} />
                <span className="text-pb-faint">–</span>
                <input className={SELECT_CLS + ' w-full'} placeholder="to" inputMode="numeric"
                       value={filters.postcode_to}
                       onChange={(e) => setFilters(f => ({ ...f, postcode_to: e.target.value }))} />
              </div>
            </Field>
            <Field label="Contacts">
              <select className={SELECT_CLS + ' w-full'} value={filters.contact}
                      onChange={(e) => setFilters(f => ({ ...f, contact: e.target.value }))}>
                <option value="">Any contacts</option>
                <option value="any_email">Has an email (any)</option>
                <option value="named_email">Has a named email</option>
                <option value="pst">Has Pres + Sec + Treas (named, emailed)</option>
              </select>
            </Field>
            <Field label="Person name">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Person name contains..."
                value={filters.person}
                onChange={(e) => setFilters(f => ({ ...f, person: e.target.value }))}
              />
            </Field>
          </div>
          <div className="mt-2.5 pt-2.5 border-t pb-hairline">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] uppercase tracking-wide text-pb-faint">Filters</span>
              <span className="text-[10px] text-pb-faintest">click to cycle: off → <span className="text-red-300">exclude</span> → <span className="text-emerald-300">include</span></span>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {MODE_FILTERS.map(mf => (
                <FilterChip key={mf.key} label={mf.label} title={mf.title}
                  mode={filters[mf.key]}
                  onChange={(v) => setFilters(f => ({ ...f, [mf.key]: v }))} />
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 mt-2.5 pt-2.5 border-t pb-hairline">
            <span className="text-[10px] uppercase tracking-wide text-pb-faint">Show only</span>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim"
                   title="Only clubs where someone has visited the public site from a link tagged with the club's UTM code">
              <input type="checkbox" checked={filters.visited}
                     onChange={(e) => setFilters(f => ({ ...f, visited: e.target.checked }))} />
              Visited the site (via their UTM)
            </label>
          </div>
        </section>

        {/* ── Actions card — everything here acts on the filtered list ─── */}
        <section className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <span className={SECTION}>Actions on the filtered list</span>
            <span className="text-[11px] text-pb-faint">{total} matching club(s)</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a className={BTN} href={api.mktExportCsvUrl(filters)} target="_blank" rel="noreferrer">
              Download CSV
            </a>
            <button className={BTN} disabled={busy === 'export'} onClick={exportComms}>
              {busy === 'export' ? 'Exporting...' : 'Export to BetterComms'}
            </button>
            <label className="flex items-center gap-1.5 text-[11px] text-pb-faint cursor-pointer select-none"
                   title="On: only the contacts ticked 'who to email' per club (office bearers by default). Off: every subscribed, emailable contact in the filtered list.">
              <input type="checkbox" className="accent-pb-accent" checked={onlyTicked}
                     onChange={e => setOnlyTicked(e.target.checked)} />
              Only ticked contacts
            </label>
            <button className={BTN} disabled={busy === 'twenty'} onClick={exportTwenty}
                    title="Push the currently-filtered clubs and their officers into the Twenty CRM (idempotent — re-running skips unchanged records)">
              {busy === 'twenty' ? 'Exporting...' : 'Export to Twenty'}
            </button>
            <button className={BTN} disabled={busy === 'twenty-refresh'} onClick={refreshTwentyEngagement}
                    title="Recompute the engagement score for every club already in Twenty from the latest usage breadcrumbs (runs daily too)">
              {busy === 'twenty-refresh' ? 'Refreshing...' : 'Refresh Twenty scores'}
            </button>
            <button className={BTN} disabled={busy === 'twenty-leads-tasks'} onClick={refreshTwentyLeadsTasks}
                    title="Seed/refresh Leads from telemetry and raise follow-up Tasks (module requests, expiring trials, upcoming renewals) in Twenty (runs daily too)">
              {busy === 'twenty-leads-tasks' ? 'Refreshing...' : 'Refresh Twenty leads/tasks'}
            </button>
            <button className={BTN} disabled={busy === 'supp'} onClick={syncSuppressions}>
              {busy === 'supp' ? 'Syncing...' : 'Sync suppressions'}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-2.5 pt-2.5 border-t pb-hairline">
            <span className="text-[10px] uppercase tracking-wide text-pb-faint mr-1">Bulk update</span>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkEmailed(true)}>
              Mark all emailed
            </button>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkEmailed(false)}>
              Unmark all emailed
            </button>
            <span className="text-pb-faint px-1">·</span>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkExcluded(true)}>
              Exclude all
            </button>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkExcluded(false)}>
              Include all
            </button>
          </div>
        </section>

        <UtmMatchPanel />

        {msg && <div className="mb-3 text-xs text-accent border border-accent/40 bg-accent/10 rounded px-3 py-2">{msg}</div>}
        {error && <div className="mb-3 text-xs text-red-300 border border-red-500/40 bg-red-500/10 rounded px-3 py-2">{error}</div>}

        {/* ── Results toolbar: grouping/sort on the left, pager on the right ── */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <div className="flex flex-wrap items-center gap-4">
            <span className={SECTION}>View</span>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={view.group}
                     onChange={(e) => setView(v => ({ ...v, group: e.target.checked }))} />
              Group by association
            </label>
            {view.group && (
              <div className="flex items-center gap-1 text-xs text-pb-dim">
                <span>Assoc.</span>
                <select className={SELECT_CLS} value={view.assocSort}
                        onChange={(e) => setView(v => ({ ...v, assocSort: e.target.value }))}>
                  <option value="asc">A → Z</option>
                  <option value="desc">Z → A</option>
                </select>
              </div>
            )}
            <div className="flex items-center gap-1 text-xs text-pb-dim">
              <span>Clubs</span>
              <select className={SELECT_CLS} value={view.clubSort}
                      onChange={(e) => setView(v => ({ ...v, clubSort: e.target.value }))}>
                <option value="asc">A → Z</option>
                <option value="desc">Z → A</option>
              </select>
            </div>
          </div>
        </div>

        <Pager total={total} page={page} pageSize={PAGE} onPage={setPage} loading={loading} />

        {loading ? (
          <div className="text-sm text-pb-dim">Loading...</div>
        ) : (
          <div className="overflow-x-auto rounded-lg border pb-hairline">
            <table className="w-full text-xs">
              <thead className="bg-pb-surface2 text-pb-faint uppercase tracking-wide">
                <tr>
                  <th className="text-left px-3 py-2">Club</th>
                  <th className="text-left px-3 py-2">Contact</th>
                  <th className="text-left px-3 py-2">Association</th>
                  <th className="text-left px-3 py-2">Location</th>
                  <th className="text-left px-3 py-2">PlayHQ ID</th>
                </tr>
              </thead>
              <tbody>
                {clubs.map((c, idx) => {
                  const top = c.contacts && c.contacts[0]
                  const more = (c.contacts?.length || 0) - 1
                  const isOpen = expanded === c.id
                  // When grouping, drop an association header row each time the
                  // association name changes from the club above it.
                  const groupName = c.association_name || 'Unassigned'
                  const prevName = idx > 0 ? (clubs[idx - 1].association_name || 'Unassigned') : null
                  const showHeader = view.group && groupName !== prevName
                  const exportedCount = (c.contacts || []).filter(ct => ct.exported).length
                  return [
                    showHeader && (
                      <tr key={c.id + '-h'} className="bg-pb-surface2/70 border-t-2 border-pb-accent/30">
                        <td colSpan={5} className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-pb-accent">
                          {groupName}
                        </td>
                      </tr>
                    ),
                    <tr key={c.id} className="border-t pb-hairline align-top">
                      <td className="px-3 py-2">
                        <button
                          className="font-medium text-pb-text flex items-center gap-1.5 text-left hover:text-pb-accent"
                          onClick={() => setExpanded(isOpen ? null : c.id)}>
                          <span className="text-pb-faint">{isOpen ? '▾' : '▸'}</span>
                          {c.name}
                          {c.is_customer && <span className="text-[10px] text-emerald-300 border border-emerald-500/40 rounded px-1">customer</span>}
                          {c.emailed_at && (
                            <span className="text-[10px] text-amber-300 border border-amber-500/40 rounded px-1"
                                  title={`Emailed via ${c.emailed_via || 'manual'}`}>
                              emailed{c.emailed_via === 'campaign' ? ' (campaign)' : ''}
                            </span>
                          )}
                          {c.excluded && (
                            <span className="text-[10px] text-red-300 border border-red-500/40 rounded px-1"
                                  title="Excluded from all outreach">excluded</span>
                          )}
                          {c.visits && (
                            <span className="text-[10px] text-violet-300 border border-violet-500/40 bg-violet-500/10 rounded px-1"
                                  title={`${c.visits.views} view(s) from ${c.visits.visitors} visitor(s)`
                                    + (c.visits.last_seen ? ` · last ${fmtWhen(c.visits.last_seen)}` : '')}>
                              visited{c.visits.views > 1 ? ` ×${c.visits.views}` : ''}
                            </span>
                          )}
                          {c.login_intent && (
                            <span className={'text-[10px] rounded px-1 border '
                              + (c.is_customer
                                ? 'text-pb-faint border-pb-hairline'
                                : 'text-amber-300 border-amber-500/40 bg-amber-500/10')}
                                  title={`${c.login_intent.visitors} visitor(s) browsed this club's pages then hit /login`
                                    + (c.login_intent.last_seen ? ` · last ${fmtWhen(c.login_intent.last_seen)}` : '')
                                    + (c.is_customer ? '' : ' — not a customer, likely wants to join')}>
                              {c.is_customer ? 'tried login' : '🔑 wants in'}
                            </span>
                          )}
                          {exportedCount > 0 && (
                            <span className="text-[10px] text-sky-300 border border-sky-500/40 bg-sky-500/10 rounded px-1"
                                  title={`${exportedCount} contact(s) already in BetterComms`}>
                              {exportedCount} exported
                            </span>
                          )}
                        </button>
                        {c.website_url && (
                          <a href={c.website_url} target="_blank" rel="noreferrer" className="text-[11px] text-pb-dim hover:text-pb-accent block">
                            {c.website_url.replace(/^https?:\/\//, '')}
                          </a>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {top ? (
                          <div>
                            {top.role && <span className="text-pb-faint">{top.role}: </span>}
                            {top.email && <a href={`mailto:${top.email}`} className="text-pb-accent">{top.email}</a>}
                            {top.mobile && <div className="text-pb-dim">{top.mobile}</div>}
                            {!top.subscribed && <span className="text-[10px] text-amber-300">unsubscribed</span>}
                            {more > 0 && (
                              <button className="text-[11px] text-pb-faint hover:text-pb-accent"
                                      onClick={() => setExpanded(isOpen ? null : c.id)}>
                                +{more} more
                              </button>
                            )}
                          </div>
                        ) : <span className="text-pb-faint">-</span>}
                      </td>
                      <td className="px-3 py-2 text-pb-dim">
                        {c.association_name || (c.associations === null ? <span className="text-pb-faint">pending</span> : '-')}
                        {Array.isArray(c.associations) && c.associations.length > 1 && (
                          <span className="text-pb-faint"> +{c.associations.length - 1}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-pb-dim">
                        {[c.suburb, c.state].filter(Boolean).join(', ')}
                        {c.postcode ? ` ${c.postcode}` : ''}
                      </td>
                      <td className="px-3 py-2 text-pb-faint font-mono text-[10px]">{c.playhq_id || '-'}</td>
                    </tr>,
                    isOpen && (
                      <tr key={c.id + '-d'} className="bg-pb-surface2/40">
                        <td colSpan={5} className="px-4 py-3">
                          <ClubDetail club={c} onToggleContact={toggleContact}
                                      onToggleEmailed={toggleEmailed}
                                      onToggleExcluded={toggleExcluded}
                                      onSaveUtm={saveUtm} onSaveSales={saveSales}
                                      onRefresh={() => { loadClubs(); loadStats() }} />
                        </td>
                      </tr>
                    ),
                  ]
                })}
                {!clubs.length && (
                  <tr><td colSpan={5} className="px-3 py-6 text-center text-pb-faint">
                    No clubs yet. Run a crawl batch to start collecting.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {!loading && total > PAGE && (
          <Pager total={total} page={page} pageSize={PAGE} onPage={setPage} loading={loading} />
        )}
      </div>
    </AdminLayout>
  )
}
