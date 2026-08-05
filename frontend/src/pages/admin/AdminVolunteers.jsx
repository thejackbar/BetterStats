import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { FilterPill } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'
import { MemberSelect, RoleMultiSelect } from '../../components/admin/clubmanager/pickers'

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

function VolunteerRow({ v, onChanged, clubRoles, onRoleCreated }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  const [roles, setRoles] = useState(v.roles_interested || [])
  const [roleIds, setRoleIds] = useState((v.roles || []).map(r => r.id))
  const [days, setDays] = useState(v.available_days || [])
  const [livesNearby, setLivesNearby] = useState(v.lives_nearby)
  const [saving, setSaving] = useState(false)

  // Reseed local state if the directory row changes (e.g. after a save/reload).
  useEffect(() => { setRoleIds((v.roles || []).map(r => r.id)) }, [v.roles])

  async function saveProfile() {
    setSaving(true)
    try {
      await api.volunteerUpsertProfile({ member_id: v.member_id, roles_interested: roles, available_days: days, lives_nearby: livesNearby, role_ids: roleIds })
      toast.success('Profile saved'); onChanged()
    } catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{v.full_name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5 flex flex-wrap gap-1.5">
            {(v.roles || []).length > 0
              ? v.roles.map(r => <span key={r.id} className="text-pb-accent">{r.title}</span>)
              : (v.roles_interested || []).length === 0
                ? <span className="text-pb-faintest">No roles set</span>
                : v.roles_interested.map(r => <span key={r}>{r}</span>)}
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
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ROLES</div>
            <RoleMultiSelect
              roles={clubRoles}
              value={roleIds}
              onChange={setRoleIds}
              onCreateRole={async (title) => {
                const role = await api.raCreateRole({ title })
                onRoleCreated(role)
                return role
              }}
              label="Assign roles"
            />
          </div>
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
            className="px-4 py-2 rounded text-[12.5px] font-semibold font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
            {saving ? 'Saving…' : 'Save profile'}
          </button>
        </div>
      )}
    </div>
  )
}


