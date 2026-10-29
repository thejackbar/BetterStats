// The controls a pack's design is made of, shared by the Pack designs tab (which saves each change as it is made) and the Make a pack
// form (which holds the design until the pack is made): a switch, a picture slot and a colour row.
import { useRef } from 'react'
import { Btn } from '../../lib/presskit'

export const IMAGE_TYPES = 'image/png,image/jpeg,image/webp,image/gif'

export function Switch({ on, onChange, label, hint }) {
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
export function ImageSlot({ kind, title, hint, url, busy, onPick, onRemove }) {
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

export function ColourRow({ label, value, onChange }) {
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

