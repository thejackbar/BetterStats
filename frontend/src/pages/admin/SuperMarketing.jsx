import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// PlayHQ stores the abbreviated state on the club (e.g. "WA", "NSW"), so the
// filter value must be the abbreviation, not the full name.
const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']

const SELECT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent'
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_ACCENT = 'px-3 py-1.5 rounded text-xs font-semibold bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 disabled:opacity-50'

// Shared layout primitives so the toolbar reads as tidy, labelled cards.
const CARD = 'rounded-xl border pb-hairline bg-pb-surface2/40 px-3 py-2.5 mb-2.5'
const SECTION = 'text-[11px] uppercase tracking-wide text-pb-faint font-semibold'
const FIELD_LABEL = 'block text-[10px] uppercase tracking-wide text-pb-faint mb-0.5'

// A labelled filter cell — keeps every control on a tidy grid with its caption.
function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className={FIELD_LABEL}>{label}</label>
      {children}
    </div>
  )
}

const STATE_STYLE = {
  running:  { dot: 'bg-emerald-400 animate-pulse', text: 'text-emerald-300', label: 'Running' },
  waiting:  { dot: 'bg-sky-400',                    text: 'text-sky-300',     label: 'Waiting' },
  paused:   { dot: 'bg-amber-400',                  text: 'text-amber-300',   label: 'Paused' },
  idle:     { dot: 'bg-pb-faint',                   text: 'text-pb-dim',      label: 'Idle' },
  complete: { dot: 'bg-emerald-400',                text: 'text-emerald-300', label: 'Complete' },
  stopped:  { dot: 'bg-red-400',                    text: 'text-red-300',     label: 'Stopped' },
}