// What the club is actually short of, read from the shifts nobody has filled.
//
// The number that matters is per DAY, not per role: six scorers is a
// comforting figure that means nothing if all six are Sunday-only and every
// open scoring shift is a Saturday. Clicking a shortage filters the list below
// to that role on that day, which is the next thing you want to do.
function ShortagesPanel({ onPick }) {
  const [data, setData] = useState(null)
  const [weeks, setWeeks] = useState(4)
  useEffect(() => { api.rosterShortages(weeks).then(setData).catch(() => setData(null)) }, [weeks])
  if (!data) return null

  const short = (data.roles || []).filter(r => r.short_by > 0)
  const covered = (data.roles || []).length - short.length

  return (
    <div className="pb-card p-4 mb-4">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest">WHAT WE ARE SHORT OF</div>
        <span className="ml-auto flex items-center gap-1.5">
          {[2, 4, 8].map(w => (
            <FilterPill key={w} active={weeks === w} onClick={() => setWeeks(w)}>{w} weeks</FilterPill>
          ))}
        </span>
      </div>

      {data.total_open === 0 ? (
        <div className="text-[12.5px] text-pb-dim">
          Every shift in the next {weeks} weeks has someone against it.
        </div>
      ) : short.length === 0 ? (
        <div className="text-[12.5px] text-pb-dim">
          {data.total_open} shift{data.total_open === 1 ? '' : 's'} still open, but there are enough people
          free on the day for each one. Nobody new needed, just the roster filling in.
        </div>
      ) : (
        <div className="space-y-2.5">
          {short.map(r => (
            <div key={r.role_id}>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-pb-text font-semibold text-[13.5px]">{r.role_title}</span>
                <span className="font-mono text-[10px] text-pb-faint">
                  {r.open_shifts} open · {r.holders} hold the role
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {r.days.filter(d => d.short_by > 0).map(d => (
                  <button key={d.day_of_week} onClick={() => onPick(r.role_title, d.day_full)}
                    title={`Show ${r.role_title} free on ${d.day}`}
                    className="px-2.5 py-1 rounded-full text-[12px] border transition-colors"
                    style={{ borderColor: 'rgba(245,181,66,0.45)', background: 'rgba(245,181,66,0.12)', color: '#f5b542' }}>
                    {d.day}: need {d.short_by} more
                  </button>
                ))}
                {r.days.filter(d => d.short_by === 0 && d.open_shifts > 0).map(d => (
                  <button key={d.day_of_week} onClick={() => onPick(r.role_title, d.day_full)}
                    title={`Show ${r.role_title} free on ${d.day}`}
                    className="px-2.5 py-1 rounded-full text-[12px] border border-pb-hairline2 bg-transparent text-pb-dim hover:text-pb-text">
                    {d.day}: {d.available} free
                  </button>
                ))}
              </div>
              {r.holders_with_no_days > 0 && (
                <div className="text-[12px] text-pb-faint mt-1">
                  {r.holders_with_no_days} {r.holders_with_no_days === 1 ? 'person holds' : 'people hold'} this role
                  with no days recorded, so the roster cannot offer it to them.
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {(data.no_role_required || []).length > 0 && (
        <div className="text-[12.5px] text-pb-dim mt-3 pt-3 border-t pb-hairline-t">
          {data.no_role_required.reduce((n, a) => n + a.open_shifts, 0)} open shift(s) in areas that ask for no
          particular role ({data.no_role_required.map(a => a.area_name).join(', ')}) — anyone can take those.
        </div>
      )}
      {covered > 0 && short.length > 0 && (
        <div className="font-mono text-[10px] text-pb-faintest mt-3">
          {covered} other role{covered === 1 ? '' : 's'} with open shifts already have enough people free.
        </div>
      )}
    </div>
  )
}

function VolunteersTab({ volunteers, load, clubRoles, onRoleCreated, allMembers }) {
  const toast = useToast()
  const [addingMemberId, setAddingMemberId] = useState(null)
  const [roleFilter, setRoleFilter] = useState('')
  const [days, setDays] = useState([])          // several days, not one
  const [groupByRole, setGroupByRole] = useState(false)

  // Picking Sat AND Sun means "free on either", which is the question you are
  // actually asking when you are trying to cover a weekend.
  const filtered = useMemo(() => {
    return (volunteers || []).filter(v => {
      const roleNames = [...(v.roles || []).map(r => r.title), ...(v.roles_interested || [])]
      const avail = v.available_days || []
      return (!roleFilter || roleNames.some(r => r.toLowerCase().includes(roleFilter.toLowerCase())))
        && (days.length === 0 || days.some(d => avail.includes(d)))
    }).sort((a, b) => (a.full_name || '').localeCompare(b.full_name || ''))
  }, [volunteers, roleFilter, days])

  // Grouped by role, each group alphabetical. Someone holding two roles appears
  // under both, because that is the point — you are looking for anyone who can
  // cover a role, not for a tidy partition of people.
  const grouped = useMemo(() => {
    if (!groupByRole) return null
    const by = new Map()
    filtered.forEach(v => {
      const titles = (v.roles || []).map(r => r.title)
      if (titles.length === 0) titles.push('No role assigned')
      titles.forEach(t => { if (!by.has(t)) by.set(t, []); by.get(t).push(v) })
    })
    return [...by.entries()].sort((a, b) =>
      a[0] === 'No role assigned' ? 1 : b[0] === 'No role assigned' ? -1 : a[0].localeCompare(b[0]))
  }, [filtered, groupByRole])

  const candidateMembers = useMemo(() => {
    const existing = new Set((volunteers || []).map(v => v.member_id))
    return allMembers.filter(m => !existing.has(m.member_id))
  }, [allMembers, volunteers])

  async function addVolunteer(memberId) {
    if (!memberId) return
    try {
      await api.volunteerUpsertProfile({ member_id: memberId, roles_interested: [], available_days: [] })
      setAddingMemberId(null)
      load()
    } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <ShortagesPanel onPick={(role, day) => { setRoleFilter(role); setDays([day]); setGroupByRole(false) }} />

      <div className="pb-card p-4 mb-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD A VOLUNTEER</div>
        <div className="flex gap-2">
          <div className="flex-1">
            <MemberSelect members={candidateMembers} value={addingMemberId} onChange={setAddingMemberId} placeholder="Search for a player or member…" />
          </div>
          <button onClick={() => addVolunteer(addingMemberId)} disabled={!addingMemberId}
            className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            + ADD
          </button>
        </div>
        <p className="text-[12.5px] leading-[1.6] text-pb-faint mt-1.5">
          Search any club member. Members already on the volunteer list are hidden.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Filter by role (e.g. Scorer)…" value={roleFilter} onChange={e => setRoleFilter(e.target.value)} />
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {DAYS.map(d => (
          <FilterPill key={d} active={days.includes(d)}
            onClick={() => setDays(cur => cur.includes(d) ? cur.filter(x => x !== d) : [...cur, d])}>
            {d.slice(0, 3)}
          </FilterPill>
        ))}
        {days.length > 0 && (
          <button onClick={() => setDays([])} className="text-[12px] text-pb-faint hover:text-pb-text">Clear days</button>
        )}
        <span className="ml-auto flex items-center gap-2">
          <FilterPill active={!groupByRole} onClick={() => setGroupByRole(false)}>By name</FilterPill>
          <FilterPill active={groupByRole} onClick={() => setGroupByRole(true)}>By role</FilterPill>
        </span>
      </div>

      <div className="text-[12.5px] text-pb-faint mb-3">
        {days.length === 0
          ? `${filtered.length} volunteer${filtered.length === 1 ? '' : 's'}.`
          : `${filtered.length} free on ${days.length === 1 ? days[0] : days.map(d => d.slice(0, 3)).join(', ')}.`}
      </div>

      {filtered.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No volunteers match.</div>
      ) : grouped ? (
        <div className="space-y-5">
          {grouped.map(([title, list]) => (
            <div key={title}>
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">
                {title.toUpperCase()} · {list.length}
              </div>
              <div className="space-y-2">
                {list.map(v => (
                  <VolunteerRow key={title + v.member_id} v={v} onChanged={load} clubRoles={clubRoles} onRoleCreated={onRoleCreated} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(v => (
            <VolunteerRow key={v.member_id} v={v} onChanged={load}
              clubRoles={clubRoles} onRoleCreated={onRoleCreated} />
          ))}
        </div>
      )}
    </div>
  )
}

function HoursTab({ volunteers, load, activities, onActivityCreated }) {
  const toast = useToast()
  const [memberId, setMemberId] = useState(null)
  const [hours, setHours] = useState(null)
  const [hoursForm, setHoursForm] = useState({ hours: '', activity_id: '', logged_date: new Date().toISOString().slice(0, 10) })
  const [newActivity, setNewActivity] = useState('')
  const [showNewActivity, setShowNewActivity] = useState(false)
  const [addingActivity, setAddingActivity] = useState(false)

  const pickerMembers = useMemo(() =>
    (volunteers || []).map(v => ({ member_id: v.member_id, full_name: v.full_name, is_linked: v.is_linked })),
    [volunteers])

  const loadHours = useCallback(() => {
    if (!memberId) { setHours(null); return }
    api.volunteerListHours(memberId).then(d => setHours(d.hours || [])).catch(() => {})
  }, [memberId])

  useEffect(() => { loadHours() }, [loadHours])

  const totalHours = useMemo(() =>
    (hours || []).reduce((sum, h) => sum + (Number(h.hours) || 0), 0),
    [hours])

  async function createActivity() {
    const t = newActivity.trim()
    if (!t) return
    setAddingActivity(true)
    try {
      const a = await api.raCreateActivity({ title: t })
      onActivityCreated(a)
      setHoursForm(f => ({ ...f, activity_id: a.id }))
      setNewActivity(''); setShowNewActivity(false)
    } catch (e) { toast.error(e.message) } finally { setAddingActivity(false) }
  }

  async function logHours() {
    if (!memberId) { toast.error('Choose a volunteer first'); return }
    if (!Number(hoursForm.hours)) { toast.error('Hours is required'); return }
    try {
      await api.volunteerLogHours({
        member_id: memberId,
        hours: Number(hoursForm.hours),
        activity_id: hoursForm.activity_id || null,
        logged_date: hoursForm.logged_date,
      })
      setHoursForm({ hours: '', activity_id: '', logged_date: new Date().toISOString().slice(0, 10) })
      loadHours(); load()
    } catch (e) { toast.error(e.message) }
  }

  async function removeHours(id) {
    try { await api.volunteerDeleteHours(id); loadHours(); load() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <div className="pb-card p-4 mb-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">WHOSE HOURS?</div>
        <MemberSelect members={pickerMembers} value={memberId} onChange={setMemberId} placeholder="Choose a volunteer…" />
      </div>

      {!memberId ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">Choose a volunteer to view and log their hours.</div>
      ) : (
        <div className="pb-card p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest">HOURS LOG</div>
            <div className="font-display font-bold text-base" style={{ color: 'var(--pb-accent)' }}>{totalHours}h total</div>
          </div>

          {hours === null ? <PbSpinner message="Loading…" /> : (
            <div className="space-y-1">
              {hours.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No hours logged yet.</div>}
              {hours.map(h => (
                <div key={h.id} className="flex items-center justify-between font-mono text-[10px] text-pb-dim">
                  <span>{h.logged_date} — {h.hours}h{h.activity ? ` (${h.activity})` : ''}</span>
                  <button onClick={() => removeHours(h.id)} className="text-pb-faintest hover:text-pb-red">✕</button>
                </div>
              ))}
            </div>
          )}

          <div className="pt-3 border-t pb-hairline-t">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">LOG HOURS</div>
            <div className="flex flex-wrap gap-2 items-center">
              <input type="date" className={`${inp} w-36`} value={hoursForm.logged_date} onChange={e => setHoursForm(f => ({ ...f, logged_date: e.target.value }))} />
              <input type="number" min="0" step="0.5" className={`${inp} w-24`} placeholder="Hours" value={hoursForm.hours} onChange={e => setHoursForm(f => ({ ...f, hours: e.target.value }))} />
              <select className={`${inp} flex-1 min-w-[140px]`} value={hoursForm.activity_id} onChange={e => setHoursForm(f => ({ ...f, activity_id: e.target.value }))}>
                <option value="">— choose activity —</option>
                {activities.map(a => <option key={a.id} value={a.id}>{a.title}</option>)}
              </select>
              <button onClick={() => setShowNewActivity(x => !x)} className="px-2 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">+ new</button>
              <button onClick={logHours} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text">Log hours</button>
            </div>
            {showNewActivity && (
              <div className="flex gap-1.5 mt-2">
                <input className={`${inp} flex-1`} placeholder="New activity title" value={newActivity} onChange={e => setNewActivity(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); createActivity() } }} />
                <button onClick={createActivity} disabled={addingActivity || !newActivity.trim()}
                  className="px-3 py-1.5 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
                  {addingActivity ? '…' : 'Add activity'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminVolunteers() {
  const toast = useToast()
  const [tab, setTab] = useState('volunteers')
  const [volunteers, setVolunteers] = useState(null)
  const [allMembers, setAllMembers] = useState([])
  const [clubRoles, setClubRoles] = useState([])
  const [activities, setActivities] = useState([])

  const load = useCallback(() => {
    api.volunteerDirectory().then(d => setVolunteers(d.volunteers || [])).catch(e => toast.error(e.message))
  }, [toast])

  const reloadRoles = useCallback(() => {
    api.raRoles({ committee: false }).then(d => setClubRoles(d.roles || [])).catch(() => {})
  }, [])

  const reloadActivities = useCallback(() => {
    api.raActivities().then(d => setActivities(d.activities || [])).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    reloadRoles()
    reloadActivities()
    api.feeAllMembers().then(d => setAllMembers(d.members || [])).catch(() => {})
  }, [load, reloadRoles, reloadActivities])

  const onRoleCreated = useCallback((role) => {
    if (role?.id) setClubRoles(prev => (prev.some(r => r.id === role.id) ? prev : [...prev, role]))
  }, [])

  const onActivityCreated = useCallback((a) => {
    if (a?.id) setActivities(prev => (prev.some(x => x.id === a.id) ? prev : [...prev, a]))
  }, [])

  if (volunteers === null) return <BetterClubManagerLayout title="Volunteer bulk entry" caption="Who is free, and logging hours for several people"><PbSpinner message="Loading volunteers…" /></BetterClubManagerLayout>
  return (
    <BetterClubManagerLayout title="Volunteer bulk entry" caption="Who is free, and logging hours for several people">
      <div className="max-w-4xl">

        <div className="flex flex-wrap gap-1 mb-5">
          {[['volunteers', 'Volunteers'], ['hours', 'Hours']].map(([k, l]) => (
            <FilterPill key={k} active={tab === k} onClick={() => setTab(k)}>{l}</FilterPill>
          ))}
        </div>

        {tab === 'volunteers' ? (
          <VolunteersTab volunteers={volunteers} load={load} clubRoles={clubRoles} onRoleCreated={onRoleCreated} allMembers={allMembers} />
        ) : (
          <HoursTab volunteers={volunteers} load={load} activities={activities} onActivityCreated={onActivityCreated} />
        )}
      </div>
    </BetterClubManagerLayout>
  )
}
