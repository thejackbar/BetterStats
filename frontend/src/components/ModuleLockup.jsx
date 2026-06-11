// The one way a Better module is shown: its logo plus the "BetterX" wordmark
// with the suffix in the module's brand colour. Used by the module sidebars and
// across the marketing site so a module always reads the same.
//
// Pass the module's own `accent` (any CSS colour). It defaults to
// var(--pb-accent) so that inside a themed surface the suffix tracks the
// surface's accent automatically.

// Just the wordmark — "Better" + a colour-suffix span. Use when the logo is
// positioned separately (e.g. a card with the mark in one corner and the name
// elsewhere).
export function ModuleWordmark({ name, accent = 'var(--pb-accent)', className = '' }) {
  if (!name) return null
  const suffix = name.startsWith('Better') ? name.slice('Better'.length) : null
  return (
    <span className={className}>
      {suffix ? <>Better<span style={{ color: accent }}>{suffix}</span></> : name}
    </span>
  )
}

// Logo + wordmark as one inline unit.
export default function ModuleLockup({
  name,
  logo,
  accent = 'var(--pb-accent)',
  size = 28,
  textClassName = 'font-display font-bold text-[15px] leading-none',
  logoClassName = '',
  className = '',
}) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      {logo && <img src={logo} alt="" className={`rounded-lg shrink-0 ${logoClassName}`} style={{ width: size, height: size }} />}
      <ModuleWordmark name={name} accent={accent} className={textClassName} />
    </span>
  )
}
