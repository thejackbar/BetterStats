import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'

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

      <div className="max-w-2xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Contact</p>
        <h1 className="font-display font-bold text-[40px] md:text-[56px] leading-none tracking-tight mb-6">
          GET IN<br />
          <span style={{ color: 'var(--pb-accent)' }}>TOUCH.</span>
        </h1>
        <p className="text-pb-dim text-lg mb-10">
          Whether you want to request access for your club, ask a question, or just have a chat — we'd love to hear from you.
        </p>

        <div className="space-y-4">
          <div className="pb-card p-6">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Request access</p>
            <p className="text-pb-dim text-sm mb-4">
              Fill out the form below and we'll be in touch to get your club set up.
            </p>
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              OPEN REQUEST FORM ↗
            </a>
          </div>

          <div className="pb-card p-6">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Email directly</p>
            <p className="text-pb-dim text-sm mb-3">For anything else, drop a line to:</p>
            <a href="mailto:betterstatsau@gmail.com" className="font-mono text-sm hover:underline" style={{ color: 'var(--pb-accent)' }}>
              betterstatsau@gmail.com
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
