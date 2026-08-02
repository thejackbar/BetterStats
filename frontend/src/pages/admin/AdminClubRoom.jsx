import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useToast } from '../../contexts/ToastContext'

const SLIDE_TYPE_INFO = {
  sponsors: { label: 'Sponsors', desc: 'One sponsor, every sponsor in rotation, or every sponsor on one screen.', module: null },
  fixtures: { label: 'Fixtures & Lineups', desc: 'Your next upcoming fixtures, with the saved lineup when one exists.', module: 'select' },
  leaderboard: { label: 'Leaderboard', desc: 'Top run-scorers, wicket-takers or fielders, podium-style.', module: null },
  records: { label: 'Club Records', desc: 'A record category, like Most Runs or Best Bowling Figures.', module: null },
  statlab_report: { label: 'Custom StatLab Report', desc: 'Any report saved and approved in StatLab.', module: null },
  social_posts: { label: 'Recent Social Posts', desc: 'Posts saved from the Post Designer with "Save to Club Room".', module: 'socials' },
  custom_images: { label: 'Custom Images', desc: 'Any images you upload below, like action shots or club notices.', module: null },
}

const BATTING_SORTS = [
  { key: 'total_runs', label: 'Most Runs' }, { key: 'average', label: 'Average' },
  { key: 'high_score', label: 'High Score' }, { key: 'fifties', label: 'Fifties' },
  { key: 'hundreds', label: 'Centuries' }, { key: 'total_sixes', label: 'Sixes' },
  { key: 'total_fours', label: 'Fours' }, { key: 'ducks', label: 'Ducks' },
]
const BOWLING_SORTS = [
  { key: 'total_wickets', label: 'Wickets' }, { key: 'economy', label: 'Economy' },
  { key: 'average', label: 'Average' }, { key: 'best_figures_wickets', label: 'Best Figures' },
  { key: 'five_fors', label: 'Five-fors' }, { key: 'total_maidens', label: 'Maidens' },
]
const FIELDING_SORTS = [
  { key: 'total_catches_non_wk', label: 'Catches' }, { key: 'total_catches_wk', label: 'WK Catches' },
  { key: 'total_run_outs', label: 'Run Outs' }, { key: 'total_stumpings', label: 'Stumpings' },
]
const SORTS_BY_GROUP = { batting: BATTING_SORTS, bowling: BOWLING_SORTS, fielding: FIELDING_SORTS }

const RECORD_CATEGORIES = [
  { key: 'batting.top_career_runs', label: 'Most Runs (Career)' },
  { key: 'batting.top_high_scores', label: 'Highest Individual Scores' },
  { key: 'batting.top_batting_avg', label: 'Best Batting Average' },
  { key: 'batting.most_fifties', label: 'Most Fifties' },
  { key: 'batting.most_hundreds', label: 'Most Centuries' },
  { key: 'batting.most_ducks', label: 'Most Ducks' },
  { key: 'batting.most_runs_season', label: 'Most Runs (Single Season)' },
  { key: 'bowling.top_career_wickets', label: 'Most Wickets (Career)' },
  { key: 'bowling.best_innings_figures', label: 'Best Bowling Figures' },
  { key: 'bowling.top_bowling_avg', label: 'Best Bowling Average' },
  { key: 'bowling.top_economy', label: 'Best Economy Rate' },
  { key: 'bowling.most_five_fors', label: 'Most Five-Wicket Hauls' },
  { key: 'bowling.most_wickets_season', label: 'Most Wickets (Single Season)' },
  { key: 'allrounders.top_allrounders', label: 'Best All-Rounders' },
]

const fieldCls = 'w-full px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent'
const labelCls = 'block text-[10px] font-mono tracking-wide2 text-pb-faint uppercase mb-1'

