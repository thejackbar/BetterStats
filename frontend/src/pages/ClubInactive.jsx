import { Link } from 'react-router-dom'
import { BRAND } from '../data/marketing'

// Turn a URL slug into a readable club name to pre-fill the onboarding form,
// e.g. 'high-wycombe' -> 'High Wycombe'. It's only a starting point; the
// visitor can correct it on the form.
function prettyName(slug) {
  if (!slug) return ''
  return slug
    .replace(/[-_]+/g, ' ')
    .trim()
    .replace(/\b\w/g, c => c.toUpperCase())
}

/**
 * Shown when a public club page can't be displayed. Two variants:
 *  - 'inactive' (403): the club is on BetterCricket but its page is paused.
 *  - 'notfound' (404): the slug doesn't match any club. This is the visitor
 *    who typed their own club's name hoping to find it — the moment to pitch
 *    getting them online.
 * Both push to the onboarding form and the marketing site.
 */
export default function ClubInactive({ variant = 'inactive', slug, clubName }) {
  const isNotFound = variant === 'notfound'
  const name = clubName || prettyName(slug)
  const contactHref = name ? `/contact?club=${encodeURIComponent(name)}` : '/contact'

  const heading = isNotFound
    ? `No club page${name ? ` for ${name}` : ''} yet`
    : 'This club page is paused'

  const body = isNotFound
    ? `We couldn't find this club on ${BRAND}. If it's your club, you can put its full stats, records and history online, synced automatically every week.`
    : `This club isn't showing on ${BRAND} right now. If you help run it, get in touch to bring it back. Or see what ${BRAND} can do for your club.`

  const primaryLabel = isNotFound ? 'Get your club online →' : 'Get in touch →'

  return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <div className="w-12 h-12 rounded-full bg-pb-surface2 border pb-hairline flex items-center justify-center mx-auto mb-6">
          <svg className="w-6 h-6 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {isNotFound ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-4.35-4.35M11 18a7 7 0 110-14 7 7 0 010 14z" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            )}
          </svg>
        </div>

        <h1 className="font-display font-bold text-2xl text-pb-text mb-3 tracking-tight">{heading}</h1>
        <p className="text-pb-dim leading-relaxed">{body}</p>

        <div className="mt-8 flex flex-col items-center gap-4">
          <Link
            to={contactHref}
            className="inline-block font-mono text-[12px] tracking-wide2 px-5 py-3 rounded text-[#08110b] hover:opacity-90 transition"
            style={{ background: 'var(--pb-accent)' }}
          >
            {primaryLabel}
          </Link>
          <Link to="/" className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
            Explore {BRAND} →
          </Link>
        </div>
      </div>
    </div>
  )
}
