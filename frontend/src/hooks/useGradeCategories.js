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
  const [availableFormats, setAvailableFormats] = useState([])
  const [categories, setCategories] = useState(null)

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    api.orgGradeCategories(orgId)
      .then(({ available: av, default: def, available_formats: fmts }) => {
        if (cancelled) return
        setAvailable(av || [])
        setAvailableFormats(fmts || [])
        setCategories(def || [])
      })
      .catch(() => {
        if (cancelled) return
        // No categories offered means no toggles drawn, which is the same
        // outcome as a club with only senior grades — a safe place to fail to.
        setAvailable([])
        setAvailableFormats([])
        setCategories([])
      })
    return () => { cancelled = true }
  }, [orgId])

  return {
    available,
    availableFormats,
    categories,
    setCategories,
    param: categories == null ? null : categoriesParam(categories),
    ready: categories != null,
  }
}

/**
 * The club dashboard's two pick-one grade filters.
 *
 * Deliberately NOT seeded from the club default the way `useGradeCategories`
 * is. "All" here means the club's own default — whatever it counts normally —
 * so the dashboard's opening numbers are the ones it has always shown, and
 * picking a grade type is a narrowing from there. Passing the default back as
 * an explicit selection would instead pin the page to a list that the club
 * could later change without the page noticing.
 */
export function useGradeFilters(orgId) {
  const [available, setAvailable] = useState([])
  const [availableFormats, setAvailableFormats] = useState([])
  const [defaultCategories, setDefaultCategories] = useState(null)
  const [gradeType, setGradeType] = useState(null)
  const [matchFormat, setMatchFormat] = useState(null)

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    api.orgGradeCategories(orgId)
      .then(({ available: av, default: def, available_formats: fmts }) => {
        if (cancelled) return
        setAvailable(av || [])
        setAvailableFormats(fmts || [])
        setDefaultCategories(def || [])
      })
      .catch(() => {
        if (cancelled) return
        setAvailable([])
        setAvailableFormats([])
        setDefaultCategories(null)
      })
    return () => { cancelled = true }
  }, [orgId])

  return {
    available,
    availableFormats,
    defaultCategories,
    gradeType,
    setGradeType,
    matchFormat,
    setMatchFormat,
    // Both go on the wire as the same comma-separated params every stats
    // endpoint already takes; null means "no filter", which for categories is
    // the club's own default and for formats is every format.
    categoriesParam: gradeType || null,
    formatsParam: matchFormat || null,
  }
}
