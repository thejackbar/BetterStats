// Shared bits for the BetterMerch surface — kept local so the module is
// self-contained, reusing the house Icon + spinner.
import { Icon } from '../betterselect/ui'

export const money = (n) =>
  `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

export const CATEGORIES = [
  { key: 'apparel', label: 'Apparel', blurb: 'Playing kit, training gear, caps' },
  { key: 'equipment', label: 'Equipment', blurb: 'Balls, bats, stumps, machines' },
  { key: 'food_drink', label: 'Food & Drink', blurb: 'Canteen and bar stock' },
]

export const categoryLabel = (key) => CATEGORIES.find((c) => c.key === key)?.label || key

// Movement kinds, grouped for the in/out picker.
export const MOVEMENT_KINDS = [
  { key: 'received', label: 'Received', dir: 'in', blurb: 'New stock came in' },
  { key: 'sold', label: 'Sold', dir: 'out', money: true, blurb: 'Sold to a member or at the canteen' },
  { key: 'issued', label: 'Issued', dir: 'out', money: true, blurb: 'Given to a player (kit)' },
  { key: 'used', label: 'Used', dir: 'out', blurb: 'Used up (e.g. match balls)' },
  { key: 'write_off', label: 'Write-off', dir: 'out', blurb: 'Damaged, lost or expired' },
  { key: 'stocktake', label: 'Stocktake', dir: 'set', blurb: 'Set the count from a hand count' },
  { key: 'adjustment', label: 'Adjustment', dir: 'delta', blurb: 'Manual correction' },
]
export const kindLabel = (k) => MOVEMENT_KINDS.find((m) => m.key === k)?.label || k

export const CONDITIONS = [
  { key: 'new', label: 'New' },
  { key: 'good', label: 'Good' },
  { key: 'fair', label: 'Fair' },
  { key: 'poor', label: 'Poor' },
  { key: 'retired', label: 'Retired' },
]
export const ASSET_STATUSES = [
  { key: 'in_service', label: 'In service' },
  { key: 'out_for_repair', label: 'Out for repair' },
  { key: 'retired', label: 'Retired' },
]

export function Btn({ children, onClick, variant = 'ghost', sm, disabled, icon, type = 'button', className = '' }) {
  const base = 'inline-flex items-center gap-1.5 rounded-lg font-medium transition disabled:opacity-40 disabled:cursor-not-allowed'
  const size = sm ? 'px-2.5 py-1.5 text-[12.5px]' : 'px-3.5 py-2 text-sm'
  const tones = {
    primary: 'bg-pb-accent text-black hover:brightness-110',
    ghost: 'border border-pb-hairline2 text-pb-text hover:bg-pb-surface2',
    danger: 'border border-pb-red/40 text-pb-red hover:bg-pb-red/10',
    subtle: 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2',
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${size} ${tones[variant] || tones.ghost} ${className}`}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}
      {children}
    </button>
  )
}

export function Field({ label, children, hint, half }) {
  return (
    <label className={half ? 'block flex-1 min-w-0 basis-[calc(50%-6px)]' : 'block'}>
      <span className="block text-[11.5px] text-pb-faint mb-[5px]">{label}</span>
      {children}
      {hint && <span className="block text-[10.5px] text-pb-faintest mt-1">{hint}</span>}
    </label>
  )
}

const inputCls = 'w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px] outline-none focus:border-pb-accent placeholder:text-pb-faint'

export function TextInput(props) {
  return <input {...props} className={`${inputCls} ${props.className || ''}`} />
}
export function NumberInput(props) {
  return <input type="number" inputMode="decimal" {...props} className={`${inputCls} ${props.className || ''}`} />
}
export function Select({ children, ...props }) {
  return <select {...props} className={`${inputCls} cursor-pointer ${props.className || ''}`}>{children}</select>
}
export function TextArea(props) {
  return <textarea {...props} className={`${inputCls} min-h-[64px] ${props.className || ''}`} />
}

export function Modal({ open, onClose, title, children, wide, footer }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4" style={{ backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`pb-card bg-pb-surface w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} mt-10 mb-8 max-h-[86vh] overflow-hidden flex flex-col`}>
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-pb-hairline shrink-0">
          <h2 className="font-display font-bold text-base">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-pb-faint hover:text-pb-text p-1 rounded hover:bg-pb-surface2"><Icon name="close" size={18} /></button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">{children}</div>
        {footer && <div className="px-5 py-3 border-t border-pb-hairline shrink-0 flex items-center justify-end gap-2">{footer}</div>}
      </div>
    </div>
  )
}

export function Kpi({ label, value, accent, warn }) {
  return (
    <div className={`pb-card px-4 py-3 ${accent ? 'border-pb-accent/40' : ''}`}>
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
      <div className={`font-display font-bold text-xl ${warn ? 'text-pb-amber' : 'text-pb-text'}`}
        style={accent && !warn ? { color: 'var(--pb-accent)' } : {}}>{value}</div>
    </div>
  )
}

export function Pill({ children, tone = 'faint' }) {
  const tones = {
    faint: 'bg-pb-surface2 text-pb-faint',
    accent: 'bg-pb-accent/12 text-pb-accent',
    amber: 'bg-pb-amber/12 text-pb-amber',
    red: 'bg-pb-red/12 text-pb-red',
    green: 'bg-emerald-500/12 text-emerald-300',
  }
  return <span className={`inline-flex items-center gap-1 px-1.5 py-px rounded font-mono text-[10px] tracking-wide ${tones[tone] || tones.faint}`}>{children}</span>
}

export { Icon }
