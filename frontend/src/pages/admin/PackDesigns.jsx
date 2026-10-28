// Player Cards, pack designs: a club makes its own look for its packs. Pick which pack (every pack, one kind, or a scheduled
// event), upload a background and a centre image, choose colours and how the pack reads, and watch the pack change as you go.
// Style changes save as you make them; pictures upload as soon as they are chosen. A pack with no design keeps the built-in look.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Btn, Card, Field, Select } from '../../lib/presskit'
import { useToast } from '../../contexts/ToastContext'
import { PackArt } from '../../components/cards/PackOpening'
import { PACKS } from '../../components/cards/cardTheme'
import { useCardStyle } from '../../components/cards/useCardStyle'

const IMAGE_TYPES = 'image/png,image/jpeg,image/webp,image/gif'
const BASE = { title: null, a: null, b: null, on: null, overlay: 0.25, show_name: true, show_logo: true, art_position: 'center', art_size: 'm', background_url: null, art_url: null }
const SAVE_DELAY = 450
// The design as the page reads it uses a, b and on; the API names them color_a, color_b and color_on.
const API_KEY = { a: 'color_a', b: 'color_b', on: 'color_on' }
const toApi = (patch) => Object.fromEntries(Object.entries(patch).map(([k, v]) => [API_KEY[k] || k, v]))

function Switch({ on, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)}
        className="mt-0.5 relative shrink-0 w-10 h-6 rounded-full transition"
        style={{ background: on ? 'var(--pb-accent)' : 'var(--pb-hairline2, #475569)' }}>
        <span className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all" style={{ left: on ? 18 : 2 }} />
      </button>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-pb-text">{label}</span>
        {hint && <span className="block text-[12.5px] text-pb-faint mt-0.5">{hint}</span>}
      </span>
    </label>
  )
}

// One picture slot: what is there, a way to choose one, a way to take it away.
function ImageSlot({ kind, title, hint, url, busy, onPick, onRemove }) {
  const input = useRef(null)
  return (
    <div className="rounded-lg border pb-hairline p-3" data-design-slot={kind}>
      <div className="flex items-center gap-3">
        <div className="shrink-0 w-14 h-14 rounded bg-pb-surface2 border pb-hairline overflow-hidden flex items-center justify-center">
          {url ? <img src={url} alt="" className="max-w-full max-h-full object-contain" /> : <span className="text-[10px] text-pb-faint">None</span>}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-pb-text">{title}</div>
          <div className="text-[12px] text-pb-faint">{hint}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mt-2.5">
        <input ref={input} type="file" accept={IMAGE_TYPES} className="hidden" aria-label={`${title} file`} data-design-file={kind}
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onPick(f) }} />
        <Btn sm onClick={() => input.current?.click()} disabled={busy}>{busy ? 'Uploading…' : url ? 'Replace' : 'Choose a picture'}</Btn>
        {url && <Btn sm onClick={onRemove} disabled={busy}>Remove</Btn>}
      </div>
    </div>
  )
}

function ColourRow({ label, value, onChange }) {
  return (
    <div className="flex items-center gap-2" data-design-colour={label}>
      <input type="color" value={value || '#888888'} aria-label={label} onChange={(e) => onChange(e.target.value)}
        className="w-9 h-8 rounded border pb-hairline bg-transparent p-0.5 cursor-pointer" />
      <span className="text-sm text-pb-text flex-1">{label}</span>
      <span className="text-[11.5px] text-pb-faint">{value ? value : 'built in'}</span>
      {value && <button type="button" className="text-[12px] text-pb-accent hover:underline" onClick={() => onChange(null)}>Use built in</button>}
    </div>
  )
}

