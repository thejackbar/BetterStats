import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import {
  Button, Field, TextInput, TextArea, Select, SegButtons, SearchInput,
  FilterPill, Badge, Modal, Note, Empty, FieldLabel,
} from '../../components/admin/ui'
import { BroadcastLine, BROADCAST_TONES } from '../../components/admin/AdminBroadcastBanner'

// Better HQ → Comms → Dashboard Messages. A super admin writes a one-line
// message for club admins, picks who it reaches and what makes it go away, and
// it appears at the top of their admin dashboard (routers/admin_broadcasts.py).

const TONE_TABS = Object.entries(BROADCAST_TONES).map(([key, t]) => ({ key, label: t.label }))

const AUDIENCE_TABS = [
  { key: 'all', label: 'Every club' },
  { key: 'clubs', label: 'Chosen clubs' },
  { key: 'users', label: 'Chosen users' },
]

const ROLE_OPTIONS = [
  { key: 'all_admins', label: 'Everyone with admin access', hint: 'Club Admins and members given access to the admin app.' },
  { key: 'club_admins', label: 'Club Admins only', hint: 'Leaves out members with limited admin access.' },
  { key: 'primary', label: 'Primary Club Admin only', hint: 'One person per club: whoever holds the account.' },
]

const PERSISTENCE_OPTIONS = [
  { key: 'until_cleared', label: 'Until I clear it', hint: 'Recipients cannot close it. It stays until you clear it here, or it reaches its stop time.' },
  { key: 'dismissible', label: 'Until each person closes it', hint: 'Each recipient can close it with the ✕. It stays for everyone who has not.' },
  { key: 'view_once_user', label: 'Until each person has seen it once', hint: 'Shows on a person’s next dashboard visit, then not again for them.' },
  { key: 'view_once_club', label: 'Until someone at the club has seen it once', hint: 'The first admin at a club to open the dashboard sees it, then it is gone for that whole club.' },
]
const PERSISTENCE_SHORT = {
  until_cleared: 'Until cleared',
  dismissible: 'Until each person closes it',
  view_once_user: 'Seen once by each person',
  view_once_club: 'Seen once per club',
}

const STOP_OPTIONS = [
  { key: 'never', label: 'No stop time' },
  { key: '24', label: 'After 1 day' },
  { key: '72', label: 'After 3 days' },
  { key: '168', label: 'After 1 week' },
  { key: '336', label: 'After 2 weeks' },
  { key: '720', label: 'After 30 days' },
  { key: 'at', label: 'At a set date and time' },
]

const STATUS = {
  live: { label: 'Live', tone: 'ok' },
  scheduled: { label: 'Scheduled', tone: 'accent' },
  complete: { label: 'Reached everyone', tone: 'calm' },
  expired: { label: 'Expired', tone: 'calm' },
  cleared: { label: 'Cleared', tone: 'block' },
}

const LIST_FILTERS = [
  { key: 'current', label: 'Live & scheduled', match: s => s === 'live' || s === 'scheduled' },
  { key: 'ended', label: 'Ended', match: s => s === 'expired' || s === 'cleared' || s === 'complete' },
  { key: 'all', label: 'All', match: () => true },
]

const fmtWhen = iso => iso
  ? new Date(iso).toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
  : '—'

