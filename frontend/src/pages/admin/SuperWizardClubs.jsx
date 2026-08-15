import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { Modal, Field, TextInput, Btn, Pill } from '../../components/admin/crm/ui'

// Clubs Searched or Selected in the Wizard.
//
// The Meta Ads page reports these as two separate read-only tables; this is the
// same clubs merged into one row each, matched to the Club Directory, and made
// actionable: filter down to who is worth contacting, turn that set into a
// BetterComms list of their directory contacts, then see which of them have
// since been emailed through one of those lists. See
// services/wizard_club_lists.py for how the matching and the email reporting
// are worked out.

const fmtTime = (iso) => {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '–'
  return d.toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

const fmtDate = (iso) => {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '–'
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

const SOURCE_LABEL = { both: 'Searched & selected', selected: 'Selected', searched: 'Searched' }

// The furthest step a club reached, exactly as meta_ads._SELECTED_STEP_LABEL
// writes it. A club that only ever searched has no step at all, which is why
// "Not completed" is the absence of the completed label rather than a step of
// its own — a searched-only club has plainly not registered either.
const STEP_COMPLETED = 'Registration completed'
const STEP_TERMS = 'Reached Terms & privacy'

function Chip({ active, onClick, children, title }) {
  return (
    <button
      type="button" onClick={onClick} title={title}
      className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
        active
          ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
          : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}
    >
      {children}
    </button>
  )
}

function SortHeader({ label, active, dir, onClick, align = 'left' }) {
  return (
    <th className={`px-2 py-2 font-medium select-none ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button type="button" onClick={onClick}
        className={`inline-flex items-center gap-1 hover:text-pb-text ${active ? 'text-pb-text' : ''}`}>
        {label}
        <span className="text-[9px] opacity-70">{active ? (dir === 'asc' ? '▲' : '▼') : '↕'}</span>
      </button>
    </th>
  )
}

// The club's send history through a list this page created — the campaign that
// reached it and when. Nothing is stored per send; it is read back off the
// send audit, so a corrected or repeated send needs nothing done here.
function EmailedCell({ club }) {
  const [open, setOpen] = useState(false)
  if (!club.emailed) {
    return <span className="font-mono text-[9px] uppercase text-pb-faintest">Not emailed</span>
  }
  const [latest, ...rest] = club.emails
  return (
    <div className="leading-tight">
      <div className="text-pb-text text-[12px]">{latest.campaign_name}</div>
      <div className="text-pb-faint text-[11px]">
        {fmtTime(latest.sent_at)} · {latest.recipients} contact{latest.recipients === 1 ? '' : 's'}
      </div>
      {rest.length > 0 && (
        <button type="button" onClick={() => setOpen(v => !v)}
          className="font-mono text-[9px] uppercase text-pb-faint hover:text-pb-text mt-0.5">
          {open ? 'Hide' : `+${rest.length} earlier`}
        </button>
      )}
      {open && rest.map(e => (
        <div key={e.campaign_id} className="text-pb-faint text-[11px] mt-0.5">
          {e.campaign_name} · {fmtTime(e.sent_at)}
        </div>
      ))}
    </div>
  )
}

function CreateListModal({ open, onClose, clubs, onCreated }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (open) { setName(''); setErr(''); setResult(null); setBusy(false) }
  }, [open])

  const sendable = clubs.filter(c => c.directory && !c.directory.excluded && c.emailable_count > 0)
  const noContacts = clubs.filter(c => c.directory && !c.directory.excluded && c.emailable_count === 0)
  const unmatched = clubs.filter(c => !c.directory)
  const unresolvedRows = unmatched.filter(c => c.is_query_row)
  const plainUnmatched = unmatched.filter(c => !c.is_query_row)
  const excludedClubs = clubs.filter(c => c.directory?.excluded)
  const contactTotal = sendable.reduce((n, c) => n + c.emailable_count, 0)

  const submit = async () => {
    if (!name.trim()) { setErr('Enter a list name.'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.superWizardClubsCreateList({
        name: name.trim(),
        club_keys: clubs.map(c => c.key),
      })
      setResult(r)
      toast.success(`Created list "${r.name}" with ${r.added} contact${r.added === 1 ? '' : 's'}.`)
      onCreated?.()
    } catch (e) {
      setErr(e.message || 'Could not create the list')
    } finally { setBusy(false) }
  }

  const footer = result ? (
    <Btn variant="primary" sm onClick={onClose}>Done</Btn>
  ) : (
    <>
      <Btn variant="subtle" sm onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" sm onClick={submit} disabled={busy || !name.trim() || sendable.length === 0}>
        {busy ? 'Creating…' : 'Create list'}
      </Btn>
    </>
  )

  return (
    <Modal open={open} onClose={onClose} wide={!result} title="Create a BetterComms list" footer={footer}>
      {err && <div className="text-pb-red text-[13px] mb-3">{err}</div>}

      {result ? (
        <div className="space-y-2 text-[13px]">
          <div className="text-pb-text">
            Created list <span className="font-medium">"{result.name}"</span> with {result.added} contact
            {result.added === 1 ? '' : 's'} across {result.clubs} club{result.clubs === 1 ? '' : 's'}
            {result.created_contacts > 0 && <> ({result.created_contacts} new contact{result.created_contacts === 1 ? '' : 's'} created)</>}.
          </div>
          <div className="text-pb-faintest">
            Find it in <Link to="/admin/comms/lists" className="underline hover:text-pb-text">BetterComms → Lists</Link> under
            "Auto-generated lists". Send an email to it and this page will report the campaign and time against each club.
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-[13px] text-pb-faint">
            This creates a new list in BetterComms → Lists (under "Auto-generated lists") holding every Club Directory
            contact for the <span className="text-pb-text font-medium">{sendable.length}</span> club
            {sendable.length === 1 ? '' : 's'} below that has one — <span className="text-pb-text font-medium">{contactTotal}</span> contact
            {contactTotal === 1 ? '' : 's'} in all. A contact with no name on file is addressed as "Committee Members".
          </div>

          <div className="max-h-[40vh] overflow-y-auto rounded-lg border border-pb-hairline">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 bg-pb-surface">
                <tr className="text-left text-pb-faint border-b border-pb-hairline">
                  <th className="px-3 py-2 font-medium">Club</th>
                  <th className="px-3 py-2 font-medium">Club Directory</th>
                  <th className="px-3 py-2 font-medium text-right">Contacts</th>
                </tr>
              </thead>
              <tbody>
                {clubs.length === 0 && (
                  <tr><td colSpan={3} className="px-3 py-6 text-center text-pb-faintest">No clubs selected.</td></tr>
                )}
                {clubs.map(c => (
                  <tr key={c.key} className="border-b border-pb-hairline last:border-0">
                    <td className="px-3 py-2 text-pb-text">
                      {c.is_query_row ? <span className="text-pb-dim">Searched &ldquo;{c.name}&rdquo;</span> : c.name}
                    </td>
                    <td className="px-3 py-2 text-pb-faint">
                      {c.is_query_row
                        ? <span className="text-pb-red">Search not resolved to a club</span>
                        : !c.directory
                          ? <span className="text-pb-red">Not in the directory</span>
                          : c.directory.excluded
                            ? <span className="text-pb-red">Excluded from outreach</span>
                            : c.directory.name}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {c.emailable_count > 0
                        ? <span className="text-pb-text">{c.emailable_count}</span>
                        : <span className="text-pb-faintest">–</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(unmatched.length > 0 || excludedClubs.length > 0 || noContacts.length > 0) && (
            <div className="text-[11.5px] text-pb-faint space-y-0.5">
              {unresolvedRows.length > 0 && <div>{unresolvedRows.length} search{unresolvedRows.length === 1 ? '' : 'es'} could not be pinned to a club, so there is nobody to email — left out.</div>}
              {plainUnmatched.length > 0 && <div>{plainUnmatched.length} club{plainUnmatched.length === 1 ? '' : 's'} could not be matched to the Club Directory and will be left out.</div>}
              {excludedClubs.length > 0 && <div>{excludedClubs.length} club{excludedClubs.length === 1 ? '' : 's'} excluded from outreach in the Club Directory will be left out.</div>}
              {noContacts.length > 0 && <div>{noContacts.length} matched club{noContacts.length === 1 ? '' : 's'} has no contact with an email address on file.</div>}
            </div>
          )}

          <Field label="List name">
            <TextInput autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit() }}
              placeholder="e.g. Wizard drop-offs — August" />
          </Field>
          <div className="text-[11.5px] text-pb-faintest">
            If a list with that name already exists, a number is added to keep it unique.
          </div>
        </div>
      )}
    </Modal>
  )
}

function ImportSalesListModal({ open, onClose, clubs, onCreated }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (open) { setName(''); setErr(''); setResult(null); setBusy(false) }
  }, [open])

  const resolvable = clubs.filter(c => !c.is_query_row)
  const unresolvedRows = clubs.filter(c => c.is_query_row)

  const submit = async () => {
    if (!name.trim()) { setErr('Enter a list name.'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.salesWorkspaceImportFromWizardClubs({
        name: name.trim(), club_keys: clubs.map(c => c.key),
      })
      setResult(r)
      toast.success(`Imported "${r.name}" — ${r.clubs_added} club${r.clubs_added === 1 ? '' : 's'} in the queue.`)
      onCreated?.()
    } catch (e) {
      setErr(e.message || 'Could not import the list')
    } finally { setBusy(false) }
  }

  const footer = result ? (
    <Btn variant="primary" sm onClick={onClose}>Done</Btn>
  ) : (
    <>
      <Btn variant="subtle" sm onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" sm onClick={submit} disabled={busy || !name.trim() || resolvable.length === 0}>
        {busy ? 'Importing…' : 'Import to Sales List'}
      </Btn>
    </>
  )

  return (
    <Modal open={open} onClose={onClose} title="Import to a Sales List" footer={footer}>
      {err && <div className="text-pb-red text-[13px] mb-3">{err}</div>}

      {result ? (
        <div className="space-y-2 text-[13px]">
          <div className="text-pb-text">
            Imported <span className="font-medium">"{result.name}"</span> — {result.clubs_matched} matched club
            {result.clubs_matched === 1 ? '' : 's'}, each given an open deal in the queue.
            {result.clubs_unmatched?.length > 0 && <> {result.clubs_unmatched.length} couldn't be matched to the Club Directory.</>}
          </div>
          <div className="text-pb-faintest">
            Find it in <Link to="/admin/super/crm/sales-lists" className="underline hover:text-pb-text">Sales Lists</Link>, or
            filter the <Link to="/admin/super/crm/workspace" className="underline hover:text-pb-text">Sales Workspace</Link> queue
            to it directly.
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-[13px] text-pb-faint">
            Matches <span className="text-pb-text font-medium">{resolvable.length}</span> of the {clubs.length} selected club
            {clubs.length === 1 ? '' : 's'} to the Club Directory and gives each one an open deal at the Target stage (or
            leaves it alone if it's already further along), so it shows up in the Sales Workspace call queue.
            {unresolvedRows.length > 0 && (
              <> {unresolvedRows.length} unresolved search{unresolvedRows.length === 1 ? '' : 'es'} can't be matched and will be skipped.</>
            )}
          </div>
          <Field label="List name">
            <TextInput autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit() }}
              placeholder="e.g. Wizard drop-offs — August" />
          </Field>
        </div>
      )}
    </Modal>
  )
}

export default function SuperWizardClubs() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  const [q, setQ] = useState('')
  const [source, setSource] = useState('')          // '' | selected | searched
  const [emailed, setEmailed] = useState('')        // '' | yes | no
  const [progress, setProgress] = useState('')      // '' | completed | not_completed | terms | selected
  const [resolved, setResolved] = useState('')      // '' | yes | no
  const [sortBy, setSortBy] = useState('last_at')   // club | last_at | contacts
  const [sortDir, setSortDir] = useState('desc')
  const [checked, setChecked] = useState(() => new Set())
  const [showCreate, setShowCreate] = useState(false)
  const [showImportSales, setShowImportSales] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setErr('')
    try {
      setData(await api.superWizardClubs())
    } catch (e) {
      setErr(e.message || 'Could not load the wizard clubs')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const clubs = data?.clubs || []

  const shown = useMemo(() => {
    const term = q.trim().toLowerCase()
    let out = clubs.filter(c => {
      if (term && !(c.name || '').toLowerCase().includes(term)
        && !((c.directory?.name || '').toLowerCase().includes(term))) return false
      if (source === 'selected' && !c.in_selected) return false
      if (source === 'searched' && !c.in_searched) return false
      if (emailed === 'yes' && !c.emailed) return false
      if (emailed === 'no' && c.emailed) return false
      const step = c.furthest_step || ''
      if (progress === 'completed' && step !== STEP_COMPLETED) return false
      if (progress === 'not_completed' && step === STEP_COMPLETED) return false
      if (progress === 'terms' && step !== STEP_TERMS) return false
      if (progress === 'selected' && step !== 'Club selected') return false
      if (resolved === 'yes' && c.is_query_row) return false
      if (resolved === 'no' && !c.is_query_row) return false
      return true
    })
    const dir = sortDir === 'asc' ? 1 : -1
    const key = {
      club: c => (c.name || '').toLowerCase(),
      last_at: c => c.last_at || '',
      contacts: c => c.contact_count || 0,
    }[sortBy] || (() => 0)
    out = [...out].sort((a, b) => {
      const av = key(a), bv = key(b)
      if (av < bv) return -dir
      if (av > bv) return dir
      // Stable tie-break so two clubs last seen the same minute don't shuffle.
      return (a.name || '').localeCompare(b.name || '')
    })
    return out
  }, [clubs, q, source, emailed, progress, resolved, sortBy, sortDir])

  // A tick survives a filter change but never targets a club that is no longer
  // on screen — "create a list from what I picked" has to mean what it says.
  const selectedRows = useMemo(
    () => shown.filter(c => checked.has(c.key)), [shown, checked])
  // With nothing ticked, the button acts on the whole filtered set — the
  // "Send the filtered result set" case, without making the user tick 40 rows.
  const targetRows = selectedRows.length ? selectedRows : shown

  const allShownChecked = shown.length > 0 && shown.every(c => checked.has(c.key))
  const someShownChecked = shown.some(c => checked.has(c.key))

  const toggleAll = () => {
    setChecked(prev => {
      const next = new Set(prev)
      if (allShownChecked) shown.forEach(c => next.delete(c.key))
      else shown.forEach(c => next.add(c.key))
      return next
    })
  }
  const toggleOne = (key) => setChecked(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key); else next.add(key)
    return next
  })

  const clickSort = (key) => {
    if (sortBy !== key) {
      setSortBy(key)
      // Newest-first reads right for a date, A-Z for a name.
      setSortDir(key === 'club' ? 'asc' : 'desc')
      return
    }
    setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
  }

  const shownContacts = shown.reduce((n, c) => n + (c.contact_count || 0), 0)
  const shownEmailable = shown.reduce((n, c) => n + (c.emailable_count || 0), 0)
  const shownCompleted = shown.filter(c => c.furthest_step === STEP_COMPLETED).length
  const shownUnresolved = shown.filter(c => c.is_query_row).length

  return (
    <AdminLayout>
      <div className="mb-1">
        <Link to="/admin/super/hub/crm" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
          ← CRM
        </Link>
      </div>
      <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
        <div>
          <h1 className="font-display font-bold text-xl">Clubs Searched or Selected in the Wizard</h1>
          <p className="text-pb-faint text-[13px] mt-0.5 max-w-3xl">
            Every club that typed its own name into the trial signup search or picked itself in the registration
            wizard, matched to the Club Directory. Pick the ones worth contacting and send their directory contacts
            to BetterComms as a list; anything emailed through one of those lists is reported back here.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/admin/super/crm/sales-lists" className="font-mono text-[10px] uppercase text-pb-faint hover:text-pb-text">
            Sales lists
          </Link>
          <Link to="/admin/comms/lists" className="font-mono text-[10px] uppercase text-pb-faint hover:text-pb-text">
            Comms lists
          </Link>
          <Btn variant="subtle" sm onClick={() => setShowImportSales(true)} disabled={targetRows.length === 0}>
            Import to Sales List{selectedRows.length ? ` (${selectedRows.length})` : ''}
          </Btn>
          <Btn variant="primary" sm onClick={() => setShowCreate(true)} disabled={targetRows.length === 0}>
            Create List{selectedRows.length ? ` (${selectedRows.length})` : ''}
          </Btn>
        </div>
      </div>

      {loading ? <PbSpinner message="Loading wizard clubs…" /> : err ? (
        <div className="pb-card px-4 py-6 text-[13px] text-pb-red">{err}</div>
      ) : (
        <>
          <div className="pb-card px-4 py-3 mb-4">
            <div className="flex items-center gap-2 flex-wrap">
              <input
                value={q} onChange={e => setQ(e.target.value)} placeholder="Search club name…"
                className="px-2.5 py-1.5 rounded-lg bg-pb-surface2 border border-pb-hairline2 text-[13px] text-pb-text placeholder:text-pb-faintest focus:outline-none focus:border-pb-accent/50"
                style={{ minWidth: 220 }}
              />
              <span className="text-pb-faintest text-[11px] uppercase font-mono ml-1">Source</span>
              <Chip active={source === ''} onClick={() => setSource('')}>All</Chip>
              <Chip active={source === 'selected'} onClick={() => setSource('selected')}>Selected</Chip>
              <Chip active={source === 'searched'} onClick={() => setSource('searched')}>Searched</Chip>
              <span className="text-pb-faintest text-[11px] uppercase font-mono ml-1">Progress</span>
              <Chip active={progress === ''} onClick={() => setProgress('')}>All</Chip>
              <Chip active={progress === 'completed'} onClick={() => setProgress('completed')}
                title="Clubs that finished the wizard and registered">Registration completed</Chip>
              <Chip active={progress === 'not_completed'} onClick={() => setProgress('not_completed')}
                title="Everyone who dropped off before registering — the ones worth chasing">Not completed</Chip>
              <Chip active={progress === 'terms'} onClick={() => setProgress('terms')}
                title="Got as far as Terms &amp; privacy, then stopped">Reached terms</Chip>
              <span className="text-pb-faintest text-[11px] uppercase font-mono ml-1">Match</span>
              <Chip active={resolved === ''} onClick={() => setResolved('')}>All</Chip>
              <Chip active={resolved === 'yes'} onClick={() => setResolved('yes')}
                title="Searches we could pin to a specific club">Resolved</Chip>
              <Chip active={resolved === 'no'} onClick={() => setResolved('no')}
                title="Half-typed searches whose match can't be trusted — the club is a guess">Unresolved</Chip>
              <span className="text-pb-faintest text-[11px] uppercase font-mono ml-1">Contact</span>
              <Chip active={emailed === ''} onClick={() => setEmailed('')}>All</Chip>
              <Chip active={emailed === 'yes'} onClick={() => setEmailed('yes')}>Emailed</Chip>
              <Chip active={emailed === 'no'} onClick={() => setEmailed('no')}>Not emailed</Chip>
            </div>
            <div className="text-[12px] text-pb-faint mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
              <span><span className="text-pb-text font-medium">{shown.length}</span> club{shown.length === 1 ? '' : 's'} shown{shown.length !== clubs.length && <> of {clubs.length}</>}</span>
              <span><span className="text-pb-text font-medium">{shownContacts}</span> directory contact{shownContacts === 1 ? '' : 's'}</span>
              <span><span className="text-pb-text font-medium">{shownEmailable}</span> emailable</span>
              {selectedRows.length > 0 && (
                <span className="text-pb-accent">{selectedRows.length} ticked</span>
              )}
              {shownUnresolved > 0 && <span className="text-amber-300">{shownUnresolved} unresolved</span>}
              <span className="text-pb-faintest">{shownCompleted} registered · {data.emailed_clubs} emailed so far</span>
            </div>
          </div>

          <div className="pb-card overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-pb-faint border-b border-pb-hairline">
                  <th className="px-2 py-2 w-8">
                    <input
                      type="checkbox" checked={allShownChecked}
                      ref={el => { if (el) el.indeterminate = !allShownChecked && someShownChecked }}
                      onChange={toggleAll} aria-label="Select all clubs shown"
                      className="cursor-pointer"
                    />
                  </th>
                  <SortHeader label="Club" active={sortBy === 'club'} dir={sortDir} onClick={() => clickSort('club')} />
                  <th className="px-2 py-2 font-medium">Source</th>
                  <th className="px-2 py-2 font-medium">Club Directory</th>
                  <SortHeader label="Contacts" align="right" active={sortBy === 'contacts'} dir={sortDir} onClick={() => clickSort('contacts')} />
                  <SortHeader label="Last seen" active={sortBy === 'last_at'} dir={sortDir} onClick={() => clickSort('last_at')} />
                  <th className="px-2 py-2 font-medium">Emailed</th>
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-6 text-center text-pb-faintest">
                    {clubs.length === 0 ? 'No club has searched or selected itself yet.' : 'No clubs match these filters.'}
                  </td></tr>
                )}
                {shown.map(c => (
                  <tr key={c.key} className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2/40 align-top">
                    <td className="px-2 py-2.5">
                      <input type="checkbox" checked={checked.has(c.key)} onChange={() => toggleOne(c.key)}
                        aria-label={`Select ${c.name}`} className="cursor-pointer" />
                    </td>
                    <td className="px-2 py-2.5">
                      {c.is_query_row ? (
                        <>
                          <div className="text-pb-dim">Searched &ldquo;{c.name}&rdquo;</div>
                          <div className="text-pb-faintest text-[11px]">
                            {c.guess_name ? `Maybe ${c.guess_name}` : 'No clear match'}
                          </div>
                        </>
                      ) : (
                        <div className="text-pb-text font-medium">{c.name}</div>
                      )}
                      {c.furthest_step && (
                        <div className="mt-0.5">
                          <span className={`font-mono text-[9px] uppercase px-1.5 py-0.5 rounded-full border ${
                            c.furthest_step === STEP_COMPLETED
                              ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                              : c.furthest_step === STEP_TERMS
                                ? 'border-amber-500/40 text-amber-300 bg-amber-500/10'
                                : 'border-pb-hairline text-pb-faintest'}`}>
                            {c.furthest_step}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2.5 whitespace-nowrap">
                      <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded-full border border-pb-hairline2 text-pb-faint">
                        {SOURCE_LABEL[c.source] || c.source}
                      </span>
                      {c.via_meta && (
                        <span className="ml-1 font-mono text-[9px] uppercase px-1.5 py-0.5 rounded-full border border-violet-500/40 text-violet-300 bg-violet-500/10">
                          Meta
                        </span>
                      )}
                      {/* What was actually typed. A club is only as trustworthy
                          as the search behind it, so the terms are on the row
                          rather than buried in a tooltip. */}
                      {(c.queries || []).length > 0 && (
                        <div className="text-pb-faintest text-[11px] mt-1 max-w-[15rem] truncate"
                          title={c.queries.map(t => `“${t}”`).join(' · ')}>
                          {c.queries.map(t => `“${t}”`).join(' · ')}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2.5">
                      {!c.directory ? (
                        <span className="text-pb-faintest">
                          {c.is_query_row ? 'Search not resolved' : 'Not matched'}
                        </span>
                      ) : (
                        <div className="leading-tight">
                          <div className="text-pb-dim">{c.directory.name}</div>
                          <div className="text-pb-faintest text-[11px]">
                            {[c.directory.state, c.directory.association].filter(Boolean).join(' · ') || '—'}
                          </div>
                          {c.directory.excluded && <Pill tone="red">Excluded</Pill>}
                          {c.directory.is_customer && <Pill tone="green">Customer</Pill>}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2.5 text-right whitespace-nowrap">
                      <span className="text-pb-text">{c.contact_count}</span>
                      {c.contact_count > 0 && (
                        <span className="text-pb-faintest text-[11px]"> / {c.emailable_count} emailable</span>
                      )}
                    </td>
                    <td className="px-2 py-2.5 text-pb-dim whitespace-nowrap">{fmtDate(c.last_at)}</td>
                    <td className="px-2 py-2.5">
                      <EmailedCell club={c} />
                      {c.lists.length > 0 && (
                        <div className="text-pb-faintest text-[10px] mt-0.5">
                          In {c.lists.length} list{c.lists.length === 1 ? '' : 's'} · {c.lists[0].list_name}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <CreateListModal
        open={showCreate} onClose={() => setShowCreate(false)} clubs={targetRows}
        onCreated={() => { setChecked(new Set()); load() }}
      />
      <ImportSalesListModal
        open={showImportSales} onClose={() => setShowImportSales(false)} clubs={targetRows}
        onCreated={() => setChecked(new Set())}
      />
    </AdminLayout>
  )
}
