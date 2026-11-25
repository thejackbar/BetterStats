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
import { battingHandLabel, bowlingLabel } from '../../lib/playerAttributes'

const STATUS_TABS = [
  { value: 'pending', label: 'Needs review' },
  { value: 'approved', label: 'Signed up' },
  { value: 'archived', label: 'Archived' },
  { value: 'all', label: 'All' },
]
const CRICKET_ROLE_LABELS = { 'All Rounder': 'All-rounder', 'Wicketkeeper-Batter': 'Keeper and batter' }

function fmtDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}

function csvCell(v) {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

// "Batter · Right handed · Off spin · Opening batter · Overseas (England)" from what they told us.
export function playingSummary(pl = {}) {
  const bits = []
  if (pl.player_role) bits.push(CRICKET_ROLE_LABELS[pl.player_role] || pl.player_role)
  const hand = battingHandLabel(pl.batting_hand)
  if (hand) bits.push(hand)
  if (pl.bowling_type) bits.push(bowlingLabel(pl.bowling_action, pl.bowling_type))
  if (pl.is_opening_batsman) bits.push('Opening batter')
  if (pl.is_overseas) bits.push(pl.overseas_country ? `Overseas (${pl.overseas_country})` : 'Overseas')
  return bits.join(' · ')
}

// What the registration is, in one tag: how a claimed record was proven, or what is waiting.
function kindTag(r) {
  if (r.kind === 'claim') {
    if (r.matched_by === 'mobile') return { tone: 'accent', text: 'Matched to their record by mobile', title: 'The mobile they typed is the one on their record' }
    if (r.matched_by === 'pin') return { tone: 'accent', text: 'Matched to their record by PIN', title: 'They gave the last 4 digits of the mobile on their record' }
    if (r.matched_by === 'admin') return { tone: 'accent', text: 'Confirmed by an admin' }
    return { tone: 'amber', text: 'Says this is their record' }
  }
  return { tone: 'faint', text: 'New to the club’s records' }
}

function approveHint(r) {
  if (r.kind === 'claim') {
    return `Their record (${r.player_name}) has no mobile, so nothing proves it is them. Approve once you are sure: the details they gave are added where the record is empty.`
  }
  return r.role === 'current_player'
    ? 'Approve to make them a player (selection, votes, a public profile) and put them on the Player Dashboard name list.'
    : 'Approve to put them on the Player Dashboard name list. They stay off selection boards.'
}

function Block({ label, children, attr }) {
  return (
    <div className="mt-3" {...attr}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">{label}</div>
      <div className="text-sm text-pb-dim">{children}</div>
    </div>
  )
}

function Item({ label, children }) {
  return <div className="min-w-0"><span className="text-pb-faint">{label} </span><span className="text-pb-text break-words">{children}</span></div>
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
  const tag = kindTag(r)
  const cricket = playingSummary(r.playing)
  const wantsToPlay = r.role === 'current_player' || r.interests.includes('play')
  const offTheList = r.kind === 'claim' && r.status !== 'archived' && r.is_player && (r.player_status === 'inactive' || r.player_dormant)
  const isClaim = r.kind === 'claim'

  return (
    <div className="pb-card p-4" data-registration-row={r.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-display font-bold text-lg text-pb-text break-words">{name}</div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            <Tag tone="accent">{r.role_label}</Tag>
            <Tag tone={tag.tone} title={tag.title}>{tag.text}</Tag>
            {r.status === 'pending' && <Tag tone="amber">Needs review</Tag>}
            {r.status === 'archived' && <Tag tone="faint">Archived</Tag>}
            {r.contacted_at && <Tag tone="accent">Contacted {fmtDate(r.contacted_at)}</Tag>}
          </div>
        </div>
        <div className="text-[11.5px] text-pb-faintest shrink-0">Signed up {fmtDate(r.created_at)}</div>
      </div>

      {isClaim && (
        <p className="text-[12.5px] text-pb-dim mt-2" data-registration-record>
          Their record: <b className="text-pb-text">{r.player_name}</b>
          {r.last_played ? `, last game ${fmtDate(r.last_played)}` : ', no games on record'}
          {r.player_status === 'inactive' ? ', marked inactive' : (r.player_dormant ? ', dormant' : '')}.
          {r.applied.length > 0 && <> Added to it: {r.applied.join(', ')}.</>}
        </p>
      )}

      {offTheList && wantsToPlay && (
        <div className="mt-3 rounded-lg px-3 py-2.5 text-[12.5px] flex flex-wrap items-center justify-between gap-2"
          style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }} data-registration-reactivate>
          <span className="min-w-0">
            {r.role === 'current_player' ? 'Says they’re playing' : 'Interested in playing again'}, but {r.player_status === 'inactive' ? 'marked inactive' : 'dormant'}, so off availability and selection.
          </span>
          <Btn sm variant="soft" disabled={busy} onClick={() => run(() => api.reactivateRegisteredPlayer(r.id), `${name} is active again`)} data-reactivate>
            Make active again
          </Btn>
        </div>
      )}

      <Block label="Contact" attr={{ 'data-registration-contact': true }}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
          <Item label="Mobile">{r.phone ? <a className="underline" href={`tel:${r.phone.replace(/\s/g, '')}`}>{r.phone}</a> : <span className="text-pb-faintest">none</span>}</Item>
          <Item label="Email">{r.email ? <a className="underline" href={`mailto:${r.email}`}>{r.email}</a> : <span className="text-pb-faintest">none given</span>}</Item>
          {r.date_of_birth && <Item label="Born">{fmtDate(r.date_of_birth)}</Item>}
        </div>
        <div className="mt-1 text-[12.5px]" data-registration-consent>
          {r.contact_consent
            ? <span className="text-pb-accent">Happy to be contacted about playing, volunteering and club news.</span>
            : <span className="text-pb-faint">Didn’t tick the box to be contacted. Their email stays here, not on their player record.</span>}
        </div>
      </Block>

      {(cricket || r.years_played || r.grades_played) && (
        <Block label="Their cricket" attr={{ 'data-registration-cricket': true }}>
          {cricket && <div className="text-pb-text">{cricket}</div>}
          {(r.years_played || r.grades_played) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 mt-1">
              {r.years_played && <Item label="Years at the club">{r.years_played}</Item>}
              {r.grades_played && <Item label="Grades">{r.grades_played}</Item>}
            </div>
          )}
        </Block>
      )}

      {r.interests.length > 0 && (
        <Block label="Would like to help with" attr={{ 'data-registration-interests': true }}>
          <div className="flex flex-wrap gap-1.5">
            {r.interests.map((k) => <Tag key={k} tone="faint">{interestLabels[k] || k}</Tag>)}
          </div>
        </Block>
      )}

      {r.notes && (
        <Block label="Anything else, in their words" attr={{ 'data-registration-notes': true }}>
          <p className="whitespace-pre-wrap break-words text-pb-text">{r.notes}</p>
        </Block>
      )}

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
  const [tab, setTab] = useState(null) // chosen once the list lands
  const [role, setRole] = useState('')
  const [interest, setInterest] = useState('')
  const [q, setQ] = useState('')

  const load = useCallback(() => {
    api.listPlayerRegistrations().then((d) => {
      setData(d)
      // Open on what needs doing; with nothing to review, on who has signed up.
      setTab((t) => t || ((d.counts?.pending || 0) > 0 ? 'pending' : 'approved'))
    }).catch((e) => setError(e?.message || 'Could not load registrations.'))
  }, [])
  useEffect(() => { load() }, [load])

  const interestLabels = useMemo(() => Object.fromEntries((data?.interests || []).map((i) => [i.key, i.label])), [data])
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase()
    return (data?.registrations || []).filter((r) =>
      (!tab || tab === 'all' || r.status === tab)
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
    const head = ['First name', 'Surname', 'Connection', 'Kind', 'Their record', 'Mobile', 'Email', 'Date of birth', 'Cricket',
      'Years at the club', 'Grades', 'Would like to help with', 'Happy to be contacted', 'Anything else', 'Status', 'Contacted', 'Club note', 'Signed up']
    const lines = rows.map((r) => [r.first_name, r.last_name, r.role_label, kindTag(r).text,
      r.kind === 'claim' ? r.player_name : '', r.phone, r.email, r.date_of_birth || '', playingSummary(r.playing), r.years_played,
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
          Everyone who signed up on the Player Dashboard. Past players matched to their own record go straight to Signed up; only new people and records nobody could prove wait for review.
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
              <Segmented sm value={tab || 'pending'} onChange={setTab}
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
