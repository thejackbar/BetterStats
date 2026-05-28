import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import CountUp from '../../components/marketing/CountUp'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />Made for cricket · by cricketers</p>
        <h1 className="font-display font-bold text-[40px] sm:text-[56px] lg:text-[72px] tracking-tight leading-[0.95] mb-6">
          The cricket stats platform <span className="gradient-text">your club deserves.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim leading-relaxed max-w-2xl mx-auto">
          BetterStats was built to do one thing well — turn the data your club already produces into a public website your members will actually open.
        </p>
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
              BetterStats was built by a group of people fed up with the way club cricket history gets forgotten as platforms change hands. Every migration — MyCricket to PlayHQ, association to association — left decades of records sitting in a corner nobody could reach.
            </p>
            <p>
              Australian cricket clubs are full of people who care about that history — who hit the first century, who took the most wickets in a season, who's closing in on 100 games. <span className="text-pb-text">BetterStats makes that information beautiful, accessible, and automatic.</span>
            </p>
            <p>
              We want to give clubs what they deserve: a better way to keep their history alive and a platform members will actually open every week.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Numbers() {
  const stats = [
    { v: 4500, suffix: '+', label: 'Australian cricket clubs ready to set up' },
    { display: '1M', suffix: '+', label: 'players ready for active profiles' },
    { v: 200, suffix: '+', label: 'pre-built reports in StatLab' },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-16 border-y pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-3 gap-10">
        {stats.map((s, i) => (
          <Reveal key={s.label} delay={i * 80}>
            <div className="text-center">
              <p className="text-4xl md:text-5xl font-bold tabular-nums gradient-text">
                {s.display ? s.display : <CountUp to={s.v} />}{s.suffix}
              </p>
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
    { n: '02', title: 'Honest with data', desc: "If a stat isn't confirmed, we say so. Older aggregates get flagged. We don't invent runs that nobody scored." },
    { n: '03', title: 'No tiers, no upsells', desc: "Every club gets every feature. We hate the SaaS playbook of locking 'the one feature you wanted' behind a Pro tier." },
    { n: '04', title: 'You own the data', desc: "Full CSV export anytime. The data belongs to your club — we just help you visualise it." },
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
                BetterStats currently supports Australian cricket clubs. We're already looking at new regions and want to bring the same platform to leagues elsewhere soon.
              </p>
              <p className="text-sm text-pb-dim leading-relaxed">
                Outside Australia and want this for your league? <Link to="/contact" className="text-accent hover:underline">Let us know</Link> — it helps us prioritise.
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
    description: 'BetterStats was built by a group of people fed up with the way platform migrations leave decades of club cricket history forgotten. A modern, automated stats platform for Australian cricket clubs.',
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
