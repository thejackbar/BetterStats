// Small presentational primitives shared across the redesigned BetterScout
// screens (Discover, Profile, Compare). Deliberately NOT the club-side
// betterselect/ui.jsx Avatar — that one links to a club player's own admin
// profile route and reads player.photo_url, neither of which apply to a
// ScoutedPlayer (no club route to link to, and — until the photo-upload
// piece lands — no photo field at all). Kept scout-local on purpose.

// Player identity colours, ported verbatim from
// frontend/src/pages/PlayerComparison.jsx so a player's colour means the
// same thing on the Compare screen there and here.
export const PLAYER_COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444']

export function initialsOf(name) {
  return (name || '?')
    .split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase() || '?'
}

// Circular avatar — photo when the player carries one (a real BetterCricket
// player photo, once the internal link / upload path supplies it), else
// initials on a dashed ring so "no photo in CA data" reads as a reserved
// frame, not a broken image.
export function PlayerAvatar({ name, photoUrl, size = 32, ringColor, dashed = false, className = '' }) {
  const common = {
    width: size, height: size, minWidth: size, borderRadius: '50%',
    border: `1.5px solid ${ringColor || 'var(--pb-hairline2)'}`,
    borderStyle: dashed && !photoUrl ? 'dashed' : 'solid',
  }
  if (photoUrl) {
    return <img src={photoUrl} alt="" className={`object-cover bg-pb-surface2 shrink-0 ${className}`} style={common} />
  }
  return (
    <span
      className={`inline-flex items-center justify-center bg-pb-surface2 text-pb-dim font-mono font-semibold shrink-0 ${className}`}
      style={{ ...common, fontSize: Math.round(size * 0.34) }}
    >
      {initialsOf(name)}
    </span>
  )
}

// Returns 'best' | 'worst' | null per value — ported from
// frontend/src/pages/PlayerComparison.jsx's getRowHighlights so Compare
// means the same thing here as it does club-side. Only a UNIQUE best/worst
// is marked; a tie gets neither.
export function getRowHighlights(values, higher) {
  const nums = values.map((v) => {
    const n = parseFloat(v)
    return isNaN(n) ? null : n
  })
  const valid = nums.filter((n) => n !== null)
  if (valid.length < 2) return values.map(() => null)

  const best = higher ? Math.max(...valid) : Math.min(...valid)
  const worst = higher ? Math.min(...valid) : Math.max(...valid)
  if (best === worst) return values.map(() => null)

  const bestCount = valid.filter((n) => n === best).length
  const worstCount = valid.filter((n) => n === worst).length

  return nums.map((n) => {
    if (n === null) return null
    if (n === best && bestCount === 1) return 'best'
    if (n === worst && worstCount === 1) return 'worst'
    return null
  })
}

// 5-bar sparkline of a metric across a player's last 5 seasons (oldest to
// newest, left to right) — bars outside the active career-window fall back
// to the dim hairline colour per the design spec ("grey bars fall outside
// the chosen window"), the second-newest is --pb-dim, the newest two are
// the accent.
export function Sparkline({ seasons, metricKey, activeYears, width = 7, gap = 3, height = 34 }) {
  const bySeason = [...(seasons || [])].sort((a, b) => a.year - b.year).slice(-5)
  if (bySeason.length === 0) return <span className="text-pb-faintest text-xs">—</span>
  const values = bySeason.map((s) => s[metricKey])
  const max = Math.max(1, ...values.filter((v) => typeof v === 'number'))
  return (
    <div className="flex items-end" style={{ gap, height }}>
      {bySeason.map((s, i) => {
        const v = s[metricKey] || 0
        const h = Math.max(2, Math.round((v / max) * height))
        const inWindow = !activeYears || activeYears.has(s.year)
        const idxFromEnd = bySeason.length - 1 - i
        const color = !inWindow
          ? 'var(--pb-hairline2)'
          : idxFromEnd <= 1 ? 'var(--pb-accent)' : 'var(--pb-dim)'
        return (
          <span key={s.year} title={`${s.year}: ${v}`}
            style={{ width, height: h, background: color, borderRadius: 2, opacity: inWindow ? 1 : 0.55 }} />
        )
      })}
    </div>
  )
}
