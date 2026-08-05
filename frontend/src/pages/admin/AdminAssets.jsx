import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { FilterPill } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'
import Calendar from '../../components/admin/clubmanager/Calendar'
import DateTimePicker from '../../components/admin/crm/DateTimePicker'
import { PersonPicker } from '../../components/admin/clubmanager/pickers'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const FACILITY_TYPES = ['ground', 'clubhouse', 'nets', 'scoreboard', 'canteen', 'storage', 'other']
const ASSET_CATEGORIES = ['equipment', 'technology', 'furniture', 'ground_maintenance', 'safety', 'other']
const ASSET_CONDITIONS = ['excellent', 'good', 'fair', 'poor', 'unserviceable']
const ASSET_STATUSES = ['in_service', 'in_repair', 'retired', 'disposed']
const ACCENT = '#8b7cf6'
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

const isoToLocal = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
const fmtTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  let h = d.getHours()
  const m = d.getMinutes()
  const ap = h < 12 ? 'am' : 'pm'
  h = h % 12 || 12
  return `${h}:${String(m).padStart(2, '0')} ${ap}`
}
const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '')

function TabBar({ tab, setTab }) {
  const tabs = [['facilities', 'Facilities'], ['bookings', 'Bookings'], ['assets', 'Assets']]
  return (
    <div className="flex flex-wrap gap-1 mb-5">
      {tabs.map(([k, l]) => (
        <FilterPill key={k} active={tab === k} onClick={() => setTab(k)}>{l}</FilterPill>
      ))}
    </div>
  )
}

