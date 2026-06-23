import { Link, Navigate, useParams } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import ZoomableImage from '../../components/marketing/ZoomableImage'
import ComparisonTable from '../../components/marketing/ComparisonTable'
import { COMPARISONS, COMPARISON_SOLO } from '../../data/marketing'
import { moduleBySlug, MODULES_MARKETING, CORE_MARKETING } from '../../data/modules-marketing'
import { CORE, PRICED_MODULES, FANTASY } from '../../data/pricing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'

// Themed faux app-window shown until a real screenshot is dropped at
// /public/marketing/modules/<slug>.jpg (then ScreenshotOrMock upgrades to it).
function ModuleMock({ m }) {
  return (
    <div className="bg-pb-surface border pb-hairline rounded-2xl overflow-hidden shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)]">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b pb-hairline bg-pb-bg">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-400/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/70" />
        </div>
        <div className="ml-4 flex-1 max-w-md mx-auto bg-pb-surface2 rounded px-3 py-1 text-[11px] text-pb-dim font-mono text-center">
          app.betterat.cricket/admin/{m.slug}
        </div>
      </div>
      <div className="p-5">
        <div className="flex items-center gap-3 mb-5">
          <img src={m.logo} alt="" className="w-9 h-9 rounded-lg" />
          <div>
            <p className="font-bold text-sm"><ModuleWordmark name={m.name} accent={m.accent} /></p>
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">{m.audience}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {m.highlights.map((h) => (
            <div key={h} className="bg-pb-surface2 border pb-hairline rounded-lg p-3">
              <span className="block w-1.5 h-1.5 rounded-full mb-2" style={{ background: m.accent }} />
              <p className="text-xs font-medium leading-snug">{h}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function modulePrice(m) {
  if (m.isCore) return `$${CORE.price} a year.`
  if (m.key === FANTASY.key) return `$${FANTASY.price} a year.`
  const p = PRICED_MODULES.find((x) => x.key === m.key)
  return p ? `$${p.price} a year.` : null
}

export default function ModuleDetail() {
  const { slug } = useParams()
  const m = moduleBySlug(slug)

  const priced = m
    ? (PRICED_MODULES.find((x) => x.key === m.key)
        || (m.slug === 'betterstats' ? CORE : null)
        || (m.key === FANTASY.key ? FANTASY : null))
    : null
  // Breadcrumb + product structured data so each module page is read as a
  // priced product sitting under Modules, not an orphan page.
  const jsonLd = m ? [
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://betterat.cricket/' },
        { '@type': 'ListItem', position: 2, name: 'Modules', item: 'https://betterat.cricket/modules' },
        { '@type': 'ListItem', position: 3, name: m.name, item: `https://betterat.cricket/modules/${m.slug}` },
      ],
    },
    ...(priced ? [{
      '@context': 'https://schema.org',
      '@type': 'Product',
      name: `${m.name} — BetterCricket`,
      description: m.summary,
      brand: { '@type': 'Brand', name: 'BetterCricket' },
      url: `https://betterat.cricket/modules/${m.slug}`,
      offers: {
        '@type': 'Offer',
        price: String(priced.price),
        priceCurrency: 'AUD',
        availability: 'https://schema.org/InStock',
        url: 'https://betterat.cricket/pricing',
      },
    }] : []),
  ] : undefined

  usePageMeta({
    title: m ? `${m.name} — ${m.tagline} | BetterCricket` : 'Modules | BetterCricket',
    description: m ? `${m.name}: ${m.summary}` : 'The BetterCricket platform modules.',
    image: 'https://betterat.cricket/og-cover.png',
    url: m ? `https://betterat.cricket/modules/${m.slug}` : 'https://betterat.cricket/modules',
    jsonLd,
  })
  if (!m) return <Navigate to="/modules" replace />

  const siblings = [CORE_MARKETING, ...MODULES_MARKETING].filter((x) => x.slug !== m.slug)
  const comparison = m.compareKey ? COMPARISONS?.[m.compareKey] : null
  const solo = m.compareKey ? COMPARISON_SOLO?.[m.compareKey] : null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        {/* Hero */}
        <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-[1280px] mx-auto relative grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
            <div className="col-span-1 lg:col-span-6">
              <div className="flex items-center gap-2.5 mb-6 text-sm">
                <Link to="/modules" className="text-pb-faint hover:text-pb-text">Modules</Link>
                <span className="text-pb-faintest">/</span>
                <span className="text-pb-dim">{m.name}</span>
              </div>
              <div className="flex items-center gap-3 mb-5">
                <img src={m.logo} alt="" className="w-12 h-12 rounded-xl" />
                <span className="pill-neutral">{m.audience}</span>
              </div>
              <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[64px] tracking-tight leading-[0.95] mb-6">
                <ModuleWordmark name={m.name} accent={m.accent} />
              </h1>
              <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-8 max-w-xl">{m.summary}</p>
              <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-3">
                <Link to="/contact" className="cta-primary">Get Your Club on BetterCricket today!</Link>
                {m.deepTour
                  ? <Link to={m.deepTour} className="cta-secondary">Full feature tour →</Link>
                  : <Link to="/pricing" className="cta-secondary">See pricing</Link>}
              </div>
            </div>
            <Reveal className="col-span-1 lg:col-span-6">
              <div className="relative">
                <div className="absolute -inset-5 bg-accent/8 blur-[60px] rounded-full" />
                <div className="relative product-shadow rounded-2xl">
                  <ScreenshotOrMock src={m.screenshot} alt={`${m.name} screenshot`} fallback={<ModuleMock m={m} />} />
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Highlights strip */}
        <section className="px-4 sm:px-6 lg:px-10 py-10 border-y pb-hairline bg-black/20">
          <div className="max-w-[1200px] mx-auto grid grid-cols-2 lg:grid-cols-4 gap-4">
            {m.highlights.map((h, i) => (
              <Reveal key={h} delay={i * 70}>
                <div className="flex items-start gap-3">
                  <span className="tick mt-0.5">✓</span>
                  <p className="text-sm font-medium leading-snug">{h}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* Features */}
        <section className="px-4 sm:px-6 lg:px-10 py-20">
          <div className="max-w-[1100px] mx-auto">
            <Reveal>
              <div className="text-center mb-12">
                <p className="pill-neutral inline-flex mb-5">What’s inside</p>
                <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">Everything {m.name} does.</h2>
              </div>
            </Reveal>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {m.features.map((f, i) => (
                <Reveal key={f.title} delay={(i % 2) * 80}>
                  <div className="surface p-6 h-full hover:border-accent/30 transition-colors">
                    <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                    <p className="text-sm text-pb-dim leading-relaxed">{f.desc}</p>
                  </div>
                </Reveal>
              ))}
            </div>

            {m.note && (
              <Reveal>
                <div className="surface p-5 mt-6 border-accent/30 bg-accent/[0.05] flex items-start gap-3">
                  <span className="text-accent text-lg">✦</span>
                  <p className="text-sm text-pb-dim">{m.note}</p>
                </div>
              </Reveal>
            )}

            {m.comingSoon && (
              <Reveal>
                <div className="surface p-6 mt-6 border-dashed">
                  <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-3">On the roadmap</p>
                  <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {m.comingSoon.map((c) => (
                      <li key={c} className="flex items-center gap-2.5 text-sm text-pb-dim"><span className="pill-neutral text-[10px]">Soon</span>{c}</li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            )}
          </div>
        </section>

        {/* Fundraiser — the club-fundraiser angle, for modules that have one */}
        {m.fundraiser && (
          <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-accent/[0.04]">
            <div className="max-w-[1000px] mx-auto">
              <Reveal>
                <div className="text-center mb-10">
                  <p className="pill-neutral inline-flex mb-5">{m.fundraiser.eyebrow}</p>
                  <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight mb-5">{m.fundraiser.headline}</h2>
                  <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed">{m.fundraiser.body}</p>
                </div>
              </Reveal>
              <Reveal>
                <div className="surface p-8 lg:p-10 border-accent/30">
                  <ul className="grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-5">
                    {m.fundraiser.points.map((p) => (
                      <li key={p} className="flex items-start gap-3">
                        <span className="tick mt-0.5">✓</span>
                        <p className="text-sm text-pb-dim leading-relaxed">{p}</p>
                      </li>
                    ))}
                  </ul>
                  {m.fundraiser.note && (
                    <p className="text-xs text-pb-faint mt-8 pt-6 border-t pb-hairline text-center max-w-2xl mx-auto leading-relaxed">
                      {m.fundraiser.note}
                    </p>
                  )}
                </div>
              </Reveal>
            </div>
          </section>
        )}

        {/* Deep dives — the module's best four screens, each with real copy */}
        {m.showcase && m.showcase.length > 0 && (
          <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
            <div className="max-w-[1280px] mx-auto">
              <Reveal>
                <div className="text-center mb-16">
                  <p className="pill-neutral inline-flex mb-5">See it in action</p>
                  <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">{m.name}, screen by screen.</h2>
                </div>
              </Reveal>
              <div className="space-y-20 lg:space-y-28">
                {m.showcase.map((s, i) => (
                  <div key={s.src} className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                    <Reveal className={`col-span-1 lg:col-span-5 ${i % 2 === 1 ? 'lg:order-2' : ''}`}>
                      <div className="lg:sticky lg:top-24">
                        <h3 className="text-3xl lg:text-4xl font-bold leading-tight mb-4">{s.headline}</h3>
                        <p className="text-pb-dim leading-relaxed mb-6">{s.body}</p>
                        <ul className="space-y-2.5">
                          {s.points.map((p) => (
                            <li key={p} className="flex items-center gap-3 text-sm"><span className="tick">✓</span>{p}</li>
                          ))}
                        </ul>
                      </div>
                    </Reveal>
                    <Reveal className={`col-span-1 lg:col-span-7 ${i % 2 === 1 ? 'lg:order-1' : ''}`}>
                      <div className="product-shadow rounded-2xl overflow-hidden">
                        <ZoomableImage src={s.src} alt={s.headline} caption={s.headline} className="block w-full h-auto" />
                      </div>
                    </Reveal>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Gallery — the screenshots that didn't make the deep-dive cut */}
        {m.gallery && m.gallery.length > 0 && (
          <section className="px-4 sm:px-6 lg:px-10 py-16 border-t pb-hairline">
            <div className="max-w-[1100px] mx-auto">
              <Reveal>
                <div className="text-center mb-10">
                  <p className="pill-neutral inline-flex mb-5">{m.showcase && m.showcase.length > 0 ? 'And the rest' : 'See it in action'}</p>
                  <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">More of {m.name}, on screen.</h2>
                </div>
              </Reveal>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {m.gallery.map((g, i) => (
                  <Reveal key={g.src} delay={(i % 2) * 80}>
                    <figure className="surface overflow-hidden product-shadow">
                      <ZoomableImage src={g.src} alt={g.caption} caption={g.caption} className="block w-full h-auto border-b pb-hairline" />
                      <figcaption className="px-4 py-3 text-sm text-pb-dim">{g.caption}</figcaption>
                    </figure>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Pricing band */}
        <section className="px-4 sm:px-6 lg:px-10 py-16 border-t pb-hairline bg-black/20">
          <div className="max-w-[900px] mx-auto surface-strong p-8 lg:p-10 text-center">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-3">Pricing</p>
            <h2 className="font-display font-bold text-2xl md:text-3xl mb-3 tracking-tight">{modulePrice(m) || 'Included in every plan.'}</h2>
            <p className="text-pb-dim max-w-xl mx-auto mb-7">
              {m.isCore
                ? 'BetterStats is included in every BetterCricket plan. Add the modules that fit how your club runs, and bundle two or more to save, up to $146 off the full set.'
                : m.key === FANTASY.key
                  ? <>That’s the standalone licence for the whole club, on its own and separate from the module bundle. It stays free for your members to play. Every plan still starts with BetterStats, the Core every club runs on.</>
                  : <>Every plan includes BetterStats. Add {m.name} on its own, or bundle two or more modules and save, up to $146 off the full set. The calculator on the pricing page works out your total.</>}
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link to="/pricing" className="cta-primary">See pricing & calculator →</Link>
              <Link to="/contact" className="cta-secondary">Request access</Link>
            </div>
          </div>
        </section>

        {/* Comparison — table for most modules, "category of one" for BetterIQ */}
        {comparison && (
          <ComparisonTable comparison={comparison} showCTA={false} />
        )}

        {solo && (
          <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline-t">
            <div className="max-w-[1000px] mx-auto">
              <Reveal>
                <div className="text-center mb-10">
                  <p className="pill-neutral inline-flex mb-5">{solo.eyebrow || 'Category of one'}</p>
                  <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
                    {solo.heading}
                  </h2>
                  {solo.sub && <p className="text-lg text-pb-dim max-w-2xl mx-auto">{solo.sub}</p>}
                </div>
              </Reveal>
              <Reveal>
                <div className="surface p-8 lg:p-10">
                  <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
                    {(solo.points || []).map((p) => (
                      <li key={p} className="flex items-start gap-3">
                        <span className="tick mt-0.5">✓</span>
                        <p className="text-sm text-pb-dim leading-relaxed">{p}</p>
                      </li>
                    ))}
                  </ul>
                  {solo.note && (
                    <p className="text-sm text-pb-faint mt-8 pt-6 border-t pb-hairline text-center">
                      {solo.note}
                    </p>
                  )}
                </div>
              </Reveal>
              {solo.cta && (
                <Reveal>
                  <div className="text-center mt-10">
                    <p className="text-base text-pb-dim mb-2 max-w-2xl mx-auto">
                      <span className="gradient-text font-semibold">{solo.cta.line}</span>
                    </p>
                  </div>
                </Reveal>
              )}
            </div>
          </section>
        )}

        {/* Other modules */}
        <section className="px-4 sm:px-6 lg:px-10 py-20">
          <div className="max-w-[1100px] mx-auto">
            <h2 className="text-xl font-bold mb-6">The rest of the platform</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {siblings.map((s) => (
                <Link key={s.slug} to={`/modules/${s.slug}`} className="surface p-5 hover:border-accent/30 transition-colors group flex items-center gap-3">
                  <img src={s.logo} alt="" className="w-10 h-10 rounded-lg flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="font-semibold text-sm"><ModuleWordmark name={s.name} accent={s.accent} /></p>
                    <p className="text-xs text-pb-dim truncate">{s.tagline}</p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </div>
      <MarketingFooter />
    </div>
  )
}
