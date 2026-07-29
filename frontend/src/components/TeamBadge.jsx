// A team's crest, with an initials fallback.
//
// Club logos come from whatever upstream holds them (our own uploaded org logo,
// or Cricket Australia's CDN for an opposition club), so a hotlinked URL can
// 404 at any time — hence the onError fallback rather than a bare <img>.
// Extracted from MatchScorecard so the scorecard and the Lineups page render
// the same badge.
import { useState } from 'react'

export default function TeamBadge({ name, logoUrl, size = 36 }) {
  const [failed, setFailed] = useState(false)
  const initials = (name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()
  if (logoUrl && !failed) {
    return (
      <img
        src={logoUrl}
        alt=""
        onError={() => setFailed(true)}
        className="shrink-0 rounded-lg object-contain bg-pb-surface2"
        style={{ width: size, height: size }}
      />
    )
  }
  return (
    <div
      className="shrink-0 rounded-lg grid place-items-center font-display font-bold tracking-tight"
      style={{
        width: size, height: size, fontSize: Math.round(size * 0.36),
        background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)',
      }}
    >
      {initials}
    </div>
  )
}
