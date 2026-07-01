import { Link } from 'react-router-dom'
import MarketingFooter from '../components/marketing/MarketingFooter'
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
 *    who typed their own club's name hoping to find it, the moment to pitch
 *    getting them online.
 * Styled like the marketing hero so it reads as a proper landing page, not an
 * error screen, and pushes to the onboarding form + the marketing site.
 */
export default function ClubInactive({ variant = 'inactive', slug, clubName }) {
  const isNotFound = variant === 'notfound'
  const name = clubName || prettyName(slug)
  const contactHref = name ? `/contact?club=${encodeURIComponent(name)}` : '/contact'

  const pill = isNotFound ? `Not on ${BRAND} yet` : 'Club page paused'
  const lead = isNotFound
    ? (name ? `No page for ${name}` : `Not on ${BRAND}`)
    : 'This club page is'
  const gradientWord = isNotFound ? 'yet.' : 'paused.'

  const body = isNotFound
    ? `We couldn't find this club on ${BRAND}. If it's yours, get its full playing history online, from your own match data and synced automatically every week.`
    : `This club isn't showing on ${BRAND} right now. If you help run it, get in touch to bring it back. Or see what ${BRAND} can do for your club.`

  const primaryLabel = isNotFound ? 'Get your club online' : 'Get in touch'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex flex-col">
      <section className="relative flex-1 flex items-center overflow-hidden px-4 sm:px-6 lg:px-10 pt-28 pb-24">
        <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />

        <div className="max-w-[820px] mx-auto relative z-10 text-center">
          <p className="pill mb-7 inline-flex"><span className="dot" />{pill}</p>

          <h1 className="font-display font-bold text-[40px] sm:text-[58px] lg:text-[68px] tracking-tight leading-[0.95] mb-6">
            {lead} <span className="gradient-text">{gradientWord}</span>
          </h1>

          <p className="text-lg text-pb-dim leading-relaxed mb-9 max-w-xl mx-auto">
            {body}
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-7">
            <Link to={contactHref} className="cta-primary">
              {primaryLabel}
              <span aria-hidden>→</span>
            </Link>
            <Link to="/" className="cta-secondary">Explore {BRAND}</Link>
          </div>

          {isNotFound && (
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-pb-faint">
              <span className="flex items-center gap-2"><span className="tick">✓</span>Live in under an hour</span>
              <span className="flex items-center gap-2"><span className="tick">✓</span>Synced automatically every week</span>
            </div>
          )}
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
