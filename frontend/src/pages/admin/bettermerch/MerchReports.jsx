import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { money, categoryLabel, Kpi, Btn, Icon } from './ui'

export default function MerchReports() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    api.merchReportSummary()
      .then((d) => { if (live) setData(d) })
      .catch((e) => toast.error(e.message || 'Could not load reports'))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [])

  return (
    <BetterMerchLayout title="Reports"
      actions={<a href={api.merchExportUrl()} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12.5px] border border-pb-hairline2 hover:bg-pb-surface2"><Icon name="arrow" size={14} /> Export CSV</a>}>
      {loading ? <PbSpinner message="Loading reports…" /> : !data ? null : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi label="Stock value (cost)" value={money(data.stock_value_cost)} accent />
            <Kpi label="Stock value (retail)" value={money(data.stock_value_retail)} />
            <Kpi label="Potential margin" value={money(data.stock_margin)} />
            <Kpi label="Owed by members" value={money(data.outstanding_owed)} warn={data.outstanding_owed > 0} />
          </div>

          <div>
            <h3 className="font-display font-bold text-sm mb-2">Stock value by type</h3>
            <div className="pb-card overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="text-left text-pb-faint border-b border-pb-hairline">
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Type</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Units</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At cost</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At retail</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.by_category || []).map((c) => (
                    <tr key={c.category} className="border-b border-pb-hairline/40">
                      <td className="px-3 py-2">{categoryLabel(c.category)}</td>
                      <td className="px-3 py-2 text-right">{c.units_on_hand}</td>
                      <td className="px-3 py-2 text-right">{money(c.stock_value_cost)}</td>
                      <td className="px-3 py-2 text-right">{money(c.stock_value_retail)}</td>
                    </tr>
                  ))}
                  {(data.by_category || []).length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-center text-pb-faint">No stock recorded.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {(data.by_category_node || []).length > 0 && (
            <div>
              <h3 className="font-display font-bold text-sm mb-2">Stock value by category</h3>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-[12.5px]">
                  <thead>
                    <tr className="text-left text-pb-faint border-b border-pb-hairline">
                      <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Category</th>
                      <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Units</th>
                      <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At cost</th>
                      <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At retail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_category_node.map((n) => (
                      <tr key={n.id} className="border-b border-pb-hairline/40">
                        <td className="px-3 py-2">
                          <span style={{ paddingLeft: `${(n.depth - 1) * 16}px` }}>{n.name}</span>
                          <span className="text-pb-faintest text-[10px] ml-2">{categoryLabel(n.top_category)}</span>
                        </td>
                        <td className="px-3 py-2 text-right">{n.units_on_hand}</td>
                        <td className="px-3 py-2 text-right">{money(n.stock_value_cost)}</td>
                        <td className="px-3 py-2 text-right">{money(n.stock_value_retail)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div>
            <h3 className="font-display font-bold text-sm mb-2">Stock value by item</h3>
            <div className="pb-card overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="text-left text-pb-faint border-b border-pb-hairline">
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Item</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase">Category</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Units</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At cost</th>
                    <th className="px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">At retail</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.by_item || []).map((it) => (
                    <tr key={it.product_id} className="border-b border-pb-hairline/40">
                      <td className="px-3 py-2">{it.name}{!it.for_resale && <span className="text-pb-faint"> (club use)</span>}</td>
                      <td className="px-3 py-2 text-pb-faint">{categoryLabel(it.category)}</td>
                      <td className="px-3 py-2 text-right">{it.units_on_hand}</td>
                      <td className="px-3 py-2 text-right">{money(it.stock_value_cost)}</td>
                      <td className="px-3 py-2 text-right">{it.for_resale ? money(it.stock_value_retail) : '-'}</td>
                    </tr>
                  ))}
                  {(data.by_item || []).length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-pb-faint">No stock recorded.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3 className="font-display font-bold text-sm mb-2">Owed by members</h3>
            {(data.owed_by_player || []).length === 0 ? (
              <div className="pb-card p-6 text-center text-pb-faint text-sm">Nothing outstanding — everyone's square.</div>
            ) : (
              <div className="pb-card divide-y divide-pb-hairline/50">
                {data.owed_by_player.map((p) => (
                  <div key={p.player_id} className="flex items-center justify-between px-4 py-2 text-[13px]">
                    <span>{p.player_name}</span>
                    <span className="font-display font-bold text-pb-amber">{money(p.owed)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </BetterMerchLayout>
  )
}
