import { useParams, Link } from 'react-router-dom'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { RichText } from '../../components/website/RichTextEditor'
import { NewsCard, WebsiteHero } from '../../components/website/parts'
import { usePageMeta } from '../../hooks/usePageMeta'

const EXPLORE = [
  { key: 'players', label: 'Players', desc: 'Squads & profiles', to: (s) => `/${s}/players` },
  { key: 'records', label: 'Records', desc: 'All-time club records', to: (s) => `/${s}/records` },
  { key: 'games', label: 'Results', desc: 'Match results & scorecards', to: (s) => `/${s}/games` },
  { key: 'yearbook', label: 'Yearbooks', desc: 'Season by season', to: (s) => `/${s}/yearbook` },
]

function Section({ title, action, children }) {
  return (
    <section className="max-w-5xl mx-auto px-4 py-10">
      <div className="flex items-end justify-between mb-5">
        <h2 className="font-display font-bold text-xl text-pb-text">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function HomeBody({ slug }) {
  const { club, site } = useWebsite()
  usePageMeta({
    title: `${site.name}. Official Club Website`,
    description: site.tagline || `News, history, teams and stats for ${site.name}.`,
    image: site.hero_image_url || club?.logo_url || null,
    url: `https://betterat.cricket/${slug}/website`,
  })

  const news = site.news || []
  const sections = site.sections || {}

  return (
    <div>
      <WebsiteHero site={site} club={club} />

      {site.intro && (
        <section className="max-w-3xl mx-auto px-4 py-10">
          <RichText html={site.intro} className="text-base" />
        </section>
      )}

      {news.length > 0 && (
        <Section
          title="Latest News"
          action={sections.news && (
            <Link to={`/${slug}/website/news`} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-accent">
              ALL NEWS →
            </Link>
          )}
        >
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {news.slice(0, 6).map(a => <NewsCard key={a.id} slug={slug} article={a} />)}
          </div>
        </Section>
      )}

      {/* Quick links into the cricket data + extra website sections */}
      <Section title="Explore the Club">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {EXPLORE.map(card => (
            <Link
              key={card.key}
              to={card.to(slug)}
              className="rounded-xl border pb-hairline bg-pb-surface p-5 hover:border-pb-accent transition-colors group"
            >
              <div className="font-display font-bold text-pb-text group-hover:text-pb-accent transition-colors">{card.label}</div>
              <div className="text-[12px] text-pb-faint mt-1">{card.desc}</div>
            </Link>
          ))}
          {sections.honours && (
            <Link to={`/${slug}/website/honours`} className="rounded-xl border pb-hairline bg-pb-surface p-5 hover:border-pb-accent transition-colors group">
              <div className="font-display font-bold text-pb-text group-hover:text-pb-accent transition-colors">Honours</div>
              <div className="text-[12px] text-pb-faint mt-1">Life members & hall of fame</div>
            </Link>
          )}
          {sections.committee && (
            <Link to={`/${slug}/website/committee`} className="rounded-xl border pb-hairline bg-pb-surface p-5 hover:border-pb-accent transition-colors group">
              <div className="font-display font-bold text-pb-text group-hover:text-pb-accent transition-colors">Committee</div>
              <div className="text-[12px] text-pb-faint mt-1">Who runs the club</div>
            </Link>
          )}
          {sections.gallery && (
            <Link to={`/${slug}/website/gallery`} className="rounded-xl border pb-hairline bg-pb-surface p-5 hover:border-pb-accent transition-colors group">
              <div className="font-display font-bold text-pb-text group-hover:text-pb-accent transition-colors">Gallery</div>
              <div className="text-[12px] text-pb-faint mt-1">Photos from around the club</div>
            </Link>
          )}
        </div>
      </Section>
    </div>
  )
}

export default function WebsiteHome() {
  const { clubSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="home">
      <HomeBody slug={clubSlug} />
    </WebsiteChrome>
  )
}
