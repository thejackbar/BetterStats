import MarketingNav from '../../components/MarketingNav'

export default function Privacy() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="inline-block bg-pb-amber/10 border border-pb-amber/30 text-pb-amber font-mono text-[10px] px-3 py-1 rounded-full mb-6">
          Draft — review before launch
        </div>
        <h1 className="font-display font-bold text-4xl mb-2">Privacy Policy</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: May 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Overview</h2>
            <p>This policy explains how BetterStats (operated by KlubPro) collects, uses, and handles information in accordance with the Australian Privacy Act 1988 and the Australian Privacy Principles (APPs).</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">What information we collect</h2>
            <ul className="space-y-2 ml-4">
              <li><strong className="text-pb-text">Cricket statistics:</strong> Player names and performance statistics sourced from publicly available cricket data.</li>
              <li><strong className="text-pb-text">Admin credentials:</strong> Username and hashed password for club administrator accounts. We never store passwords in plain text.</li>
              <li><strong className="text-pb-text">Club information:</strong> Club name, contact email address, and branding preferences provided by club administrators.</li>
              <li><strong className="text-pb-text">Usage data:</strong> Standard web server logs (IP addresses, page views) for security and performance monitoring.</li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">How we use information</h2>
            <p>We use the information we collect to: display statistics on public club pages, provide admin access to club administrators, improve the Service, and respond to support requests. We do not sell or share personal information with third parties for marketing purposes.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Data storage</h2>
            <p>All data is stored on servers located in Australia. We use industry-standard security measures including encrypted connections (HTTPS) and password hashing.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Public statistics</h2>
            <p>Player names and statistics are displayed publicly on club pages. This mirrors data already publicly available. If a player wishes to have their statistics removed, they should contact their club administrator or us directly.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Access and correction</h2>
            <p>You may request access to or correction of any personal information we hold about you by contacting <a href="mailto:betterstatsau@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betterstatsau@gmail.com</a>. We will respond within 30 days.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Complaints</h2>
            <p>If you believe your privacy has been breached, please contact us. If you are unsatisfied with our response, you may lodge a complaint with the Office of the Australian Information Commissioner (OAIC) at <a href="https://www.oaic.gov.au" className="hover:underline" style={{ color: 'var(--pb-accent)' }} target="_blank" rel="noopener noreferrer">oaic.gov.au</a>.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">Contact</h2>
            <p><a href="mailto:betterstatsau@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betterstatsau@gmail.com</a></p>
          </section>
        </div>
      </div>
    </div>
  )
}
