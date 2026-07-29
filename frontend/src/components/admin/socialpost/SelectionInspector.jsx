// Contextual inspector — floats over the bottom of the canvas and shows only the
// controls for what is selected. This REPLACES the long per-property list at the
// bottom of components/admin/BlankCanvasEditor.jsx (that file keeps only the
// add-block/starter/layer duties, which move into the rail panels).
//
// Props:
//   items, selIds                      from useBlankLayer
//   onUpdate(id, patch)                from useBlankLayer
//   onReorder(id, 'up'|'down')         from useBlankLayer
//   onDuplicate(id), onRemove(id)      from useBlankLayer
//   onAlign(mode)                      from useBlankLayer (multi-selection)
//   palette                            active post palette (resolveBlankColor tokens)
//   players                            roster for the player-block picker
//   onPickImage(itemId)                opens the media library / file picker
import { useState } from 'react'
import { Icon } from '../../../pages/admin/betterselect/ui'
import { BLANK_FONTS } from '../../../social/blank-template'

const TOKENS = [
  { key: 'primary', label: 'Club primary' },
  { key: 'secondary', label: 'Club secondary' },
  { key: 'accent', label: 'Accent' },
  { key: 'ink', label: 'Text' },
  { key: 'white', label: 'White' },
  { key: 'black', label: 'Black' },
]
const tokenColor = (t, palette) => ({
  primary: palette.primary, secondary: palette.secondary, accent: palette.accent,
  ink: palette.ink, white: '#ffffff', black: '#0a0a0a',
}[t] || t)

const PLAYER_KINDS = ['player', 'playerphoto', 'playername']