export default function PackDesigns({ data, setData }) {
  const toast = useToast()
  const { accent, display } = useCardStyle(data.club)
  const targets = data.design_targets || []
  const [target, setTarget] = useState('default')
  const [busy, setBusy] = useState('')
  const [draft, setDraft] = useState({})
  const [confirmReset, setConfirmReset] = useState(false)
  const pending = useRef({})
  const timer = useRef(null)
  const designs = data.designs || {}
  const saved = designs[target] || null
  const current = targets.find((t) => t.key === target) || targets[0]
  const source = target.startsWith('event:') ? 'event' : target === 'default' ? 'weekly' : target

  // A new target, or a design changed from outside, starts the draft from what is saved.
  useEffect(() => { setDraft({}); setConfirmReset(false) }, [target])
  useEffect(() => () => clearTimeout(timer.current), [])

  const design = useMemo(() => ({ ...BASE, ...(saved || {}), ...draft }), [saved, draft])
  const shown = saved || Object.keys(draft).length ? design : null

  const flush = async () => {
    const patch = pending.current
    pending.current = {}
    if (!Object.keys(patch).length) return
    try {
      const out = await api.savePlayerCardDesign(target, toApi(patch))
      setData((d) => ({ ...d, designs: out.designs }))
      setDraft((cur) => { const next = { ...cur }; Object.keys(patch).forEach((k) => { if (next[k] === patch[k]) delete next[k] }); return next })
    } catch (e) {
      setDraft({})
      toast?.error?.(e?.message || 'Could not save that.')
    }
  }
  // Show the change at once, send it a moment later (so dragging a slider is one save, not forty).
  const change = (patch) => {
    setDraft((d) => ({ ...d, ...patch }))
    pending.current = { ...pending.current, ...patch }
    clearTimeout(timer.current)
    timer.current = setTimeout(flush, SAVE_DELAY)
  }
  const upload = async (kind, file) => {
    setBusy(kind)
    try {
      const out = await api.uploadPlayerCardDesignImage(target, kind, file)
      setData((d) => ({ ...d, designs: out.designs }))
      toast?.success?.('Picture saved')
    } catch (e) { toast?.error?.(e?.message || 'That picture could not be saved.') } finally { setBusy('') }
  }
  const removeImage = async (kind) => {
    setBusy(kind)
    try { const out = await api.removePlayerCardDesignImage(target, kind); setData((d) => ({ ...d, designs: out.designs })) } catch (e) { toast?.error?.(e?.message || 'Could not remove that.') } finally { setBusy('') }
  }
  const reset = async () => {
    clearTimeout(timer.current); pending.current = {}
    try { const out = await api.resetPlayerCardDesign(target); setData((d) => ({ ...d, designs: out.designs })); setDraft({}); setConfirmReset(false) } catch (e) { toast?.error?.(e?.message || 'Could not reset that.') }
  }

  const groups = useMemo(() => {
    const out = []
    for (const t of targets) {
      let g = out.find((x) => x.name === t.group)
      if (!g) { g = { name: t.group, items: [] }; out.push(g) }
      g.items.push(t)
    }
    return out
  }, [targets])
  const isEvent = target.startsWith('event:')
  const canName = target !== 'default' && !isEvent

  return (
    <div className="space-y-4" data-pack-designs>
      <Card title="Pack designs">
        <p className="text-[12.5px] text-pb-faint max-w-prose">Give your packs your own look: a background picture, a centre picture (a logo, a trophy, a sponsor), your colours. Start with <strong>Every pack</strong> to set one look for all of them, then give a kind of pack, or a Test match you have scheduled, a look of its own. A pack takes the most specific design that exists, and one with none keeps the built-in look.</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
        <Card title="Which pack">
          <div className="space-y-3" data-design-targets>
            {groups.map((g) => (
              <div key={g.name}>
                <div className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint mb-1">{g.name}</div>
                <div className="flex flex-wrap lg:flex-col gap-1.5">
                  {g.items.map((t) => (
                    <button key={t.key} type="button" data-design-target={t.key} aria-pressed={target === t.key} onClick={() => setTarget(t.key)}
                      className={`text-left px-2.5 py-1.5 rounded border text-[12.5px] flex items-center gap-2 ${target === t.key ? 'border-pb-accent bg-pb-surface2 text-pb-text' : 'border-pb-hairline2 text-pb-text hover:bg-pb-surface2'}`}>
                      <span className="min-w-0 flex-1 truncate">{t.label}</span>
                      {designs[t.key] && <span aria-label="Has a design" title="Has a design" className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--pb-accent)' }} />}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card title={current ? current.label : 'Design'}>
          <div className="grid gap-5 sm:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex flex-col items-center gap-2" data-design-preview>
              <PackArt source={source} label={isEvent ? current?.label : (canName && design.title) || null} design={shown} club={data.club} accent={accent} display={display} width={220} />
              <div className="text-[11.5px] text-pb-faint text-center">{shown ? 'How this pack looks to players' : `The built-in look. Add something below to make it yours.`}</div>
            </div>
            <div className="space-y-3 min-w-0">
              {canName && (
                <Field label="Name on the pack">
                  <input value={draft.title !== undefined ? (draft.title || '') : (saved?.title || '')} maxLength={40} placeholder={PACKS[source]?.label || 'Pack'} aria-label="Name on the pack"
                    onChange={(e) => change({ title: e.target.value || null })} className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" />
                </Field>
              )}
              <ImageSlot kind="bg" title="Background" hint="Fills the whole pack. A pack is 2 wide by 3 tall, so tall pictures fit best." url={saved?.background_url} busy={busy === 'bg'}
                onPick={(f) => upload('bg', f)} onRemove={() => removeImage('bg')} />
              <ImageSlot kind="art" title="Centre picture" hint="Sits on top of the background. A PNG with a see-through background works best." url={saved?.art_url} busy={busy === 'art'}
                onPick={(f) => upload('art', f)} onRemove={() => removeImage('art')} />
              <p className="text-[11.5px] text-pb-faint">PNG, JPEG, WebP or GIF, up to 6 MB. Pictures are resized for you.</p>
              {saved?.background_url && (
                <Field label={`How dark the background is (${Math.round(design.overlay * 100)}%)`}>
                  <input type="range" min="0" max="0.8" step="0.05" value={design.overlay} aria-label="How dark the background is" data-design-overlay
                    onChange={(e) => change({ overlay: Number(e.target.value) })} className="w-full" />
                </Field>
              )}
              {saved?.art_url && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Centre picture sits"><Select value={design.art_position} aria-label="Centre picture position" onChange={(e) => change({ art_position: e.target.value })}><option value="top">Near the top</option><option value="center">In the middle</option><option value="bottom">Near the bottom</option></Select></Field>
                  <Field label="Centre picture size"><Select value={design.art_size} aria-label="Centre picture size" onChange={(e) => change({ art_size: e.target.value })}><option value="s">Small</option><option value="m">Medium</option><option value="l">Large</option></Select></Field>
                </div>
              )}
              <div className="space-y-2">
                <ColourRow label="Foil colour" value={design.a} onChange={(v) => change({ a: v })} />
                <ColourRow label="Foil shade" value={design.b} onChange={(v) => change({ b: v })} />
                <ColourRow label="Writing" value={design.on} onChange={(v) => change({ on: v })} />
              </div>
              <Switch on={design.show_name} onChange={(v) => change({ show_name: v })} label="Show the pack's name" hint="Switch off to let the picture speak for itself." />
              <Switch on={design.show_logo} onChange={(v) => change({ show_logo: v })} label="Show the club logo" hint="Only when there is no centre picture." />
              {saved && (
                <div className="pt-1">
                  {confirmReset
                    ? <span className="flex flex-wrap items-center gap-2 text-sm">Take this pack back to the built-in look? <Btn sm danger onClick={reset}>Yes, reset it</Btn><Btn sm onClick={() => setConfirmReset(false)}>Keep it</Btn></span>
                    : <span data-design-reset><Btn sm onClick={() => setConfirmReset(true)}>Reset to the built-in look</Btn></span>}
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
