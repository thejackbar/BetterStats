// Shared filter primitives for the BetterSelect admin screens, so Selection and
// Availability draw their filter controls from one styled source instead of
// re-defining near-identical components per page. (Distinct from presskit's
// unrelated FilterGroup, which has a different API.)

// Compact labelled <select> for a filter bar. `options` is [value, label][].
// When includeAny is true (default), a blank "any" option is prepended.
export function FilterSelect({ label, value, onChange, options, anyLabel = 'Any', includeAny = true }) {
  return (
    <div>
      <label className="font-mono text-[10px] text-pb-faintest block mb-1">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
      >
        {includeAny && <option value="">{anyLabel}</option>}
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}

// A titled group of multi-select checkbox facets for the filter panel.
export function FilterGroup({ title, children }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2 pb-1.5 border-b pb-hairline">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

export function FilterCheck({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-pb-faint hover:text-pb-text cursor-pointer">
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-pb-accent" />
      {label}
    </label>
  )
}
