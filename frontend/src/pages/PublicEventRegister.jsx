// Events/Ticketing — public event view + registration (no login).
//
// Reached via a link shared by the club (/events/:eventId — the event's own
// UUID is the "token", same unguessable-id posture the rest of this codebase
// uses for public views keyed off a random id). No online payment collection
// yet (see services/events.py) — a priced event's registration is recorded
// `awaiting_payment` and the club follows up to collect payment by hand.
import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

function money(cents) {
  return `$${(cents / 100).toFixed(2)}`
}

export default function PublicEventRegister() {
  const { eventId } = useParams()
  const [event, setEvent] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', quantity: 1 })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)

  const load = useCallback(() => {
    api.publicEventGet(eventId).then(setEvent).catch(e => setError(e.message || 'Event not found'))
  }, [eventId])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.full_name.trim()) { setError('Name is required'); return }
    setBusy(true); setError('')
    try {
      const r = await api.publicEventRegister(eventId, form)
      setDone(r)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (error && !event) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <div className="font-display font-bold text-lg text-pb-text mb-1">Event not found</div>
          <div className="font-mono text-[11px] text-pb-faint">{error}</div>
        </div>
      </div>
    )
  }
  if (!event) {
    return <div className="min-h-screen bg-pb-bg flex items-center justify-center"><div className="font-mono text-[11px] text-pb-faint">Loading…</div></div>
  }

  return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full">
        <div className="text-center mb-6">
          {event.club_name && <div className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{event.club_name.toUpperCase()}</div>}
          <div className="font-display font-bold text-2xl text-pb-text">{event.title}</div>
          <div className="font-mono text-[11px] text-pb-faint mt-1">
            {new Date(event.starts_at).toLocaleString()}{event.location ? ` · ${event.location}` : ''}
          </div>
          {event.is_ticketed && event.ticket_price_cents > 0 && (
            <div className="font-mono text-[12px] mt-1" style={{ color: 'var(--pb-accent)' }}>{money(event.ticket_price_cents)} per person</div>
          )}
          {event.spots_left != null && (
            <div className="font-mono text-[10px] text-pb-faintest mt-1">{event.sold_out ? 'Fully booked' : `${event.spots_left} spot${event.spots_left === 1 ? '' : 's'} left`}</div>
          )}
        </div>
        {event.description && <p className="text-pb-dim text-sm text-center mb-6">{event.description}</p>}

        {done ? (
          <div className="pb-card p-5 text-center">
            <div className="text-pb-text font-semibold mb-1">You're registered, {done.full_name}!</div>
            <div className="font-mono text-[11px] text-pb-faint">
              {done.payment_status === 'awaiting_payment'
                ? `The club will follow up to collect payment (${money(done.amount_cents)}).`
                : "See you there."}
            </div>
          </div>
        ) : !event.registration_open || event.sold_out ? (
          <div className="pb-card p-5 text-center text-pb-dim text-sm">
            {event.sold_out ? 'This event is fully booked.' : 'Registration is closed for this event.'}
          </div>
        ) : (
          <div className="pb-card p-5">
            {error && <div className="text-pb-red text-sm mb-3">{error}</div>}
            <div className="space-y-2.5">
              <input className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                placeholder="Full name" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
              <input className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                placeholder="Email (optional)" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
              <input className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                placeholder="Phone (optional)" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
              <div className="flex items-center gap-2">
                <label className="font-mono text-[11px] text-pb-faint">Number of people</label>
                <input type="number" min="1" className="w-20 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  value={form.quantity} onChange={e => setForm(f => ({ ...f, quantity: Math.max(1, Number(e.target.value) || 1) }))} />
              </div>
              <button onClick={submit} disabled={busy || !form.full_name.trim()}
                className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}>
                {busy ? 'REGISTERING…' : 'REGISTER'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
