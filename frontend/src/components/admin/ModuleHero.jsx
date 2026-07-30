import ModuleLockup from '../ModuleLockup'

// The identity block at the top of a module's own Overview page — logo,
// colour-suffixed "BetterX" heading, one-line blurb. Matches the hand-rolled
// hero BetterAdmin/BetterSocials already use (same lockup, same type scale),
// so every module surface's landing page reads the same regardless of
// whether its cards are separate billable products (BetterAdmin) or tool
// groups within one module (BetterStats, BetterSelect).
export default function ModuleHero({ name, logo, blurb }) {
  return (
    <div className="mb-6">
      <ModuleLockup name={name} logo={logo} size={36} textClassName="font-display font-bold text-2xl text-pb-text" className="mb-1" />
      {blurb && <p className="text-pb-faint text-sm max-w-2xl">{blurb}</p>}
    </div>
  )
}
