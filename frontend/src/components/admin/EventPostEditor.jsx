// Events tab for the BetterSocials Post Designer (AdminSocialPost).
//
// Self-contained controls panel for the club-event / announcement posters in
// event-templates.jsx. Mirrors the look of the other designer tabs (pb-* global
// classes, mono labels) but keeps all of its own small UI helpers so it drops in
// with no extra imports. The parent owns the palette / font / dark-mode controls
// and the render + export pipeline, exactly as it does for the other tabs.
//
// Props:
//   event        — the editable facts object ({ kicker, title, … })
//   setEvent     — patcher: setEvent({ title: '…' })
//   presetKey    — currently selected example key (or '')
//   onPickPreset — (presetKey) => void  (fills event + suggests template/motif)
//   setPresetKey — clears the example highlight once the name is hand-edited
//   templateId   — selected EVENT template id (e.g. 'EV1')
//   setTemplateId
//   motifKey     — selected watermark glyph key
//   setMotifKey
//   bgImage      — object URL of the uploaded background photo (or null)
//   setBgImage   — (url|null) => void
//   bgOpacity    — 0..1
//   setBgOpacity
//   motifIcon / setMotifIcon — a searched icon (data URI) used when motifKey is 'custom'
//   eventList / setEventList — the run of events the list layouts (EL1 to EL3) draw
//   uploadPhoto(file) => Promise<url>  puts a picture in the club library
//   accent, dark — for the icon search's line-icon colours
import { useRef, useState } from 'react'
import { EVENT_PRESETS, EVENT_MOTIFS, EVENT_TEMPLATES, MAX_LIST_ITEMS } from '../../social/event-templates'
import IconSearch from './socialpost/IconSearch'

function Field({ label, children }) {
  return (
    <div>
      <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">{label}</label>
      {children}
    </div>
  )
}

function TextInput({ value, onChange, placeholder }) {
  return (
    <input value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest" />
  )
}

const newItemId = () => `e${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`

