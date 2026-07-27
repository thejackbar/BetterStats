// Shared bits for BetterCRM — used by BOTH the club-facing module
// (pages/admin/bettercrm) and the platform-scope Super Admin page
// (pages/admin/SuperCrm.jsx), so a single Kanban/detail implementation serves
// the internal sales pipeline and the club's own CRM. Mirrors the
// self-contained bettermerch/ui.jsx pattern.
import { useState, useEffect } from 'react'
import { Icon } from '../../../pages/admin/betterselect/ui'
import { api } from '../../../lib/api'

// Dollar values everywhere here are cents (matches the backend's value_cents).
export const money = (cents) =>
  `$${(Number(cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

export const moneyToCents = (dollars) => Math.round(Number(dollars || 0) * 100)
export const centsToMoneyInput = (cents) => (Number(cents || 0) / 100) || ''

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

export function Field({ label, children, hint, half, width }) {
  // `width` (e.g. "140px") pins an explicit flex-basis via inline style, which
  // reliably wins over the shared inputCls's `w-full` (same-specificity
  // Tailwind utilities are order-dependent, not override-safe) — use it for
  // any field that shouldn't stretch to the modal's full grid width.
  const style = width ? { flexBasis: width, maxWidth: width, minWidth: 0 } : undefined
  return (
    <label className={half && !width ? 'block flex-1 min-w-0 basis-[calc(50%-6px)]' : width ? 'block flex-none' : 'block'} style={style}>
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

// Vocabulary the Kanban board + deal detail modal render with — deliberately
// overridable per surface. The platform-scope sales pipeline keeps the
// Pipedrive-style "Won/Lost/deal" language a sales team expects; the
// club-facing module (currently scoped to Sponsors) overrides it to plain
// words a volunteer club officer already uses, so the SAME components serve
// both without either audience seeing the other's jargon.
export const DEFAULT_CRM_TERMS = { won: 'Won', lost: 'Lost', itemSingular: 'deal', itemPlural: 'deals', titleLabel: 'Title' }

// Product Interest / module_keys vocabulary, shared by every surface that
// renders a deal's modules (Kanban card, list view, detail modal) — the raw
// backend keys are lowercase billing_pricing keys ('core' for BetterStats),
// always shown Sentence Case and in this fixed order regardless of the
// order module_keys happens to store them in.
export const MODULE_ORDER = ['core', 'select', 'socials', 'admin', 'iq', 'fantasy']
export const MODULE_LABELS = { core: 'Stats', select: 'Select', socials: 'Socials', admin: 'Admin', iq: 'IQ', fantasy: 'Fantasy' }
export const moduleLabel = (key) => MODULE_LABELS[key] || (key ? key[0].toUpperCase() + key.slice(1) : key)
// Sorted-for-display copy of a module_keys array — always Stats-first through
// Fantasy-last, with anything unrecognised tacked on the end alphabetically.
export const sortModuleKeys = (keys) => {
  const known = MODULE_ORDER.filter(k => (keys || []).includes(k))
  const unknown = (keys || []).filter(k => !MODULE_ORDER.includes(k)).sort()
  return [...known, ...unknown]
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

// How a club came to be onboarded — shown/edited on the deal detail card.
export const ONBOARDING_METHOD_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'self_serve_trial', label: 'Self-Serve Trial' },
  { value: 'super_admin_trial', label: 'Super Admin Trial' },
  { value: 'direct_subscriber', label: 'Direct to Subscriber (no trial)' },
  { value: 'none', label: 'None (not yet onboarded)' },
]
export const ONBOARDING_METHOD_LABELS = Object.fromEntries(ONBOARDING_METHOD_OPTIONS.map(o => [o.value, o.label]))

// Original acquisition channel, as a manually-set field on the deal (distinct
// from the auto-derived acquisition_channel shown in the CRM list/filters).
export const LEAD_SOURCE_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'edm', label: 'EDM' },
  { value: 'meta_ads', label: 'Meta Ads' },
  { value: 'outreach', label: 'Outreach' },
  { value: 'referral', label: 'Referral' },
  { value: 'google_search', label: 'Google Search' },
  { value: 'ai_search_assistants', label: 'AI / Search Assistants' },
  { value: 'other', label: 'Other' },
]

// Website Analytics — only meaningful for a platform deal/candidate linked to
// a Marketing Directory club (a marketing_club_id, whether or not a CrmDeal
// row exists yet — the New Deal modal's club-search step uses this the same
// way DealDetailModal does, before any deal is created). Reuses the SAME
// super-admin endpoint the Club Directory's own "visited the site" panel
// calls (services/club_directory.club_visit_detail).
export function WebsiteAnalyticsPanel({ marketingClubId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (!marketingClubId) return
    let alive = true
    setLoading(true)
    api.mktClubVisits(marketingClubId).then(d => { if (alive) setData(d) }).catch(() => {}).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [marketingClubId])

  if (!marketingClubId) return null
  return (
    <div>
      <h3 className="font-display font-bold text-[13px] mb-2">Website analytics</h3>
      {loading ? <p className="text-[12px] text-pb-faintest">Loading…</p> : !data?.views ? (
        <p className="text-[12px] text-pb-faintest">No tracked site visits for this club yet.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
          <div className="pb-card px-2.5 py-2">
            <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Page views</div>
            <div className="font-display font-bold text-[15px]">{data.views}</div>
          </div>
          <div className="pb-card px-2.5 py-2">
            <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Days visited</div>
            <div className="font-display font-bold text-[15px]">{data.distinct_days}</div>
          </div>
          <div className="pb-card px-2.5 py-2">
            <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Unique IPs</div>
            <div className="font-display font-bold text-[15px]">{data.unique_ips}</div>
            {data.visits_per_ip != null && <div className="text-pb-faintest text-[10.5px]">{data.visits_per_ip}/IP avg</div>}
          </div>
          <div className="pb-card px-2.5 py-2">
            <div className="text-pb-faint text-[10.5px] uppercase tracking-wide">Contact page</div>
            <div className="font-display font-bold text-[15px]">{data.contact_page_visited ? 'Visited' : 'No'}</div>
          </div>
          {data.inferred_modules?.length > 0 && (
            <div className="col-span-2 sm:col-span-4 pb-card px-2.5 py-2">
              <div className="text-pb-faint text-[10.5px] uppercase tracking-wide mb-1">Analytics-derived product interest</div>
              <div className="flex flex-wrap gap-1">
                {data.inferred_modules.map(k => <Pill key={k} tone="accent">{moduleLabel(k)}</Pill>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export { Icon }
