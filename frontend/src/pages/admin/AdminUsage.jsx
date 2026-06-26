import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// A simple, live view of the public site: who's on it right now, the pages
// they're viewing in real time, and where the traffic comes from. Polls a
// single endpoint every few seconds.

const POLL_MS = 8000

const SOURCE_STYLE = {
  facebook:    { label: 'Facebook',     dot: '#1877f2' },
  instagram:   { label: 'Instagram',    dot: '#e1306c' },
  google:      { label: 'Google',       dot: '#ea4335' },
  bing:        { label: 'Bing',         dot: '#0c8484' },
  email:       { label: 'Email',        dot: '#f59e0b' },
  twitter:     { label: 'X / Twitter',  dot: '#1d9bf0' },
  linkedin:    { label: 'LinkedIn',     dot: '#0a66c2' },
  tiktok:      { label: 'TikTok',       dot: '#ff0050' },
  youtube:     { label: 'YouTube',      dot: '#ff0000' },
  whatsapp:    { label: 'WhatsApp',     dot: '#25d366' },
  reddit:      { label: 'Reddit',       dot: '#ff4500' },
  referral:    { label: 'Referral',     dot: '#a855f7' },
  direct:      { label: 'Direct',       dot: 'var(--pb-faint)' },
}
function sourceMeta(s) {
  const key = (s || 'direct').toLowerCase()
  return SOURCE_STYLE[key] || { label: s, dot: 'var(--pb-accent)' }
}

function flagFor(cc) {
  if (!cc || cc.length !== 2) return ''
  const cp = cc.toUpperCase().split('').map(c => 0x1f1e6 + c.charCodeAt(0) - 65)
  try { return String.fromCodePoint(...cp) } catch { return '' }
}

function fmtAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 10) return 'now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24); return `${d}d ago`
}

function deviceIcon(d) {
  switch (d?.type) {
    case 'mobile':  return '📱'
    case 'tablet':  return '📲'
    case 'bot':     return '🤖'
    case 'desktop': return '🖥️'
    default:        return '🌐'
  }
}

function Dot({ on, color = '#10b981', size = 6 }) {
  return (
    <span className={on ? 'animate-pulse' : ''}
      style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%',
               background: on ? color : 'transparent' }} />
  )
}

