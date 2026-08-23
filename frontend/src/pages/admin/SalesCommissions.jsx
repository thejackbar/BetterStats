import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { Pill, money, moneyToCents, moduleLabel } from '../../components/admin/crm/ui'

const CARD = 'pb-card p-3'
const TH = 'text-right py-1.5 px-2 whitespace-nowrap'
const TD = 'text-right py-1.5 px-2 whitespace-nowrap'
const INPUT = 'bg-pb-surface border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text'

const pct = (v) => `${Number(v || 0).toFixed(Number(v) % 1 ? 2 : 0)}%`

// Commission due is allowed to be negative — an overpayment is a real state
// and rounding it away to zero would lose it — so it is the one figure drawn
// in a colour rather than plain. The shared `money` helper puts the minus
// AFTER the dollar sign ("$-40"), which reads as a typo; a negative is signed
// out front here, where a reader is looking for it.
function Due({ cents }) {
  if (!cents) return <span className="text-pb-faintest">$0</span>
  const tone = cents > 0 ? 'text-pb-text font-medium' : 'text-pb-positive-ink'
  return <span className={tone}>{cents < 0 ? `-${money(-cents)}` : money(cents)}</span>
}

function Kpi({ label, value, hint }) {
  return (
    <div className={CARD}>
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
      <div className="font-display font-bold text-xl text-pb-text">{value}</div>
      {hint && <div className="text-[11px] text-pb-faintest mt-0.5">{hint}</div>}
    </div>
  )
}

// A zero has nothing behind it, so it stays plain text rather than a button
// that opens an empty list — the same rule Sales Performance's figures follow.
function Figure({ cents, onOpen, active, title }) {
  if (!cents) return <span className="text-pb-faintest">$0</span>
  return (
    <button
      type="button" onClick={onOpen} title={title}
      className={`cursor-pointer underline decoration-dotted decoration-pb-faint underline-offset-2
        hover:decoration-solid hover:text-pb-accent-ink rounded-sm
        ${active ? 'text-pb-accent-ink decoration-solid' : 'text-pb-text'}`}
    >
      {money(cents)}
    </button>
  )
}

function ForecastTable({ rows, totals, onOpen, activeKey }) {
  if (!rows.length) {
    return <p className="text-[12px] text-pb-faintest">No sales reps yet.</p>
  }
  const line = (r, key) => (
    <>
      <td className="py-1.5 pr-2 text-pb-text font-medium">
        {r.rep_name}
        {r.unattributed && <span className="text-pb-faintest font-normal ml-1">(pool)</span>}
      </td>
      <td className={TD}>{r.clubs_attributed || <span className="text-pb-faintest">0</span>}</td>
      <td className={TD}>
        <Figure cents={r.pipeline_value_cents} active={activeKey === `${key}|open`}
                title="Their open deals. Click for the clubs behind it"
                onOpen={() => onOpen(r, 'open')} />
      </td>
      <td className={TD}>{money(r.forecast_commission_cents)}</td>
      <td className={TD}>{money(r.weighted_pipeline_value_cents)}</td>
      <td className={`${TD} font-medium`}>{money(r.weighted_forecast_commission_cents)}</td>
    </>
  )
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Salesperson</th>
            <th className={TH} title="Distinct clubs they earned, won or open">Clubs</th>
            <th className={TH}>Pipeline value</th>
            <th className={TH}>Pipeline commission</th>
            <th className={TH} title="Value × the deal's own likelihood">Weighted pipeline</th>
            <th className={TH}>Weighted commission</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.rep_user_id} className="border-b border-pb-hairline/50">{line(r, r.rep_user_id)}</tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              <td className="py-1.5 pr-2">Everyone</td>
              <td className={TD}>{totals.clubs_attributed}</td>
              <td className={TD}>{money(totals.pipeline_value_cents)}</td>
              <td className={TD}>{money(totals.forecast_commission_cents)}</td>
              <td className={TD}>{money(totals.weighted_pipeline_value_cents)}</td>
              <td className={TD}>{money(totals.weighted_forecast_commission_cents)}</td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

