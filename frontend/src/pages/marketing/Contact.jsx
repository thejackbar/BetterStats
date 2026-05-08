import MarketingNav from '../../components/MarketingNav'

export default function Contact() {
  return (
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      <div className="max-w-2xl mx-auto px-4 py-16">
        <h1 className="font-display font-bold text-4xl md:text-5xl mb-4">Get in touch</h1>
        <p className="text-slate-300 text-lg mb-10">
          Whether you want to request access for your club, ask a question, or just have a chat — we'd love to hear from you.
        </p>

        <div className="space-y-6">
          <div className="bg-navy-900 border border-navy-700 rounded-lg p-6">
            <h2 className="font-medium text-white mb-2">Request access for your club</h2>
            <p className="text-slate-400 text-sm mb-4">
              Fill out the form below and we'll be in touch to get your club set up.
            </p>
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSdTODO/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary text-sm"
            >
              Open request form ↗
            </a>
          </div>

          <div className="bg-navy-900 border border-navy-700 rounded-lg p-6">
            <h2 className="font-medium text-white mb-2">Email directly</h2>
            <p className="text-slate-400 text-sm mb-3">
              For anything else, drop a line to:
            </p>
            <a href="mailto:jack@klubpro.com" className="text-accent hover:underline font-mono">
              jack@klubpro.com
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
