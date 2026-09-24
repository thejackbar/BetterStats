// Pay by invoice (migration 308) — the pieces the club's Account page and the
// Super Admin's per-club modal both draw, so the two can never describe the
// same invoice differently. The data is services/invoice_billing.py's
// `overview` and `plan_out` shapes, read as-is.

const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : ''
// A Perth "due by" is 11:59:59pm on its date; format it in Perth so a browser
// in another timezone doesn't show the day after.
const fmtDue = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString('en-AU', {
        day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Australia/Perth',
      })
    : ''
const money = (dollars) => `$${Number(dollars || 0).toFixed(2)}`
const cents = (c) => money((c || 0) / 100)
const stripPrefix = (name) => (name || '').replace(/^BetterCricket\s*—\s*/, '')

const LABEL = 'font-mono text-[10px] tracking-wide2 text-pb-faint uppercase'
const BTN = 'font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50 shrink-0'

// `clubView` is the club's own Account page: invoicing is arranged by a Super
// Admin, never chosen by the club, so there it is a statement of how the club
// pays rather than a choice between the two.
export function BillingMethodCard({ overview, canEdit, busy, onChange, clubView = false }) {
  if (!overview) return null
  const method = overview.billing_method
  const who = overview.primary_admin
  const period = overview.period
  const option = (value, title, body, disabled) => (
    <label
      className={`flex items-start gap-3 p-3 rounded border ${method === value ? 'border-pb-accent' : 'pb-hairline'} ${disabled ? 'opacity-60' : 'cursor-pointer'}`}
    >
      <input
        type="radio"
        name="billing-method"
        className="mt-0.5 shrink-0"
        checked={method === value}
        disabled={!canEdit || busy || disabled}
        onChange={() => onChange(value)}
      />
      <span className="min-w-0">
        <span className="block font-display font-bold text-sm text-pb-text">{title}</span>
        <span className="block text-[12px] text-pb-dim leading-snug mt-0.5">{body}</span>
      </span>
    </label>
  )
  return (
    <div className="pb-card p-4" data-testid="billing-method">
      <p className={`${LABEL} mb-3`}>How your club pays</p>
      {clubView ? (
        <div data-testid="billing-method-status">
          <p className="font-display font-bold text-sm text-pb-text">Pay by invoice</p>
          <p className="text-[12px] text-pb-dim leading-snug mt-0.5">
            BetterCricket manages your club's invoices. To add or cancel a module, or to go back to paying by card,
            contact <a className="underline" href="mailto:support@bettersports.com.au">support@bettersports.com.au</a>.
          </p>
        </div>
      ) : (
      <div className="grid gap-2 sm:grid-cols-2">
        {option('card', 'Pay by card', 'Check out through Stripe now. Renews automatically each year on the same card.')}
        {option(
          'invoice',
          'Pay by invoice',
          `We email an invoice to ${who ? who.name : "your club's Primary Admin"}, and a renewal invoice ${overview.renewal_notice_days} days before each year ends.`,
          !overview.can_use_invoice,
        )}
      </div>
      )}
      {!clubView && !overview.can_use_invoice && (
        <p className="text-[12px] text-pb-dim mt-2">
          Your club already pays by card through a Stripe subscription, so invoice billing can be chosen once that
          subscription has ended.
        </p>
      )}
      {method === 'invoice' && (
        <div className="mt-3 space-y-1 text-[12px] text-pb-dim">
          {who ? (
            <p>
              Invoices go to your Primary Admin, <span className="text-pb-text">{who.name}</span>
              {who.email ? <> ({who.email})</> : <span className="text-pb-red"> — no email address on file</span>}.
            </p>
          ) : (
            <p className="text-pb-red">
              Your club has no Primary Admin, so there is nobody to send an invoice to. Set one on your club's users.
            </p>
          )}
          {period?.renewal_date && (
            <p>
              Paid until <span className="text-pb-text">{fmtDue(period.ends_at)}</span>. Your renewal invoice
              {period.renewal_invoice
                ? <> ({period.renewal_invoice.invoice_number}) has been sent.</>
                : <> will be emailed on {fmtDate(period.renewal_invoice_on)}.</>}
            </p>
          )}
          {overview.email_live === false && (
            <p className="text-amber-300">
              Email isn't switched on for this server yet, so invoices are raised but not emailed. Use the pay link
              below.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function OpenInvoicesCard({ invoices, onResend, onVoid, busyId }) {
  if (!invoices?.length) return null
  return (
    <div className="pb-card p-4" data-testid="open-invoices">
      <p className={`${LABEL} mb-3`}>Invoices to pay</p>
      <div className="space-y-3">
        {invoices.map((inv) => (
          <div key={inv.id} className="border-b pb-hairline pb-3 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="font-display font-bold text-sm text-pb-text">
                {inv.invoice_number || 'Invoice'}
                <span className="font-mono text-[10px] text-pb-dim ml-2 uppercase">
                  {inv.invoice_kind === 'renewal' ? 'Renewal' : inv.invoice_kind === 'addon' ? 'Modules added' : 'Subscription'}
                </span>
              </p>
              <p className="font-mono text-[12px] text-pb-text">{cents(inv.amount_total_cents)} incl. GST</p>
            </div>
            <p className="text-[12px] text-pb-dim mt-1">
              {(inv.line_items || []).map((li) => stripPrefix(li.name)).join(', ')}
              {inv.service_start_date && <> · {fmtDate(inv.service_start_date)} to {fmtDate(inv.service_end_date)}</>}
            </p>
            <p className="text-[12px] text-pb-dim">
              Due by <span className="text-pb-text">{fmtDue(inv.due_at)}</span>
              {inv.emailed_at
                ? <> · emailed to {inv.sent_to_email} on {fmtDate(inv.emailed_at)}</>
                : inv.email_error
                  ? <span className="text-amber-300"> · not emailed: {inv.email_error}</span>
                  : null}
            </p>
            <div className="flex flex-wrap gap-2 mt-2">
              {inv.pay_url && (
                <a
                  href={inv.pay_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold"
                  style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                >
                  PAY NOW
                </a>
              )}
              {inv.invoice_pdf && (
                <a href={inv.invoice_pdf} target="_blank" rel="noreferrer" className={BTN}>
                  DOWNLOAD PDF
                </a>
              )}
              {onResend && (
                <button type="button" className={BTN} disabled={busyId === inv.id} onClick={() => onResend(inv)}>
                  {busyId === inv.id ? 'SENDING…' : 'EMAIL IT AGAIN'}
                </button>
              )}
              {onVoid && (
                <button
                  type="button"
                  disabled={busyId === inv.id}
                  onClick={() => onVoid(inv)}
                  className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50"
                >
                  VOID
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// The invoice-mode price summary. `quote` is plan_out's shape.
export function InvoiceQuoteSummary({ quote }) {
  if (!quote) return null
  const addon = quote.kind === 'addon'
  return (
    <div className="mb-3 space-y-1" data-testid="invoice-quote">
      {quote.line_items.map((li) => (
        <div key={li.key} className="flex items-center justify-between font-mono text-[11px] text-pb-dim gap-2">
          <span>{li.name}</span>
          <span>
            {addon && li.amount !== li.full_price && (
              <span className="text-pb-faint line-through mr-1">{money(li.full_price)}</span>
            )}
            {money(li.amount)}
          </span>
        </div>
      ))}
      {quote.discount > 0 && (
        <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400">
          <span>Bundle discount</span>
          <span>-{money(quote.discount)}</span>
        </div>
      )}
      {quote.coupon && (
        <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400">
          <span>{quote.coupon.display_name} ({quote.coupon.code})</span>
          <span>-{money(quote.coupon.amount_off)}</span>
        </div>
      )}
      <div className="flex items-center justify-between font-mono text-[12px] text-pb-text font-semibold pt-2 mt-1 border-t pb-hairline">
        <span>Invoice total, plus GST</span>
        <span>{money(quote.total)}</span>
      </div>
      <p className="text-[11px] text-pb-dim pt-1 leading-snug">
        {addon
          ? `Prorated to your renewal on ${fmtDate(quote.service_end_date)} (${quote.prorated?.days} of ${quote.prorated?.of_days} days), so your whole club renews together.`
          : `Covers ${fmtDate(quote.service_start_date)} to ${fmtDate(quote.service_end_date)}. If your club is in a trial, the year starts when the trial ends, so paying early costs you none of it.`}
        {' '}Due by {fmtDue(quote.due_at)}. GST is added on the invoice.
      </p>
    </div>
  )
}

// The Super Admin's live draft of the invoice being built, laid out the way
// the emailed one reads: who it goes to, one line per module, the bundle and
// the code, GST, and when it is due. Every figure comes from the server's
// plan_invoice, the same function the real invoice is raised from, so what is
// previewed is what is sent. GST is shown at 10% because the invoice adds it;
// Stripe works out the exact figure when the invoice is raised.
export function InvoicePreview({ club, admin, quote, pricing, empty, error }) {
  const exGst = quote ? Number(quote.total || 0) : 0
  const gst = Math.round(exGst * 10) / 100
  const addon = quote?.kind === 'addon'
  return (
    <div
      className="min-w-0 rounded border pb-hairline bg-pb-surface2 p-4 self-start"
      data-testid="invoice-preview"
      aria-live="polite"
      aria-busy={pricing ? 'true' : 'false'}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="font-display font-bold text-sm text-pb-text">Invoice</p>
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">
            Draft · {addon ? 'modules added to the current year' : quote ? 'first subscription' : 'not raised yet'}
          </p>
        </div>
        {pricing && <span className="font-mono text-[10px] text-pb-faint shrink-0">Updating…</span>}
      </div>
      <div className="mb-3">
        <p className={LABEL}>Bill to</p>
        <p className="text-[13px] text-pb-text">{club?.name}</p>
        {admin ? (
          <p className="text-[12px] text-pb-dim break-all">{admin.name}{admin.email ? ` · ${admin.email}` : ''}</p>
        ) : (
          <p className="text-[12px] text-pb-red">No Primary Club Admin with an email address to send it to.</p>
        )}
      </div>
      {empty ? (
        <p className="text-[12px] text-pb-dim py-3" data-testid="invoice-preview-empty">Pick a module to start the invoice.</p>
      ) : error && !quote ? (
        <p className="font-mono text-[11px] text-pb-red py-3">{error}</p>
      ) : !quote ? (
        <p className="text-[12px] text-pb-dim py-3">Working out the invoice…</p>
      ) : (
        <div className={`space-y-1 ${pricing ? 'opacity-60' : ''}`} data-testid="invoice-quote">
          {quote.line_items.map((li) => (
            <div key={li.key} className="flex items-center justify-between font-mono text-[11px] text-pb-dim gap-2" data-testid="invoice-line">
              <span className="min-w-0">{stripPrefix(li.name)}</span>
              <span className="shrink-0">
                {addon && li.amount !== li.full_price && (
                  <span className="text-pb-faint line-through mr-1">{money(li.full_price)}</span>
                )}
                {money(li.amount)}
              </span>
            </div>
          ))}
          {quote.discount > 0 && (
            <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400">
              <span>Bundle discount</span>
              <span>-{money(quote.discount)}</span>
            </div>
          )}
          {quote.coupon && (
            <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400" data-testid="invoice-coupon-line">
              <span className="min-w-0">{quote.coupon.display_name} ({quote.coupon.code})</span>
              <span className="shrink-0">-{money(quote.coupon.amount_off)}</span>
            </div>
          )}
          <div className="flex items-center justify-between font-mono text-[11px] text-pb-text pt-2 mt-1 border-t pb-hairline">
            <span>Subtotal (ex GST)</span>
            <span data-testid="invoice-total-ex">{money(exGst)}</span>
          </div>
          <div className="flex items-center justify-between font-mono text-[11px] text-pb-dim">
            <span>GST 10%</span>
            <span>{money(gst)}</span>
          </div>
          <div className="flex items-center justify-between font-mono text-[12px] text-pb-text font-semibold pt-1">
            <span>Total</span>
            <span>{money(exGst + gst)}</span>
          </div>
          <p className="text-[11px] text-pb-dim pt-2 leading-snug">
            {addon
              ? `Prorated to the renewal on ${fmtDate(quote.service_end_date)} (${quote.prorated?.days} of ${quote.prorated?.of_days} days), so the whole club renews together.`
              : `Covers ${fmtDate(quote.service_start_date)} to ${fmtDate(quote.service_end_date)}. A trial still running is not cut short: the year starts when it ends.`}
            {' '}Due by {fmtDue(quote.due_at)}. Stripe confirms the GST when the invoice is raised.
          </p>
        </div>
      )}
    </div>
  )
}

export { fmtDue }
