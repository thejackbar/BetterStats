import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import ZoomableImage from '../../components/marketing/ZoomableImage'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import {
  MockLeaderboard,
  MockPlayerProfile,
  MockYearbook,
  MockHeritageCard,
} from '../../components/marketing/Mockups'
import { SCREENSHOT_PATHS } from '../../data/marketing'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'
import { useSelfServeTrialGate } from '../../hooks/useSelfServeTrialGate'

// ============================================================
// SECTIONS — preserves the existing detailed content for SEO,
// reorganised into hero blocks (first 6 features have visuals)
// and a tight list for the long tail.
// ============================================================
const HERO_SECTIONS = [
  {
    n: '01',
    eyebrow: 'Leaderboards',
    title: 'The ladder, for every category.',
    desc: 'Every batting, bowling and fielding leaderboard your club has ever had, live and filterable.',
    bullets: [
      'Every category, by season, grade, competition and match type',
      'Juniors, women’s and masters in or out with a tap',
      'Rank badges on every player',
      'Updated after every sync',
    ],
    src: SCREENSHOT_PATHS.shortCompetition,
    mock: <MockLeaderboard />,
  },
  {
    n: '02',
    eyebrow: 'Player profiles',
    title: 'A whole career on one page.',
    desc: 'Every player gets a public page that keeps itself up to date, back to their first game.',
    bullets: [
      'Career and season batting, bowling and fielding',
      'Charts, dismissals, partnerships and format splits',
      'Milestones, honours and a shareable stat card',
      'Junior seasons kept out of a senior career by default',
    ],
    src: SCREENSHOT_PATHS.landingHeroCard,
    mock: <MockHeritageCard />,
  },
  {
    n: '03',
    eyebrow: 'Club records',
    title: 'The record books, always current.',
    desc: 'All-time and season bests across the club, with new ones flagged the week they are set.',
    bullets: [
      'Batting, bowling, all-rounders and partnerships',
      'A record at every wicket',
      'Team records such as biggest chases',
    ],
    src: SCREENSHOT_PATHS.featuresHonours,
    mock: <MockPlayerProfile />,
  },
  {
    n: '04',
    eyebrow: 'Scorecards and yearbooks',
    title: 'Every game kept. Every season told.',
    desc: 'The full card for every match, and a season annual that fills itself.',
    bullets: [
      'Both innings, dismissals, fall of wickets and partnerships',
      'A yearbook for each season with honours and top performers',
      'A permanent link for every game and every year',
    ],
    src: SCREENSHOT_PATHS.featuresYearbook,
    mock: <MockYearbook />,
  },
  {
    n: '05',
    eyebrow: 'Player Dashboard and Cards',
    title: 'Give every player a reason to open it.',
    desc: 'Each player gets their own page and a collectable card, from one club link.',
    bullets: [
      'Season panels, last five innings, and availability, Fantasy and fees if you run them',
      'Weekly packs, swaps, sets and challenges, with no paid packs',
      'Switched on from BetterStats',
    ],
    src: SCREENSHOT_PATHS.shortPlayerDash,
    mock: <MockPlayerProfile />,
  },
  {
    n: '06',
    eyebrow: 'Your history',
    title: 'Bring all of it. Keep one record.',
    desc: 'Connect once and your history flows in, then merge the spreadsheets and scorebooks you already have.',
    bullets: [
      'Automatic sync from PlayHQ or Play-Cricket after every game',
      'One spreadsheet, CricketStatz or the scorebook, merged without doubling up',
      'Card review: choose which scorecard the site shows, with an undo',
      'Duplicate players merged in a click',
    ],
    src: SCREENSHOT_PATHS.shortImport,
    mock: <MockLeaderboard />,
  },
  {
    n: '07',
    eyebrow: 'Your club, your colours',
    title: 'A site that looks like you.',
    desc: 'Your crest, colours and fonts, with sponsors placed by tier across every page.',
    bullets: [
      'A major sponsor slot, and Presented by strips on the pages they back',
      'A notification centre for syncs and new milestones',
      'Separate logins for your committee',
    ],
    src: SCREENSHOT_PATHS.sponsorSlot,
    mock: <MockPlayerProfile />,
  },
]

const SHORT_SECTIONS = [
  {
    title: 'StatLab',
    desc: 'Build any table you can think of. 50+ metrics, team records and saved reports.',
    src: SCREENSHOT_PATHS.shortStatlab,
  },
  {
    title: 'Player comparison',
    desc: 'Two players side by side across their careers.',
    src: SCREENSHOT_PATHS.shortCompare,
  },
  {
    title: 'Premierships and honours',
    desc: 'Flags fill in from grand final scorecards, beside awards and the honour board.',
    src: SCREENSHOT_PATHS.premierships,
  },
  {
    title: 'Club Room Mode',
    desc: 'A TV slideshow for the clubhouse, fed by your own records.',
    src: SCREENSHOT_PATHS.shortClubRoom,
  },
  {
    title: 'Opposition analysis',
    desc: 'Every player’s record against each opponent.',
    src: SCREENSHOT_PATHS.shortOpposition,
  },
  {
    title: 'Match archive',
    desc: 'Every game the club has played, with the full scorecard one click away.',
    src: SCREENSHOT_PATHS.shortGames,
  },
]

