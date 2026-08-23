import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { money, Btn, Select, Pill } from './ui'

const STATUS_TONE = { pending_payment: 'amber', paid: 'accent', fulfilled: 'green', cancelled: 'faint' }
const STATUS_LABEL = { pending_payment: 'Awaiting payment', paid: 'Paid', fulfilled: 'Fulfilled', cancelled: 'Cancelled' }

function OrderRow({ order, onChanged }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  async function setStatus(status) {
    setBusy(true)
    try { await api.merchUpdateOrder(order.id, status); toast.success('Updated'); onChanged() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-pb-text font-semibold text-sm">{order.customer_name}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {order.email || order.phone || '—'} · {new Date(order.created_at).toLocaleString()}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-display font-bold text-sm text-pb-text">{money(order.total_cents / 100)}</div>
          <Pill tone={STATUS_TONE[order.status] || 'faint'}>{STATUS_LABEL[order.status] || order.status}</Pill>
        </div>
      </div>
      <div className="mt-2 space-y-0.5">
        {order.items.map(i => (
          <div key={i.id} className="font-mono text-[11px] text-pb-dim flex justify-between">
            <span>{i.quantity}× {i.product_name}{i.variant_label ? ` (${i.variant_label})` : ''}</span>
            <span>{money((i.unit_price_cents * i.quantity) / 100)}</span>
          </div>
        ))}
      </div>
      {order.status === 'paid' && (
        <div className="mt-2 flex gap-2">
          <Btn sm variant="primary" disabled={busy} onClick={() => setStatus('fulfilled')}>Mark fulfilled</Btn>
        </div>
      )}
      {order.status === 'pending_payment' && (
        <div className="mt-2 flex gap-2">
          <Btn sm variant="danger" disabled={busy} onClick={() => setStatus('cancelled')}>Cancel (abandoned)</Btn>
        </div>
      )}
    </div>
  )
}

export default function MerchOrders() {
  const toast = useToast()
  const [orders, setOrders] = useState(null)
  const [status, setStatus] = useState('')

  const load = useCallback(() => {
    api.merchListOrders(status || undefined).then(d => setOrders(d.orders || [])).catch(e => toast.error(e.message))
  }, [status, toast])
  useEffect(() => { load() }, [load])

  return (
    <BetterMerchLayout title="Online Store">
      {orders === null ? <PbSpinner message="Loading orders…" /> : (
        <div>
          <p className="font-mono text-[10px] text-pb-faintest mb-3 leading-relaxed">
            Orders placed through the public online store. "Awaiting payment" clears itself once Stripe confirms, 
            if one sits there for a while, the customer likely abandoned checkout.
          </p>
          <div className="mb-3">
            <Select value={status} onChange={e => setStatus(e.target.value)} className="w-56">
              <option value="">All statuses</option>
              <option value="pending_payment">Awaiting payment</option>
              <option value="paid">Paid</option>
              <option value="fulfilled">Fulfilled</option>
              <option value="cancelled">Cancelled</option>
            </Select>
          </div>
          {orders.length === 0 ? (
            <div className="pb-card p-6 text-center text-pb-dim text-sm">No orders yet.</div>
          ) : (
            <div className="space-y-2">
              {orders.map(o => <OrderRow key={o.id} order={o} onChanged={load} />)}
            </div>
          )}
        </div>
      )}
    </BetterMerchLayout>
  )
}
