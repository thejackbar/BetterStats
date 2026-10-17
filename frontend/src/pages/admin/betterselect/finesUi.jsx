// Small shared pieces of the BetterSelect Fines screens: money and date
// formatting, the card and modal shells, and the one input style.
import { useEffect, useRef } from 'react'

export const money = (n) => `${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const shortDate = (iso) => {
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) } catch { return iso }
}
export const todayISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export const METHODS = ['PayID', 'Bank transfer', 'Cash', 'Other']
// useToast() hands back a new object each time a toast comes or goes, so a load
// keyed on it would re-run (and blank the screen) after every message. Read the
// latest one through a ref instead.
export function useLatest(value) {
  const ref = useRef(value)
  ref.current = value
  return ref
}
export const inputCls = 'bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-1.5 text-[13.5px] focus:outline-none focus:border-pb-accent min-w-0'

export function Card({ title, sub, children, right }) {
  return (
    <section className="pb-card rounded-xl p-4 sm:p-5 mb-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <h2 className="font-display font-bold text-[15px] tracking-tight">{title}</h2>
          {sub && <p className="text-[12.5px] text-pb-dim mt-0.5 max-w-[66ch]">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-3" style={{ background: 'rgba(0,0,0,.55)' }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-label={title} className="pb-card rounded-xl w-full max-w-md max-h-[88vh] overflow-y-auto p-4 sm:p-5 bg-pb-bg">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold text-[16px] min-w-0 truncate">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Close" className="text-pb-faint hover:text-pb-text text-lg leading-none px-1">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

