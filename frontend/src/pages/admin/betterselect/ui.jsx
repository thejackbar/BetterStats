// BetterSelect atom kit — the small presentational primitives the redesigned
// module screens share (icons, avatars, status dots, chips, segmented control,
// search, availability summary, the quick-update modal). These were prototyped
// in docs/design_handoff_betterselect/prototype/bs-shared.jsx and are ported
// here to real components that read the pb-* theme tokens.
//
// Colours come from `cssVar` on AVAILABILITY (inline styles), not dynamically
// built Tailwind classes — Tailwind's JIT only sees literal class strings, so
// anything status-coloured uses the CSS variable directly.
import { useNavigate } from 'react-router-dom'
import { AVAILABILITY, AVAIL_STATUSES, AVAIL_ORDER, availRank } from '../../../lib/availability'

/* ── Icons — simple geometric line glyphs (stroke = currentColor) ────────── */
const ICON_PATHS = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  fixtures: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9h18M8 3v3M16 3v3" /></>,
  teams: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9" /></>,
  player: <><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></>,
  availability: <><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 4.5-5" /></>,
  selection: <><path d="M12 3l2.4 5.3L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-.7z" /></>,
  ladders: <><path d="M5 21V9M12 21V4M19 21v-8" /></>,
  votes: <><rect x="4" y="9.5" width="16" height="10.5" rx="2" /><path d="M8.5 13.5h7" /><path d="M12 2v5M9.5 4.5L12 7l2.5-2.5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>,
  filter: <><path d="M4 6h16M7 12h10M10 18h4" /></>,
  close: <><path d="M6 6l12 12M18 6L6 18" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  minus: <><path d="M5 12h14" /></>,
  grip: <><circle cx="9" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="6" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="12" r="1.1" fill="currentColor" stroke="none" /><circle cx="9" cy="18" r="1.1" fill="currentColor" stroke="none" /><circle cx="15" cy="18" r="1.1" fill="currentColor" stroke="none" /></>,
  chevron: <><path d="M9 6l6 6-6 6" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  check: <><path d="M5 12.5l4.5 4.5L19 7" /></>,
  share: <><circle cx="6" cy="12" r="2.4" /><circle cx="17" cy="6" r="2.4" /><circle cx="17" cy="18" r="2.4" /><path d="M8.1 11l6.8-3.9M8.1 13l6.8 3.9" /></>,
  bolt: <><path d="M13 3L5 13h6l-1 8 8-10h-6z" /></>,
  back: <><path d="M19 12H5M11 6l-6 6 6 6" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  money: <><rect x="2.5" y="6" width="19" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M6 9.5v5M18 9.5v5" /></>,
  list: <><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" /></>,
  nets: <><path d="M4 4v16M20 4v16M4 4h16M4 9h16M4 14h16M4 19h16M9 4v16M14 4v16" /></>,
  timer: <><circle cx="12" cy="13" r="8" /><path d="M12 13V9M9 2h6M12 5V2" /></>,
  play: <><path d="M7 5l12 7-12 7z" fill="currentColor" stroke="none" /></>,
  pause: <><rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none" /><rect x="13.5" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none" /></>,
  reset: <><path d="M3.5 12a8.5 8.5 0 1 1 2.5 6" /><path d="M3.5 20v-5h5" /></>,
  sound: <><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /></>,
  mute: <><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M22 9l-6 6M16 9l6 6" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M22 12h-3M5 12H2M19.1 4.9l-2.1 2.1M7 17l-2.1 2.1M19.1 19.1L17 17M7 7L4.9 4.9" /></>,
  next: <><path d="M5 5l9 7-9 7zM18 5v14" /></>,
  cols: <><rect x="3.5" y="4" width="7" height="16" rx="1.6" /><rect x="13.5" y="4" width="7" height="16" rx="1.6" /></>,
  sheet: <><rect x="4" y="3.5" width="16" height="17" rx="2" /><path d="M8 8.5h8M8 12h8M8 15.5h5" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4" /></>,
  moon: <><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></>,
  tv: <><rect x="2.5" y="5" width="19" height="13" rx="2" /><path d="M8 21h8M12 18v3" /></>,
}

export function Icon({ name, size = 18, strokeWidth = 1.6, className = '', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style} aria-hidden="true">
      {ICON_PATHS[name] || null}
    </svg>
  )
}

/* ── Player avatar — photo when present, else initials; keeper gets an amber ring ── */
function isKeeper(player) {
  return (player?.skill_positions || player?.roles || []).includes('WKT')
}
function playerName(player) {
  return player?.display_name || player?.name || '?'
}

