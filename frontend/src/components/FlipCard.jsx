// Two faces on a card that turns over on its Y axis (the React Bits "Flip Card" idea). Controlled: the parent
// owns `flipped`, so a Share button can export whichever face is showing. The faces are rendered flat at the
// size they are given; scale the wrapper, not the faces, when the card has to shrink.
const reduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export default function FlipCard({ front, back, flipped, onFlip, width, height, label }) {
  const face = { position: 'absolute', inset: 0, backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' }
  return (
    <div style={{ width, height, perspective: 1400 }}>
      <div
        role="button" tabIndex={0} aria-pressed={flipped} aria-label={label}
        onClick={onFlip}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFlip() } }}
        style={{
          position: 'relative', width: '100%', height: '100%', cursor: 'pointer', transformStyle: 'preserve-3d', outline: 'none',
          transition: reduced() ? 'none' : 'transform .7s cubic-bezier(.4,.2,.2,1)', transform: flipped ? 'rotateY(180deg)' : 'none',
        }}
      >
        <div style={face} aria-hidden={flipped}>{front}</div>
        <div style={{ ...face, transform: 'rotateY(180deg)' }} aria-hidden={!flipped}>{back}</div>
      </div>
    </div>
  )
}
