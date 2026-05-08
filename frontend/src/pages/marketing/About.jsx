import MarketingNav from '../../components/MarketingNav'
import { Link } from 'react-router-dom'

export default function About() {
  return (
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      <div className="max-w-3xl mx-auto px-4 py-16">
        <h1 className="font-display font-bold text-4xl md:text-5xl mb-8">About BetterStats</h1>

        <div className="prose prose-invert max-w-none space-y-6 text-slate-300 leading-relaxed">
          <p>
            BetterStats started as an internal stats platform for Applecross Cricket Club in Perth, Western Australia. Built by a club member who was tired of manually updating spreadsheets after every game, it's now being made available to other clubs who want the same thing.
          </p>

          <p>
            Australian cricket clubs are full of people who care deeply about the history and records of their club — who hit the first century, who took the most wickets in a season, who's closing in on 100 games. BetterStats makes that information beautiful, accessible, and automatic.
          </p>

          <p>
            The platform plugs directly into PlayHQ, the national cricket management platform. If your club registers on PlayHQ, your stats come through automatically after every match — no data entry, no spreadsheets.
          </p>

          <h2 className="font-display font-bold text-2xl text-white mt-10">Built by</h2>
          <p>
            Jack, a software developer and cricket club member based in Perth. Get in touch at{' '}
            <a href="mailto:jack@klubpro.com" className="text-accent hover:underline">jack@klubpro.com</a>
            {' '}— happy to chat about whether BetterStats is a good fit for your club.
          </p>
        </div>

        <div className="mt-12 flex gap-4">
          <Link to="/features" className="btn-ghost text-slate-300">Features</Link>
          <Link to="/pricing" className="btn-ghost text-slate-300">Pricing</Link>
          <Link to="/contact" className="btn-ghost text-slate-300">Get in touch</Link>
        </div>
      </div>
    </div>
  )
}
