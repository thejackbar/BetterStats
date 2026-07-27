import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const FACILITY_TYPES = ['ground', 'clubhouse', 'nets', 'scoreboard', 'canteen', 'storage', 'other']
const ASSET_CATEGORIES = ['equipment', 'technology', 'furniture', 'ground_maintenance', 'safety', 'other']
const ASSET_CONDITIONS = ['excellent', 'good', 'fair', 'poor', 'unserviceable']
const ASSET_STATUSES = ['in_service', 'in_repair', 'retired', 'disposed']
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

function TabBar({ tab, setTab }) {
  const tabs = [['facilities', 'Facilities'], ['bookings', 'Bookings'], ['assets', 'Assets']]
  return (
    <div className="flex gap-1 mb-5">
      {tabs.map(([k, l]) => (
        <button key={k} onClick={() => setTab(k)}
          className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>
          {l}
        </button>
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

function FacilitiesTab() {
  const toast = useToast()
  const [facilities, setFacilities] = useState(null)
  const [form, setForm] = useState({ name: '', facility_type: 'other', description: '', key_location: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.assetsListFacilities().then(d => setFacilities(d.facilities || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.assetsCreateFacility(form)
      setForm({ name: '', facility_type: 'other', description: '', key_location: '' })
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (facilities === null) return <PbSpinner message="Loading facilities…" />
  return (
    <div>
      <div className="pb-card p-4 mb-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW FACILITY</div>
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Name (e.g. Main Oval, Clubhouse)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <select className={`${inp} w-40`} value={form.facility_type} onChange={e => setForm(f => ({ ...f, facility_type: e.target.value }))}>
            {FACILITY_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
          </select>
          <input className={`${inp} w-40`} placeholder="Key location" value={form.key_location} onChange={e => setForm(f => ({ ...f, key_location: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.name.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ FACILITY'}
          </button>
        </div>
      </div>
      {facilities.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No facilities yet.</div>
      ) : (
        <div className="space-y-2">
          {facilities.map(f => <FacilityCard key={f.id} facility={f} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

// ── Bookings tab ──────────────────────────────────────────────────────────────
function BookingsTab({ facilities }) {
  const toast = useToast()
  const [bookings, setBookings] = useState(null)
  const [form, setForm] = useState({ facility_id: '', title: '', starts_at: '', ends_at: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.assetsListBookings({ upcomingOnly: true }).then(d => setBookings(d.bookings || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.facility_id || !form.title.trim() || !form.starts_at) return
    setBusy(true)
    try {
      await api.assetsCreateBooking({
        ...form, starts_at: new Date(form.starts_at).toISOString(),
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
      })
      setForm({ facility_id: '', title: '', starts_at: '', ends_at: '' })
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(b) {
    if (!confirm(`Cancel booking "${b.title}"?`)) return
    try { await api.assetsDeleteBooking(b.id); load() } catch (e) { toast.error(e.message) }
  }
  const facilityName = (id) => facilities.find(f => f.id === id)?.name || '—'

  if (bookings === null) return <PbSpinner message="Loading bookings…" />
  return (
    <div>
      <div className="pb-card p-4 mb-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW BOOKING</div>
        <div className="flex flex-wrap gap-2">
          <select className={`${inp} w-44`} value={form.facility_id} onChange={e => setForm(f => ({ ...f, facility_id: e.target.value }))}>
            <option value="">Facility…</option>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Title (e.g. Junior training)" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <input type="datetime-local" className={`${inp} w-56`} value={form.starts_at} onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))} />
          <input type="datetime-local" className={`${inp} w-56`} value={form.ends_at} onChange={e => setForm(f => ({ ...f, ends_at: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.facility_id || !form.title.trim() || !form.starts_at}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'BOOKING…' : '+ BOOKING'}
          </button>
        </div>
      </div>
      {bookings.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No upcoming bookings.</div>
      ) : (
        <div className="space-y-1.5">
          {bookings.map(b => (
            <div key={b.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div>
                <div className="text-pb-text text-sm">{b.title}</div>
                <div className="font-mono text-[10px] text-pb-faint">{facilityName(b.facility_id)} · {new Date(b.starts_at).toLocaleString()}</div>
              </div>
              <button onClick={() => remove(b)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red shrink-0">Cancel</button>
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
            {asset.service_due_date && <div><span className="font-mono text-[9px] text-pb-faintest block mb-1">SERVICE DUE</span><span className="text-pb-text">{asset.service_due_date}</span></div>}
          </div>
          {asset.notes && <div className="text-pb-faint text-[12px]">{asset.notes}</div>}
          <MaintenanceLogPanel subjectType="asset" subjectId={asset.id} />
        </div>
      )}
    </div>
  )
}

function NewAssetForm({ facilities, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', category: 'other', asset_tag: '', facility_id: '', purchase_cost: '', service_due_date: '' })
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.assetsCreateItem({
        ...form, facility_id: form.facility_id || null,
        purchase_cost: form.purchase_cost ? Number(form.purchase_cost) : null,
        service_due_date: form.service_due_date || null,
      })
      setForm({ name: '', category: 'other', asset_tag: '', facility_id: '', purchase_cost: '', service_due_date: '' })
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW ASSET</div>
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Name (e.g. Ride-on mower)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        <select className={`${inp} w-44`} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
          {ASSET_CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <input className={`${inp} w-32`} placeholder="Asset tag" value={form.asset_tag} onChange={e => setForm(f => ({ ...f, asset_tag: e.target.value }))} />
        <select className={`${inp} w-40`} value={form.facility_id} onChange={e => setForm(f => ({ ...f, facility_id: e.target.value }))}>
          <option value="">No facility</option>
          {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <input type="number" step="0.01" className={`${inp} w-28`} placeholder="Cost $" value={form.purchase_cost} onChange={e => setForm(f => ({ ...f, purchase_cost: e.target.value }))} />
        <input type="date" className={`${inp} w-40`} placeholder="Service due" value={form.service_due_date} onChange={e => setForm(f => ({ ...f, service_due_date: e.target.value }))} />
        <button onClick={submit} disabled={busy || !form.name.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'ADDING…' : '+ ASSET'}
        </button>
      </div>
    </div>
  )
}

function AssetsTab({ facilities }) {
  const toast = useToast()
  const [assets, setAssets] = useState(null)

  const load = useCallback(() => {
    api.assetsListItems().then(d => setAssets(d.assets || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  if (assets === null) return <PbSpinner message="Loading assets…" />
  return (
    <div>
      <NewAssetForm facilities={facilities} onCreated={load} />
      {assets.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No assets recorded yet.</div>
      ) : (
        <div className="space-y-2">
          {assets.map(a => <AssetCard key={a.id} asset={a} facilities={facilities} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

export default function AdminAssets() {
  const toast = useToast()
  const [tab, setTab] = useState('facilities')
  const [facilities, setFacilities] = useState([])

  useEffect(() => {
    api.assetsListFacilities().then(d => setFacilities(d.facilities || [])).catch(e => toast.error(e.message))
  }, [toast, tab])

  return (
    <BetterClubManagerLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Assets & Facilities</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Club property — grounds, clubhouse, equipment — with bookings and a maintenance/service history.
        </p>
        <TabBar tab={tab} setTab={setTab} />
        {tab === 'facilities' && <FacilitiesTab />}
        {tab === 'bookings' && <BookingsTab facilities={facilities} />}
        {tab === 'assets' && <AssetsTab facilities={facilities} />}
      </div>
    </BetterClubManagerLayout>
  )
}
