import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function Terms() {
  usePageMeta({
    title: 'Terms of Service — Better Cricket',
    description: 'Terms of service for Better Cricket, the cricket platform for Australian clubs, provided by BetterSports.',
    url: 'https://betterat.cricket/terms',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        <h1 className="font-display font-bold text-4xl mb-2">Terms of Service</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: 9 June 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">1. About these terms</h2>
            <p>
              Better Cricket ("the Service", "we", "us", "our") is a cricket platform for Australian clubs,
              provided by BetterSports (ABN 32 624 335 397), a trading name based in Perth, Western Australia.
              These terms govern your club's use of the Service. By creating an account or using the Service,
              your club agrees to these terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">2. The service</h2>
            <p>
              Better Cricket helps your club keep its records, statistics and history online, and run its
              season, back office and match preparation through the modules included in your plan. Some
              information published through the Service, such as club statistics pages, is public by design.
              We may add, change or remove features from time to time as the Service evolves.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">3. Accounts</h2>
            <p>
              Each club is provided with administrator login credentials. You are responsible for keeping your
              credentials confidential, for all activity that takes place under your account, and for ensuring
              that anyone you give access to is authorised to act for your club. Please notify us immediately at{' '}
              <a href="mailto:betteratcricket@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betteratcricket@gmail.com</a>{' '}
              if you believe your account has been accessed without authorisation.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">4. Acceptable use</h2>
            <p>
              You agree to use the Service only for lawful purposes and only for your own club. You must not
              attempt to access another club's data or admin area, interfere with or disrupt the Service, probe
              or test its security, or use it in any way that breaches applicable law or these terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">5. Subscription &amp; payment</h2>
            <p>
              The Service is offered on flat per-club plans: the <strong className="text-pb-text">Core</strong> (BetterStats)
              is $399 per year, and you can add modules (<strong className="text-pb-text">BetterSelect</strong>,{' '}
              <strong className="text-pb-text">BetterSocials</strong> and <strong className="text-pb-text">BetterAdmin</strong> at
              $149 per year each, <strong className="text-pb-text">BetterIQ</strong> at $249), with a discount when you bundle.
              Pricing is per club regardless of how many grades, teams or players you run. The plan you select at
              sign-up, and what it includes, is set out on our{' '}
              <Link to="/pricing" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>pricing page</Link>.
            </p>
            <p className="mt-3">
              Subscriptions are an annual licence, invoiced once a year. Access continues
              for the period you have paid for; we will contact you before each renewal. Fees are payable in
              Australian dollars. Except where required by Australian Consumer Law, fees already paid are
              non-refundable for partial periods.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">6. Your data</h2>
            <p>
              Your club's data remains yours. We process it to provide the Service, and you can export your club's
              data as CSV at any time. The statistics shown in the Service are derived from your club's own match
              data, the records your club produces and maintains. While we work hard to keep everything accurate,
              we don't guarantee that every statistic is complete or error-free, and you remain responsible for the
              accuracy of the data your club provides. We may use de-identified, aggregated information to operate,
              secure and improve the Service.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">7. Availability &amp; support</h2>
            <p>
              We aim to keep the Service available and up to date, and we provide support by email at{' '}
              <a href="mailto:betteratcricket@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betteratcricket@gmail.com</a>.
              We don't guarantee uninterrupted availability, and the Service may occasionally be unavailable for
              maintenance or for reasons outside our control. If we ever decide to discontinue the Service, we will
              give subscribers reasonable notice.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">8. Limitation of liability</h2>
            <p>
              Nothing in these terms excludes, restricts or modifies any rights or remedies you have under the
              Australian Consumer Law or other laws that cannot lawfully be excluded. Subject to that, and to the
              maximum extent permitted by law, the Service is provided "as is", and we are not liable for any
              indirect, incidental, special or consequential loss arising from your use of the Service. Where our
              liability cannot be excluded but can be limited, it is limited to resupplying the Service or paying
              the cost of having it resupplied.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">9. Changes to these terms</h2>
            <p>
              We may update these terms from time to time. If we make a material change, we'll let subscribers know
              by email or through the Service. Continuing to use the Service after a change takes effect means your
              club accepts the updated terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">10. Contact</h2>
            <p>
              Better Cricket is provided by BetterSports (ABN 32 624 335 397), Perth, Western Australia. Questions
              about these terms? Email{' '}
              <a href="mailto:betteratcricket@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betteratcricket@gmail.com</a>.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </div>
  )
}
