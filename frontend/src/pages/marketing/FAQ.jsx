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
        a: "BetterCricket imports your club's full match history automatically and keeps it current after every match, with no spreadsheets and no data entry. Anything that isn't already online can be imported with our simple CSV templates and automated import tools.",
      },
      {
        q: 'Do we need to install anything?',
        a: "No software, plugins or app store downloads. BetterCricket is a public website that works across phones, tablets and laptops, and your members and admins just open the URL.",
      },
      {
        q: 'Do we have to change how our club scores or registers?',
        a: "No. BetterCricket sits on top of however your club already runs match day. We keep your history, analyse it and present it beautifully, plus we add modules that help automate and centralise practically all of your club functions. Nothing about your scoring or registration changes, and the stats just turn up on your site automatically.",
      },
      {
        q: 'Do we have to move away from anything to use BetterCricket?',
        a: "No. BetterCricket complements the way you already run your club rather than replacing it. Keep scoring exactly the way you do today, and BetterCricket adds the public stats website, historical archive, leaderboards and yearbook on top, plus player availability tracking, net management, team selection, opposition scouting, social posts, fee management, member emails and more.",
      },
    ],
  },
  {
    id: 'data',
    title: 'Data & accuracy',
    items: [
      {
        q: 'How far back does the historical data go?',
        a: "As far back as you can go. Every club is different, so we bring across whatever's available and you can layer manually-imported records on top of that.",
      },
      {
        q: 'What happens to old career averages?',
        a: "We rebuild them, accurately. Many clubs have career stats spread across old aggregates, recent seasons and a spreadsheet. We reconcile them all and flag anything inconsistent so the statistician can sign off.",
      },
      {
        q: "What if our scorers haven't been perfect?",
        a: "We've built tools for it: merge duplicate players, fix mis-attributed innings, tag aliases. Most clubs find about 10% of their history needs a clean-up. We make it 5 minutes' work, not weekends.",
      },
      {
        q: 'How are duplicate player records handled?',
        a: "When the same player ends up with two records, their stats can split across both. BetterCricket has a one-click merge tool that combines the records and preserves every innings, spell, catch and partnership, and you can undo it if you change your mind.",
      },
      {
        q: 'Do we own the data?',
        a: "Always. The data belongs to your club. We just help you analyse and visualise it. You can export all of your data to CSV any time.",
      },
    ],
  },
  {
    id: 'features',
    title: 'Product & features',
    items: [
      {
        q: 'What is BetterCricket?',
        a: "BetterCricket is a modular platform for Australian club cricket, owned by BetterSports. Every club starts with BetterStats: it brings in every batting, bowling and fielding stat and turns it into a beautiful public club website with player profiles, leaderboards, all-time records, partnerships, awards, season yearbooks and shareable stat cards. On top of BetterStats you can add modules: BetterSelect (player availability, team selection and net manager), BetterSocials (social-post generation and a CRM to manage your club's website), BetterAdmin (member fee management, bulk emailing, and merch and stock management, coming soon) and BetterIQ (deep analytics and opposition scouting).",
      },
      {
        q: 'Do we have to change how our club scores or registers to use BetterCricket?',
        a: "No. BetterCricket sits on top of however your club already runs match day. We keep your history, analyse it and present it beautifully, plus we add modules that help automate and centralise practically all of your club functions. Nothing about your scoring or registration changes. We take your club's full match history and add the presentation, history and analytics layer that your club, members, parents and sponsors actually want.",
      },
      {
        q: 'Does each player get their own profile?',
        a: 'Yes. Every player gets a public profile page with career stats, season-by-season breakdown, career progression charts, dismissal breakdowns, batting-position analysis, partnership history, milestone badges, club awards and a one-tap shareable social card.',
      },
      {
        q: 'Can BetterCricket publish a season yearbook?',
        a: 'Yes. BetterCricket automatically generates a publishable digital yearbook for each season, populated with results, batting/bowling/fielding/all-rounder honours, partnership records and a season-progression chart. Admins can layer on a President\'s Report, Coach\'s Report, photo galleries and custom awards.',
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
        a: "Yes. You choose the layout and appearance of your club's site: colours, crest, sponsor placement and hero imagery. You have full control of how it looks.",
      },
      {
        q: 'Can we use our own domain?',
        a: "Every club gets a unique URL for its BetterCricket site by default (betterat.cricket/your-clubname). In addition, if you've selected the BetterSocials module, you'll also get a betterat.cricket/your-clubname/website URL.",
      },
      {
        q: 'Where do sponsor logos appear?',
        a: 'Currently in the site footer and in the season yearbook. We\'ll be expanding sponsor placements over time.',
      },
    ],
  },
  {
    id: 'pricing',
    title: 'Pricing & modules',
    items: [
      {
        q: 'How much does it cost?',
        a: "BetterCricket is modular. BetterStats is $399 a year and includes your public stats site. From there you add only the modules you want: BetterSelect, BetterSocials and BetterAdmin are $149 a year each, and BetterIQ is $249. There's a set discount when you bundle two or more modules: $48 off for two, $97 off for three, and up to $146 off the full set, which brings BetterStats plus every module to $949 a year. Every price covers unlimited players, seasons and teams, whatever the club's size.",
      },
      {
        q: 'What does each module include?',
        a: "BetterStats brings in every batting, bowling and fielding stat and turns it into your public club site, with player profiles, leaderboards, all-time records, partnerships, awards, season yearbooks and shareable stat cards. BetterSelect adds player availability, team selection and the net manager. BetterSocials adds social-post generation and a CRM with template pages and your club stats to run your public website. BetterAdmin adds member fee management, bulk emailing, and merch and stock management (coming soon). BetterIQ adds deep analytics and opposition scouting.",
      },
      {
        q: 'Can I add just one module?',
        a: "Yes. For a small additional annual charge, any single module can be added to your current subscription.",
      },
      {
        q: 'Does the price change based on club size?',
        a: "No. Every price is a flat rate per club. One team or fifty teams, juniors and seniors, men's and women's, the price is the same. There's no per-team, per-player or per-grade pricing.",
      },
      {
        q: 'Monthly or annual?',
        a: "BetterCricket is an annual licence, billed once a year.",
      },
      {
        q: 'Can we add modules later?',
        a: "Yes. You can add new modules at any time and the entitlements switch on immediately. Adding a module is an annual commitment.",
      },
      {
        q: 'Are there setup fees?',
        a: "Up to two hours of dedicated support is included in your first year on BetterStats. If all of your club's match history is already uploaded, you should be up and running in no time. We'll guide you through merging players and grades if needed, and show you how to load all of your club's history into BetterCricket.",
      },
      {
        q: 'Do you offer a free trial?',
        a: "Yes. We offer a 14-day free trial of every BetterCricket module, so you can try the lot before you commit.",
      },
      {
        q: 'Do you offer discounts for junior-only clubs?',
        a: "Yes. A junior club linked to a senior club that's currently subscribed to BetterCricket gets a discount. Contact us for the code.",
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
        q: 'Where is BetterCricket hosted and what data does it store?',
        a: 'BetterCricket is hosted on infrastructure in Australia. Stored data includes your club\'s public cricket statistics, club logos and admin login details. See the privacy policy for the full breakdown.',
      },
      {
        q: 'Who is BetterCricket for?',
        a: "Australian cricket clubs of any size: premier grade, district, suburban, country, association and social clubs, plus the stats volunteers, captains, coaches, committees, members, players, parents and sponsors who care about the club.",
      },
      {
        q: 'How do I request access for my club?',
        a: "Fill in the request-access form (tap the button on the homepage) or email betteratcricket@gmail.com. The BetterCricket team handles the technical setup.",
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
          Can't find your answer? Email <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent hover:underline">{SUPPORT_EMAIL}</a>. We usually reply same-day.
        </p>
      </div>
    </section>
  )
}

function FAQList() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-12">
      <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-12 gap-10">
        <aside className="col-span-1 md:col-span-3">
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

        <div className="col-span-1 md:col-span-9 space-y-12">
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
    title: 'FAQ — BetterCricket | Cricket club platform questions',
    description: 'Frequently asked questions about BetterCricket: pricing, onboarding, historical data depth, player profiles, season yearbooks, and how it works for Australian cricket clubs.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/faq',
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
