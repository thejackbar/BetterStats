import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function Privacy() {
  usePageMeta({
    title: 'Privacy Policy | BetterCricket',
    description: 'How BetterCricket, provided by BetterSports, collects, stores and handles club, player and account information under the Australian Privacy Act.',
    url: 'https://betterat.cricket/privacy',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        <h1 className="font-display font-bold text-4xl mb-2">Privacy Policy</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: 9 June 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Who we are</h2>
            <p>
              BetterCricket is provided by BetterSports (ABN 32 624 335 397), a Registered Business Name of
              KlubPro Pty Ltd, in Perth, Western Australia. This policy explains how we collect, use, store and
              handle personal information,
              in accordance with the Australian Privacy Act 1988 and the Australian Privacy Principles (APPs). It
              applies to the BetterCricket service and websites.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">What we collect</h2>
            <ul className="space-y-2 ml-4 list-disc">
              <li><strong className="text-pb-text">Club and player information:</strong> Player names and cricket statistics derived from your club's own match data, along with club details such as name, contact email and branding preferences.</li>
              <li><strong className="text-pb-text">Admin account information:</strong> The email address, mobile number, username and password used to sign in to a club's admin area. Passwords are stored only as a secure hash, never in plain text.</li>
              <li><strong className="text-pb-text">Usage and analytics data:</strong> Standard web logs and analytics such as IP address, device and browser details, and pages viewed, used to keep the Service secure and to understand and improve how it's used.</li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">How we use information</h2>
            <p>
              We use the information we collect to provide and operate the Service: to display statistics on
              public club pages, give administrators access to their club's admin area, run the modules included
              in a club's plan, keep the Service secure, respond to support requests, and improve how everything
              works. We don't use your information for unrelated purposes without telling you.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Where match data comes from</h2>
            <p>
              The statistics in BetterCricket are derived from your club's own match data, the records your club
              produces and maintains. We are not the source of that underlying data, and we don't guarantee that
              every figure is complete or error-free. If something looks wrong, your club administrator can correct
              or update it.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Public club pages</h2>
            <p>
              Club statistics pages are public by design. Player names and their performance statistics are shown
              on these pages so that clubs and their communities can follow and celebrate their cricket. If an
              individual would prefer their statistics not to appear, they can contact their club administrator or
              email us, and we'll work with the club to address the request.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Storage and security</h2>
            <p>
              We take reasonable steps to protect personal information from loss, misuse and unauthorised access.
              Data is transmitted over encrypted connections (HTTPS), account passwords are stored as secure
              hashes, and access to club admin areas is restricted to authorised users. No system can be
              guaranteed completely secure, but we work to keep your information safe.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">We don't sell your data</h2>
            <p>
              We do not sell personal information, and we do not share it with third parties for their own
              marketing. We only share information with service providers who help us run the Service (for example,
              hosting and email), and only as needed for them to do so, or where we're required to by law.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Your rights</h2>
            <p>
              You can ask to access the personal information we hold about you, or to have it corrected, by
              emailing{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>.
              Players can also reach out through their club administrator. We'll respond within a reasonable time,
              and generally within 30 days.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Complaints</h2>
            <p>
              If you believe we've mishandled your personal information, please contact us first so we can put it
              right. If you're not satisfied with our response, you can lodge a complaint with the Office of the
              Australian Information Commissioner (OAIC) at{' '}
              <a href="https://www.oaic.gov.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }} target="_blank" rel="noopener noreferrer">oaic.gov.au</a>.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Contact</h2>
            <p>
              KlubPro Pty Ltd, trading as BetterSports (ABN 32 624 335 397) · Perth, Western Australia ·{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </div>
  )
}
