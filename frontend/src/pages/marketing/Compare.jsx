import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import Reveal from '../../components/marketing/Reveal'
import { COMPARISON_SOLO } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// The per-module comparisons, each with a plain-English intro line. The actual
// table content lives in COMPARISONS (src/data/marketing.js) — here we just
// pick which one to show and frame it.
const MODULE_COMPARES = [
  {
    which: 'betterstats',
    eyebrow: 'BetterStats · the Core',
    intro:
      'Every club gets BetterStats — your full reconciled history and a public site worth visiting. Here is how it sits next to the dedicated cricket-stats tools.',
  },
  {
    which: 'bettersocials',
    eyebrow: 'BetterSocials',
    intro:
      'A designer and a website builder rolled into one — except this one already knows your cricket, so there is nothing to retype.',
  },
  {
    which: 'betterselect',
    eyebrow: 'BetterSelect',
    intro:
      'Collecting availability and picking a side, stacked up against the group chats, spreadsheets and one-size-fits-all team apps clubs usually wrestle with.',
  },
  {
    which: 'betteradmin',
    eyebrow: 'BetterAdmin',
    intro:
      'Your back office — fees, comms and merch — next to the email tool and spreadsheets most clubs stitch together every month.',
  },
]

// Short heading that introduces each per-module table, so the stacked tables
// read as a guided tour rather than a wall of grids.
function CompareIntro({ eyebrow, intro }) {
  return (
    <Reveal>
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 pt-24 pb-2 text-center">
        <p className="pill-neutral inline-flex mb-4">{eyebrow}</p>
        <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed">{intro}</p>
      </div>
    </Reveal>
  )
}

// BetterIQ has no club-platform equivalent — so it gets a panel, not a table.
function CategoryOfOne() {
  const solo = COMPARISON_SOLO.betteriq
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline-t">
      <div className="max-w-[1000px] mx-auto">
        <Reveal>
          <div className="surface-strong p-8 lg:p-12 relative overflow-hidden">
            <div className="absolute inset-0 dot-grid opacity-20 pointer-events-none" />
            <div className="relative">
              <p className="pill-neutral inline-flex mb-5">{solo.eyebrow}</p>
              <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight leading-[1.05]">
                {solo.heading}
              </h2>
              <p className="text-lg text-pb-dim max-w-2xl mb-8">{solo.sub}</p>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 mb-8">
                {solo.points.map((p) => (
                  <li key={p} className="flex items-start gap-3 text-sm text-pb-dim leading-relaxed">
                    <span className="tick mt-0.5">✓</span>
                    {p}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-pb-faint max-w-2xl">{solo.note}</p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

export default function Compare() {
  usePageMeta({
    title: 'Compare — Better Cricket vs the tools clubs already use',
    description:
      'An honest, side-by-side look at how Better Cricket stacks up against the spreadsheets, website builders, design apps and email tools your club is already paying for — surface by surface.',
    image: 'https://betterat.cricket/og-image.png',
    url: 'https://betterat.cricket/compare',
  })

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        {/* Hero */}
        <section className="pt-32 pb-4 px-4 sm:px-6 lg:px-10">
          <div className="max-w-[900px] mx-auto text-center">
            <p className="pill mb-6 inline-flex"><span className="dot" />Side-by-side</p>
            <h1 className="font-display font-bold text-[44px] sm:text-[56px] lg:text-[72px] tracking-tight leading-[0.95] mb-5">
              How Better Cricket <span className="gradient-text">stacks up.</span>
            </h1>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed">
              An honest look at where Better Cricket sits next to the tools your club already uses
              — the spreadsheets, the website builder, the design app, the email tool and the group
              chats. Whole platform first, then surface by surface.
            </p>
          </div>
        </section>

        {/* Whole-platform comparison — the "compares everything" one. */}
        <Comparison3Way id="compare" which="platform" showCTA={false} />

        {/* Per-module comparisons, each with a short intro. */}
        {MODULE_COMPARES.map(({ which, eyebrow, intro }) => (
          <div key={which}>
            <CompareIntro eyebrow={eyebrow} intro={intro} />
            <Comparison3Way id={`compare-${which}`} which={which} showCTA={false} />
          </div>
        ))}

        {/* BetterIQ — category of one, no table. */}
        <CategoryOfOne />

        {/* Final CTA */}
        <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline-t text-center">
          <div className="max-w-[760px] mx-auto">
            <Reveal>
              <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight leading-[1.05]">
                One login. The whole club.
              </h2>
              <p className="text-lg text-pb-dim max-w-2xl mx-auto mb-8 leading-relaxed">
                Stop stitching five tools together every weekend. We bring your history across,
                set it all up and have your club live in under an hour.
              </p>
              <Link to="/contact" className="cta-primary">Get your club on Better Cricket →</Link>
            </Reveal>
          </div>
        </section>
      </div>
      <MarketingFooter />
    </div>
  )
}
