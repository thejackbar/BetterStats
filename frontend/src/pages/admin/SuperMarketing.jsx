import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// PlayHQ stores the abbreviated state on the club (e.g. "WA", "NSW"), so the
// filter value must be the abbreviation, not the full name.
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']

const SELECT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent'
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_ACCENT = 'px-3 py-1.5 rounded text-xs font-semibold bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 disabled:opacity-50'

const STATE_STYLE = {
  running:  { dot: 'bg-emerald-400 animate-pulse', text: 'text-emerald-300', label: 'Running' },
  waiting:  { dot: 'bg-sky-400',                    text: 'text-sky-300',     label: 'Waiting' },
  paused:   { dot: 'bg-amber-400',                  text: 'text-amber-300',   label: 'Paused' },
  idle:     { dot: 'bg-pb-faint',                   text: 'text-pb-dim',      label: 'Idle' },
  complete: { dot: 'bg-emerald-400',                text: 'text-emerald-300', label: 'Complete' },
}

function CrawlStatus({ status }) {
  if (!status) return null
  const s = STATE_STYLE[status.state] || STATE_STYLE.idle
  return (
    <div className="flex items-center gap-2 rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2 mb-4">
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

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint">{label}</div>
      <div className="text-lg font-semibold text-pb-text">{value ?? '-'}</div>
    </div>
  )
}

