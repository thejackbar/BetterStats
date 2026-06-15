import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { money, Kpi, Pill, Icon, categoryLabel } from './ui'

function AlertCard({ title, icon, tone, items, empty, render }) {
  return (
    <div className="pb-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name={icon} size={16} className={tone === 'red' ? 'text-pb-red' : tone === 'amber' ? 'text-pb-amber' : 'text-pb-accent'} />
        <h3 className="font-display font-bold text-sm">{title}</h3>
        {items.length > 0 && <Pill tone={tone}>{items.length}</Pill>}
      </div>
      {items.length === 0
        ? <p className="text-[12.5px] text-pb-faint">{empty}</p>
        : <ul className="space-y-2">{items.map(render)}</ul>}
    </div>
  )
}

export default function BetterMerchHome() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    api.merchOverview()
      .then((d) => { if (live) setData(d) })
      .catch((e) => toast.error(e.message || 'Could not load BetterMerch'))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [])

  const alerts = data?.alerts || { low_stock: [], expiring: [], service_due: [] }

  return (
    <BetterMerchLayout title="BetterMerch"
      actions={<Link to="/admin/merch/stock" className="text-[12px] font-mono text-pb-faint hover:text-pb-accent">Manage stock →</Link>}>
      {loading ? <PbSpinner message="Loading stock…" /> : !data ? null : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi label="Stock value (cost)" value={money(data.stock_value_cost)} accent />
            <Kpi label="Stock value (retail)" value={money(data.stock_value_retail)} />
            <Kpi label="Units on hand" value={Number(data.units_on_hand || 0).toLocaleString()} />
            <Kpi label="Owed by members" value={money(data.outstanding_owed)} warn={data.outstanding_owed > 0} />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-pb-faint">
            <span>{data.product_count} products</span><span className="text-pb-faintest">·</span>
            <span>{data.variant_count} stock lines</span><span className="text-pb-faintest">·</span>
            <span>{data.asset_count} equipment assets</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <AlertCard title="Low stock" icon="list" tone="amber" items={alerts.low_stock}
              empty="Everything's above its reorder point."
              render={(it) => (
                <li key={it.variant_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <Link to={`/admin/merch/stock?product=${it.product_id}`} className="truncate hover:text-pb-accent">
                    {it.product_name}<span className="text-pb-faint"> · {it.variant_label}</span>
                  </Link>
                  <Pill tone={it.quantity <= 0 ? 'red' : 'amber'}>{it.quantity} left</Pill>
                </li>
              )} />
            <AlertCard title="Expiring soon" icon="timer" tone="red" items={alerts.expiring}
              empty="Nothing expiring in the next 30 days."
              render={(it) => (
                <li key={it.variant_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="truncate">{it.product_name}<span className="text-pb-faint"> · {it.variant_label}</span></span>
                  <Pill tone={it.expired ? 'red' : 'amber'}>{it.expired ? 'expired' : it.expiry_date}</Pill>
                </li>
              )} />
            <AlertCard title="Service / replace due" icon="settings" tone="amber" items={alerts.service_due}
              empty="No equipment due for service or replacement."
              render={(it) => (
                <li key={it.asset_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <Link to="/admin/merch/equipment" className="truncate hover:text-pb-accent">{it.name}</Link>
                  <Pill tone={(it.service_overdue || it.replace_overdue) ? 'red' : 'amber'}>
                    {it.replace_due ? 'replace' : 'service'} {(it.replace_due ? it.replace_due_date : it.service_due_date)}
                  </Pill>
                </li>
              )} />
          </div>

          <div className="flex flex-wrap gap-3">
            <Link to="/admin/merch/stock" className="pb-card px-4 py-3 hover:border-pb-accent/40 transition flex items-center gap-2 text-sm">
              <Icon name="plus" size={16} /> Add stock
            </Link>
            <Link to="/admin/merch/equipment" className="pb-card px-4 py-3 hover:border-pb-accent/40 transition flex items-center gap-2 text-sm">
              <Icon name="settings" size={16} /> Add equipment
            </Link>
            <Link to="/admin/merch/reports" className="pb-card px-4 py-3 hover:border-pb-accent/40 transition flex items-center gap-2 text-sm">
              <Icon name="ladders" size={16} /> Reports
            </Link>
          </div>
        </div>
      )}
    </BetterMerchLayout>
  )
}
