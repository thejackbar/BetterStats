// BetterFantasyCricket — app chrome shared across screens: the club header with
// the FPL gradient rule, the nav pills, per-screen titles, the photo-led player
// row, and the message banner.
import {
  Aurora, GradientRule, Crest, Avatar, DISP, cardSx, tintBg, mix,
  RED, GREEN, AMBER, useFantasy, cx,
} from './ui'

// The club header on My Team (crest + name + season, search + manager chip),
// with a soft aurora behind it and the gradient rule under it.
export function AppHeader({ season, manager, onSearch, onBell, onProfile, unread = 0 }) {
  const { club } = useFantasy()
  const seasonName = season?.name || 'Fantasy'
  const mInitials = manager ? (manager.display_name || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase() : '?'
  return (
    <div style={{ position: 'relative', overflow: 'hidden', padding: '6px 0 0' }}>
      <Aurora style={{ inset: '-60% -30% auto', height: '200%' }} blur={46} />
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
          <Crest size={38} />
          <div style={{ lineHeight: 1 }}>
            <div style={{ font: `800 17px ${DISP}`, letterSpacing: '.02em', textTransform: 'uppercase', color: 'var(--text)' }}>{club?.name || 'Fantasy Cricket'}</div>
            <div style={{ font: `600 9px 'Hanken Grotesk'`, letterSpacing: '.2em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 3 }}>{seasonName}</div>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 9 }}>
            <button onClick={onBell} aria-label="Notifications" style={{
              position: 'relative', width: 30, height: 30, borderRadius: '50%', cursor: 'pointer',
              background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `600 13px 'Hanken Grotesk'`,
            }}>
              {'◉'}
              {unread > 0 && <span style={{ position: 'absolute', top: -3, right: -3, minWidth: 15, height: 15, padding: '0 3px', borderRadius: 8, background: RED, color: '#fff', font: `800 9px ${DISP}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{unread}</span>}
            </button>
            <button onClick={onSearch} aria-label="Search players" style={{
              width: 30, height: 30, borderRadius: '50%', cursor: 'pointer',
              background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `600 13px 'Hanken Grotesk'`,
            }}>⌕</button>
            <button onClick={onProfile} aria-label="Profile & settings" style={{
              width: 30, height: 30, borderRadius: '50%', cursor: 'pointer',
              background: tintBg(18, 'var(--surface)'), border: 'none', color: 'var(--accent-strong)', font: `700 12px 'Hanken Grotesk'`,
            }}>{mInitials}</button>
          </div>
        </div>
        <GradientRule />
      </div>
    </div>
  )
}

export function NavPills({ items, value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6, padding: '12px 0 4px', overflowX: 'auto', scrollbarWidth: 'none' }}>
      {items.map(([k, label]) => {
        const on = value === k
        return (
          <button key={k} onClick={() => onChange(k)} style={{
            padding: '7px 13px', borderRadius: 9, border: 'none', cursor: 'pointer', whiteSpace: 'nowrap',
            font: `${on ? 700 : 600} 12.5px 'Hanken Grotesk'`,
            background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)',
          }}>{label}</button>
        )
      })}
    </div>
  )
}

// A simple title header for the inner screens (gradient-top wash + Saira title +
// the gradient rule). `back` shows a chevron; `right` is an optional slot.
export function ScreenTitle({ title, sub, right, back, onBack }) {
  return (
    <div style={{ padding: '10px 0 0', background: 'linear-gradient(180deg,var(--grad-top),var(--bg))', borderRadius: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {back && (
          <button onClick={onBack} aria-label="Back" style={{
            width: 30, height: 30, borderRadius: '50%', cursor: 'pointer', flex: 'none',
            background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `700 16px 'Hanken Grotesk'`,
          }}>{'‹'}</button>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ font: `800 18px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{title}</div>
          {sub && <div style={{ font: `600 9px 'Hanken Grotesk'`, letterSpacing: '.2em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 3 }}>{sub}</div>}
        </div>
        {right}
      </div>
      <GradientRule />
    </div>
  )
}

export function SectionLabel({ children, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 2px 7px' }}>
      <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)' }}>{children}</span>
      {right}
    </div>
  )
}

// The reusable photo-led player row used everywhere. `right` is the trailing
// content (a big points number, a +/✓ control, a price…). `tone`:
// 'plain' | 'picked' (accent tint) | 'bench' (dashed, dimmed).
export function PlayerRow({ name, sub, photoUrl, badge, right, onClick, tone = 'plain', avatarSize = 38 }) {
  const picked = tone === 'picked'
  const bench = tone === 'bench'
  const sx = {
    display: 'flex', alignItems: 'center', gap: 11, padding: '9px 11px', borderRadius: 13,
    width: '100%', textAlign: 'left', cursor: onClick ? 'pointer' : 'default',
    ...(bench
      ? { background: 'var(--bench)', border: '1px dashed var(--hairline)', opacity: 0.6 }
      : picked
        ? { background: tintBg(12, 'var(--bg)'), border: `1px solid ${tintBg(34)}` }
        : { ...cardSx }),
  }
  const El = onClick ? 'button' : 'div'
  return (
    <El onClick={onClick} style={sx}>
      <Avatar name={name} photoUrl={photoUrl} size={avatarSize} dim={bench} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ font: `700 13.5px 'Hanken Grotesk'`, color: bench ? 'var(--dim)' : 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
          {badge}
        </div>
        {sub != null && <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 2 }}>{sub}</div>}
      </div>
      {right}
    </El>
  )
}

// Big trailing points number for a player row.
export function RowPoints({ value, color = 'var(--text)', label = 'pts' }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ font: `700 17px ${DISP}`, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{value}</div>
      <div style={{ font: `600 8px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 3 }}>{label}</div>
    </div>
  )
}

export function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? RED : tone === 'ok' ? GREEN : AMBER
  return (
    <div style={{
      borderRadius: 10, padding: '9px 12px', margin: '0 0 12px', font: `600 12px 'Hanken Grotesk'`,
      background: mix(color, 12), color, border: `1px solid ${mix(color, 30)}`,
    }}>{children}</div>
  )
}

export { cx }
