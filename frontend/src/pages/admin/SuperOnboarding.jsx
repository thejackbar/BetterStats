import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const STATUSES = ['new', 'contacted', 'onboarded', 'closed']

const STATUS_STYLE = {
  new:       'bg-accent/15 text-accent border-accent/40',
  contacted: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  onboarded: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  closed:    'bg-pb-surface2 text-pb-faint border-pb-hairline',
}

const SELECT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent'

function fmtDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Webinar registrations — a SEPARATE list from the onboarding enquiries above,
// on purpose. Somebody who signed up to watch a demo has not asked to be
// onboarded, and folding a hundred of them into that queue would bury the
// clubs who did ask. The campaign columns are what make this reconcilable
// against Meta's own attributed numbers; the two will not match, because Meta
// counts on a 7-day click window.
function WebinarRegistrations() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Open by default. This list is the answer to "did that registration land?",
  // and a panel that opens closed makes a real registration look like a missing
  // one until somebody finds the toggle.
  const [open, setOpen] = useState(true)
  const [reminding, setReminding] = useState(false)
  const [reminderNote, setReminderNote] = useState('')
  const [pushing, setPushing] = useState(false)

  const load = () => api.superWebinarRegistrations()
    .then((data) => { setRows(Array.isArray(data) ? data : []); setError('') })
    .catch((e) => setError(e.message || 'Could not load registrations.'))
    .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  // The escape hatch, not the mechanism: the hourly sweep is what normally
  // sends these. It is here because the reminder has one chance to be useful,
  // and pressing it twice emails nobody twice — the claim is on the row.
  const remind = async () => {
    if (reminding) return
    if (!window.confirm(
      'Email every registrant who has not had the day-of reminder yet?\n\n'
      + 'Nobody is emailed twice, and nothing is sent outside the few hours '
      + 'before the session starts.'
    )) return
    setReminding(true)
    setReminderNote('')
    try {
      const r = await api.superSendWebinarReminders()
      setReminderNote(
        r?.skipped
          ? 'Not sent: outside the reminder window (it opens a few hours before the session).'
          : `Sent ${r?.sent ?? 0}${r?.failed ? `, ${r.failed} failed` : ''}.`
      )
      await load()
    } catch (e) {
      setReminderNote(e.message || 'Could not send reminders.')
    } finally {
      setReminding(false)
    }
  }

  // The catch-up, not the mechanism: each registration is pushed as it arrives
  // and the hourly pass retries anything that failed. This is for the two cases
  // where an hour is too long — the registrations taken before the push
  // existed, and a run of failures just fixed at the StreamYard end. A row
  // already pushed is skipped before any request, so pressing it twice
  // registers nobody twice.
  const pushStreamyard = async () => {
    if (pushing) return
    setPushing(true)
    setReminderNote('')
    try {
      const r = await api.superSyncWebinarStreamyard()
      setReminderNote(
        r?.considered
          ? `StreamYard: ${r.pushed} pushed`
            + (r.skipped ? `, ${r.skipped} skipped` : '')
            + (r.failed ? `, ${r.failed} failed` : '')
          : 'StreamYard already has every registrant.'
      )
      await load()
    } catch (e) {
      setReminderNote(e.message || 'Could not push to StreamYard.')
    } finally {
      setPushing(false)
    }
  }

  const csv = () => {
    const cols = ['created_at', 'name', 'email', 'phone', 'club', 'role', 'utm_campaign',
                  'utm_source', 'utm_medium', 'utm_content', 'email_sent', 'reminder_sent_at',
                  'streamyard_id']
    const escape = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const body = [cols.join(','), ...rows.map((r) => cols.map((c) => escape(r[c])).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'webinar-registrations.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return null
  if (error) {
    return <p className="text-sm text-red-400 mt-8">{error}</p>
  }

  return (
    <div className="mt-10">
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div>
          <h2 className="text-lg font-semibold text-pb-text">Webinar registrations</h2>
          <p className="text-xs text-pb-faint mt-1 max-w-2xl">
            Everyone who registered at /demo, newest first. Registering for the demo is not the
            same as asking to be onboarded, so these are kept out of the list above.
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          {rows.length > 0 && (
            <button
              onClick={pushStreamyard}
              disabled={pushing}
              title="Register anyone StreamYard does not have yet"
              className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5 transition disabled:opacity-50"
            >
              {pushing ? 'Pushing…' : 'Push to StreamYard'}
            </button>
          )}
          {rows.length > 0 && (
            <button
              onClick={remind}
              disabled={reminding}
              title="Email everyone who has not had the day-of reminder"
              className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5 transition disabled:opacity-50"
            >
              {reminding ? 'Sending…' : 'Send reminder'}
            </button>
          )}
          {rows.length > 0 && (
            <button
              onClick={csv}
              className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5 transition"
            >
              Export CSV
            </button>
          )}
          <button
            onClick={() => setOpen((o) => !o)}
            className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5 transition"
          >
            {open ? 'Hide' : `Show (${rows.length})`}
          </button>
        </div>
      </div>

      {reminderNote && <p className="text-xs text-pb-dim mb-3">{reminderNote}</p>}

      {open && (rows.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <p className="text-sm text-pb-dim">
            Nobody has registered yet. Registrations from /demo show up here.
          </p>
        </div>
      ) : (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">Club</th>
                <th className="px-3 py-2.5">Role</th>
                <th className="px-3 py-2.5">Campaign</th>
                <th className="px-3 py-2.5">Email</th>
                <th className="px-3 py-2.5">Reminder</th>
                <th className="px-3 py-2.5">StreamYard</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b pb-hairline last:border-0 align-top">
                  <td className="px-3 py-2.5 whitespace-nowrap text-pb-dim">{fmtDate(r.created_at)}</td>
                  <td className="px-3 py-2.5">
                    <div className="text-pb-text">{r.name}</div>
                    <a href={`mailto:${r.email}`} className="text-xs text-pb-faint hover:text-pb-text underline">{r.email}</a>
                  </td>
                  {/* A real tel: link — this list is worked from a desk. Often
                      blank, and that is expected: the field is optional, and a
                      registration taken before it existed carries none either. */}
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {r.phone
                      ? <a href={`tel:${String(r.phone).replace(/\s/g, '')}`} className="text-pb-text hover:underline">{r.phone}</a>
                      : <span className="text-pb-faintest">-</span>}
                  </td>
                  <td className="px-3 py-2.5 text-pb-text">{r.club}</td>
                  <td className="px-3 py-2.5 text-pb-dim">{r.role || '-'}</td>
                  <td className="px-3 py-2.5">
                    <div className="text-pb-dim">{r.utm_campaign || (r.click_source ? `${r.click_source} (no campaign tag)` : 'Direct')}</div>
                    {r.utm_content && <div className="font-mono text-[10px] text-pb-faintest">{r.utm_content}</div>}
                  </td>
                  <td className="px-3 py-2.5">
                    {/* Whether the provider accepted the confirmation email, and
                        why not if it didn't - what makes "they say they never
                        got it" answerable months later. */}
                    {r.email_sent
                      ? <span className="font-mono text-[10px] text-emerald-400">SENT</span>
                      : <span className="font-mono text-[10px] text-amber-400" title={r.email_error || 'Not sent yet'}>
                          {r.email_error ? 'FAILED' : 'PENDING'}
                        </span>}
                  </td>
                  <td className="px-3 py-2.5">
                    {/* The day-of reminder is its own send with its own
                        outcome. A dash before the event is the ordinary state,
                        not a problem — it goes out a few hours beforehand. */}
                    {r.reminder_sent_at
                      ? <span className="font-mono text-[10px] text-emerald-400" title={fmtDate(r.reminder_sent_at)}>SENT</span>
                      : r.reminder_error
                        ? <span className="font-mono text-[10px] text-amber-400" title={r.reminder_error}>FAILED</span>
                        : <span className="text-pb-faintest">-</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    {/* Whether StreamYard has them too, so nobody is asked to
                        register a second time. A reason without an id is not
                        always a failure — "no surname to send" is a row there
                        was nothing to do for, which is why the amber carries
                        the reason rather than just reading FAILED. */}
                    {r.streamyard_id
                      ? <span className="font-mono text-[10px] text-emerald-400" title={r.streamyard_id}>REGISTERED</span>
                      : r.streamyard_error
                        ? <span className="font-mono text-[10px] text-amber-400" title={r.streamyard_error}>NOT SENT</span>
                        : <span className="text-pb-faintest">-</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

export default function SuperOnboarding() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')

  const load = () => {
    setLoading(true)
    api.superListOnboarding()
      .then((data) => { setRows(data); setError('') })
      .catch((e) => setError(e.message || 'Could not load requests.'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const counts = useMemo(() => {
    const c = { all: rows.length }
    for (const s of STATUSES) c[s] = rows.filter(r => r.status === s).length
    return c
  }, [rows])

  const visible = filter === 'all' ? rows : rows.filter(r => r.status === filter)

  const setStatus = async (id, status) => {
    setRows(rs => rs.map(r => (r.id === id ? { ...r, status } : r)))  // optimistic
    try {
      await api.superUpdateOnboarding(id, status)
    } catch {
      load()  // reload to undo the optimistic change if the save failed
    }
  }

  const remove = async (row) => {
    if (!window.confirm(`Delete the enquiry from ${row.club || row.email}? This can't be undone.`)) return
    const prev = rows
    setRows(rs => rs.filter(r => r.id !== row.id))  // optimistic
    try {
      await api.superDeleteOnboarding(row.id)
    } catch (e) {
      setRows(prev)  // restore if the delete failed
      setError(e.message || 'Could not delete the request.')
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Onboarding requests</h1>
          <p className="text-sm text-pb-dim mt-1">
            Clubs that enquired through the marketing Contact form, newest first.
          </p>
          <p className="text-xs text-pb-faint mt-2 max-w-2xl">
            Status tracks where each club is up to: new when it lands, contacted once you've
            replied, onboarded when they're set up, closed if it goes nowhere.
          </p>
        </div>

        {/* Status filter */}
        <div className="flex flex-wrap gap-2 mb-4">
          {['all', ...STATUSES].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
                filter === s ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}
            >
              {s} ({counts[s] ?? 0})
            </button>
          ))}
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : visible.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">
              {rows.length === 0
                ? "No onboarding requests yet. When a club fills in the Contact form, it shows up here."
                : 'No requests with this status.'}
            </p>
          </div>
        ) : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Date</th>
                  <th className="px-3 py-2.5">Club</th>
                  <th className="px-3 py-2.5">Contact</th>
                  <th className="px-3 py-2.5">Association</th>
                  <th className="px-3 py-2.5">Grades</th>
                  <th className="px-3 py-2.5">Timeline</th>
                  <th className="px-3 py-2.5">Current setup</th>
                  <th className="px-3 py-2.5">Message</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.id} className="border-b pb-hairline align-top hover:bg-pb-surface2/40">
                    <td className="px-3 py-2.5 whitespace-nowrap text-pb-dim">{fmtDate(r.created_at)}</td>
                    <td className="px-3 py-2.5 font-medium text-pb-text">
                      {r.club}
                      {/* Whether the name is one the enquirer picked out of the
                          Cricket Australia club list (so it's the club's real
                          record, guid and all) or one they typed in — worth
                          knowing before matching them to a club by hand. */}
                      {r.club_source === 'search' && (
                        <div className="font-normal text-pb-faint text-xs" title={r.club_org_id || ''}>
                          Matched from PlayHQ
                        </div>
                      )}
                      {r.club_source === 'manual' && (
                        <div className="font-normal text-pb-faint text-xs">Typed in by hand</div>
                      )}
                      {r.founded_year && <div className="font-normal text-pb-faint text-xs">est. {r.founded_year}</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-pb-text">{r.name}{r.role && <span className="text-pb-faint font-normal"> · {r.role}</span>}</div>
                      <a href={`mailto:${r.email}`} className="text-accent hover:underline block">{r.email}</a>
                      {r.phone && <div className="text-pb-faint text-xs">{r.phone}</div>}
                      {r.contact_method && <div className="text-pb-faint text-xs">Prefers {r.contact_method.toLowerCase()}</div>}
                      {r.club_url && (
                        <a href={r.club_url.startsWith('http') ? r.club_url : `https://${r.club_url}`}
                          target="_blank" rel="noopener noreferrer"
                          className="text-pb-faint text-xs hover:text-pb-text block truncate max-w-[180px]">
                          {r.club_url}
                        </a>
                      )}
                      {r.heard_about && <div className="text-pb-faint text-xs italic">via {r.heard_about}</div>}
                    </td>
                    <td className="px-3 py-2.5 text-pb-dim">{r.association || '-'}</td>
                    <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{r.grades || '-'}</td>
                    <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{r.timeline || '-'}</td>
                    <td className="px-3 py-2.5 text-pb-dim max-w-[220px]">
                      <div>{r.storage || '-'}</div>
                      {(r.playhq_status || r.has_historical) && (
                        <div className="text-pb-faint text-xs mt-0.5">
                          PlayHQ: {r.playhq_status || '?'}{r.has_historical ? ` · historical: ${r.has_historical}` : ''}
                        </div>
                      )}
                      {r.interests && <div className="text-pb-faint text-xs mt-0.5">Wants: {r.interests}</div>}
                    </td>
                    <td className="px-3 py-2.5 text-pb-dim max-w-[240px]">
                      {r.message ? <span title={r.message} className="line-clamp-3">{r.message}</span> : <span className="text-pb-faint">-</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block mb-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase ${STATUS_STYLE[r.status] || ''}`}>
                        {r.status}
                      </span>
                      <select
                        value={r.status}
                        onChange={(e) => setStatus(r.id, e.target.value)}
                        className={`${SELECT_CLS} block`}
                        aria-label={`Status for ${r.club}`}
                      >
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap space-y-1.5">
                      {r.visitor_id && (
                        <Link
                          to={`/admin/usage?q=${r.visitor_id}&days=90`}
                          className="block font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2 transition text-center"
                        >
                          View activity
                        </Link>
                      )}
                      <button
                        onClick={() => remove(r)}
                        aria-label={`Delete request from ${r.club}`}
                        className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-red-400 border pb-hairline rounded px-2 py-1 hover:border-red-500/40 transition"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <WebinarRegistrations />
      </div>
    </AdminLayout>
  )
}
