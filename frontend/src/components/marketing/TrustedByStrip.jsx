import { Link } from 'react-router-dom'
import { TRUST_CLUBS } from '../../data/trustedClubs'

// Full-width "Trusted by clubs at" logo marquee. Shared between the homepage
// (compact=false, the original size) and the Trial landing page (compact=true
// — smaller logos/text and lighter padding, just enough to build trust without
// competing with the search box above it).
export default function TrustedByStrip({ compact = false }) {
  return (
    <section className={`px-4 sm:px-6 lg:px-10 border-y pb-hairline ${compact ? 'py-6' : 'py-12'}`}>
      <div className="max-w-[1200px] mx-auto flex flex-col sm:flex-row sm:items-center gap-x-10 gap-y-3">
        <p className={`font-mono uppercase tracking-wide3 font-medium shrink-0 text-pb-faint ${compact ? 'text-[10px]' : 'text-xs'}`}>
          Trusted by clubs at
        </p>
        <div className="logo-marquee">
          <div className="logo-marquee-track">
            {[...TRUST_CLUBS, ...TRUST_CLUBS].map((c, i) => (
              <Link
                key={`${c.slug}-${i}`}
                to={`/${c.slug}`}
                className={`flex items-center gap-3 font-semibold text-pb-text/80 hover:text-accent transition-colors shrink-0 ${compact ? 'text-sm' : 'text-base'}`}
              >
                <img
                  src={c.logo}
                  alt={c.name}
                  className={`object-contain ${compact ? 'w-6 h-6' : 'w-9 h-9'}`}
                  loading="lazy"
                />
                {c.name}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
