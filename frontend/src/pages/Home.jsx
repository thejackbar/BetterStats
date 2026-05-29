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
    <div className="min-h-screen bg-pb-bg text-pb-text">
      {/* Hero */}
      <section className="relative overflow-hidden pb-hairline-b">
        <div className="relative max-w-5xl mx-auto px-4 py-24 md:py-36">
          <div className="max-w-2xl">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-6 uppercase">Built for Australian cricket clubs</p>
            <h1 className="font-display font-bold text-[56px] md:text-[88px] text-pb-text leading-none mb-6 tracking-tight">
              YOUR STATS.<br />
              <span style={{ color: 'var(--pb-accent)' }}>YOUR GAME.</span>
            </h1>
            <p className="text-pb-dim text-lg md:text-xl leading-relaxed mb-8 max-w-xl">
              The cricket statistics platform built for players. Career averages, innings history,
              and live match data — all powered by PlayHQ. No manual exports.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                to="/onboard"
                className="px-6 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                ADD YOUR CLUB
              </Link>
              {orgs.length > 0 && (
                <Link
                  to={`/${orgs[0].slug}`}
                  className="border pb-hairline text-pb-dim hover:text-pb-text px-6 py-3 rounded font-mono text-[11px] tracking-wide2 font-semibold transition-colors"
                >
                  VIEW DASHBOARD →
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Feature blocks */}
      <section className="max-w-5xl mx-auto px-4 py-20">
        <div className="text-center mb-14">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4">WHY BETTERSTATS?</p>
          <h2 className="font-display font-bold text-[32px] md:text-[44px] text-pb-text tracking-tight">
            BUILT FOR CRICKET, BUILT FOR PLAYERS
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-5">
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
            <div key={title} className="pb-card p-6">
              <img src={icon} alt="" className="w-10 h-10 object-contain mb-4" />
              <p className="font-mono text-[10px] tracking-wide3 mb-2" style={{ color: 'var(--pb-accent)' }}>{title.toUpperCase()}</p>
              <p className="text-pb-dim text-sm leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Clubs */}
      {orgs.length > 0 && (
        <section className="pb-hairline-t max-w-5xl mx-auto px-4 py-16">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-6 uppercase">Clubs on BetterStats</p>
          <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
            {orgs.map(org => (
              <Link
                key={org.id}
                to={`/${org.slug}`}
                className="pb-card p-5 hover:bg-pb-surface2 transition-colors group"
              >
                <div className="font-display font-bold text-lg text-pb-text group-hover:text-pb-accent transition-colors">
                  {org.name}
                </div>
                {org.short_name && (
                  <div className="font-mono text-[10px] text-pb-faintest mt-1">{org.short_name}</div>
                )}
                <div className="font-mono text-[10px] tracking-wide2 mt-3" style={{ color: 'var(--pb-accent)' }}>View stats →</div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="pb-hairline-t">
        <div className="max-w-5xl mx-auto px-4 py-16 text-center">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4">GET STARTED</p>
          <h2 className="font-display font-bold text-3xl text-pb-text mb-4 tracking-tight">READY TO GET YOUR STATS?</h2>
          <p className="text-pb-faint mb-8">Add your club's PlayHQ Organisation ID and we'll pull everything automatically.</p>
          <Link
            to="/onboard"
            className="inline-block px-8 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            GET STARTED — IT'S FREE
          </Link>
        </div>
      </section>
    </div>
  )
}
