// Sponsors panel — which of the club's sponsors are on this post, and how they sit.
//
// Every post carries at least one sponsor, so this opens on what the post already
// has and why (the team's own sponsor, the club's default, or its top sponsor). A
// tick adds or removes a logo, and the grid on the post resizes to fit. Nothing
// here moves the block: that is the canvas's job, so "Move and resize on the
// post" hands over to the editor's own drag and resize handles.
//
// Props:
//   sponsors           [{ id, name, url, tier }] every sponsor the club has
//   block              the post's sponsor block, or null when it has none
//   defaultInfo        { ids, source } what a post like this one starts with
//   context            { team, grade } what this post is about (for the pin buttons)
//   native             true on a layout with sponsor slots of its own
//   onPick(ids)        set the block's sponsors (creates the block if absent)
//   onPanel(style)     'light' | 'dark' | 'none'
//   onUseDefault()     put the block back on the default sponsors
//   onEditOnPost()     switch the canvas to editing so the block can be dragged
//   onRemove()         take the sponsors off this post (the editor confirms first)
//   onPin(kind)        pin the block's sponsors to the team or grade
//   pinState           null | 'saving' | 'saved:<kind>' | 'err:<message>'
const SOURCE_TEXT = {
  team: 'the sponsor your club set for this team',
  grade: 'the sponsor your club set for this grade',
  club: "your club's default sponsors (set under Sponsors, Social posts)",
  top: 'your top sponsor',
  none: 'nothing yet',
}
const PANEL_STYLES = [
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
  { key: 'none', label: 'None' },
]

const Seg = ({ active, onClick, children, title }) => (
  <button type="button" onClick={onClick} title={title}
    className={`h-7 px-2.5 rounded-md border text-[11px] transition-colors ${active ? 'text-pb-accent' : 'border-pb-hairline2 bg-pb-surface2 text-pb-dim hover:text-pb-text'}`}
    style={active ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
    {children}
  </button>
)

export default function SponsorsPanel({
  sponsors = [], block, defaultInfo, context = {}, native = false,
  onPick, onPanel, onUseDefault, onEditOnPost, onRemove, onPin, pinState,
}) {
  const usable = sponsors.filter((s) => s.url)
  const unusable = sponsors.filter((s) => !s.url)
  const picked = new Set(block?.sponsorIds || [])
  const toggle = (id) => {
    const next = picked.has(id) ? [...picked].filter((x) => x !== id) : [...picked, id]
    onPick(next)
  }

  if (native) {
    return (
      <div className="flex flex-col gap-2" data-testid="sponsors-panel">
        <p className="text-[12px] leading-relaxed text-pb-dim">
          This layout has sponsor slots of its own. They start with your default sponsors. Change them
          under Sponsor logos in the Content panel.
        </p>
      </div>
    )
  }

  if (!sponsors.length) {
    return (
      <div className="flex flex-col gap-2" data-testid="sponsors-panel">
        <p className="text-[12px] leading-relaxed text-pb-dim">
          Your club has no sponsors yet, so this post has none. Add them under Sponsors in the club
          admin, with a logo, and every new post will start with one.
        </p>
      </div>
    )
  }

  const teamLabel = (context.team || '').trim()
  const gradeLabel = (context.grade || '').trim()

  return (
    <div className="flex flex-col gap-3.5" data-testid="sponsors-panel">
      <p className="text-[11px] leading-relaxed text-pb-faint">
        Every post carries a sponsor. This one starts with {SOURCE_TEXT[defaultInfo?.source || 'none']}.
      </p>

      <div className="flex flex-col gap-1.5">
        {usable.map((s) => (
          <label key={s.id}
            className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border cursor-pointer transition-colors ${picked.has(s.id) ? 'border-pb-accent' : 'pb-hairline hover:border-pb-hairline2'}`}
            style={picked.has(s.id) ? { background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' } : undefined}>
            <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} aria-label={`Put ${s.name} on this post`} />
            <span className="shrink-0 w-14 h-8 grid place-items-center rounded bg-white/90 overflow-hidden">
              <img src={s.url} alt="" className="max-w-full max-h-full object-contain" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12px] text-pb-text truncate">{s.name}</span>
              {s.tierLabel && <span className="block font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest">{s.tierLabel}</span>}
            </span>
          </label>
        ))}
        {unusable.length > 0 && (
          <p className="text-[10px] leading-relaxed text-pb-faintest">
            {unusable.map((s) => s.name).join(', ')} {unusable.length === 1 ? 'has' : 'have'} no logo, so can't go on a post.
          </p>
        )}
      </div>

      {block && (
        <>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mr-1">Backing</span>
            {PANEL_STYLES.map((p) => (
              <Seg key={p.key} active={(block.panel || 'light') === p.key} onClick={() => onPanel(p.key)}
                title={p.key === 'none' ? 'Logos straight onto the post' : `A ${p.key} panel behind the logos`}>
                {p.label}
              </Seg>
            ))}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Seg onClick={onEditOnPost} title="Drag the sponsors to move them, pull a corner to resize">Move and resize on the post</Seg>
            <Seg onClick={onUseDefault} title="Back to the sponsors a post like this starts with">Use the default</Seg>
          </div>
        </>
      )}

      {block && (teamLabel || gradeLabel) && (
        <div className="rounded-md border pb-hairline bg-pb-surface2 p-2.5 flex flex-col gap-1.5">
          <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Make this the starting point</span>
          <div className="flex flex-wrap gap-1.5">
            {teamLabel && <Seg onClick={() => onPin('teams')}>Every {teamLabel} post</Seg>}
            {gradeLabel && gradeLabel !== teamLabel && <Seg onClick={() => onPin('grades')}>Every {gradeLabel} post</Seg>}
          </div>
          {pinState === 'saving' && <span className="text-[10px] text-pb-faint">Saving…</span>}
          {pinState && pinState.startsWith('saved:') && <span className="text-[10px] text-pb-accent">Saved. New posts for it start with these sponsors.</span>}
          {pinState && pinState.startsWith('err:') && <span className="text-[10px] text-red-400">{pinState.slice(4)}</span>}
        </div>
      )}

      {block && (
        <button type="button" onClick={onRemove}
          className="self-start font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-red-400 underline">
          Take the sponsors off this post
        </button>
      )}
    </div>
  )
}