// Everything collected for one club — all stored contacts, every association it
// plays in, address and ids. Driven entirely by the /clubs payload (no extra fetch).
function ClubDetail({ club, onToggleContact, onToggleEmailed }) {
  const contacts = club.contacts || []
  const assocs = club.associations
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div>
        <div className="text-[11px] uppercase tracking-wide text-pb-faint mb-1">
          Contacts ({contacts.length}) · tick who to email
        </div>
        {contacts.length ? (
          <table className="w-full text-xs">
            <tbody>
              {contacts.map((ct) => {
                const canEmail = !!ct.email && ct.subscribed
                return (
                  <tr key={ct.id} className="align-top">
                    <td className="py-0.5 pr-2">
                      <input type="checkbox" checked={!!ct.selected} disabled={!canEmail}
                             title={canEmail ? 'Include in outreach' : 'No emailable address'}
                             onChange={(e) => onToggleContact(club.id, ct.id, e.target.checked)} />
                    </td>
                    <td className="py-0.5 pr-2 text-pb-faint whitespace-nowrap">{ct.role || '-'}</td>
                    <td className="py-0.5 pr-2 text-pb-text">{ct.full_name || '-'}</td>
                    <td className="py-0.5 pr-2">
                      {ct.email
                        ? <a href={`mailto:${ct.email}`} className="text-pb-accent">{ct.email}</a>
                        : <span className="text-pb-faint">-</span>}
                      {!ct.subscribed && <span className="ml-1 text-[10px] text-amber-300">unsub</span>}
                    </td>
                    <td className="py-0.5 text-pb-dim whitespace-nowrap">{ct.mobile || ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : <div className="text-pb-faint text-xs">No contacts stored.</div>}
      </div>
      <div className="text-xs space-y-2">
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
        <div className="text-pb-dim">
          <div><span className="text-pb-faint">Address: </span>
            {[club.address_line1, club.suburb, club.state, club.postcode].filter(Boolean).join(', ') || '-'}</div>
          <div><span className="text-pb-faint">Website: </span>
            {club.website_url
              ? <a href={club.website_url} target="_blank" rel="noreferrer" className="text-pb-accent">{club.website_url}</a>
              : '-'}</div>
          <div><span className="text-pb-faint">PlayHQ code: </span>{club.playhq_id || '-'}
            <span className="text-pb-faint"> · GUID: </span><span className="font-mono text-[10px]">{club.grassroots_guid || '-'}</span></div>
          <div><span className="text-pb-faint">Status: </span>{club.status || '-'}
            {club.is_customer && <span className="text-emerald-300"> · already a customer</span>}</div>
          <div className="pt-1">
            <span className="text-pb-faint">Emailed: </span>
            {club.emailed_at
              ? <span className="text-amber-300">yes ({club.emailed_via || 'manual'})</span>
              : <span className="text-pb-faint">no</span>}
            <button
              className="ml-2 px-2 py-0.5 rounded border pb-hairline text-[11px] text-pb-text hover:border-pb-accent"
              onClick={() => onToggleEmailed(club.id, !club.emailed_at)}>
              {club.emailed_at ? 'Unmark emailed' : 'Mark as emailed'}
            </button>
          </div>
        </div>
      </div>
    </div>
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
  const [filters, setFilters] = useState({
    q: '', state: '', association: '', postcode_from: '', postcode_to: '', contact: '',
    person: '', exclude_junior: false, exclude_emailed: false,
  })
  const [expanded, setExpanded] = useState(null)

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
    api.mktClubs({ ...filters, limit: 100 })
      .then((d) => { setClubs(d.clubs); setTotal(d.total); setError('') })
      .catch((e) => setError(e.message || 'Could not load the directory.'))
      .finally(() => setLoading(false))
  }, [filters])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadClubs() }, [loadClubs])

  const runCrawl = async () => {
    setBusy('crawl'); setMsg('')
    try {
      await api.mktCrawl()
      setMsg('Crawl batch started in the background. Watch the status above — it is rate-limited, so progress is slow.')
      setTimeout(loadStats, 2000)  // let the first fetch land, then refresh the status pill
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const exportComms = async () => {
    setBusy('export'); setMsg('')
    try {
      const r = await api.mktExportComms({ ...filters })
      setMsg(`Exported to ${r.org}: ${r.added} added, ${r.already_present} already there, ${r.already_suppressed} suppressed.`)
    } catch (e) { setError(e.message) } finally { setBusy('') }
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

  const syncSuppressions = async () => {
    setBusy('supp'); setMsg('')
    try {
      const r = await api.mktSyncSuppressions()
      setMsg(`Synced ${r.suppressed} suppression(s) back to the directory.`)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Club directory</h1>
          <p className="text-sm text-pb-dim mt-1">
            Every Australian cricket club from the PlayHQ public directory, for
            BetterCricket outreach. Each club stores its whole published committee
            (names, roles, emails, mobiles) plus the association(s) it plays in. Click
            a club to see everything collected and tick which contacts to email —
            office bearers are pre-ticked. "Export to BetterAdmin Comms" pushes only
            the ticked contacts (within the current filter) into the comms send pipeline.
          </p>
        </div>

        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-9 gap-2 mb-5">
            <Stat label="Clubs" value={stats.clubs} />
            <Stat label="Contacts" value={stats.contacts} />
            <Stat label="To email" value={stats.selected_contacts} />
            <Stat label="With email" value={stats.clubs_with_email} />
            <Stat label="Emailed" value={stats.emailed} />
            <Stat label="Assoc. linked" value={stats.associations_fetched} />
            <Stat label="Assoc. pending" value={stats.associations_pending} />
            <Stat label="Associations" value={stats.distinct_associations} />
            <Stat label="Already ours" value={stats.already_customers} />
          </div>
        )}

        <CrawlStatus status={status} />

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <button className={BTN_ACCENT} disabled={busy === 'crawl'} onClick={runCrawl}>
            {busy === 'crawl' ? 'Starting...' : 'Run crawl batch'}
          </button>
          <button className={BTN} onClick={() => { loadStats(); loadClubs() }}>Refresh</button>
          <a className={BTN} href={api.mktExportCsvUrl(filters)} target="_blank" rel="noreferrer">
            Download CSV (filtered)
          </a>
          <button className={BTN} disabled={busy === 'export'} onClick={exportComms}>
            {busy === 'export' ? 'Exporting...' : 'Export to BetterAdmin Comms (filtered)'}
          </button>
          <button className={BTN} disabled={busy === 'supp'} onClick={syncSuppressions}>
            {busy === 'supp' ? 'Syncing...' : 'Sync suppressions'}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-1">
          <input
            className={SELECT_CLS + ' min-w-[180px]'}
            placeholder="Search club or association..."
            value={filters.q}
            onChange={(e) => setFilters(f => ({ ...f, q: e.target.value }))}
          />
          <input
            className={SELECT_CLS + ' min-w-[160px]'}
            placeholder="Association contains..."
            value={filters.association}
            onChange={(e) => setFilters(f => ({ ...f, association: e.target.value }))}
          />
          <select className={SELECT_CLS} value={filters.state}
                  onChange={(e) => setFilters(f => ({ ...f, state: e.target.value }))}>
            <option value="">All states</option>
            {STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="flex items-center gap-1 text-xs text-pb-dim">
            <span>Postcode</span>
            <input className={SELECT_CLS + ' w-20'} placeholder="from" inputMode="numeric"
                   value={filters.postcode_from}
                   onChange={(e) => setFilters(f => ({ ...f, postcode_from: e.target.value }))} />
            <span>–</span>
            <input className={SELECT_CLS + ' w-20'} placeholder="to" inputMode="numeric"
                   value={filters.postcode_to}
                   onChange={(e) => setFilters(f => ({ ...f, postcode_to: e.target.value }))} />
          </div>
          <select className={SELECT_CLS} value={filters.contact}
                  onChange={(e) => setFilters(f => ({ ...f, contact: e.target.value }))}>
            <option value="">Any contacts</option>
            <option value="any_email">Has an email (any)</option>
            <option value="named_email">Has a named email</option>
            <option value="pst">Has Pres + Sec + Treas (named, emailed)</option>
          </select>
          <input
            className={SELECT_CLS + ' min-w-[150px]'}
            placeholder="Person name contains..."
            value={filters.person}
            onChange={(e) => setFilters(f => ({ ...f, person: e.target.value }))}
          />
          <label className="flex items-center gap-1.5 text-xs text-pb-dim">
            <input type="checkbox" checked={filters.exclude_junior}
                   onChange={(e) => setFilters(f => ({ ...f, exclude_junior: e.target.checked }))} />
            Exclude juniors
          </label>
          <label className="flex items-center gap-1.5 text-xs text-pb-dim">
            <input type="checkbox" checked={filters.exclude_emailed}
                   onChange={(e) => setFilters(f => ({ ...f, exclude_emailed: e.target.checked }))} />
            Hide already-emailed
          </label>
          {(filters.q || filters.association || filters.state || filters.postcode_from
            || filters.postcode_to || filters.contact || filters.person
            || filters.exclude_junior || filters.exclude_emailed) && (
            <button className="text-[11px] text-pb-faint hover:text-pb-accent"
                    onClick={() => setFilters({ q: '', state: '', association: '',
                                                postcode_from: '', postcode_to: '', contact: '',
                                                person: '', exclude_junior: false, exclude_emailed: false })}>
              clear
            </button>
          )}
        </div>
        <div className="text-[11px] text-pb-faint mb-3">
          Download CSV and Export to BetterAdmin Comms act on this filtered list.
        </div>

        {msg && <div className="mb-3 text-xs text-accent border border-accent/40 bg-accent/10 rounded px-3 py-2">{msg}</div>}
        {error && <div className="mb-3 text-xs text-red-300 border border-red-500/40 bg-red-500/10 rounded px-3 py-2">{error}</div>}

        <div className="text-[11px] text-pb-faint mb-2">{total} matching club(s)</div>

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
                {clubs.map(c => {
                  const top = c.contacts && c.contacts[0]
                  const more = (c.contacts?.length || 0) - 1
                  const isOpen = expanded === c.id
                  return [
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
                                      onToggleEmailed={toggleEmailed} />
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
      </div>
    </AdminLayout>
  )
}
