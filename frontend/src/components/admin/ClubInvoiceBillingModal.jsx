import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { BillingMethodCard, InvoiceQuoteSummary, OpenInvoicesCard, fmtDue } from './InvoiceBilling'

// Super Admin, on a club's behalf (migration 308): switch how the club pays,
// raise an invoice for the modules it wants (bundle and code applied, emailed
// to its Primary Club Admin), send this period's renewal invoice early, and
// resend or void an invoice. Same endpoints as the club's own Account page,
// addressed by org id — see routers/billing.py's /super/clubs/{org_id}/… routes.

export default function ClubInvoiceBillingModal({ club, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [code, setCode] = useState('')
  const [appliedCode, setAppliedCode] = useState('')
  const [quote, setQuote] = useState(null)
  const [quoteError, setQuoteError] = useState('')

  const load = () =>
    api.superInvoiceOverview(club.id).then(setData).catch((e) => setError(e.message || 'Could not load billing'))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selected.size === 0) { setQuote(null); setQuoteError(''); return }
    let cancelled = false
    setQuoteError('')
    api.superInvoiceQuote(club.id, [...selected], appliedCode)
      .then((q) => { if (!cancelled) setQuote(q) })
      .catch((e) => { if (!cancelled) { setQuote(null); setQuoteError(e.message || 'Could not price this') } })
    return () => { cancelled = true }
  }, [selected, appliedCode, club.id])

  const run = async (key, fn) => {
    setBusy(key)
    setError('')
    setMsg('')
    try {
      await fn()
    } catch (e) {
      setError(e.message || 'Something went wrong')
    } finally {
      setBusy('')
    }
  }

  // Only a Super Admin offers invoicing to a club (off by default). Stored on
  // the club itself, through the same All Clubs PATCH as every other setting.
  const setOffered = (on) => run('offer', async () => {
    if (!on && data?.billing_method === 'invoice'
      && !window.confirm(`${club.name} pays by invoice. Switching invoicing off moves it back to card: no renewal invoice will be sent, and it will need to subscribe by card when its current period ends. Continue?`)) return
    await api.superPatchClub(club.id, { invoice_billing_enabled: on })
    await load()
    setMsg(on ? `Invoicing is now available to ${club.name}.` : `Invoicing is switched off for ${club.name}.`)
  })

  const changeMethod = (method) => run('method', async () => {
    setData(await api.superSetBillingMethod(club.id, method))
    setMsg(method === 'invoice' ? 'This club now pays by invoice.' : 'This club now pays by card.')
  })

  const reported = (res) => {
    const inv = res.invoice
    setMsg(res.emailed
      ? `Invoice ${inv.invoice_number || ''} emailed to ${inv.sent_to_email}, due by ${fmtDue(inv.due_at)}.`
      : `Invoice ${inv.invoice_number || ''} raised but not emailed: ${res.email_error}. Its pay link is below.`)
  }

  const raise = () => run('raise', async () => {
    const res = await api.superRequestInvoice(club.id, [...selected], appliedCode)
    reported(res)
    setSelected(new Set())
    setCode('')
    setAppliedCode('')
    await load()
  })

  const renewalNow = () => run('renewal', async () => {
    if (!window.confirm(`Raise and email ${club.name}'s renewal invoice now, instead of waiting for the 14-day mark?`)) return
    reported(await api.superIssueRenewalInvoice(club.id))
    await load()
  })

  const resend = (inv) => run(inv.id, async () => {
    const res = await api.superResendInvoice(club.id, inv.id)
    if (res.ok) setMsg(`Emailed again to ${res.to}.`)
    else setError(`Not emailed: ${res.error}`)
    await load()
  })

  const voidIt = (inv) => run(inv.id, async () => {
    if (!window.confirm(`Void invoice ${inv.invoice_number || ''}? It can no longer be paid. Nothing the club already holds changes.`)) return
    await api.superVoidInvoice(club.id, inv.id)
    setMsg(`Invoice ${inv.invoice_number || ''} voided.`)
    await load()
  })

  const toggle = (key) => setSelected((s) => {
    const next = new Set(s)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  const modules = (data?.modules || []).filter((m) => m.can_subscribe)
  const period = data?.period

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="pb-card w-full max-w-2xl bg-pb-surface mt-10 mb-10 flex flex-col">
        <div className="p-5 pb-3 flex items-center justify-between gap-3">
          <h2 className="font-display font-bold text-lg text-pb-text min-w-0 truncate">{club.name} — invoicing</h2>
          <button onClick={onClose} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text shrink-0">Close</button>
        </div>
        <div className="p-5 pt-0 space-y-4">
          {error && <p className="font-mono text-[11px] text-pb-red">{error}</p>}
          {msg && <p className="font-mono text-[11px] text-emerald-400">{msg}</p>}
          {!data ? (
            <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
          ) : (
            <>
              <label className="pb-card p-4 flex items-start gap-3 cursor-pointer" data-testid="invoice-offer">
                <input
                  type="checkbox"
                  className="mt-0.5 shrink-0"
                  checked={!!data.invoice_billing_enabled}
                  disabled={busy === 'offer'}
                  onChange={(e) => setOffered(e.target.checked)}
                />
                <span className="min-w-0">
                  <span className="block font-display font-bold text-sm text-pb-text">Offer this club pay by invoice</span>
                  <span className="block text-[12px] text-pb-dim leading-snug mt-0.5">
                    Off by default. While it is off the club only sees the card checkout, and nothing here can raise
                    an invoice for it.
                  </span>
                </span>
              </label>

              {!data.invoice_billing_enabled ? null : (<>
              <BillingMethodCard overview={data} canEdit busy={busy === 'method'} onChange={changeMethod} />

              {period?.renewal_date && !period.renewal_invoice && (
                <div className="pb-card p-4 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[12px] text-pb-dim">
                    Renewal invoice due to go out {period.renewal_invoice_on}. Send it now instead?
                  </p>
                  <button
                    type="button"
                    onClick={renewalNow}
                    disabled={busy === 'renewal'}
                    className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50"
                  >
                    {busy === 'renewal' ? 'SENDING…' : 'SEND RENEWAL INVOICE NOW'}
                  </button>
                </div>
              )}

              <OpenInvoicesCard invoices={data.open_invoices} onResend={resend} onVoid={voidIt} busyId={busy} />

              <div className="pb-card p-4">
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">Raise an invoice</p>
                {!modules.length ? (
                  <p className="text-[12px] text-pb-dim">Every module is already subscribed.</p>
                ) : (
                  <div className="grid gap-1 sm:grid-cols-2 mb-3">
                    {modules.map((m) => (
                      <label key={m.module} className="flex items-center gap-2 text-[13px] text-pb-text cursor-pointer">
                        <input type="checkbox" checked={selected.has(m.module)} onChange={() => toggle(m.module)} />
                        <span className="min-w-0 truncate">{m.name}</span>
                        <span className="font-mono text-[10px] text-pb-dim uppercase">{m.status.replace('_', ' ')}</span>
                      </label>
                    ))}
                  </div>
                )}
                {selected.size > 0 && (
                  <>
                    {quote?.kind !== 'addon' && (
                      <div className="flex gap-2 mb-3">
                        <input
                          value={code}
                          onChange={(e) => setCode(e.target.value)}
                          placeholder="Discount code (optional)"
                          className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-[12px] font-mono focus:outline-none focus:border-pb-accent"
                        />
                        <button
                          type="button"
                          onClick={() => setAppliedCode(appliedCode ? '' : code.trim())}
                          disabled={!appliedCode && !code.trim()}
                          className="font-mono text-[10px] tracking-wide2 px-2 py-1.5 rounded border pb-hairline text-pb-text disabled:opacity-50"
                        >
                          {appliedCode ? 'REMOVE' : 'APPLY'}
                        </button>
                      </div>
                    )}
                    {quoteError && <p className="font-mono text-[11px] text-pb-red mb-2">{quoteError}</p>}
                    <InvoiceQuoteSummary quote={quote} />
                    <button
                      type="button"
                      onClick={raise}
                      disabled={busy === 'raise' || !quote || !data.primary_admin?.email}
                      className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold disabled:opacity-50"
                      style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                    >
                      {busy === 'raise' ? 'RAISING…' : `EMAIL INVOICE TO ${(data.primary_admin?.name || 'PRIMARY ADMIN').toUpperCase()}`}
                    </button>
                    {data.billing_method !== 'invoice' && (
                      <p className="text-[11px] text-pb-dim mt-2">Raising an invoice moves this club to invoice billing.</p>
                    )}
                  </>
                )}
              </div>
              </>)}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
