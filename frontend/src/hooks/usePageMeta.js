import { useEffect } from 'react'

const BASE_URL = 'https://betterstats.cricket'

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

export function usePageMeta({ title, description, image, url, type = 'website' } = {}) {
  useEffect(() => {
    const prevTitle = document.title
    if (title) document.title = title

    const tags = [
      ['og:title', title],
      ['og:description', description],
      ['og:image', image],
      ['og:url', url || (BASE_URL + window.location.pathname)],
      ['og:type', type],
      ['twitter:card', image ? 'summary_large_image' : 'summary'],
      ['twitter:title', title],
      ['twitter:description', description],
      ['twitter:image', image],
    ]

    const added = tags
      .filter(([, v]) => v)
      .map(([p, v]) => setMeta(p, v))
      .filter(Boolean)

    return () => {
      document.title = prevTitle
      tags.forEach(([p]) => removeMeta(p))
    }
  }, [title, description, image, url, type])
}
