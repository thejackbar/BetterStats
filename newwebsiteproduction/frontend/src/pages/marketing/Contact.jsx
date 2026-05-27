import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import { FORM_URL, SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

function ContactPanel() {
  return (
    <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative">
        <div className="grid grid-cols-12 gap-10">
          <div className="col-span-12 lg:col-span-5">
            <p className="pill mb-6 inline-flex"><span className="dot" />Onboarding within 48 hours</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[60px] tracking-tight leading-[0.95] mb-6">
              Tell us about <span className="gradient-text">your club.</span>
            </h1>
            <p className="text-lg text-pb-dim leading-relaxed mb-8">
              Drop your details and we'll come back within 24 hours with a short demo specific to your club, your colours, and (if you give us a PlayHQ URL) your actual data.
            </p>

            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">✉</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Email</p>
                  <a href={`mailto:${SUPPORT_EMAIL}`} className="text-sm text-accent hover:underline">{SUPPORT_EMAIL}</a>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">⚲</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Based in</p>
                  <p className="text-sm text-pb-dim">Perth, WA · We work with clubs Australia-wide.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">⏱</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Response time</p>
                  <p className="text-sm text-pb-dim">Within 24 hours, usually same day.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-7">
            <Reveal>
              <div className="surface p-7 lg:p-9">
                <div className="mb-6">
                  <h2 className="text-2xl font-bold mb-2">Request club access</h2>
                  <p className="text-sm text-pb-dim">
                    The fastest way to get going is our short access form. Takes ~5 minutes.
                  </p>
                </div>

                <a
                  href={FORM_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="cta-primary w-full justify-center !py-4 mb-6"
                  aria-label="Open BetterStats access form (opens in new tab)"
                >
                  Open the request form ↗
                </a>

                <p className="text-xs text-pb-faint text-center mb-6">
                  The form asks for your club name, PlayHQ org / club URL, and how you want us to help. We respond within 24 hours.
                </p>

                <div className="pt-6 border-t pb-hairline">
                  <p className="text-sm font-semibold mb-3">Prefer email?</p>
                  <p className="text-sm text-pb-dim mb-3">
                    For anything else, drop a line directly.
                  </p>
                  <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent text-sm font-medium hover:underline">
                    {SUPPORT_EMAIL} →
                  </a>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function Contact() {
  usePageMeta({
    title: 'Contact — Request Access for Your Cricket Club | BetterStats',
    description: 'Request access for your Australian cricket club, ask a question, or email the BetterStats team directly at betterstatsau@gmail.com.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/contact',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <ContactPanel />
      </div>
      <MarketingFooter />
    </div>
  )
}
