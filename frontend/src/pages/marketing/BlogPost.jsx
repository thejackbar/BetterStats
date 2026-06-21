import { useState } from 'react'
import { Link, useParams, Navigate } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'
import ZoomableImage from '../../components/marketing/ZoomableImage'
import { getPost, POSTS } from '../../data/blog'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
}

function HeroImage({ src, title }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return null
  return (
    <div className="mb-10 rounded-xl overflow-hidden border pb-hairline h-56 sm:h-72">
      <ZoomableImage
        src={src}
        alt={title}
        caption={title}
        className="w-full h-full object-cover object-top"
        wrapperClassName="h-full"
        onError={() => setFailed(true)}
        loading="eager"
      />
    </div>
  )
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
    case 'links':
      return (
        <div className="my-6">
          {block.heading && (
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">{block.heading}</p>
          )}
          <ul className="space-y-1.5">
            {block.items.map((it, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="mt-0.5 shrink-0" style={{ color: 'var(--pb-accent)' }}>→</span>
                {it.external ? (
                  <a href={it.href} rel="noopener" className="text-pb-dim hover:text-pb-text underline transition-colors">{it.label}</a>
                ) : (
                  <Link to={it.href} className="text-pb-dim hover:text-pb-text underline transition-colors">{it.label}</Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )
    default:
      return null
  }
}

export default function BlogPost() {
  const { slug } = useParams()
  const post = getPost(slug)

  const postUrl = post ? `https://betterat.cricket/blog/${post.slug}` : ''
  const postImage = post?.image ? `https://betterat.cricket${post.image}` : 'https://betterat.cricket/og-cover.png'

  // BlogPosting + breadcrumb structured data so search and AI engines read the
  // article cleanly (headline, date, publisher) and show it in the right place.
  const jsonLd = post ? [
    {
      '@context': 'https://schema.org',
      '@type': 'BlogPosting',
      headline: post.title,
      description: post.description,
      image: postImage,
      datePublished: post.date,
      dateModified: post.date,
      inLanguage: 'en-AU',
      author: { '@type': 'Organization', name: 'BetterCricket', url: 'https://betterat.cricket/' },
      publisher: {
        '@type': 'Organization',
        name: 'BetterSports',
        logo: { '@type': 'ImageObject', url: 'https://betterat.cricket/og-image.png' },
      },
      mainEntityOfPage: { '@type': 'WebPage', '@id': postUrl },
      url: postUrl,
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://betterat.cricket/' },
        { '@type': 'ListItem', position: 2, name: 'Blog', item: 'https://betterat.cricket/blog' },
        { '@type': 'ListItem', position: 3, name: post.title, item: postUrl },
      ],
    },
    ...(post.faq?.length ? [{
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: post.faq.map(({ q, a }) => ({
        '@type': 'Question',
        name: q,
        acceptedAnswer: { '@type': 'Answer', text: a },
      })),
    }] : []),
  ] : undefined

  usePageMeta(post ? {
    title: `${post.title} | BetterCricket`,
    description: post.description,
    image: postImage,
    url: postUrl,
    type: 'article',
    jsonLd,
  } : {})

  if (!post) return <Navigate to="/blog" replace />

  const currentIdx = POSTS.findIndex(p => p.slug === slug)
  const prev = POSTS[currentIdx + 1] ?? null
  const next = POSTS[currentIdx - 1] ?? null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-2xl mx-auto px-4 py-16 pt-28">
        {/* Breadcrumb */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-8">
          <Link to="/blog" className="hover:text-pb-text transition-colors">BLOG</Link>
          <span className="mx-2">›</span>
          <span className="text-pb-faintest">{post.title.toUpperCase().slice(0, 40)}{post.title.length > 40 ? '…' : ''}</span>
        </p>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">{formatDate(post.date)}</p>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest">{post.readTime}</p>
          </div>
          <h1 className="font-display font-bold text-[32px] md:text-[40px] tracking-tight text-pb-text leading-tight">
            {post.title}
          </h1>
        </div>

        {/* Hero image */}
        <HeroImage src={post.image} title={post.title} />

        {/* Content */}
        <div>
          {post.content.map((block, i) => (
            <ContentBlock key={i} block={block} />
          ))}
        </div>

        {/* FAQ */}
        {post.faq?.length > 0 && (
          <div className="mt-12 pb-hairline-t pt-10">
            <h2 className="font-display font-bold text-[22px] text-pb-text mb-5 leading-tight">Frequently asked questions</h2>
            <div className="space-y-6">
              {post.faq.map((f, i) => (
                <div key={i}>
                  <h3 className="font-semibold text-pb-text mb-1.5">{f.q}</h3>
                  <p className="text-pb-dim leading-relaxed text-sm">{f.a}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* CTA */}
        <div className="mt-16 pb-hairline-t pt-10">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Want this for your club?</p>
          <h2 className="font-display font-bold text-2xl text-pb-text mb-4 tracking-tight">Get automated stats for your cricket club.</h2>
          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              to="/contact"
              aria-label="Request access"
              className="inline-block px-6 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              REQUEST ACCESS
            </Link>
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

      <MarketingFooter />
    </div>
  )
}