// <input type="datetime-local"> works in local time with no zone, so convert
// both ways here and send the server a real instant.
const toLocalInput = iso => {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const fromLocalInput = v => (v ? new Date(v).toISOString() : null)

const blankForm = () => ({
  message: '', tone: 'info', link_url: '', link_label: '',
  audience: 'all', audience_roles: 'all_admins', org_ids: [], user_ids: [],
  persistence: 'until_cleared', start: 'now', starts_at: '', stop: 'never', expires_at: '',
})

function formFrom(b) {
  return {
    message: b.message, tone: b.tone, link_url: b.link_url || '', link_label: b.link_label || '',
    audience: b.audience, audience_roles: b.audience_roles, org_ids: b.org_ids || [], user_ids: b.user_ids || [],
    persistence: b.persistence,
    start: 'at', starts_at: toLocalInput(b.starts_at),
    stop: b.expires_at ? 'at' : 'never', expires_at: toLocalInput(b.expires_at),
  }
}

function audienceSummary(b) {
  const roles = { all_admins: '', club_admins: ' · Club Admins only', primary: ' · Primary Club Admin only' }[b.audience_roles] || ''
  if (b.audience === 'clubs') {
    const names = b.club_names || []
    return `${names.slice(0, 3).join(', ')}${names.length > 3 ? ` +${names.length - 3} more` : ''}${roles}`
  }
  if (b.audience === 'users') {
    const names = b.user_names || []
    return `${names.slice(0, 3).join(', ')}${names.length > 3 ? ` +${names.length - 3} more` : ''}`
  }
  return `Every club${roles}`
}

// ── Club and user pickers ──────────────────────────────────────────────────

function ClubPicker({ clubs, value, onChange }) {
  const [q, setQ] = useState('')
  const chosen = new Set(value)
  const needle = q.trim().toLowerCase()
  const shown = needle ? clubs.filter(c => c.name.toLowerCase().includes(needle)) : clubs
  const toggle = id => onChange(chosen.has(id) ? value.filter(v => v !== id) : [...value, id])
  const byId = Object.fromEntries(clubs.map(c => [c.id, c]))
  return (
    <div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map(id => (
            <button key={id} type="button" onClick={() => toggle(id)}
              className="text-[12px] rounded-full px-2.5 py-1 border border-pb-hairline2 text-pb-text hover:border-pb-red/50"
              aria-label={`Remove ${byId[id]?.name || 'club'}`}>
              {byId[id]?.name || 'Unknown club'} ✕
            </button>
          ))}
        </div>
      )}
      <SearchInput value={q} onChange={setQ} placeholder="Search clubs…" className="!max-w-none" />
      <div className="mt-2 max-h-64 overflow-y-auto pb-scroll border border-pb-hairline rounded-lg divide-y divide-pb-hairline">
        {shown.length === 0 && <Empty>No club matches “{q}”.</Empty>}
        {shown.slice(0, 300).map(c => (
          <label key={c.id} className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-pb-surface2">
            <input type="checkbox" checked={chosen.has(c.id)} onChange={() => toggle(c.id)} className="accent-pb-accent" />
            <span className="min-w-0 flex-1 text-[13px] text-pb-text truncate">{c.name}</span>
            <span className="font-mono text-[10px] text-pb-faintest shrink-0">{c.users.length} admin{c.users.length === 1 ? '' : 's'}</span>
          </label>
        ))}
      </div>
      <p className="font-mono text-[10px] text-pb-faint mt-1.5">{value.length} club{value.length === 1 ? '' : 's'} chosen</p>
    </div>
  )
}

