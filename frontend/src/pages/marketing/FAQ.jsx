import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// FAQ content preserved from existing FAQ.jsx — high SEO value + accurate.
// Reorganised into categories for the new layout with sidebar nav.
const CATEGORIES = [
  {
    id: 'setup',
    title: 'Setup & onboarding',
    items: [
      {
        q: 'How long does setup take?',
        a: 'A simple setup is live in under an hour. You give us your PlayHQ club ID; we handle the sync, the historical backfill (however far your data goes), and the initial site polish. Onboarding included on the annual plan.',
      },
      {
        q: 'Where does the data come from?',
        a: 'Direct from PlayHQ and MyCricket. We pull every batting innings, bowling spell, and fielding contribution — going back as far as your data does. No manual data entry, ever.',
      },
      {
        q: 'Do we need to install anything?',
        a: "No software, no plugins, no app store downloads. BetterStats is a public website — your members open the URL on their phone. Admins access through any browser.",
      },
      {
        q: 'Does BetterStats integrate with PlayHQ?',
        a: 'Yes. BetterStats syncs directly with PlayHQ and MyCricket via the official Cricket Australia grassroots data backends. The club does not change how scorers enter results — stats just appear on the BetterStats site automatically after each match.',
      },
      {
        q: "Do we have to switch away from PlayHQ to use BetterStats?",
        a: 'No. BetterStats does not replace PlayHQ — it reads from it. Scorers continue using the PlayHQ app exactly as they do today, and BetterStats adds the public stats website, historical archive, leaderboards and yearbook on top.',
      },
    ],
  },
  {
    id: 'data',
    title: 'Data & accuracy',
    items: [
      {
        q: 'How far back does the historical data go?',
        a: 'BetterStats imports the full historical dataset Cricket Australia exposes for your club. In practice this typically reaches back to the early 2000s and, for many clubs that pre-date the MyCricket migration, into the 1980s and 1970s.',
      },
      {
        q: 'What happens to old career averages?',
        a: 'We rebuild them — accurately. Many clubs have career stats spread across MyCricket aggregates, PlayHQ, and a spreadsheet. We reconcile them all and flag anything inconsistent so the statistician can sign off.',
      },
      {
        q: "What if our scorers haven't been perfect?",
        a: "We've built tools for it: merge duplicate players, fix mis-attributed innings, tag aliases. Most clubs find ~10% of their history needs a clean-up — we make it 5-minute work, not weekends.",
      },
      {
        q: 'How are duplicate player records handled?',
        a: 'PlayHQ occasionally creates a new ID for an existing player, which would normally split their stats. BetterStats has a one-click merge tool in the admin panel that combines the records and preserves every historical innings, spell, catch and partnership.',
      },
      {
        q: 'Do we own the data?',
        a: "Always. Full CSV export at any time. The platform is a lens on data PlayHQ and MyCricket already hold — we're not the source of truth, we're the layer that finally makes it useful.",
      },
    ],
  },
  {
    id: 'features',
    title: 'Product & features',
    items: [
      {
        q: 'What is BetterStats?',
        a: "BetterStats is an automated cricket statistics platform for Australian club cricket. It pulls every batting, bowling and fielding stat from PlayHQ and MyCricket and turns it into a beautiful public club website — with player profiles, leaderboards, all-time records, partnerships, awards, season yearbooks and shareable stat cards.",
      },
      {
        q: 'How is BetterStats different from PlayHQ or MyCricket?',
        a: "PlayHQ and MyCricket show only the current season's stats, hide partnership and milestone data, and offer no shareable, club-branded experience. BetterStats sits alongside PlayHQ — it reads the same official data and adds the presentation, history and analytics layer your club, parents and sponsors actually want.",
      },
      {
        q: 'Does each player get their own profile?',
        a: 'Yes. Every player gets a public profile page with career stats, season-by-season breakdown, career progression charts, dismissal breakdowns, batting-position analysis, partnership history, milestone badges, club awards and a one-tap shareable social card.',
      },
      {
        q: 'Can BetterStats publish a season yearbook?',
        a: 'Yes. BetterStats automatically generates a publishable digital yearbook for each season, populated with results, batting/bowling/fielding/all-rounder honours, partnership records and a season-progression chart. Admins can layer on a President\'s Report, Coach\'s Report, photo galleries and custom awards.',
      },
      {
        q: 'Can I get a shareable cricket stat card?',
        a: 'Yes. Every player profile has a clean, branded shareable stat card showing career or season stats, club rank badges (e.g. #1 Runs, #2 Wickets), milestone indicators and the player photo. One tap to share natively on mobile.',
      },
    ],
  },
  {
    id: 'customisation',
    title: 'Customisation & branding',
    items: [
      {
        q: 'Can we customise the look?',
        a: 'Yes — club colours, crest, sponsor logos, custom hero imagery, social card themes. Our team handles the design polish; you sign off. Annual plan includes one custom branding pass.',
      },
      {
        q: 'Can we use our own domain?',
        a: 'Yes. Either a subdomain we provide (yourclub.betterstats.cricket) or your own domain (stats.yourclub.com.au). DNS setup included.',
      },
      {
        q: 'Can we add custom pages or content?',
        a: 'Yes — every site comes with editorial slots for committee notes, news posts, and free-form content. CMS access for committee members included.',
      },
      {
        q: 'Sponsor logos — where do they appear?',
        a: 'Header, footer, yearbook, share cards, match reports. We make sure your sponsors get the placement they paid for.',
      },
    ],
  },
  {
    id: 'pricing',
    title: 'Pricing & contracts',
    items: [
      {
        q: 'How much does BetterStats cost?',
        a: 'BetterStats is $49 AUD per club per month, or $400 AUD per club per year (saves $188 vs. monthly). One plan covers unlimited players, unlimited seasons, automatic PlayHQ/MyCricket sync, the full public stats website, season yearbooks, awards & honours management and the admin panel. Setup and the first historical sync are handled by the BetterStats team at no extra cost. No lock-in, cancel anytime.',
      },
      {
        q: 'Are there setup fees?',
        a: 'No setup fees on the annual plan. Monthly plan customers can pay $99 once for hands-on onboarding, or do it themselves through our admin guides.',
      },
      {
        q: 'Can we cancel anytime?',
        a: 'Yes. Cancel any time on monthly — your site stays up to the end of the billing month. Annual cancels at the end of the term. Data exports cleanly to CSV.',
      },
      {
        q: 'Do you offer a free trial?',
        a: "We don't run free trials, but the monthly plan acts like one. $49 gets you the full platform for 30 days. If you cancel, you only pay for that month.",
      },
      {
        q: 'Do you offer discounts for junior-only clubs?',
        a: 'Yes — junior-only clubs pay $250/year. Contact us for the discount code.',
      },
    ],
  },
  {
    id: 'meta',
    title: 'Hosting & misc',
    items: [
      {
        q: 'Where is BetterStats hosted and what data does it store?',
        a: 'BetterStats is hosted on infrastructure in Australia. Stored data includes the public cricket statistics pulled from PlayHQ/MyCricket, club logos and admin login details. See the privacy policy for the full breakdown.',
      },
      {
        q: 'Who is BetterStats for?',
        a: 'Australian cricket clubs of any size — premier grade, district, suburban, country and association clubs — and the stats volunteers, captains, coaches, committees, players, parents and sponsors who care about the club. Currently focused on Australia, initially proven at Applecross Cricket Club in Perth.',
      },
      {
        q: 'How do I request access for my club?',
        a: 'Fill in the request-access form linked from the homepage, features page, pricing page and contact page — or email betterstatsau@gmail.com. The BetterStats team handles the technical setup.',
      },
    ],
  },
]

