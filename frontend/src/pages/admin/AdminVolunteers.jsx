import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function TagInput({ values, onChange, placeholder }) {
  const [text, setText] = useState('')
  function add() {
    const v = text.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setText('')
  }
  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-1.5">
        {values.map(v => (
          <span key={v} className="font-mono text-[10px] border pb-hairline rounded px-1.5 py-0.5 text-pb-dim flex items-center gap-1">
            {v}
            <button onClick={() => onChange(values.filter(x => x !== v))} className="text-pb-faintest hover:text-pb-red">✕</button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input className={inp} placeholder={placeholder} value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
        <button onClick={add} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">Add</button>
      </div>
    </div>
  )
}

function VolunteerRow({ v, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  const [roles, setRoles] = useState(v.roles_interested || [])
  const [days, setDays] = useState(v.available_days || [])
  const [livesNearby, setLivesNearby] = useState(v.lives_nearby)
  const [hours, setHours] = useState(null)
  const [hoursForm, setHoursForm] = useState({ hours: '', activity: '', logged_date: new Date().toISOString().slice(0, 10) })
  const [saving, setSaving] = useState(false)

  const loadHours = useCallback(() => {
    api.volunteerListHours(v.member_id).then(d => setHours(d.hours || [])).catch(() => {})
  }, [v.member_id])

  useEffect(() => { if (expanded && hours === null) loadHours() }, [expanded, hours, loadHours])

  async function saveProfile() {
    setSaving(true)
    try {
      await api.volunteerUpsertProfile({ member_id: v.member_id, roles_interested: roles, available_days: days, lives_nearby: livesNearby })
      toast.success('Profile saved'); onChanged()
    } catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  async function logHours() {
    if (!Number(hoursForm.hours)) { toast.error('Hours is required'); return }
    try {
      await api.volunteerLogHours({ member_id: v.member_id, hours: Number(hoursForm.hours), activity: hoursForm.activity || null, logged_date: hoursForm.logged_date })
      setHoursForm({ hours: '', activity: '', logged_date: new Date().toISOString().slice(0, 10) })
      loadHours(); onChanged()
    } catch (e) { toast.error(e.message) }
  }

  async function removeHours(id) {
    try { await api.volunteerDeleteHours(id); loadHours(); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{v.full_name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5 flex flex-wrap gap-1.5">
            {(v.roles_interested || []).length === 0 ? <span className="text-pb-faintest">No roles set</span> : v.roles_interested.map(r => <span key={r}>{r}</span>)}
            {v.lives_nearby && <span className="text-pb-accent">· Lives nearby</span>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-display font-bold text-base" style={{ color: 'var(--pb-accent)' }}>{v.total_hours}h</div>
          <span className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>
      {expanded && (
        <div className="border-t pb-hairline-t px-4 py-3 space-y-4">
          <div>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ROLES INTERESTED</div>
            <TagInput values={roles} onChange={setRoles} placeholder="e.g. Scorer, BBQ, Ground prep" />
          </div>
          <div>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">AVAILABLE DAYS</div>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map(d => {
                const on = days.includes(d)
                return (
                  <button key={d} onClick={() => setDays(on ? days.filter(x => x !== d) : [...days, d])}
                    className={`font-mono text-[10px] px-2 py-1 rounded border transition ${on ? 'pb-hairline text-pb-text bg-pb-surface2' : 'border-dashed border-pb-faintest text-pb-faintest hover:text-pb-faint'}`}>
                    {d.slice(0, 3)}
                  </button>
                )
              })}
            </div>
          </div>
          <label className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
            <input type="checkbox" checked={livesNearby} onChange={e => setLivesNearby(e.target.checked)} />
            Lives nearby
          </label>
          <button onClick={saveProfile} disabled={saving}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
            {saving ? 'SAVING…' : 'SAVE PROFILE'}
          </button>

          <div className="pt-3 border-t pb-hairline-t">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">HOURS LOG</div>
            {hours === null ? <PbSpinner message="Loading…" /> : (
              <div className="space-y-1 mb-2">
                {hours.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No hours logged yet.</div>}
                {hours.map(h => (
                  <div key={h.id} className="flex items-center justify-between font-mono text-[10px] text-pb-dim">
                    <span>{h.logged_date} — {h.hours}h{h.activity ? ` (${h.activity})` : ''}</span>
                    <button onClick={() => removeHours(h.id)} className="text-pb-faintest hover:text-pb-red">✕</button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <input type="date" className={`${inp} w-36`} value={hoursForm.logged_date} onChange={e => setHoursForm(f => ({ ...f, logged_date: e.target.value }))} />
              <input type="number" min="0" step="0.5" className={`${inp} w-24`} placeholder="Hours" value={hoursForm.hours} onChange={e => setHoursForm(f => ({ ...f, hours: e.target.value }))} />
              <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Activity" value={hoursForm.activity} onChange={e => setHoursForm(f => ({ ...f, activity: e.target.value }))} />
              <button onClick={logHours} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text">Log hours</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminVolunteers() {
  const toast = useToast()
  const [volunteers, setVolunteers] = useState(null)
  const [allMembers, setAllMembers] = useState([])
  const [seasons, setSeasons] = useState([])
  const [addingMemberId, setAddingMemberId] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [dayFilter, setDayFilter] = useState('')

  const load = useCallback(() => {
    api.volunteerDirectory().then(d => setVolunteers(d.volunteers || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => {
    load()
    api.adminListSeasons().then(seas => {
      const sorted = (seas || []).filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
      setSeasons(sorted)
      if (sorted[0]) api.feeListMembers(sorted[0].id).then(d => setAllMembers(d.members || [])).catch(() => {})
    }).catch(() => {})
  }, [load])

  const filtered = useMemo(() => {
    if (!volunteers) return []
    return volunteers.filter(v =>
      (!roleFilter || (v.roles_interested || []).some(r => r.toLowerCase().includes(roleFilter.toLowerCase()))) &&
      (!dayFilter || (v.available_days || []).includes(dayFilter))
    )
  }, [volunteers, roleFilter, dayFilter])

  const candidateMembers = useMemo(() => {
    const existing = new Set((volunteers || []).map(v => v.member_id))
    return allMembers.filter(m => !existing.has(m.member_id))
  }, [allMembers, volunteers])

  async function addVolunteer() {
    if (!addingMemberId) return
    try {
      await api.volunteerUpsertProfile({ member_id: addingMemberId, roles_interested: [], available_days: [], lives_nearby: false })
      setAddingMemberId('')
      load()
    } catch (e) { toast.error(e.message) }
  }

  if (volunteers === null) return <AdminLayout><PbSpinner message="Loading volunteers…" /></AdminLayout>
  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Volunteers</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Roles interested, availability, and an hours ledger — filter to find who's available, qualified and nearby.
        </p>

        <div className="pb-card p-4 mb-4">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD A VOLUNTEER</div>
          <div className="flex gap-2">
            <select className={`${inp} flex-1`} value={addingMemberId} onChange={e => setAddingMemberId(e.target.value)}>
              <option value="">Select member…</option>
              {candidateMembers.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
            </select>
            <button onClick={addVolunteer} disabled={!addingMemberId}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
              + ADD
            </button>
          </div>
          <p className="font-mono text-[10px] text-pb-faintest mt-1.5">
            Candidates come from BetterFees' members for the latest season — add them there first if not listed.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 mb-3">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Filter by role (e.g. Scorer)…" value={roleFilter} onChange={e => setRoleFilter(e.target.value)} />
          <select className={`${inp} w-40`} value={dayFilter} onChange={e => setDayFilter(e.target.value)}>
            <option value="">Any day</option>
            {DAYS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {filtered.length === 0 ? (
          <div className="pb-card p-6 text-center text-pb-dim text-sm">No volunteers match.</div>
        ) : (
          <div className="space-y-2">
            {filtered.map(v => <VolunteerRow key={v.member_id} v={v} onChanged={load} />)}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
