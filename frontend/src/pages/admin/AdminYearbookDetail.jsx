import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner, Btn } from '../../lib/presskit'
import ImageEditorModal from '../../components/ImageEditorModal'

// Yearbook image paths can be either legacy on-disk relative paths
// ("yearbooks/{org_id}/...") or new DB-backed serving URLs ("/api/images/...").
const imageSrc = (p) => !p ? null : (p.startsWith('/') ? p : `/uploads/${p}`)

const AWARD_PRESETS = [
  'Best & Fairest', 'Best Batter', 'Best Bowler', 'Best Fieldsman',
  'Club Champion', 'Rookie of the Year', 'Most Improved',
  'Most Valuable Player', "Club Person of the Year", "President's Award", 'Custom',
]

function Chevron({ open }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>
      <path d="M2.5 5L7 9.5L11.5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

function HeroImagePanel({ orgId, seasonId, heroPath, onRefresh }) {
  const inputRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState(null)
  const [collapsed, setCollapsed] = useState(false)
  const [editorSource, setEditorSource] = useState(null)

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) setEditorSource(file)
  }

  const uploadFile = async (file) => {
    setEditorSource(null)
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
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between mb-1 group"
      >
        <h2 className="text-[13px] font-semibold text-white/90">Hero Image</h2>
        <span className="text-white/30 group-hover:text-white/60 transition"><Chevron open={!collapsed} /></span>
      </button>
      {!collapsed && (
        <>
          <p className="text-[11px] text-white/40 mb-4">Shown as the yearbook cover background. Landscape photos work best.</p>
          {heroPath ? (
            <div className="mb-3">
              <img
                src={imageSrc(heroPath)}
                alt="Hero"
                className="w-full max-h-48 object-cover rounded-lg border border-white/10"
              />
              <div className="flex gap-2 mt-2">
                <Btn onClick={() => inputRef.current?.click()} disabled={uploading}>
                  {uploading ? 'Uploading…' : 'Replace'}
                </Btn>
                <Btn onClick={() => setEditorSource(imageSrc(heroPath))} disabled={uploading}>
                  Edit
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
        </>
      )}
      <ImageEditorModal
        open={!!editorSource}
        source={editorSource}
        title="Edit Hero Image"
        aspect={null}
        outputType="image/jpeg"
        outputName="hero.jpg"
        allowBackgroundRemoval={false}
        onCancel={() => setEditorSource(null)}
        onApply={uploadFile}
      />
    </div>
  )
}

function GalleryPanel({ orgId, seasonId, images, onRefresh }) {
  const inputRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [err, setErr] = useState(null)
  const [collapsed, setCollapsed] = useState(false)
  const [editorQueue, setEditorQueue] = useState([])

  const galleryImages = images.filter(i => i.image_type === 'gallery')

  const handleFile = (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (!files.length) return
    setEditorQueue(files)
  }

  const uploadOne = async (file) => {
    setUploading(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await api.uploadYearbookGallery(orgId, seasonId, fd)
      onRefresh()
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setUploading(false)
    }
  }

  const advanceQueue = () => setEditorQueue(q => q.slice(1))

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
      <div className="flex items-center justify-between mb-1">
        <button onClick={() => setCollapsed(c => !c)} className="flex items-center gap-2 group flex-1 text-left">
          <h2 className="text-[13px] font-semibold text-white/90">Photo Gallery</h2>
          <span className="text-white/30 group-hover:text-white/60 transition"><Chevron open={!collapsed} /></span>
        </button>
        {!collapsed && (
          <Btn onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? 'Uploading…' : '+ Add Photos'}
          </Btn>
        )}
      </div>
      {!collapsed && (
        <>
          <p className="text-[11px] text-white/40 mt-0.5 mb-3">Team photos, match shots, presentations — shown on the public yearbook.</p>
          {galleryImages.length > 0 ? (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-2">
              {galleryImages.map(img => (
                <div key={img.id} className="relative group aspect-square">
                  <img
                    src={imageSrc(img.file_path)}
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
        </>
      )}
      <ImageEditorModal
        open={editorQueue.length > 0}
        source={editorQueue[0]}
        title={editorQueue.length > 1 ? `Edit Photo (${editorQueue.length} queued)` : 'Edit Photo'}
        aspect={null}
        outputType="image/jpeg"
        outputName={editorQueue[0]?.name || 'photo.jpg'}
        allowBackgroundRemoval={false}
        onCancel={advanceQueue}
        onApply={async (file) => {
          advanceQueue()
          await uploadOne(file)
        }}
      />
    </div>
  )
}

function ClubAwardsPanel({ orgId, seasonId, awards, pulledAwards, featuredIds, players, onRefresh }) {
  const [collapsed, setCollapsed] = useState(false)
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
  const [toggling, setToggling] = useState(null)
  const [err, setErr] = useState(null)

  const featuredSet = new Set(featuredIds || [])

  const handleToggleFeatured = async (a) => {
    setToggling(a.id)
    try {
      if (featuredSet.has(String(a.id))) {
        await api.removeFeaturedAchievement(orgId, seasonId, a.id)
      } else {
        await api.addFeaturedAchievement(orgId, seasonId, a.id)
      }
      onRefresh()
    } catch (ex) { setErr(ex.message) }
    finally { setToggling(null) }
  }

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

  const pulled = pulledAwards || []
  const totalCount = awards.length + pulled.length

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 mb-4">
      <div className="flex items-center justify-between mb-1">
        <button onClick={() => setCollapsed(c => !c)} className="flex items-center gap-2 group flex-1 text-left">
          <h2 className="text-[13px] font-semibold text-white/90">Club Awards</h2>
          <span className="text-white/30 group-hover:text-white/60 transition"><Chevron open={!collapsed} /></span>
        </button>
        {!collapsed && !adding && <Btn onClick={() => { setAdding(true); setErr(null) }}>+ Add Award</Btn>}
      </div>
      {!collapsed && (
        <p className="text-[11px] text-white/40 mt-0.5 mb-4">
          {totalCount === 0 ? 'Season award winners — shown on the Awards tab.' : `${totalCount} award${totalCount !== 1 ? 's' : ''} for this season`}
          {pulled.length > 0 && (
            <span className="ml-1 text-white/30">
              · {pulled.length} from <Link to="/admin/awards" className="text-pb-accent/70 hover:text-pb-accent underline-offset-2 hover:underline">Awards admin</Link>
            </span>
          )}
        </p>
      )}

      {!collapsed && pulled.length > 0 && (
        <>
          <p className="text-[10px] font-mono text-white/25 uppercase tracking-wide mb-1.5">
            Toggle awards to display them in the yearbook overview
          </p>
          {err && <p className="text-[11px] text-red-400/80 mb-2">{err}</p>}
          <div className="mb-4 divide-y divide-white/5 rounded-lg border border-white/8 overflow-hidden">
            {pulled.map(a => {
              const isFeatured = featuredSet.has(String(a.id))
              const isToggling = toggling === a.id
              return (
                <div key={`pulled-${a.id}`} className={`flex items-center gap-3 px-4 py-3 transition-colors ${isFeatured ? 'bg-pb-accent/5' : 'bg-white/[0.015]'}`}>
                  {/* Toggle switch */}
                  <button
                    onClick={() => handleToggleFeatured(a)}
                    disabled={isToggling}
                    title={isFeatured ? 'Hide from overview' : 'Show in overview'}
                    className="shrink-0 disabled:opacity-40"
                    aria-label={isFeatured ? 'Hide from overview' : 'Show in overview'}
                  >
                    <span className={`relative inline-flex h-5 w-9 items-center rounded-full border transition-colors duration-200 ${
                      isFeatured ? 'bg-pb-accent border-pb-accent' : 'bg-white/10 border-white/15'
                    }`}>
                      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform duration-200 ${
                        isToggling ? 'opacity-50' : ''
                      } ${isFeatured ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
                    </span>
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[10px] text-white/40 uppercase tracking-wide">
                        {a.achievement}
                      </span>
                      {a.subcategory && (
                        <span className="font-mono text-[10px] text-white/25">· {a.subcategory}</span>
                      )}
                      <span className="font-mono text-[9px] text-pb-accent/60 border border-pb-accent/25 rounded px-1.5 py-px tracking-wide">
                        {a.category?.toUpperCase()}
                      </span>
                    </div>
                    <div className="text-[13px] text-white/80 mt-0.5">{a.player_name || '—'}</div>
                    {a.detail && <div className="text-[11px] text-white/35 mt-0.5 italic">{a.detail}</div>}
                  </div>
                  <Link
                    to="/admin/awards"
                    className="shrink-0 text-white/25 hover:text-white/60 transition text-[11px] font-mono"
                    title="Manage in Awards admin"
                  >
                    Edit →
                  </Link>
                </div>
              )
            })}
          </div>
        </>
      )}

      {!collapsed && awards.length > 0 && (
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

      {!collapsed && adding && (
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
  const [collapsed, setCollapsed] = useState(false)
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
      <div className="flex items-center justify-between mb-1">
        <button onClick={() => setCollapsed(c => !c)} className="flex items-center gap-2 group flex-1 text-left">
          <h2 className="text-[13px] font-semibold text-white/90">Editorial Sections</h2>
          <span className="text-white/30 group-hover:text-white/60 transition"><Chevron open={!collapsed} /></span>
        </button>
        {!collapsed && !adding && (
          <Btn onClick={() => setAdding(true)}>+ Add Section</Btn>
        )}
      </div>

      {!collapsed && (
        <p className="text-[11px] text-white/40 mt-0.5 mb-4">
          Optional club reports shown on the public yearbook — toggle each one on/off.
        </p>
      )}

      {/* Existing sections */}
      {!collapsed && sections.length === 0 && !adding && (
        <p className="text-[12px] text-white/25 italic mb-3">No sections yet. Add a President's Report, Sponsor's Message, or any custom section.</p>
      )}

      {!collapsed && <div className="space-y-4">
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
      </div>}

      {/* Add section form */}
      {!collapsed && adding && (
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
  const [narrativeCollapsed, setNarrativeCollapsed] = useState(false)

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
        <div className="flex items-center justify-between mb-1">
          <button onClick={() => setNarrativeCollapsed(c => !c)} className="flex items-center gap-2 group flex-1 text-left">
            <h2 className="text-[13px] font-semibold text-white/90">Season Narrative</h2>
            <span className="text-white/30 group-hover:text-white/60 transition"><Chevron open={!narrativeCollapsed} /></span>
          </button>
          {!narrativeCollapsed && (
            <Btn onClick={generateNarrative} disabled={generating} className="shrink-0">
              {generating ? 'Generating…' : hasAiDraft ? 'Regenerate' : 'Generate AI Draft'}
            </Btn>
          )}
        </div>
        {!narrativeCollapsed && (
          <>
            <p className="text-[11px] text-white/40 mt-0.5 mb-3">
              {hasSaved ? 'Saved — shown publicly when yearbook is published.'
                : hasAiDraft ? 'AI draft ready — edit and save to publish.'
                : 'Generate an AI draft then edit before saving.'}
            </p>
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
          </>
        )}
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
        pulledAwards={yearbook.pulled_awards || []}
        featuredIds={yearbook.featured_achievement_ids || []}
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

    </div>
  )
}
