import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { RichText } from '../../components/website/RichTextEditor'
import { NewsCard, formatDate } from '../../components/website/parts'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

function ArticleBody({ slug, newsSlug }) {
  const { site } = useWebsite()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setNotFound(false)
    api.webGetArticle(slug, newsSlug)
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(() => { if (!cancelled) { setNotFound(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [slug, newsSlug])

  const article = data?.article
  usePageMeta({
    title: article ? `${article.title} - ${site.name}` : `News - ${site.name}`,
    description: article?.summary || null,
    image: article?.cover_image_url || null,
    url: `https://betterat.cricket/${slug}/website/news/${newsSlug}`,
  })

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>
  if (notFound || !article) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <p className="text-pb-faint mb-4">This article couldn't be found.</p>
        <Link to={`/${slug}/website/news`} className="text-pb-accent font-mono text-sm">← Back to news</Link>
      </div>
    )
  }

  return (
    <article className="max-w-3xl mx-auto px-4 py-10">
      <Link to={`/${slug}/website/news`} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-accent">
        ← ALL NEWS
      </Link>
      <h1 className="font-display font-extrabold text-3xl sm:text-4xl text-pb-text leading-tight mt-3">{article.title}</h1>
      <div className="flex items-center gap-3 mt-3 text-pb-faint font-mono text-[11px] tracking-wide2">
        <span>{formatDate(article.published_at)}</span>
        {article.author && <><span>·</span><span>By {article.author}</span></>}
      </div>

      {article.cover_image_url && (
        <img src={article.cover_image_url} alt="" className="w-full rounded-xl mt-6 mb-2 object-cover" />
      )}

      <div className="mt-6">
        {article.body ? <RichText html={article.body} className="text-base" />
          : article.summary && <p className="text-pb-dim text-lg">{article.summary}</p>}
      </div>

      {data.more?.length > 0 && (
        <div className="mt-16 pt-8 border-t pb-hairline-t">
          <h2 className="font-display font-bold text-lg text-pb-text mb-5">More news</h2>
          <div className="grid sm:grid-cols-3 gap-5">
            {data.more.map(a => <NewsCard key={a.id} slug={slug} article={a} />)}
          </div>
        </div>
      )}
    </article>
  )
}

export default function WebsiteArticle() {
  const { clubSlug, newsSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="news">
      <ArticleBody slug={clubSlug} newsSlug={newsSlug} />
    </WebsiteChrome>
  )
}
