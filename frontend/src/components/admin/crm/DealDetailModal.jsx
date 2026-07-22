import { useState, useEffect, useCallback } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { Modal, Field, TextInput, NumberInput, Select, TextArea, Btn, Pill, money, moneyToCents, centsToMoneyInput } from './ui'

// Deal detail/edit — used by BOTH the club CRM module and the platform-scope
// Super Admin sales pipeline. `client` bundles the scope-specific api.js calls
// (club vs platform) so this component itself is scope-agnostic.
export default function DealDetailModal({ dealId, open, onClose, stages, client, onChanged, moduleOptions }) {
  const toast = useToast()
  const [deal, setDeal] = useState(null)
  const [activities, setActivities] = useState([])
  const [contacts, setContacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [noteType, setNoteType] = useState('note')
  const [lostReason, setLostReason] = useState('')
  const [showLostBox, setShowLostBox] = useState(false)
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')

  const load = useCallback(() => {
    if (!dealId) return
    setLoading(true)
    Promise.all([client.getDeal(dealId), client.listActivities(dealId), client.listContacts(dealId)])
      .then(([d, a, c]) => { setDeal(d); setActivities(a.activities || []); setContacts(c.contacts || []) })
      .catch(e => toast.error(e.message || 'Could not load deal'))
      .finally(() => setLoading(false))
  }, [dealId, client, toast])

  useEffect(() => { if (open) load() }, [open, load])

  if (!open) return null

  const refresh = async () => { await load(); onChanged?.() }

  const patch = async (fields) => {
    setSaving(true)
    try {
      const updated = await client.updateDeal(dealId, fields)
      setDeal(updated)
      onChanged?.()
    } catch (e) { toast.error(e.message || 'Could not save') } finally { setSaving(false) }
  }

  const moveStage = async (stageId) => {
    setSaving(true)
    try {
      const updated = await client.moveStage(dealId, { stage_id: stageId })
      setDeal(updated)
      onChanged?.()
    } catch (e) { toast.error(e.message || 'Could not move stage') } finally { setSaving(false) }
  }

  const closeDeal = async (status) => {
    if (status === 'lost' && !showLostBox) { setShowLostBox(true); return }
    setSaving(true)
    try {
      const updated = await client.closeDeal(dealId, { status, lost_reason: status === 'lost' ? lostReason : null })
      setDeal(updated)
      setShowLostBox(false)
      onChanged?.()
    } catch (e) { toast.error(e.message || 'Could not close deal') } finally { setSaving(false) }
  }

  const archive = async () => {
    if (!window.confirm('Archive this deal? It will drop off the board.')) return
    try {
      await client.archiveDeal(dealId)
      onChanged?.()
      onClose()
    } catch (e) { toast.error(e.message || 'Could not archive') }
  }

  const addActivity = async (e) => {
    e.preventDefault()
    if (!note.trim()) return
    try {
      await client.addActivity(dealId, { type: noteType, body: note.trim() })
      setNote('')
      await refresh()
    } catch (e2) { toast.error(e2.message || 'Could not add note') }
  }

  const addContact = async (e) => {
    e.preventDefault()
    if (!contactName.trim()) return
    try {
      await client.linkContact(dealId, { full_name: contactName.trim(), email: contactEmail.trim() || undefined })
      setContactName(''); setContactEmail('')
      await refresh()
    } catch (e2) { toast.error(e2.message || 'Could not add contact') }
  }

  const removeContact = async (personId) => {
    try { await client.unlinkContact(dealId, personId); await refresh() }
    catch (e) { toast.error(e.message || 'Could not remove contact') }
  }

  const toggleModule = (key) => {
    const cur = deal?.module_keys || []
    const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
    patch({ module_keys: next })
  }

  return (
    <Modal open={open} onClose={onClose} wide title={deal ? deal.title : 'Deal'}
      footer={deal && deal.status === 'open' ? (
        <>
          <Btn variant="danger" onClick={archive}>Archive</Btn>
          <Btn variant="danger" onClick={() => closeDeal('lost')}>Mark Lost</Btn>
          <Btn variant="primary" onClick={() => closeDeal('won')}>Mark Won</Btn>
        </>
      ) : deal ? <Btn variant="ghost" onClick={archive}>Archive</Btn> : null}>
      {loading || !deal ? <p className="text-pb-faint text-sm">Loading…</p> : (
        <div className="space-y-5">
          {deal.status !== 'open' && (
            <Pill tone={deal.status === 'won' ? 'green' : 'red'}>{deal.status === 'won' ? 'WON' : 'LOST'}</Pill>
          )}
          <div className="flex flex-wrap gap-3">
            <Field label="Title" half>
              <TextInput defaultValue={deal.title} onBlur={e => e.target.value !== deal.title && patch({ title: e.target.value })} />
            </Field>
            <Field label="Value ($)" half>
              <NumberInput defaultValue={centsToMoneyInput(deal.value_cents)} min={0}
                onBlur={e => patch({ value_cents: moneyToCents(e.target.value) })} />
            </Field>
            <Field label="Stage" half>
              <Select value={deal.stage_id} disabled={saving} onChange={e => moveStage(e.target.value)}>
                {(stages || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
            <Field label="Probability override (%)" hint={`Stage default: ${deal.effective_probability ?? '—'}%`} half>
              <NumberInput min={0} max={100} defaultValue={deal.probability ?? ''} placeholder="auto"
                onBlur={e => patch({ probability: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Expected close date" half>
              <TextInput type="date" defaultValue={deal.expected_close_date || ''}
                onBlur={e => patch({ expected_close_date: e.target.value || null })} />
            </Field>
            <Field label="Weighted value" half>
              <div className="px-2.5 py-2 text-[13.5px] text-pb-faint">{money(deal.weighted_value_cents)}</div>
            </Field>
          </div>

          {showLostBox && (
            <Field label="Reason lost">
              <div className="flex gap-2">
                <TextInput value={lostReason} onChange={e => setLostReason(e.target.value)} placeholder="e.g. went with a competitor" />
                <Btn variant="danger" onClick={() => closeDeal('lost')}>Confirm</Btn>
              </div>
            </Field>
          )}

          {moduleOptions && moduleOptions.length > 0 && (
            <Field label="Product interest">
              <div className="flex flex-wrap gap-2">
                {moduleOptions.map(m => (
                  <button key={m.key} type="button" onClick={() => toggleModule(m.key)}
                    className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                      (deal.module_keys || []).includes(m.key)
                        ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                        : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                    {m.label}
                  </button>
                ))}
              </div>
            </Field>
          )}

          <div>
            <h3 className="font-display font-bold text-[13px] mb-2">Contacts</h3>
            <div className="space-y-1.5 mb-2">
              {contacts.length === 0 && <p className="text-[12px] text-pb-faintest">No contacts linked yet.</p>}
              {contacts.map(c => (
                <div key={c.id} className="flex items-center justify-between gap-2 text-[12.5px] pb-card px-2.5 py-1.5">
                  <span className="truncate">{c.full_name}{c.email ? <span className="text-pb-faint"> · {c.email}</span> : null}</span>
                  <button onClick={() => removeContact(c.id)} className="text-pb-faint hover:text-pb-red text-[11px]">Remove</button>
                </div>
              ))}
            </div>
            <form onSubmit={addContact} className="flex gap-2">
              <TextInput placeholder="Name" value={contactName} onChange={e => setContactName(e.target.value)} className="flex-1" />
              <TextInput placeholder="Email (optional)" value={contactEmail} onChange={e => setContactEmail(e.target.value)} className="flex-1" />
              <Btn type="submit" variant="ghost" sm>Add</Btn>
            </form>
          </div>

          <div>
            <h3 className="font-display font-bold text-[13px] mb-2">Activity</h3>
            <div className="space-y-2 mb-2 max-h-48 overflow-y-auto">
              {activities.length === 0 && <p className="text-[12px] text-pb-faintest">No activity logged yet.</p>}
              {activities.map(a => (
                <div key={a.id} className="text-[12.5px] pb-card px-2.5 py-2">
                  <div className="flex items-center gap-2 mb-0.5">
                    <Pill>{a.type}</Pill>
                    <span className="text-pb-faintest text-[10.5px]">{a.occurred_at ? new Date(a.occurred_at).toLocaleString() : ''}</span>
                  </div>
                  {a.body && <p className="text-pb-text">{a.body}</p>}
                </div>
              ))}
            </div>
            <form onSubmit={addActivity} className="flex gap-2">
              <Select value={noteType} onChange={e => setNoteType(e.target.value)} className="w-28 shrink-0">
                <option value="note">Note</option>
                <option value="call">Call</option>
                <option value="email">Email</option>
                <option value="meeting">Meeting</option>
              </Select>
              <TextInput placeholder="Log an update…" value={note} onChange={e => setNote(e.target.value)} className="flex-1" />
              <Btn type="submit" variant="ghost" sm>Add</Btn>
            </form>
          </div>
        </div>
      )}
    </Modal>
  )
}