// One event in a list. Collapsed it is a line (date, title); open it edits
// everything, including the icon or photo that leads it on the post.
function EventListItem({ it, idx, count, open, onToggle, onChange, onRemove, onMove, uploadPhoto, accent, dark }) {
  const [search, setSearch] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef(null)
  const visual = it.imageUrl ? 'photo' : it.iconKey === 'custom' && it.iconUri ? 'icon' : it.iconKey ? 'glyph' : ''
  const thumb = it.imageUrl || (it.iconKey === 'custom' ? it.iconUri : EVENT_MOTIFS.find((m) => m.key === it.iconKey)?.icon) || null

  const onFile = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setBusy(true); setErr('')
    try {
      const url = await uploadPhoto(f)
      if (!url) throw new Error('The picture could not be saved to the club library.')
      onChange({ imageUrl: url })
    } catch (er) { setErr(er?.message || 'Could not upload that picture.') } finally { setBusy(false) }
  }

  return (
    <div className="rounded border pb-hairline bg-pb-surface min-w-0" data-testid="event-item">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <div className="flex flex-col gap-0.5">
          <button onClick={() => onMove(-1)} disabled={idx === 0} aria-label="Move up" className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▲</button>
          <button onClick={() => onMove(1)} disabled={idx === count - 1} aria-label="Move down" className="text-pb-faintest hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▼</button>
        </div>
        <button onClick={onToggle} className="flex-1 min-w-0 flex items-center gap-2 text-left">
          <span className="w-7 h-7 rounded bg-pb-surface2 flex items-center justify-center overflow-hidden shrink-0">
            {thumb ? <img src={thumb} alt="" className="w-full h-full object-contain" /> : <span className="text-pb-faintest text-[10px]">{idx + 1}</span>}
          </span>
          <span className="min-w-0">
            <span className="block text-sm text-pb-text truncate">{it.title || 'Untitled event'}</span>
            <span className="block font-mono text-[9px] text-pb-faintest truncate">{[it.date, it.time].filter(Boolean).join(' · ') || 'No date yet'}</span>
          </span>
        </button>
        <button onClick={onRemove} aria-label="Remove event" className="text-pb-faintest hover:text-red-400 text-xs shrink-0">✕</button>
      </div>
      {open && (
        <div className="px-2.5 pb-3 pt-1 flex flex-col gap-2 border-t pb-hairline">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Title"><TextInput value={it.title} onChange={(v) => onChange({ title: v })} placeholder="Quiz Night" /></Field>
            <Field label="Date">
              <input type="date" value={it.date || ''} onChange={(e) => onChange({ date: e.target.value })} data-testid="event-date"
                className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text" />
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Time"><TextInput value={it.time} onChange={(v) => onChange({ time: v })} placeholder="7:30 PM" /></Field>
            <Field label="Venue"><TextInput value={it.venue} onChange={(v) => onChange({ venue: v })} placeholder="Clubhouse" /></Field>
            <Field label="Price"><TextInput value={it.price} onChange={(v) => onChange({ price: v })} placeholder="$12" /></Field>
          </div>
          <div>
            <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">Icon or photo</label>
            <div className="grid grid-cols-6 gap-1.5 mb-2">
              {EVENT_MOTIFS.map((m) => (
                <button key={m.key} onClick={() => onChange({ iconKey: m.key, imageUrl: '' })} title={m.label}
                  className="aspect-square rounded border pb-hairline flex items-center justify-center bg-pb-surface2"
                  style={visual === 'glyph' && it.iconKey === m.key ? { borderColor: 'var(--pb-accent)', boxShadow: '0 0 0 1px var(--pb-accent)' } : {}}>
                  <img src={m.icon} alt={m.label} className="w-6 h-6 object-contain" />
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => setSearch((v) => !v)} data-testid="event-icon-search-toggle"
                className="px-2.5 py-1.5 rounded border pb-hairline2 text-xs font-mono text-pb-dim hover:text-pb-text hover:border-pb-accent">{search ? 'Hide icon search' : 'Search more icons'}</button>
              <button onClick={() => fileRef.current?.click()} disabled={busy}
                className="px-2.5 py-1.5 rounded border pb-hairline2 text-xs font-mono text-pb-dim hover:text-pb-text hover:border-pb-accent disabled:opacity-50">{busy ? 'Uploading…' : it.imageUrl ? 'Change photo' : 'Use a photo'}</button>
              {(it.imageUrl || it.iconKey) && (
                <button onClick={() => onChange({ imageUrl: '', iconKey: '', iconUri: '' })} className="text-xs font-mono text-pb-faint hover:text-pb-text">Clear</button>
              )}
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onFile} />
            </div>
            {err && <p className="text-[11px] text-red-400 mt-1" role="alert">{err}</p>}
            {search && (
              <div className="mt-2 p-2 rounded border pb-hairline bg-pb-surface2">
                <IconSearch accent={accent} dark={dark} onPick={(ic) => { onChange({ iconKey: 'custom', iconUri: ic.dataUri, imageUrl: '' }); setSearch(false) }} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function EventListEditor({ list, setList, uploadPhoto, accent, dark }) {
  const items = list?.items || []
  const [openId, setOpenId] = useState(items[0]?.id || null)
  const setItems = (next) => setList({ ...list, items: next })
  const patch = (id, p) => setItems(items.map((it) => (it.id === id ? { ...it, ...p } : it)))
  const move = (idx, dir) => {
    const j = idx + dir
    if (j < 0 || j >= items.length) return
    const next = items.slice();[next[idx], next[j]] = [next[j], next[idx]]
    setItems(next)
  }
  const add = () => {
    const it = { id: newItemId(), date: '', title: '', time: '', venue: '', price: '', iconKey: 'star', iconUri: '', imageUrl: '' }
    setItems([...items, it]); setOpenId(it.id)
  }
  return (
    <div data-testid="event-list-editor">
      <div className="flex items-center justify-between mb-2">
        <label className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Events on this post ({items.length}/{MAX_LIST_ITEMS})</label>
      </div>
      <div className="flex flex-col gap-1.5">
        {items.map((it, idx) => (
          <EventListItem key={it.id} it={it} idx={idx} count={items.length} open={openId === it.id}
            onToggle={() => setOpenId((cur) => (cur === it.id ? null : it.id))}
            onChange={(p) => patch(it.id, p)}
            onRemove={() => { setItems(items.filter((x) => x.id !== it.id)); if (openId === it.id) setOpenId(null) }}
            onMove={(d) => move(idx, d)} uploadPhoto={uploadPhoto} accent={accent} dark={dark} />
        ))}
      </div>
      {items.length < MAX_LIST_ITEMS ? (
        <button onClick={add} data-testid="event-add"
          className="mt-2 px-3 py-1.5 rounded border pb-hairline text-[11px] font-mono text-pb-dim hover:text-pb-text hover:border-pb-accent">+ ADD AN EVENT</button>
      ) : (
        <p className="mt-2 font-mono text-[9px] text-pb-faintest leading-relaxed">That is the most one post holds ({MAX_LIST_ITEMS}). Make a second post for the rest.</p>
      )}
      <p className="font-mono text-[9px] text-pb-faintest mt-2 leading-relaxed">
        The calendar layout uses the real dates, and shows the month of the earliest one. The agenda and cards read the date as a label.
      </p>
    </div>
  )
}

export default function EventPostEditor({
  event, setEvent,
  presetKey, onPickPreset, setPresetKey,
  templateId, setTemplateId,
  motifKey, setMotifKey,
  bgImage, setBgImage,
  bgOpacity = 0.85, setBgOpacity,
  savedEvents = [], activeSavedKey = null, onPickSaved,
  motifIcon = '', setMotifIcon, eventList, setEventList, uploadPhoto, accent, dark,
}) {
  const [motifSearch, setMotifSearch] = useState(false)
  const fileRef = useRef(null)
  const patch = (p) => setEvent({ ...event, ...p })

  const tmpl = EVENT_TEMPLATES.find((t) => t.id === templateId) || EVENT_TEMPLATES[0]
  const usesPhoto = tmpl?.photo
  const isList = !!tmpl?.list

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBgImage(URL.createObjectURL(file))
  }

  return (
    <div className="space-y-5">
      {/* ── Event name (free text — this is the poster headline) ─────────── */}
      <Field label={isList ? 'Post title' : 'Event name'}>
        <TextInput value={event.title} onChange={(v) => { patch({ title: v }); if (presetKey && setPresetKey) setPresetKey('') }} placeholder={isList ? "e.g. What's on this term" : 'e.g. Wine & Cheese Night'} />
      </Field>

      {/* ── Start from an example (optional) ───────────────────────────── */}
      <div>
        <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-2">Start from an example (optional)</label>
        <div className="grid grid-cols-2 gap-1.5">
          {EVENT_PRESETS.map((p) => (
            <button key={p.key} onClick={() => onPickPreset(p.key)}
              className="text-left px-2.5 py-2 rounded border pb-hairline text-xs transition-colors"
              style={presetKey === p.key
                ? { background: 'var(--pb-accent)', color: 'var(--pb-bg)', borderColor: 'var(--pb-accent)' }
                : {}}>
              {p.label}
            </button>
          ))}
        </div>
        {savedEvents.length > 0 && onPickSaved && (
          <div className="mt-3" data-testid="saved-events">
            <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-2">Your saved events ({savedEvents.length})</label>
            <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
              {savedEvents.map((t) => (
                <button key={t.key} onClick={() => onPickSaved(t.key)} data-testid="saved-event"
                  className="text-left px-2.5 py-2 rounded border pb-hairline text-xs transition-colors min-w-0"
                  style={activeSavedKey === t.key ? { borderColor: 'var(--pb-accent)' } : {}}>
                  <div className="text-pb-text truncate">{t.name}</div>
                  <div className="font-mono text-[9px] text-pb-faintest truncate mt-0.5">{[t.title && t.title !== t.name ? t.title : '', t.layout].filter(Boolean).join(' · ')}</div>
                </button>
              ))}
            </div>
            <p className="font-mono text-[9px] text-pb-faintest mt-2 leading-relaxed">
              These keep the wording, motif and photo you saved, along with the layout.
            </p>
          </div>
        )}
        <p className="font-mono text-[9px] text-pb-faintest mt-2 leading-relaxed">
          Only examples. Pick one to pre-fill the copy and a matching layout, then change anything. Or type your own event name above and fill in the details below.
        </p>
      </div>

      {/* ── Layout (template) ──────────────────────────────────────────── */}
      <Field label="Layout">
        <div className="grid grid-cols-3 gap-1.5">
          {EVENT_TEMPLATES.map((t) => (
            <button key={t.id} onClick={() => setTemplateId(t.id)} title={t.desc}
              className="px-2 py-1.5 rounded border pb-hairline text-[11px] truncate transition-colors"
              style={templateId === t.id
                ? { background: 'var(--pb-accent)', color: 'var(--pb-bg)', borderColor: 'var(--pb-accent)' }
                : {}}>
              {t.name}
            </button>
          ))}
        </div>
      </Field>

      {/* ── Facts (Event name lives up top) ────────────────────────────── */}
      <Field label="Kicker / eyebrow"><TextInput value={event.kicker} onChange={(v) => patch({ kicker: v })} placeholder="Club Social" /></Field>
      <Field label="Subtitle">
        <textarea value={event.subtitle || ''} onChange={(e) => patch({ subtitle: e.target.value })} rows={2} placeholder="One line about the event…"
          className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest resize-none" />
      </Field>
      {isList ? (
        eventList && setEventList && <EventListEditor list={eventList} setList={setEventList} uploadPhoto={uploadPhoto} accent={accent} dark={dark} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date"><TextInput value={event.date} onChange={(v) => patch({ date: v })} placeholder="Fri 18 Jul" /></Field>
            <Field label="Time"><TextInput value={event.time} onChange={(v) => patch({ time: v })} placeholder="7:00 PM" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Venue"><TextInput value={event.venue} onChange={(v) => patch({ venue: v })} placeholder="The Clubhouse" /></Field>
            <Field label="Price / entry"><TextInput value={event.price} onChange={(v) => patch({ price: v })} placeholder="$25 / head" /></Field>
          </div>
          <Field label="Call to action"><TextInput value={event.cta} onChange={(v) => patch({ cta: v })} placeholder="RSVP by Wed" /></Field>
        </>
      )}
      <Field label="Sponsor / footer"><TextInput value={event.sponsor} onChange={(v) => patch({ sponsor: v })} placeholder="Sponsored by …" /></Field>

      {/* ── Background photo (the themed-motif feature) ────────────────── */}
      {!isList && (
      <div className="pt-2 border-t pb-hairline">
        <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-2">Background photo</label>
        {usesPhoto ? (
          <>
            <div className="flex items-center gap-2">
              <button onClick={() => fileRef.current?.click()}
                className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2"
                style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                {bgImage ? 'Replace photo' : 'Upload photo'}
              </button>
              {bgImage && (
                <button onClick={() => setBgImage(null)} className="text-pb-faintest hover:text-red-400 text-xs">✕ remove</button>
              )}
              <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
            </div>
            {bgImage && (
              <div className="mt-3">
                <img src={bgImage} alt="" className="w-full h-24 object-cover rounded border pb-hairline" />
                <label className="block font-mono text-[10px] text-pb-faint uppercase mt-2 mb-1">Opacity · {Math.round(bgOpacity * 100)}%</label>
                <input type="range" min={0.2} max={1} step={0.05} value={bgOpacity}
                  onChange={(e) => setBgOpacity(parseFloat(e.target.value))} className="w-full accent-pb-accent" />
              </div>
            )}
            <p className="font-mono text-[9px] text-pb-faintest mt-2 leading-relaxed">
              Drop in a curry shot for Curry Night, a band photo for Live Music, etc. The template lays it behind a dark scrim so the text stays readable.
            </p>
          </>
        ) : (
          <p className="font-mono text-[9px] text-pb-faintest leading-relaxed">
            The <span className="text-pb-faint">{tmpl?.name}</span> layout uses a faded glyph instead of a photo. Pick a glyph below, or switch to Floodlit / Colour Block / Kinetic / Gazette / Sticker / Polaroid for a photo background.
          </p>
        )}
      </div>
      )}

      {/* ── Watermark glyph (no-photo motif) ───────────────────────────── */}
      {!isList && (
      <Field label="Motif glyph">
        <div className="grid grid-cols-5 gap-1.5">
          {EVENT_MOTIFS.map((m) => (
            <button key={m.key} onClick={() => setMotifKey(m.key)} title={m.label}
              className="aspect-square rounded border pb-hairline flex items-center justify-center bg-pb-surface2 transition-colors"
              style={motifKey === m.key ? { borderColor: 'var(--pb-accent)', boxShadow: '0 0 0 1px var(--pb-accent)' } : {}}>
              <img src={m.icon} alt={m.label} className="w-7 h-7 object-contain" />
            </button>
          ))}
          {motifIcon && (
            <button onClick={() => setMotifKey('custom')} title="Your searched icon" data-testid="custom-motif"
              className="aspect-square rounded border pb-hairline flex items-center justify-center bg-pb-surface2 transition-colors"
              style={motifKey === 'custom' ? { borderColor: 'var(--pb-accent)', boxShadow: '0 0 0 1px var(--pb-accent)' } : {}}>
              <img src={motifIcon} alt="Your icon" className="w-7 h-7 object-contain" />
            </button>
          )}
        </div>
        {setMotifIcon && (
          <div className="mt-2">
            <button onClick={() => setMotifSearch((v) => !v)} data-testid="motif-icon-search-toggle"
              className="px-2.5 py-1.5 rounded border pb-hairline2 text-xs font-mono text-pb-dim hover:text-pb-text hover:border-pb-accent">{motifSearch ? 'Hide icon search' : 'Search more icons'}</button>
            {motifSearch && (
              <div className="mt-2 p-2 rounded border pb-hairline bg-pb-surface2">
                <IconSearch accent={accent} dark={dark} onPick={(ic) => { setMotifIcon(ic.dataUri); setMotifKey('custom'); setMotifSearch(false) }} />
              </div>
            )}
          </div>
        )}
      </Field>
      )}
    </div>
  )
}
