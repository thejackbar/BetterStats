import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner, Btn } from '../../lib/presskit'

const AWARD_PRESETS = [
  'Best & Fairest', 'Best Batter', 'Best Bowler', 'Best Fieldsman',
  'Club Champion', 'Rookie of the Year', 'Most Improved',
  'Most Valuable Player', "Club Person of the Year", "President's Award", 'Custom',
]

function HeroImagePanel({ orgId, seasonId, heroPath, onRefresh }) {
  const inputRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState(null)

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setErr(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      await api.uploadYearbookHero(orgId, seasonId, fd)
      onRefresh()
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleClear = async () => {
    setErr(null)
    try {
      await api.clearYearbookHero(orgId, seasonId)
      onRefresh()
    } catch (ex) {
      setErr(ex.message)
    }
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <h2 className="text-[13px] font-semibold text-white/90 mb-1">Hero Image</h2>
      <p className="text-[11px] text-white/40 mb-4">Shown as the yearbook cover background. Landscape photos work best.</p>
      {heroPath ? (
        <div className="mb-3">
          <img
            src={`/uploads/${heroPath}`}
            alt="Hero"
            className="w-full max-h-48 object-cover rounded-lg border border-white/10"
          />
          <div className="flex gap-2 mt-2">
            <Btn onClick={() => inputRef.current?.click()} disabled={uploading}>
              {uploading ? 'Uploading…' : 'Replace'}
            </Btn>
            <button
              onClick={handleClear}
              className="px-3 py-1.5 text-[12px] font-mono text-red-400/60 hover:text-red-400 transition"
            >
              Remove
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="w-full border-2 border-dashed border-white/15 rounded-lg py-8 text-center hover:border-white/25 transition-colors disabled:opacity-40"
        >
          <div className="text-white/40 text-[13px]">{uploading ? 'Uploading…' : '+ Upload Hero Image'}</div>
          <div className="text-white/25 text-[11px] font-mono mt-1">JPG, PNG, WEBP up to 20MB</div>
        </button>
      )}
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
      {err && <p className="text-[11px] text-red-400/80 mt-2">{err}</p>}
    </div>
  )
}

function GalleryPanel({ orgId, seasonId, images, onRefresh }) {
  const inputRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [err, setErr] = useState(null)

  const galleryImages = images.filter(i => i.image_type === 'gallery')

  const handleFile = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setUploading(true)
    setErr(null)
    try {
      for (const file of files) {
        const fd = new FormData()
        fd.append('file', file)
        await api.uploadYearbookGallery(orgId, seasonId, fd)
      }
      onRefresh()
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDelete = async (img) => {
    setDeleting(img.id)
    try {
      await api.deleteYearbookImage(orgId, seasonId, img.id)
      onRefresh()
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-[13px] font-semibold text-white/90">Photo Gallery</h2>
          <p className="text-[11px] text-white/40 mt-0.5">Team photos, match shots, presentations — shown on the public yearbook.</p>
        </div>
        <Btn onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? 'Uploading…' : '+ Add Photos'}
        </Btn>
      </div>
      {galleryImages.length > 0 ? (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-2">
          {galleryImages.map(img => (
            <div key={img.id} className="relative group aspect-square">
              <img
                src={`/uploads/${img.file_path}`}
                alt=""
                className="w-full h-full object-cover rounded-lg border border-white/8"
              />
              <button
                onClick={() => handleDelete(img)}
                disabled={deleting === img.id}
                className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white/70 hover:text-red-400 flex items-center justify-center text-[13px] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
              >
                {deleting === img.id ? '…' : '×'}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-white/25 italic mb-2">No photos yet.</p>
      )}
      <input ref={inputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleFile} />
      {err && <p className="text-[11px] text-red-400/80 mt-1">{err}</p>}
    </div>
  )
}

function ClubAwardsPanel({ orgId, seasonId, awards, players, onRefresh }) {
  const [adding, setAdding] = useState(false)
  const [awardName, setAwardName] = useState('')
  const [customName, setCustomName] = useState('')
  const [usePlayer, setUsePlayer] = useState(true)
  const [playerId, setPlayerId] = useState('')
  const [playerSearch, setPlayerSearch] = useState('')
  const [nameOverride, setNameOverride] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [err, setErr] = useState(null)

  const filteredPlayers = players.filter(p =>
    !playerSearch || (p.display_name || p.name || '').toLowerCase().includes(playerSearch.toLowerCase())
  )

  const handleAdd = async () => {
    const finalName = awardName === 'Custom' ? customName.trim() : awardName
    if (!finalName) { setErr('Award name required.'); return }
    if (usePlayer && !playerId) { setErr('Select a player or switch to free text.'); return }
    if (!usePlayer && !nameOverride.trim()) { setErr('Recipient name required.'); return }
    setSaving(true); setErr(null)
    try {
      await api.createYearbookAward(orgId, seasonId, {
        award_name: finalName,
        player_id: usePlayer ? playerId : null,
        name_override: !usePlayer ? nameOverride.trim() : null,
        notes: notes.trim() || null,
        sort_order: awards.length,
      })
      setAdding(false); setAwardName(''); setCustomName(''); setPlayerId('')
      setNameOverride(''); setNotes(''); setPlayerSearch('')
      onRefresh()
    } catch (ex) { setErr(ex.message) }
    finally { setSaving(false) }
  }

  const handleDelete = async (award) => {
    setDeleting(award.id)
    try { await api.deleteYearbookAward(orgId, seasonId, award.id); onRefresh() }
    catch (ex) { setErr(ex.message) }
    finally { setDeleting(null) }
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-[13px] font-semibold text-white/90">Club Awards</h2>
          <p className="text-[11px] text-white/40 mt-0.5">
            {awards.length === 0 ? 'Season award winners — shown on the Awards tab.' : `${awards.length} award${awards.length !== 1 ? 's' : ''} recorded`}
          </p>
        </div>
        {!adding && <Btn onClick={() => { setAdding(true); setErr(null) }}>+ Add Award</Btn>}
      </div>

      {awards.length > 0 && (
        <div className="mb-4 divide-y divide-white/5 rounded-lg border border-white/8 overflow-hidden">
          {awards.map(a => (
            <div key={a.id} className="flex items-start gap-4 px-4 py-3">
              <div className="flex-1 min-w-0">
                <span className="font-mono text-[10px] text-white/40 uppercase tracking-wide">{a.award_name}</span>
                <div className="text-[13px] text-white/80 mt-0.5">{a.player_name || a.name_override || '—'}</div>
                {a.notes && <div className="text-[11px] text-white/35 mt-0.5 italic">{a.notes}</div>}
              </div>
              <button
                onClick={() => handleDelete(a)}
                disabled={deleting === a.id}
                className="shrink-0 text-white/20 hover:text-red-400/70 transition text-[12px] font-mono disabled:opacity-40 pt-0.5"
              >
                {deleting === a.id ? '…' : 'Delete'}
              </button>
            </div>
          ))}
        </div>
      )}

      {adding && (
        <div className="rounded-lg border border-white/10 bg-white/3 p-4 space-y-3">
          {/* Award name presets */}
          <div>
            <label className="block text-[11px] font-mono text-white/40 mb-1.5">AWARD</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {AWARD_PRESETS.map(p => (
                <button key={p} onClick={() => setAwardName(p)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-colors ${awardName === p ? 'border-pb-accent/50 text-pb-accent bg-pb-accent/10' : 'border-white/10 text-white/30 hover:border-white/20 hover:text-white/50'}`}>
                  {p}
                </button>
              ))}
            </div>
            {awardName === 'Custom' && (
              <input type="text" value={customName} onChange={e => setCustomName(e.target.value)}
                placeholder="Award name…"
                className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20" />
            )}
          </div>

          {/* Player vs free text */}
          <div className="flex items-center gap-2">
            {[['Select Player', true], ['Free Text', false]].map(([label, val]) => (
              <button key={label} onClick={() => setUsePlayer(val)}
                className={`text-[11px] font-mono px-2.5 py-1 rounded border transition-colors ${usePlayer === val ? 'border-pb-accent/40 text-pb-accent bg-pb-accent/10' : 'border-white/10 text-white/30 hover:text-white/50'}`}>
                {label}
              </button>
            ))}
          </div>

          {usePlayer ? (
            <div>
              <input type="text" value={playerSearch} onChange={e => setPlayerSearch(e.target.value)}
                placeholder="Search players…"
                className="w-full rounded-t bg-white/5 border border-white/10 border-b-0 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20" />
              <div className="max-h-36 overflow-y-auto rounded-b bg-white/5 border border-white/10">
                {filteredPlayers.slice(0, 25).map(p => (
                  <button key={p.id} onClick={() => { setPlayerId(p.id); setPlayerSearch(p.display_name || p.name) }}
                    className={`w-full text-left px-3 py-2 text-[13px] transition-colors ${playerId === p.id ? 'bg-pb-accent/15 text-white/90' : 'text-white/70 hover:bg-white/5'}`}>
                    {p.display_name || p.name}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <input type="text" value={nameOverride} onChange={e => setNameOverride(e.target.value)}
              placeholder="Recipient name…"
              className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20" />
          )}

          <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Optional note (e.g. season highlights)…"
            className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20" />

          {err && <p className="text-[11px] text-red-400/80">{err}</p>}
          <div className="flex items-center gap-2">
            <Btn onClick={handleAdd} disabled={saving}>{saving ? 'Adding…' : 'Add Award'}</Btn>
            <button onClick={() => { setAdding(false); setErr(null); setAwardName(''); setCustomName('') }}
              className="px-3 py-1.5 text-[12px] font-mono text-white/30 hover:text-white/50 transition">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

const SECTION_PRESETS = [
  { type: 'presidents_report',  label: "President's Report" },
  { type: 'treasurers_report',  label: "Treasurer's Report" },
  { type: 'secretarys_report',  label: "Secretary's Report" },
  { type: 'coachs_report',      label: "Coach's Report" },
  { type: 'sponsors_message',   label: "Sponsor's Message" },
  { type: 'custom',             label: 'Custom' },
]

function CustomSectionsPanel({ orgId, seasonId, sections, onRefresh }) {
  const [adding, setAdding] = useState(false)
  const [newType, setNewType] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  // Per-section editor state: { [id]: { content, title, dirty, saving } }
  const [editors, setEditors] = useState({})

  const setEditor = (id, patch) =>
    setEditors(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }))

  const getEditor = (s) =>
    editors[s.id] ?? { content: s.content_markdown || '', title: s.title || '', dirty: false, saving: false }

  // Sync editors when sections reload
  useEffect(() => {
    setEditors(prev => {
      const next = { ...prev }
      sections.forEach(s => {
        if (!next[s.id]) {
          next[s.id] = { content: s.content_markdown || '', title: s.title || '', dirty: false, saving: false }
        }
      })
      return next
    })
  }, [sections])

  const handleCreate = async () => {
    if (!newType) return
    const preset = SECTION_PRESETS.find(p => p.type === newType)
    const title = newType === 'custom' ? (newTitle.trim() || 'Custom Section') : preset.label
    setCreating(true)
    try {
      await api.createYearbookSection(orgId, seasonId, {
        section_type: newType,
        title,
        content_markdown: '',
        sort_order: sections.length,
        is_enabled: false,
      })
      setAdding(false)
      setNewType('')
      setNewTitle('')
      onRefresh()
    } catch (e) {
      console.error(e)
    } finally {
      setCreating(false)
    }
  }

  const handleSave = async (s) => {
    const ed = getEditor(s)
    setEditor(s.id, { saving: true })
    try {
      await api.updateYearbookSection(orgId, seasonId, s.id, {
        section_type: s.section_type,
        title: ed.title,
        content_markdown: ed.content,
        sort_order: s.sort_order,
        is_enabled: s.is_enabled,
      })
      setEditor(s.id, { dirty: false, saving: false })
      onRefresh()
    } catch (e) {
      setEditor(s.id, { saving: false })
    }
  }

  const handleToggle = async (s) => {
    const ed = getEditor(s)
    try {
      await api.updateYearbookSection(orgId, seasonId, s.id, {
        section_type: s.section_type,
        title: ed.title,
        content_markdown: ed.content,
        sort_order: s.sort_order,
        is_enabled: !s.is_enabled,
      })
      onRefresh()
    } catch (e) {
      console.error(e)
    }
  }

  const handleDelete = async (s) => {
    if (!confirm(`Delete "${s.title}"? This cannot be undone.`)) return
    try {
      await api.deleteYearbookSection(orgId, seasonId, s.id)
      onRefresh()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-[13px] font-semibold text-white/90">Editorial Sections</h2>
          <p className="text-[11px] text-white/40 mt-0.5">
            Optional club reports shown on the public yearbook — toggle each one on/off.
          </p>
        </div>
        {!adding && (
          <Btn onClick={() => setAdding(true)}>+ Add Section</Btn>
        )}
      </div>

      {/* Existing sections */}
      {sections.length === 0 && !adding && (
        <p className="text-[12px] text-white/25 italic mb-3">No sections yet. Add a President's Report, Sponsor's Message, or any custom section.</p>
      )}

      <div className="space-y-4">
        {sections.map(s => {
          const ed = getEditor(s)
          return (
            <div key={s.id} className="rounded-lg border border-white/8 bg-white/2 p-4">
              {/* Section header */}
              <div className="flex items-center gap-3 mb-3">
                <input
                  type="text"
                  value={ed.title}
                  onChange={e => setEditor(s.id, { title: e.target.value, dirty: true })}
                  className="flex-1 bg-transparent border-b border-white/10 focus:border-white/25 text-[13px] font-semibold text-white/80 py-0.5 focus:outline-none"
                />
                {/* Toggle */}
                <button
                  onClick={() => handleToggle(s)}
                  title={s.is_enabled ? 'Visible on public page' : 'Hidden — toggle to show'}
                  className={`shrink-0 px-2.5 py-1 rounded border text-[10px] font-mono transition-colors ${
                    s.is_enabled
                      ? 'border-green-500/30 text-green-400 bg-green-500/10'
                      : 'border-white/15 text-white/30 hover:border-white/25'
                  }`}
                >
                  {s.is_enabled ? 'ON' : 'OFF'}
                </button>
                <button
                  onClick={() => handleDelete(s)}
                  className="shrink-0 text-white/20 hover:text-red-400/70 transition text-[12px] font-mono"
                  title="Delete section"
                >
                  Delete
                </button>
              </div>

              {/* Content textarea */}
              <textarea
                value={ed.content}
                onChange={e => setEditor(s.id, { content: e.target.value, dirty: true })}
                rows={7}
                placeholder="Write your content here…"
                className="w-full rounded bg-white/5 border border-white/10 text-white/75 text-sm px-3 py-2.5 resize-y font-sans leading-relaxed focus:outline-none focus:border-white/25 placeholder:text-white/20"
              />

              <div className="flex items-center justify-between mt-2.5">
                <span className="text-[10px] font-mono text-white/20">
                  {ed.content.length} chars
                  {ed.dirty && <span className="ml-2 text-amber-400/60">· unsaved</span>}
                </span>
                <Btn onClick={() => handleSave(s)} disabled={ed.saving || !ed.dirty}>
                  {ed.saving ? 'Saving…' : 'Save'}
                </Btn>
              </div>
            </div>
          )
        })}
      </div>

      {/* Add section form */}
      {adding && (
        <div className="mt-4 rounded-lg border border-white/10 bg-white/3 p-4 space-y-3">
          <p className="text-[12px] font-semibold text-white/70">Choose section type</p>
          <div className="flex flex-wrap gap-2">
            {SECTION_PRESETS.map(p => (
              <button
                key={p.type}
                onClick={() => setNewType(p.type)}
                className={`px-3 py-1.5 rounded border text-[12px] font-mono transition-colors ${
                  newType === p.type
                    ? 'border-pb-accent/50 text-pb-accent bg-pb-accent/10'
                    : 'border-white/15 text-white/40 hover:border-white/25 hover:text-white/60'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {newType === 'custom' && (
            <input
              type="text"
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              placeholder="Section title…"
              className="w-full rounded bg-white/5 border border-white/10 text-white/80 text-[13px] px-3 py-2 focus:outline-none focus:border-white/25 placeholder:text-white/20"
            />
          )}
          <div className="flex items-center gap-2">
            <Btn onClick={handleCreate} disabled={creating || !newType}>
              {creating ? 'Creating…' : 'Create Section'}
            </Btn>
            <button
              onClick={() => { setAdding(false); setNewType(''); setNewTitle('') }}
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

      {/* Hero Image */}
      <HeroImagePanel
        orgId={org.id}
        seasonId={seasonId}
        heroPath={yearbook.hero_image_path}
        onRefresh={load}
      />

      {/* Gallery */}
      <GalleryPanel
        orgId={org.id}
        seasonId={seasonId}
        images={yearbook.images || []}
        onRefresh={load}
      />

      {/* Club Awards */}
      <ClubAwardsPanel
        orgId={org.id}
        seasonId={seasonId}
        awards={yearbook.awards || []}
        players={players}
        onRefresh={load}
      />

      {/* Editorial Sections */}
      <CustomSectionsPanel
        orgId={org.id}
        seasonId={seasonId}
        sections={(yearbook.sections || []).filter(s => s.section_type !== 'narrative')}
        onRefresh={load}
      />

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
