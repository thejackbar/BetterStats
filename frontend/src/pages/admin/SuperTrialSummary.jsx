import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { SORTS } from '../../lib/trialSummarySort'

// Better HQ > Reporting > Trial Summary. One row per club that signed up or went on a trial
// (services/trial_summary.py): when it signed up, what it is trialling, how much its own people
// have used the platform, and when the trial ends. Read only; every figure is read fresh.

const STATUS = {
  on_trial: { label: 'On trial', cls: 'border-sky-500/40 text-sky-300 bg-sky-500/10' },
  paying: { label: 'Paying', cls: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' },
  trial_ended: { label: 'Trial ended', cls: 'border-red-500/40 text-red-300 bg-red-500/10' },
  paused: { label: 'Paused', cls: 'border-pb-hairline text-pb-dim' },
  archived: { label: 'Archived', cls: 'border-pb-hairline text-pb-faint' },
  no_modules: { label: 'No modules', cls: 'border-pb-hairline text-pb-faint' },
}

const FROM_LABEL = {
  registration: 'the date they registered',
  trial_start: 'their first trial start (no registration on record)',
  first_module: 'their first module (no registration or trial start on record)',
}
const CONTACT_LABEL = {
  club_admin: 'Club admin',
  club_directory: 'From the Club Directory (no club member has an email)',
  club_settings: "The club's contact email",
}

// Chips, in the order someone working through trials would use them.
const CHIPS = [
  { key: 'active', label: 'Current', test: (c) => !['archived', 'paused'].includes(c.status) },
  { key: 'ending_soon', label: 'Ending soon', test: (c) => c.ending_soon },
  { key: 'on_trial', label: 'On trial', test: (c) => c.status === 'on_trial' },
  { key: 'new', label: 'Signed up this week', test: (c, now) => c.signed_up_at && now - new Date(c.signed_up_at) <= 7 * 86400000 },
  { key: 'trial_ended', label: 'Trial ended', test: (c) => c.status === 'trial_ended' },
  { key: 'paying', label: 'Paying', test: (c) => c.status === 'paying' },
  { key: 'all', label: 'All, including paused and archived', test: () => true },
]

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : null)
const fmtShort = (iso) => (iso ? new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : null)
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
const areaName = (a) => a.replace(/[-_]/g, ' ').replace(/^\w/, (ch) => ch.toUpperCase())

