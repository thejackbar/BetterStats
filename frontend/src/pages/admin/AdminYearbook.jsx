import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner, Btn } from '../../lib/presskit'
import { formatSeason } from '../../lib/cricketFormat'

function _seasonSlug(name) {
  if (!name) return ''
  const m1 = name.match(/(\d{4})\/(\d{2,4})/)
  if (m1) return `${m1[1]}-${m1[2].slice(-2)}`
  const m2 = name.match(/(\d{4})/)
  if (m2) return m2[1]
  return name.toLowerCase().replace(/\s+/g, '-')
}

export default function AdminYearbook() {
  const [org, setOrg] = useState(null)
  const [yearbooks, setYearbooks] = useState(null)
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.adminGetSettings().then(setOrg).catch(() => {})
  }, [])

  const load = useCallback(() => {
    if (!org?.id) return
    setLoading(true)
    api.listYearbooks(org.id)
      .then(setYearbooks)
      .finally(() => setLoading(false))
  }, [org?.id])

  useEffect(load, [load])

  const togglePublish = async (yb) => {
    setPublishing(yb.season_id)
    try {
      if (yb.status === 'published') {
        await api.unpublishYearbook(org.id, yb.season_id)
        setMsg(`${formatSeason(yb.season_name)} set back to Draft.`)
      } else {
        await api.publishYearbook(org.id, yb.season_id)
        setMsg(`${formatSeason(yb.season_name)} published!`)
      }
      load()
    } catch (e) {
      setMsg(`Error: ${e.message}`)
    } finally {
      setPublishing(null)
    }
  }

  const generateStubs = async () => {
    setGenerating(true)
    try {
      const res = await api.generateYearbookStubs(org.id)
      setMsg(`Created ${res.created} new yearbook stub${res.created !== 1 ? 's' : ''}.`)
      load()
    } catch (e) {
      setMsg(`Error: ${e.message}`)
    } finally {
      setGenerating(false)
    }
  }

  if (!org) return <PbSpinner />

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Yearbooks</h1>
          <p className="text-sm text-white/40 mt-0.5">Manage season yearbooks — publish to make them publicly accessible.</p>
        </div>
        <Btn onClick={generateStubs} disabled={generating}>
          {generating ? 'Generating…' : 'Generate Missing Stubs'}
        </Btn>
      </div>

      {msg && (
        <div className="mb-4 px-4 py-3 rounded-lg border border-white/15 bg-white/5 text-sm text-white/70 flex items-center justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="text-white/30 hover:text-white/60 text-lg leading-none ml-3">×</button>
        </div>
      )}

      {loading ? <PbSpinner /> : (
        <div className="space-y-2">
          {yearbooks?.length === 0 && (
            <p className="text-white/30 text-sm italic text-center py-8">
              No yearbooks yet. Click "Generate Missing Stubs" to create drafts for all synced seasons.
            </p>
          )}
          {yearbooks?.map(yb => (
            <div
              key={yb.season_id}
              className="flex items-center gap-4 rounded-xl border border-white/8 bg-white/3 px-5 py-4"
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium text-white/90 text-[14px]">{formatSeason(yb.season_name)}</div>
                <div className="flex items-center gap-3 mt-1">
                  <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono tracking-wide3 border ${
                    yb.status === 'published'
                      ? 'border-green-500/30 text-green-400 bg-green-500/10'
                      : 'border-white/15 text-white/40'
                  }`}>
                    {yb.status === 'published' ? 'PUBLISHED' : 'DRAFT'}
                  </span>
                  {yb.published_at && (
                    <span className="text-[11px] text-white/30 font-mono">
                      {new Date(yb.published_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Link
                  to={`/admin/yearbook/${yb.season_id}`}
                  className="px-3 py-1.5 rounded border border-white/15 text-[12px] font-mono text-white/50 hover:text-white/70 hover:border-white/25 transition-colors"
                >
                  Manage
                </Link>
                <Link
                  to={`/${org.slug}/yearbook/${_seasonSlug(yb.season_name)}`}
                  target="_blank"
                  className="px-3 py-1.5 rounded border border-white/15 text-[12px] font-mono text-white/50 hover:text-white/70 hover:border-white/25 transition-colors"
                >
                  Preview
                </Link>
                <button
                  onClick={() => togglePublish(yb)}
                  disabled={publishing === yb.season_id}
                  className={`px-3 py-1.5 rounded border text-[12px] font-mono transition-colors ${
                    yb.status === 'published'
                      ? 'border-white/20 text-white/50 hover:border-red-400/30 hover:text-red-400'
                      : 'border-green-500/30 text-green-400 hover:bg-green-500/10'
                  } disabled:opacity-40`}
                >
                  {publishing === yb.season_id ? '…' : yb.status === 'published' ? 'Unpublish' : 'Publish'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