const Btn = ({ active, title, onClick, children }) => (
  <button onClick={onClick} title={title}
    className={`h-7 min-w-7 px-2 rounded-md border text-[11px] transition-colors ${
      active ? 'text-pb-accent' : 'border-pb-hairline2 bg-pb-surface2 text-pb-dim hover:text-pb-text'
    }`}
    style={active ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
    {children}
  </button>
)

const Num = ({ value, onChange, min, max, step = 1, w = 'w-[62px]' }) => (
  <input type="number" value={value ?? 0} min={min} max={max} step={step}
    onChange={e => onChange(Number(e.target.value))}
    className={`${w} h-6 px-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[11px] font-mono`} />
)

const Label = ({ children }) => (
  <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">{children}</span>
)

function Swatches({ value, onChange, palette }) {
  return (
    <span className="flex items-center gap-1">
      {TOKENS.map(t => (
        <button key={t.key} title={t.label} onClick={() => onChange(t.key)}
          className="w-[22px] h-[22px] rounded-md border"
          style={{
            background: tokenColor(t.key, palette),
            borderColor: value === t.key ? 'var(--pb-accent)' : 'rgba(255,255,255,.18)',
            borderWidth: value === t.key ? 2 : 1,
          }} />
      ))}
      <input type="color" title="Custom colour"
        value={typeof value === 'string' && value.startsWith('#') ? value : '#ffffff'}
        onChange={e => onChange(e.target.value)}
        className="w-6 h-6 rounded-md border pb-hairline2 bg-transparent p-0 cursor-pointer" />
    </span>
  )
}

export default function SelectionInspector({
  items, selIds, onUpdate, onReorder, onDuplicate, onRemove, onAlign,
  palette, players = [], onPickImage,
}) {
  const [more, setMore] = useState(false)
  const single = selIds.length === 1 ? items.find(it => it.id === selIds[0]) : null
  const bar = 'absolute left-[22px] right-[22px] bottom-4 rounded-[10px] border pb-hairline2 px-3 py-2.5 backdrop-blur'

  if (!selIds.length) {
    return (
      <div className={`${bar} h-[46px] flex items-center justify-center`} style={{ background: 'rgba(16,20,29,.96)' }}>
        <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">
          Select something on the canvas to edit it
        </span>
      </div>
    )
  }

  const patch = p => onUpdate(single.id, p)

  return (
    <div className={bar} style={{ background: 'rgba(16,20,29,.96)', boxShadow: '0 16px 40px rgba(0,0,0,.5)' }}>
      <div className="flex items-center gap-2.5 flex-wrap">
        <Label>{single ? single.type : `${selIds.length} selected`}</Label>
        <span className="w-px h-5 bg-pb-hairline" />

        {!single && (
          <>
            <Btn title="Align left" onClick={() => onAlign('left')}>⇤</Btn>
            <Btn title="Align centre" onClick={() => onAlign('center')}>⇔</Btn>
            <Btn title="Align right" onClick={() => onAlign('right')}>⇥</Btn>
          </>
        )}

        {single?.type === 'text' && (
          <>
            <select value={single.fontFamily} onChange={e => patch({ fontFamily: e.target.value })}
              className="h-7 max-w-[148px] px-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[11px]">
              {BLANK_FONTS.map(f => <option key={f.key} value={f.family}>{f.name}</option>)}
            </select>
            <Num value={single.fontSize} onChange={v => patch({ fontSize: v })} min={8} max={400} w="w-[58px]" />
            <Btn active={single.bold} title="Bold" onClick={() => patch({ bold: !single.bold })}>B</Btn>
            <Btn active={single.uppercase} title="Uppercase" onClick={() => patch({ uppercase: !single.uppercase })}>AA</Btn>
            {['left', 'center', 'right'].map(a => (
              <Btn key={a} active={single.align === a} onClick={() => patch({ align: a })}>
                {a === 'left' ? '⇤' : a === 'center' ? '⇔' : '⇥'}
              </Btn>
            ))}
          </>
        )}

        {single && single.type !== 'image' && (
          <Swatches value={single.color} onChange={c => patch({ color: c })} palette={palette} />
        )}

        {single?.type === 'image' && (
          <>
            <Btn onClick={() => onPickImage(single.id)}>Replace</Btn>
            <Btn onClick={() => patch({ fit: single.fit === 'cover' ? 'contain' : 'cover' })}>
              {single.fit === 'cover' ? 'Fill' : 'Fit'}
            </Btn>
          </>
        )}

        {single?.type === 'data' && (single.kind === 'fixtures' || single.kind === 'results') && (
          <label className="flex items-center gap-1.5"><Label>Rows</Label>
            <Num value={single.count} onChange={v => patch({ count: Math.max(1, Math.min(12, v)) })} min={1} max={12} w="w-12" />
          </label>
        )}

        {single?.type === 'data' && PLAYER_KINDS.includes(single.kind) && (
          <label className="flex items-center gap-1.5"><Label>Player</Label>
            <select value={single.playerId || ''}
              onChange={e => {
                const p = players.find(x => x.id === e.target.value)
                patch({ playerId: e.target.value || null, playerName: p ? (p.display_name || p.name) : '' })
              }}
              className="h-7 max-w-[170px] px-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[11px]">
              <option value="">Select player…</option>
              {players.map(p => <option key={p.id} value={p.id}>{p.display_name || p.name}</option>)}
            </select>
          </label>
        )}

        <div className="flex-1" />

        {single && (
          <span className="flex items-center gap-0.5">
            <Btn title="Bring forward" onClick={() => onReorder(single.id, 'up')}><Icon name="chevron" size={13} className="-rotate-90" /></Btn>
            <Btn title="Send backward" onClick={() => onReorder(single.id, 'down')}><Icon name="chevron" size={13} className="rotate-90" /></Btn>
            <Btn title="Duplicate" onClick={() => onDuplicate(single.id)}><Icon name="cols" size={13} /></Btn>
            <Btn title="Delete" onClick={() => onRemove(single.id)}><Icon name="trash" size={13} /></Btn>
            <Btn active={more} title="More settings" onClick={() => setMore(m => !m)}><Icon name="filter" size={14} /></Btn>
          </span>
        )}
      </div>

      {more && single && (
        <div className="mt-2.5 pt-2.5 border-t pb-hairline flex flex-wrap items-center gap-3.5">
          {single.type === 'text' && (
            <>
              <textarea value={single.text} rows={2} onChange={e => patch({ text: e.target.value })}
                className="flex-1 min-w-[200px] px-2 py-1.5 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[12px] resize-y" />
              <label className="flex items-center gap-1.5"><Label>Line height</Label>
                <input type="range" min={0.8} max={2} step={0.05} value={single.lineHeight ?? 1}
                  onChange={e => patch({ lineHeight: Number(e.target.value) })} className="w-24" />
              </label>
              <label className="flex items-center gap-1.5"><Label>Letter sp</Label>
                <Num value={single.letterSpacing} onChange={v => patch({ letterSpacing: v })} min={-20} max={60} />
              </label>
            </>
          )}
          {single.type === 'element' && (
            <>
              <label className="flex items-center gap-1.5"><Label>Rotation</Label>
                <input type="range" min={-180} max={180} value={single.rotation || 0}
                  onChange={e => patch({ rotation: Number(e.target.value) })} className="w-24" />
              </label>
              <label className="flex items-center gap-1.5"><Label>Opacity</Label>
                <input type="range" min={0.1} max={1} step={0.05} value={single.opacity ?? 1}
                  onChange={e => patch({ opacity: Number(e.target.value) })} className="w-24" />
              </label>
            </>
          )}
          {'w' in single && (
            <label className="flex items-center gap-1.5"><Label>Width</Label>
              <Num value={single.w} onChange={v => patch({ w: v })} min={4} max={1080} />
            </label>
          )}
          {'h' in single && single.type !== 'text' && (
            <label className="flex items-center gap-1.5"><Label>Height</Label>
              <Num value={single.h} onChange={v => patch({ h: v })} min={4} max={1080} />
            </label>
          )}
          {single.type === 'brand' && (
            <label className="flex items-center gap-1.5"><Label>Size</Label>
              <input type="range" min={60} max={420} value={single.size}
                onChange={e => patch({ size: Number(e.target.value) })} className="w-24" />
            </label>
          )}
          <label className="flex items-center gap-1.5"><Label>X</Label>
            <Num value={single.x} onChange={v => patch({ x: v })} min={-400} max={1080} w="w-14" />
          </label>
          <label className="flex items-center gap-1.5"><Label>Y</Label>
            <Num value={single.y} onChange={v => patch({ y: v })} min={-400} max={1080} w="w-14" />
          </label>
        </div>
      )}
    </div>
  )
}