export default function AdminUsage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [live, setLive] = useState(true)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [, tick] = useState(0)
  const firstLoad = useRef(true)

  const load = useCallback(async () => {
    try {
      const d = await api.adminUsageLive()
      setData(d); setError(null); setUpdatedAt(Date.now())
    } catch (e) {
      setError(e?.message || 'Failed to load')
    } finally {
      firstLoad.current = false
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!live) return
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [live, load])

  // Re-render every second so the relative timers stay current.
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const A = data?.active
  const recent = data?.recent || []
  const perMinute = data?.per_minute || []
  const pmMax = Math.max(1, ...perMinute.map(p => p.views))
  const topPages = data?.top_pages || []
  const topMax = Math.max(1, ...topPages.map(p => p.views))
  const sources = data?.sources || []
  const srcMax = Math.max(1, ...sources.map(s => s.visitors))
  const utms = data?.utms || []

  const windows = [
    { key: 'now',   label: 'Active now',   sub: 'last 5 min',  live: true },
    { key: 'm30',   label: 'Last 30 min',  sub: '' },
    { key: 'today', label: 'Today',        sub: 'last 24h' },
    { key: 'week',  label: 'Last 7 days',  sub: '' },
  ]

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">Live</h1>
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border pb-hairline">
            <Dot on={live} />
            <span className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
              {live ? 'live' : 'paused'}
            </span>
          </span>
          <div className="ml-auto flex items-center gap-3">
            <span className="font-mono text-[10px] text-pb-faintest">
              {updatedAt ? `updated ${fmtAgo(new Date(updatedAt).toISOString())}` : ''}
            </span>
            <button onClick={() => setLive(l => !l)}
              className="font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text">
              {live ? 'Pause' : 'Resume'}
            </button>
            <button onClick={load}
              className="font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text">
              Refresh
            </button>
          </div>
        </div>
        <p className="text-pb-faint text-sm mb-5">
          Visitors on the public site right now and the pages they're viewing. Anonymous traffic only,
          so it reflects real visitors rather than us.
        </p>

        {error && (
          <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">
            {error}
          </div>
        )}
        {firstLoad.current && !data && (
          <div className="py-10 text-center font-mono text-[11px] text-pb-faint">Connecting…</div>
        )}

        {data && (
          <>
            {/* Active-visitor windows */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              {windows.map(w => {
                const a = A?.[w.key] || { visitors: 0, views: 0 }
                return (
                  <div key={w.key} className="pb-card px-4 py-3"
                    style={w.live ? { background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' } : undefined}>
                    <div className="flex items-center gap-1.5">
                      {w.live && <Dot on={live} />}
                      <span className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">{w.label}</span>
                    </div>
                    <div className="font-display text-3xl text-pb-text leading-tight mt-1">{a.visitors}</div>
                    <div className="font-mono text-[10px] text-pb-faintest">
                      {a.visitors === 1 ? 'visitor' : 'visitors'} · {a.views} views{w.sub ? ` · ${w.sub}` : ''}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Page views per minute */}
            <div className="pb-card px-4 py-3 mb-5">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">Page views per minute</span>
                <span className="font-mono text-[9px] text-pb-faintest">last 30 min</span>
              </div>
              <div className="flex items-end gap-[3px] h-14">
                {perMinute.map((p, i) => (
                  <div key={i} className="flex-1 rounded-t transition-all"
                    style={{ height: `${Math.max(3, (p.views / pmMax) * 100)}%`,
                             background: p.views ? 'var(--pb-accent)' : 'var(--pb-surface2)',
                             opacity: p.views ? (0.55 + 0.45 * (p.views / pmMax)) : 1 }}
                    title={`${new Date(p.minute).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })} · ${p.views} views`} />
                ))}
              </div>
            </div>

            {/* Main: live feed (left) + breakdowns (right) */}
            <div className="grid lg:grid-cols-3 gap-5">
              {/* Live page-view feed */}
              <div className="lg:col-span-2">
                <div className="flex items-center gap-2 mb-2">
                  <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">Live page views</h2>
                  <Dot on={live} />
                </div>
                <div className="pb-card overflow-hidden">
                  {recent.length === 0 && (
                    <div className="py-10 text-center font-mono text-[11px] text-pb-faint">No page views yet.</div>
                  )}
                  <div className="max-h-[640px] overflow-y-auto">
                    {recent.map((e, i) => {
                      const m = sourceMeta(e.source)
                      const isNew = (Date.now() - new Date(e.created_at).getTime()) < 15000
                      return (
                        <div key={`${e.created_at}-${i}`}
                          className={`flex items-center gap-2.5 px-3 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                          <Dot on={isNew} />
                          <span className="font-mono text-[10px] text-pb-faintest w-14 shrink-0">{fmtAgo(e.created_at)}</span>
                          <div className="flex-1 min-w-0">
                            <div className="text-[13px] text-pb-text truncate">{e.label}</div>
                            <a href={e.page} target="_blank" rel="noopener noreferrer"
                              className="font-mono text-[10px] text-pb-faint hover:text-pb-accent hover:underline truncate block">
                              {e.page}
                              {e.utm_source && <span className="text-pb-accent"> · {e.utm_source}{e.utm_campaign ? `/${e.utm_campaign}` : ''}</span>}
                            </a>
                          </div>
                          <span className="inline-flex items-center gap-1 shrink-0" title={`Source: ${m.label}`}>
                            <span className="w-2 h-2 rounded-full" style={{ background: m.dot }} />
                            <span className="font-mono text-[9px] text-pb-faint hidden sm:inline">{m.label}</span>
                          </span>
                          <span className="font-mono text-[10px] text-pb-faint w-20 text-right truncate shrink-0"
                            title={[e.city, e.region, e.country].filter(Boolean).join(', ')}>
                            {e.country ? `${flagFor(e.country)} ${e.city || e.country}` : ''}
                          </span>
                          <span className="shrink-0 text-sm" title={[e.device?.os, e.device?.browser].filter(Boolean).join(' ')}>
                            {deviceIcon(e.device)}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* Right column: top pages, sources, UTMs */}
              <div className="space-y-5">
                <div>
                  <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-2">Top pages</h2>
                  <p className="font-mono text-[9px] text-pb-faintest mb-2">last 24 hours</p>
                  <div className="pb-card px-3 py-2">
                    {topPages.length === 0 && <div className="py-3 text-center font-mono text-[10px] text-pb-faint">No views yet.</div>}
                    {topPages.map((p, i) => (
                      <div key={i} className="flex items-center gap-2 py-1">
                        <div className="w-32 truncate text-[12px] text-pb-text" title={p.page}>{p.label}</div>
                        <div className="flex-1 h-3 bg-pb-surface2 rounded overflow-hidden">
                          <div className="h-full bg-pb-accent rounded" style={{ width: `${Math.round((p.views / topMax) * 100)}%` }} />
                        </div>
                        <div className="w-10 text-right font-mono text-[10px] text-pb-faint">{p.views}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-2">Sources</h2>
                  <p className="font-mono text-[9px] text-pb-faintest mb-2">last 24 hours</p>
                  <div className="pb-card px-3 py-2">
                    {sources.length === 0 && <div className="py-3 text-center font-mono text-[10px] text-pb-faint">No traffic yet.</div>}
                    {sources.map((s, i) => {
                      const m = sourceMeta(s.source)
                      return (
                        <div key={i} className="flex items-center gap-2 py-1">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: m.dot }} />
                          <div className="w-20 truncate text-[12px] text-pb-text" title={m.label}>{m.label}</div>
                          <div className="flex-1 h-3 bg-pb-surface2 rounded overflow-hidden">
                            <div className="h-full rounded" style={{ width: `${Math.round((s.visitors / srcMax) * 100)}%`, background: m.dot }} />
                          </div>
                          <div className="w-12 text-right font-mono text-[10px] text-pb-faint">{s.visitors}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                <div>
                  <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-2">UTM links</h2>
                  <p className="font-mono text-[9px] text-pb-faintest mb-2">last 24 hours</p>
                  <div className="pb-card px-3 py-2">
                    {utms.length === 0 ? (
                      <div className="py-2 font-mono text-[10px] text-pb-faintest leading-relaxed">
                        No UTM-tagged links in the last 24h. Add <span className="text-pb-faint">?utm_source=…</span> to
                        your share links to track them here.
                      </div>
                    ) : utms.map((u, i) => (
                      <div key={i} className="flex items-center gap-2 py-1">
                        <div className="flex-1 min-w-0">
                          <div className="font-mono text-[11px] text-pb-text truncate">
                            {u.utm_source}{u.utm_campaign ? <span className="text-pb-faint"> / {u.utm_campaign}</span> : ''}
                          </div>
                          {u.utm_medium && <div className="font-mono text-[9px] text-pb-faintest">{u.utm_medium}</div>}
                        </div>
                        <div className="text-right shrink-0">
                          <div className="font-mono text-[10px] text-pb-text">{u.visitors} ppl</div>
                          <div className="font-mono text-[9px] text-pb-faintest">{u.views} views</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
