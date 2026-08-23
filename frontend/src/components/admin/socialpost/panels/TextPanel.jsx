// Text panel — add heading / subheading / body presets (shown in their real
// canvas fonts) plus the full font list. Adds a text block via onAdd.
import { BLANK_FONTS } from '../../../../social/blank-template'

const PRESETS = [
  { key: 'heading', label: 'Heading', text: 'HEADLINE', fontFamily: "'Anton', sans-serif", fontSize: 130, bold: true, uppercase: true, preview: 26 },
  { key: 'subheading', label: 'Subheading', text: 'SUB HEADLINE', fontFamily: "'Barlow Condensed', sans-serif", fontSize: 66, bold: true, uppercase: true, preview: 18 },
  { key: 'body', label: 'Body', text: 'Add your body copy here: a sentence or two from the club.', fontFamily: "'Inter', sans-serif", fontSize: 40, bold: false, uppercase: false, lineHeight: 1.25, preview: 12 },
]

export default function TextPanel({ onAdd }) {
  const add = (p) => onAdd('text', {
    text: p.text, fontFamily: p.fontFamily, fontSize: p.fontSize,
    bold: p.bold, uppercase: p.uppercase, lineHeight: p.lineHeight ?? (p.uppercase ? 0.92 : 1.25),
  })
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-col gap-2">
        {PRESETS.map((p) => (
          <button key={p.key} onClick={() => add(p)}
            className="text-left px-3 py-2.5 rounded-lg border pb-hairline bg-pb-surface2 hover:border-pb-accent transition-colors">
            <span style={{ fontFamily: p.fontFamily, fontSize: p.preview, fontWeight: p.bold ? 800 : 400, textTransform: p.uppercase ? 'uppercase' : 'none' }}
              className="text-pb-text block leading-tight">{p.label}</span>
          </button>
        ))}
      </div>

      <div>
        <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-2">Fonts</div>
        <div className="flex flex-col gap-1">
          {BLANK_FONTS.map((f) => (
            <button key={f.key} onClick={() => onAdd('text', { text: f.name.toUpperCase(), fontFamily: f.family })}
              title={`Add text in ${f.name}`}
              className="text-left px-2.5 py-1.5 rounded-md hover:bg-pb-surface2 transition-colors text-pb-dim hover:text-pb-text"
              style={{ fontFamily: f.family, fontSize: 15 }}>
              {f.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
