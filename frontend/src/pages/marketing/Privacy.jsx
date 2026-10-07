import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function Privacy() {
  usePageMeta({
    title: 'Privacy Policy — BetterCricket',
    description: 'How BetterCricket, provided by BetterSports, collects, stores and handles club, player and account information, and how to ask for your details to be hidden or removed.',
    url: 'https://betterat.cricket/privacy',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        <h1 className="font-display font-bold text-4xl mb-2">Privacy Policy</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: 7 October 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Who we are</h2>
            <p>
              BetterCricket is provided by BetterSports (ABN 32 624 335 397), a Registered Business Name of
              KlubPro Pty Ltd, in Perth, Western Australia. This policy explains how we collect, use, store and
              handle personal information in the BetterCricket service and websites.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">What we collect</h2>
            <ul className="space-y-2 ml-4 list-disc">
              <li><strong className="text-pb-text">Club and player information:</strong> Player names and cricket statistics taken from match records (see "Where match data comes from" below), along with club details such as name, contact email and branding preferences.</li>
              <li><strong className="text-pb-text">Information clubs add about their people:</strong> Depending on the modules a club uses, a club may record things like contact details, photos, date of birth, availability, selection and fee records. The club decides what it records and why, and we hold it on the club's behalf. If you want to know what a club holds about you, ask the club first.</li>
              <li><strong className="text-pb-text">Email records:</strong> When a club sends email through BetterCricket, we keep the delivery results and a list of people who have unsubscribed or asked not to be emailed, so we don't contact them again.</li>
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
              The statistics in BetterCricket come from match records: the scorecards Cricket Australia publishes
              for a club's competitions, and anything a club imports or types in itself, such as scorebook
              records. We are not the source of that underlying data, and we don't guarantee that every figure is
              complete or error-free. If something looks wrong, your club administrator can correct or update it.
            </p>
            <p className="mt-3">
              Cricket Australia hides the names of some junior players in its own scorecards, and we treat those
              names the same way. Clubs can also choose to hide their junior players from public pages.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Public club pages</h2>
            <p>
              Club statistics pages are public by design. Player names and their performance statistics are shown
              on these pages so that clubs and their communities can follow and celebrate their cricket. A player's
              name can also appear in match scorecards, ladders, records, awards, yearbooks and the share images
              built from them, and a player's photo appears if the club has added one.
            </p>
            <p className="mt-3">
              Clubs that use BetterIQ can also look at opposition players in their private admin area, using the
              same published match data.
            </p>
            <p className="mt-3">
              If you would prefer not to appear, you can ask us to hide your details. See the next section.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Asking us to hide or remove your details</h2>
            <p>
              You can ask us to take your profile, photos and name off the public site by emailing{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>.
              Tell us your name and the club or clubs you play for. A parent or guardian can ask on behalf of a
              child. Once we have confirmed who you are, we will:
            </p>
            <ul className="space-y-2 ml-4 list-disc mt-3">
              <li>Hide your profile at every club that holds a record for you, and take you out of public search, leaderboards, records, the sitemap and share images.</li>
              <li>Delete your photos, including any copy held for opposition analysis in BetterIQ. Photos are not restored if the request is later withdrawn.</li>
              <li>Replace your name with ******** on public scorecards, dismissal lines, awards and other public pages, wherever we can recognise it.</li>
              <li>Stop emails from BetterCricket reaching your address, including club newsletters, fee notices and selection emails.</li>
              <li>Stop a club from switching your profile back on, and stop it being created again the next time match data is updated. To do that we keep a short record that you asked, when you asked, and the identifiers and email addresses we need to recognise you. We keep it for that purpose only.</li>
            </ul>
            <p className="mt-3">There are limits you should know about:</p>
            <ul className="space-y-2 ml-4 list-disc mt-3">
              <li>We keep the match results themselves. Other players' scores, partnerships and ladders depend on them, and the club needs its own records to run the club. Your club's administrators can still see you in their private admin area.</li>
              <li>We can only hide a name we can recognise. A nickname nobody recorded, a misspelling, or text inside an image or PDF may be missed. Where a relative with the same surname and initial also played, we leave an unclear line alone rather than hide the wrong person.</li>
              <li>We don't control Cricket Australia's own site or app, search engine caches, web archives or screenshots and posts other people have already made. Those need to be taken up with whoever runs them.</li>
            </ul>
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
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Access and correction</h2>
            <p>
              You can ask to see the personal information we hold about you, or to have it corrected, by
              emailing{' '}
              <a href="mailto:support@bettersports.com.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>support@bettersports.com.au</a>.
              Players can also reach out through their club administrator. We'll respond within a reasonable time,
              and generally within 30 days.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Changes to this policy</h2>
            <p>
              We update this policy from time to time. The date at the top shows when it last changed.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Contact</h2>
            <p>
              Questions about this policy, and requests about your information, go to us at the address below.
              <br />
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
