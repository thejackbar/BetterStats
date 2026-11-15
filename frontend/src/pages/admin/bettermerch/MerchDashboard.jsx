import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { money, categoryLabel, Kpi, Pill, Select, TextInput, Icon } from './ui'

const WINDOWS = [
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
  { days: 180, label: 'Last 6 months' },
  { days: 365, label: 'Last 12 months' },
]

// One colour per meaning, reused everywhere: the theme accent is stock, green is
// sold, blue is given out to players, amber is a warning, red is gone.
const C = {
  stock: 'var(--pb-accent, #16c784)',
  sold: 'var(--pb-positive, #22c55e)',
  issued: '#38bdf8',
  warn: 'var(--pb-amber, #f59e0b)',
  lost: 'var(--pb-red, #ef4444)',
  muted: 'var(--pb-faintest, #475569)',
}
const AXIS = { fill: 'var(--pb-faint, #64748b)', fontSize: 10 }

const STATUS = {
  out: { label: 'Out of stock', tone: 'red', rank: 0 },
  low: { label: 'Low stock', tone: 'amber', rank: 1 },
  running_low: { label: 'Running low', tone: 'amber', rank: 2 },
  not_selling: { label: 'Not selling', tone: 'faint', rank: 3 },
  ok: { label: 'OK', tone: 'green', rank: 4 },
}

