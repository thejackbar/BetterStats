import { useState, useEffect, useRef } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { validateImageFile } from '../../../lib/validation'
import ImageEditorModal from '../../../components/ImageEditorModal'
import RichTextEditor from '../../../components/website/RichTextEditor'
import { useFlash, Flash, inputCls, btnPrimary } from './adminParts'

// Hero banner crop ratio — wide landscape; matches the public hero layout.
const HERO_ASPECT = 8 / 3  // 1600 × 600 px

const SOCIAL_FIELDS = [
  ['facebook', 'Facebook URL'],
  ['instagram', 'Instagram URL'],
  ['x', 'X (Twitter) URL'],
  ['youtube', 'YouTube URL'],
  ['tiktok', 'TikTok URL'],
  ['website', 'Other website URL'],
]

export default function WebsiteSettings() {
  const toast = useToast()
  const [flash, showFlash] = useFlash()
  const [loaded, setLoaded] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [tagline, setTagline] = useState('')
  const [intro, setIntro] = useState('')
  const [social, setSocial] = useState({})
  const [heroUrl, setHeroUrl] = useState(null)
  const [heroAllPages, setHeroAllPages] = useState(false)
  const [heroUploading, setHeroUploading] = useState(false)
  const [heroEditorSource, setHeroEditorSource] = useState(null)
  const heroFileRef = useRef(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.webAdminSettings().then(s => {
      setEnabled(!!s.enabled)
      setTagline(s.tagline || '')
      setIntro(s.intro || '')
      setSocial(s.social || {})
      setHeroUrl(s.hero_image_url || null)
      setHeroAllPages(!!s.hero_all_pages)
      setLoaded(true)
    }).catch(e => toast.error(e.message))
  }, [])

  async function save() {
    setSaving(true)
    try {
      await api.webAdminSaveSettings({ enabled, tagline, intro, social, hero_all_pages: heroAllPages })
      showFlash('Website settings saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function uploadHero(file) {
    setHeroUploading(true)
    try {
      const r = await api.webAdminUploadHero(file)
      setHeroUrl(r.hero_image_url)
      showFlash('Hero image updated')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setHeroUploading(false)
    }
  }

  async function removeHero() {
    try { await api.webAdminDeleteHero(); setHeroUrl(null); showFlash('Hero image removed') }
    catch (e) { toast.error(e.message) }
  }

  if (!loaded) return <p className="text-pb-faint text-sm">Loading…</p>

  return (
    <div className="space-y-6">
      <Flash msg={flash} />

      {/* Enable */}
      <div className="pb-card p-4 flex items-start justify-between gap-4">
        <div>
          <div className="font-medium text-pb-text">Publish the website</div>
          <p className="text-pb-faint text-sm mt-0.5">
            When on, a <span className="font-mono text-pb-dim">Website</span> link appears on your public club nav and
            visitors can browse it. Off keeps it hidden while you build it out.
          </p>
        </div>
        <button
          onClick={() => setEnabled(e => !e)}
          className={`shrink-0 w-12 h-7 rounded-full transition-colors relative ${enabled ? 'bg-pb-accent' : 'bg-pb-surface2'}`}
          style={enabled ? { background: 'var(--pb-accent)' } : {}}
          aria-pressed={enabled}
        >
          <span className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all ${enabled ? 'left-6' : 'left-1'}`} />
        </button>
      </div>

      {/* Hero */}
      <div className="pb-card p-4">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-1">Hero image</h3>
        <p className="text-pb-faintest text-[11px] mb-3">
          Use a wide landscape photo (e.g. your ground) — at least <span className="text-pb-faint font-medium">1600 × 600 px</span>, bigger is sharper. You'll crop to a 8:3 banner, shown exactly as cropped. Max 6 MB.
        </p>
        <div className="aspect-[8/3] rounded-lg overflow-hidden bg-pb-surface2 mb-3 flex items-center justify-center">
          {heroUrl
            ? <img src={heroUrl} alt="Hero" className="w-full h-full object-cover" />
            : <span className="text-pb-faintest font-mono text-[11px]">NO HERO IMAGE</span>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => heroFileRef.current?.click()}
            disabled={heroUploading}
            className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5 disabled:opacity-50"
          >
            {heroUploading ? 'UPLOADING…' : (heroUrl ? 'REPLACE & CROP' : 'UPLOAD & CROP')}
          </button>
          {heroUrl && (
            <button onClick={() => setHeroEditorSource(heroUrl)} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5">
              RE-CROP
            </button>
          )}
          {heroUrl && (
            <button onClick={removeHero} className="font-mono text-[10px] tracking-wide2 text-red-400 hover:text-red-300 border border-red-400/30 rounded px-3 py-1.5">
              REMOVE
            </button>
          )}
        </div>
        <input
          ref={heroFileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
          onChange={e => {
            const f = e.target.files?.[0]; e.target.value = ''
            if (!f) return
            const err = validateImageFile(f)
            if (err) { toast.error(err); return }
            setHeroEditorSource(f)
          }}
        />

        {/* Hero on every page */}
        <label className="flex items-center justify-between gap-4 mt-4 pt-4 border-t pb-hairline-t cursor-pointer">
          <span>
            <span className="block text-sm text-pb-text">Show hero on every page</span>
            <span className="block text-pb-faint text-[12px]">Use it as a banner across News, Pages, Honours, etc. — not just the homepage.</span>
          </span>
          <button
            type="button" onClick={() => setHeroAllPages(v => !v)} aria-pressed={heroAllPages}
            className={`shrink-0 w-12 h-7 rounded-full transition-colors relative ${heroAllPages ? '' : 'bg-pb-surface2'}`}
            style={heroAllPages ? { background: 'var(--pb-accent)' } : {}}
          >
            <span className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all ${heroAllPages ? 'left-6' : 'left-1'}`} />
          </button>
        </label>
      </div>

      {/* Tagline + intro */}
      <div className="pb-card p-4 space-y-4">
        <div>
          <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Tagline</label>
          <input value={tagline} onChange={e => setTagline(e.target.value)} maxLength={200}
            placeholder="e.g. Est. 1952 · 9 men's & 2 women's teams" className={inputCls} />
        </div>
        <div>
          <label className="block font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Welcome / intro</label>
          <RichTextEditor value={intro} onChange={setIntro} placeholder="A short welcome shown on your homepage…" minHeight={160} />
        </div>
      </div>

      {/* Social */}
      <div className="pb-card p-4">
        <h3 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">Social links</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          {SOCIAL_FIELDS.map(([key, label]) => (
            <input
              key={key}
              value={social[key] || ''}
              onChange={e => setSocial(s => ({ ...s, [key]: e.target.value }))}
              placeholder={label}
              className={inputCls}
            />
          ))}
        </div>
        <p className="text-pb-faintest text-[11px] mt-2">Shown as icons in the website footer. Leave blank to hide.</p>
      </div>

      <div className="flex justify-end">
        <button onClick={save} disabled={saving} className={btnPrimary}>{saving ? 'Saving…' : 'Save settings'}</button>
      </div>

      <ImageEditorModal
        open={!!heroEditorSource}
        source={heroEditorSource}
        title="Crop hero image"
        aspect={HERO_ASPECT}
        outputType="image/jpeg"
        outputName="hero.jpg"
        maxOutputSize={2400}
        onCancel={() => setHeroEditorSource(null)}
        onApply={async (file) => { setHeroEditorSource(null); await uploadHero(file) }}
      />
    </div>
  )
}
