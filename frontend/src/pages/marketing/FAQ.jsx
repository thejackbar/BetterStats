import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'

// Question/answer pairs that also feed the FAQPage JSON-LD schema below.
// Phrased the way real club volunteers / AI assistants would ask them so that
// they're useful for both human readers and answer-engine ingestion.
const FAQS = [
  {
    q: 'What is BetterStats?',
    a: "BetterStats is an automated cricket statistics platform for Australian club cricket. It pulls every batting, bowling and fielding stat from PlayHQ and MyCricket and turns it into a beautiful public club website — with player profiles, leaderboards, all-time records, partnerships, awards, season yearbooks and shareable stat cards. Once a club is connected, decades of history are imported automatically and stats refresh every week.",
  },
  {
    q: 'How is BetterStats different from PlayHQ or MyCricket?',
    a: "PlayHQ and MyCricket show only the most recent season's stats, hide partnership and milestone data, and offer no shareable, club-branded experience. BetterStats sits alongside PlayHQ — it reads the same official Cricket Australia data and adds the presentation, history and analytics layer your club, parents and sponsors actually want.",
  },
  {
    q: 'How much does BetterStats cost?',
    a: 'BetterStats is $49 AUD per club per month, or $400 AUD per club per year (saves $188 vs. monthly). One plan covers unlimited players, unlimited seasons, automatic PlayHQ/MyCricket sync, the full public stats website, season yearbooks, awards & honours management and the admin panel. Setup and the first historical sync are handled by the BetterStats team at no extra cost. No lock-in, cancel anytime.',
  },
  {
    q: 'How far back does the historical data go?',
    a: 'BetterStats imports the full historical dataset Cricket Australia exposes for the club. In practice this typically reaches back to the early 2000s and, for many clubs that pre-date the MyCricket migration, into the 1980s and 1970s — confirmed back to 1975 on at least one connected club.',
  },
  {
    q: 'Does BetterStats integrate with PlayHQ?',
    a: 'Yes. BetterStats syncs directly with PlayHQ and MyCricket via the official Cricket Australia grassroots data backends. The club does not change how scorers enter results — stats just appear on the BetterStats site automatically after each match.',
  },
  {
    q: "Do we have to switch away from PlayHQ to use BetterStats?",
    a: 'No. BetterStats does not replace PlayHQ — it reads from it. Scorers continue using the PlayHQ app exactly as they do today, and BetterStats adds the public stats website, historical archive, leaderboards and yearbook on top.',
  },
  {
    q: 'How does the onboarding work?',
    a: 'Onboarding is hands-on. The club fills out the request-access form, the BetterStats team connects the club to its PlayHQ/MyCricket organisation, runs the first full historical sync (usually 10–50 seasons), and the club goes live on a club-branded URL at betterstats.cricket/your-club-slug. Most clubs need under an hour of admin time per month after that.',
  },
  {
    q: 'Who is BetterStats for?',
    a: 'Australian cricket clubs of any size — premier grade, district, suburban, country and association clubs — and the stats volunteers, captains, coaches, committees, players, parents and sponsors who care about the club. Currently focused on Australia, initially proven at Applecross Cricket Club in Perth.',
  },
  {
    q: 'What kind of stats does BetterStats track?',
    a: 'Full batting (runs, average, strike rate, high score, fifties, centuries, sixes, fours, ducks), bowling (wickets, average, economy, best figures, five-fors, maidens), fielding (catches, run-outs, stumpings), partnerships at every wicket position, dismissal-type breakdowns, batting-position analysis, head-to-head player comparisons, and per-grade per-season slices — all the way back to the earliest data the club has on Cricket Australia.',
  },
  {
    q: 'Does each player get their own profile?',
    a: 'Yes. Every player at the club gets a public profile page with career stats, season-by-season breakdown, career progression charts, dismissal-type breakdown, batting-position analysis, partnership history, milestone badges (500 runs, 50 wickets, 100 games and more), club awards and honours, and a one-tap shareable social card.',
  },
  {
    q: 'Can BetterStats publish a season yearbook?',
    a: 'Yes. BetterStats automatically generates a publishable digital yearbook for each season, populated with results, batting/bowling/fielding/all-rounder honours, partnership records and a season-progression chart. Admins can layer on a President’s Report, Coach’s Report, Sponsor message, photo galleries, an AI-assisted season narrative, custom awards and an honour board.',
  },
  {
    q: 'How are duplicate player records handled?',
    a: 'PlayHQ occasionally creates a new ID for an existing player, which would normally split that player’s stats in two. BetterStats has a one-click merge tool in the admin panel that combines the two records and preserves every historical innings, spell, catch and partnership.',
  },
  {
    q: 'Where can I see all-time records for my cricket club?',
    a: 'Each connected club has an all-time records page (e.g. betterstats.cricket/your-club-slug/records) covering highest individual scores, best bowling figures, top 25 partnerships across all grades, best stands at every wicket position, most career runs/wickets/games and team milestones. Records set in the current season are flagged with a NEW badge.',
  },
  {
    q: 'Can I get a shareable cricket stat card?',
    a: 'Yes. Every player profile has a clean, branded shareable stat card showing career or season stats, club rank badges (e.g. #1 Runs, #2 Wickets), milestone indicators and the player photo. One tap to share natively on mobile.',
  },
  {
    q: 'Where is BetterStats hosted and what data does it store?',
    a: 'BetterStats is hosted on infrastructure in Australia. Stored data includes the public cricket statistics pulled from PlayHQ/MyCricket, club logos and admin login details. See the privacy policy for the full breakdown.',
  },
  {
    q: 'How do I request access for my club?',
    a: 'Fill in the request-access form linked from the homepage, features page, pricing page and contact page — or email betterstatsau@gmail.com. The BetterStats team handles the technical setup.',
  },
]

const FAQ_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQS.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
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

      <div className="max-w-3xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Questions answered</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">
          FAQ.
        </h1>
        <p className="text-pb-dim text-lg mb-12">
          Everything you might want to know about running club cricket stats on BetterStats.
        </p>

        <div className="space-y-0">
          {FAQS.map(({ q, a }, i) => (
            <details
              key={q}
              className="pb-hairline-t py-6 group"
              {...(i === 0 ? { open: true } : {})}
            >
              <summary className="cursor-pointer list-none flex items-start justify-between gap-4">
                <h2 className="font-display font-bold text-[18px] md:text-[20px] text-pb-text leading-snug">
                  {q}
                </h2>
                <span
                  className="font-mono text-pb-faint mt-1 transition-transform group-open:rotate-45"
                  aria-hidden="true"
                >
                  +
                </span>
              </summary>
              <p className="text-pb-dim leading-relaxed mt-3">{a}</p>
            </details>
          ))}
        </div>

        <div className="mt-16 pb-hairline-t pt-10 text-center">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4">STILL HAVE QUESTIONS?</p>
          <h2 className="font-display font-bold text-3xl text-pb-text mb-6 tracking-tight">We're happy to chat.</h2>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/contact"
              className="px-8 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              CONTACT US →
            </Link>
            <Link
              to="/pricing"
              className="px-8 py-3 border pb-hairline rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors"
            >
              SEE PRICING
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