const num = (n) => Number(n || 0).toLocaleString()
const shortDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '')
const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many}`
const trunc = (s, n = 20) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s)

function ChartTip({ active, payload, label, fmt }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border border-pb-hairline2 rounded px-3 py-2 text-[12px] shadow-lg">
      <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-sm" style={{ background: p.color || p.fill }} />
          <span className="text-pb-faint">{p.name}</span>
          <span className="font-mono font-bold text-pb-text ml-auto pl-3">{fmt ? fmt(p.value, p.dataKey) : num(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

function Card({ title, sub, right, children, className = '' }) {
  return (
    <section className={`pb-card p-4 min-w-0 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <h3 className="font-display font-bold text-sm">{title}</h3>
          {sub && <p className="text-[11.5px] text-pb-faint mt-0.5">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Toggle({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-lg border border-pb-hairline2 overflow-hidden text-[11.5px]" role="group">
      {options.map((o) => (
        <button key={o.key} type="button" onClick={() => onChange(o.key)} aria-pressed={value === o.key}
          className={`px-2.5 py-1 ${value === o.key ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Empty({ children }) {
  return <p className="text-[12.5px] text-pb-faint py-10 text-center">{children}</p>
}

function StockOverTime({ data }) {
  const [mode, setMode] = useState('units')
  const rows = data.series.map((s) => ({ ...s, label: shortDate(s.start) }))
  const key = mode === 'units' ? 'stock_units' : 'stock_value_cost'
  const flat = rows.length > 0 && rows.every((r) => r[key] === rows[0][key])
  return (
    <Card title="Stock on hand over time"
      sub={data.notes.history || `Balance at the end of each ${data.bucket}, walked back from today's count through every movement.`}
      right={<Toggle value={mode} onChange={setMode} options={[{ key: 'units', label: 'Units' }, { key: 'value', label: 'Value at cost' }]} />}>
      {flat && <p className="text-[11.5px] text-pb-faint mb-2">Flat so far: nothing has moved in this window. The line fills in as you record sales, deliveries and stocktakes.</p>}
      <ResponsiveContainer width="100%" height={230}>
        <AreaChart data={rows} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <defs>
            <linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--pb-accent, #16c784)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--pb-accent, #16c784)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} minTickGap={24} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} width={52}
            tickFormatter={mode === 'units' ? num : (v) => `$${num(v)}`} />
          <Tooltip content={<ChartTip fmt={mode === 'units' ? undefined : (v) => money(v)} />} />
          <Area type="monotone" dataKey={key} name={mode === 'units' ? 'Units on hand' : 'Value at cost'}
            stroke={C.stock} strokeWidth={2} fill="url(#stockFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  )
}

function SalesOverTime({ data }) {
  const [mode, setMode] = useState('units')
  const rows = data.series.map((s) => ({ ...s, label: shortDate(s.start) }))
  const any = rows.some((r) => r.sold || r.issued || r.revenue)
  return (
    <Card title="What went out"
      sub={`Per ${data.bucket}. Sold is what customers bought; issued is kit given to players.`}
      right={<Toggle value={mode} onChange={setMode} options={[{ key: 'units', label: 'Units' }, { key: 'revenue', label: 'Revenue' }]} />}>
      {!any ? <Empty>No sales recorded in the last {data.window_days} days. They appear here as you record Sold movements, sync Square, or orders come in from the online store.</Empty> : (
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={rows} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" vertical={false} />
            <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} minTickGap={24} />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} width={52}
              tickFormatter={mode === 'units' ? num : (v) => `$${num(v)}`} />
            <Tooltip content={<ChartTip fmt={mode === 'units' ? undefined : (v) => money(v)} />} cursor={{ fill: 'rgba(148,163,184,0.08)' }} />
            {mode === 'units' ? (
              <>
                <Legend iconType="square" wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="sold" name="Sold" stackId="a" fill={C.sold} radius={[0, 0, 0, 0]} />
                <Bar dataKey="issued" name="Issued" stackId="a" fill={C.issued} radius={[2, 2, 0, 0]} />
              </>
            ) : (
              <Bar dataKey="revenue" name="Revenue" fill={C.sold} radius={[2, 2, 0, 0]} />
            )}
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}

function BestSellers({ data }) {
  const [mode, setMode] = useState('sold')
  const rows = useMemo(() => (
    data.products.filter((p) => p[mode] > 0)
      .sort((a, b) => b[mode] - a[mode] || a.name.localeCompare(b.name))
      .slice(0, 10)
      .map((p) => ({ name: trunc(p.name, 22), full: p.name, value: p[mode] }))
  ), [data, mode])
  return (
    <Card title="Best sellers"
      sub={`Top ten over the last ${data.window_days} days.`}
      right={<Toggle value={mode} onChange={setMode} options={[{ key: 'sold', label: 'Units' }, { key: 'revenue', label: 'Revenue' }]} />}>
      {rows.length === 0 ? <Empty>Nothing has sold in this window yet.</Empty> : (
        <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 28 + 20)}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" horizontal={false} />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false}
              tickFormatter={mode === 'sold' ? num : (v) => `$${num(v)}`} />
            <YAxis type="category" dataKey="name" tick={{ ...AXIS, fontSize: 11 }} axisLine={false} tickLine={false} width={120} />
            <Tooltip content={<ChartTip fmt={mode === 'sold' ? undefined : (v) => money(v)} />} cursor={{ fill: 'rgba(148,163,184,0.08)' }}
              labelFormatter={(_, p) => p?.[0]?.payload?.full} />
            <Bar dataKey="value" name={mode === 'sold' ? 'Units sold' : 'Revenue'} fill={C.sold} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}

function SizeColour({ data }) {
  const [by, setBy] = useState('size')
  const rows = (by === 'size' ? data.by_size : data.by_colour)
    .map((r) => ({ name: by === 'size' ? r.size : r.colour, on_hand: r.on_hand, sold: r.sold }))
  return (
    <Card title={by === 'size' ? 'Apparel by size' : 'Apparel by colour'}
      sub={`Units on the shelf now beside units sold in the last ${data.window_days} days.`}
      right={<Toggle value={by} onChange={setBy} options={[{ key: 'size', label: 'Size' }, { key: 'colour', label: 'Colour' }]} />}>
      {rows.length === 0 ? <Empty>No apparel with a {by} recorded. Add a {by} to each stock line in Inventory to see this.</Empty> : (
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={rows} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" vertical={false} />
            <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} interval={0} />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} allowDecimals={false} />
            <Tooltip content={<ChartTip />} cursor={{ fill: 'rgba(148,163,184,0.08)' }} />
            <Legend iconType="square" wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="on_hand" name="On hand" fill={C.stock} radius={[2, 2, 0, 0]} />
            <Bar dataKey="sold" name="Sold" fill={C.sold} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}

function ValueByCategory({ data }) {
  const rows = data.by_category.filter((g) => g.value_cost > 0 || g.units_on_hand > 0)
    .slice(0, 12).map((g) => ({ name: trunc(g.name === 'Uncategorised' ? `${categoryLabel(g.category)}, no category` : g.name, 24), full: `${g.name} (${categoryLabel(g.category)})`, value: g.value_cost, units: g.units_on_hand }))
  return (
    <Card title="Where the money is sitting" sub="Stock value at cost by category, with units on the shelf in the tooltip.">
      {rows.length === 0 ? <Empty>No stock value recorded. Add a cost to your items to see this.</Empty> : (
        <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 28 + 20)}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" horizontal={false} />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} tickFormatter={(v) => `$${num(v)}`} />
            <YAxis type="category" dataKey="name" tick={{ ...AXIS, fontSize: 11 }} axisLine={false} tickLine={false} width={120} />
            <Tooltip cursor={{ fill: 'rgba(148,163,184,0.08)' }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload
              return (
                <div className="bg-pb-surface border border-pb-hairline2 rounded px-3 py-2 text-[12px] shadow-lg">
                  <p className="font-mono text-[10px] text-pb-faint mb-1">{p.full}</p>
                  <p><span className="font-mono font-bold">{money(p.value)}</span> <span className="text-pb-faint">at cost · {num(p.units)} units</span></p>
                </div>
              )
            }} />
            <Bar dataKey="value" name="Value at cost" fill={C.stock} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}

function Attention({ title, tone, items, empty, render }) {
  return (
    <div className="pb-card p-4 min-w-0">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="font-display font-bold text-sm">{title}</h3>
        {items.length > 0 && <Pill tone={tone}>{items.length}</Pill>}
      </div>
      {items.length === 0 ? <p className="text-[12.5px] text-pb-faint">{empty}</p> : (
        <ul className="space-y-1.5">
          {items.slice(0, 6).map(render)}
          {items.length > 6 && <li className="text-[11.5px] text-pb-faint">and {items.length - 6} more in the table below</li>}
        </ul>
      )}
    </div>
  )
}

function VariantLines({ p }) {
  const max = Math.max(1, ...p.variants.map((v) => v.quantity))
  return (
    <div className="px-3 py-2 bg-pb-surface2/40">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-left text-pb-faint">
            <th className="py-1 pr-2 font-normal">Line</th>
            <th className="py-1 pr-2 font-normal w-[40%]">On hand</th>
            <th className="py-1 pr-2 font-normal text-right">Reorder at</th>
            <th className="py-1 pr-2 font-normal text-right">Sold</th>
            <th className="py-1 font-normal text-right">Last sold</th>
          </tr>
        </thead>
        <tbody>
          {p.variants.map((v) => (
            <tr key={v.variant_id} className="border-t border-pb-hairline/40">
              <td className="py-1 pr-2">{v.label}{v.colour && v.label !== v.colour && !v.label.includes(v.colour) ? <span className="text-pb-faint"> · {v.colour}</span> : null}</td>
              <td className="py-1 pr-2">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 rounded-full bg-pb-surface3 flex-1 min-w-[40px] overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(v.quantity / max) * 100}%`, background: v.quantity <= 0 ? C.lost : v.low_stock ? C.warn : C.stock }} />
                  </div>
                  <span className="w-8 text-right font-mono">{v.quantity}</span>
                </div>
              </td>
              <td className="py-1 pr-2 text-right text-pb-faint">{v.threshold ?? '–'}</td>
              <td className="py-1 pr-2 text-right">{v.sold}</td>
              <td className="py-1 text-right text-pb-faint">{v.last_sold ? shortDate(v.last_sold) : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const SORTS = {
  name: { label: 'Name', fn: (a, b) => a.name.localeCompare(b.name) },
  sold: { label: 'Sold', fn: (a, b) => b.sold - a.sold || a.name.localeCompare(b.name) },
  on_hand: { label: 'On hand', fn: (a, b) => b.on_hand - a.on_hand || a.name.localeCompare(b.name) },
  value: { label: 'Value', fn: (a, b) => b.value_cost - a.value_cost || a.name.localeCompare(b.name) },
  cover: { label: 'Weeks left', fn: (a, b) => (a.weeks_cover ?? 1e9) - (b.weeks_cover ?? 1e9) || a.name.localeCompare(b.name) },
  status: { label: 'Needs attention', fn: (a, b) => STATUS[a.status].rank - STATUS[b.status].rank || a.name.localeCompare(b.name) },
}

function ProductTable({ data }) {
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('status')
  const [open, setOpen] = useState(null)
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return data.products
      .filter((p) => (!needle || p.name.toLowerCase().includes(needle))
        && (!type || p.category === type) && (!status || p.status === status))
      .sort(SORTS[sort].fn)
  }, [data, q, type, status, sort])
  const th = 'px-3 py-2 font-mono text-[10px] tracking-wide2 uppercase'
  return (
    <Card title="Every item" sub={`${rows.length} of ${data.products.length} products. Tap a row for its sizes and colours.`}>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search items" aria-label="Search items" className="!w-48" />
        <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type" className="!w-40">
          <option value="">All types</option>
          <option value="apparel">Apparel</option>
          <option value="equipment">Equipment</option>
          <option value="food_drink">Food &amp; Drink</option>
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status" className="!w-44">
          <option value="">Any status</option>
          {Object.entries(STATUS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort" className="!w-44">
          {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>Sort: {s.label}</option>)}
        </Select>
      </div>
      <div className="overflow-x-auto -mx-4 px-4">
        <table className="w-full text-[12.5px] min-w-[720px]">
          <thead>
            <tr className="text-left text-pb-faint border-b border-pb-hairline">
              <th className={th}>Item</th>
              <th className={`${th} text-right`}>On hand</th>
              <th className={`${th} text-right`}>Sold</th>
              <th className={`${th} text-right`}>Per week</th>
              <th className={`${th} text-right`}>Weeks left</th>
              <th className={`${th} text-right`}>Value (cost)</th>
              <th className={`${th} text-right`}>Revenue</th>
              <th className={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const st = STATUS[p.status]
              const expanded = open === p.product_id
              return [
                <tr key={p.product_id} onClick={() => setOpen(expanded ? null : p.product_id)}
                  className="border-b border-pb-hairline/40 cursor-pointer hover:bg-pb-surface2/40">
                  <td className="px-3 py-2">
                    <button type="button" aria-expanded={expanded} className="text-left flex items-center gap-1.5"
                      onClick={(e) => { e.stopPropagation(); setOpen(expanded ? null : p.product_id) }}>
                      <span className={`inline-block text-pb-faint transition ${expanded ? 'rotate-90' : ''}`}>›</span>
                      <span>{p.name}</span>
                    </button>
                    <span className="text-pb-faintest text-[10.5px] ml-4">
                      {categoryLabel(p.category)}{p.category_name ? ` · ${p.category_name}` : ''}{!p.for_resale ? ' · club use' : ''}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{num(p.on_hand)}</td>
                  <td className="px-3 py-2 text-right font-mono">{num(p.sold)}</td>
                  <td className="px-3 py-2 text-right font-mono text-pb-faint">{p.per_week ? p.per_week : '–'}</td>
                  <td className="px-3 py-2 text-right font-mono text-pb-faint">{p.weeks_cover ?? '–'}</td>
                  <td className="px-3 py-2 text-right">{p.value_cost ? money(p.value_cost) : '–'}</td>
                  <td className="px-3 py-2 text-right">{p.revenue ? money(p.revenue) : '–'}</td>
                  <td className="px-3 py-2"><Pill tone={st.tone}>{st.label}</Pill></td>
                </tr>,
                expanded && (
                  <tr key={`${p.product_id}-v`} className="border-b border-pb-hairline/40">
                    <td colSpan={8} className="p-0"><VariantLines p={p} /></td>
                  </tr>
                ),
              ]
            })}
            {rows.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-pb-faint">No items match.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function ExportLinks({ days }) {
  const cls = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12.5px] border border-pb-hairline2 hover:bg-pb-surface2'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <a href={api.merchExportWorkbookUrl(days)} className={cls} download><Icon name="arrow" size={14} /> Excel workbook</a>
      <a href={api.merchExportUrl()} className={cls} download>Stock CSV</a>
      <a href={api.merchExportMovementsUrl(0)} className={cls} download>All movements CSV</a>
    </div>
  )
}

export default function MerchDashboard() {
  const toast = useToast()
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    api.merchDashboard(days)
      .then((d) => { if (live) setData(d) })
      .catch((e) => toast.error(e.message || 'Could not load the stock dashboard'))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [days])

  const k = data?.kpis
  const byStatus = (s) => (data?.products || []).filter((p) => p.status === s)

  return (
    <BetterMerchLayout title="Stock dashboard"
      actions={(
        <Select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time window" className="!w-40">
          {WINDOWS.map((w) => <option key={w.days} value={w.days}>{w.label}</option>)}
        </Select>
      )}>
      {loading && !data ? <PbSpinner message="Crunching stock…" /> : !data ? null : !data.notes.has_stock ? (
        <div className="pb-card p-8 text-center">
          <p className="text-sm mb-3">No stock entered yet.</p>
          <Link to="/admin/merch/stock" className="text-pb-accent text-sm hover:underline">Add your first item in Inventory →</Link>
        </div>
      ) : (
        <div className={`space-y-6 ${loading ? 'opacity-60 transition' : ''}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12px] text-pb-faint max-w-xl">
              Stock figures are as of today. Sales, issues and rates cover the last {data.window_days} days.
              Values use each item's cost and sell price as set now.
            </p>
            <ExportLinks days={days} />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi label="Units on hand" value={num(k.units_on_hand)} accent />
            <Kpi label="Stock value (cost)" value={money(k.stock_value_cost)} />
            <Kpi label="Stock value (retail)" value={money(k.stock_value_retail)} />
            <Kpi label="Potential margin" value={money(k.potential_margin)} />
            <Kpi label={`Units sold (${data.window_days}d)`} value={num(k.units_sold)} />
            <Kpi label={`Revenue (${data.window_days}d)`} value={money(k.revenue)} />
            <Kpi label="Est. margin on sales" value={money(k.est_margin)} />
            <Kpi label="Needs a look" value={num(k.out_of_stock + k.low_stock + k.running_low)}
              warn={k.out_of_stock + k.low_stock + k.running_low > 0} />
          </div>

          {(data.notes.variants_without_cost > 0 || data.notes.variants_without_price > 0 || data.notes.sold_units_without_price > 0) && (
            <div className="pb-card p-3 text-[12px] text-pb-faint space-y-1">
              {data.notes.variants_without_cost > 0 && <p>{plural(data.notes.variants_without_cost, 'stock line has', 'stock lines have')} no cost, so {data.notes.variants_without_cost === 1 ? 'it adds' : 'they add'} nothing to stock value or margin.</p>}
              {data.notes.variants_without_price > 0 && <p>{plural(data.notes.variants_without_price, 'stock line for sale has', 'stock lines for sale have')} no sell price, so {data.notes.variants_without_price === 1 ? 'it adds' : 'they add'} nothing to retail value.</p>}
              {data.notes.sold_units_without_price > 0 && <p>{plural(data.notes.sold_units_without_price, 'unit was', 'units were')} sold with no price recorded, so {data.notes.sold_units_without_price === 1 ? 'it counts' : 'they count'} as {data.notes.sold_units_without_price === 1 ? 'a sale' : 'sales'} but add{data.notes.sold_units_without_price === 1 ? 's' : ''} no revenue.</p>}
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <StockOverTime data={data} />
            <SalesOverTime data={data} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <BestSellers data={data} />
            <SizeColour data={data} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <ValueByCategory data={data} />
            <Card title="How it sold" sub={`Units and revenue by where the sale was recorded, last ${data.window_days} days.`}>
              {data.sales_by_source.length === 0 ? <Empty>No sales in this window.</Empty> : (
                <table className="w-full text-[12.5px]">
                  <thead>
                    <tr className="text-left text-pb-faint border-b border-pb-hairline">
                      <th className="py-2 font-mono text-[10px] tracking-wide2 uppercase">Source</th>
                      <th className="py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Units</th>
                      <th className="py-2 font-mono text-[10px] tracking-wide2 uppercase text-right">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.sales_by_source.map((s) => (
                      <tr key={s.source} className="border-b border-pb-hairline/40">
                        <td className="py-2">{{ manual: 'Recorded by hand', square: 'Square', online_store: 'Online store' }[s.source] || s.source}</td>
                        <td className="py-2 text-right font-mono">{num(s.units)}</td>
                        <td className="py-2 text-right">{money(s.revenue)}</td>
                      </tr>
                    ))}
                    {data.retired_sales.length > 0 && (
                      <tr><td colSpan={3} className="pt-3 text-[11.5px] text-pb-faint">
                        Includes {num(data.retired_sales.reduce((a, r) => a + r.units, 0))} units of retired items ({data.retired_sales.slice(0, 3).map((r) => r.name).join(', ')}{data.retired_sales.length > 3 ? '…' : ''}).
                      </td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <Attention title="Out of stock" tone="red" items={byStatus('out')} empty="Nothing has run out."
              render={(p) => (
                <li key={p.product_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="truncate min-w-0">{p.name}</span>
                  <Pill tone="red">{p.sold ? `${p.sold} sold` : 'none left'}</Pill>
                </li>
              )} />
            <Attention title="Low stock" tone="amber" items={byStatus('low')} empty="Everything is above its reorder point."
              render={(p) => {
                const low = p.variants.filter((v) => v.low_stock)
                return (
                  <li key={p.product_id} className="text-[12.5px]">
                    <span className="truncate block">{p.name}</span>
                    <span className="text-[11px] text-pb-faint">{low.slice(0, 4).map((v) => `${v.label} (${v.quantity})`).join(', ')}{low.length > 4 ? '…' : ''}</span>
                  </li>
                )
              }} />
            <Attention title="Running low" tone="amber" items={byStatus('running_low').sort((a, b) => a.weeks_cover - b.weeks_cover)}
              empty={`Nothing will run out within ${4} weeks at its current rate.`}
              render={(p) => (
                <li key={p.product_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="truncate min-w-0">{p.name}</span>
                  <Pill tone="amber">{p.weeks_cover} wks left</Pill>
                </li>
              )} />
            <Attention title="Not selling" tone="faint" items={byStatus('not_selling').sort((a, b) => b.value_cost - a.value_cost)}
              empty="Everything for sale has sold in this window."
              render={(p) => (
                <li key={p.product_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="truncate min-w-0">{p.name}</span>
                  <Pill>{money(p.value_cost)} tied up</Pill>
                </li>
              )} />
          </div>

          <ProductTable data={data} />
        </div>
      )}
    </BetterMerchLayout>
  )
}