function UserPicker({ clubs, value, onChange }) {
  const [q, setQ] = useState('')
  const chosen = new Set(value)
  const needle = q.trim().toLowerCase()
  const groups = clubs
    .map(c => {
      const clubHit = !needle || c.name.toLowerCase().includes(needle)
      const users = clubHit ? c.users : c.users.filter(u =>
        [u.name, u.username, u.email].some(s => (s || '').toLowerCase().includes(needle)))
      return { ...c, users }
    })
    .filter(c => c.users.length)
  const allUsers = Object.fromEntries(clubs.flatMap(c => c.users.map(u => [u.id, { ...u, club: c.name }])))
  const toggle = id => onChange(chosen.has(id) ? value.filter(v => v !== id) : [...value, id])
  const toggleClub = c => {
    const ids = c.users.map(u => u.id)
    const all = ids.every(id => chosen.has(id))
    onChange(all ? value.filter(v => !ids.includes(v)) : [...new Set([...value, ...ids])])
  }
  return (
    <div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map(id => (
            <button key={id} type="button" onClick={() => toggle(id)}
              className="text-[12px] rounded-full px-2.5 py-1 border border-pb-hairline2 text-pb-text hover:border-pb-red/50"
              aria-label={`Remove ${allUsers[id]?.name || 'user'}`}>
              {allUsers[id]?.name || 'No longer an admin'}
              {allUsers[id] && <span className="text-pb-faint"> · {allUsers[id].club}</span>} ✕
            </button>
          ))}
        </div>
      )}
      <SearchInput value={q} onChange={setQ} placeholder="Search a club, a name or an email…" className="!max-w-none" />
      <div className="mt-2 max-h-72 overflow-y-auto pb-scroll border border-pb-hairline rounded-lg">
        {groups.length === 0 && <Empty>No admin matches “{q}”.</Empty>}
        {groups.slice(0, 150).map(c => {
          const all = c.users.every(u => chosen.has(u.id))
          return (
            <div key={c.id} className="border-b border-pb-hairline last:border-b-0">
              <div className="flex items-center gap-2 px-3 py-2 bg-pb-surface2">
                <span className="min-w-0 flex-1 text-[12.5px] font-semibold text-pb-text truncate">{c.name}</span>
                <button type="button" onClick={() => toggleClub(c)}
                  className="font-mono text-[10px] text-pb-faint hover:text-pb-text shrink-0 py-1">
                  {all ? 'CLEAR' : 'ALL'}
                </button>
              </div>
              {c.users.map(u => (
                <label key={u.id} className="flex items-start gap-3 px-3 py-2 cursor-pointer hover:bg-pb-surface2">
                  <input type="checkbox" checked={chosen.has(u.id)} onChange={() => toggle(u.id)} className="accent-pb-accent mt-1" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] text-pb-text truncate">
                      {u.name}
                      {u.is_primary && <span className="font-mono text-[9px] text-pb-faint ml-2">PRIMARY</span>}
                      {u.role === 'club_member' && <span className="font-mono text-[9px] text-pb-faint ml-2">MEMBER</span>}
                    </span>
                    {u.email && <span className="block text-[11.5px] text-pb-faint truncate">{u.email}</span>}
                  </span>
                </label>
              ))}
            </div>
          )
        })}
      </div>
      <p className="font-mono text-[10px] text-pb-faint mt-1.5">{value.length} user{value.length === 1 ? '' : 's'} chosen</p>
    </div>
  )
}

// ── Composer ───────────────────────────────────────────────────────────────

