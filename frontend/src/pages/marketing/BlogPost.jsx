import { Link, useParams, Navigate } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'
import { getPost, POSTS } from '../../data/blog'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
}

function ContentBlock({ block }) {
  switch (block.type) {
    case 'h2':
      return <h2 className="font-display font-bold text-[22px] text-pb-text mt-10 mb-3 leading-tight">{block.text}</h2>
    case 'p':
      return <p className="text-pb-dim leading-relaxed mb-4">{block.text}</p>
    case 'ul':
      return (
        <ul className="space-y-2 mb-4 ml-1">
          {block.items.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-pb-dim">
              <span className="mt-0.5 font-mono shrink-0" style={{ color: 'var(--pb-accent)' }}>✓</span>
              {item}
            </li>
          ))}
        </ul>
      )
    case 'callout':
      return (
        <div className="my-8 pb-card p-5 border-l-2" style={{ borderLeftColor: 'var(--pb-accent)' }}>
          <p className="text-pb-dim text-sm leading-relaxed">{block.text}</p>
          <Link
            to="/contact"
            className="inline-block mt-3 font-mono text-[10px] tracking-wide2 font-semibold"
            style={{ color: 'var(--pb-accent)' }}
          >
            LEARN MORE →
          </Link>
        </div>
      )
    default:
      return null
  }
}

export default function BlogPost() {
  const { slug } = useParams()
  const post = getPost(slug)

  usePageMeta(post ? {
    title: `${post.title} | BetterStats`,
    description: post.description,
    image: 'https://betterstats.cricket/og-image.png',
    url: `https://betterstats.cricket/blog/${post.slug}`,
  } : {})

  if (!post) return <Navigate to="/blog" replace />

  const currentIdx = POSTS.findIndex(p => p.slug === slug)
  const prev = POSTS[currentIdx + 1] ?? null
  const next = POSTS[currentIdx - 1] ?? null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-2xl mx-auto px-4 py-16">
        {/* Breadcrumb */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-8">
          <Link to="/blog" className="hover:text-pb-text transition-colors">BLOG</Link>
          <span className="mx-2">›</span>
          <span className="text-pb-faintest">{post.title.toUpperCase().slice(0, 40)}{post.title.length > 40 ? '…' : ''}</span>
        </p>

        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">{formatDate(post.date)}</p>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest">{post.readTime}</p>
          </div>
          <h1 className="font-display font-bold text-[32px] md:text-[40px] tracking-tight text-pb-text leading-tight">
            {post.title}
          </h1>
        </div>

        {/* Content */}
        <div>
          {post.content.map((block, i) => (
            <ContentBlock key={i} block={block} />
          ))}
        </div>

        {/* CTA */}
        <div className="mt-16 pb-hairline-t pt-10">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Want this for your club?</p>
          <h2 className="font-display font-bold text-2xl text-pb-text mb-4 tracking-tight">Get automated stats for your cricket club.</h2>
          <div className="flex flex-col sm:flex-row gap-3">
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block px-6 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              REQUEST ACCESS
            </a>
            <Link
              to="/features"
              className="inline-block px-6 py-3 border pb-hairline rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors"
            >
              SEE FEATURES →
            </Link>
          </div>
        </div>

        {/* Prev / Next */}
        {(prev || next) && (
          <div className="mt-12 pb-hairline-t pt-8 grid grid-cols-2 gap-4">
            <div>
              {next && (
                <Link to={`/blog/${next.slug}`} className="group block">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">← NEWER</p>
                  <p className="text-sm text-pb-dim group-hover:text-pb-text transition-colors leading-snug">{next.title}</p>
                </Link>
              )}
            </div>
            <div className="text-right">
              {prev && (
                <Link to={`/blog/${prev.slug}`} className="group block">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">OLDER →</p>
                  <p className="text-sm text-pb-dim group-hover:text-pb-text transition-colors leading-snug">{prev.title}</p>
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
