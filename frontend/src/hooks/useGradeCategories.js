import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { categoriesParam } from '../lib/gradeCategories'

/**
 * Which grade categories a stats page is counting, and which it can offer.
 *
 * Seeded from the club's own default (`GET /organisations/{id}/grade-categories`)
 * rather than a hardcoded list, so a junior club that has set its default to
 * count juniors opens that way instead of flicking to it after first paint.
 * Selection is per visitor and per page — it is a way of reading the numbers,
 * not a setting, so it deliberately does not persist.
 *
 * `param` is what goes on the wire: null while the default is still loading, so
 * a page's first fetch does not race ahead with a guess and then correct itself.
 */
export function useGradeCategories(orgId) {
  const [available, setAvailable] = useState([])
  const [categories, setCategories] = useState(null)

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    api.orgGradeCategories(orgId)
      .then(({ available: av, default: def }) => {
        if (cancelled) return
        setAvailable(av || [])
        setCategories(def || [])
      })
      .catch(() => {
        if (cancelled) return
        // No categories offered means no toggles drawn, which is the same
        // outcome as a club with only senior grades — a safe place to fail to.
        setAvailable([])
        setCategories([])
      })
    return () => { cancelled = true }
  }, [orgId])

  return {
    available,
    categories,
    setCategories,
    param: categories == null ? null : categoriesParam(categories),
    ready: categories != null,
  }
}
