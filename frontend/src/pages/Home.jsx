import { Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { thiings } from '../assets/thiings'

export default function Home() {
  const [orgs, setOrgs] = useState([])

  useEffect(() => {
    api.listOrgs().then(setOrgs).catch(() => {})
  }, [])

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-navy-700">
        <div className="absolute inset-0 bg-gradient-to-br from-navy-800 via-navy-900 to-navy-950" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-accent/5 rounded-full blur-3xl" />
        <div className="relative max-w-7xl mx-auto px-4 py-24 md:py-36">
          <div className="max-w-2xl">
            <div className="accent-bar mb-6" />
            <h1 className="display-heading text-5xl md:text-7xl text-white leading-none mb-6">
              YOUR STATS.<br />
              <span className="text-accent">YOUR GAME.</span>
            </h1>
            <p className="text-slate-400 text-lg md:text-xl leading-relaxed mb-8 max-w-xl">
              The cricket statistics platform built for players. Career averages, innings history,
              and live match data — all powered by PlayHQ. No manual exports.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link to="/onboard" className="btn-primary text-base px-6 py-3">
                Add Your Club
              </Link>
              {orgs.length > 0 && (
                <Link
                  to={`/dashboard/${orgs[0].id}`}
                  className="border border-navy-600 hover:border-accent text-white hover:text-accent px-6 py-3 rounded-lg transition-colors text-sm font-semibold"
                >
                  View Dashboard →
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Feature blocks */}
      <section className="max-w-7xl mx-auto px-4 py-20">
        <div className="text-center mb-14">
          <div className="accent-bar mx-auto mb-4" />
          <h2 className="display-heading text-3xl md:text-4xl text-white">
            BUILT FOR CRICKET, BUILT FOR PLAYERS
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              icon: thiings.barChart,
              title: 'Complete Career Stats',
              desc: 'Every innings, every bowling spell, tracked automatically from PlayHQ. Batting average, strike rate, economy — all computed for you.',
            },
            {
              icon: thiings.lightningBolt,
              title: 'Live Match Updates',
              desc: 'PlayHQ webhooks push game updates in real time. Stats refresh automatically after every match — zero manual input.',
            },
            {
              icon: thiings.cricketBat,
              title: 'Player Profiles',
              desc: 'Claim your profile, track your form, share your season highlight. A home page for every cricketer in the club.',
            },
          ].map(({ icon, title, desc }) => (
            <div key={title} className="card p-6">
              <img src={icon} alt="" className="w-12 h-12 object-contain mb-4" />
              <h3 className="display-heading text-xl text-white mb-2">{title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Clubs */}
      {orgs.length > 0 && (
        <section className="border-t border-navy-700 max-w-7xl mx-auto px-4 py-16">
          <h2 className="section-label mb-6">Clubs on BetterStats</h2>
          <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
            {orgs.map(org => (
              <Link
                key={org.id}
                to={`/dashboard/${org.id}`}
                className="card p-5 hover:border-accent/40 transition-colors group"
              >
                <div className="display-heading text-lg text-white group-hover:text-accent transition-colors">
                  {org.name}
                </div>
                {org.short_name && (
                  <div className="text-xs text-slate-500 mt-1 font-mono">{org.short_name}</div>
                )}
                <div className="text-accent text-xs mt-3 font-semibold">View stats →</div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="border-t border-navy-700 bg-navy-800/50">
        <div className="max-w-7xl mx-auto px-4 py-16 text-center">
          <h2 className="display-heading text-3xl text-white mb-4">READY TO GET YOUR STATS?</h2>
          <p className="text-slate-400 mb-8">Add your club's PlayHQ Organisation ID and we'll pull everything automatically.</p>
          <Link to="/onboard" className="btn-primary text-base px-8 py-3">
            Get Started — It's Free
          </Link>
        </div>
      </section>
    </div>
  )
}