function EarnedTable({ rows, totals, onOpen, activeKey }) {
  if (!rows.length) return <p className="text-[12px] text-pb-faintest">Nothing won yet.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Salesperson</th>
            <th className={TH} title="Confirmed Stripe payments that were new business">Payments</th>
            <th className={TH} title="What those clubs paid, net of GST">Paid by clubs</th>
            <th className={TH}>Commission earned</th>
            <th className={TH}>Paid</th>
            <th className={TH}>Due</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.rep_user_id} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2 text-pb-text font-medium">
                {r.rep_name}
                {r.unattributed && <span className="text-pb-faintest font-normal ml-1">(pool)</span>}
              </td>
              <td className={TD}>{r.paid_invoices || <span className="text-pb-faintest">0</span>}</td>
              <td className={TD}>
                <Figure cents={r.won_value_cents} active={activeKey === `${r.rep_user_id}|won`}
                        title="What their clubs have actually paid. Click for the payments"
                        onOpen={() => onOpen(r, 'won')} />
              </td>
              <td className={TD}>{money(r.commission_earned_cents)}</td>
              <td className={TD}>{money(r.commission_paid_cents)}</td>
              <td className={TD}><Due cents={r.commission_due_cents} /></td>
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              <td className="py-1.5 pr-2">Everyone</td>
              <td className={TD}>{totals.paid_invoices}</td>
              <td className={TD}>{money(totals.won_value_cents)}</td>
              <td className={TD}>{money(totals.commission_earned_cents)}</td>
              <td className={TD}>{money(totals.commission_paid_cents)}</td>
              <td className={TD}><Due cents={totals.commission_due_cents} /></td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

// What is behind whichever figure was clicked, drawn under the table it came
// from rather than in a dialog, so the row stays on screen and a run of reps
// can be compared without reopening anything.
//
// The two figures are different kinds of thing, so the table is too. A
// FORECAST is CRM deals — each with a likelihood, hence both a flat pipeline
// commission and a weighted one. What has been EARNED is confirmed Stripe
// PAYMENTS: money that actually arrived, with the rate stamped on it the day
// it landed. There is nothing to weight about a payment already banked.
const KIND_LABEL = { initial: 'First payment', expansion: 'Added modules' }

