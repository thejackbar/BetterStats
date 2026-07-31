import { useState } from 'react'
import { Modal, Field, TextInput, Select, Btn, Pill } from './ui'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'

// Turn the CRM's current filtered deal set into an auto-generated BetterComms
// List. Steps: name → (prepare) → resolve any deal whose contact isn't already
// a BetterComms contact → confirm any deal left without a valid email → commit.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const validEmail = (e) => EMAIL_RE.test((e || '').trim())

function splitName(full) {
  const parts = (full || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return { first: '', last: '' }
  if (parts.length === 1) return { first: parts[0], last: '' }
  return { first: parts[0], last: parts.slice(1).join(' ') }
}

// Editor row for one unmatched deal, pre-selecting the resolved suggestion.
function initRow(u) {
  let mode = 'skip'
  let first = '', last = '', email = ''
  const s = u.suggested
  if (s?.email) {
    const inList = (u.club_contacts || []).some(c => c.email === s.email)
    if (inList) {
      mode = `email:${s.email}`
    } else {
      mode = 'manual'
      const sp = splitName(s.name)
      first = sp.first; last = sp.last; email = s.email
    }
  }
  return { ...u, mode, first, last, email }
}

export default function CreateListModal({ open, onClose, deals, defaultName = '', filterSummary = [] }) {
  const toast = useToast()
  const [step, setStep] = useState('name')
  const [name, setName] = useState(defaultName)
  const [prep, setPrep] = useState(null)
  const [rows, setRows] = useState([])
  const [pending, setPending] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  const dealIds = (deals || []).map(d => d.id)

  const close = () => {
    setStep('name'); setName(defaultName); setPrep(null); setRows([])
    setPending([]); setErr(''); setResult(null); setBusy(false)
    onClose()
  }

  const doCommit = async (prepResult, resolutions) => {
    setBusy(true); setErr('')
    try {
      const r = await api.superCrmListExportCommit({
        name: name.trim(),
        matched_contact_ids: (prepResult.matched || []).map(m => m.contact_id),
        resolutions,
      })
      setResult(r); setStep('done')
      toast.success(`Created list "${r.name}" with ${r.added} contact${r.added === 1 ? '' : 's'}.`)
    } catch (e) {
      setErr(e.message || 'Could not create the list')
    } finally { setBusy(false) }
  }

  const onContinue = async () => {
    if (!name.trim()) { setErr('Enter a list name.'); return }
    setBusy(true); setErr('')
    try {
      const p = await api.superCrmListExportPrepare(dealIds)
      setPrep(p)
      if (!(p.unmatched || []).length) {
        await doCommit(p, [])
        return
      }
      setRows((p.unmatched || []).map(initRow))
      setStep('resolve')
    } catch (e) {
      setErr(e.message || 'Could not prepare the list')
    } finally { setBusy(false) }
  }

  const setRow = (i, patch) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  // resolutions to send + the deals left without a valid email (won't be sent).
  const buildResolutions = () => {
    const resolutions = []
    const skipped = []
    for (const r of rows) {
      if (r.mode.startsWith('email:')) {
        const em = r.mode.slice(6)
        const c = (r.club_contacts || []).find(cc => cc.email === em)
        resolutions.push({ deal_id: r.deal_id, club_id: r.club_id, email: em, name: c?.name || '' })
      } else if (r.mode === 'manual' && r.first.trim() && r.last.trim() && validEmail(r.email)) {
        resolutions.push({
          deal_id: r.deal_id, club_id: r.club_id, email: r.email.trim(),
          first_name: r.first.trim(), last_name: r.last.trim(),
        })
      } else {
        skipped.push(r)
      }
    }
    return { resolutions, skipped }
  }

  const onSubmitResolve = () => {
    const { resolutions, skipped } = buildResolutions()
    if (skipped.length) { setPending(skipped); setStep('confirm'); return }
    doCommit(prep, resolutions)
  }

  const onConfirm = () => doCommit(prep, buildResolutions().resolutions)

  const matchedCount = (prep?.matched || []).length

  // ── footers per step ──
  let footer = null
  if (step === 'name') {
    footer = <>
      <Btn variant="subtle" sm onClick={close}>Cancel</Btn>
      <Btn variant="primary" sm onClick={onContinue} disabled={busy || !name.trim() || dealIds.length === 0}>
        {busy ? 'Preparing…' : 'Continue'}
      </Btn>
    </>
  } else if (step === 'resolve') {
    footer = <>
      <Btn variant="subtle" sm onClick={close}>Cancel</Btn>
      <Btn variant="primary" sm onClick={onSubmitResolve} disabled={busy}>{busy ? 'Working…' : 'Submit'}</Btn>
    </>
  } else if (step === 'confirm') {
    footer = <>
      <Btn variant="subtle" sm onClick={() => setStep('resolve')}>Back</Btn>
      <Btn variant="primary" sm onClick={onConfirm} disabled={busy}>{busy ? 'Creating…' : 'Confirm & create list'}</Btn>
    </>
  } else if (step === 'done') {
    footer = <Btn variant="primary" sm onClick={close}>Done</Btn>
  }

  const missingContact = (d) => !(d.point_of_contact_name || '').trim()
  const missingEmail = (d) => !validEmail(d.point_of_contact_email)
  const missingCount = (deals || []).filter(d => missingContact(d) || missingEmail(d)).length

  return (
    <Modal open={open} onClose={close} wide={step === 'name' || step === 'resolve' || step === 'confirm'}
      title="Create a BetterComms list" footer={footer}>
      {err && <div className="text-pb-red text-[13px] mb-3">{err}</div>}

      {step === 'name' && (
        <div className="space-y-3">
          <div className="text-[13px] text-pb-faint">
            This creates a new list in BetterComms → Lists (under "Auto-generated lists") from the{' '}
            <span className="text-pb-text font-medium">{dealIds.length}</span> deal{dealIds.length === 1 ? '' : 's'} currently shown,
            one contact per deal.
          </div>

          {/* Which searches / filters / ranges produced this result set. */}
          <div className="rounded-lg border border-pb-hairline px-3 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-pb-faint mb-1.5">Filters applied</div>
            {filterSummary.length === 0 ? (
              <div className="text-[12.5px] text-pb-faintest">No filters — every deal in the pipeline.</div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {filterSummary.map((f, i) => (
                  <span key={i} className="inline-flex items-center gap-1 rounded-full border border-pb-hairline2 px-2 py-0.5 text-[11.5px]">
                    <span className="text-pb-faint">{f.label}:</span>
                    <span className="text-pb-text font-medium">{f.value}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* The deals in the set, so it's clear who's about to be included and
              which ones are missing a contact name or email. */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[11px] uppercase tracking-wide text-pb-faint">
                Deals in this list ({deals.length})
              </div>
              {missingCount > 0 && (
                <Pill tone="red">{missingCount} missing contact or email</Pill>
              )}
            </div>
            <div className="max-h-[44vh] overflow-y-auto rounded-lg border border-pb-hairline">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-pb-surface">
                  <tr className="text-left text-pb-faint border-b border-pb-hairline">
                    <th className="px-3 py-2 font-medium">Contact name</th>
                    <th className="px-3 py-2 font-medium">Email</th>
                    <th className="px-3 py-2 font-medium">Club</th>
                    <th className="px-3 py-2 font-medium">Stage</th>
                  </tr>
                </thead>
                <tbody>
                  {deals.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-6 text-center text-pb-faintest">No deals selected.</td></tr>
                  )}
                  {deals.map(d => (
                    <tr key={d.id} className="border-b border-pb-hairline last:border-0">
                      <td className="px-3 py-2">
                        {missingContact(d)
                          ? <span className="text-pb-red">Missing</span>
                          : <span className="text-pb-text">{d.point_of_contact_name}</span>}
                      </td>
                      <td className="px-3 py-2">
                        {missingEmail(d)
                          ? <span className="text-pb-red">{d.point_of_contact_email ? 'Invalid email' : 'Missing'}</span>
                          : <span className="text-pb-text">{d.point_of_contact_email}</span>}
                      </td>
                      <td className="px-3 py-2 text-pb-faint">{d.marketing_club_name || d.title || '—'}</td>
                      <td className="px-3 py-2 text-pb-faint">{d.stage_name || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {missingCount > 0 && (
              <div className="text-[11.5px] text-pb-faint mt-1.5">
                Deals missing a contact name or a valid email are highlighted. You can fill them in at the next step;
                any left without a valid email won't receive an email and won't be added to the list.
              </div>
            )}
          </div>

          <Field label="List name">
            <TextInput autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') onContinue() }}
              placeholder="e.g. Trial Ending Conversion" />
          </Field>
          <div className="text-[11.5px] text-pb-faintest">
            If a list with that name already exists, a number is added to keep it unique.
          </div>
        </div>
      )}

      {step === 'resolve' && (
        <div className="space-y-3">
          <div className="text-[13px] text-pb-faint">
            {matchedCount > 0 && <><Pill tone="green">{matchedCount}</Pill> matched an existing contact and will be added automatically. </>}
            The {rows.length} below need a contact: pick one of the club's contacts, or enter a name and email by hand.
            Set a deal to "Don't include" to leave it out (it won't receive an email).
          </div>
          <div className="max-h-[52vh] overflow-y-auto pb-hairline rounded-lg border border-pb-hairline">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-pb-faint border-b border-pb-hairline">
                  <th className="px-3 py-2 font-medium">Club</th>
                  <th className="px-3 py-2 font-medium">Contact</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.deal_id} className="border-b border-pb-hairline last:border-0 align-top">
                    <td className="px-3 py-2.5 text-pb-text w-1/3">{r.club_name}</td>
                    <td className="px-3 py-2.5">
                      <Select value={r.mode} onChange={e => setRow(i, { mode: e.target.value })}>
                        {(r.club_contacts || []).map(c => (
                          <option key={c.email} value={`email:${c.email}`}>
                            {(c.name || c.email)}{c.role ? ` — ${c.role}` : ''}
                          </option>
                        ))}
                        <option value="manual">Enter manually…</option>
                        <option value="skip">Don't include (no email)</option>
                      </Select>
                      {r.mode === 'manual' && (
                        <div className="flex flex-wrap gap-2 mt-2">
                          <TextInput placeholder="First name" value={r.first}
                            onChange={e => setRow(i, { first: e.target.value })} style={{ width: 120 }} />
                          <TextInput placeholder="Last name" value={r.last}
                            onChange={e => setRow(i, { last: e.target.value })} style={{ width: 120 }} />
                          <TextInput placeholder="Email" value={r.email}
                            onChange={e => setRow(i, { email: e.target.value })} style={{ width: 200 }}
                            className={r.email && !validEmail(r.email) ? 'border-pb-red' : ''} />
                        </div>
                      )}
                      {r.mode.startsWith('email:') && (
                        <div className="text-[11px] text-pb-faintest mt-1">{r.mode.slice(6)}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {step === 'confirm' && (
        <div className="space-y-3">
          <div className="text-[13px] text-pb-text">
            {pending.length} deal{pending.length === 1 ? '' : 's'} {pending.length === 1 ? 'does' : 'do'} not have a
            complete name and valid email, so {pending.length === 1 ? 'it' : 'they'} won't receive an email and won't be
            added to the list:
          </div>
          <ul className="text-[13px] text-pb-faint list-disc pl-5 max-h-[40vh] overflow-y-auto">
            {pending.map(r => <li key={r.deal_id}>{r.club_name}</li>)}
          </ul>
          <div className="text-[12px] text-pb-faintest">Everyone else will be added. Continue?</div>
        </div>
      )}

      {step === 'done' && result && (
        <div className="space-y-2 text-[13px]">
          <div className="text-pb-text">
            Created list <span className="font-medium">"{result.name}"</span> with {result.added} contact{result.added === 1 ? '' : 's'}
            {result.created_contacts > 0 && <> ({result.created_contacts} new contact{result.created_contacts === 1 ? '' : 's'} created)</>}.
          </div>
          {(result.skipped || []).length > 0 && (
            <div className="text-pb-faint">{result.skipped.length} entr{result.skipped.length === 1 ? 'y was' : 'ies were'} skipped for an invalid email.</div>
          )}
          <div className="text-pb-faintest">Find it in BetterComms → Lists under "Auto-generated lists".</div>
        </div>
      )}
    </Modal>
  )
}
