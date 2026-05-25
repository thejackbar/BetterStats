import { useEffect } from 'react'

const BASE_URL = 'https://betterstats.cricket'
const JSON_LD_ID = 'route-jsonld'
const CANONICAL_ID = 'route-canonical'

function setMeta(property, content) {
  if (!content) return null
  const existing = document.querySelector(`meta[property="${property}"], meta[name="${property}"]`)
  if (existing) {
    existing.setAttribute('content', content)
    return existing
  }
  const el = document.createElement('meta')
  if (property.startsWith('og:') || property.startsWith('twitter:')) {
    el.setAttribute(property.startsWith('twitter:') ? 'name' : 'property', property)
  } else {
    el.setAttribute('name', property)
  }
  el.setAttribute('content', content)
  document.head.appendChild(el)
  return el
}

function removeMeta(property) {
  const el = document.querySelector(`meta[property="${property}"], meta[name="${property}"]`)
  el?.remove()
}

function setCanonical(href) {
  if (!href) return
  let link = document.querySelector(`link[rel="canonical"]#${CANONICAL_ID}`)
  if (!link) {
    // Replace the default canonical (set in index.html) with one we control.
    document.querySelectorAll('link[rel="canonical"]').forEach(l => l.remove())
    link = document.createElement('link')
    link.rel = 'canonical'
    link.id = CANONICAL_ID
    document.head.appendChild(link)
  }
  link.href = href
}

function setJsonLd(data) {
  document.querySelectorAll(`script[type="application/ld+json"]#${JSON_LD_ID}`).forEach(s => s.remove())
  if (!data) return
  const script = document.createElement('script')
  script.type = 'application/ld+json'
  script.id = JSON_LD_ID
  script.text = JSON.stringify(data)
  document.head.appendChild(script)
}

/**
 * Per-route meta tag manager.
 *   - title / description: <title> + <meta name=description>
 *   - image: og:image + twitter:image (uses summary_large_image if present)
 *   - url:   og:url (defaults to current path on betterstats.cricket)
 *   - type:  og:type (default 'website')
 *   - jsonLd: optional schema.org JSON-LD object or array — injected as a
 *             scoped <script> and cleared on unmount.
 *   - canonical: explicit canonical URL (defaults to og:url)
 */
export function usePageMeta({ title, description, image, url, type = 'website', jsonLd, canonical } = {}) {
  useEffect(() => {
    const prevTitle = document.title
    if (title) document.title = title

    const resolvedUrl = url || (BASE_URL + window.location.pathname)
    const resolvedCanonical = canonical || resolvedUrl

    const tags = [
      ['description', description],
      ['og:title', title],
      ['og:description', description],
      ['og:image', image],
      ['og:url', resolvedUrl],
      ['og:type', type],
      ['twitter:card', image ? 'summary_large_image' : 'summary'],
      ['twitter:title', title],
      ['twitter:description', description],
      ['twitter:image', image],
    ]

    tags.filter(([, v]) => v).forEach(([p, v]) => setMeta(p, v))
    setCanonical(resolvedCanonical)
    if (jsonLd) setJsonLd(jsonLd)

    return () => {
      document.title = prevTitle
      // Don't remove the description/canonical/JSON-LD wholesale — the next
      // page's usePageMeta call will overwrite them. Only clear tags we added.
      if (jsonLd) setJsonLd(null)
    }
  }, [title, description, image, url, type, canonical, JSON.stringify(jsonLd)])
}
