// First-run / empty state for the BetterPosts editor. Answers "what am I
// posting?" before any canvas appears so a volunteer never lands on a blank
// page. Choosing a type deep-links into the editor (?type=…).
//
// Props:
//   types         [{ key, label, count, icon }]   one per post type
//   club          { name, subtitle, logo }
//   moduleLogo    the BetterSocials mark
//   savedTemplates[{ key, name, templateId }]
//   lastType      { key, label } | null           the post you had open last
//   onPick(typeKey)            open the editor on this type
//   onResume()                 reopen the last post you were working on
//   onApplyTemplate(tpl)       apply a saved template + open the editor
//   onExit()                   leave to the admin app
import { Icon } from '../../../pages/admin/betterselect/ui'

function TypeCard({ type, onClick }) {
  return (
    <button onClick={onClick}
      className="text-left p-2.5 rounded-[9px] border pb-hairline bg-pb-surface hover:border-pb-accent transition-colors">
      <span className="block h-[74px] rounded-md mb-[7px] grid place-items-center text-pb-accent"
        style={{ background: 'color-mix(in srgb, var(--pb-accent) 10%, var(--pb-surface2))' }}>
        <Icon name={type.icon || 'sheet'} size={28} />
      </span>
      <span className="block font-semibold text-pb-text text-[12px] leading-tight">{type.label}</span>
      <span className="block font-mono text-[9px] text-pb-faint mt-0.5">{type.count} layout{type.count === 1 ? '' : 's'}</span>
    </button>
  )
}

export default function StartScreen({
  types = [], club = {}, moduleLogo, savedTemplates = [], lastType,
  onPick, onResume, onApplyTemplate, onExit,
}) {
  return (
    <div className="fixed inset-0 z-40 flex flex-col items-center justify-center gap-[26px] px-6 md:px-[60px] py-10 bg-pb-bg text-pb-text overflow-auto">
      {onExit && (
        <button onClick={onExit} title="Back to admin"
          className="absolute top-4 left-4 flex items-center gap-1.5 px-2.5 h-8 rounded-md border pb-hairline2 text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors">
          <Icon name="back" size={14} /><span className="font-mono text-[9px] tracking-wide2 uppercase">Admin</span>
        </button>
      )}

      {/* Module lockup */}
      <div className="flex items-center gap-3">
        {moduleLogo && <img src={moduleLogo} alt="" className="w-10 h-10 rounded-[11px]" />}
        <div>
          <div className="font-display font-extrabold text-[34px] leading-none">Better<span style={{ color: '#EC4899' }}>Posts</span></div>
          <div className="font-mono text-[10px] tracking-[0.12em] text-pb-faint mt-1">
            {[club.name, club.subtitle].filter(Boolean).join(' · ') || 'Your club'}
          </div>
        </div>
      </div>

      {/* Prompt row */}
      <div className="w-full max-w-[1120px] flex items-end justify-between gap-4">
        <span className="text-[15px] font-semibold">What are you posting?</span>
        <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint hidden sm:block">Every layout arrives pre-filled with your club's data</span>
      </div>

      {/* Type grid */}
      <div className="w-full max-w-[1120px] grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))' }}>
        {types.map((t) => <TypeCard key={t.key} type={t} onClick={() => onPick(t.key)} />)}
      </div>

      {/* Footer, resume where you left off */}
      <div className="w-full max-w-[1120px] pt-5 border-t pb-hairline flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Pick up where you left off</span>
          {savedTemplates.slice(0, 5).map((t) => (
            <button key={t.key} onClick={() => onApplyTemplate(t)}
              className="px-2.5 py-1 rounded-md border pb-hairline bg-pb-surface text-[11px] text-pb-dim hover:border-pb-accent hover:text-pb-text transition-colors truncate max-w-[160px]">{t.name}</button>
          ))}
          {savedTemplates.length === 0 && <span className="font-mono text-[9px] text-pb-faintest">No saved templates yet</span>}
        </div>
        <button onClick={onResume}
          className="flex items-center gap-1.5 px-4 h-[34px] rounded-md font-mono text-[10px] tracking-wide2 uppercase"
          style={{ background: '#EC4899', color: '#0a0d14' }}>
          {lastType ? `Continue · ${lastType.label}` : 'Open the editor'} <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  )
}
