import { useState, useEffect, useCallback } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import {
  Modal, Field, TextInput, NumberInput, Select, TextArea, Btn, Pill, money, moneyToCents, centsToMoneyInput,
  DEFAULT_CRM_TERMS, moduleLabel, sortModuleKeys, ONBOARDING_METHOD_OPTIONS, LEAD_SOURCE_OPTIONS,
} from './ui'
import { TIER_TONE } from './PipelineBoard'

// Deal detail/edit — used by BOTH the club CRM module and the platform-scope
// Super Admin sales pipeline. `client` bundles the scope-specific api.js calls
// (club vs platform) so this component itself is scope-agnostic. `terms`
// swaps the Won/Lost/"deal" sales language for the club-facing module's own
// vocabulary (see ui.jsx's DEFAULT_CRM_TERMS). `ownerOptions` (platform scope
// only — an internal staff pool, not a club's own users) shows/hides the
// Owner picker; engagement score is read-only either way (mirrored from
// marketing_clubs, computed elsewhere).
export default function DealDetailModal({ dealId, open, onClose, stages, client, onChanged, moduleOptions, ownerOptions, terms }) {
  const toast = useToast()
  const t = { ...DEFAULT_CRM_TERMS, ...terms }
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
  const [contactPhone, setContactPhone] = useState('')
  const [editPhoneId, setEditPhoneId] = useState(null)
  const [showPurgeBox, setShowPurgeBox] = useState(false)
  const [resetClub, setResetClub] = useState(false)
  const [discountAmount, setDiscountAmount] = useState('')
  const [discountPercent, setDiscountPercent] = useState('')
  const [discountReason, setDiscountReason] = useState('')
  const [showDiscount, setShowDiscount] = useState(false)

  const load = useCallback(() => {
    if (!dealId) return
    setLoading(true)
    Promise.all([client.getDeal(dealId), client.listActivities(dealId), client.listContacts(dealId)])
      .then(([d, a, c]) => { setDeal(d); setActivities(a.activities || []); setContacts(c.contacts || []) })
      .catch(e => toast.error(e.message || `Could not load ${t.itemSingular}`))
      .finally(() => setLoading(false))
  }, [dealId, client, toast])

  useEffect(() => { if (open) load() }, [open, load])
  useEffect(() => {
    if (!deal) return
    setDiscountAmount(deal.discount_amount_cents != null ? centsToMoneyInput(deal.discount_amount_cents) : '')
    setDiscountPercent(deal.discount_percent ?? '')
    setDiscountReason(deal.discount_reason || '')
    setShowDiscount(!!(deal.discount_amount_cents || deal.discount_percent))
  }, [deal])

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
    } catch (e) { toast.error(e.message || `Could not close ${t.itemSingular}`) } finally { setSaving(false) }
  }

  const archive = async () => {
    if (!window.confirm(`Archive this ${t.itemSingular}? It will drop off the board.`)) return
    try {
      await client.archiveDeal(dealId)
      onChanged?.()
      onClose()
    } catch (e) { toast.error(e.message || 'Could not archive') }
  }

  const deletePermanently = async () => {
    try {
      await client.deletePermanent(dealId, resetClub)
      onChanged?.()
      onClose()
    } catch (e) { toast.error(e.message || `Could not delete this ${t.itemSingular}`) }
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
      await client.linkContact(dealId, {
        full_name: contactName.trim(), email: contactEmail.trim() || undefined,
        phone: contactPhone.trim() || undefined,
      })
      setContactName(''); setContactEmail(''); setContactPhone('')
      await refresh()
    } catch (e2) { toast.error(e2.message || 'Could not add contact') }
  }

  const removeContact = async (personId) => {
    try { await client.unlinkContact(dealId, personId); await refresh() }
    catch (e) { toast.error(e.message || 'Could not remove contact') }
  }

  const savePhone = async (personId, phone) => {
    if (!client.updatePerson) { setEditPhoneId(null); return }
    try { await client.updatePerson(personId, { phone: phone.trim() || null }); setEditPhoneId(null); await refresh() }
    catch (e) { toast.error(e.message || 'Could not save mobile number') }
  }

  const saveDiscount = async () => {
    const amountCents = discountAmount !== '' ? moneyToCents(discountAmount) : null
    const percent = discountPercent !== '' ? Number(discountPercent) : null
    if ((amountCents || percent) && !discountReason.trim()) {
      toast.error('A discount needs a reason'); return
    }
    await patch({
      discount_amount_cents: amountCents,
      discount_percent: amountCents ? null : percent,
      discount_reason: (amountCents || percent) ? discountReason.trim() : null,
    })
  }

  const clearDiscount = async () => {
    setDiscountAmount(''); setDiscountPercent(''); setDiscountReason(''); setShowDiscount(false)
    await patch({ discount_amount_cents: null, discount_percent: null, discount_reason: null })
  }

  const makePointOfContact = async (personId) => {
    try { await client.setPointOfContact(dealId, { person_id: personId }); await refresh() }
    catch (e) { toast.error(e.message || 'Could not set point of contact') }
  }

  const toggleModule = (key) => {
    const cur = deal?.module_keys || []
    const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
    patch({ module_keys: next })
  }

  const titleNode = deal ? (
    <span className="flex items-center gap-2">
      <span className="truncate">{deal.title}</span>
      {deal.is_customer && (
        <span title="Already a BetterCricket subscriber"
          className="text-[9px] font-mono uppercase tracking-wide px-1 py-px rounded bg-emerald-500/12 text-emerald-300 shrink-0">
          customer
        </span>
      )}
      {deal.engagement_score != null && (
        <span title={`Engagement — ${(deal.engagement_tier || '').replace(/_/g, ' ')}`}>
          <Pill tone={TIER_TONE[deal.engagement_tier] || 'faint'}>{deal.engagement_score}</Pill>
        </span>
      )}
    </span>
  ) : (t.itemSingular[0].toUpperCase() + t.itemSingular.slice(1))

  return (
    <Modal open={open} onClose={onClose} wide title={titleNode}
      footer={deal ? (
        <>
          <Btn variant="ghost" onClick={() => setShowPurgeBox(v => !v)}>Delete permanently…</Btn>
          {deal.status === 'open' ? (
            <>
              <Btn variant="danger" onClick={archive}>Archive</Btn>
              <Btn variant="danger" onClick={() => closeDeal('lost')}>Mark {t.lost}</Btn>
              <Btn variant="primary" onClick={() => closeDeal('won')}>Mark {t.won}</Btn>
            </>
          ) : (
            <Btn variant="ghost" onClick={archive}>Archive</Btn>
          )}
        </>
      ) : null}>
      {loading || !deal ? <p className="text-pb-faint text-sm">Loading…</p> : (
        <div className="space-y-5">
          {deal.status !== 'open' && (
            <Pill tone={deal.status === 'won' ? 'green' : 'red'}>{(deal.status === 'won' ? t.won : t.lost).toUpperCase()}</Pill>
          )}

          {showPurgeBox && (
            <div className="pb-card px-3 py-3 border-pb-red/40 space-y-2">
              <p className="text-[12.5px] text-pb-text">
                Permanently deletes this {t.itemSingular} — its notes, activity and contact links
                go with it. This can't be undone. Archive instead if you might want it back.
              </p>
              {deal.marketing_club_id && (
                <label className="flex items-start gap-2 text-[12px] text-pb-faint">
                  <input type="checkbox" checked={resetClub} onChange={e => setResetClub(e.target.checked)} className="mt-0.5" />
                  <span>Also reset this club's engagement score and trial/demo flags — use this only
                    if this was test activity, so a real future enquiry starts fresh.</span>
                </label>
              )}
              <div className="flex justify-end gap-2">
                <Btn variant="ghost" sm onClick={() => setShowPurgeBox(false)}>Cancel</Btn>
                <Btn variant="danger" sm onClick={deletePermanently}>Confirm delete</Btn>
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            <Field label={t.titleLabel} half>
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
            {ownerOptions && ownerOptions.length > 0 && (
              <Field label="Owner" half>
                <Select value={deal.owner_user_id || ''} onChange={e => patch({ owner_user_id: e.target.value || null })}>
                  <option value="">Unassigned</option>
                  {ownerOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              </Field>
            )}
            <Field label="Onboarding method" half>
              <Select value={deal.onboarding_method || ''} onChange={e => patch({ onboarding_method: e.target.value || null })}>
                {ONBOARDING_METHOD_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <Field label="Lead source" half>
              <Select value={deal.lead_source || ''} onChange={e => patch({ lead_source: e.target.value || null })}>
                {LEAD_SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
          </div>

          {showLostBox && (
            <Field label={`Reason ${t.lost.toLowerCase()}`}>
              <div className="flex gap-2">
                <TextInput value={lostReason} onChange={e => setLostReason(e.target.value)} placeholder="e.g. went with a competitor" />
                <Btn variant="danger" onClick={() => closeDeal('lost')}>Confirm</Btn>
              </div>
            </Field>
          )}

          {moduleOptions && moduleOptions.length > 0 && (() => {
            // Sentence-Case, fixed order (Stats first, Fantasy last) regardless
            // of what order module_keys stores them in — a club with no
            // Product Interest set at all is always assumed to want at least
            // Stats. Each chip for a module currently on trial shows its days
            // remaining, bolding whichever module is soonest to expire.
            const heldKeys = (deal.module_keys || []).length ? deal.module_keys : ['core']
            const trialDays = deal.trial_days_remaining || {}
            const minDays = Object.keys(trialDays).length ? Math.min(...Object.values(trialDays)) : null
            return (
              <Field label="Product interest">
                <div className="flex flex-wrap gap-2">
                  {moduleOptions.map(m => {
                    const on = heldKeys.includes(m.key)
                    const days = trialDays[m.key]
                    return (
                      <button key={m.key} type="button" onClick={() => toggleModule(m.key)}
                        className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                          on ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent'
                             : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                        {moduleLabel(m.key)}
                        {days != null && (
                          <span className={days === minDays ? 'font-bold ml-1' : 'ml-1 opacity-80'}>({days})</span>
                        )}
                      </button>
                    )
                  })}
                </div>
                {Object.keys(trialDays).length > 0 && (
                  <p className="text-[10.5px] text-pb-faintest mt-1">Days remaining on trial, in brackets.</p>
                )}
              </Field>
            )
          })()}

          <Field label="Discretionary discount">
            {!showDiscount ? (
              <Btn variant="ghost" sm onClick={() => setShowDiscount(true)}>+ Add a discount</Btn>
            ) : (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2 items-end">
                  <div className="w-32">
                    <span className="block text-[10.5px] text-pb-faint mb-1">Amount ($)</span>
                    <NumberInput min={0} value={discountAmount}
                      onChange={e => { setDiscountAmount(e.target.value); if (e.target.value) setDiscountPercent('') }} />
                  </div>
                  <span className="text-[11px] text-pb-faintest pb-2">or</span>
                  <div className="w-28">
                    <span className="block text-[10.5px] text-pb-faint mb-1">Percent (%)</span>
                    <NumberInput min={0} max={100} value={discountPercent}
                      onChange={e => { setDiscountPercent(e.target.value); if (e.target.value) setDiscountAmount('') }} />
                  </div>
                  <div className="flex-1 min-w-[180px]">
                    <span className="block text-[10.5px] text-pb-faint mb-1">Reason (required)</span>
                    <TextInput value={discountReason} onChange={e => setDiscountReason(e.target.value)}
                      placeholder="e.g. loyalty renewal incentive" />
                  </div>
                  <Btn variant="primary" sm onClick={saveDiscount} disabled={saving}>Save</Btn>
                  {(deal.discount_amount_cents || deal.discount_percent) && (
                    <Btn variant="ghost" sm onClick={clearDiscount}>Remove</Btn>
                  )}
                </div>
                <p className="text-[11px] text-pb-faint">
                  {money(deal.value_cents)} base → <span className="text-pb-text font-medium">{money(deal.effective_value_cents ?? deal.value_cents)}</span> after discount
                </p>
              </div>
            )}
          </Field>

          <div>
            <h3 className="font-display font-bold text-[13px] mb-2">Contacts</h3>
            {(() => {
              const poc = contacts.find(c => c.role_on_deal === 'point_of_contact')
              const others = contacts.filter(c => c.role_on_deal !== 'point_of_contact')
              const phoneField = (c) => editPhoneId === c.id ? (
                <TextInput autoFocus defaultValue={c.phone || ''} placeholder="Mobile" className="w-32 shrink-0"
                  onBlur={e => savePhone(c.id, e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') setEditPhoneId(null) }} />
              ) : (
                <button onClick={() => setEditPhoneId(c.id)}
                  className="text-pb-faint hover:text-pb-accent text-[11px] shrink-0">
                  {c.phone || '+ mobile'}
                </button>
              )
              const ContactRow = ({ c, isPoc }) => (
                <div className={`flex items-center justify-between gap-2 text-[12.5px] pb-card px-2.5 py-1.5 ${isPoc ? 'border-pb-accent/40' : ''}`}>
                  <span className="truncate">
                    {isPoc && <span className="font-mono text-[9.5px] tracking-wide text-pb-accent uppercase mr-1.5">POC</span>}
                    {c.full_name}{c.email ? <span className="text-pb-faint"> · {c.email}</span> : null}
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    {phoneField(c)}
                    {!isPoc && <button onClick={() => makePointOfContact(c.id)} className="text-pb-faint hover:text-pb-accent text-[11px]">Make POC</button>}
                    <button onClick={() => removeContact(c.id)} className="text-pb-faint hover:text-pb-red text-[11px]">Remove</button>
                  </span>
                </div>
              )
              return (
                <div className="space-y-1.5 mb-2">
                  {poc ? <ContactRow c={poc} isPoc /> : contacts.length > 0 && (
                    <p className="text-[11px] text-pb-faintest">No point of contact set — pick one below.</p>
                  )}
                  {contacts.length === 0 && <p className="text-[12px] text-pb-faintest">No contacts linked yet.</p>}
                  {others.map(c => <ContactRow key={c.id} c={c} />)}
                </div>
              )
            })()}
            <form onSubmit={addContact} className="flex gap-2">
              <TextInput placeholder="Name" value={contactName} onChange={e => setContactName(e.target.value)} className="flex-1" />
              <TextInput placeholder="Email (optional)" value={contactEmail} onChange={e => setContactEmail(e.target.value)} className="flex-1" />
              <TextInput placeholder="Mobile (optional)" value={contactPhone} onChange={e => setContactPhone(e.target.value)} className="w-32 shrink-0" />
              <Btn type="submit" variant="ghost" sm>Add</Btn>
            </form>
          </div>

          <div>
            <h3 className="font-display font-bold text-[13px] mb-2">Notes &amp; activity</h3>
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
            <form onSubmit={addActivity} className="space-y-2">
              <TextArea placeholder="Log an update…" value={note} onChange={e => setNote(e.target.value)}
                style={{ minHeight: '110px' }} />
              <div className="flex items-center justify-between gap-2">
                {/* Sized to fit the widest option ("Meeting"), not a fixed
                    Tailwind width — the inline style wins over the shared
                    Select's w-full so the box hugs its content. */}
                <Select value={noteType} onChange={e => setNoteType(e.target.value)} style={{ width: 'auto' }}>
                  <option value="note">Note</option>
                  <option value="call">Call</option>
                  <option value="email">Email</option>
                  <option value="meeting">Meeting</option>
                </Select>
                <Btn type="submit" variant="ghost" sm>Add</Btn>
              </div>
            </form>
          </div>
        </div>
      )}
    </Modal>
  )
}
