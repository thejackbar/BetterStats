import { Link } from 'react-router-dom'
import { DEMO, trackDemoClick } from '../../data/webinar'

// The recorded demo, linked from the rest of the marketing site. Every piece
// here links OUT to /demo rather than embedding the recording, so a page that
// mentions the demo never pays for a second video player.

function PlayIcon({ className = 'w-5 h-5' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l11.1-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14Z" />
    </svg>
  )
}

// A text link, for sitting under a trial button without competing with it.
export function WatchDemoLink({ placement, children = 'Watch the full demo', className = '' }) {
  return (
    <Link
      to={DEMO.path}
      onClick={() => trackDemoClick(placement)}
      data-demo-link={placement}
      className={`text-sm text-accent font-medium hover:underline inline-flex items-center gap-1.5 ${className}`}
    >
      <PlayIcon className="w-3.5 h-3.5" />
      {children}
    </Link>
  )
}

// The poster with a play button over it. Decorative: the link around it is
// what carries the name.
export function DemoPoster({ className = '' }) {
  return (
    <div className={`relative rounded-xl overflow-hidden border pb-hairline bg-black aspect-video ${className}`}>
      <img
        src={DEMO.poster}
        alt=""
        loading="lazy"
        decoding="async"
        className="absolute inset-0 w-full h-full object-cover opacity-70 group-hover:opacity-85 transition-opacity"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
      <span className="absolute inset-0 flex items-center justify-center">
        <span className="w-16 h-16 rounded-full bg-accent text-[var(--pb-on-accent,#08110b)] flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
          <PlayIcon className="w-7 h-7 ml-1" />
        </span>
      </span>
      <span className="absolute left-3 bottom-3 font-mono text-[11px] tracking-wide text-white/90 bg-black/50 rounded px-2 py-1">
        RECORDING · {DEMO.length.toUpperCase()}
      </span>
    </div>
  )
}

// The home page band, after the product showcase.
export function DemoBand() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline" data-testid="demo-band">
      <div className="max-w-[1200px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        <Link
          to={DEMO.path}
          onClick={() => trackDemoClick('home_band')}
          className="group col-span-1 lg:col-span-7 block"
          aria-label="Watch the full BetterCricket demo"
        >
          <DemoPoster />
        </Link>
        <div className="col-span-1 lg:col-span-5">
          <p className="pill-neutral inline-flex mb-5">{DEMO.recordedLabel}</p>
          <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight leading-[1.05] mb-4">
            See the whole platform <span className="gradient-text">in one sitting.</span>
          </h2>
          <p className="text-pb-dim leading-relaxed mb-7">
            A walk through every module: stats and history, selection,
            socials, club admin and opposition analysis, finishing with the questions
            clubs asked on the night.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <Link to={DEMO.path} onClick={() => trackDemoClick('home_band')} className="cta-primary">
              Watch the demo
            </Link>
            <Link to="/videos" className="cta-secondary">Browse how-to videos</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

// The card at the top of /videos. Fixed in the page rather than a managed
// video row, so reordering or deleting the library cannot remove it.
export function DemoFeatureCard() {
  return (
    <Link
      to={DEMO.path}
      onClick={() => trackDemoClick('videos_featured')}
      className="group pb-card p-4 sm:p-5 mb-12 grid grid-cols-1 sm:grid-cols-12 gap-5 items-center hover:border-accent/40 transition-colors"
      data-testid="videos-demo-card"
    >
      <DemoPoster className="sm:col-span-5" />
      <div className="sm:col-span-7">
        <p className="font-mono text-[10px] tracking-wide3 text-accent uppercase mb-2">Start here</p>
        <h2 className="font-display font-bold text-2xl text-pb-text leading-snug mb-2 group-hover:text-accent transition-colors">
          The full platform demo
        </h2>
        <p className="text-pb-dim text-sm leading-relaxed mb-3">
          Every module in one session, with the questions clubs asked on the night.
          The videos below then go deeper into one job at a time.
        </p>
        <p className="font-mono text-[11px] text-pb-faint">{DEMO.recordedLabel} · {DEMO.length}</p>
      </div>
    </Link>
  )
}
