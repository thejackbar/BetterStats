import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { RichText } from '../../components/website/RichTextEditor'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

function PageBody({ slug, pageSlug }) {
  const { site } = useWebsite()
  const [page, setPage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setNotFound(false)
    api.webGetPage(slug, pageSlug)
      .then(d => { if (!cancelled) { setPage(d); setLoading(false) } })
      .catch(() => { if (!cancelled) { setNotFound(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [slug, pageSlug])

  usePageMeta({
    title: page ? `${page.title} - ${site.name}` : site.name,
    url: `https://betterat.cricket/${slug}/website/page/${pageSlug}`,
  })

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>
  if (notFound || !page) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <p className="text-pb-faint mb-4">This page couldn't be found.</p>
        <Link to={`/${slug}/website`} className="text-pb-accent font-mono text-sm">← Back home</Link>
      </div>
    )
  }

  return (
    <article className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="font-display font-extrabold text-3xl sm:text-4xl text-pb-text leading-tight mb-8">{page.title}</h1>
      {page.body ? <RichText html={page.body} className="text-base" />
        : <p className="text-pb-faint">Nothing here yet.</p>}
    </article>
  )
}

export default function WebsitePage() {
  const { clubSlug, pageSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="page">
      <PageBody slug={clubSlug} pageSlug={pageSlug} />
    </WebsiteChrome>
  )
}
