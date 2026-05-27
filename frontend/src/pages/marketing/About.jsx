import MarketingNav from '../../components/MarketingNav'
import { Link } from 'react-router-dom'
import { usePageMeta } from '../../hooks/usePageMeta'

export default function About() {
  usePageMeta({
    title: 'About — BetterStats Cricket Stats Platform',
    description: 'BetterStats was built by a club cricketer at Applecross Cricket Club in Perth, Western Australia, who was tired of maintaining stats in spreadsheets. Now offered to any Australian cricket club.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/about',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">About</p>
        <h1 className="font-display font-bold text-[40px] md:text-[56px] leading-none tracking-tight mb-10">
          ABOUT<br />
          <span style={{ color: 'var(--pb-accent)' }}>BETTERSTATS.</span>
        </h1>

        <div className="space-y-6 text-pb-dim leading-relaxed">
          <p>
            BetterStats started as an internal stats platform for Applecross Cricket Club in Perth, Western Australia. Built by a club member who was tired of manually updating spreadsheets after every game, it's now being made available to other clubs who want the same thing.
          </p>

          <p>
            Australian cricket clubs are full of people who care deeply about the history and records of their club — who hit the first century, who took the most wickets in a season, who's closing in on 100 games. BetterStats makes that information beautiful, accessible, and automatic.
          </p>

          <p>
            Once your club is set up, stats come through automatically after every match — no data entry, no spreadsheets, no chasing scorers. Your full history going back decades is pulled in on first sync, and everything stays up to date from there.
          </p>

          <div className="pb-hairline-t pt-8">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-4">Get in touch</p>
            <p>
              Have a question or want to know if BetterStats is right for your club? Reach out at{' '}
              <a href="mailto:betterstatsau@gmail.com" className="hover:underline" style={{ color: 'var(--pb-accent)' }}>betterstatsau@gmail.com</a>
              {' '}— happy to chat.
            </p>
          </div>
        </div>

        <div className="mt-12 flex gap-4">
          <Link to="/features" className="border pb-hairline text-pb-faint hover:text-pb-text px-4 py-2 rounded font-mono text-[10px] tracking-wide2 transition-colors">Features</Link>
          <Link to="/pricing" className="border pb-hairline text-pb-faint hover:text-pb-text px-4 py-2 rounded font-mono text-[10px] tracking-wide2 transition-colors">Pricing</Link>
          <Link to="/contact" className="border pb-hairline text-pb-faint hover:text-pb-text px-4 py-2 rounded font-mono text-[10px] tracking-wide2 transition-colors">Get in touch</Link>
        </div>
      </div>
    </div>
  )
}