function Composer({ clubs, editing, onSaved, onCancel }) {
  const [f, setF] = useState(() => (editing ? formFrom(editing) : blankForm()))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = patch => setF(prev => ({ ...prev, ...patch }))

  // How far it reaches, worked out from the same list the pickers draw, so the
  // figure moves as clubs and people are ticked.
  const reach = useMemo(() => {
    let people = []
    if (f.audience === 'users') {
      const ids = new Set(f.user_ids)
      people = clubs.flatMap(c => c.users.filter(u => ids.has(u.id)).map(u => ({ ...u, club: c.id })))
    } else {
      const pool = f.audience === 'clubs' ? clubs.filter(c => f.org_ids.includes(c.id)) : clubs
      people = pool.flatMap(c => c.users.map(u => ({ ...u, club: c.id })))
      if (f.audience_roles === 'club_admins') people = people.filter(u => u.role === 'club_admin')
      if (f.audience_roles === 'primary') people = people.filter(u => u.role === 'club_admin' && u.is_primary)
    }
    return { people: people.length, clubs: new Set(people.map(p => p.club)).size }
  }, [clubs, f.audience, f.audience_roles, f.org_ids, f.user_ids])

  const submit = async () => {
    setError('')
    if (!f.message.trim()) { setError('Write a message.'); return }
    if (f.audience === 'clubs' && !f.org_ids.length) { setError('Pick at least one club.'); return }
    if (f.audience === 'users' && !f.user_ids.length) { setError('Pick at least one user.'); return }
    if (f.start === 'at' && !f.starts_at) { setError('Choose when it starts.'); return }
    if (f.stop === 'at' && !f.expires_at) { setError('Choose when it stops.'); return }
    const startIso = f.start === 'at' ? fromLocalInput(f.starts_at) : new Date().toISOString()
    let expires = null
    if (f.stop === 'at') expires = fromLocalInput(f.expires_at)
    else if (f.stop !== 'never') expires = new Date(new Date(startIso).getTime() + Number(f.stop) * 3600e3).toISOString()
    const body = {
      message: f.message, tone: f.tone,
      link_url: f.link_url.trim() || null, link_label: f.link_label.trim() || null,
      audience: f.audience, audience_roles: f.audience_roles,
      org_ids: f.audience === 'clubs' ? f.org_ids : [],
      user_ids: f.audience === 'users' ? f.user_ids : [],
      persistence: f.persistence, starts_at: startIso, expires_at: expires,
    }
    setSaving(true)
    try {
      const saved = editing
        ? await api.superUpdateBroadcast(editing.id, body)
        : await api.superCreateBroadcast(body)
      onSaved(saved, !!editing)
    } catch (e) {
      setError(e.message || 'Could not save the message')
    } finally {
      setSaving(false)
    }
  }

  const previewItem = {
    id: 'preview', message: f.message.trim() || 'Your message will appear here.', tone: f.tone,
    link_url: f.link_url.trim() || null, link_label: f.link_label.trim() || null,
  }
  const persistHint = PERSISTENCE_OPTIONS.find(o => o.key === f.persistence)?.hint

  return (
    <div className="pb-card p-4 sm:p-5 mb-6 space-y-5" data-testid="broadcast-composer">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display font-bold text-[17px] text-pb-text">{editing ? 'Edit message' : 'New message'}</h2>
        <Button variant="quiet" size="sm" onClick={onCancel}>Cancel</Button>
      </div>

      <Field label="Message" hint={`${f.message.length}/500 · one or two sentences reads best on a phone.`}>
        <TextArea value={f.message} maxLength={500} onChange={e => set({ message: e.target.value })}
          placeholder="e.g. BetterCricket will be offline for maintenance on Sunday 6 October from 9pm to 10pm AWST." />
      </Field>

      <Field label="Tone" composite>
        <SegButtons tabs={TONE_TABS} value={f.tone} onChange={tone => set({ tone })} />
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_200px] gap-3">
        <Field label="Link (optional)" hint="https://… for another site, or /admin/… for a page in the app.">
          <TextInput value={f.link_url} onChange={e => set({ link_url: e.target.value })} placeholder="/admin/account" />
        </Field>
        <Field label="Link text">
          <TextInput value={f.link_label} maxLength={60} onChange={e => set({ link_label: e.target.value })} placeholder="Find out more" />
        </Field>
      </div>

      <div>
        <FieldLabel>Preview</FieldLabel>
        <BroadcastLine item={previewItem} onDismiss={f.persistence !== 'until_cleared' ? () => {} : undefined} />
      </div>

      <div className="space-y-3">
        <Field label="Who sees it" composite>
          <SegButtons tabs={AUDIENCE_TABS} value={f.audience} onChange={audience => set({ audience })} />
        </Field>
        {f.audience !== 'users' && (
          <Field label="Which admins at each club" hint={ROLE_OPTIONS.find(o => o.key === f.audience_roles)?.hint}>
            <Select value={f.audience_roles} onChange={e => set({ audience_roles: e.target.value })}>
              {ROLE_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </Select>
          </Field>
        )}
        {f.audience === 'clubs' && <ClubPicker clubs={clubs} value={f.org_ids} onChange={org_ids => set({ org_ids })} />}
        {f.audience === 'users' && <UserPicker clubs={clubs} value={f.user_ids} onChange={user_ids => set({ user_ids })} />}
        <p className="text-[12.5px] text-pb-dim" data-testid="broadcast-reach">
          Reaches <strong className="text-pb-text">{reach.people}</strong> {reach.people === 1 ? 'person' : 'people'} at{' '}
          <strong className="text-pb-text">{reach.clubs}</strong> club{reach.clubs === 1 ? '' : 's'}.
          {' '}Archived clubs are never included.
        </p>
      </div>

      <Field label="Stays until" hint={persistHint}>
        <Select value={f.persistence} onChange={e => set({ persistence: e.target.value })}>
          {PERSISTENCE_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </Select>
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-2">
          <Field label="Starts">
            <Select value={f.start} onChange={e => set({ start: e.target.value })}>
              <option value="now">{editing ? 'Now' : 'As soon as I send it'}</option>
              <option value="at">At a set date and time</option>
            </Select>
          </Field>
          {f.start === 'at' && (
            <TextInput type="datetime-local" aria-label="Start date and time" value={f.starts_at}
              onChange={e => set({ starts_at: e.target.value })} />
          )}
        </div>
        <div className="space-y-2">
          <Field label="Stops">
            <Select value={f.stop} onChange={e => set({ stop: e.target.value })}>
              {STOP_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </Select>
          </Field>
          {f.stop === 'at' && (
            <TextInput type="datetime-local" aria-label="Stop date and time" value={f.expires_at}
              onChange={e => set({ expires_at: e.target.value })} />
          )}
        </div>
      </div>
      <p className="text-[11.5px] text-pb-faintest -mt-3">
        A stop time applies whatever “stays until” says, and you can clear any message early from the list below.
      </p>

      {error && <p className="text-[12.5px] text-pb-red" role="alert">{error}</p>}
      <div className="flex flex-wrap gap-2 justify-end">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={saving}>
          {saving ? 'Saving…' : editing ? 'Save changes' : f.start === 'at' ? 'Schedule message' : 'Send message'}
        </Button>
      </div>
    </div>
  )
}

// ── Who has seen it ────────────────────────────────────────────────────────

function RecipientsModal({ broadcast, onClose }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.superBroadcastRecipients(broadcast.id)
      .then(d => setRows(d?.items || []))
      .catch(e => setError(e.message || 'Could not load recipients'))
  }, [broadcast.id])
  const seen = rows ? rows.filter(r => r.seen_at).length : 0
  return (
    <Modal title="Who it reaches" subtitle={rows ? `${seen} of ${rows.length} have seen it` : undefined}
      onClose={onClose} width={620}>
      {error && <p className="text-pb-red text-sm py-4">{error}</p>}
      {!rows && !error && <Empty>Loading…</Empty>}
      {rows && rows.length === 0 && <Empty>Nobody is in this audience right now.</Empty>}
      {rows && rows.length > 0 && (
        <div className="divide-y divide-pb-hairline mb-3">
          {rows.map(r => (
            <div key={r.user_id} className="py-2.5 flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-[13px] text-pb-text truncate">
                  {r.name}{r.is_primary && <span className="font-mono text-[9px] text-pb-faint ml-2">PRIMARY</span>}
                </div>
                <div className="text-[11.5px] text-pb-faint truncate">{r.club_name}</div>
              </div>
              <div className="font-mono text-[10px] text-pb-faint sm:text-right shrink-0">
                {r.seen_at ? `SEEN ${fmtWhen(r.seen_at)}` : 'NOT SEEN YET'}
                {r.dismissed_at && <div>CLOSED {fmtWhen(r.dismissed_at)}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function SuperBroadcasts() {
  const [items, setItems] = useState(null)
  const [clubs, setClubs] = useState([])
  const [error, setError] = useState('')
  const [composer, setComposer] = useState(null) // null | 'new' | broadcast
  const [filter, setFilter] = useState('current')
  const [recipientsFor, setRecipientsFor] = useState(null)
  const [busy, setBusy] = useState('')

  const load = () => api.superListBroadcasts()
    .then(d => setItems(d?.items || []))
    .catch(e => setError(e.message || 'Could not load messages'))

  useEffect(() => {
    load()
    api.superBroadcastAudience().then(d => setClubs(d?.clubs || [])).catch(() => {})
  }, [])

  const replace = row => setItems(list => (list || []).map(i => (i.id === row.id ? row : i)))

  const act = async (b, fn, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(b.id)
    try {
      const row = await fn(b.id)
      if (row) replace(row)
      else setItems(list => list.filter(i => i.id !== b.id))
    } catch (e) {
      window.alert(e.message || 'That did not work')
    } finally {
      setBusy('')
    }
  }

  const counts = useMemo(() => Object.fromEntries(LIST_FILTERS.map(fl =>
    [fl.key, (items || []).filter(i => fl.match(i.status)).length])), [items])
  const shown = (items || []).filter(i => LIST_FILTERS.find(fl => fl.key === filter).match(i.status))

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
          <div className="min-w-0">
            <h1 className="font-display font-bold text-2xl text-pb-text">Dashboard Messages</h1>
            <p className="text-pb-faint text-sm mt-1">
              A short message at the top of the club admin dashboard, for every club, chosen clubs or chosen people.
            </p>
          </div>
          {!composer && (
            <Button variant="primary" onClick={() => setComposer('new')}>New message</Button>
          )}
        </div>

        {composer && (
          <Composer
            key={composer === 'new' ? 'new' : composer.id}
            clubs={clubs}
            editing={composer === 'new' ? null : composer}
            onCancel={() => setComposer(null)}
            onSaved={(row, wasEdit) => {
              setItems(list => (wasEdit ? (list || []).map(i => (i.id === row.id ? row : i)) : [row, ...(list || [])]))
              setComposer(null)
              setFilter('current')
            }}
          />
        )}

        <div className="flex flex-wrap gap-2 mb-3">
          {LIST_FILTERS.map(fl => (
            <FilterPill key={fl.key} active={filter === fl.key} onClick={() => setFilter(fl.key)} count={counts[fl.key]}>
              {fl.label}
            </FilterPill>
          ))}
        </div>

        {error && <Note toneKey="block">{error}</Note>}
        {items === null && !error && <Empty>Loading…</Empty>}
        {items && shown.length === 0 && (
          <Empty>{filter === 'current' ? 'No messages are showing right now.' : 'Nothing here.'}</Empty>
        )}

        <div className="space-y-3">
          {shown.map(b => {
            const st = STATUS[b.status] || STATUS.live
            const tracksViews = b.persistence !== 'until_cleared'
            return (
              <div key={b.id} className="pb-card p-4" data-testid="broadcast-row">
                <BroadcastLine item={b} />
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-pb-dim">
                  <Badge toneKey={st.tone}>{st.label}</Badge>
                  <span><span className="text-pb-faint">To:</span> {audienceSummary(b)}</span>
                  <span><span className="text-pb-faint">Stays:</span> {PERSISTENCE_SHORT[b.persistence]}</span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10.5px] text-pb-faint">
                  <span>STARTS {fmtWhen(b.starts_at)}</span>
                  <span>{b.expires_at ? `STOPS ${fmtWhen(b.expires_at)}` : 'NO STOP TIME'}</span>
                  {b.cleared_at && <span>CLEARED {fmtWhen(b.cleared_at)}</span>}
                  <span>
                    SEEN BY {b.seen}/{b.recipients}
                    {b.persistence === 'view_once_club' && ` · ${b.clubs_seen}/${b.clubs} CLUBS`}
                    {b.persistence === 'dismissible' && ` · CLOSED BY ${b.dismissed}`}
                  </span>
                  {b.created_by && <span>BY {b.created_by.toUpperCase()}</span>}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Button size="sm" variant="soft" onClick={() => setComposer(b)} disabled={busy === b.id}>Edit</Button>
                  <Button size="sm" variant="secondary" onClick={() => setRecipientsFor(b)}>Who has seen it</Button>
                  {b.status === 'cleared' ? (
                    <Button size="sm" variant="secondary" disabled={busy === b.id}
                      onClick={() => act(b, api.superRestoreBroadcast)}>Restore</Button>
                  ) : (
                    <Button size="sm" variant="secondary" disabled={busy === b.id}
                      onClick={() => act(b, api.superClearBroadcast, 'Clear this message from every dashboard now? You can restore it later.')}>
                      Clear now
                    </Button>
                  )}
                  {tracksViews && b.seen > 0 && (
                    <Button size="sm" variant="quiet" disabled={busy === b.id}
                      onClick={() => act(b, api.superResetBroadcastViews, 'Forget who has seen or closed this, so it shows to everyone again?')}>
                      Show again to everyone
                    </Button>
                  )}
                  <Button size="sm" variant="quiet-danger" disabled={busy === b.id}
                    onClick={() => act(b, async id => { await api.superDeleteBroadcast(id); return null },
                      'Delete this message for good? Its view history goes with it.')}>
                    Delete
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
      {recipientsFor && <RecipientsModal broadcast={recipientsFor} onClose={() => setRecipientsFor(null)} />}
    </AdminLayout>
  )
}