function daysAgo(iso, now) {
  if (!iso) return null
  const d = Math.floor((now - new Date(iso)) / 86400000)
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`
}

function TrialEnd({ c, now }) {
  if (c.status === 'on_trial' || (c.status === 'paying' && c.trial_ends_at)) {
    if (c.trial_open_ended && !c.trial_ends_at) return <span className="text-pb-dim">No end date set</span>
    const left = c.days_left
    return (
      <span>
        <span className="text-pb-text">{fmtDate(c.trial_ends_at)}</span>
        <span data-testid="trial-days-left" className={`block text-[11px] ${c.ending_soon ? 'text-amber-300 font-medium' : 'text-pb-faint'}`}>
          {left <= 0 ? 'ends today' : `${plural(left, 'day')} left`}{c.status === 'paying' ? ' on an add-on trial' : ''}
        </span>
      </span>
    )
  }
  if (c.status === 'trial_ended' && c.trial_ended_at) {
    return (
      <span>
        <span className="text-pb-dim">{fmtDate(c.trial_ended_at)}</span>
        <span className="block text-[11px] text-red-300">ended {daysAgo(c.trial_ended_at, now)}</span>
      </span>
    )
  }
  return <span className="text-pb-faint">–</span>
}

// The activity cell: one plain line on use, one on what they used, one on when.
function Activity({ c, now, recentDays }) {
  const a = c.activity || {}
  if (!a.views) {
    return (
      <span data-testid="activity" className="text-pb-faint">
        {c.last_login_at ? `Signed in ${daysAgo(c.last_login_at, now)}, has not opened the admin since` : 'Has not used the admin yet'}
      </span>
    )
  }
  return (
    <span data-testid="activity" className="text-pb-dim">
      <span className="text-pb-text">Active {plural(a.active_days, 'day')}</span>
      {' '}({a.active_days_recent} in the last {recentDays}) · {plural(a.views, 'page view')} · {plural(a.active_people, 'person', 'people')}
      {a.top_areas?.length > 0 && (
        <span className="block text-[11px] text-pb-faint">Mostly {a.top_areas.map((t) => areaName(t.area)).join(', ')}</span>
      )}
      <span className="block text-[11px] text-pb-faint">Last active {daysAgo(a.last_active_at, now)}</span>
    </span>
  )
}

function Modules({ c }) {
  if (!c.modules?.length) return <span className="text-pb-faint">–</span>
  return (
    <span className="flex flex-wrap gap-1">
      {c.modules.map((m) => (
        <span key={m.module} title={m.status === 'trial_expired' ? 'Trial ended' : m.status === 'subscribed' ? 'Paid' : 'On trial'}
          className={`px-1.5 py-0.5 rounded border font-mono text-[10px] whitespace-nowrap ${
            m.status === 'subscribed' ? 'border-emerald-500/40 text-emerald-300'
              : m.status === 'trial_expired' ? 'border-pb-hairline text-pb-faint line-through'
                : 'border-sky-500/40 text-sky-300'}`}>
          {m.name}{m.status === 'subscribed' ? ' (paid)' : ''}
        </span>
      ))}
    </span>
  )
}

export default function SuperTrialSummary() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [chip, setChip] = useState('active')
  const [sort, setSort] = useState('signed_up')
  const [q, setQ] = useState('')

  useEffect(() => {
    api.superTrialSummary()
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message || 'Could not load the trial summary.'))
  }, [])

  const now = useMemo(() => (data?.generated_at ? new Date(data.generated_at) : new Date()), [data])
  const clubs = useMemo(() => data?.clubs || [], [data])
  const counts = useMemo(() => Object.fromEntries(CHIPS.map((ch) => [ch.key, clubs.filter((c) => ch.test(c, now)).length])), [clubs, now])
  const shown = useMemo(() => {
    const test = CHIPS.find((ch) => ch.key === chip)?.test || (() => true)
    const needle = q.trim().toLowerCase()
    return clubs
      .filter((c) => test(c, now) && (!needle || (c.name || '').toLowerCase().includes(needle)))
      .slice()
      .sort(SORTS[sort].fn)
  }, [clubs, chip, sort, q, now])
  const recentDays = data?.recent_days || 7

  return (
    <AdminLayout>
      <div className="max-w-[1400px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Trial Summary</h1>
          <p className="text-sm text-pb-dim mt-1">
            Every club that signed up or went on a trial: when, what it is trialling, how much its own people have used
            the platform, and when the trial ends.
          </p>
          <p className="text-xs text-pb-faint mt-2 max-w-3xl">
            Activity counts signed-in page views by the club&rsquo;s own people, never our team. &ldquo;Ending soon&rdquo; is
            {' '}{data?.ending_soon_days ?? 3} days or fewer, the same window as the trial emails and the All Clubs page.
          </p>
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>}

        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {CHIPS.map((ch) => (
            <button key={ch.key} type="button" data-testid={`trial-chip-${ch.key}`} aria-pressed={chip === ch.key} onClick={() => setChip(ch.key)}
              className={`px-2 py-1 rounded-full border font-mono text-[10px] ${chip === ch.key ? 'border-pb-accent bg-pb-accent/15 text-pb-text' : 'border-pb-hairline text-pb-dim hover:border-pb-dim'}`}>
              {ch.label} <span data-testid={`trial-chip-count-${ch.key}`} className="opacity-70">{data ? counts[ch.key] : ''}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search club name" data-testid="trial-search"
            className="w-full sm:w-auto sm:flex-1 sm:min-w-[220px] bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
          <label className="flex items-center gap-1.5 font-mono text-[10px] text-pb-dim">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value)} data-testid="trial-sort"
              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 font-mono text-[10px] text-pb-text">
              {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
            </select>
          </label>
        </div>

        {!data && !error && <p className="text-sm text-pb-dim">Loading&hellip;</p>}
        {data && clubs.length === 0 && (
          <div className="pb-card p-8 text-center text-sm text-pb-dim" data-testid="trial-empty">No club has signed up or started a trial yet.</div>
        )}
        {data && clubs.length > 0 && shown.length === 0 && (
          <div className="pb-card p-6 text-center text-sm text-pb-dim" data-testid="trial-no-match">No club matches those filters.</div>
        )}

        {shown.length > 0 && (
          <div className="pb-card overflow-x-auto" data-testid="trial-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Club</th>
                  <th className="px-3 py-2.5">Signed up</th>
                  <th className="px-3 py-2.5">Modules</th>
                  <th className="px-3 py-2.5">Trial ends</th>
                  <th className="px-3 py-2.5">Activity</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((c) => (
                  <tr key={c.org_id} data-testid="trial-row" className={`border-b pb-hairline align-top hover:bg-pb-surface2/40 ${c.ending_soon ? 'bg-amber-500/5' : ''}`}>
                    <td className="px-3 py-2.5 min-w-[180px] max-w-[260px]">
                      <span className="block font-medium text-pb-text">
                        {c.slug ? <a href={`/${c.slug}`} target="_blank" rel="noopener noreferrer" className="hover:underline">{c.name}</a> : c.name}
                      </span>
                      <span data-testid="trial-status" className={`mt-1 inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase whitespace-nowrap ${STATUS[c.status]?.cls || ''}`}>
                        {STATUS[c.status]?.label || c.status}
                      </span>
                      <span className="block mt-1.5 text-[11px]" title={CONTACT_LABEL[c.contact_source] || 'No contact on record'}>
                        {c.admin_name && <span className="block text-pb-dim">{c.admin_name}</span>}
                        {c.admin_email
                          ? <a href={`mailto:${c.admin_email}`} className="text-pb-faint hover:underline break-all">{c.admin_email}</a>
                          : <span className="text-pb-faint">No contact on record</span>}
                        {c.contact_source === 'club_directory' && <span className="block text-[10px] text-pb-faint">from the Club Directory</span>}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 min-w-[130px] max-w-[190px]" title={c.signed_up_from ? `Dated from ${FROM_LABEL[c.signed_up_from]}` : 'No sign-up date on record'}>
                      <span className="block text-pb-text whitespace-nowrap">{fmtDate(c.signed_up_at) || 'Unknown'}</span>
                      <span className="block text-[11px] text-pb-faint">{c.signup_channel}{c.origin?.label ? ` · ${c.origin.label}` : ''}</span>
                    </td>
                    <td className="px-3 py-2.5 min-w-[150px]"><Modules c={c} /></td>
                    <td className="px-3 py-2.5 whitespace-nowrap"><TrialEnd c={c} now={now} /></td>
                    <td className="px-3 py-2.5 min-w-[240px]">
                      <Activity c={c} now={now} recentDays={recentDays} />
                      <span data-testid="trial-data" className="block mt-1 text-[11px] text-pb-faint">
                        {plural(c.data?.players || 0, 'player')} · {plural(c.data?.games || 0, 'game')} ·{' '}
                        {c.data?.last_sync_at ? `synced ${fmtShort(c.data.last_sync_at)}` : 'never synced'}
                        {c.data?.last_sync_status === 'error' ? ' · last sync failed' : ''}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <p className="font-mono text-[10px] text-pb-faintest mt-3">{shown.length} of {clubs.length} clubs</p>}
      </div>
    </AdminLayout>
  )
}
