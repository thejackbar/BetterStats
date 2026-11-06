import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { TRUST_CLUBS } from '../../data/trustedClubs'
import { api } from '../../lib/api'

// Full-width "Trusted by" logo marquee. Shared between the homepage
// (compact=false, the original size) and the Trial landing page (compact=true
// : smaller logos/text and lighter padding, just enough to build trust without
// competing with the search box above it).
//
// The list is the curated clubs first (data/trustedClubs.js), then every club
// that is paying for BetterStats, newest first, from GET /public/trusted-clubs.
// If that call fails the curated list is all there is, so the strip never goes
// empty. One request per page load, shared by every strip on the page.

let livePromise = null
function loadLiveClubs() {
  if (!livePromise) {
    livePromise = api.publicTrustedClubs()
      .then((d) => (Array.isArray(d?.clubs) ? d.clubs : []))
      .catch(() => [])
  }
  return livePromise
}

function mergeClubs(live) {
  const have = new Set(TRUST_CLUBS.map((c) => c.slug))
  return [...TRUST_CLUBS, ...live.filter((c) => c?.slug && c?.name && !have.has(c.slug))]
}

// A crest that fails to load falls back to initials, never a broken-image icon.
function StripLogo({ club, className }) {
  const [ok, setOk] = useState(true)
  if (!ok || !club.logo) {
    const initials = club.name.split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()
    return (
      <span aria-hidden="true" className={`${className} rounded-md border pb-hairline flex items-center justify-center text-[10px] font-mono text-pb-dim`}>
        {initials}
      </span>
    )
  }
  return <img src={club.logo} alt={club.name} className={`object-contain ${className}`} loading="lazy" onError={() => setOk(false)} />
}

export default function TrustedByStrip({ compact = false }) {
  const [clubs, setClubs] = useState(TRUST_CLUBS)
  useEffect(() => {
    let alive = true
    loadLiveClubs().then((live) => { if (alive && live.length) setClubs(mergeClubs(live)) })
    return () => { alive = false }
  }, [])
  // About 3.5 seconds per club, never faster than the original 28s loop, so a
  // longer list scrolls at the same pace instead of racing past.
  const seconds = Math.max(28, Math.round(clubs.length * 3.5))
  return (
    <section className={`px-4 sm:px-6 lg:px-10 border-y pb-hairline ${compact ? 'py-6' : 'py-12'}`}>
      <div className="max-w-[1200px] mx-auto flex flex-col sm:flex-row sm:items-center gap-x-10 gap-y-3">
        <p className={`font-mono uppercase tracking-wide3 font-medium shrink-0 text-pb-faint ${compact ? 'text-[10px]' : 'text-xs'}`}>
          Trusted by
        </p>
        <div className="logo-marquee">
          <div className="logo-marquee-track" style={{ animationDuration: `${seconds}s` }}>
            {[...clubs, ...clubs].map((c, i) => (
              <Link
                key={`${c.slug}-${i}`}
                to={`/${c.slug}`}
                className={`flex items-center gap-3 font-semibold text-pb-text/80 hover:text-accent transition-colors shrink-0 ${compact ? 'text-sm' : 'text-base'}`}
              >
                <StripLogo club={c} className={compact ? 'w-6 h-6' : 'w-9 h-9'} />
                {c.name}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
