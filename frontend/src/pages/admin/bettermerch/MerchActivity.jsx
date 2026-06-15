import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { money, MOVEMENT_KINDS, kindLabel, Btn, Select, Pill, Icon } from './ui'

const dirTone = (kind) => {
  const m = MOVEMENT_KINDS.find((x) => x.key === kind)
  if (kind === 'received') return 'green'
  if (m?.dir === 'out') return 'red'
  return 'faint'
}

export default function MerchActivity() {
  const toast = useToast()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [kind, setKind] = useState('')
  const [unpaidOnly, setUnpaidOnly] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.merchListMovements({ kind: kind || undefined, unpaidOnly, limit: 300 })
      setRows(d.movements || [])
    } catch (e) {
      toast.error(e.message || 'Could not load activity')
    } finally {
      setLoading(false)
    }
  }, [kind, unpaidOnly])
  useEffect(() => { load() }, [load])

  const markPaid = async (m, paid) => {
    try {
      await api.merchUpdateMovement(m.id, { paid })
      toast.success(paid ? 'Marked paid' : 'Marked owing')
      load()
    } catch (e) { toast.error(e.message || 'Could not update') }
  }
  const undo = async (m) => {
    if (!window.confirm('Undo this movement? It reverses the stock change.')) return
    try {
      await api.merchDeleteMovement(m.id)
      toast.success('Movement undone')
      load()
    } catch (e) { toast.error(e.message || 'Could not undo') }
  }

  return (
    <BetterMerchLayout title="Activity">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-44">
          <option value="">All movement types</option>
          {MOVEMENT_KINDS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-[12.5px] text-pb-faint cursor-pointer">
          <input type="checkbox" checked={unpaidOnly} onChange={(e) => setUnpaidOnly(e.target.checked)} /> Owing only
        </label>
      </div>

      {loading ? <PbSpinner message="Loading activity…" /> : rows.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">No movements recorded yet.</div>
      ) : (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-pb-faint border-b border-pb-hairline">
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Date</th>
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Item</th>
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Type</th>
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Change</th>
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Player</th>
                <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Amount</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-b border-pb-hairline/40 hover:bg-pb-surface2/40">
                  <td className="px-3 py-2 text-pb-faint whitespace-nowrap">{m.occurred_on || (m.created_at || '').slice(0, 10)}</td>
                  <td className="px-3 py-2"><span className="truncate">{m.product_name}</span><span className="text-pb-faint"> · {m.variant_label}</span></td>
                  <td className="px-3 py-2"><Pill tone={dirTone(m.kind)}>{kindLabel(m.kind)}</Pill></td>
                  <td className={`px-3 py-2 text-right font-display font-bold ${m.delta > 0 ? 'text-emerald-300' : m.delta < 0 ? 'text-pb-red' : ''}`}>{m.delta > 0 ? `+${m.delta}` : m.delta}<span className="text-pb-faintest font-normal"> → {m.quantity_after}</span></td>
                  <td className="px-3 py-2 text-pb-faint">{m.player_name || '—'}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {m.amount != null ? (
                      <span className="inline-flex items-center gap-2 justify-end">
                        {money(m.amount)}
                        {m.paid ? <Pill tone="green">paid</Pill>
                          : <button onClick={() => markPaid(m, true)} className="text-pb-amber underline hover:text-pb-accent">owing</button>}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => undo(m)} title="Undo" className="text-pb-faint hover:text-pb-red p-1"><Icon name="trash" size={14} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </BetterMerchLayout>
  )
}
