import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

// Super Admin equivalent of the Payment Methods panel on AdminAccount.jsx —
// same underlying Stripe Customer, any club by id, no "acting as" round
// trip needed. See routers/billing.py's /super/clubs/{org_id}/payment-methods
// routes. Add opens a Stripe-hosted setup-mode Checkout Session in a new tab
// (this modal has no post-redirect page of its own to return to), so the
// admin comes back here and hits Refresh once it's done.

export default function ClubPaymentMethodsModal({ club, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const load = () =>
    api.superListPaymentMethods(club.id).then(setData).catch((e) => setError(e.message || 'Could not load payment methods'))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const addPaymentMethod = async () => {
    setBusy('add')
    setError('')
    try {
      const res = await api.superCreatePaymentMethodSetupSession(club.id)
      window.open(res.url, '_blank', 'noopener')
    } catch (e) {
      setError(e.message || 'Could not start adding a payment method')
    } finally {
      setBusy('')
    }
  }

  const setDefault = async (pmId) => {
    setBusy(pmId)
    setError('')
    try {
      setData(await api.superSetDefaultPaymentMethod(club.id, pmId))
    } catch (e) {
      setError(e.message || 'Could not set this as the default payment method')
    } finally {
      setBusy('')
    }
  }

  const remove = async (pmId) => {
    if (!window.confirm('Remove this payment method?')) return
    setBusy(pmId)
    setError('')
    try {
      setData(await api.superRemovePaymentMethod(club.id, pmId))
    } catch (e) {
      setError(e.message || 'Could not remove this payment method')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="pb-card w-full max-w-md bg-pb-surface mt-16 max-h-[80vh] overflow-hidden flex flex-col">
        <div className="p-5 pb-3 shrink-0 flex items-center justify-between">
          <h2 className="font-display font-bold text-lg text-pb-text">{club.name}, payment methods</h2>
          <button onClick={load} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">Refresh</button>
        </div>
        <div className="p-5 pt-0 overflow-y-auto space-y-2">
          {error && <p className="font-mono text-[11px] text-pb-red mb-2">{error}</p>}
          {data === null ? (
            <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
          ) : !data.payment_methods.length ? (
            <p className="font-mono text-[11px] text-pb-faint">No payment methods on file.</p>
          ) : (
            data.payment_methods.map((pm) => (
              <div key={pm.id} className="flex items-center justify-between gap-2 font-mono text-[11px] border-b pb-hairline pb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-pb-text truncate">{pm.summary}</span>
                  {pm.is_default && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded-full text-[9px] uppercase bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
                      Default
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {!pm.is_default && (
                    <button onClick={() => setDefault(pm.id)} disabled={busy === pm.id}
                      className="font-mono text-[10px] tracking-wide2 px-2 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
                      {busy === pm.id ? '…' : 'SET DEFAULT'}
                    </button>
                  )}
                  {data.payment_methods.length > 1 && (
                    <button onClick={() => remove(pm.id)} disabled={busy === pm.id}
                      className="font-mono text-[10px] tracking-wide2 px-2 py-1 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50">
                      {busy === pm.id ? '…' : 'REMOVE'}
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="p-5 pt-3 border-t pb-hairline shrink-0 flex gap-2 justify-between">
          <button onClick={addPaymentMethod} disabled={busy === 'add'}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50">
            {busy === 'add' ? 'OPENING…' : '+ ADD (opens in a new tab)'}
          </button>
          <button onClick={onClose} className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
