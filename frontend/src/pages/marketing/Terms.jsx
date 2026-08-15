import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function Terms() {
  usePageMeta({
    title: 'Terms of Service — BetterCricket',
    description: 'Terms of service for BetterCricket, the cricket platform for Australian clubs, provided by BetterSports.',
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
              BetterCricket ("the Service", "we", "us", "our") is a software platform for cricket clubs,
              provided by BetterSports, which is a Registered Business Name of KlubPro Pty Limited
              (ABN 32 624 335 397), based in Perth, Western Australia. These terms govern your club's use of the
              Service. By creating an account or using the Service, your club agrees to these terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">2. The service</h2>
            <p>
              BetterCricket helps your club keep its records, statistics and history online, and run its
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
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>{' '}
              if you believe your account has been accessed without authorisation.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">4. Acceptable use</h2>
            <p>
              You agree to use the Service only for lawful purposes and only for your own club. You must not
              attempt to register a club which you have no authorised responsibility for or association with.
              You must not attempt to access another club's data or admin area, interfere with or disrupt the
              Service, probe or test its security, or use it in any way that breaches applicable law or these
              terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">5. Email and BetterComms</h2>
            <p>
              BetterComms lets your club email its players and members. You may email only your own members and
              associates, or people who have asked to hear from you. You must not use bought, scraped or shared
              lists. Every email includes a one-click unsubscribe. Every email you send using BetterComms must
              clearly identify your club, as the Spam Act 2003 requires. BetterCricket honours unsubscribes
              across your club automatically.
            </p>
            <p className="mt-3">
              All BetterComms email goes out through a shared email service, so we set sending limits to keep it
              healthy for everyone. A new club starts with a small daily limit and can ask us to raise that limit
              once its sending looks clean. We may pace, cap or pause sending to protect the service, and we may
              suspend a club whose emails bounce or get marked as spam too often, until the problem is fixed.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">6. Subscription &amp; payment</h2>
            <p>
              The Service is offered on flat per-club annual plans: the <strong className="text-pb-text">Core</strong> (BetterStats)
              is a mandatory module, and you can add other modules (e.g. <strong className="text-pb-text">BetterSelect</strong>,{' '}
              <strong className="text-pb-text">BetterSocials</strong> and <strong className="text-pb-text">BetterClubhouse</strong>).
              We may offer a bundle discount for your first year when you select multiple modules in addition to
              BetterStats on your first subscription. Pricing is per club regardless of how many grades, teams or
              players you run. The plan you select at sign-up, and what it includes, is set out on our{' '}
              <Link to="/pricing" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>pricing page</Link>.
            </p>
            <p className="mt-3">
              Subscriptions are an annual licence, invoiced once a year. Access continues for the period you have
              paid for; we will notify you when a module's trial is expiring and when a module's subscription is
              about to renew. The fee for an additional module subscribed to during the BetterStats subscription
              period will be prorated to the renewal date of the BetterStats subscription. Subscription fees are
              payable in advance. Except where required by Australian Consumer Law, fees already paid are
              non-refundable for partial periods.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">7. Your data</h2>
            <p>
              Your club's data remains yours. We process it to provide the Service, and you can export your club's
              data as CSV at any time. The statistics shown in the Service are derived from your club's own match
              data, the records your club produces and maintains. While we work hard to keep everything accurate,
              we don't guarantee that every statistic is complete or error-free, and you remain responsible for the
              accuracy of the data your club provides. We may use de-identified, aggregated information to operate,
              analyse, secure and improve the Service.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">8. Availability &amp; support</h2>
            <p>
              We aim to keep the Service available and up to date, and we provide support by email at{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>.
              We don't guarantee uninterrupted availability, and the Service may occasionally be unavailable for
              maintenance or for reasons outside our control. If we ever decide to discontinue the Service, we will
              give subscribers reasonable notice.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">9. Limitation of liability</h2>
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
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">10. Changes to these terms</h2>
            <p>
              We may update these terms from time to time. If we make a material change, we may inform
              subscribers by email or through the Service. Continuing to use the Service after a change takes
              effect means your club accepts the updated terms.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">11. Contact</h2>
            <p>
              BetterCricket is provided by KlubPro Pty Ltd, trading as BetterSports (ABN 32 624 335 397), Perth,
              Western Australia. Questions about these terms? Email{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </div>
  )
}
