import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../lib/api'

const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab', 'yearbook', 'yearbooks', 'games', 'website']
// Single-segment paths that are NOT club slugs (must stay in sync with App.jsx routes)
const RESERVED_ROOT_SEGMENTS = new Set([
  'login', 'admin', 'onboard', 'club-inactive',
  'games', 'match', 'scorecards', 'players',
  'features', 'pricing', 'compare', 'about', 'contact', 'faq',
  'terms', 'privacy', 'blog',
])

function useSlug() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0]
  }
  if (segments.length === 1 && !RESERVED_ROOT_SEGMENTS.has(segments[0])) {
    return segments[0]
  }
  return null
}

export default function SponsorFooter() {
  const slug = useSlug()
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!slug) { setData(null); return }
    api.getClubSponsors(slug).then(setData).catch(() => setData(null))
  }, [slug])

  if (!data || !data.sponsors || data.sponsors.length === 0) return null

  const { club_name, current_season, sponsors } = data
  // Cap at 6
  const visible = sponsors.slice(0, 6)

  return (
    <footer className="sticky bottom-0 z-40 bg-pb-surface pb-hairline-t">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
        <div className="flex items-center h-10 gap-4">
          {/* Left label */}
          <span className="shrink-0 font-mono text-[10px] tracking-wide2 text-pb-faint whitespace-nowrap">
            {club_name}{current_season ? ` · ${current_season}` : ''} Sponsors
          </span>

          {/* Divider */}
          <span className="shrink-0 text-pb-faintest text-[10px]">·</span>

          {/* Sponsor logos — evenly distributed */}
          <div className="flex-1 flex items-center justify-evenly gap-3 min-w-0 overflow-hidden">
            {visible.map((sponsor) => (
              <a
                key={sponsor.id}
                href={sponsor.website_url || '#'}
                target={sponsor.website_url ? '_blank' : undefined}
                rel="noopener noreferrer"
                title={sponsor.name}
                className="flex items-center justify-center h-7 shrink-0 opacity-75 hover:opacity-100 transition-opacity"
              >
                <img
                  src={sponsor.logo_url}
                  alt={sponsor.name}
                  className="max-h-7 max-w-[100px] object-contain"
                  loading="lazy"
                />
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}