export function Avatar({ player, size = 30, className = '', noLink = false }) {
  const navigate = useNavigate()
  const ring = isKeeper(player)
    ? 'color-mix(in srgb, var(--pb-amber) 55%, transparent)'
    : 'var(--pb-hairline2)'
  const common = {
    width: size, height: size, minWidth: size, borderRadius: '50%',
    border: `1.5px solid ${ring}`,
  }
  // Anywhere in BetterSelect, clicking a player's avatar opens their profile.
  // stopPropagation keeps it from also firing the surrounding card's click
  // (e.g. add-to-XI / select). noLink opts out (modals, headers).
  const linked = !noLink && player?.id
  const go = (e) => { e.stopPropagation(); navigate(`/admin/betterselect/players?player=${player.id}`) }
  const linkProps = linked
    ? { onClick: go, role: 'button', tabIndex: 0, title: `Open ${playerName(player)}'s profile`,
        onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(e) } },
        className: `cursor-pointer hover:brightness-110 hover:ring-2 hover:ring-pb-accent/40 transition` }
    : { className: '' }
  if (player?.photo_url) {
    return <img src={player.photo_url} alt="" {...linkProps}
      className={`object-cover bg-pb-surface2 ${linkProps.className} ${className}`} style={common} />
  }
  const initials = playerName(player).split(/[ ,]+/).filter(Boolean).slice(0, 2).map((s) => s[0]).join('').toUpperCase()
  return (
    <span {...linkProps}
      className={`inline-flex items-center justify-center bg-pb-surface2 text-pb-dim font-mono font-semibold ${linkProps.className} ${className}`}
      style={{ ...common, fontSize: Math.round(size * 0.34) }}>
      {initials}
    </span>
  )
}

/* ── Availability dot (NO_RESPONSE renders as a hollow ring) ─────────────── */
export function Dot({ status, size = 9, glow = false, className = '', style }) {
  const meta = AVAILABILITY[status] || AVAILABILITY.NO_RESPONSE
  const hollow = status === 'NO_RESPONSE'
  return (
    <span className={`inline-block rounded-full ${className}`} style={{
      width: size, height: size, minWidth: size,
      background: hollow ? 'transparent' : meta.cssVar,
      border: hollow ? `1.5px solid ${meta.cssVar}` : 'none',
      boxShadow: glow ? `0 0 0 3px color-mix(in srgb, ${meta.cssVar} 28%, transparent)` : 'none',
      ...style,
    }} />
  )
}

/* Clickable status dot — calls onEdit(player) (used to open QuickAvailModal). */
export function AvailDot({ player, status, onEdit, glow, size }) {
  const s = status ?? player?.availability ?? player?.avail ?? 'NO_RESPONSE'
  return (
    <span
      onClick={onEdit ? (e) => { e.stopPropagation(); onEdit(player) } : undefined}
      title={onEdit ? 'Update availability' : undefined}
      className={`inline-flex items-center -m-1 p-1 rounded-full ${onEdit ? 'cursor-pointer' : ''}`}>
      <Dot status={s} glow={glow} size={size} />
    </span>
  )
}

/* ── Role chips — mono BAT/BWL/ALL/WK tags (keeper = amber) ──────────────── */
const ROLE_SHORT = { BAT: 'BAT', BWL: 'BWL', ALL: 'ALL', WKT: 'WK' }

export function RoleChips({ roles, muted = false }) {
  const list = roles || []
  return (
    <span className="inline-flex gap-1">
      {list.map((r) => {
        const wk = r === 'WKT'
        return (
          <span key={r} className={`font-mono text-[9.5px] font-semibold tracking-wide px-1.5 py-0.5 rounded ${
            wk ? 'bg-pb-amber/10 text-pb-amber' : `bg-pb-surface2 ${muted ? 'text-pb-faint' : 'text-pb-dim'}`
          }`}>
            {ROLE_SHORT[r] || r}
          </span>
        )
      })}
    </span>
  )
}

/* ── Small mono pill (captain/keeper tags, status badges) ────────────────── */
const TAG_TONE = {
  accent: 'bg-pb-accent/15 text-pb-accent',
  amber: 'bg-pb-amber/15 text-pb-amber',
  red: 'bg-pb-red/15 text-pb-red',
  faint: 'bg-pb-surface2 text-pb-faint',
}
export function Tag({ children, tone = 'accent', className = '' }) {
  return (
    <span className={`inline-flex items-center font-mono text-[9.5px] font-bold tracking-wide2 px-1.5 py-0.5 rounded ${TAG_TONE[tone] || TAG_TONE.accent} ${className}`}>
      {children}
    </span>
  )
}

/* ── Buttons ─────────────────────────────────────────────────────────────
   A module-local button matching the prototype's variant set (primary / ghost
   / soft / danger). presskit's Btn uses a different boolean API and is kept for
   the rest of the app; this one is for the redesigned BetterSelect screens. */