// ── Maintenance log (shared by Facilities and Assets) ───────────────────────
function MaintenanceLogPanel({ subjectType, subjectId }) {
  const toast = useToast()
  const [logs, setLogs] = useState(null)
  const [form, setForm] = useState({ description: '', performed_at: new Date().toISOString().slice(0, 10), cost: '', performed_by: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.assetsListMaintenanceLogs(subjectType, subjectId).then(d => setLogs(d.logs || [])).catch(e => toast.error(e.message))
  }, [subjectType, subjectId, toast])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.description.trim()) return
    setBusy(true)
    try {
      await api.assetsCreateMaintenanceLog({
        subject_type: subjectType, subject_id: subjectId, description: form.description,
        performed_at: form.performed_at || null, cost: form.cost ? Number(form.cost) : null, performed_by: form.performed_by || null,
      })
      setForm({ description: '', performed_at: new Date().toISOString().slice(0, 10), cost: '', performed_by: '' })
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(id) {
    try { await api.assetsDeleteMaintenanceLog(id); load() } catch (e) { toast.error(e.message) }
  }

  return (
    <div className="mt-2 pt-2 border-t pb-hairline-t">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">MAINTENANCE / SERVICE HISTORY</div>
      {logs === null ? <PbSpinner message="Loading…" /> : (
        <div className="space-y-1 mb-2">
          {logs.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No history yet.</div>}
          {logs.map(l => (
            <div key={l.id} className="flex items-center justify-between font-mono text-[10px] text-pb-dim">
              <span>{l.performed_at} — {l.description}{l.cost ? ` ($${l.cost})` : ''}{l.performed_by ? ` · ${l.performed_by}` : ''}</span>
              <button onClick={() => remove(l.id)} className="text-pb-faintest hover:text-pb-red">✕</button>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <input type="date" className={`${inp} w-36`} value={form.performed_at} onChange={e => setForm(f => ({ ...f, performed_at: e.target.value }))} />
        <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Description" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        <input type="number" step="0.01" className={`${inp} w-24`} placeholder="Cost $" value={form.cost} onChange={e => setForm(f => ({ ...f, cost: e.target.value }))} />
        <input className={`${inp} w-32`} placeholder="Performed by" value={form.performed_by} onChange={e => setForm(f => ({ ...f, performed_by: e.target.value }))} />
        <button onClick={submit} disabled={busy || !form.description.trim()} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text">Log</button>
      </div>
    </div>
  )
}

// ── Facilities tab ───────────────────────────────────────────────────────────
function FacilityCard({ facility, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  async function archive() {
    if (!confirm(`Archive "${facility.name}"?`)) return
    try { await api.assetsDeleteFacility(facility.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{facility.name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">{label(facility.facility_type)}{facility.key_location ? ` · Key: ${facility.key_location}` : ''}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span onClick={(e) => { e.stopPropagation(); archive() }} className="font-mono text-[10px] text-pb-faintest hover:text-pb-red">✕</span>
          <span className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>
      {expanded && (
        <div className="border-t pb-hairline-t px-4 py-3">
          {facility.description && <div className="text-pb-faint text-[12px] mb-2">{facility.description}</div>}
          <MaintenanceLogPanel subjectType="facility" subjectId={facility.id} />
        </div>
      )}
    </div>
  )
}

function FacilitiesTab({ onFacilitiesChanged }) {
  const toast = useToast()
  const [facilities, setFacilities] = useState(null)
  const [form, setForm] = useState({ name: '', facility_type: 'other', description: '', key_location: '' })
  const [busy, setBusy] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [q, setQ] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const load = useCallback(() => {
    api.assetsListFacilities().then(d => { setFacilities(d.facilities || []); onFacilitiesChanged && onFacilitiesChanged() }).catch(e => toast.error(e.message))
  }, [toast, onFacilitiesChanged])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.assetsCreateFacility(form)
      setForm({ name: '', facility_type: 'other', description: '', key_location: '' })
      setShowForm(false)
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const filtered = useMemo(() => {
    if (!facilities) return []
    const n = q.trim().toLowerCase()
    return facilities.filter(f =>
      (!n || (f.name || '').toLowerCase().includes(n)) &&
      (!typeFilter || f.facility_type === typeFilter))
  }, [facilities, q, typeFilter])

  if (facilities === null) return <PbSpinner message="Loading facilities…" />
  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-2">
        <div className="font-mono text-[11px] text-pb-faint">{facilities.length} {facilities.length === 1 ? 'facility' : 'facilities'}</div>
        <button onClick={() => setShowForm(s => !s)}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {showForm ? 'Close' : '+ Add new facility'}
        </button>
      </div>

      {showForm && (
        <div className="pb-card p-4 mb-4">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW FACILITY</div>
          <div className="flex flex-wrap gap-2">
            <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Name (e.g. Main Oval, Clubhouse)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <select className={`${inp} w-40`} value={form.facility_type} onChange={e => setForm(f => ({ ...f, facility_type: e.target.value }))}>
              {FACILITY_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
            </select>
            <input className={`${inp} w-40`} placeholder="Key location" value={form.key_location} onChange={e => setForm(f => ({ ...f, key_location: e.target.value }))} />
            <button onClick={submit} disabled={busy || !form.name.trim()}
              className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
              {busy ? 'Adding…' : '+ Facility'}
            </button>
          </div>
          <input className={`${inp} mt-2`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        </div>
      )}

      <div className="pb-card p-3 mb-4 flex flex-wrap gap-2 items-center">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Search by name…" value={q} onChange={e => setQ(e.target.value)} />
        <select className={`${inp} w-44`} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {FACILITY_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
        </select>
      </div>

      {filtered.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">{facilities.length === 0 ? 'No facilities yet.' : 'No facilities match.'}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map(f => <FacilityCard key={f.id} facility={f} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

// ── Bookings tab ──────────────────────────────────────────────────────────────
function BookingForm({ facilities, members, initial, onCancel, onSaved }) {
  const toast = useToast()
  const blank = { facility_id: '', title: '', starts_at: '', ends_at: '', contact_name: '', contact_email: '', contact_mobile: '', owner_member_id: null, owner_name: '', notes: '' }
  const [form, setForm] = useState(() => initial ? {
    facility_id: initial.facility_id || '',
    title: initial.title || '',
    starts_at: isoToLocal(initial.starts_at),
    ends_at: isoToLocal(initial.ends_at),
    contact_name: initial.contact_name || '',
    contact_email: initial.contact_email || '',
    contact_mobile: initial.contact_mobile || '',
    owner_member_id: initial.owner_member_id || null,
    owner_name: initial.owner_name || '',
    notes: initial.notes || '',
  } : blank)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit() {
    if (!form.facility_id || !form.title.trim() || !form.starts_at) return
    setBusy(true)
    try {
      const payload = {
        facility_id: form.facility_id,
        title: form.title,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        contact_name: form.contact_name || null,
        contact_email: form.contact_email || null,
        contact_mobile: form.contact_mobile || null,
        owner_member_id: form.owner_member_id || null,
        owner_name: form.owner_name || null,
        notes: form.notes || null,
      }
      if (initial) await api.assetsUpdateBooking(initial.id, payload)
      else await api.assetsCreateBooking(payload)
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">{initial ? 'EDIT BOOKING' : 'NEW BOOKING'}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">FACILITY</label>
          <select className={inp} value={form.facility_id} onChange={e => set('facility_id', e.target.value)}>
            <option value="">Facility…</option>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">TITLE</label>
          <input className={inp} placeholder="e.g. Junior training, Private hire" value={form.title} onChange={e => set('title', e.target.value)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">STARTS</label>
          <DateTimePicker value={form.starts_at} onChange={v => set('starts_at', v)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">ENDS (may span days)</label>
          <DateTimePicker value={form.ends_at} onChange={v => set('ends_at', v)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">BOOKING CONTACT NAME</label>
          <input className={inp} placeholder="Who's hiring / booking" value={form.contact_name} onChange={e => set('contact_name', e.target.value)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">CONTACT EMAIL</label>
          <input className={inp} placeholder="Email" value={form.contact_email} onChange={e => set('contact_email', e.target.value)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">CONTACT MOBILE</label>
          <input className={inp} placeholder="Mobile" value={form.contact_mobile} onChange={e => set('contact_mobile', e.target.value)} />
        </div>
        <div>
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">BOOKING OWNER (club member)</label>
          <PersonPicker members={members} memberId={form.owner_member_id} name={form.owner_name}
            onChange={({ member_id, name }) => setForm(f => ({ ...f, owner_member_id: member_id, owner_name: name || '' }))} />
        </div>
        <div className="md:col-span-2">
          <label className="font-mono text-[9px] tracking-wide2 text-pb-faintest block mb-1">NOTES</label>
          <input className={inp} placeholder="Notes (optional)" value={form.notes} onChange={e => set('notes', e.target.value)} />
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={submit} disabled={busy || !form.facility_id || !form.title.trim() || !form.starts_at}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Saving…' : (initial ? 'Save booking' : '+ Booking')}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
      </div>
    </div>
  )
}

function BookingsTab({ facilities, members }) {
  const toast = useToast()
  const [bookings, setBookings] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [view, setView] = useState('calendar')
  const [q, setQ] = useState('')
  const [facilityFilter, setFacilityFilter] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const load = useCallback(() => {
    api.assetsListBookings().then(d => setBookings(d.bookings || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  const facilityName = useCallback((id) => facilities.find(f => f.id === id)?.name || '—', [facilities])
  const ownerNameOf = useCallback((b) => members.find(m => m.member_id === b.owner_member_id)?.full_name || b.owner_name || '', [members])

  const owners = useMemo(() => {
    if (!bookings) return []
    const set = new Set()
    bookings.forEach(b => { const o = ownerNameOf(b); if (o) set.add(o) })
    return Array.from(set).sort()
  }, [bookings, ownerNameOf])

  const filtered = useMemo(() => {
    if (!bookings) return []
    const n = q.trim().toLowerCase()
    const fromMs = fromDate ? new Date(fromDate + 'T00:00').getTime() : null
    const toMs = toDate ? new Date(toDate + 'T23:59:59').getTime() : null
    return bookings.filter(b => {
      if (n && !((b.title || '').toLowerCase().includes(n) || (b.contact_name || '').toLowerCase().includes(n))) return false
      if (facilityFilter && b.facility_id !== facilityFilter) return false
      if (ownerFilter && ownerNameOf(b) !== ownerFilter) return false
      if (fromMs != null || toMs != null) {
        const s = new Date(b.starts_at).getTime()
        const e = b.ends_at ? new Date(b.ends_at).getTime() : s
        if (fromMs != null && e < fromMs) return false
        if (toMs != null && s > toMs) return false
      }
      return true
    })
  }, [bookings, q, facilityFilter, ownerFilter, fromDate, toDate, ownerNameOf])

  async function remove(b) {
    if (!confirm(`Cancel booking "${b.title}"?`)) return
    try { await api.assetsDeleteBooking(b.id); load() } catch (e) { toast.error(e.message) }
  }
  function openNew() { setEditing(null); setShowForm(true) }
  function openEdit(b) { setEditing(b); setShowForm(true) }
  function onSaved() { setShowForm(false); setEditing(null); load() }

  const renderChip = (b, { compact }) => (
    <div className="rounded px-1.5 py-1 text-[10px] leading-tight border" style={{ background: `${ACCENT}1a`, borderColor: `${ACCENT}55`, color: ACCENT }}>
      <div className="font-semibold truncate">{b.title}</div>
      <div className="truncate opacity-90">{facilityName(b.facility_id)}</div>
      {!compact && (
        <div className="truncate opacity-80 text-[9px] mt-0.5">
          {fmtTime(b.starts_at)} to {fmtTime(b.ends_at)}
          {b.contact_name ? ` · ${b.contact_name}` : ''}
          {ownerNameOf(b) ? ` · ${ownerNameOf(b)}` : ''}
        </div>
      )}
    </div>
  )

  const pill = (a) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${a ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`

  if (bookings === null) return <PbSpinner message="Loading bookings…" />
  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <button onClick={() => setView('calendar')} className={pill(view === 'calendar')}>Calendar</button>
          <button onClick={() => setView('list')} className={pill(view === 'list')}>List</button>
        </div>
        <button onClick={openNew}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          + ADD NEW BOOKING
        </button>
      </div>

      {showForm && (
        <BookingForm facilities={facilities} members={members} initial={editing} onCancel={() => { setShowForm(false); setEditing(null) }} onSaved={onSaved} />
      )}

      <div className="pb-card p-3 mb-4 flex flex-wrap gap-2 items-center">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Search title or contact name…" value={q} onChange={e => setQ(e.target.value)} />
        <select className={`${inp} w-44`} value={facilityFilter} onChange={e => setFacilityFilter(e.target.value)}>
          <option value="">All facilities</option>
          {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <select className={`${inp} w-44`} value={ownerFilter} onChange={e => setOwnerFilter(e.target.value)}>
          <option value="">All owners</option>
          {owners.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        {view === 'list' && (
          <div className="flex items-center gap-1">
            <span className="font-mono text-[9px] text-pb-faintest">FROM</span>
            <input type="date" className={`${inp} w-36`} value={fromDate} onChange={e => setFromDate(e.target.value)} />
            <span className="font-mono text-[9px] text-pb-faintest">TO</span>
            <input type="date" className={`${inp} w-36`} value={toDate} onChange={e => setToDate(e.target.value)} />
          </div>
        )}
      </div>

      {view === 'calendar' ? (
        <Calendar
          items={filtered}
          getStart={b => b.starts_at}
          getEnd={b => b.ends_at || b.starts_at}
          renderChip={renderChip}
          onItemClick={openEdit}
          accent={ACCENT}
        />
      ) : filtered.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">{bookings.length === 0 ? 'No bookings yet.' : 'No bookings match.'}</div>
      ) : (
        <div className="space-y-1.5">
          {filtered.slice().sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at)).map(b => (
            <div key={b.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div className="min-w-0">
                <div className="text-pb-text text-sm truncate">{b.title}</div>
                <div className="font-mono text-[10px] text-pb-faint truncate">
                  {facilityName(b.facility_id)} · {fmtDateTime(b.starts_at)}{b.ends_at ? ` → ${fmtDateTime(b.ends_at)}` : ''}
                  {b.contact_name ? ` · ${b.contact_name}` : ''}
                  {ownerNameOf(b) ? ` · Owner: ${ownerNameOf(b)}` : ''}
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button onClick={() => openEdit(b)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
                <button onClick={() => remove(b)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Cancel</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Assets tab ────────────────────────────────────────────────────────────────
function AssetCard({ asset, facilities, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  async function setStatus(status) {
    try { await api.assetsUpdateItem(asset.id, { status }); onChanged() } catch (e) { toast.error(e.message) }
  }
  async function setCondition(condition) {
    try { await api.assetsUpdateItem(asset.id, { condition }); onChanged() } catch (e) { toast.error(e.message) }
  }
  async function remove() {
    if (!confirm(`Archive "${asset.name}"?`)) return
    try { await api.assetsDeleteItem(asset.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  const facilityName = (id) => facilities.find(f => f.id === id)?.name

  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{asset.name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {label(asset.category)}{asset.asset_tag ? ` · #${asset.asset_tag}` : ''}{asset.facility_id ? ` · ${facilityName(asset.facility_id) || ''}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border pb-hairline ${asset.status === 'in_service' ? 'text-pb-accent' : 'text-pb-faint'}`}>{label(asset.status)}</span>
          <span onClick={(e) => { e.stopPropagation(); remove() }} className="font-mono text-[10px] text-pb-faintest hover:text-pb-red">✕</span>
          <span className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>
      {expanded && (
        <div className="border-t pb-hairline-t px-4 py-3 space-y-2">
          <div className="flex flex-wrap gap-3 text-[11px]">
            <div>
              <span className="font-mono text-[9px] text-pb-faintest block mb-1">CONDITION</span>
              <select className="bg-pb-surface2 text-pb-text text-[10px] font-mono border pb-hairline rounded px-1.5 py-1" value={asset.condition} onChange={e => setCondition(e.target.value)}>
                {ASSET_CONDITIONS.map(c => <option key={c} value={c}>{label(c)}</option>)}
              </select>
            </div>
            <div>
              <span className="font-mono text-[9px] text-pb-faintest block mb-1">STATUS</span>
              <select className="bg-pb-surface2 text-pb-text text-[10px] font-mono border pb-hairline rounded px-1.5 py-1" value={asset.status} onChange={e => setStatus(e.target.value)}>
                {ASSET_STATUSES.map(s => <option key={s} value={s}>{label(s)}</option>)}
              </select>
            </div>
            {asset.purchase_cost != null && <div><span className="font-mono text-[9px] text-pb-faintest block mb-1">PURCHASE COST</span><span className="text-pb-text">${asset.purchase_cost}</span></div>}
            {asset.purchase_date && <div><span className="font-mono text-[9px] text-pb-faintest block mb-1">ACQUIRED</span><span className="text-pb-text">{asset.purchase_date}</span></div>}
            {asset.service_due_date && <div><span className="font-mono text-[9px] text-pb-faintest block mb-1">SERVICE DUE</span><span className="text-pb-text">{asset.service_due_date}</span></div>}
          </div>
          {asset.notes && <div className="text-pb-faint text-[12px]">{asset.notes}</div>}
          <MaintenanceLogPanel subjectType="asset" subjectId={asset.id} />
        </div>
      )}
    </div>
  )
}

function NewAssetForm({ facilities, onCreated, onCancel }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', category: 'other', asset_tag: '', purchase_cost: '', purchase_date: '', condition: 'good', status: 'in_service', service_due_date: '', facility_id: '', notes: '' })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.assetsCreateItem({
        name: form.name,
        category: form.category,
        asset_tag: form.asset_tag || null,
        facility_id: form.facility_id || null,
        purchase_cost: form.purchase_cost ? Number(form.purchase_cost) : null,
        purchase_date: form.purchase_date || null,
        condition: form.condition,
        status: form.status,
        service_due_date: form.service_due_date || null,
        notes: form.notes || null,
      })
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW ASSET</div>
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Name (e.g. Ride-on mower)" value={form.name} onChange={e => set('name', e.target.value)} />
        <select className={`${inp} w-44`} value={form.category} onChange={e => set('category', e.target.value)}>
          {ASSET_CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <input className={`${inp} w-32`} placeholder="Asset tag" value={form.asset_tag} onChange={e => set('asset_tag', e.target.value)} />
        <select className={`${inp} w-40`} value={form.facility_id} onChange={e => set('facility_id', e.target.value)}>
          <option value="">No facility</option>
          {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <input type="number" step="0.01" className={`${inp} w-28`} placeholder="Cost $" value={form.purchase_cost} onChange={e => set('purchase_cost', e.target.value)} />
        <div className="flex flex-col">
          <span className="font-mono text-[8px] text-pb-faintest">ACQUIRED</span>
          <input type="date" className={`${inp} w-40`} value={form.purchase_date} onChange={e => set('purchase_date', e.target.value)} />
        </div>
        <select className={`${inp} w-36`} value={form.condition} onChange={e => set('condition', e.target.value)}>
          {ASSET_CONDITIONS.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <select className={`${inp} w-36`} value={form.status} onChange={e => set('status', e.target.value)}>
          {ASSET_STATUSES.map(s => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <div className="flex flex-col">
          <span className="font-mono text-[8px] text-pb-faintest">SERVICE DUE</span>
          <input type="date" className={`${inp} w-40`} value={form.service_due_date} onChange={e => set('service_due_date', e.target.value)} />
        </div>
      </div>
      <input className={`${inp} mt-2`} placeholder="Notes (optional)" value={form.notes} onChange={e => set('notes', e.target.value)} />
      <div className="flex gap-2 mt-3">
        <button onClick={submit} disabled={busy || !form.name.trim()}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Adding…' : '+ Asset'}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
      </div>
    </div>
  )
}

function AssetsTab({ facilities }) {
  const toast = useToast()
  const [assets, setAssets] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [q, setQ] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [facilityFilter, setFacilityFilter] = useState('')
  const [costMin, setCostMin] = useState('')
  const [costMax, setCostMax] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const load = useCallback(() => {
    api.assetsListItems().then(d => setAssets(d.assets || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    if (!assets) return []
    const n = q.trim().toLowerCase()
    const min = costMin !== '' ? Number(costMin) : null
    const max = costMax !== '' ? Number(costMax) : null
    const fromMs = fromDate ? new Date(fromDate + 'T00:00').getTime() : null
    const toMs = toDate ? new Date(toDate + 'T23:59:59').getTime() : null
    return assets.filter(a => {
      if (n && !((a.name || '').toLowerCase().includes(n) || (a.asset_tag || '').toLowerCase().includes(n))) return false
      if (catFilter && a.category !== catFilter) return false
      if (facilityFilter && a.facility_id !== facilityFilter) return false
      if (min != null && (a.purchase_cost == null || Number(a.purchase_cost) < min)) return false
      if (max != null && (a.purchase_cost == null || Number(a.purchase_cost) > max)) return false
      if (fromMs != null || toMs != null) {
        if (!a.purchase_date) return false
        const t = new Date(a.purchase_date + 'T00:00').getTime()
        if (fromMs != null && t < fromMs) return false
        if (toMs != null && t > toMs) return false
      }
      return true
    })
  }, [assets, q, catFilter, facilityFilter, costMin, costMax, fromDate, toDate])

  if (assets === null) return <PbSpinner message="Loading assets…" />
  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-2">
        <div className="font-mono text-[11px] text-pb-faint">{assets.length} {assets.length === 1 ? 'asset' : 'assets'}</div>
        <button onClick={() => setShowForm(s => !s)}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {showForm ? 'Close' : '+ Add new asset'}
        </button>
      </div>

      {showForm && <NewAssetForm facilities={facilities} onCreated={() => { setShowForm(false); load() }} onCancel={() => setShowForm(false)} />}

      <div className="pb-card p-3 mb-4 flex flex-wrap gap-2 items-center">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Search by name or tag…" value={q} onChange={e => setQ(e.target.value)} />
        <select className={`${inp} w-40`} value={catFilter} onChange={e => setCatFilter(e.target.value)}>
          <option value="">All types</option>
          {ASSET_CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <select className={`${inp} w-40`} value={facilityFilter} onChange={e => setFacilityFilter(e.target.value)}>
          <option value="">All facilities</option>
          {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[9px] text-pb-faintest">$</span>
          <input type="number" className={`${inp} w-24`} placeholder="Min" value={costMin} onChange={e => setCostMin(e.target.value)} />
          <span className="font-mono text-[9px] text-pb-faintest">–</span>
          <input type="number" className={`${inp} w-24`} placeholder="Max" value={costMax} onChange={e => setCostMax(e.target.value)} />
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[9px] text-pb-faintest">ACQUIRED FROM</span>
          <input type="date" className={`${inp} w-36`} value={fromDate} onChange={e => setFromDate(e.target.value)} />
          <span className="font-mono text-[9px] text-pb-faintest">TO</span>
          <input type="date" className={`${inp} w-36`} value={toDate} onChange={e => setToDate(e.target.value)} />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">{assets.length === 0 ? 'No assets recorded yet.' : 'No assets match.'}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map(a => <AssetCard key={a.id} asset={a} facilities={facilities} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

export default function AdminAssets() {
  const toast = useToast()
  const [tab, setTab] = useState('facilities')
  const [facilities, setFacilities] = useState([])
  const [members, setMembers] = useState([])

  const loadFacilities = useCallback(() => {
    api.assetsListFacilities().then(d => setFacilities(d.facilities || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => { loadFacilities() }, [loadFacilities])
  useEffect(() => {
    api.feeAllMembers().then(d => setMembers(d.members || [])).catch(e => toast.error(e.message))
  }, [toast])

  return (
    <BetterClubManagerLayout title="Facilities" caption="Grounds, gear, bookings and service history">
      <div className="max-w-4xl">
        <TabBar tab={tab} setTab={setTab} />
        {tab === 'facilities' && <FacilitiesTab onFacilitiesChanged={loadFacilities} />}
        {tab === 'bookings' && <BookingsTab facilities={facilities} members={members} />}
        {tab === 'assets' && <AssetsTab facilities={facilities} />}
      </div>
    </BetterClubManagerLayout>
  )
}
