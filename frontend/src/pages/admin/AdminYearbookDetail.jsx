import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner, Btn } from '../../lib/presskit'

export default function AdminYearbookDetail() {
  const { seasonId } = useParams()
  const [org, setOrg] = useState(null)
  const [yearbook, setYearbook] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [msg, setMsg] = useState(null)

  // Narrative editor state
  const [narrativeText, setNarrativeText] = useState('')
  const [narrativeDirty, setNarrativeDirty] = useState(false)

  useEffect(() => {
    api.adminGetSettings().then(setOrg).catch(() => {})
  }, [])

  const load = useCallback(() => {
    if (!org?.id || !seasonId) return
    setLoading(true)
    api.getYearbook(org.id, seasonId)
      .then(yb => {
        setYearbook(yb)
        const narrative = yb.sections?.find(s => s.section_type === 'narrative')
        setNarrativeText(narrative?.content_markdown || narrative?.ai_draft || '')
        setNarrativeDirty(false)
      })
      .finally(() => setLoading(false))
  }, [org?.id, seasonId])

  useEffect(load, [load])

  const generateNarrative = async () => {
    setGenerating(true)
    setMsg(null)
    try {
      const res = await api.generateYearbookNarrative(org.id, seasonId)
      setNarrativeText(res.narrative)
      setNarrativeDirty(true)
      setMsg('AI draft generated — review and save to publish.')
      // Reload to get section id
      load()
    } catch (e) {
      setMsg(`Error generating narrative: ${e.message}`)
    } finally {
      setGenerating(false)
    }
  }

  const saveNarrative = async () => {
    const narrative = yearbook?.sections?.find(s => s.section_type === 'narrative')
    setSaving(true)
    setMsg(null)
    try {
      if (narrative?.id) {
        await api.updateYearbookSection(org.id, seasonId, narrative.id, {
          section_type: 'narrative',
          title: narrative.title || 'Season in Brief',
          content_markdown: narrativeText,
          sort_order: narrative.sort_order || 0,
          is_enabled: true,
        })
      } else {
        await api.request(`/yearbooks/${org.id}/${seasonId}/sections`, {
          method: 'POST',
          body: JSON.stringify({
            section_type: 'narrative',
            title: 'Season in Brief',
            content_markdown: narrativeText,
            sort_order: 0,
            is_enabled: true,
          }),
        })
      }
      setNarrativeDirty(false)
      setMsg('Narrative saved.')
      load()
    } catch (e) {
      setMsg(`Error saving: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const togglePublish = async () => {
    if (!yearbook) return
    setPublishing(true)
    setMsg(null)
    try {
      if (yearbook.status === 'published') {
        await api.unpublishYearbook(org.id, seasonId)
        setMsg('Yearbook set back to Draft.')
      } else {
        await api.publishYearbook(org.id, seasonId)
        setMsg('Yearbook published!')
      }
      load()
    } catch (e) {
      setMsg(`Error: ${e.message}`)
    } finally {
      setPublishing(false)
    }
  }

  if (!org || loading) return <PbSpinner />
  if (!yearbook) return <div className="max-w-3xl mx-auto px-4 py-8 text-white/50">Yearbook not found.</div>

  const seasonName = yearbook.season?.name || seasonId
  const isPublished = yearbook.status === 'published'
  const narrative = yearbook.sections?.find(s => s.section_type === 'narrative')
  const hasAiDraft = !!narrative?.ai_draft
  const hasSaved = !!narrative?.content_markdown

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <Link to="/admin/yearbook" className="text-[11px] font-mono text-white/30 hover:text-white/50 transition mb-2 inline-block">
            ← All Yearbooks
          </Link>
          <h1 className="text-xl font-semibold text-white">{seasonName}</h1>
          <div className="flex items-center gap-3 mt-1.5">
            <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono tracking-wide3 border ${
              isPublished
                ? 'border-green-500/30 text-green-400 bg-green-500/10'
                : 'border-white/15 text-white/40'
            }`}>
              {isPublished ? 'PUBLISHED' : 'DRAFT'}
            </span>
            {yearbook.published_at && (
              <span className="text-[11px] text-white/30 font-mono">
                Published {new Date(yearbook.published_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link
            to={`/${org.slug}/yearbook`}
            target="_blank"
            className="px-3 py-1.5 rounded border border-white/15 text-[12px] font-mono text-white/50 hover:text-white/70 hover:border-white/25 transition-colors"
          >
            Preview
          </Link>
          <button
            onClick={togglePublish}
            disabled={publishing}
            className={`px-3 py-1.5 rounded border text-[12px] font-mono transition-colors disabled:opacity-40 ${
              isPublished
                ? 'border-white/20 text-white/50 hover:border-red-400/30 hover:text-red-400'
                : 'border-green-500/30 text-green-400 hover:bg-green-500/10'
            }`}
          >
            {publishing ? '…' : isPublished ? 'Unpublish' : 'Publish'}
          </button>
        </div>
      </div>

      {msg && (
        <div className="mb-5 px-4 py-3 rounded-lg border border-white/15 bg-white/5 text-sm text-white/70 flex items-center justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="text-white/30 hover:text-white/60 text-lg leading-none ml-3">×</button>
        </div>
      )}

      {/* Narrative Section */}
      <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-[13px] font-semibold text-white/90">Season Narrative</h2>
            <p className="text-[11px] text-white/40 mt-0.5">
              {hasSaved ? 'Saved — shown publicly when yearbook is published.'
                : hasAiDraft ? 'AI draft ready — edit and save to publish.'
                : 'Generate an AI draft then edit before saving.'}
            </p>
          </div>
          <Btn onClick={generateNarrative} disabled={generating} className="shrink-0">
            {generating ? 'Generating…' : hasAiDraft ? 'Regenerate' : 'Generate AI Draft'}
          </Btn>
        </div>

        <textarea
          value={narrativeText}
          onChange={e => { setNarrativeText(e.target.value); setNarrativeDirty(true) }}
          rows={10}
          placeholder="Click 'Generate AI Draft' to auto-generate a season narrative, or type your own…"
          className="w-full rounded-lg bg-white/5 border border-white/10 text-white/80 text-sm px-4 py-3 resize-y font-sans leading-relaxed focus:outline-none focus:border-white/25 placeholder:text-white/20"
        />

        <div className="flex items-center justify-between mt-3">
          <span className="text-[11px] text-white/25 font-mono">
            {narrativeText.length} chars
            {narrativeDirty && <span className="ml-2 text-amber-400/60">· unsaved changes</span>}
          </span>
          <Btn
            onClick={saveNarrative}
            disabled={saving || !narrativeText.trim()}
          >
            {saving ? 'Saving…' : 'Save Narrative'}
          </Btn>
        </div>
      </div>

      {/* Future sections placeholder */}
      <div className="rounded-xl border border-white/5 bg-white/1 px-5 py-4 text-center">
        <p className="text-[11px] text-white/25 font-mono">More sections coming soon — Honour Board, Awards, Gallery</p>
      </div>
    </div>
  )
}
