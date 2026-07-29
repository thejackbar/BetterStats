// Left icon rail for the BetterPosts editor. Icons come from the app's own kit —
// never draw new ones here.
//
// Props:
//   tool      — active tool key
//   onTool    — (key) => void
import { Icon } from '../../../pages/admin/betterselect/ui'

// Bottom-pinned tools sit after a divider (Layers today; History/Comments later).
export const TOOLS = [
  { key: 'source',   icon: 'bolt',      label: 'Data' },
  { key: 'design',   icon: 'overview',  label: 'Design' },
  { key: 'content',  icon: 'sheet',     label: 'Content' },
  { key: 'text',     icon: 'list',      label: 'Text' },
  { key: 'elements', icon: 'selection', label: 'Shapes' },
  { key: 'photos',   icon: 'player',    label: 'Photos' },
  { key: 'data',     icon: 'ladders',   label: 'Club data' },
  { key: 'brand',    icon: 'settings',  label: 'Brand' },
]
export const END_TOOLS = [
  { key: 'layers', icon: 'cols', label: 'Layers' },
]

export const TOOL_TITLE = {
  source: 'Get your data', design: 'Design', content: 'Content', text: 'Text', elements: 'Shapes',
  photos: 'Photos & badge', data: 'Club data', brand: 'Brand kit', layers: 'Layers',
}

function RailButton({ item, active, onClick }) {
  return (
    <button
      onClick={onClick}
      title={item.label}
      className={`mx-1.5 h-[58px] rounded-lg flex flex-col items-center justify-center gap-1.5 transition-colors ${
        active ? 'text-pb-accent' : 'text-pb-faint hover:text-pb-dim'
      }`}
      style={active ? { background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}
    >
      <Icon name={item.icon} size={18} />
      <span className="font-mono text-[8px] tracking-wide2 uppercase">{item.label}</span>
    </button>
  )
}

export default function ToolRail({ tool, onTool }) {
  return (
    <nav className="w-[74px] shrink-0 bg-pb-surface border-r pb-hairline flex flex-col py-2 gap-0.5">
      {TOOLS.map(t => (
        <RailButton key={t.key} item={t} active={tool === t.key} onClick={() => onTool(t.key)} />
      ))}
      <div className="flex-1" />
      <div className="mx-3 my-1.5 h-px bg-pb-hairline" />
      {END_TOOLS.map(t => (
        <RailButton key={t.key} item={t} active={tool === t.key} onClick={() => onTool(t.key)} />
      ))}
    </nav>
  )
}