export default function AdminClubRoom() {
  const toast = useToast()
  const { hasModule } = useAuth()
  const [settings, setSettings] = useState(null)
  const [slides, setSlides] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingSettings, setSavingSettings] = useState(false)
  const [rotationInput, setRotationInput] = useState('15')
  const [editing, setEditing] = useState({}) // { [id]: draft config object }
  const [adding, setAdding] = useState(null)
  const [customMedia, setCustomMedia] = useState([])
  const [socialMedia, setSocialMedia] = useState([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [sponsors, setSponsors] = useState([])
  const [seasons, setSeasons] = useState([])
  const [reports, setReports] = useState([])
  const dragItem = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => { load() }, [])
  useEffect(() => { loadMedia() }, [])
  useEffect(() => {
    api.adminListSponsors().then(setSponsors).catch(() => {})
    api.adminListSeasons().then(setSeasons).catch(() => {})
    api.clubRoomListReports().then(setReports).catch(() => {})
  }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await api.clubRoomGetSettings()
      setSettings({ enabled: data.enabled, rotation_seconds: data.rotation_seconds, theme: data.theme, shuffle: data.shuffle })
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

  function defaultConfigFor(slideType) {
    if (slideType === 'sponsors') return { mode: 'sequence' }
    if (slideType === 'fixtures') return { count: 3 }
    if (slideType === 'leaderboard') return { stat_group: 'batting', sort_by: 'total_runs', season_id: '', limit: 10 }
    if (slideType === 'records') return { category: 'batting.top_career_runs', season_id: '', limit: 8 }
    if (slideType === 'statlab_report') return { report_id: '' }
    return {}
  }

  async function addSlide(slideType) {
    setAdding(slideType)
    try {
      const slide = await api.clubRoomCreateSlide({ slide_type: slideType, config: defaultConfigFor(slideType) })
      setSlides(prev => [...prev, slide])
      startEdit(slide)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setAdding(null)
    }
  }

  function startEdit(slide) {
    setEditing(prev => ({
      ...prev,
      [slide.id]: { title: slide.title || '', duration_seconds: slide.duration_seconds || '', config: { ...defaultConfigFor(slide.slide_type), ...slide.config } },
    }))
  }

  function cancelEdit(id) {
    setEditing(prev => { const n = { ...prev }; delete n[id]; return n })
  }

  function setDraftConfig(id, patch) {
    setEditing(prev => ({ ...prev, [id]: { ...prev[id], config: { ...prev[id].config, ...patch } } }))
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
          Build a rotating slideshow of sponsors, fixtures, lineups, stats and your own images,
          then leave it running full-screen on a TV in the club room. Open "Launch on this screen" on the
          TV's browser and it takes care of itself from there.
        </p>

        {!loading && settings && (
          <div className="pb-card px-4 py-4 mb-6 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="text-pb-text text-sm font-medium">Turn Club Room Mode on</div>
                <div className="text-pb-faintest text-[11px] mt-0.5">The launch page shows an "off" message until this is on.</div>
              </div>
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
            <div className="flex items-center gap-6 flex-wrap pt-3 pb-hairline-t">
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
              <label className="flex items-center gap-2 text-[11px] font-mono text-pb-faint">
                STAGE THEME
                <select
                  value={settings.theme}
                  onChange={e => patchSettings({ theme: e.target.value })}
                  className="px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text"
                >
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-[11px] font-mono text-pb-faint cursor-pointer">
                <input type="checkbox" checked={settings.shuffle} onChange={e => patchSettings({ shuffle: e.target.checked })} />
                SHUFFLE SLIDES
              </label>
            </div>
          </div>
        )}

        <PublicLinkPanel toast={toast} />

        {/* Playlist */}
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Playlist</h2>
        {settings?.shuffle && (
          <p className="text-pb-faintest text-[11px] mb-2">Shuffle is on, so the order below is ignored on the TV. Slides play in a random order each loop.</p>
        )}
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
                  draggable={!settings?.shuffle}
                  onDragStart={() => onDragStart(i)}
                  onDragEnter={() => onDragEnter(i)}
                  onDragEnd={onDragEnd}
                  onDragOver={e => e.preventDefault()}
                  className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 ${slide.enabled ? '' : 'opacity-50'}`}
                >
                  <div className="flex items-start gap-3">
                    {!settings?.shuffle && <span className="text-pb-faintest mt-1 select-none text-xs cursor-grab">⠿</span>}
                    <div className="flex-1 min-w-0">
                      {isEditing ? (
                        <div className="space-y-3">
                          <div>
                            <label className={labelCls}>Slide title (optional)</label>
                            <input
                              value={editing[slide.id].title}
                              onChange={e => setEditing(prev => ({ ...prev, [slide.id]: { ...prev[slide.id], title: e.target.value } }))}
                              placeholder={info.label}
                              className={fieldCls}
                            />
                          </div>

                          <SlideConfigFields
                            slide={slide}
                            draft={editing[slide.id]}
                            setConfig={patch => setDraftConfig(slide.id, patch)}
                            sponsors={sponsors}
                            seasons={seasons}
                            reports={reports}
                            customMedia={customMedia}
                            socialMedia={socialMedia}
                          />

                          <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint">
                            SECONDS (default {settings?.rotation_seconds})
                            <input
                              type="number" min={3} max={300}
                              value={editing[slide.id].duration_seconds}
                              onChange={e => setEditing(prev => ({ ...prev, [slide.id]: { ...prev[slide.id], duration_seconds: e.target.value } }))}
                              className="w-16 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center"
                            />
                          </label>

                          <div className="flex gap-2 pt-1">
                            <button onClick={() => saveEdit(slide.id)} className="px-3 py-1 text-xs rounded bg-pb-accent text-white">Save</button>
                            <button onClick={() => cancelEdit(slide.id)} className="px-3 py-1 text-xs rounded border pb-hairline text-pb-faint hover:text-pb-text">Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="text-pb-text text-sm font-medium">{slide.title || info.label}</div>
                          <div className="text-pb-faintest text-[11px] mt-0.5">
                            {slideSummary(slide, info)} · {slide.duration_seconds || settings?.rotation_seconds}s per slide
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
          <p className="text-pb-faintest text-[11px] mb-3">
            Sponsors can be added more than once. Pick "One sponsor" each time to control which sponsor gets more airtime.
          </p>
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

function slideSummary(slide, info) {
  const cfg = slide.config || {}
  if (slide.slide_type === 'sponsors') {
    if (cfg.mode === 'single') return `${info.label} · one sponsor`
    if (cfg.mode === 'grid') return `${info.label} · all on one screen`
    return `${info.label} · rotating`
  }
  if (slide.slide_type === 'leaderboard') return `${info.label} · ${cfg.stat_group || 'batting'}`
  if (slide.slide_type === 'records') return `${info.label} · ${(RECORD_CATEGORIES.find(c => c.key === cfg.category) || {}).label || ''}`
  if (slide.slide_type === 'statlab_report') return info.label
  if (cfg.media_ids?.length) return `${info.label} · ${cfg.media_ids.length} picked`
  if (cfg.count) return `${info.label} · up to ${cfg.count}`
  return info.label
}

function SlideConfigFields({ slide, draft, setConfig, sponsors, seasons, reports, customMedia, socialMedia }) {
  const cfg = draft.config

  if (slide.slide_type === 'sponsors') {
    return (
      <div className="space-y-2">
        <div>
          <label className={labelCls}>How should sponsors appear?</label>
          <select value={cfg.mode || 'sequence'} onChange={e => setConfig({ mode: e.target.value })} className={fieldCls}>
            <option value="sequence">All sponsors, one at a time</option>
            <option value="single">One sponsor (choose below)</option>
            <option value="grid">All sponsors, on one screen</option>
          </select>
        </div>
        {cfg.mode === 'single' && (
          <div>
            <label className={labelCls}>Sponsor</label>
            <select value={cfg.sponsor_id || ''} onChange={e => setConfig({ sponsor_id: e.target.value })} className={fieldCls}>
              <option value="">Choose a sponsor</option>
              {sponsors.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        )}
      </div>
    )
  }

  if (slide.slide_type === 'fixtures') {
    return (
      <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint">
        HOW MANY FIXTURES
        <input type="number" min={1} max={10} value={cfg.count ?? 3}
          onChange={e => setConfig({ count: e.target.value ? Number(e.target.value) : undefined })}
          className="w-14 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center" />
      </label>
    )
  }

  if (slide.slide_type === 'leaderboard') {
    const statGroup = cfg.stat_group || 'batting'
    const sortOptions = SORTS_BY_GROUP[statGroup] || BATTING_SORTS
    return (
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls}>Stat</label>
          <select value={statGroup} onChange={e => setConfig({ stat_group: e.target.value, sort_by: (SORTS_BY_GROUP[e.target.value] || [])[0]?.key })} className={fieldCls}>
            <option value="batting">Batting</option>
            <option value="bowling">Bowling</option>
            <option value="fielding">Fielding</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Sorted by</label>
          <select value={cfg.sort_by || sortOptions[0].key} onChange={e => setConfig({ sort_by: e.target.value })} className={fieldCls}>
            {sortOptions.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Season</label>
          <select value={cfg.season_id || ''} onChange={e => setConfig({ season_id: e.target.value })} className={fieldCls}>
            <option value="">All-time</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Top N</label>
          <input type="number" min={3} max={20} value={cfg.limit ?? 10}
            onChange={e => setConfig({ limit: e.target.value ? Number(e.target.value) : undefined })} className={fieldCls} />
        </div>
      </div>
    )
  }

  if (slide.slide_type === 'records') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2">
          <label className={labelCls}>Record</label>
          <select value={cfg.category || RECORD_CATEGORIES[0].key} onChange={e => setConfig({ category: e.target.value })} className={fieldCls}>
            {RECORD_CATEGORIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Season</label>
          <select value={cfg.season_id || ''} onChange={e => setConfig({ season_id: e.target.value })} className={fieldCls}>
            <option value="">All-time</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Top N</label>
          <input type="number" min={3} max={15} value={cfg.limit ?? 8}
            onChange={e => setConfig({ limit: e.target.value ? Number(e.target.value) : undefined })} className={fieldCls} />
        </div>
      </div>
    )
  }

  if (slide.slide_type === 'statlab_report') {
    return (
      <div>
        <label className={labelCls}>Saved report</label>
        <select value={cfg.report_id || ''} onChange={e => setConfig({ report_id: e.target.value })} className={fieldCls}>
          <option value="">Choose a report</option>
          {reports.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
        </select>
        {reports.length === 0 && (
          <p className="text-pb-faintest text-[11px] mt-1">No approved saved reports yet. Build and save one in StatLab first.</p>
        )}
      </div>
    )
  }

  if (slide.slide_type === 'social_posts' || slide.slide_type === 'custom_images') {
    const library = slide.slide_type === 'social_posts' ? socialMedia : customMedia
    const picking = !!cfg.media_ids
    return (
      <div className="space-y-2">
        <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint cursor-pointer">
          <input type="checkbox" checked={picking} onChange={e => setConfig({ media_ids: e.target.checked ? [] : undefined, count: e.target.checked ? undefined : 6 })} />
          PICK SPECIFIC {slide.slide_type === 'social_posts' ? 'POSTS' : 'IMAGES'} (INSTEAD OF "MOST RECENT")
        </label>
        {picking ? (
          <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 max-h-56 overflow-y-auto p-1">
            {library.map(m => {
              const picked = (cfg.media_ids || []).includes(m.id)
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setConfig({
                    media_ids: picked ? (cfg.media_ids || []).filter(x => x !== m.id) : [...(cfg.media_ids || []), m.id],
                  })}
                  className={`relative aspect-square rounded overflow-hidden border-2 ${picked ? 'border-pb-accent' : 'border-transparent'}`}
                >
                  <img src={m.url} alt="" className="w-full h-full object-cover" />
                  {picked && <span className="absolute inset-0 bg-black/30 grid place-items-center text-white text-lg">✓</span>}
                </button>
              )
            })}
            {library.length === 0 && <p className="col-span-full text-pb-faintest text-[11px]">Nothing available to pick yet.</p>}
          </div>
        ) : (
          <label className="flex items-center gap-1.5 text-[11px] font-mono text-pb-faint">
            HOW MANY, MOST RECENT FIRST
            <input type="number" min={1} max={30} value={cfg.count ?? (slide.slide_type === 'custom_images' ? 30 : 6)}
              onChange={e => setConfig({ count: e.target.value ? Number(e.target.value) : undefined })}
              className="w-14 px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text text-center" />
          </label>
        )}
      </div>
    )
  }

  return null
}

// Lets a club run the TV off /room/{token} + a PIN, with no admin session on
// that browser — for a Chromebook or smart TV pinned permanently in the club
// room. Mirrors BetterSelect's SelfServiceLinkPanel (link + QR + regenerate),
// rebuilt in this page's own plain-Tailwind style rather than importing that
// component's BetterSelect-specific UI kit.
function PublicLinkPanel({ toast }) {
  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState(null)
  const [pinInput, setPinInput] = useState('')

  const fullUrl = cfg?.link_token ? `${window.location.origin}/room/${cfg.link_token}` : ''

  useEffect(() => {
    api.clubRoomGetPublicLink().then(setCfg).catch(() => {})
  }, [])

  useEffect(() => {
    if (!open || !fullUrl) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(fullUrl, { margin: 1, width: 220, errorCorrectionLevel: 'M' })
      .then(u => { if (alive) setQr(u) })
      .catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [open, fullUrl])

  async function update(patch) {
    setBusy(true)
    try {
      setCfg(await api.clubRoomSetPublicLink(patch))
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function savePin() {
    if (pinInput.length !== 4) return
    await update({ pin: pinInput })
    setPinInput('')
  }

  async function regenerate() {
    if (!confirm("Generate a new link? The old link and QR code will stop working immediately.")) return
    setBusy(true)
    try {
      setCfg(await api.clubRoomRegeneratePublicLink())
      toast.success('New link generated')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function copyText(text, label) {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${label} copied`)
    } catch {
      toast.error('Copy failed. Select and copy manually.')
    }
  }

  if (!cfg) return null
  const enabled = !!cfg.enabled
  const needsPin = enabled && cfg.require_pin && !cfg.has_pin

  return (
    <div className="pb-card mb-6 overflow-hidden">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <div>
          <div className="text-pb-text text-sm font-medium flex items-center gap-2">
            Public link
            <span
              className="font-mono text-[10px] px-2 py-0.5 rounded-full"
              style={enabled
                ? { background: 'color-mix(in srgb, var(--pb-accent) 16%, transparent)', color: 'var(--pb-accent)' }
                : { background: 'var(--pb-surface2)', color: 'var(--pb-faintest)' }}
            >
              {enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="text-pb-faintest text-[11px] mt-0.5">
            Run the show on a club room TV with no one logged in, gated by a PIN.
          </div>
        </div>
        <span className="text-pb-faint">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 pt-3 pb-hairline-t space-y-4">
          <div className="flex items-center gap-6 flex-wrap">
            <label className="flex items-center gap-2 text-[11px] font-mono text-pb-faint">
              STATUS
              <select
                value={enabled ? 'on' : 'off'}
                onChange={e => update({ enabled: e.target.value === 'on' })}
                disabled={busy}
                className="px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text"
              >
                <option value="off">Off</option>
                <option value="on">On</option>
              </select>
            </label>
            {enabled && (
              <label className="flex items-center gap-2 text-[11px] font-mono text-pb-faint">
                PIN
                <select
                  value={cfg.require_pin ? 'pin' : 'nopin'}
                  onChange={e => update({ require_pin: e.target.value === 'pin' })}
                  disabled={busy}
                  className="px-2 py-1 bg-pb-bg border pb-hairline rounded text-pb-text"
                >
                  <option value="pin">Required</option>
                  <option value="nopin">Not required</option>
                </select>
              </label>
            )}
          </div>

          {!enabled ? (
            <p className="text-pb-faint text-sm">
              Turn this on to generate a link for the club room's TV or Chromebook. Once unlocked it stays signed
              in on that browser for about a month, so it survives the TV being switched off and on again.
            </p>
          ) : (
            <>
              {cfg.require_pin && (
                <div>
                  <label className={labelCls}>{cfg.has_pin ? 'Change PIN' : 'Set a 4-digit PIN'}</label>
                  <div className="flex items-center gap-2">
                    <input
                      value={pinInput}
                      onChange={e => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 4))}
                      inputMode="numeric"
                      placeholder="••••"
                      className="w-24 px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text text-center tracking-[0.4em] font-mono"
                    />
                    <button
                      onClick={savePin}
                      disabled={pinInput.length !== 4 || busy}
                      className="px-3 py-1.5 text-xs rounded bg-pb-accent text-white disabled:opacity-50"
                    >
                      {cfg.has_pin ? 'Update PIN' : 'Save PIN'}
                    </button>
                  </div>
                  {needsPin && (
                    <p className="text-[11px] mt-1.5" style={{ color: 'var(--pb-amber)' }}>
                      No PIN set yet, so the link won't unlock for anyone until you set one.
                    </p>
                  )}
                </div>
              )}

              <div>
                <label className={labelCls}>Shareable link</label>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    readOnly
                    value={fullUrl}
                    onFocus={e => e.target.select()}
                    className="flex-1 min-w-[220px] bg-pb-bg border pb-hairline rounded px-3 py-2 text-sm font-mono text-pb-faint"
                  />
                  <button onClick={() => copyText(fullUrl, 'Link')} className="px-3 py-1.5 text-xs rounded border pb-hairline text-pb-faint hover:text-pb-text">
                    Copy link
                  </button>
                  <button onClick={regenerate} disabled={busy} className="px-3 py-1.5 text-xs rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
                    Regenerate
                  </button>
                </div>
                <p className="text-pb-faintest text-[11px] mt-1.5">
                  Bookmark it on the TV's browser, or scan the QR code below from a phone or tablet.
                </p>
              </div>

              {qr && (
                <div>
                  <img src={qr} alt="Club Room link QR code" className="w-36 h-36 rounded-lg bg-white p-2" />
                  <div className="font-mono text-[10px] text-pb-faintest mt-1.5">Scan to open</div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
