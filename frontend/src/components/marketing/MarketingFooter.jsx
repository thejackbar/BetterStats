import { Link } from 'react-router-dom'
import BrandLogo from '../BrandLogo'
import { MODULES_MARKETING } from '../../data/modules-marketing'

export default function MarketingFooter() {
  return (
    <footer className="border-t pb-hairline bg-pb-bg">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="grid grid-cols-2 md:grid-cols-12 gap-8 mb-12">
          <div className="col-span-2 md:col-span-4">
            <Link to="/" className="flex items-center gap-2.5 mb-5" aria-label="BetterCricket home">
              <BrandLogo className="w-7 h-7 object-contain" />
              <span className="font-bold text-lg tracking-tight">
                Better<span className="text-accent">Cricket</span>
              </span>
            </Link>
            <p className="text-pb-dim text-sm leading-relaxed max-w-sm mb-6">
              Everything an Australian cricket club runs on, in one place: stats and history, weekend selection, social posts, the back office and match prep.
            </p>
            <div className="flex gap-4 text-sm text-pb-dim">
              <a href="https://x.com/betterstatsau" target="_blank" rel="noopener noreferrer me" className="hover:text-pb-text transition-colors">Twitter</a>
              <a href="https://www.facebook.com/profile.php?id=61590372751599" target="_blank" rel="noopener noreferrer me" className="hover:text-pb-text transition-colors">Facebook</a>
              <a href="mailto:support@bettersports.com.au" className="hover:text-pb-text transition-colors">Email</a>
            </div>
          </div>

          <div className="col-span-1 md:col-span-2">
            <p className="text-sm font-semibold mb-4">Modules</p>
            <ul className="space-y-2.5">
              <li><Link to="/modules" className="text-sm text-pb-dim hover:text-pb-text">Overview</Link></li>
              {MODULES_MARKETING.map((m) => (
                <li key={m.slug}><Link to={`/modules/${m.slug}`} className="text-sm text-pb-dim hover:text-pb-text">{m.name}</Link></li>
              ))}
            </ul>
          </div>

          <div className="col-span-1 md:col-span-2">
            <p className="text-sm font-semibold mb-4">Product</p>
            <ul className="space-y-2.5">
              <li><Link to="/features" className="text-sm text-pb-dim hover:text-pb-text">Core (BetterStats)</Link></li>
              <li><Link to="/pricing" className="text-sm text-pb-dim hover:text-pb-text">Pricing</Link></li>
              <li><Link to="/compare" className="text-sm text-pb-dim hover:text-pb-text">Compare</Link></li>
              <li><Link to="/blog" className="text-sm text-pb-dim hover:text-pb-text">Blog</Link></li>
            </ul>
          </div>

          <div className="col-span-1 md:col-span-2">
            <p className="text-sm font-semibold mb-4">Company</p>
            <ul className="space-y-2.5">
              <li><Link to="/about" className="text-sm text-pb-dim hover:text-pb-text">About</Link></li>
              <li><Link to="/contact" className="text-sm text-pb-dim hover:text-pb-text">Contact</Link></li>
              <li><Link to="/faq" className="text-sm text-pb-dim hover:text-pb-text">FAQ</Link></li>
              <li><Link to="/login" className="text-sm text-pb-dim hover:text-pb-text">Admin Login</Link></li>
            </ul>
          </div>

          <div className="col-span-1 md:col-span-2">
            <p className="text-sm font-semibold mb-4">Australian cricket</p>
            <p className="text-sm text-pb-dim mb-3 leading-relaxed">
              BetterCricket keeps your club's full history online and updates it automatically after every match. You don't keep spreadsheets or enter stats by hand.
            </p>
            <Link to="/about" className="text-sm text-accent hover:underline">Read our story →</Link>
          </div>
        </div>

        <div className="border-t pb-hairline pt-8 flex flex-col md:flex-row md:items-center justify-between gap-3 text-sm text-pb-faint">
          <p>© {new Date().getFullYear()} BetterCricket · A BetterSports product · ABN 32 624 335 397 · Perth, WA</p>
          <div className="flex flex-wrap gap-6">
            <Link to="/terms" className="hover:text-pb-text">Terms</Link>
            <Link to="/privacy" className="hover:text-pb-text">Privacy</Link>
            <span><span className="text-accent">●</span> all systems normal</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