function CrawlStatus({ status }) {
  if (!status) return null
  const s = STATE_STYLE[status.state] || STATE_STYLE.idle
  return (
    <div className="flex items-center gap-2 rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2 mb-2.5">
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

// Searchable multi-select of associations. Selecting several filters clubs that
// belong to ANY of them. The ✕ on the button clears all selections.
function AssocMultiSelect({ options, selected, onChange, onSaveShort }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const ql = q.toLowerCase()
  const filtered = options
    .filter(o => o.name.toLowerCase().includes(ql) || (o.short || '').toLowerCase().includes(ql))
    .slice(0, 800)
  const toggle = (name) =>
    onChange(selected.includes(name) ? selected.filter(n => n !== name) : [...selected, name])
  return (
    <div className="relative" ref={ref}>
      <button type="button" className={SELECT_CLS + ' flex items-center gap-1.5'}
              onClick={() => setOpen(o => !o)}>
        <span>{selected.length ? `Associations (${selected.length})` : 'Associations'}</span>
        {selected.length > 0 && (
          <span role="button" title="Clear selection" className="text-pb-faint hover:text-red-300"
                onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-[40rem] max-w-[92vw] max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          <input autoFocus className={SELECT_CLS + ' w-full mb-2'} placeholder="Search associations..."
                 value={q} onChange={(e) => setQ(e.target.value)} />
          {selected.length > 0 && (
            <button type="button" className="text-[11px] text-pb-faint hover:text-pb-accent mb-1"
                    onClick={() => onChange([])}>clear selection</button>
          )}
          <div className="text-[10px] text-pb-faint px-1 mb-1">Short code is editable — type and press Enter (blank resets to default).</div>
          {!filtered.length && <div className="text-xs text-pb-faint px-1 py-2">No matches.</div>}
          {filtered.map(o => (
            <div key={o.name}
                 className="flex items-center gap-2 px-1 py-0.5 text-xs text-pb-text hover:bg-pb-surface rounded">
              <label className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                <input type="checkbox" checked={selected.includes(o.name)} onChange={() => toggle(o.name)} />
                <span className="truncate" title={o.name}>{o.name}</span>
              </label>
              {o.resolved === false
                ? <span className="text-[10px] text-pb-faint italic shrink-0" title="Roster not fetched yet — select and click Fetch full roster">not fetched</span>
                : <span className="text-pb-faint shrink-0">{o.count}</span>}
              <input
                key={`sc-${o.id}-${o.short || ''}`}
                defaultValue={o.short || ''}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onSaveShort(o.id, e.target.value); e.target.blur() } }}
                onBlur={(e) => { if ((e.target.value || '') !== (o.short || '')) onSaveShort(o.id, e.target.value) }}
                title="Short code — edit and press Enter (blank resets to default)"
                className="w-16 shrink-0 text-[10px] uppercase bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 focus:outline-none focus:border-pb-accent" />
            </div>
          ))}
        </div>
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

function Pager({ total, page, pageSize, onPage, loading }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total ? page * pageSize + 1 : 0
  const to = Math.min((page + 1) * pageSize, total)
  const btn = 'px-2 py-0.5 rounded border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-40'
  return (
    <div className="flex items-center justify-between text-[11px] text-pb-faint my-2">
      <span>{total} matching club(s){total > 0 ? ` · showing ${from}–${to}` : ''}</span>
      {pages > 1 && (
        <span className="flex items-center gap-2">
          <button className={btn} disabled={page === 0 || loading}
                  onClick={() => onPage(p => Math.max(0, p - 1))}>Prev</button>
          <span>Page {page + 1} / {pages}</span>
          <button className={btn} disabled={page + 1 >= pages || loading}
                  onClick={() => onPage(p => p + 1)}>Next</button>
        </span>
      )}
    </div>
  )
}

// Everything collected for one club — all stored contacts, every association it
// plays in, address and ids. Driven entirely by the /clubs payload (no extra fetch).
function ClubDetail({ club, onToggleContact, onToggleEmailed, onToggleExcluded, onSaveUtm }) {
  const contacts = club.contacts || []
  const assocs = club.associations
  const [utm, setUtm] = useState(club.utm_code || '')
  const [utmBusy, setUtmBusy] = useState(false)
  const saveUtm = async () => {
    setUtmBusy(true)
    try { await onSaveUtm(club.id, utm) } finally { setUtmBusy(false) }
  }
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
          <div className="flex items-center gap-1 pt-1">
            <span className="text-pb-faint">UTM:</span>
            <input className={SELECT_CLS + ' w-56 font-mono'} value={utm}
                   placeholder={club.utm_code || 'utm code'}
                   onChange={(e) => setUtm(e.target.value)} />
            <button disabled={utmBusy || utm === (club.utm_code || '')}
                    className="px-2 py-0.5 rounded border pb-hairline text-[11px] text-pb-text hover:border-pb-accent disabled:opacity-40"
                    onClick={saveUtm}>{utmBusy ? '...' : 'Save'}</button>
            <span className="text-[10px] text-pb-faint" title="Blank resets to the default">(blank = default)</span>
          </div>
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
            <button
              className={'ml-2 px-2 py-0.5 rounded border text-[11px] hover:opacity-80 '
                + (club.excluded ? 'border-red-500/50 text-red-300 bg-red-500/10' : 'pb-hairline text-pb-text')}
              title="Excluded clubs are never exported, and any contacts already in BetterAdmin Comms are dropped from audiences"
              onClick={() => onToggleExcluded(club.id, !club.excluded)}>
              {club.excluded ? 'Excluded ✕ — click to include' : 'Exclude'}
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
  const [page, setPage] = useState(0)
  const [assocOptions, setAssocOptions] = useState([])
  const PAGE = 100
  const [filters, setFilters] = useState({
    q: '', state: '', association: '', associations: [], postcode_from: '', postcode_to: '',
    contact: '', person: '', exclude_junior: false, exclude_emailed: false,
    exclude_carnival: false, exclude_school: false,
  })
  const [expanded, setExpanded] = useState(null)
  const [view, setView] = useState({ group: false, assocSort: 'asc', clubSort: 'asc' })

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
    api.mktClubs({
      ...filters, limit: PAGE, offset: page * PAGE,
      group_by_association: view.group, assoc_sort: view.assocSort, club_sort: view.clubSort,
    })
      .then((d) => { setClubs(d.clubs); setTotal(d.total); setError('') })
      .catch((e) => setError(e.message || 'Could not load the directory.'))
      .finally(() => setLoading(false))
  }, [filters, page, view])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadClubs() }, [loadClubs])
  useEffect(() => { setPage(0) }, [filters, view])  // back to first page when filters or sort change
  useEffect(() => { api.mktAssociations().then(setAssocOptions).catch(() => {}) }, [])

  const runCrawl = async () => {
    setBusy('crawl'); setMsg('')
    try {
      await api.mktCrawl()
      setMsg('Crawl batch started in the background. Watch the status above — it is rate-limited, so progress is slow.')
      setTimeout(loadStats, 2000)  // let the first fetch land, then refresh the status pill
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const setCrawlPaused = async (paused) => {
    setBusy('control'); setMsg('')
    try {
      await api.mktCrawlControl(paused)
      setMsg(paused ? 'Crawler stopped. It will idle until you start it again.'
                    : 'Crawler started.')
      api.mktStatus().then(setStatus).catch(() => {})
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const exportComms = async () => {
    setBusy('export'); setMsg('')
    try {
      const r = await api.mktExportComms({ ...filters })
      setMsg(`Exported to ${r.org}: ${r.added} added, ${r.already_present} already there, ${r.already_suppressed} suppressed.`)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const bulkEmailed = async (value) => {
    if (!window.confirm(
      `${value ? 'Mark' : 'Unmark'} all ${total} club(s) in the current filtered list as `
      + `${value ? 'emailed' : 'not emailed'}?`)) return
    setBusy('bulk'); setMsg('')
    try {
      const r = await api.mktBulkEmailed(value, filters)
      setMsg(`${r.updated} club(s) marked ${value ? 'emailed' : 'not emailed'}.`)
      loadStats(); loadClubs()
    } catch (e) { setError(e.message || 'Could not update.') } finally { setBusy('') }
  }

  const bulkExcluded = async (value) => {
    if (!window.confirm(
      `${value ? 'Exclude' : 'Include'} all ${total} club(s) in the current filtered list`
      + `${value ? ' from outreach' : ''}?`)) return
    setBusy('bulk'); setMsg('')
    try {
      const r = await api.mktBulkExcluded(value, filters)
      setMsg(`${r.updated} club(s) ${value ? 'excluded' : 'included'}.`)
      loadStats(); loadClubs()
    } catch (e) { setError(e.message || 'Could not update.') } finally { setBusy('') }
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

  const toggleExcluded = async (clubId, excluded) => {
    setClubs(cs => cs.map(c => c.id !== clubId ? c : { ...c, excluded }))
    try {
      await api.mktSetClubExcluded(clubId, excluded)
      loadStats()
    } catch (e) {
      setError(e.message || 'Could not update.')
      loadClubs()
    }
  }

  const resolveSelectedAssociations = async () => {
    setBusy('resolve'); setMsg('')
    const byName = Object.fromEntries(assocOptions.map(o => [o.name, o.id]))
    let done = 0
    try {
      for (const name of filters.associations) {
        const id = byName[name]
        if (!id) continue
        await api.mktResolveAssociation(id, name)
        done += 1
      }
      setMsg(`Fetching ${done} roster(s) in the background — this takes up to a minute or two each. Click Refresh to see them fill in.`)
      // Give the background resolve(s) time, then refresh the view + counts.
      setTimeout(() => { loadStats(); loadClubs(); api.mktAssociations().then(setAssocOptions).catch(() => {}) }, 60000)
    } catch (e) { setError(e.message || 'Could not start the roster fetch.') } finally { setBusy('') }
  }

  const saveAssocShort = async (id, short) => {
    try {
      const r = await api.mktSetAssocShortcode(id, short)
      setAssocOptions(opts => opts.map(o => o.id === id ? { ...o, short: r.short } : o))
    } catch (e) { setError(e.message || 'Could not update the short code.') }
  }

  const saveUtm = async (clubId, utm) => {
    try {
      const r = await api.mktSetClubUtm(clubId, utm)
      setClubs(cs => cs.map(c => c.id === clubId ? { ...c, utm_code: r.utm_code } : c))
      setMsg(`UTM updated to ${r.utm_code}`)
    } catch (e) { setError(e.message || 'Could not update the UTM.') }
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
        <div className="mb-3">
          <h1 className="text-xl font-semibold text-pb-text">Club directory</h1>
          <p className="text-xs text-pb-dim mt-0.5">
            Every Australian cricket club from the PlayHQ public directory, for
            BetterCricket outreach. Click a club to see its committee and tick which
            contacts to email; "Export to BetterAdmin Comms" pushes the ticked
            contacts (within the current filter) into the send pipeline.
          </p>
        </div>

        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-3">
            <Stat label="Clubs" value={stats.clubs} />
            <Stat label="Contacts" value={stats.contacts} />
            <Stat label="To email" value={stats.selected_contacts} />
            <Stat label="With email" value={stats.clubs_with_email} />
            <Stat label="Emailed" value={stats.emailed} />
            <Stat label="Assoc. linked" value={stats.associations_fetched} />
            <Stat label="Assoc. pending" value={stats.associations_pending} />
            <Stat label="Associations" value={stats.distinct_associations} />
            <Stat label="Assoc. swept"
                  value={stats.associations_registry != null
                    ? `${stats.associations_resolved ?? 0}/${stats.associations_registry}` : '-'} />
            <Stat label="Already ours" value={stats.already_customers} />
          </div>
        )}

        <CrawlStatus status={status} />

        {/* Crawler controls — sit directly under the status pill */}
        <div className="flex flex-wrap items-center gap-2 mb-2.5">
          <button className={BTN_ACCENT} disabled={busy === 'crawl' || status?.paused} onClick={runCrawl}>
            {busy === 'crawl' ? 'Starting...' : 'Run crawl batch'}
          </button>
          {status?.paused ? (
            <button className="px-3 py-1.5 rounded text-xs font-semibold border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50"
                    disabled={busy === 'control'} onClick={() => setCrawlPaused(false)}>
              {busy === 'control' ? '...' : 'Start crawling'}
            </button>
          ) : (
            <button className="px-3 py-1.5 rounded text-xs font-semibold border border-red-500/40 bg-red-500/15 text-red-300 hover:bg-red-500/25 disabled:opacity-50"
                    disabled={busy === 'control'} onClick={() => setCrawlPaused(true)}>
              {busy === 'control' ? '...' : 'Stop crawling'}
            </button>
          )}
          <button className={BTN} onClick={() => { loadStats(); loadClubs() }}>Refresh</button>
        </div>

        {/* ── Filter card ─────────────────────────────────────────────── */}
        <section className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <span className={SECTION}>Filter clubs</span>
            {(filters.q || filters.association || filters.associations.length || filters.state
              || filters.postcode_from || filters.postcode_to || filters.contact || filters.person
              || filters.exclude_junior || filters.exclude_emailed || filters.exclude_carnival
              || filters.exclude_school) && (
              <button className="text-[11px] text-pb-faint hover:text-pb-accent"
                      onClick={() => setFilters({ q: '', state: '', association: '', associations: [],
                                                  postcode_from: '', postcode_to: '', contact: '',
                                                  person: '', exclude_junior: false, exclude_emailed: false,
                                                  exclude_carnival: false, exclude_school: false })}>
                Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-3 gap-y-2">
            <Field label="Search">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Club or association..."
                value={filters.q}
                onChange={(e) => setFilters(f => ({ ...f, q: e.target.value }))}
              />
            </Field>
            <Field label="Association">
              <div className="flex items-center gap-2">
                <AssocMultiSelect
                  options={assocOptions}
                  selected={filters.associations}
                  onChange={(a) => setFilters(f => ({ ...f, associations: a }))}
                  onSaveShort={saveAssocShort}
                />
                {filters.associations.length > 0 && (
                  <button className={BTN + ' whitespace-nowrap'} disabled={busy === 'resolve'}
                          onClick={resolveSelectedAssociations}
                          title="Fetch the complete club roster for the selected association(s) from PlayHQ">
                    {busy === 'resolve' ? 'Fetching…' : `Fetch roster${filters.associations.length > 1 ? 's' : ''}`}
                  </button>
                )}
              </div>
            </Field>
            <Field label="Association contains">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Name or short code..."
                value={filters.association}
                onChange={(e) => setFilters(f => ({ ...f, association: e.target.value }))}
              />
            </Field>
            <Field label="State">
              <select className={SELECT_CLS + ' w-full'} value={filters.state}
                      onChange={(e) => setFilters(f => ({ ...f, state: e.target.value }))}>
                <option value="">All states</option>
                {STATES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Postcode range">
              <div className="flex items-center gap-1">
                <input className={SELECT_CLS + ' w-full'} placeholder="from" inputMode="numeric"
                       value={filters.postcode_from}
                       onChange={(e) => setFilters(f => ({ ...f, postcode_from: e.target.value }))} />
                <span className="text-pb-faint">–</span>
                <input className={SELECT_CLS + ' w-full'} placeholder="to" inputMode="numeric"
                       value={filters.postcode_to}
                       onChange={(e) => setFilters(f => ({ ...f, postcode_to: e.target.value }))} />
              </div>
            </Field>
            <Field label="Contacts">
              <select className={SELECT_CLS + ' w-full'} value={filters.contact}
                      onChange={(e) => setFilters(f => ({ ...f, contact: e.target.value }))}>
                <option value="">Any contacts</option>
                <option value="any_email">Has an email (any)</option>
                <option value="named_email">Has a named email</option>
                <option value="pst">Has Pres + Sec + Treas (named, emailed)</option>
              </select>
            </Field>
            <Field label="Person name">
              <input
                className={SELECT_CLS + ' w-full'}
                placeholder="Person name contains..."
                value={filters.person}
                onChange={(e) => setFilters(f => ({ ...f, person: e.target.value }))}
              />
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 mt-2.5 pt-2.5 border-t pb-hairline">
            <span className="text-[10px] uppercase tracking-wide text-pb-faint">Exclude</span>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={filters.exclude_junior}
                     onChange={(e) => setFilters(f => ({ ...f, exclude_junior: e.target.checked }))} />
              Juniors
            </label>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={filters.exclude_carnival}
                     onChange={(e) => setFilters(f => ({ ...f, exclude_carnival: e.target.checked }))} />
              Carnivals
            </label>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={filters.exclude_school}
                     onChange={(e) => setFilters(f => ({ ...f, exclude_school: e.target.checked }))} />
              Schools
            </label>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={filters.exclude_emailed}
                     onChange={(e) => setFilters(f => ({ ...f, exclude_emailed: e.target.checked }))} />
              Already-emailed
            </label>
          </div>
        </section>

        {/* ── Actions card — everything here acts on the filtered list ─── */}
        <section className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <span className={SECTION}>Actions on the filtered list</span>
            <span className="text-[11px] text-pb-faint">{total} matching club(s)</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a className={BTN} href={api.mktExportCsvUrl(filters)} target="_blank" rel="noreferrer">
              Download CSV
            </a>
            <button className={BTN} disabled={busy === 'export'} onClick={exportComms}>
              {busy === 'export' ? 'Exporting...' : 'Export to BetterAdmin Comms'}
            </button>
            <button className={BTN} disabled={busy === 'supp'} onClick={syncSuppressions}>
              {busy === 'supp' ? 'Syncing...' : 'Sync suppressions'}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-2.5 pt-2.5 border-t pb-hairline">
            <span className="text-[10px] uppercase tracking-wide text-pb-faint mr-1">Bulk update</span>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkEmailed(true)}>
              Mark all emailed
            </button>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkEmailed(false)}>
              Unmark all emailed
            </button>
            <span className="text-pb-faint px-1">·</span>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkExcluded(true)}>
              Exclude all
            </button>
            <button className={BTN} disabled={busy === 'bulk' || !total} onClick={() => bulkExcluded(false)}>
              Include all
            </button>
          </div>
        </section>

        {msg && <div className="mb-3 text-xs text-accent border border-accent/40 bg-accent/10 rounded px-3 py-2">{msg}</div>}
        {error && <div className="mb-3 text-xs text-red-300 border border-red-500/40 bg-red-500/10 rounded px-3 py-2">{error}</div>}

        {/* ── Results toolbar: grouping/sort on the left, pager on the right ── */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <div className="flex flex-wrap items-center gap-4">
            <span className={SECTION}>View</span>
            <label className="flex items-center gap-1.5 text-xs text-pb-dim">
              <input type="checkbox" checked={view.group}
                     onChange={(e) => setView(v => ({ ...v, group: e.target.checked }))} />
              Group by association
            </label>
            {view.group && (
              <div className="flex items-center gap-1 text-xs text-pb-dim">
                <span>Assoc.</span>
                <select className={SELECT_CLS} value={view.assocSort}
                        onChange={(e) => setView(v => ({ ...v, assocSort: e.target.value }))}>
                  <option value="asc">A → Z</option>
                  <option value="desc">Z → A</option>
                </select>
              </div>
            )}
            <div className="flex items-center gap-1 text-xs text-pb-dim">
              <span>Clubs</span>
              <select className={SELECT_CLS} value={view.clubSort}
                      onChange={(e) => setView(v => ({ ...v, clubSort: e.target.value }))}>
                <option value="asc">A → Z</option>
                <option value="desc">Z → A</option>
              </select>
            </div>
          </div>
        </div>

        <Pager total={total} page={page} pageSize={PAGE} onPage={setPage} loading={loading} />

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
                {clubs.map((c, idx) => {
                  const top = c.contacts && c.contacts[0]
                  const more = (c.contacts?.length || 0) - 1
                  const isOpen = expanded === c.id
                  // When grouping, drop an association header row each time the
                  // association name changes from the club above it.
                  const groupName = c.association_name || 'Unassigned'
                  const prevName = idx > 0 ? (clubs[idx - 1].association_name || 'Unassigned') : null
                  const showHeader = view.group && groupName !== prevName
                  return [
                    showHeader && (
                      <tr key={c.id + '-h'} className="bg-pb-surface2/70 border-t-2 border-pb-accent/30">
                        <td colSpan={5} className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-pb-accent">
                          {groupName}
                        </td>
                      </tr>
                    ),
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
                          {c.excluded && (
                            <span className="text-[10px] text-red-300 border border-red-500/40 rounded px-1"
                                  title="Excluded from all outreach">excluded</span>
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
                                      onToggleEmailed={toggleEmailed}
                                      onToggleExcluded={toggleExcluded}
                                      onSaveUtm={saveUtm} />
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
        {!loading && total > PAGE && (
          <Pager total={total} page={page} pageSize={PAGE} onPage={setPage} loading={loading} />
        )}
      </div>
    </AdminLayout>
  )
}
