import MarketingNav from '../../components/MarketingNav'

export default function Terms() {
  return (
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="inline-block bg-amber-cricket/10 border border-amber-cricket/30 text-amber-cricket text-xs px-3 py-1 rounded-full mb-6">
          Draft — review before launch
        </div>
        <h1 className="font-display font-bold text-4xl mb-2">Terms of Service</h1>
        <p className="text-slate-500 text-sm mb-10">Last updated: May 2026</p>

        <div className="space-y-8 text-slate-300 leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">1. Service description</h2>
            <p>BetterStats ("the Service") is a cricket statistics platform provided by KlubPro (ABN pending) to registered cricket clubs in Australia. The Service displays publicly available cricket statistics sourced from PlayHQ.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">2. Account terms</h2>
            <p>Each club is provided with administrator login credentials. You are responsible for maintaining the confidentiality of your credentials. You must notify us immediately of any unauthorised use of your account.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">3. Payment</h2>
            <p>The annual subscription fee is $250 AUD per club. Access continues until the subscription lapses. We will contact you prior to renewal. No refunds are provided for partial years.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">4. Data</h2>
            <p>Statistics displayed on BetterStats are sourced from PlayHQ's public data feed. We do not guarantee the accuracy of statistics. You retain ownership of any custom content you add (awards, descriptions, etc.). We may use aggregated, anonymised data to improve the Service.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">5. Acceptable use</h2>
            <p>You agree not to use the Service for any unlawful purpose, to attempt to gain unauthorised access to other clubs' data, or to interfere with the Service's operation.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">6. Service availability</h2>
            <p>We aim to keep BetterStats available and up to date, but we do not guarantee uninterrupted availability. The Service may be temporarily unavailable for maintenance. We reserve the right to discontinue the Service with 30 days' notice.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">7. Limitation of liability</h2>
            <p>To the maximum extent permitted by Australian law, we are not liable for any indirect, incidental, or consequential damages arising from your use of the Service.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">8. Changes to terms</h2>
            <p>We may update these terms from time to time. We will notify subscribers via email. Continued use of the Service after changes constitutes acceptance of the new terms.</p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-white mb-3">9. Contact</h2>
            <p>Questions about these terms: <a href="mailto:jack@klubpro.com" className="text-accent hover:underline">jack@klubpro.com</a></p>
          </section>
        </div>
      </div>
    </div>
  )
}
