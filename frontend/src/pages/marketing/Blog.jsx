import { useState } from 'react'
import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'
import { POSTS } from '../../data/blog'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
}

function PostThumb({ src, title }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return null
  return (
    <div className="hidden sm:block flex-shrink-0 w-28 h-20 rounded-lg overflow-hidden border pb-hairline">
      <img
        src={src}
        alt={title}
        className="w-full h-full object-cover object-top"
        onError={() => setFailed(true)}
        loading="lazy"
      />
    </div>
  )
}

export default function Blog() {
  usePageMeta({
    title: 'Blog — Cricket Stats Guides & Club Tips | Better Cricket',
    description: 'Cricket statistics guides and club management tips from the Better Cricket team — batting averages, bowling economy, historical data, and more.',
    image: 'https://betterat.cricket/og-image.png',
    url: 'https://betterat.cricket/blog',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Stats guides & club tips</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Blog.</h1>
        <p className="text-pb-dim text-lg mb-12">Cricket statistics explained — for club players, captains, and committee members.</p>

        <div className="space-y-0">
          {POSTS.map((post) => (
            <Link
              key={post.slug}
              to={`/blog/${post.slug}`}
              className="flex items-start gap-5 pb-hairline-t py-7 group"
            >
              <PostThumb src={post.image} title={post.title} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-4 mb-2">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">{formatDate(post.date)}</p>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest">{post.readTime}</p>
                </div>
                <h2 className="font-display font-bold text-[18px] md:text-[20px] text-pb-text leading-snug mb-1.5 group-hover:text-accent transition-colors">
                  {post.title}
                </h2>
                <p className="text-pb-dim text-sm leading-relaxed line-clamp-2">{post.description}</p>
                <p className="mt-2.5 font-mono text-[10px] tracking-wide2 transition-colors" style={{ color: 'var(--pb-accent)' }}>
                  READ →
                </p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <MarketingFooter />
    </div>
  )
}