// Card with optional screenshot thumbnail at top
function ShortCard({ s, delay }) {
  const [imgFailed, setImgFailed] = useState(false)
  return (
    <Reveal delay={delay}>
      <div className="surface h-full overflow-hidden">
        {s.src && !imgFailed && (
          <div className="border-b pb-hairline overflow-hidden h-44 rounded-t-[calc(1rem-1px)]">
            <ZoomableImage
              src={s.src}
              alt={s.title}
              caption={s.desc}
              className="w-full h-full object-cover object-top"
              wrapperClassName="h-full"
              onError={() => setImgFailed(true)}
            />
          </div>
        )}
        <div className="p-6">
          <h3 className="text-lg font-semibold mb-2">{s.title}</h3>
          <p className="text-sm text-pb-dim leading-relaxed">{s.desc}</p>
        </div>
      </div>
    </Reveal>
  )
}

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />In every plan</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-6">
          <span className="gradient-text">BetterStats.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-xl mx-auto leading-relaxed">
          Your club’s whole history, on a public site that updates itself. Included in every BetterCricket plan.
        </p>
      </div>
    </section>
  )
}

// ─── The other modules ────────────────────────────────────────────────────
function BeyondCore() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">The other modules</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">There’s more than stats.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">Bolt on the modules that run your season and your club.</p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {MODULES_MARKETING.map((m, i) => (
            <Reveal key={m.slug} delay={(i % 4) * 70} className="h-full">
              <Link to={`/modules/${m.slug}`} className="surface p-6 h-full flex flex-col hover:border-accent/30 transition-colors group block">
                <div className="flex items-center mb-4">
                  <img src={m.logo} alt="" className="w-10 h-10 rounded-xl" />
                </div>
                <h3 className="text-lg font-semibold mb-1.5"><ModuleWordmark name={m.name} accent={m.accent} /></h3>
                <p className="text-sm text-pb-dim leading-relaxed mb-4 flex-1">{m.tagline}</p>
                <span className="text-sm font-medium inline-flex items-center gap-1" style={{ color: m.accent }}>Explore <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
              </Link>
            </Reveal>
          ))}
        </div>
        <div className="text-center mt-10">
          <Link to="/modules" className="cta-secondary">Tour all modules →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Feature Block (alternating layout) ──────────────────────────────────
function FeatureBlock({ f, idx, onCta }) {
  const flip = idx % 2 === 1
  return (
    <section className={`px-4 sm:px-6 lg:px-10 py-20 ${idx % 2 === 1 ? 'bg-black/20 border-y pb-hairline' : ''}`}>
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className={`grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center ${flip ? 'lg:flex-row-reverse lg:[direction:rtl]' : ''}`}>
            <div className="col-span-1 lg:col-span-5 lg:[direction:ltr]">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/40 flex items-center justify-center text-accent font-bold">{f.n}</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-accent">{f.eyebrow}</p>
              </div>
              <h2 className="text-3xl lg:text-5xl font-bold leading-tight mb-6 tracking-tight">{f.title}</h2>
              <p className="text-pb-dim text-lg mb-6 leading-relaxed">{f.desc}</p>
              <ul className="space-y-3 mb-7">
                {f.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-3 text-pb-dim">
                    <span className="tick mt-0.5">✓</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={onCta} className="cta-primary !text-sm !py-2.5 !px-5">Get Your Club on BetterCricket today!</button>
            </div>
            <div className="col-span-1 lg:col-span-7 lg:[direction:ltr]">
              <div className="relative product-shadow rounded-2xl">
                <ScreenshotOrMock src={f.src} alt={f.eyebrow} fallback={f.mock} />
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Short feature list (long-tail tools) ────────────────────────────────
function ShortFeatures() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">And the rest</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">And a few more.</h2>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SHORT_SECTIONS.map((s, i) => (
            <ShortCard key={s.title} s={s} delay={(i % 3) * 80} />
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── CTA ─────────────────────────────────────────────────────────────────
function FeaturesCTA({ onCta }) {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 relative overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative">
        <div className="surface-strong p-10 lg:p-14 text-center">
          <p className="pill mb-6 mx-auto"><span className="dot" />In every plan</p>
          <h2 className="font-display font-bold text-4xl md:text-5xl mb-5 tracking-tight">BetterStats, <span className="gradient-text">in every plan.</span></h2>
          <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">
            BetterStats is $399 a year, a flat rate per club. Add modules whenever you’re ready.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button type="button" onClick={onCta} className="cta-primary">Request club access →</button>
            <Link to="/pricing" className="cta-secondary">See pricing</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Features() {
  usePageMeta({
    title: 'Features — Automated Cricket Club Stats | BetterCricket',
    description: 'Automatic stats sync, rich player profiles, leaderboards, records and season yearbooks, the foundation of every BetterCricket plan. Plus a dashboard and collectable cards for every player, stats by competition, StatLab custom queries, premierships and honour boards, Club Room Mode and history imports.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/features',
  })
  const { trigger: triggerTrial, modalOpen: trialModalOpen, setModalOpen: setTrialModalOpen, defaultTrialDays } = useSelfServeTrialGate()
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        {HERO_SECTIONS.map((f, i) => (
          <FeatureBlock key={f.n} f={f} idx={i} onCta={triggerTrial} />
        ))}
        <ShortFeatures />
        <Comparison3Way which="betterstats" />
        <BeyondCore />
        <FeaturesCTA onCta={triggerTrial} />
      </div>
      <MarketingFooter />
      {trialModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setTrialModalOpen(false)}
        />
      )}
    </div>
  )
}
