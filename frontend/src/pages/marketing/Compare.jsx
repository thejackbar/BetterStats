import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function Compare() {
  usePageMeta({
    title: 'Compare — BetterStats vs the alternatives',
    description: 'A side-by-side comparison of BetterStats with the platforms your club already uses. Data depth, presentation, setup and cost — laid out so you can make the call.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/compare',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <section className="pt-32 pb-4 px-4 sm:px-6 lg:px-10">
          <div className="max-w-[900px] mx-auto text-center">
            <p className="pill mb-6 inline-flex"><span className="dot" />Side-by-side</p>
            <h1 className="font-display font-bold text-[44px] sm:text-[56px] lg:text-[72px] tracking-tight leading-[0.95] mb-5">
              How BetterStats <span className="gradient-text">stacks up.</span>
            </h1>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed">
              An honest look at where BetterStats sits next to the platforms your club is already using.
            </p>
          </div>
        </section>
        <Comparison3Way id="compare" />
      </div>
      <MarketingFooter />
    </div>
  )
}
