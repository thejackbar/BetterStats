import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'
import { POSTS } from '../../data/blog'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function Blog() {
  usePageMeta({
    title: 'Blog — Cricket Stats Guides & Club Tips | BetterStats',
    description: 'Cricket statistics guides and club management tips from the BetterStats team — batting averages, bowling economy, historical data, and more.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/blog',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-3xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Stats guides & club tips</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Blog.</h1>
        <p className="text-pb-dim text-lg mb-12">Cricket statistics explained — for club players, captains, and committee members.</p>

        <div className="space-y-0">
          {POSTS.map((post, i) => (
            <Link
              key={post.slug}
              to={`/blog/${post.slug}`}
              className="block pb-hairline-t py-8 group"
            >
              <div className="grid md:grid-cols-[1fr_3fr] gap-6 items-start">
                <div>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">{formatDate(post.date)}</p>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest mt-0.5">{post.readTime}</p>
                </div>
                <div>
                  <h2 className="font-display font-bold text-[20px] md:text-[22px] text-pb-text leading-snug mb-2 group-hover:text-pb-accent transition-colors">
                    {post.title}
                  </h2>
                  <p className="text-pb-dim text-sm leading-relaxed">{post.description}</p>
                  <p className="mt-3 font-mono text-[10px] tracking-wide2 transition-colors" style={{ color: 'var(--pb-accent)' }}>
                    READ →
                  </p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
