import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useToast } from '../../contexts/ToastContext'

const SLIDE_TYPE_INFO = {
  sponsors: { label: 'Sponsors', desc: 'One slide per sponsor with a logo, in your Sponsors order.', module: null },
  fixtures: { label: 'Fixtures & Lineups', desc: 'Your next upcoming fixtures, with the saved lineup when one exists.', module: 'select' },
  social_posts: { label: 'Recent Social Posts', desc: 'Posts saved from the Post Designer with "Save to Club Room".', module: 'socials' },
  custom_images: { label: 'Custom Images', desc: 'Any images you upload below, like action shots or club notices.', module: null },
}

export default function AdminClubRoom() {
  const toast = useToast()
  const { hasModule } = useAuth()
  const [settings, setSettings] = useState(null)
  const [slides, setSlides] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingSettings, setSavingSettings] = useState(false)
  const [rotationInput, setRotationInput] = useState('15')
  const [editing, setEditing] = useState({}) // { [id]: { title, duration_seconds, config } }
  const [adding, setAdding] = useState(null) // slide_type being added
  const [customMedia, setCustomMedia] = useState([])
  const [socialMedia, setSocialMedia] = useState([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const dragItem = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await api.clubRoomGetSettings()
      setSettings({ enabled: data.enabled, rotation_seconds: data.rotation_seconds })
      setRotationInput(String(data.rotation_seconds))
      setSlides(data.slides)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadMedia() {
    setMediaLoading(true)
    try {
      const [custom, social] = await Promise.all([
        api.clubRoomListMedia('upload'),
        api.clubRoomListMedia('social_export'),
      ])
      setCustomMedia(custom)
      setSocialMedia(social)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setMediaLoading(false)
    }
  }

  useEffect(() => { loadMedia() }, [])

  async function patchSettings(patch) {
    setSavingSettings(true)
    try {
      const updated = await api.clubRoomPatchSettings(patch)
      setSettings(updated)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSavingSettings(false)
    }
  }

  async function addSlide(slideType) {
    setAdding(slideType)
    try {
      const slide = await api.clubRoomCreateSlide({ slide_type: slideType })
      setSlides(prev => [...prev, slide])
    } catch (e) {
      toast.error(e.message)
    } finally {
      setAdding(null)
    }
  }

  function startEdit(slide) {
    setEditing(prev => ({
      ...prev,
      [slide.id]: { title: slide.title || '', duration_seconds: slide.duration_seconds || '', config: { ...slide.config } },
    }))
  }

  function cancelEdit(id) {
    setEditing(prev => { const n = { ...prev }; delete n[id]; return n })
  }

  async function saveEdit(id) {
    const vals = editing[id]
    if (!vals) return
    try {
      const updated = await api.clubRoomPatchSlide(id, {
        title: vals.title.trim() || null,
        duration_seconds: vals.duration_seconds ? Number(vals.duration_seconds) : null,
        config: vals.config,
      })
      setSlides(prev => prev.map(s => s.id === id ? updated : s))
      cancelEdit(id)
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function toggleEnabled(slide) {
    try {
      const updated = await api.clubRoomPatchSlide(slide.id, { enabled: !slide.enabled })
      setSlides(prev => prev.map(s => s.id === slide.id ? updated : s))
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function deleteSlide(id) {
    if (!confirm('Remove this from the playlist?')) return
    try {
      await api.clubRoomDeleteSlide(id)
      setSlides(prev => prev.filter(s => s.id !== id))
    } catch (e) {
      toast.error(e.message)
    }
  }

  function onDragStart(index) { dragItem.current = index }
  function onDragEnter(index) {
    if (dragItem.current === null || dragItem.current === index) return
    setSlides(prev => {
      const next = [...prev]
      const dragged = next.splice(dragItem.current, 1)[0]
      next.splice(index, 0, dragged)
      dragItem.current = index
      return next
    })
  }
  async function onDragEnd() {
    dragItem.current = null
    try {
      await api.clubRoomReorderSlides(slides.map((s, i) => ({ id: s.id, position: i })))
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      const media = await api.clubRoomUploadMedia(file)
      setCustomMedia(prev => [media, ...prev])
      toast.success('Image uploaded')
    } catch (e2) {
      toast.error(e2.message)
    } finally {
      setUploading(false)
    }
  }

  async function deleteMedia(id, isCustom) {
    if (!confirm('Delete this image?')) return
    try {
      await api.clubRoomDeleteMedia(id)
      if (isCustom) setCustomMedia(prev => prev.filter(m => m.id !== id))
      else setSocialMedia(prev => prev.filter(m => m.id !== id))
    } catch (e) {
      toast.error(e.message)
    }
  }

  const availableTypes = Object.entries(SLIDE_TYPE_INFO).filter(
    ([, info]) => !info.module || hasModule(info.module)
  )

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Club Room Mode</h1>
          <a
            href="/admin/club-room/play"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-1.5 rounded text-sm font-medium bg-pb-accent text-white"
          >
            Launch on this screen ↗
          </a>
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Build a rotating slideshow of sponsors, fixtures, lineups, social posts and your own images,
          then leave it running full-screen on a TV in the club room. Open "Launch on this screen" on the
          TV's browser and it takes care of itself from there.
        </p>

        {!loading && settings && (
          <div className="pb-card px-4 py-4 mb-6 flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="text-pb-text text-sm font-medium">Turn Club Room Mode on</div>
              <div className="text-pb-faintest text-[11px] mt-0.5">The launch page shows an "off" message until this is on.</div>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-[11px] font-mono text-pb-faint">
                DEFAULT SECONDS PER SLIDE
                <input
                  type="number" min={3} max={300} value={rotationInput}
                  onChange={e => setRotationInput(e.target.value)}
                  onBlur={() => {
                    const n = Number(rotationInput)
                    if (n && n !== settings.rotation_seconds) patchSettings({ rotation_seconds: n })
                  }}
                  className="w-16 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center"
                />
              </label>
              <button
                onClick={() => patchSettings({ enabled: !settings.enabled })}
                disabled={savingSettings}
                className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                  settings.enabled ? 'bg-pb-accent text-white' : 'border pb-hairline text-pb-faint hover:text-pb-text'
                }`}
              >
                {settings.enabled ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
        )}

        {/* Playlist */}
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Playlist</h2>
        {!loading && (
          <div className="pb-card overflow-hidden mb-3">
            {slides.length === 0 && (
              <div className="px-4 py-8 text-center font-mono text-[11px] text-pb-faint">
                Empty. Add something to show below.
              </div>
            )}
            {slides.map((slide, i) => {
              const info = SLIDE_TYPE_INFO[slide.slide_type] || { label: slide.slide_type }
              const isEditing = !!editing[slide.id]
              return (
                <div
                  key={slide.id}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragEnter={() => onDragEnter(i)}
                  onDragEnd={onDragEnd}
                  onDragOver={e => e.preventDefault()}
                  className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 ${slide.enabled ? '' : 'opacity-50'}`}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-pb-faintest mt-1 select-none text-xs cursor-grab">⠿</span>
                    <div className="flex-1 min-w-0">
                      {isEditing ? (
                        <div className="space-y-1.5">
                          <input
                            value={editing[slide.id].title}
                            onChange={e => setEditing(prev => ({ ...prev, [slide.id]: { ...prev[slide.id], title: e.target.value } }))}
                            placeholder={info.label}
                            className="w-full px-2 py-1 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                          />
                          <div className="flex items-center gap-3 flex-wrap">
                            <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint">
                              SECONDS (default {settings?.rotation_seconds})
                              <input
                                type="number" min={3} max={300}
                                value={editing[slide.id].duration_seconds}
                                onChange={e => setEditing(prev => ({ ...prev, [slide.id]: { ...prev[slide.id], duration_seconds: e.target.value } }))}
                                className="w-16 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center"
                              />
                            </label>
                            {(slide.slide_type === 'fixtures' || slide.slide_type === 'social_posts' || slide.slide_type === 'custom_images') && (
                              <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint">
                                {slide.slide_type === 'fixtures' ? 'HOW MANY FIXTURES' : 'HOW MANY IMAGES'}
                                <input
                                  type="number" min={1} max={30}
                                  value={editing[slide.id].config.count ?? ''}
                                  onChange={e => setEditing(prev => ({
                                    ...prev,
                                    [slide.id]: { ...prev[slide.id], config: { ...prev[slide.id].config, count: e.target.value ? Number(e.target.value) : undefined } },
                                  }))}
                                  className="w-14 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center"
                                />
                              </label>
                            )}
                          </div>
                          <div className="flex gap-2 pt-1">
                            <button onClick={() => saveEdit(slide.id)} className="px-3 py-1 text-xs rounded bg-pb-accent text-white">Save</button>
                            <button onClick={() => cancelEdit(slide.id)} className="px-3 py-1 text-xs rounded border pb-hairline text-pb-faint hover:text-pb-text">Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="text-pb-text text-sm font-medium">{slide.title || info.label}</div>
                          <div className="text-pb-faintest text-[11px] mt-0.5">
                            {info.label} · {slide.duration_seconds || settings?.rotation_seconds}s per slide
                            {slide.config?.count ? ` · up to ${slide.config.count}` : ''}
                          </div>
                        </>
                      )}
                    </div>
                    {!isEditing && (
                      <div className="flex flex-col gap-1 shrink-0">
                        <button onClick={() => startEdit(slide)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline">EDIT</button>
                        <button onClick={() => toggleEnabled(slide)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline">
                          {slide.enabled ? 'HIDE' : 'SHOW'}
                        </button>
                        <button onClick={() => deleteSlide(slide.id)} className="font-mono text-[10px] text-red-400 hover:text-red-300 px-2 py-1 rounded border border-red-400/30">DELETE</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="pb-card px-4 py-4 mb-8">
          <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">Add to playlist</h2>
          <div className="grid sm:grid-cols-2 gap-2">
            {availableTypes.map(([key, info]) => (
              <button
                key={key}
                onClick={() => addSlide(key)}
                disabled={adding === key}
                className="text-left px-3 py-2.5 rounded border pb-hairline hover:border-pb-accent transition-colors disabled:opacity-50"
              >
                <div className="text-pb-text text-sm font-medium">+ {info.label}</div>
                <div className="text-pb-faintest text-[11px] mt-0.5">{info.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Custom image library */}
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Custom images</h2>
        <p className="text-pb-faintest text-[11px] mb-3">
          Upload action shots or anything else you want in rotation, then add a "Custom Images" entry above.
        </p>
        <div className="pb-card px-4 py-4 mb-8">
          <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={handleUpload} />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-4 py-2 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-50 mb-3"
          >
            {uploading ? 'Uploading…' : 'Upload image'}
          </button>
          {!mediaLoading && customMedia.length === 0 && (
            <p className="text-pb-faintest text-[11px]">No custom images yet.</p>
          )}
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            {customMedia.map(m => (
              <div key={m.id} className="relative group aspect-square bg-pb-surface2 rounded overflow-hidden">
                <img src={m.url} alt={m.caption || ''} className="w-full h-full object-cover" />
                <button
                  onClick={() => deleteMedia(m.id, true)}
                  className="absolute top-1 right-1 w-6 h-6 grid place-items-center rounded-full bg-black/60 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Saved social posts */}
        {hasModule('socials') && (
          <>
            <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Saved social posts</h2>
            <p className="text-pb-faintest text-[11px] mb-3">
              Saved from the Post Designer's "Save to Club Room" button. Add a "Recent Social Posts" entry above to show them.
            </p>
            <div className="pb-card px-4 py-4 mb-8">
              {!mediaLoading && socialMedia.length === 0 && (
                <p className="text-pb-faintest text-[11px]">Nothing saved yet.</p>
              )}
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {socialMedia.map(m => (
                  <div key={m.id} className="relative group aspect-square bg-pb-surface2 rounded overflow-hidden">
                    <img src={m.url} alt={m.caption || ''} className="w-full h-full object-cover" />
                    <button
                      onClick={() => deleteMedia(m.id, false)}
                      className="absolute top-1 right-1 w-6 h-6 grid place-items-center rounded-full bg-black/60 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </BetterStatsLayout>
  )
}
