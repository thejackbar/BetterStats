import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import { usePageMeta } from '../../hooks/usePageMeta'

const MAIL = 'support@bettersports.com.au'
const linkStyle = { color: 'var(--pb-accent)' }
const H2 = 'font-display font-bold text-xl text-pb-text mb-3'
const B = 'text-pb-text'

function Mail() {
  return <a href={`mailto:${MAIL}`} className="hover:underline" style={linkStyle}>{MAIL}</a>
}

export default function Privacy() {
  usePageMeta({
    title: 'Privacy Policy — BetterCricket',
    description: 'How BetterCricket, provided by BetterSports, collects, stores and handles club, player and account information, and how to ask for your details to be hidden.',
    url: 'https://betterat.cricket/privacy',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        <h1 className="font-display font-bold text-4xl mb-2">Privacy Policy</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: October 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          <section>
            <h2 className={H2}>Who we are</h2>
            <p>
              BetterCricket is provided by BetterSports (ABN 32 624 335 397), a Registered Business Name of
              KlubPro Pty Ltd, in Perth, Western Australia. This policy explains how we collect, use, store and
              handle personal information in the BetterCricket service and websites.
            </p>
          </section>

          <section>
            <h2 className={H2}>What we collect</h2>
            <ul className="space-y-2 ml-4 list-disc">
              <li><strong className={B}>Club and player information:</strong> Player names, match scorecards, cricket statistics, grades, seasons and teams, and identifiers that link a person's records together. We also hold club details such as name, contact email and branding preferences.</li>
              <li><strong className={B}>Information clubs add about their people:</strong> Depending on the BetterCricket modules a club uses, a club may record things like contact details, date of birth, availability, selection and fee records. The club decides what it records and why, and we hold it on the club's behalf. If you want to know what a club holds about you, please ask the club.</li>
              <li><strong className={B}>Email records:</strong> When a club sends email through BetterCricket, we keep the delivery results and a list of people who have unsubscribed or asked not to be emailed, so we don't contact them again.</li>
              <li><strong className={B}>Admin account information:</strong> The email address, mobile number, username and password used to sign in to a club's admin area. Passwords are stored only as a secure hash, never in plain text.</li>
              <li><strong className={B}>Usage and analytics data:</strong> Standard web logs and analytics such as IP address, device and browser details, and the pages viewed, used to keep the Service secure and to understand and improve how it's used.</li>
            </ul>
          </section>

          <section>
            <h2 className={H2}>How we use information</h2>
            <p>
              We use the information we collect to provide and operate the Service: to display statistics on
              public club pages, give administrators access to their club's admin area, run the BetterCricket
              modules included in a club's plan, keep the Service secure, respond to support requests, and
              improve how everything works. We don't use your information for unrelated purposes without telling you.
            </p>
          </section>

          <section>
            <h2 className={H2}>Where our information comes from</h2>
            <ul className="space-y-2 ml-4 list-disc">
              <li><strong className={B}>Published match records.</strong> We collect match records for a club's competitions, such as scorecards, results and statistics, from published match data, and we keep them up to date.</li>
              <li><strong className={B}>The club.</strong> Clubs can import records from their own sources, such as scorebooks, spreadsheets and previous systems, and can type in games and corrections by hand. Where a club does that, the club is the source.</li>
              <li><strong className={B}>You.</strong> If you have a BetterCricket admin account, the details you give us when you sign up and sign in.</li>
            </ul>
            <p className="mt-3">
              We are not the source of the underlying match data, and we don't guarantee that every figure is
              complete or error-free. If something looks wrong, your club administrator can correct or update it.
              Some junior players' names are already hidden in the published records, and we treat those names the
              same way. Clubs can also choose to hide any player from public pages.
            </p>
          </section>

          <section>
            <h2 className={H2}>Matching records to a person</h2>
            <p>
              We keep identifiers with each profile so that the same person's games, seasons and clubs are matched
              to one person, so that new records are added to the right profile instead of creating a duplicate,
              and so that a person who has asked to be hidden stays hidden.
            </p>
          </section>

          <section>
            <h2 className={H2}>Public club and player pages</h2>
            <p>
              Club statistics pages and player profiles are public by design. You don't need to sign in to see one.
              They show player names and performance statistics so that clubs and their communities can follow and
              celebrate their past and present members. A player's name can also appear in match scorecards,
              ladders, records, awards and yearbooks.
            </p>
            <p className="mt-3">Profiles of people who have asked to be hidden return “not found”.</p>
            <p className="mt-3">
              If you would prefer not to appear, you can ask us or the club to hide your details. See the next section.
            </p>
          </section>

          <section>
            <h2 className={H2}>Asking us to hide or remove your details</h2>
            <p>
              You can ask the club or ask us to take your profile and name off the public site by emailing <Mail />.
              Tell us your name and the club or clubs you play for, or send the address of your profile. A parent or
              guardian can ask on behalf of a child. Once we have confirmed who you are, we will:
            </p>
            <ul className="space-y-2 ml-4 list-disc mt-3">
              <li>Hide your profile at every club that holds a record for you, and take you out of public search, leaderboards, records and share images.</li>
              <li>Replace your name with ******** on public scorecards, dismissal lines, awards and other public pages, wherever we can recognise it.</li>
              <li>Stop emails from BetterCricket reaching your address (if your email is held by the club), including club newsletters, fee notices and selection emails.</li>
              <li>Stop a club from switching your profile back on, and stop it being created again when records are updated.</li>
            </ul>
            <p className="mt-3">We then confirm by email what we have done.</p>
            <p className="mt-3">
              To stop a profile coming back, we keep your name and identifiers, hidden from public view. We keep it
              for as long as the club's records need it and for that purpose only.
            </p>
            <p className="mt-3">There are limits you should know about:</p>
            <ul className="space-y-2 ml-4 list-disc mt-3">
              <li>We keep the match results themselves. Other players' scores, partnerships and ladders depend on them, and the club needs its own records to run the club.</li>
              <li>We don't control other websites and apps that publish the same match records, search engine caches, web archives, or screenshots and posts other people have already made. Those need to be taken up with whoever runs them.</li>
            </ul>
          </section>

          <section>
            <h2 className={H2}>Storage and security</h2>
            <p>
              We take reasonable steps to protect personal information from loss, misuse and unauthorised access.
              Data is transmitted over encrypted connections (HTTPS), account passwords are stored as secure
              hashes, and access to club admin areas is restricted to authorised users. No system can be
              guaranteed completely secure, but we work to keep your information safe.
            </p>
          </section>

          <section>
            <h2 className={H2}>Who we share information with</h2>
            <p>
              We do not sell personal information. We share information with service providers who help us run the
              Service, such as hosting and email delivery, and only as needed for them to do so, or where we're
              required to by law.
            </p>
          </section>

          <section>
            <h2 className={H2}>Access and correction</h2>
            <p>
              You can ask to see the personal information we hold about you or to have it corrected, by emailing <Mail />.
              Players can also reach out through their club administrator. We'll respond within a reasonable time,
              and generally within 30 days.
            </p>
          </section>

          <section>
            <h2 className={H2}>Changes to this policy</h2>
            <p>We update this policy from time to time. The date at the top shows when it last changed.</p>
          </section>

          <section>
            <h2 className={H2}>Contact</h2>
            <p>
              For questions about this policy, and requests about your information, please contact <Mail />.
            </p>
            <p className="mt-3">
              KlubPro Pty Ltd, trading as BetterSports (ABN 32 624 335 397) · Perth, Western Australia ·{' '}
              <Mail />
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </div>
  )
}
