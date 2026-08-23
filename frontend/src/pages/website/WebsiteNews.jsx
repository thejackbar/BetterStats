import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { NewsCard } from '../../components/website/parts'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

const PAGE = 24

function NewsBody({ slug }) {
  const { site } = useWebsite()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)

  usePageMeta({ title: `News - ${site.name}`, url: `https://betterat.cricket/${slug}/website/news` })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.webListNews(slug, { limit: PAGE, offset: 0 })
      .then(d => { if (!cancelled) { setItems(d.items); setTotal(d.total); setLoading(false) } })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const d = await api.webListNews(slug, { limit: PAGE, offset: items.length })
      setItems(prev => [...prev, ...d.items])
      setTotal(d.total)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h1 className="font-display font-extrabold text-3xl text-pb-text mb-1">News</h1>
      <p className="text-pb-faint text-sm mb-8">Latest from {site.name}</p>

      {loading ? (
        <PbSpinner message="Loading news…" />
      ) : items.length === 0 ? (
        <p className="text-pb-faint py-12 text-center">No news yet. Check back soon.</p>
      ) : (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {items.map(a => <NewsCard key={a.id} slug={slug} article={a} />)}
          </div>
          {items.length < total && (
            <div className="text-center mt-8">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="px-5 py-2 rounded-lg border pb-hairline text-sm font-mono tracking-wide2 text-pb-faint hover:text-pb-text hover:border-pb-accent disabled:opacity-50"
              >
                {loadingMore ? 'LOADING…' : 'LOAD MORE'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function WebsiteNews() {
  const { clubSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="news">
      <NewsBody slug={clubSlug} />
    </WebsiteChrome>
  )
}
