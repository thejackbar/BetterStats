// Shared building blocks for the public club website.
import { Link } from 'react-router-dom'

export function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

// A news teaser card (homepage + news index).
export function NewsCard({ slug, article }) {
  return (
    <Link
      to={`/${slug}/website/news/${article.slug}`}
      className="group block rounded-xl overflow-hidden border pb-hairline bg-pb-surface hover:border-pb-accent transition-colors"
    >
      <div className="aspect-[16/9] bg-pb-surface2 overflow-hidden">
        {article.cover_image_url ? (
          <img
            src={article.cover_image_url}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-pb-faintest font-mono text-[11px]">
            {article.is_pinned ? '📌 PINNED' : 'NEWS'}
          </div>
        )}
      </div>
      <div className="p-4">
        <div className="flex items-center gap-2 mb-1">
          {article.is_pinned && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-pb-accent/15 text-pb-accent">PINNED</span>
          )}
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">{formatDate(article.published_at)}</span>
        </div>
        <h3 className="font-display font-bold text-pb-text leading-snug group-hover:text-pb-accent transition-colors">
          {article.title}
        </h3>
        {article.summary && (
          <p className="mt-1.5 text-[13px] text-pb-dim line-clamp-2">{article.summary}</p>
        )}
        {article.author && (
          <p className="mt-2 font-mono text-[10px] text-pb-faintest">By {article.author}</p>
        )}
      </div>
    </Link>
  )
}

// Page hero — uses the club's hero image when present, else a clean banner.
export function WebsiteHero({ site, club }) {
  const hero = site.hero_image_url
  return (
    <div className="relative overflow-hidden">
      {hero ? (
        <>
          <img src={hero} alt="" className="w-full aspect-[8/3] object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
        </>
      ) : (
        <div className="h-[30vh] min-h-[200px]" style={{ background: 'linear-gradient(135deg, color-mix(in srgb, var(--pb-accent) 22%, var(--pb-bg)), var(--pb-bg))' }} />
      )}
      <div className={`${hero ? 'absolute bottom-0 left-0 right-0' : 'absolute inset-0 flex items-center'}`}>
        <div className="max-w-5xl mx-auto px-4 pb-8 w-full">
          <div className="flex items-center gap-4">
            {club?.logo_url && (
              <img src={club.logo_url} alt="" className="w-16 h-16 rounded-lg object-contain bg-white/10 p-1 shrink-0" />
            )}
            <div>
              <h1 className={`font-display font-extrabold text-3xl sm:text-4xl leading-tight ${hero ? 'text-white' : 'text-pb-text'}`}>
                {site.name}
              </h1>
              {site.tagline && (
                <p className={`mt-1 text-sm sm:text-base ${hero ? 'text-white/80' : 'text-pb-dim'}`}>{site.tagline}</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
