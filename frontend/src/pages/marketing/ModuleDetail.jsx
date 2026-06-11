import { Link, Navigate, useParams } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import ComparisonTable from '../../components/marketing/ComparisonTable'
import { FORM_URL, COMPARISONS, COMPARISON_SOLO } from '../../data/marketing'
import { moduleBySlug, MODULES_MARKETING, TIER_INFO } from '../../data/modules-marketing'
import ModuleLockup, { ModuleWordmark } from '../../components/ModuleLockup'
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

function tierBlurb(tier) {
  const t = TIER_INFO[tier]
  if (tier === 'better') return `Part of the Better and Best tiers — from $${t.annual}/yr.`
  if (tier === 'best') return `Part of the Best tier — $${t.annual}/yr.`
  return `Included in every tier — from $${t.annual}/yr.`
}

export default function ModuleDetail() {
  const { slug } = useParams()
  const m = moduleBySlug(slug)
  usePageMeta({
    title: m ? `${m.name} — ${m.tagline} | Better Cricket` : 'Modules | Better Cricket',
    description: m ? `${m.name}: ${m.summary}` : 'The Better Cricket platform modules.',
    image: 'https://betterat.cricket/og-image.png',
    url: m ? `https://betterat.cricket/modules/${m.slug}` : 'https://betterat.cricket/modules',
  })
  if (!m) return <Navigate to="/modules" replace />

  const siblings = MODULES_MARKETING.filter((x) => x.slug !== m.slug)
  const comparison = m.compareKey ? COMPARISONS?.[m.compareKey] : null
  const solo = m.compareKey ? COMPARISON_SOLO?.[m.compareKey] : null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        {/* Hero */}
        <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-[1280px] mx-auto relative grid grid-cols-12 gap-10 items-center">
            <div className="col-span-12 lg:col-span-6">
              <div className="flex items-center gap-2.5 mb-6 text-sm">
                <Link to="/modules" className="text-pb-faint hover:text-pb-text">Modules</Link>
                <span className="text-pb-faintest">/</span>
                <span className="text-pb-dim">{m.name}</span>
              </div>
              <div className="flex items-center gap-3 mb-5">
                <img src={m.logo} alt="" className="w-12 h-12 rounded-xl" />
                <span className="pill-neutral">{TIER_INFO[m.tier].label} tier · {m.audience}</span>
              </div>
              <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[64px] tracking-tight leading-[0.95] mb-6">
                <ModuleWordmark name={m.name} accent={m.accent} />
              </h1>
              <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-8 max-w-xl">{m.summary}</p>
              <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-3">
                <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Get this on your club →</a>
                <Link to="/pricing" className="cta-secondary">See pricing</Link>
              </div>
            </div>
            <Reveal className="col-span-12 lg:col-span-6">
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

        {/* Gallery */}
        {m.gallery && m.gallery.length > 0 && (
          <section className="px-4 sm:px-6 lg:px-10 py-16 border-t pb-hairline">
            <div className="max-w-[1100px] mx-auto">
              <Reveal>
                <div className="text-center mb-10">
                  <p className="pill-neutral inline-flex mb-5">See it in action</p>
                  <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">{m.name}, on screen.</h2>
                </div>
              </Reveal>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {m.gallery.map((g, i) => (
                  <Reveal key={g.src} delay={(i % 2) * 80}>
                    <figure className="surface overflow-hidden product-shadow">
                      <img src={g.src} alt={g.caption} loading="lazy" className="block w-full h-auto border-b pb-hairline" />
                      <figcaption className="px-4 py-3 text-sm text-pb-dim">{g.caption}</figcaption>
                    </figure>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Tier band */}
        <section className="px-4 sm:px-6 lg:px-10 py-16 border-t pb-hairline bg-black/20">
          <div className="max-w-[900px] mx-auto surface-strong p-8 lg:p-10 text-center">
            <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-3">Plan</p>
            <h2 className="font-display font-bold text-2xl md:text-3xl mb-3 tracking-tight">{tierBlurb(m.tier)}</h2>
            <p className="text-pb-dim max-w-xl mx-auto mb-7">
              Every plan also includes the BetterStats Core. Not sure which tier you need? The calculator on the pricing page matches a tier to the modules you pick.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link to="/pricing" className="cta-primary">See pricing & calculator →</Link>
              <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-secondary">Request access</a>
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
                    <p className="text-xs text-pb-dim truncate">{TIER_INFO[s.tier].label} tier</p>
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
