import MarketingNav from '../../components/MarketingNav'

export default function Terms() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="inline-block bg-pb-amber/10 border border-pb-amber/30 text-pb-amber font-mono text-[10px] px-3 py-1 rounded-full mb-6">
          Draft — review before launch
        </div>
        <h1 className="font-display font-bold text-4xl mb-2">Terms of Service</h1>
        <p className="font-mono text-[10px] text-pb-faint mb-10">Last updated: May 2026</p>

        <div className="space-y-8 text-pb-dim leading-relaxed">
          {[
            {
              title: '1. Service description',
              body: 'BetterStats ("the Service") is a cricket statistics platform provided by KlubPro (ABN pending) to registered cricket clubs in Australia. The Service displays publicly available cricket statistics sourced from public cricket data.',
            },
            {
              title: '2. Account terms',
              body: 'Each club is provided with administrator login credentials. You are responsible for maintaining the confidentiality of your credentials. You must notify us immediately of any unauthorised use of your account.',
            },
            {
              title: '3. Payment',
              body: 'The annual subscription fee is $250 AUD per club. Access continues until the subscription lapses. We will contact you prior to renewal. No refunds are provided for partial years.',
            },
            {
              title: '4. Data',
              body: 'Statistics displayed on BetterStats are sourced from public cricket data feeds. We do not guarantee the accuracy of statistics. You retain ownership of any custom content you add (awards, descriptions, etc.). We may use aggregated, anonymised data to improve the Service.',
            },
            {
              title: '5. Acceptable use',
              body: 'You agree not to use the Service for any unlawful purpose, to attempt to gain unauthorised access to other clubs\' data, or to interfere with the Service\'s operation.',
            },
            {
              title: '6. Service availability',
              body: 'We aim to keep BetterStats available and up to date, but we do not guarantee uninterrupted availability. The Service may be temporarily unavailable for maintenance. We reserve the right to discontinue the Service with 30 days\' notice.',
            },
            {
              title: '7. Limitation of liability',
              body: 'To the maximum extent permitted by Australian law, we are not liable for any indirect, incidental, or consequential damages arising from your use of the Service.',
            },
            {
              title: '8. Changes to terms',
              body: 'We may update these terms from time to time. We will notify subscribers via email. Continued use of the Service after changes constitutes acceptance of the new terms.',
            },
          ].map(({ title, body }) => (
            <section key={title}>
              <h2 className="font-display font-bold text-xl text-pb-text mb-3">{title}</h2>
              <p>{body}</p>
            </section>
          ))}
          <section>
            <h2 className="font-display font-bold text-xl text-pb-text mb-3">9. Contact</h2>
            <p>Questions about these terms: <a href="mailto:betterstatsau@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betterstatsau@gmail.com</a></p>
          </section>
        </div>
      </div>
    </div>
  )
}
