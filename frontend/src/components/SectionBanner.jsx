import { useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useSectionNames, PATH_SEGMENT_TO_KEY } from '../lib/sectionNames'
import { readClubSlug, onClubSlugChange } from '../lib/clubSlug'

// A slim "Presented by" strip under the nav on a section whose name the club has
// linked to a sponsor. It sits in one place for every section, keyed off the URL,
// so a page does not need to know about it. Draws nothing when no sponsor is
// linked to the section being viewed.
const SLUGLESS = new Set(['players'])

function useSectionKey() {
  const { pathname } = useLocation()
  const [remembered, setRemembered] = useState(() => readClubSlug())
  useEffect(() => onClubSlugChange(setRemembered), [])
  const seg = pathname.split('/').filter(Boolean)
  if (seg.length === 2 && SLUGLESS.has(seg[0]) && seg[1] !== 'share') {
    // /players/:id is a player profile, which carries no club slug in the URL.
    return { slug: remembered, key: 'player_profile' }
  }
  if (seg.length >= 2 && PATH_SEGMENT_TO_KEY[seg[1]]) {
    return { slug: seg[0], key: PATH_SEGMENT_TO_KEY[seg[1]] }
  }
  return { slug: null, key: null }
}

export default function SectionBanner() {
  const { slug, key } = useSectionKey()
  const sec = useSectionNames(slug)
  const sponsor = key ? sec.sponsor(key) : null
  if (!sponsor || !sponsor.logo_url) return null
  const label = sec.name(key)
  const logo = (
    <img src={sponsor.logo_url} alt={sponsor.name} className="max-h-7 max-w-[140px] object-contain" />
  )
  return (
    <div className="bg-pb-surface pb-hairline-b" data-testid="section-banner">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-1.5 flex items-center justify-center gap-3 min-w-0">
        {label && <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase truncate">{label}</span>}
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase shrink-0">Presented by</span>
        {sponsor.website_url ? (
          <a href={sponsor.website_url} target="_blank" rel="noopener noreferrer" title={sponsor.name} className="shrink-0">{logo}</a>
        ) : logo}
      </div>
    </div>
  )
}