const BTN_VARIANTS = {
  primary: 'bg-pb-accent text-[#08110b] font-semibold border border-transparent hover:opacity-90',
  ghost: 'bg-transparent text-pb-dim border border-pb-hairline2 hover:text-pb-text',
  soft: 'bg-pb-surface2 text-pb-text border border-pb-hairline hover:border-pb-hairline2',
  danger: 'bg-transparent text-pb-red border border-pb-red/40 hover:bg-pb-red/10',
}
export function Btn({ children, variant = 'ghost', sm = false, icon, onClick, disabled = false, type = 'button', className = '', title }) {
  const size = sm ? 'text-[12.5px] px-2.5 py-1.5 gap-1.5' : 'text-[13.5px] px-3.5 py-2 gap-2'
  return (
    <button type={type} onClick={disabled ? undefined : onClick} disabled={disabled} title={title}
      className={`inline-flex items-center justify-center rounded-lg font-display leading-none transition whitespace-nowrap disabled:opacity-40 disabled:cursor-default ${size} ${BTN_VARIANTS[variant] || BTN_VARIANTS.ghost} ${className}`}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}
    </button>
  )
}

/* ── Segmented control ───────────────────────────────────────────────────── */
export function Segmented({ options, value, onChange, sm = false }) {
  return (
    <div className="inline-flex flex-wrap p-[3px] gap-0.5 bg-pb-surface2 rounded-lg border border-pb-hairline">
      {options.map((o) => {
        const active = o.value === value
        return (
          <button key={o.value} type="button" onClick={() => onChange(o.value)}
            className={`rounded-md font-display font-semibold transition ${sm ? 'text-xs px-2.5 py-1' : 'text-[13px] px-3 py-1.5'} ${
              active ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-text'
            }`}>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* ── Search input ────────────────────────────────────────────────────────── */
export function Search({ value, onChange, placeholder = 'Search…', className = '' }) {
  return (
    <div className={`flex items-center gap-2 bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-pb-faint focus-within:border-pb-accent ${className}`}>
      <Icon name="search" size={16} />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="bg-transparent border-0 outline-none text-pb-text text-sm w-full placeholder:text-pb-faint" />
    </div>
  )
}

/* ── Toggle chip (filter pills) ──────────────────────────────────────────── */
export function Chip({ label, active = false, onClick, dot, className = '' }) {
  return (
    <button type="button" onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium transition whitespace-nowrap border ${
        active ? 'bg-pb-accent/12 text-pb-accent border-pb-accent/40' : 'bg-transparent text-pb-dim border-pb-hairline2 hover:text-pb-text'
      } ${className}`}>
      {dot && <span className="w-[7px] h-[7px] rounded-full" style={{ background: dot }} />}
      {label}
    </button>
  )
}

/* ── Empty-state line ────────────────────────────────────────────────────── */
export function Empty({ children, className = '' }) {
  return <div className={`text-pb-faint text-sm ${className}`}>{children}</div>
}

/* ── Player recency filter (shared, deliberately quiet) ──────────────────────
 * "Played within N years (by last appearance)". Used on every player list so
 * the long tail of historical-only players can be hidden — rendered as a small
 * subtle dropdown, never a prominent chip row. */
export const RECENCY_OPTIONS = [
  { value: 0, label: 'Played: any time' },
  { value: 1, label: 'Played ≤ 1 yr' },
  { value: 2, label: 'Played ≤ 2 yrs' },
  { value: 3, label: 'Played ≤ 3 yrs' },
  { value: 5, label: 'Played ≤ 5 yrs' },
  { value: 10, label: 'Played ≤ 10 yrs' },
]
export function playedWithinYears(lastPlayed, years) {
  if (!years) return true
  if (!lastPlayed) return true // never-played (e.g. a new manual add) — keep
  const cutoff = new Date(); cutoff.setFullYear(cutoff.getFullYear() - years)
  return new Date(lastPlayed + 'T00:00:00') >= cutoff
}
export function RecencySelect({ value, onChange, title = 'Hide players who haven’t played recently', className = '' }) {
  return (
    <select value={value} onChange={(e) => onChange(Number(e.target.value))} title={title}
      className={`bg-transparent text-[11.5px] rounded-md border px-1.5 py-1 focus:outline-none focus:border-pb-accent transition-colors ${
        value ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faint border-pb-hairline hover:text-pb-text'
      } ${className}`}>
      {RECENCY_OPTIONS.map((o) => <option key={o.value} value={o.value} className="bg-pb-surface text-pb-text">{o.label}</option>)}
    </select>
  )
}

/* ── Filters toggle + reveal panel (shared) ──────────────────────────────────
 * The quiet "Filters" affordance used across player lists: a small button that
 * shows an active-count badge, plus a panel container for the facet controls. */
export function FilterButton({ active, count = 0, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12.5px] transition-colors ${
        active || count ? 'border-pb-accent/50 text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'
      }`}>
      <Icon name="filter" size={14} />
      {count ? `Filters · ${count}` : 'Filters'}
    </button>
  )
}
export function FilterPanel({ children, className = '' }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-pb-hairline2 bg-pb-surface2/40 px-3 py-2 ${className}`}>
      {children}
    </div>
  )
}
export function FacetGroup({ label, children }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest">{label}</span>
      {children}
    </span>
  )
}


/* ── Availability summary — stacked bar + legend over a set of players ────── */
export function AvailSummary({ players, statusOf = (p) => p.availability ?? p.avail ?? 'NO_RESPONSE', compact = false, hideTotal = false, className = '' }) {
  const total = players.length
  const tally = AVAIL_ORDER.reduce((acc, s) => ({ ...acc, [s]: 0 }), {})
  players.forEach((p) => { const s = statusOf(p); tally[s] = (tally[s] || 0) + 1 })
  const segs = AVAIL_ORDER.filter((s) => tally[s] > 0)
  return (
    <div className={`flex flex-col ${compact ? 'gap-1.5' : 'gap-2'} ${className}`}>
      <div className={`flex ${compact ? 'h-1.5' : 'h-2'} rounded-full overflow-hidden bg-pb-surface2`}>
        {segs.map((s) => (
          <div key={s} title={`${tally[s]} ${AVAILABILITY[s].label.toLowerCase()}`} style={{
            flexGrow: tally[s],
            background: AVAILABILITY[s].cssVar,
            opacity: s === 'NO_RESPONSE' ? 0.5 : 1,
          }} />
        ))}
      </div>
      <div className={`flex flex-wrap ${compact ? 'gap-2.5' : 'gap-3.5'}`}>
        {AVAIL_ORDER.map((s) => (
          <span key={s} className={`inline-flex items-center gap-1.5 text-pb-dim ${compact ? 'text-[11px]' : 'text-xs'}`}>
            <Dot status={s} /> <b className="text-pb-text font-semibold pb-num">{tally[s]}</b>
            <span className="text-pb-faint">{AVAILABILITY[s].label.toLowerCase()}</span>
          </span>
        ))}
        {!hideTotal && <span className={`ml-auto text-pb-faint pb-num ${compact ? 'text-[11px]' : 'text-xs'}`}>{total} in squad</span>}
      </div>
    </div>
  )
}

/* ── Quick-update availability modal (presentational) ─────────────────────
   onPick(status) is called when a status is chosen; the caller persists it. */
export function QuickAvailModal({ player, dateLabel, current, onPick, onClose }) {
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[380px] max-w-full bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-center gap-3 px-[18px] py-4 border-b border-pb-hairline">
          {player && <Avatar player={player} size={38} noLink />}
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">
              Update availability{dateLabel ? ` · ${dateLabel}` : ''}
            </div>
            <div className="font-display font-bold text-[17px] mt-0.5 truncate">{player ? playerName(player) : 'Player'}</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1" aria-label="Close"><Icon name="close" size={18} /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-2.5">
          {AVAIL_ORDER.map((s) => {
            const meta = AVAILABILITY[s]
            const on = current === s
            return (
              <button key={s} type="button" onClick={() => onPick(s)}
                className="flex items-center gap-2.5 px-3.5 py-3 rounded-xl font-display font-semibold text-[14.5px] text-left transition"
                style={{
                  border: `1.5px solid ${on ? meta.cssVar : 'var(--pb-hairline2)'}`,
                  background: on ? `color-mix(in srgb, ${meta.cssVar} 12%, transparent)` : 'transparent',
                  color: on ? meta.cssVar : 'var(--pb-dim)',
                }}>
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full font-mono text-[13px] font-bold"
                  style={{
                    background: s === 'NO_RESPONSE' ? 'transparent' : meta.cssVar,
                    border: s === 'NO_RESPONSE' ? `1.5px solid ${meta.cssVar}` : 'none',
                    color: s === 'NO_RESPONSE' ? meta.cssVar : '#08110b',
                  }}>{meta.glyph}</span>
                {meta.label}
              </button>
            )
          })}
        </div>
        <div className="px-4 pb-4 flex items-center gap-1.5 text-[11.5px] text-pb-faint">
          <Icon name="info" size={13} /> Tap a status — saves instantly.
        </div>
      </div>
    </div>
  )
}

/* Sort helper: available-first, then by name. Re-exported for screen use. */
export function byAvailThenName(statusOf = (p) => p.availability ?? p.avail, nameOf = (p) => p.display_name || p.name || '') {
  return (a, b) => {
    const r = availRank(statusOf(a)) - availRank(statusOf(b))
    return r !== 0 ? r : nameOf(a).localeCompare(nameOf(b))
  }
}

export { AVAILABILITY, AVAIL_STATUSES, AVAIL_ORDER }
