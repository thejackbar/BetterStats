import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import CountUp from '../../components/marketing/CountUp'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import { SCREENSHOT_PATHS, SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// Founder photo placeholder — keep a tasteful mock until the real photo is dropped in /public/marketing/.
function FounderMock() {
  return (
    <div className="w-full aspect-[4/5] rounded-2xl border pb-hairline bg-gradient-to-br from-pb-surface to-pb-bg flex items-center justify-center">
      <div className="text-center">
        <div className="w-24 h-24 rounded-full bg-pb-surface2 border pb-hairline mx-auto mb-4 flex items-center justify-center">
          <span className="text-4xl">🏏</span>
        </div>
        <p className="text-xs font-mono uppercase tracking-wide3 text-pb-faint mb-1">Founder photo</p>
        <p className="text-xs text-pb-dim max-w-[200px] mx-auto">Drop a JPG at <br /><code className="text-accent">/public/marketing/founder.png</code></p>
      </div>
    </div>
  )
}

function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1100px] mx-auto relative">
        <div className="grid grid-cols-12 gap-10 items-center">
          <div className="col-span-12 lg:col-span-7">
            <p className="pill mb-6 inline-flex"><span className="dot" />Made for cricket · by cricketers</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[56px] lg:text-[72px] tracking-tight leading-[0.95] mb-6">
              The cricket stats platform <span className="gradient-text">your club deserves.</span>
            </h1>
            <p className="text-lg lg:text-xl text-pb-dim leading-relaxed">
              BetterStats was built to do one thing well — turn the data your club already produces into a public website your members will actually open.
            </p>
          </div>
          <div className="col-span-12 lg:col-span-5">
            <div className="relative product-shadow rounded-2xl">
              <ScreenshotOrMock src={SCREENSHOT_PATHS.aboutFounder} alt="BetterStats founder" fallback={<FounderMock />} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Story() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20">
      <div className="max-w-[760px] mx-auto">
        <Reveal>
          <p className="pill-neutral inline-flex mb-6">What we do</p>
          <div className="space-y-5 text-lg text-pb-dim leading-relaxed">
            <p>
              BetterStats started as an internal stats platform for Applecross Cricket Club in Perth, Western Australia — built by a club member tired of manually updating spreadsheets after every game. It's now being made available to other clubs who want the same thing.
            </p>
            <p>
              Australian cricket clubs are full of people who care about the history of their club — who hit the first century, who took the most wickets in a season, who's closing in on 100 games. <span className="text-pb-text">BetterStats makes that information beautiful, accessible, and automatic.</span>
            </p>
            <p>
              Once your club is set up, stats come through automatically after every match — no data entry, no spreadsheets, no chasing scorers. Your full history is pulled in on first sync, and everything stays up to date from there.
            </p>
            <p>
              We sit on top of PlayHQ — the official Australian cricket data feed — so the data stays accurate and current, and your scorers keep using the tools they already know.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Numbers() {
  const stats = [
    { v: 100000, suffix: '+', label: 'Innings parsed' },
    { v: 7, suffix: '', label: 'Clubs live' },
    { v: 30, suffix: '+', label: 'Stat columns' },
    { v: 100, suffix: '%', label: 'Automated' },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-16 border-y pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-6">
        {stats.map((s, i) => (
          <Reveal key={s.label} delay={i * 80}>
            <div className="text-center md:text-left">
              <p className="text-4xl md:text-5xl font-bold tabular-nums gradient-text"><CountUp to={s.v} />{s.suffix}</p>
              <p className="text-sm text-pb-dim mt-1">{s.label}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

function Principles() {
  const principles = [
    { n: '01', title: 'Cricketers first', desc: "Every product decision asks: what would a club statistician or committee volunteer actually want here? Built by people who keep a scorebook." },
    { n: '02', title: 'Honest with data', desc: "If a stat isn't confirmed, we say so. Old MyCricket aggregates get flagged. We don't invent runs that nobody scored." },
    { n: '03', title: 'No tiers, no upsells', desc: "Every club gets every feature. We hate the SaaS playbook of locking 'the one feature you wanted' behind a Pro tier." },
    { n: '04', title: 'You own the data', desc: "Full CSV export anytime. We're a lens on PlayHQ's data — not the source of truth, just the layer that makes it useful." },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">How we work</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">Four things we won't change.</h2>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {principles.map((p, i) => (
            <Reveal key={p.n} delay={i * 100}>
              <div className="surface p-7 h-full">
                <div className="icon-tile mb-5">{p.n}</div>
                <h3 className="text-xl font-semibold mb-2">{p.title}</h3>
                <p className="text-pb-dim leading-relaxed">{p.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

function Promise_() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1100px] mx-auto">
        <div className="grid grid-cols-12 gap-8 items-stretch">
          <Reveal className="col-span-12 md:col-span-7">
            <div className="surface p-8 lg:p-10 h-full border-accent/30 bg-gradient-to-b from-accent/[0.05] to-transparent">
              <div className="flex items-center gap-3 mb-5">
                <div className="icon-tile">★</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-accent">Player-first</p>
              </div>
              <h2 className="text-3xl lg:text-4xl font-bold leading-tight mb-4 tracking-tight">
                We welcome <span className="gradient-text">feedback and feature requests.</span>
              </h2>
              <p className="text-pb-dim leading-relaxed mb-5">
                BetterStats is built by cricketers, for cricketers. We listen to the captains, committee members, statisticians and the kids who just want to see their own century on a profile page.
              </p>
              <p className="text-pb-text font-medium mb-6">
                If something is missing — tell us. If it's important to you, it's important to us.
              </p>
              <Link to="/contact" className="cta-primary !text-sm !py-2.5 !px-5">Send us a feature request →</Link>
            </div>
          </Reveal>

          <Reveal delay={120} className="col-span-12 md:col-span-5">
            <div className="surface p-8 h-full">
              <div className="flex items-center gap-3 mb-5">
                <div className="icon-tile">🇦🇺</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-pb-faint">Australia, for now</p>
              </div>
              <h3 className="text-xl font-bold mb-3 tracking-tight">
                Built for Australian clubs.
              </h3>
              <p className="text-sm text-pb-dim leading-relaxed mb-4">
                BetterStats syncs from PlayHQ — the official Australian cricket data feed. We currently only support clubs playing in the Australian PlayHQ ecosystem.
              </p>
              <p className="text-sm text-pb-dim leading-relaxed">
                Outside Australia and want this for your league? <Link to="/contact" className="text-accent hover:underline">Let us know</Link> — international support is on the roadmap.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

function ContactBlock() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[760px] mx-auto text-center">
        <p className="pill-neutral inline-flex mb-5">Get in touch</p>
        <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">Have a question? <span className="gradient-text">Drop us a line.</span></h2>
        <p className="text-lg text-pb-dim mb-8">
          Wondering if BetterStats is right for your club? Email <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent hover:underline">{SUPPORT_EMAIL}</a>{' '}— happy to chat.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/contact" className="cta-primary">Get in touch →</Link>
          <Link to="/features" className="cta-secondary">See the product</Link>
        </div>
      </div>
    </section>
  )
}

export default function About() {
  usePageMeta({
    title: 'About — BetterStats Cricket Stats Platform',
    description: 'BetterStats was built by a club cricketer at Applecross Cricket Club in Perth, Western Australia, who was tired of maintaining stats in spreadsheets. Now offered to any Australian cricket club.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/about',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Story />
        <Numbers />
        <Principles />
        <Promise_ />
        <ContactBlock />
      </div>
      <MarketingFooter />
    </div>
  )
}
