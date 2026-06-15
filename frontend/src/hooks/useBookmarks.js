import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

// Shared state for the admin sidebar bookmarks. Call once where both the header
// star and the sidebar list live (AdminLayout) so they stay in step. Updates are
// optimistic and revert on a failed save, so the star never lies about state.
export function useBookmarks(enabled = true) {
  const [bookmarks, setBookmarks] = useState([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    try {
      const list = await api.listBookmarks()
      setBookmarks(Array.isArray(list) ? list : [])
    } catch {
      // leave the current list in place — a failed refresh shouldn't blank it
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => { refresh() }, [refresh])

  const isBookmarked = useCallback(
    (path) => bookmarks.some(b => b.path === path),
    [bookmarks],
  )

  const add = useCallback(async (path, label) => {
    if (!path) return
    setBookmarks(prev => prev.some(b => b.path === path)
      ? prev
      : [...prev, { id: `tmp-${path}`, path, label: label || path, sort_order: prev.length + 1 }])
    try {
      const saved = await api.addBookmark(path, label)
      setBookmarks(prev => [...prev.filter(b => b.path !== path), saved]
        .sort((a, b) => (a.sort_order - b.sort_order)))
    } catch {
      setBookmarks(prev => prev.filter(b => b.path !== path)) // revert
    }
  }, [])

  const remove = useCallback(async (path) => {
    let snapshot
    setBookmarks(prev => { snapshot = prev; return prev.filter(b => b.path !== path) })
    try {
      await api.removeBookmark(path)
    } catch {
      if (snapshot) setBookmarks(snapshot) // revert
    }
  }, [])

  const toggle = useCallback((path, label) => {
    if (bookmarks.some(b => b.path === path)) remove(path)
    else add(path, label)
  }, [bookmarks, add, remove])

  return { bookmarks, loading, isBookmarked, add, remove, toggle, refresh }
}
