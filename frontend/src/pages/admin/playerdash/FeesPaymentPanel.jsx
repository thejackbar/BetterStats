// BetterStats > Player Dashboard > How players pay fees: what a player sees under "How to pay"
// in the Fees section of their dashboard. Bank details they can copy, a pay-online button (TeamApp,
// PlayHQ, a Square link, your own shop) and anything else, such as cash at the bar. The whole set
// is saved together; clearing a box clears that line.
import { useEffect, useState } from 'react'
import { Btn } from '../betterselect/ui'

const FIELDS = [
  { key: 'account_name', label: 'Account name', placeholder: 'Yourtown Cricket Club' },
  { key: 'bsb', label: 'BSB', placeholder: '062-000' },
  { key: 'account_number', label: 'Account number', placeholder: '1234 5678' },
  { key: 'payid', label: 'PayID', placeholder: 'treasurer@yourclub.com.au' },
  { key: 'payid_name', label: 'Name the PayID shows', placeholder: 'Yourtown CC' },
  { key: 'reference_hint', label: 'Reference to use', placeholder: 'Your surname and "fees"' },
  { key: 'pay_online_url', label: 'Pay online link', placeholder: 'https://', hint: 'TeamApp, PlayHQ, a Square or Stripe link, or your club shop.' },
  { key: 'pay_online_label', label: 'Pay online button text', placeholder: 'Pay online' },
]

const inputCls = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest focus:outline-none focus:border-pb-accent'

export default function FeesPaymentPanel({ value, feesModule, busy, onSave }) {
  const [f, setF] = useState(value || {})
  useEffect(() => { setF(value || {}) }, [value])
  const set = (k) => (e) => setF((c) => ({ ...c, [k]: e.target.value }))
  const dirty = JSON.stringify(Object.fromEntries(Object.entries(f).filter(([, v]) => v))) !== JSON.stringify(value || {})
  const fieldBlocked = feesModule && (!feesModule.enabled || feesModule.blocked)
  return (
    <form data-fees-payment className="pt-4 border-t pb-hairline" onSubmit={(e) => { e.preventDefault(); onSave(f) }}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">How players pay fees</div>
      <p className="text-[12px] text-pb-faintest mb-2">
        Shown under How to pay in the Fees section of a player's dashboard while they owe money. Fill in whichever ways your club takes payment and leave the rest blank.
      </p>
      {fieldBlocked && (
        <p className="text-[12px] mb-2" style={{ color: 'var(--pb-amber)' }} data-fees-payment-note>
          {feesModule.enabled ? `Players do not see Fees yet. ${feesModule.blocked}` : 'Players do not see Fees yet. Tick Fees owing under Player dashboard below.'}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((x) => (
          <div key={x.key} className="flex flex-col gap-1 min-w-0">
            <label htmlFor={`fees-pay-${x.key}`} className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{x.label}</label>
            <input id={`fees-pay-${x.key}`} data-pay-field={x.key} className={inputCls} value={f[x.key] || ''} onChange={set(x.key)}
              placeholder={x.placeholder} maxLength={x.key === 'pay_online_url' ? 2000 : 120} />
            {x.hint && <span className="text-[11px] text-pb-faintest">{x.hint}</span>}
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1 mt-3">
        <label htmlFor="fees-pay-other" className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Other ways to pay</label>
        <textarea id="fees-pay-other" data-pay-field="other_instructions" className={`${inputCls} min-h-[70px]`} maxLength={1000}
          value={f.other_instructions || ''} onChange={set('other_instructions')}
          placeholder="Cash or card at the bar on Saturdays. Payment plans: talk to the treasurer." />
      </div>
      <div className="mt-3"><Btn sm variant="primary" type="submit" disabled={busy || !dirty} data-save-fees-payment>Save payment details</Btn></div>
    </form>
  )
}
