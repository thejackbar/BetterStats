import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useClubSponsors, forSpot } from '../lib/useClubSponsors'
import { readClubSlug, onClubSlugChange } from '../lib/clubSlug'

const CLUB_SECTIONS = [
  'dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab', 'competitions',
  'yearbook', 'yearbooks', 'games', 'fixtures', 'lineups', 'teams', 'premierships',
  'honour-board', 'ladders', 'website',
]
// Single-segment paths that are NOT club slugs (must stay in sync with App.jsx routes)
const RESERVED_ROOT_SEGMENTS = new Set([
  'login', 'admin', 'onboard', 'club-inactive',
  'games', 'match', 'scorecards', 'players',
  'features', 'pricing', 'compare', 'about', 'contact', 'faq',
  'terms', 'privacy', 'blog', 'videos', 'trial', 'demo',
])
// Pages that belong to a club but carry no slug in the URL (/players/:id,
// /games/:id). The page that loaded the player or game says which club it is.
const SLUGLESS_CLUB_PAGES = new Set(['players', 'games', 'match', 'scorecards'])

function useSlug() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  const [remembered, setRemembered] = useState(() => readClubSlug())
  useEffect(() => onClubSlugChange(setRemembered), [])
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0]
  }
  if (segments.length === 1 && !RESERVED_ROOT_SEGMENTS.has(segments[0])) {
    return segments[0]
  }
  if (segments.length >= 2 && SLUGLESS_CLUB_PAGES.has(segments[0])) {
    return remembered
  }
  return null
}

// How big each tier draws in the full list. Logos scale by tier so a major
// partner reads as one. A sponsor with no logo is named in text at the same rank.
const TIER_LOGO = {
  major: { h: 'max-h-16', w: 'max-w-[260px]', text: 'text-xl font-semibold' },
  gold: { h: 'max-h-12', w: 'max-w-[200px]', text: 'text-lg font-semibold' },
  silver: { h: 'max-h-9', w: 'max-w-[150px]', text: 'text-sm font-medium' },
  supporter: { h: 'max-h-6', w: 'max-w-[110px]', text: 'text-xs' },
}
const TIER_ORDER = ['major', 'gold', 'silver', 'supporter']

function SponsorMark({ sponsor, tier }) {
  const size = TIER_LOGO[tier] || TIER_LOGO.silver
  const inner = sponsor.logo_url ? (
    <img
      src={sponsor.logo_url}
      alt={sponsor.name}
      className={`${size.h} ${size.w} object-contain`}
      loading="lazy"
    />
  ) : (
    <span className={`${size.text} text-pb-dim`}>{sponsor.name}</span>
  )
  return sponsor.website_url ? (
    <a
      href={sponsor.website_url}
      target="_blank"
      rel="noopener noreferrer"
      title={sponsor.name}
      className="flex items-center justify-center opacity-80 hover:opacity-100 transition-opacity"
    >
      {inner}
    </a>
  ) : (
    <span title={sponsor.name} className="flex items-center justify-center opacity-80">{inner}</span>
  )
}

// Every sponsor the club lists, grouped by tier, at the very bottom of the page.
export function SponsorWall({ data }) {
  const all = forSpot(data, 'footer')
  if (all.length === 0) return null
  const labels = data.tier_labels || {}
  const groups = TIER_ORDER
    .map((tier) => ({ tier, list: all.filter((s) => (s.tier || 'silver') === tier) }))
    .filter((g) => g.list.length > 0)
  return (
    <section aria-label="Club sponsors" className="bg-pb-bg pb-hairline-t mt-8">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="font-mono text-[10px] tracking-wide2 text-pb-faint text-center uppercase">
          {data.club_name}{data.current_season ? ` · ${data.current_season}` : ''} Sponsors
        </div>
        {groups.map(({ tier, list }) => (
          <div key={tier}>
            <div className="font-mono text-[9px] tracking-wide2 text-pb-faintest text-center uppercase mb-3">
              {labels[tier] || tier}
            </div>
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
              {list.map((s) => <SponsorMark key={s.id} sponsor={s} tier={tier} />)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function SponsorFooter() {
  const slug = useSlug()
  const data = useClubSponsors(slug)

  if (!data) return null

  const { club_name, current_season } = data
  // Cap the bar at 6; tier order puts the biggest partners first.
  const visible = forSpot(data, 'bar').slice(0, 6)

  return (
    <>
      <SponsorWall data={data} />
      {visible.length > 0 && (
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
      )}
    </>
  )
}
