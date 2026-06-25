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
//   presetKey    — currently selected preset key (or '')
//   onPickPreset — (presetKey) => void  (fills event + suggests template/motif)
//   templateId   — selected EVENT template id (e.g. 'EV1')
//   setTemplateId
//   motifKey     — selected watermark glyph key
//   setMotifKey
//   bgImage      — object URL of the uploaded background photo (or null)
//   setBgImage   — (url|null) => void
//   bgOpacity    — 0..1
//   setBgOpacity
import { useRef } from 'react'
import { EVENT_PRESETS, EVENT_MOTIFS, EVENT_TEMPLATES } from '../../social/event-templates'

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

export default function EventPostEditor({
  event, setEvent,
  presetKey, onPickPreset,
  templateId, setTemplateId,
  motifKey, setMotifKey,
  bgImage, setBgImage,
  bgOpacity = 0.85, setBgOpacity,
}) {
  const fileRef = useRef(null)
  const patch = (p) => setEvent({ ...event, ...p })

  const tmpl = EVENT_TEMPLATES.find((t) => t.id === templateId) || EVENT_TEMPLATES[0]
  const usesPhoto = tmpl?.photo

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBgImage(URL.createObjectURL(file))
  }

  return (
    <div className="space-y-5">
      {/* ── Event preset ───────────────────────────────────────────────── */}
      <div>
        <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-2">Event</label>
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

      {/* ── Facts ──────────────────────────────────────────────────────── */}
      <Field label="Kicker / eyebrow"><TextInput value={event.kicker} onChange={(v) => patch({ kicker: v })} placeholder="Club Social" /></Field>
      <Field label="Title"><TextInput value={event.title} onChange={(v) => patch({ title: v })} placeholder="Curry Night" /></Field>
      <Field label="Subtitle">
        <textarea value={event.subtitle || ''} onChange={(e) => patch({ subtitle: e.target.value })} rows={2} placeholder="One line about the event…"
          className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest resize-none" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date"><TextInput value={event.date} onChange={(v) => patch({ date: v })} placeholder="Fri 18 Jul" /></Field>
        <Field label="Time"><TextInput value={event.time} onChange={(v) => patch({ time: v })} placeholder="7:00 PM" /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Venue"><TextInput value={event.venue} onChange={(v) => patch({ venue: v })} placeholder="The Clubhouse" /></Field>
        <Field label="Price / entry"><TextInput value={event.price} onChange={(v) => patch({ price: v })} placeholder="$25 / head" /></Field>
      </div>
      <Field label="Call to action"><TextInput value={event.cta} onChange={(v) => patch({ cta: v })} placeholder="RSVP by Wed" /></Field>
      <Field label="Sponsor / footer"><TextInput value={event.sponsor} onChange={(v) => patch({ sponsor: v })} placeholder="Sponsored by …" /></Field>

      {/* ── Background photo (the themed-motif feature) ────────────────── */}
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

      {/* ── Watermark glyph (no-photo motif) ───────────────────────────── */}
      <Field label="Motif glyph">
        <div className="grid grid-cols-5 gap-1.5">
          {EVENT_MOTIFS.map((m) => (
            <button key={m.key} onClick={() => setMotifKey(m.key)} title={m.label}
              className="aspect-square rounded border pb-hairline flex items-center justify-center bg-pb-surface2 transition-colors"
              style={motifKey === m.key ? { borderColor: 'var(--pb-accent)', boxShadow: '0 0 0 1px var(--pb-accent)' } : {}}>
              <img src={m.icon} alt={m.label} className="w-7 h-7 object-contain" />
            </button>
          ))}
        </div>
      </Field>
    </div>
  )
}
