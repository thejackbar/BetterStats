// Registrations (BetterStats): everyone who used "Can't find your name?" on the Player Dashboard.
//
// Two kinds. New people (a players row the registration created, "Not a player" until approved)
// and past players who found and claimed their old record. Approving puts a new person on the
// public name list, makes a "current player" a player, and fills a claimed record's empty mobile,
// email and date of birth. Archive takes a row off the list (and a new person off the Player
// Dashboard); nothing is deleted and Restore undoes it. The note and the Contacted tick are the
// club's own follow-up. Server: routers/player_dashboard_admin.py, gated on manage_players.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useToast } from '../../contexts/ToastContext'
import { Btn, Segmented, Search, Tag } from './betterselect/ui'

const STATUS_TABS = [
  { value: 'pending', label: 'To review' },
  { value: 'approved', label: 'Approved' },
  { value: 'archived', label: 'Archived' },
  { value: 'all', label: 'All' },
]

function fmtDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}

function csvCell(v) {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function approveHint(r) {
  if (r.kind === 'claim') {
    return r.role === 'current_player'
      ? 'Approve to add the details they gave where the record is empty and mark them no longer dormant, so they show for selection.'
      : 'Approve to add the details they gave where the record is empty.'
  }
  return r.role === 'current_player'
    ? 'Approve to make them a player (selection, votes, a public profile) and put them on the Player Dashboard name list.'
    : 'Approve to put them on the Player Dashboard name list. They stay off selection boards.'
}

function Row({ r, interestLabels, onChanged }) {
  const toast = useToast()
  const [note, setNote] = useState(r.admin_note)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setNote(r.admin_note) }, [r.admin_note])

  const run = async (fn, okMsg) => {
    setBusy(true)
    try {
      onChanged(await fn())
      if (okMsg) toast.success(okMsg)
    } catch (e) {
      toast.error(e.message || 'That didn’t save')
    } finally { setBusy(false) }
  }
  const saveNote = () => {
    if ((note || '') === (r.admin_note || '')) return
    run(() => api.updatePlayerRegistration(r.id, { admin_note: note }))
  }
  const name = `${r.first_name} ${r.last_name}`.trim()

  return (
    <div className="pb-card p-4" data-registration-row={r.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-display font-bold text-lg text-pb-text break-words">{name}</div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            <Tag tone="accent">{r.role_label}</Tag>
            {r.kind === 'claim'
              ? <Tag tone="accent" title="They found their old record in the past-player search">Claimed record: {r.player_name}</Tag>
              : <Tag tone="faint">New to the club’s records</Tag>}
            {r.status === 'pending' && <Tag tone="amber">To review</Tag>}
            {r.status === 'archived' && <Tag tone="faint">Archived</Tag>}
            {r.contacted_at && <Tag tone="accent">Contacted {fmtDate(r.contacted_at)}</Tag>}
          </div>
        </div>
        <div className="text-[11.5px] text-pb-faintest shrink-0">Added {fmtDate(r.created_at)}</div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 mt-3 text-sm">
        <div><span className="text-pb-faint">Mobile </span>{r.phone ? <a className="text-pb-text underline" href={`tel:${r.phone.replace(/\s/g, '')}`}>{r.phone}</a> : <span className="text-pb-faintest">none</span>}</div>
        <div className="min-w-0 truncate"><span className="text-pb-faint">Email </span>{r.email ? <a className="text-pb-text underline" href={`mailto:${r.email}`}>{r.email}</a> : <span className="text-pb-faintest">none given</span>}</div>
        {r.date_of_birth && <div><span className="text-pb-faint">Born </span>{fmtDate(r.date_of_birth)}</div>}
        {r.years_played && <div><span className="text-pb-faint">Played </span>{r.years_played}</div>}
        {r.grades_played && <div><span className="text-pb-faint">Grades </span>{r.grades_played}</div>}
        {r.kind === 'claim' && <div><span className="text-pb-faint">Last game on record </span>{r.last_played ? fmtDate(r.last_played) : 'none'}</div>}
      </div>

      <div className="mt-2 text-[12.5px]" data-registration-consent>
        {r.contact_consent
          ? <span className="text-pb-accent">Happy to be contacted about playing, volunteering and club news.</span>
          : <span className="text-pb-faint">Did not tick the box to be contacted. Their email is kept here only, not on their player record.</span>}
      </div>
      {r.interests.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          <span className="text-[12px] text-pb-faint">Interested in</span>
          {r.interests.map((k) => <Tag key={k} tone="faint">{interestLabels[k] || k}</Tag>)}
        </div>
      )}
      {r.notes && <p className="mt-2 text-sm text-pb-dim whitespace-pre-wrap break-words">“{r.notes}”</p>}

      <div className="mt-3">
        <label htmlFor={`note-${r.id}`} className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Club note</label>
        <textarea id={`note-${r.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} onBlur={saveNote}
          placeholder="Who’s following up, what was said…"
          className="w-full bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm text-pb-text" />
      </div>

      {r.status === 'pending' && <p className="text-[11.5px] text-pb-faintest mt-2">{approveHint(r)}</p>}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        {r.status === 'pending' && (
          <Btn sm variant="primary" disabled={busy} onClick={() => run(() => api.approvePlayerRegistration(r.id), `${name} approved`)} data-approve>Approve</Btn>
        )}
        <Btn sm disabled={busy} onClick={() => run(() => api.updatePlayerRegistration(r.id, { contacted: !r.contacted_at }))} data-contacted>
          {r.contacted_at ? 'Not contacted yet' : 'Mark contacted'}
        </Btn>
        {r.status !== 'archived'
          ? <Btn sm variant="ghost" disabled={busy} data-archive
              onClick={() => {
                if (r.kind === 'new' && !window.confirm(`Archive ${name}? They will lose access to the Player Dashboard. You can restore them later.`)) return
                run(() => api.archivePlayerRegistration(r.id), `${name} archived`)
              }}>Archive</Btn>
          : <Btn sm variant="ghost" disabled={busy} onClick={() => run(() => api.restorePlayerRegistration(r.id), `${name} restored`)} data-restore>Restore</Btn>}
      </div>
    </div>
  )
}

export default function AdminPlayerRegistrations() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('pending')
  const [role, setRole] = useState('')
  const [interest, setInterest] = useState('')
  const [q, setQ] = useState('')

  const load = useCallback(() => {
    api.listPlayerRegistrations().then(setData).catch((e) => setError(e?.message || 'Could not load registrations.'))
  }, [])
  useEffect(() => { load() }, [load])

  const interestLabels = useMemo(() => Object.fromEntries((data?.interests || []).map((i) => [i.key, i.label])), [data])
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase()
    return (data?.registrations || []).filter((r) =>
      (tab === 'all' || r.status === tab)
      && (!role || r.role === role)
      && (!interest || r.interests.includes(interest))
      && (!term || `${r.first_name} ${r.last_name} ${r.email} ${r.phone} ${r.player_name || ''}`.toLowerCase().includes(term)))
  }, [data, tab, role, interest, q])

  const onChanged = (updated) => setData((d) => ({
    ...d,
    registrations: d.registrations.map((r) => (r.id === updated.id ? updated : r)),
    counts: Object.fromEntries(['pending', 'approved', 'archived'].map((s) => [s,
      d.registrations.map((r) => (r.id === updated.id ? updated : r)).filter((r) => r.status === s).length])),
  }))

  const exportCsv = () => {
    const head = ['First name', 'Surname', 'Role', 'Kind', 'Claimed record', 'Mobile', 'Email', 'Date of birth', 'Years played',
      'Grades', 'Interests', 'Happy to be contacted', 'Notes', 'Status', 'Contacted', 'Club note', 'Added']
    const lines = rows.map((r) => [r.first_name, r.last_name, r.role_label, r.kind === 'claim' ? 'Claimed old record' : 'New',
      r.player_name && r.kind === 'claim' ? r.player_name : '', r.phone, r.email, r.date_of_birth || '', r.years_played,
      r.grades_played, r.interests.map((k) => interestLabels[k] || k).join('; '), r.contact_consent ? 'Yes' : 'No', r.notes,
      r.status, r.contacted_at ? fmtDate(r.contacted_at) : '', r.admin_note, fmtDate(r.created_at)].map(csvCell).join(','))
    const blob = new Blob([[head.join(','), ...lines].join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'player-dashboard-registrations.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const counts = data?.counts || {}
  const selectCls = 'bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-1.5 text-sm text-pb-text'

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl" data-player-registrations-admin>
        <h1 className="font-display font-bold text-2xl text-pb-text">Registrations</h1>
        <p className="text-sm text-pb-faint mt-1 mb-4">
          People who couldn’t find their name on the Player Dashboard and added themselves, or found their old record. Welcome them, approve them onto the name list and follow up about playing or helping out.
        </p>
        {data && !data.registration_enabled && (
          <p className="text-[12.5px] rounded-lg px-3 py-2 mb-4" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
            Registration is switched off, so nobody new can add themselves. Turn it on in <Link className="underline" to="/admin/player-dashboard">Player Dashboard</Link>.
          </p>
        )}
        {error && <div role="alert" className="text-sm text-pb-red mb-4">{error}</div>}
        {!data && !error && <div className="text-sm text-pb-faint">Loading…</div>}
        {data && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Segmented sm value={tab} onChange={setTab}
                options={STATUS_TABS.map((t) => ({ value: t.value, label: t.value === 'all' ? t.label : `${t.label} ${counts[t.value] || 0}` }))} />
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Search value={q} onChange={setQ} placeholder="Search name, mobile, email…" className="flex-1 min-w-[180px]" />
              <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className={selectCls}>
                <option value="">Every role</option>
                {(data.roles || []).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
              <select aria-label="Interest" value={interest} onChange={(e) => setInterest(e.target.value)} className={selectCls}>
                <option value="">Any interest</option>
                {(data.interests || []).map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}
              </select>
              <Btn sm onClick={exportCsv} disabled={!rows.length}>Export CSV</Btn>
            </div>
            {rows.length === 0 ? (
              <div className="pb-card p-6 text-center text-sm text-pb-faint" data-registrations-empty>
                {(data.registrations || []).length === 0
                  ? 'Nobody has registered yet. When someone taps “Can’t find your name?” on the Player Dashboard and adds themselves, they show here.'
                  : 'Nobody matches these filters.'}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {rows.map((r) => <Row key={r.id} r={r} interestLabels={interestLabels} onChanged={onChanged} />)}
              </div>
            )}
          </>
        )}
      </div>
    </BetterStatsLayout>
  )
}
