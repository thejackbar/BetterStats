import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { CHANGELOG } from '../data/changelog'
import { SITE_VERSION } from '../version'

function compareVersions(a, b) {
  const parse = v => (v || '').replace('v', '').split('.').map(Number)
  const av = parse(a)
  const bv = parse(b)
  for (let i = 0; i < Math.max(av.length, bv.length); i++) {
    const diff = (av[i] || 0) - (bv[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

export default function NotificationBell({ onOpen, refreshTrigger }) {
  const [data, setData] = useState({ unseen_count: 0, last_seen_version: null })

  const refresh = useCallback(async () => {
    try {
      const d = await api.getNotificationsCount()
      setData(d)
    } catch {
      // fail silently — bell just shows 0
    }
  }, [])

  useEffect(() => { refresh() }, [refresh, refreshTrigger])
  useEffect(() => {
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  const newChangelogCount = CHANGELOG.filter(
    e => compareVersions(e.version, data.last_seen_version) > 0
  ).length

  const totalCount = (data.unseen_count || 0) + newChangelogCount
  const capped = totalCount > 99 ? '99+' : totalCount

  return (
    <button
      onClick={onOpen}
      className="relative w-8 h-8 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition"
      title="Notifications"
      aria-label="Open notifications"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {totalCount > 0 && (
        <span
          className="absolute top-0.5 right-0.5 min-w-[14px] h-[14px] flex items-center justify-center rounded-full font-mono text-[9px] font-bold leading-none px-[3px]"
          style={{ background: 'var(--pb-accent)', color: '#000' }}
        >
          {capped}
        </span>
      )}
    </button>
  )
}