// Flatten for JSON-LD
const ALL_FAQS = CATEGORIES.flatMap((c) => c.items)
const FAQ_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: ALL_FAQS.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
}

function FAQItem({ q, a }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="surface overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-6 p-5 text-left">
        <span className="text-base md:text-lg font-semibold pr-4">{q}</span>
        <span className="w-8 h-8 rounded-full bg-pb-surface2 flex items-center justify-center text-accent text-lg flex-shrink-0">{open ? '−' : '+'}</span>
      </button>
      <div className={`overflow-hidden transition-all duration-500 ${open ? 'max-h-[600px]' : 'max-h-0'}`}>
        <p className="px-5 pb-5 text-sm text-pb-dim leading-relaxed">{a}</p>
      </div>
    </div>
  )
}

function Hero() {
  return (
    <section className="relative pt-32 pb-12 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />Last updated · {new Date().toLocaleDateString('en-AU', { month: 'long', year: 'numeric' })}</p>
        <h1 className="font-display font-bold text-[40px] sm:text-[56px] lg:text-[72px] tracking-tight leading-[0.95] mb-6">
          Questions clubs <span className="gradient-text">always ask.</span>
        </h1>
        <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed">
          Can't find your answer? Email <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent hover:underline">{SUPPORT_EMAIL}</a> — we usually reply same-day.
        </p>
      </div>
    </section>
  )
}

function FAQList() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-12">
      <div className="max-w-[1100px] mx-auto grid grid-cols-12 gap-10">
        <aside className="col-span-12 md:col-span-3">
          <div className="md:sticky md:top-24">
            <p className="pill-neutral inline-flex mb-4">Jump to</p>
            <nav className="space-y-2">
              {CATEGORIES.map((c, i) => (
                <a key={c.id} href={`#cat-${c.id}`} className="block text-sm font-medium text-pb-dim hover:text-pb-text transition-colors py-1">
                  {String(i + 1).padStart(2, '0')} · {c.title}
                </a>
              ))}
            </nav>
          </div>
        </aside>

        <div className="col-span-12 md:col-span-9 space-y-12">
          {CATEGORIES.map((cat) => (
            <div key={cat.id} id={`cat-${cat.id}`}>
              <h2 className="text-2xl font-bold mb-5 scroll-mt-24">{cat.title}</h2>
              <div className="space-y-2">
                {cat.items.map((it) => (
                  <FAQItem key={it.q} {...it} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function CTA() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
      <div className="max-w-[800px] mx-auto text-center">
        <h2 className="font-display font-bold text-3xl md:text-5xl mb-5 tracking-tight">Still have a question?</h2>
        <p className="text-lg text-pb-dim mb-8">
          Email us, or jump on a 15-minute call. We'd rather over-explain than have you sign up confused.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/contact" className="cta-primary">Get in touch →</Link>
          <a href={`mailto:${SUPPORT_EMAIL}`} className="cta-secondary">Email us directly</a>
        </div>
      </div>
    </section>
  )
}

export default function FAQ() {
  usePageMeta({
    title: 'FAQ — Cricket Club Stats Platform Questions | BetterStats',
    description: 'Frequently asked questions about BetterStats — pricing, PlayHQ and MyCricket integration, onboarding, historical data depth, player profiles, season yearbooks, and how it works for Australian cricket clubs.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/faq',
    jsonLd: FAQ_JSONLD,
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <FAQList />
        <CTA />
      </div>
      <MarketingFooter />
    </div>
  )
}
