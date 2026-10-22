// "Update details": the player corrects their own email, mobile, address and
// emergency contact in a pop-up. The form is read from their own record when it
// opens, only the fields they changed are sent (an untouched field is never
// cleared), and the save asks for their current PIN again, because a signed-in page
// is only as strong as four digits. The server decides what is valid and says so in
// the player's words; this form just shows it.
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'

const FIELDS = [
  { key: 'email', label: 'Email', type: 'email', auto: 'email', wide: true },
  { key: 'phone', label: 'Mobile', type: 'tel', auto: 'tel', wide: true },
  { key: 'address_line1', label: 'Street address', type: 'text', auto: 'address-line1', wide: true },
  { key: 'suburb', label: 'Suburb', type: 'text', auto: 'address-level2' },
  { key: 'state', label: 'State', type: 'text', auto: 'address-level1' },
  { key: 'postcode', label: 'Postcode', type: 'text', auto: 'postal-code', inputMode: 'numeric' },
  { key: 'emergency_contact_name', label: 'Emergency contact name', type: 'text', auto: 'off', wide: true },
  { key: 'emergency_contact_phone', label: 'Emergency contact mobile', type: 'tel', auto: 'off', wide: true },
]

const inputCls = 'w-full bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2.5 text-[15px] focus:outline-none focus:border-pb-accent'

export default function DetailsModal({ token, onClose, onSaved }) {
  const [initial, setInitial] = useState(null)   // what the server holds, as the form first read it
  const [form, setForm] = useState({})
  const [pin, setPin] = useState('')
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const firstRef = useRef(null)
  const dialogRef = useRef(null)

  useEffect(() => {
    let alive = true
    api.availPublicDetails(token)
      .then((d) => { if (alive) { setInitial(d.details); setForm(d.details) } })
      .catch((e) => { if (alive) setLoadError(e.message || 'Your details could not be loaded.') })
    return () => { alive = false }
  }, [token])

  // Escape closes it, the page behind stops scrolling, and focus lands in the form.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !saving) onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose, saving])
  useEffect(() => { if (initial && firstRef.current) firstRef.current.focus() }, [initial])

  const changed = initial ? FIELDS.filter((f) => (form[f.key] || '').trim() !== (initial[f.key] || '').trim()).map((f) => f.key) : []
  const phoneChanged = changed.includes('phone')
  const canSave = initial && changed.length > 0 && pin.length === 4 && !saving

  const save = async (e) => {
    e.preventDefault()
    if (!canSave) return
    setSaving(true)
    setError('')
    try {
      const body = { pin }
      for (const k of changed) body[k] = (form[k] || '').trim()
      const res = await api.availPublicUpdateDetails(token, body)
      onSaved({ changed: res.changed || changed, phoneChanged })
    } catch (err) {
      setError(err.message || 'That could not be saved. Please try again.')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4" data-details-modal>
      <button type="button" aria-label="Close" tabIndex={-1} onClick={() => !saving && onClose()}
        className="absolute inset-0 bg-black/60 cursor-default" />
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="details-title"
        className="relative w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl border pb-hairline bg-pb-surface text-pb-text shadow-2xl">
        <form onSubmit={save} noValidate className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h2 id="details-title" className="font-display font-bold text-[19px]">Update your details</h2>
            <button type="button" onClick={onClose} disabled={saving} aria-label="Close" data-details-close
              className="shrink-0 w-8 h-8 -mr-1 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2">✕</button>
          </div>
          <p className="text-[12.5px] text-pb-faint mb-4">Your club sees what you change. Leave a box alone to keep it as it is.</p>

          {loadError && <div className="rounded-lg px-3.5 py-2.5 mb-3 text-sm" data-details-load-error
            style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>{loadError}</div>}
          {!initial && !loadError && <div className="text-sm text-pb-faint py-6 text-center">Loading your details…</div>}

          {initial && (
            <>
              <div className="grid grid-cols-2 gap-x-3 gap-y-3">
                {FIELDS.map((f, i) => (
                  <label key={f.key} className={`block min-w-0 ${f.wide ? 'col-span-2' : f.key === 'postcode' ? 'col-span-1' : 'col-span-1'}`}>
                    <span className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">{f.label}</span>
                    <input
                      ref={i === 0 ? firstRef : undefined}
                      name={f.key}
                      type={f.type}
                      autoComplete={f.auto}
                      inputMode={f.inputMode}
                      value={form[f.key] || ''}
                      maxLength={f.key === 'postcode' ? 10 : 254}
                      onChange={(e) => setForm((cur) => ({ ...cur, [f.key]: e.target.value }))}
                      className={inputCls}
                    />
                  </label>
                ))}
              </div>
              {phoneChanged && (
                <p className="text-[12px] mt-3" data-details-pin-note style={{ color: 'var(--pb-amber)' }}>
                  Your PIN is the last 4 digits of your mobile. After this change, use the last 4 digits of the new number.
                </p>
              )}

              <div className="mt-4 pt-4 border-t pb-hairline">
                <label className="block">
                  <span className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Your current PIN</span>
                  <input name="pin" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                    inputMode="numeric" autoComplete="one-time-code" placeholder="••••" aria-describedby="details-pin-help"
                    className={`${inputCls} tracking-[0.5em] font-mono text-center max-w-[9rem]`} />
                </label>
                <p id="details-pin-help" className="text-[11.5px] text-pb-faintest mt-1">The last 4 digits of the mobile your club has for you now. We ask each time you save.</p>
              </div>

              {error && <div className="rounded-lg px-3.5 py-2.5 mt-3 text-sm" role="alert" data-details-error
                style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>{error}</div>}

              <div className="flex items-center justify-end gap-2 mt-5">
                <button type="button" onClick={onClose} disabled={saving} data-details-cancel
                  className="px-4 py-2.5 rounded-lg text-sm font-semibold text-pb-faint hover:text-pb-text">Cancel</button>
                <button type="submit" disabled={!canSave} data-details-save
                  className="px-5 py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  )
}