function PaymentsTable({ payments }) {
  const sum = (key) => payments.reduce((t, p) => t + (p[key] || 0), 0)
  return (
    <div className="max-h-80 overflow-y-auto overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Club</th>
            <th className="text-left py-1.5 pr-2">What was bought</th>
            <th className={TH}>Paid on</th>
            <th className={TH} title="Net of GST">Amount</th>
            <th className={TH}>Rate</th>
            <th className={TH}>Commission earned</th>
          </tr>
        </thead>
        <tbody>
          {payments.map(p => (
            <tr key={p.invoice_id} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2 text-pb-text">{p.club_name}</td>
              <td className="py-1.5 pr-2 text-pb-faint">
                <span className="text-pb-faintest">{KIND_LABEL[p.kind] || p.kind}</span>
                {p.line_items?.length ? ` · ${p.line_items.map(l => l.name).filter(Boolean).join(', ')}` : ''}
              </td>
              <td className={`${TD} font-mono text-[11px] text-pb-faint`}>{p.paid_on || '—'}</td>
              <td className={TD}>{money(p.amount_cents)}</td>
              <td className={`${TD} text-pb-faint`}>{pct(p.rate_percent)}</td>
              <td className={`${TD} font-medium`}>{money(p.commission_cents)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-pb-hairline text-pb-text font-medium">
            <td className="py-1.5 pr-2" colSpan={3}>Total</td>
            <td className={TD}>{money(sum('amount_cents'))}</td>
            <td className={TD} />
            <td className={TD}>{money(sum('commission_cents'))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function DealsTable({ deals }) {
  const sum = (key) => deals.reduce((t, d) => t + (d[key] || 0), 0)
  return (
    <div className="max-h-80 overflow-y-auto overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Club</th>
            <th className="text-left py-1.5 pr-2">Interested in</th>
            <th className={TH}>Stage</th>
            <th className={TH}>Value</th>
            <th className={TH}>Rate</th>
            <th className={TH}>Pipeline commission</th>
            <th className={TH}>Weighted commission</th>
          </tr>
        </thead>
        <tbody>
          {deals.map(d => (
            <tr key={d.deal_id} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2">
                <Link
                  to={`/admin/super/crm/workspace?club=${d.deal_id}`}
                  title="Open this club in the Sales Workspace"
                  className="text-pb-text underline decoration-dotted decoration-pb-faint
                             underline-offset-2 hover:decoration-solid hover:text-pb-accent-ink"
                >
                  {d.club_name}
                </Link>
                {d.state && <span className="font-mono text-[10px] text-pb-faintest ml-1">{d.state}</span>}
              </td>
              <td className="py-1.5 pr-2 text-pb-faint">
                {d.module_keys.length ? d.module_keys.map(moduleLabel).join(', ') : '—'}
              </td>
              <td className={`${TD} text-pb-faint`}>
                {d.stage_name || '—'}
                {d.probability ? <span className="text-pb-faintest"> · {d.probability}%</span> : null}
              </td>
              <td className={TD}>{money(d.value_cents)}</td>
              <td className={`${TD} text-pb-faint`}>{pct(d.rate_percent)}</td>
              <td className={TD}>{money(d.commission_cents)}</td>
              <td className={`${TD} font-medium`}>{money(d.weighted_commission_cents)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-pb-hairline text-pb-text font-medium">
            <td className="py-1.5 pr-2" colSpan={3}>Total</td>
            <td className={TD}>{money(sum('value_cents'))}</td>
            <td className={TD} />
            <td className={TD}>{money(sum('commission_cents'))}</td>
            <td className={TD}>{money(sum('weighted_commission_cents'))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function Drilldown({ open, onClose }) {
  if (!open) return null
  const { title, loading, error, data, status } = open
  const isOpen = status === 'open'
  const items = (isOpen ? data?.deals : data?.payments) || []
  const noun = isOpen ? 'deal' : 'payment'
  // Every rate in the list is the same rep's, so all-zero means the rep has no
  // rate — which is why the money columns read $0, and worth saying rather
  // than leaving someone to work out.
  const noRate = items.length > 0 && items.every(i => !i.rate_percent)

  return (
    <div className="mt-3 border-t border-pb-hairline pt-3">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h4 className="font-display font-bold text-[12px] text-pb-text">{title}</h4>
          {data && (
            <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
              {data.count} {noun}{data.count === 1 ? '' : 's'}
            </p>
          )}
        </div>
        <button type="button" onClick={onClose}
          className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-2 py-1 shrink-0">
          CLOSE
        </button>
      </div>
      {loading && <p className="text-[12px] text-pb-faintest">Loading…</p>}
      {error && <p className="text-[12px] text-pb-red-ink">{error}</p>}
      {noRate && (
        <p className="text-[11px] text-pb-text mb-2">
          No commission rate is set for this salesperson, so every commission figure here is
          $0. Set one under Commission rates below.
        </p>
      )}
      {data && items.length === 0 && (
        <p className="text-[12px] text-pb-faintest">
          {isOpen ? 'No deals behind this figure.'
            : 'No payments behind this figure yet. Commission is earned when Stripe confirms one.'}
        </p>
      )}
      {items.length > 0 && (isOpen ? <DealsTable deals={items} /> : <PaymentsTable payments={items} />)}
    </div>
  )
}

function RatesPanel({ reps, defaultRate, onSave, onClear, busy }) {
  const [draft, setDraft] = useState({})
  const value = (key, fallback) => (draft[key] !== undefined ? draft[key] : String(fallback ?? ''))
  const row = (key, label, current, hasOwn) => (
    <div key={key} className="flex items-center gap-2 py-1.5 border-b border-pb-hairline/50 last:border-0">
      <span className="text-[12px] text-pb-text flex-1 truncate">{label}</span>
      {!hasOwn && key !== 'default' && <Pill tone="faint">default</Pill>}
      {/* A rep sitting on 0% earns nothing on anything, which is a real
          setting and not obviously a deliberate one — the commission columns
          all read $0 and nothing else on the screen says why. */}
      {key !== 'default' && !Number(value(key, current)) && (
        <Pill tone="amber">earns nothing</Pill>
      )}
      <input
        type="number" step="0.01" min="0" max="100" className={`${INPUT} w-20 text-right`}
        value={value(key, current)}
        onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
      />
      <span className="text-[12px] text-pb-faint">%</span>
      <button
        type="button" disabled={busy}
        onClick={() => onSave(key === 'default' ? null : key, value(key, current))
          .then(() => setDraft(d => { const n = { ...d }; delete n[key]; return n }))}
        className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2 py-1
                   text-pb-faint hover:text-pb-text disabled:opacity-50"
      >SAVE</button>
      {key !== 'default' && hasOwn && (
        <button
          type="button" disabled={busy} onClick={() => onClear(key)}
          className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2 py-1
                     text-pb-faint hover:text-pb-red-ink disabled:opacity-50"
          title="Drop this rep's own rate so they fall back to the default"
        >RESET</button>
      )}
    </div>
  )
  return (
    <div className={CARD}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-display font-bold text-[13px]">Commission rates</h3>
        <Pill tone="faint">percent of deal value</Pill>
      </div>
      {row('default', 'Everyone (default)', defaultRate, true)}
      {reps.map(r => row(r.id, r.name, r.rate_percent, r.has_own_rate))}
      <p className="text-[11px] text-pb-faintest mt-2">
        A rep with no rate of their own is paid at the default. Changing a rate moves every
        forecast, and never rewrites commission already earned. Each payment keeps the rate
        that applied on the day it landed.
      </p>
    </div>
  )
}

function PaymentsPanel({ reps, payments, onAdd, onDelete, busy }) {
  const [rep, setRep] = useState('')
  const [amount, setAmount] = useState('')
  const [paidOn, setPaidOn] = useState(() => new Date().toISOString().slice(0, 10))
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')

  const submit = (e) => {
    e.preventDefault()
    if (!rep || !Number(amount)) return
    onAdd({
      rep_user_id: rep, amount_cents: moneyToCents(amount), paid_on: paidOn,
      reference: reference || null, note: note || null,
    }).then(() => { setAmount(''); setReference(''); setNote('') })
  }

  return (
    <div className={CARD}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-display font-bold text-[13px]">Commission paid</h3>
        <Pill tone="faint">reduces what is due</Pill>
      </div>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 mb-3">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Rep</span>
          <select className={INPUT} value={rep} onChange={e => setRep(e.target.value)}>
            <option value="">Choose…</option>
            {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Amount ($)</span>
          <input className={`${INPUT} w-28`} type="number" step="0.01" value={amount}
                 onChange={e => setAmount(e.target.value)} placeholder="0.00" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Paid on</span>
          <input className={INPUT} type="date" value={paidOn} onChange={e => setPaidOn(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Reference</span>
          <input className={`${INPUT} w-32`} value={reference} onChange={e => setReference(e.target.value)}
                 placeholder="optional" />
        </label>
        <label className="flex flex-col gap-1 flex-1 min-w-[8rem]">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Note</span>
          <input className={`${INPUT} w-full`} value={note} onChange={e => setNote(e.target.value)}
                 placeholder="optional" />
        </label>
        <button type="submit" disabled={busy || !rep || !Number(amount)}
          className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5
                     text-pb-text hover:text-pb-accent-ink disabled:opacity-40">
          RECORD
        </button>
      </form>
      {payments.length === 0 ? (
        <p className="text-[12px] text-pb-faintest">Nothing paid out yet.</p>
      ) : (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-pb-faint border-b border-pb-hairline">
                <th className="text-left py-1.5 pr-2">Paid on</th>
                <th className="text-left py-1.5 pr-2">Rep</th>
                <th className={TH}>Amount</th>
                <th className="text-left py-1.5 px-2">Reference</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payments.map(p => (
                <tr key={p.id} className="border-b border-pb-hairline/50">
                  <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-faint">{p.paid_on}</td>
                  <td className="py-1.5 pr-2 text-pb-text">{p.rep_name}</td>
                  <td className={TD}>{money(p.amount_cents)}</td>
                  <td className="py-1.5 px-2 text-pb-faint truncate max-w-[12rem]"
                      title={[p.reference, p.note].filter(Boolean).join(' — ')}>
                    {p.reference || p.note || '—'}
                  </td>
                  <td className="py-1.5 text-right">
                    <button type="button" disabled={busy} onClick={() => onDelete(p)}
                      className="font-mono text-[10px] text-pb-faintest hover:text-pb-red-ink disabled:opacity-40">
                      DELETE
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-pb-faintest mt-2">
        A payout entered wrongly is best corrected with an offsetting negative amount, which
        leaves both entries in the ledger. Delete is for one that never happened.
      </p>
    </div>
  )
}

function PeriodsPanel({ periodType, onType, data, loading }) {
  const periods = data?.periods || []
  const anything = periods.some(p => p.totals.earned_cents || p.totals.paid_cents)
  return (
    <div className={CARD}>
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <h3 className="font-display font-bold text-[13px]">Earned and paid by period</h3>
        <div className="flex gap-1">
          {[['quarter', 'Quarter'], ['fiscal_year', 'Financial year']].map(([k, label]) => (
            <button
              key={k} type="button" onClick={() => onType(k)}
              className={`font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2 py-1
                ${periodType === k ? 'text-pb-accent-ink border-pb-accent/50' : 'text-pb-faint hover:text-pb-text'}`}
            >{label.toUpperCase()}</button>
          ))}
        </div>
      </div>
      {loading && <p className="text-[12px] text-pb-faintest">Loading…</p>}
      {!loading && !anything && (
        <p className="text-[12px] text-pb-faintest">
          Nothing earned or paid in {periodType === 'quarter' ? 'these quarters' : 'these years'} yet.
        </p>
      )}
      {!loading && anything && (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-pb-faint border-b border-pb-hairline">
                <th className="text-left py-1.5 pr-2">Period</th>
                <th className="text-left py-1.5 pr-2">Salesperson</th>
                <th className={TH}>Earned</th>
                <th className={TH}>Paid</th>
              </tr>
            </thead>
            <tbody>
              {periods.map(p => (
                p.rows.length === 0 ? (
                  <tr key={p.key} className="border-b border-pb-hairline/50">
                    <td className="py-1.5 pr-2 text-pb-text font-medium">{p.label}</td>
                    <td className="py-1.5 pr-2 text-pb-faintest" colSpan={3}>Nothing</td>
                  </tr>
                ) : p.rows.map((r, i) => (
                  <tr key={`${p.key}-${r.rep_user_id}`} className="border-b border-pb-hairline/50">
                    <td className="py-1.5 pr-2 text-pb-text font-medium">{i === 0 ? p.label : ''}</td>
                    <td className="py-1.5 pr-2 text-pb-text">{r.rep_name}</td>
                    <td className={TD}>{money(r.earned_cents)}</td>
                    <td className={TD}>{money(r.paid_cents)}</td>
                  </tr>
                ))
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-pb-faintest mt-2">
        Commission is earned in the period the club's payment landed and paid in the period the
        payout was made, so the two legitimately land in different columns, a quarter's work is
        routinely paid in the next one.
      </p>
    </div>
  )
}

export default function SalesCommissions() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [drill, setDrill] = useState(null)
  const [periodType, setPeriodType] = useState('quarter')
  const [periods, setPeriods] = useState(null)
  const [periodsLoading, setPeriodsLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    return api.salesCommissions().then(setData)
      .catch(() => toast?.error('Could not load commissions'))
      .finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    setPeriodsLoading(true)
    api.salesCommissionPeriods(periodType).then(setPeriods)
      .catch(() => toast?.error('Could not load the period summary'))
      .finally(() => setPeriodsLoading(false))
  }, [periodType, toast])

  const openDeals = useCallback((row, status) => {
    const key = `${row.rep_user_id}|${status}`
    const what = status === 'open' ? 'forecast pipeline' : 'payments received'
    setDrill({ key, status, title: `${row.rep_name}. ${what}`, loading: true })
    api.salesCommissionDeals(row.rep_user_id, status)
      .then(res => setDrill(d => (d && d.key === key ? { ...d, loading: false, data: res } : d)))
      .catch(() => setDrill(d => (d && d.key === key
        ? { ...d, loading: false, error: 'Could not load the deals behind this figure.' } : d)))
  }, [])

  const saveRate = useCallback((userId, raw) => {
    setBusy(true)
    return api.salesCommissionSetRate(userId, Number(raw))
      .then(() => load())
      .then(() => toast?.success('Rate saved'))
      .catch(e => toast?.error(e?.detail || 'Could not save the rate'))
      .finally(() => setBusy(false))
  }, [load, toast])

  const clearRate = useCallback((userId) => {
    setBusy(true)
    return api.salesCommissionClearRate(userId)
      .then(() => load())
      .catch(() => toast?.error('Could not clear the rate'))
      .finally(() => setBusy(false))
  }, [load, toast])

  const addPayment = useCallback((payload) => {
    setBusy(true)
    return api.salesCommissionAddPayment(payload)
      .then(() => load())
      .then(() => { setPeriodsLoading(true); return api.salesCommissionPeriods(periodType).then(setPeriods) })
      .then(() => toast?.success('Payment recorded'))
      .catch(e => toast?.error(e?.detail || 'Could not record the payment'))
      .finally(() => { setBusy(false); setPeriodsLoading(false) })
  }, [load, periodType, toast])

  const deletePayment = useCallback((p) => {
    if (!window.confirm(`Delete the ${money(p.amount_cents)} payment to ${p.rep_name} on ${p.paid_on}? `
                        + 'It goes back onto what they are owed.')) return Promise.resolve()
    setBusy(true)
    return api.salesCommissionDeletePayment(p.id)
      .then(() => load())
      .then(() => { setPeriodsLoading(true); return api.salesCommissionPeriods(periodType).then(setPeriods) })
      .catch(() => toast?.error('Could not delete the payment'))
      .finally(() => { setBusy(false); setPeriodsLoading(false) })
  }, [load, periodType, toast])

  const totals = data?.totals

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="mb-1">
          <Link to="/admin/super/crm/sales-management"
                className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            ← Sales Management
          </Link>
        </div>
        <div className="mb-4">
          <h1 className="font-display font-bold text-2xl text-pb-text">Sales Commissions</h1>
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
            Forecast on the open book, earned on the money that arrived
          </p>
        </div>

        {loading || !data ? (
          <p className="text-[12px] text-pb-faintest">Loading…</p>
        ) : (
          <>
            {!data.rate_set && (
              <div className={`${CARD} mb-4 border-pb-accent/40`}>
                <p className="text-[12px] text-pb-text">
                  No commission rate is set yet, so every figure below reads $0. Set the default
                  rate, or a rate per rep, in Commission rates.
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
              <Kpi label="Clubs attributed" value={totals.clubs_attributed} />
              <Kpi label="Pipeline value" value={money(totals.pipeline_value_cents)} />
              <Kpi label="Pipeline commission" value={money(totals.forecast_commission_cents)} />
              <Kpi label="Weighted commission" value={money(totals.weighted_forecast_commission_cents)}
                   hint="value × likelihood" />
            </div>

            <div className={`${CARD} mb-4`}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-display font-bold text-[13px]">Commission forecast by salesperson</h3>
                <Pill tone="faint">open deals</Pill>
              </div>
              <ForecastTable rows={data.rows} totals={totals} onOpen={openDeals}
                             activeKey={drill?.key} />
              <p className="text-[11px] text-pb-faintest mt-2">
                A club counts for the rep who EARNED it, the first to log a call outcome or send
                it an email, not whoever holds it now. A deal's value is the price of the modules
                it is expected to buy, less any discount; weighted multiplies that by the deal's
                own likelihood. Click any pipeline figure for the deals behind it.
              </p>
              {drill?.key?.endsWith('|open') && (
                <Drilldown open={drill} onClose={() => setDrill(null)} />
              )}
            </div>

            <div className={`${CARD} mb-4`}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-display font-bold text-[13px]">Commission earned and owed</h3>
                <Pill tone="faint">confirmed payments</Pill>
              </div>
              <EarnedTable rows={data.rows} totals={totals} onOpen={openDeals}
                           activeKey={drill?.key} />
              <p className="text-[11px] text-pb-faintest mt-2">
                Commission is earned on a confirmed Stripe payment, never on a deal's stage. Only
                new business counts. A club's first payment, and later ones that add modules; an
                annual renewal of what they already hold earns nothing. Figures are net of GST, at
                the rate that applied on the day the payment landed. Due is earned minus paid.
              </p>
              {drill?.key?.endsWith('|won') && (
                <Drilldown open={drill} onClose={() => setDrill(null)} />
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
              <RatesPanel reps={data.reps} defaultRate={data.default_rate_percent}
                          onSave={saveRate} onClear={clearRate} busy={busy} />
              <PaymentsPanel reps={data.reps} payments={data.payments}
                             onAdd={addPayment} onDelete={deletePayment} busy={busy} />
            </div>

            <PeriodsPanel periodType={periodType} onType={setPeriodType}
                          data={periods} loading={periodsLoading} />
          </>
        )}
      </div>
    </AdminLayout>
  )
}
