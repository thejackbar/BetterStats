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
        a: 'A simple setup is live in under an hour. We start the first sync to bring your data in, then walk you through a quick clean-up so the site looks the way you want before it goes public.',
      },
      {
        q: 'Where does the data come from?',
        a: "We can pull your club's existing data automatically and we can import anything that isn't online manually — using our simple CSV templates and automated import tools.",
      },
      {
        q: 'Do we need to install anything?',
        a: "No software, no plugins, no app store downloads. BetterStats is a public website that works across phones, tablets and laptops — your members and admins just open the URL.",
      },
      {
        q: 'Does BetterStats integrate with the platforms we already use?',
        a: 'Yes. BetterStats works alongside the tools your club already uses — your scorers don\'t change anything about how they record matches, and the stats turn up on your BetterStats site automatically.',
      },
      {
        q: "Do we have to move away from anything to use BetterStats?",
        a: 'No. BetterStats complements the platforms you already use rather than replacing them. Keep scoring exactly the way you do today; BetterStats adds the public stats website, historical archive, leaderboards and yearbook on top.',
      },
    ],
  },
  {
    id: 'data',
    title: 'Data & accuracy',
    items: [
      {
        q: 'How far back does the historical data go?',
        a: 'As far back as it can go. Every club is different — we bring across whatever\'s available and you can layer manually-imported records on top of that.',
      },
      {
        q: 'What happens to old career averages?',
        a: 'We rebuild them — accurately. Many clubs have career stats spread across old aggregates, current platforms and a spreadsheet. We reconcile them all and flag anything inconsistent so the statistician can sign off.',
      },
      {
        q: "What if our scorers haven't been perfect?",
        a: "We've built tools for it: merge duplicate players, fix mis-attributed innings, tag aliases. Most clubs find ~10% of their history needs a clean-up — we make it 5-minute work, not weekends.",
      },
      {
        q: 'How are duplicate player records handled?',
        a: "When the same player ends up with more than one profile, their stats can split across both. BetterStats has a one-click merge tool that combines the records and preserves every innings, spell, catch and partnership — and you can undo it if you change your mind.",
      },
      {
        q: 'Do we own the data?',
        a: "Always. The data belongs to your club — we just help you visualise it. Full CSV export at any time.",
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
        a: 'Yes. You choose the layout and appearance of your club site — colours, crest, sponsor placement, hero imagery. You have full control of how it looks.',
      },
      {
        q: 'Can we use our own domain?',
        a: 'Every club gets a BetterStats link by default (yourclub.betterstats.cricket). Custom domains are available for an additional fee — get in touch and we\'ll set it up.',
      },
      {
        q: 'Sponsor logos — where do they appear?',
        a: 'Currently in the site footer and in the season yearbook. We\'ll be expanding sponsor placements over time.',
      },
    ],
  },
  {
    id: 'pricing',
    title: 'Pricing & contracts',
    items: [
      {
        q: 'How much does BetterStats cost?',
        a: 'BetterStats is $49 AUD per club per month, or $400 AUD per club per year (saves $188 vs. monthly). One plan covers unlimited players, unlimited seasons, automatic data sync, the full public stats website, season yearbooks, awards & honours management and the admin panel.',
      },
      {
        q: 'Are there setup fees?',
        a: "We don't have a flat setup fee. We do a short consultation, look at how much historical data your club has and how much clean-up it'll need, then work out a low-cost plan that fits.",
      },
      {
        q: 'Can we cancel anytime?',
        a: "On monthly, yes — when you cancel, the public page comes down but your data isn't lost. The annual plan runs to the end of its term.",
      },
      {
        q: 'Do you offer a free trial?',
        a: "We don't run free trials — but we're happy to demo your club for you so you can see exactly what BetterStats will look like with your data.",
      },
      {
        q: 'Do you offer discounts for junior-only clubs?',
        a: 'Yes — junior-only clubs get a discount, but only if the senior club is already onboarded with BetterStats. Contact us for the discount code.',
      },
      {
        q: 'How do we pay?',
        a: "Right now it's bank transfer / PayID. Most clubs don't have a card and we don't want to put financial pressure on volunteers. Card payments are on the roadmap.",
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
        a: 'Australian cricket clubs of any size — premier grade, district, suburban, country and association clubs — and the stats volunteers, captains, coaches, committees, players, parents and sponsors who care about the club.',
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
