import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner, Btn } from '../../lib/presskit'

const PRESET_POSITIONS = [
  'President', 'Vice President', 'Secretary', 'Treasurer',
  'Captain (1st Grade)', 'Vice Captain (1st Grade)',
  'Captain (2nd Grade)', 'Vice Captain (2nd Grade)',
  'Captain (3rd Grade)', 'Vice Captain (3rd Grade)',
  'Captain (4th Grade)', 'Vice Captain (4th Grade)',
  'Coach', 'Assistant Coach', 'Club Champion', 'Best & Fairest',
  'Rookie of the Year', 'Life Member',
]

function HonourBoardSection({ orgId, seasonId, entries, players, onRefresh }) {
  const [adding, setAdding] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [position, setPosition] = useState('')
  const [usePlayer, setUsePlayer] = useState(true)
  const [playerId, setPlayerId] = useState('')
  const [nameOverride, setNameOverride] = useState('')
  const [sortOrder, setSortOrder] = useState(0)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)
  const [playerSearch, setPlayerSearch] = useState('')

  // Group entries by position
  const byPos = entries.reduce((acc, h) => {
    if (!acc[h.position_title]) acc[h.position_title] = []
    acc[h.position_title].push(h)
    return acc
  }, {})

  // Derive sort order from existing entries for the same position
  const getNextOrder = (pos) => {
    const existing = entries.filter(e => e.position_title === pos)
    return existing.length > 0 ? Math.max(...existing.map(e => e.sort_order || 0)) + 1 : 0
  }

  const filteredPlayers = players.filter(p => {
    if (!playerSearch) return true
    const name = (p.display_name || p.name || '').toLowerCase()
    return name.includes(playerSearch.toLowerCase())
  })

  const handleAdd = async () => {
    if (!position.trim()) { setErr('Position title is required.'); return }
    if (usePlayer && !playerId) { setErr('Select a player or switch to free-text.'); return }
    if (!usePlayer && !nameOverride.trim()) { setErr('Name is required.'); return }
    setSaving(true)
    setErr(null)
    try {
      await api.addHonourBoardEntry(orgId, seasonId, {
        position_title: position.trim(),
        player_id: usePlayer ? playerId : null,
        name_override: !usePlayer ? nameOverride.trim() : null,
        sort_order: getNextOrder(position.trim()),
      })
      setPosition('')
      setPlayerId('')
      setNameOverride('')
      setPlayerSearch('')
      setAdding(false)
      onRefresh()
    } catch (e) {
      setErr(`Error: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (entry) => {
    setDeleting(entry.id)
    try {
      await api.deleteHonourBoardEntry(orgId, seasonId, entry.id)
      onRefresh()
    } catch (e) {
      setErr(`Error: ${e.message}`)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-[13px] font-semibold text-white/90">Honour Board</h2>
          <p className="text-[11px] text-white/40 mt-0.5">
            {entries.length === 0 ? 'No entries yet — add club positions and holders.' : `${entries.length} entr${entries.length === 1 ? 'y' : 'ies'} across ${Object.keys(byPos).length} position${Object.keys(byPos).length !== 1 ? 's' : ''}`}
          </p>
        </div>
        {!adding && (
          <Btn onClick={() => { setAdding(true); setErr(null) }}>+ Add Entry</Btn>
        )}
      </div>

      {/* Current entries */}
      {Object.keys(byPos).length > 0 && (
        <div className="mb-4 divide-y divide-white/5 rounded-lg border border-white/8 overflow-hidden">
          {Object.entries(byPos).map(([pos, holders]) => (
            <div key={pos} className="flex items-start gap-4 px-4 py-3">
              <span className="font-mono text-[11px] text-white/40 uppercase tracking-wide w-44 shrink-0 pt-0.5">{pos}</span>
              <div className="flex-1 flex flex-wrap gap-2">
                {holders.map(h => (
                  <div key={h.id} className="flex items-center gap-1.5 bg-white/5 rounded px-2 py-1">
                    <span className="text-[12px] text-white/80">
                      {h.player_name || h.name_override || '—'}
                    </span>
                    <button
                      onClick={() => handleDelete(h)}
                      disabled={deleting === h.id}
                      className="text-white/20 hover:text-red-400/70 transition ml-1 text-[14px] leading-none disabled:opacity-40"
                      title="Remove"
                    >
                      {deleting === h.id ? '…' : '×'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add entry form */}
      {adding && (
        <div className="rounded-lg border border-white/10 bg-white/3 p-4 space-y-3">
          {/* Position title */}
          <div>
            <label className="block text-[11px] font-mono text-white/40 mb-1.5">POSITION TITLE</label>
            <input
              type="text"
              value={position}
              onChange={e => setPosition(e.target.value)}
              placeholder="e.g. Captain (1st Grade)"
              className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20"
            />
            {/* Preset chips */}
            <div className="flex flex-wrap gap-1.5 mt-2">
              {PRESET_POSITIONS.map(p => (
                <button
                  key={p}
                  onClick={() => setPosition(p)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                    position === p
                      ? 'border-pb-accent/50 text-pb-accent bg-pb-accent/10'
                      : 'border-white/10 text-white/30 hover:border-white/20 hover:text-white/50'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Toggle player vs free-text */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setUsePlayer(true)}
              className={`text-[11px] font-mono px-2.5 py-1 rounded border transition-colors ${usePlayer ? 'border-pb-accent/40 text-pb-accent bg-pb-accent/10' : 'border-white/10 text-white/30 hover:text-white/50'}`}
            >
              Select Player
            </button>
            <button
              onClick={() => setUsePlayer(false)}
              className={`text-[11px] font-mono px-2.5 py-1 rounded border transition-colors ${!usePlayer ? 'border-pb-accent/40 text-pb-accent bg-pb-accent/10' : 'border-white/10 text-white/30 hover:text-white/50'}`}
            >
              Free Text
            </button>
            <span className="text-[10px] text-white/25 font-mono">(use free text for non-registered members)</span>
          </div>

          {usePlayer ? (
            <div>
              <label className="block text-[11px] font-mono text-white/40 mb-1.5">PLAYER</label>
              <input
                type="text"
                value={playerSearch}
                onChange={e => setPlayerSearch(e.target.value)}
                placeholder="Search players…"
                className="w-full rounded-t bg-white/5 border border-white/10 border-b-0 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20"
              />
              <div className="max-h-40 overflow-y-auto rounded-b bg-white/5 border border-white/10">
                {filteredPlayers.length === 0 && (
                  <div className="px-3 py-2 text-[12px] text-white/25 italic">No players found</div>
                )}
                {filteredPlayers.slice(0, 30).map(p => (
                  <button
                    key={p.id}
                    onClick={() => { setPlayerId(p.id); setPlayerSearch(p.display_name || p.name) }}
                    className={`w-full text-left px-3 py-2 text-[13px] transition-colors ${
                      playerId === p.id ? 'bg-pb-accent/15 text-white/90' : 'text-white/70 hover:bg-white/5'
                    }`}
                  >
                    {p.display_name || p.name}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-[11px] font-mono text-white/40 mb-1.5">NAME</label>
              <input
                type="text"
                value={nameOverride}
                onChange={e => setNameOverride(e.target.value)}
                placeholder="Full name"
                className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20"
              />
            </div>
          )}

          {err && <p className="text-[11px] text-red-400/80">{err}</p>}

          <div className="flex items-center gap-2 pt-1">
            <Btn onClick={handleAdd} disabled={saving}>
              {saving ? 'Adding…' : 'Add Entry'}
            </Btn>
            <button
              onClick={() => { setAdding(false); setErr(null); setPosition(''); setPlayerId(''); setNameOverride(''); setPlayerSearch('') }}
              className="px-3 py-1.5 text-[12px] font-mono text-white/30 hover:text-white/50 transition"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminYearbookDetail() {
  const { seasonId } = useParams()
  const [org, setOrg] = useState(null)
  const [yearbook, setYearbook] = useState(null)
  const [players, setPlayers] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [msg, setMsg] = useState(null)

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

  useEffect(() => {
    if (!org?.id) return
    api.listPlayers(org.id).then(setPlayers).catch(() => {})
  }, [org?.id])

  const generateNarrative = async () => {
    setGenerating(true)
    setMsg(null)
    try {
      const res = await api.generateYearbookNarrative(org.id, seasonId)
      setNarrativeText(res.narrative)
      setNarrativeDirty(true)
      setMsg('AI draft generated — review and save to publish.')
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
        await api.createYearbookSection(org.id, seasonId, {
          section_type: 'narrative',
          title: 'Season in Brief',
          content_markdown: narrativeText,
          sort_order: 0,
          is_enabled: true,
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
          <Btn onClick={saveNarrative} disabled={saving || !narrativeText.trim()}>
            {saving ? 'Saving…' : 'Save Narrative'}
          </Btn>
        </div>
      </div>

      {/* Honour Board */}
      <HonourBoardSection
        orgId={org.id}
        seasonId={seasonId}
        entries={yearbook.honour_board || []}
        players={players}
        onRefresh={load}
      />
    </div>
  )
}
