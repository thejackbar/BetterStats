// Carousel page rail — sits immediately left of the canvas.
//
// Props (all from usePages):
//   count, index, onGoTo(i), onAdd(), onDuplicate(), onRemove(i)
// onDuplicate is optional — derived-page modes (fixtures/results roundups
// spread over N pages) have nothing to duplicate, so the DUP button hides.
export default function PageStrip({ count, index, onGoTo, onAdd, onDuplicate, onRemove }) {
  return (
    <div className="absolute -left-[84px] top-0 flex flex-col items-center gap-1.5">
      <span className="font-mono text-[8px] tracking-wide2 text-pb-faintest mb-0.5">PAGES</span>

      {Array.from({ length: count }, (_, i) => {
        const active = i === index
        return (
          <button
            key={i}
            onClick={() => onGoTo(i)}
            className={`relative w-[46px] h-[46px] rounded-md grid place-items-center font-mono text-[11px] border-2 transition-colors ${
              active ? 'text-pb-accent' : 'text-pb-faint border-pb-hairline2 hover:text-pb-dim'
            }`}
            style={active ? { borderColor: 'var(--pb-accent)' } : undefined}
          >
            {i + 1}
            {count > 1 && (
              <span
                role="button"
                title="Delete page"
                onClick={e => { e.stopPropagation(); onRemove(i) }}
                className="absolute -top-1.5 -right-1.5 w-[15px] h-[15px] rounded-full grid place-items-center bg-pb-surface border pb-hairline2 text-pb-faint hover:text-pb-red text-[8px] leading-none"
              >✕</span>
            )}
          </button>
        )
      })}

      <button
        onClick={onAdd}
        title="Add a page"
        className="w-[46px] h-[30px] rounded-md border border-dashed border-pb-hairline2 text-pb-faint hover:text-pb-text hover:border-pb-accent text-[13px] transition-colors"
      >+</button>
      {onDuplicate && (
        <button
          onClick={onDuplicate}
          title="Duplicate this page"
          className="w-[46px] h-6 rounded-md border pb-hairline font-mono text-[8px] text-pb-faint hover:text-pb-text transition-colors"
        >DUP</button>
      )}
    </div>
  )
}
