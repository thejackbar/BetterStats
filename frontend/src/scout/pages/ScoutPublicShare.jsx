import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { BAT_HANDS, bowlingLabel } from '../lib/watchlistOptions'

function batHandLabel(code) {
  const found = BAT_HANDS.find(([c]) => c === code)
  return found ? found[1] : null
}

// Standalone public page — no scout login, no ScoutLayout chrome. The global
// Navbar/ClubCTABar/FaviconManager already exclude everything under
// /betterscout, so no extra wiring is needed for those.
export default function ScoutPublicShare() {
  const { token } = useParams()
  const [data, setData] = useState(undefined) // undefined = loading, null = invalid link
  const [error, setError] = useState(null)

  useEffect(() => {
    scoutApi.getSharedCard(token)
      .then(setData)
      .catch((err) => { setError(err.message); setData(null) })
  }, [token])

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <style>{`
        @media print {
          .scout-no-print { display: none !important; }
          .scout-print-area { box-shadow: none !important; }
          body { background: white !important; }
        }
      `}</style>
      <header className="scout-no-print border-b border-pb-hairline bg-pb-surface">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <span className="font-bold">Better<span className="pb-gradient-text">Scout</span></span>
          <span className="text-xs text-pb-dim uppercase font-mono">Shared player</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {data === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}
        {data === null && (
          <div className="pb-card p-6 text-center">
            <p className="font-medium">This share link isn't valid.</p>
            <p className="text-sm text-pb-dim mt-1">It may have been turned off, or the address is wrong.</p>
          </div>
        )}
        {data && <SharedCard data={data} />}
      </main>
    </div>
  )
}

function SharedCard({ data }) {
  const { player, stats, tags, role, batting_hand, bowling_action, bowling_type, region, level, notes } = data
  const totals = stats?.totals
  const seasons = stats?.seasons || []
  const bowling = bowlingLabel(bowling_action, bowling_type)

  const hand = batHandLabel(batting_hand)
  const chips = [
    role,
    hand,
    bowling && bowling !== '—' ? bowling : null,
    region,
    level,
  ].filter(Boolean)

  return (
    <div className="scout-print-area space-y-6">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">{player.name}</h1>
          <p className="text-sm text-pb-dim">{player.club_name || 'No club recorded'}</p>
        </div>
        <button onClick={() => window.print()} className="scout-no-print text-sm px-3 py-1.5 rounded border border-pb-hairline hover:bg-pb-surface2">
          Print / Save PDF
        </button>
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <span key={c} className="text-xs px-2 py-1 rounded-full bg-pb-surface2 text-pb-dim">{c}</span>
          ))}
        </div>
      )}

      {tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span key={t} className="text-xs px-2 py-1 rounded-full border border-[var(--pb-accent)] text-[var(--pb-accent)]">{t}</span>
          ))}
        </div>
      )}

      {notes && (
        <div className="pb-card p-4">
          <div className="text-xs text-pb-dim uppercase font-mono mb-1">Notes</div>
          <p className="text-sm whitespace-pre-wrap">{notes}</p>
        </div>
      )}

      {!totals && <p className="text-sm text-pb-dim">No stats available for this player.</p>}

      {totals && (
        <>
          <div className="pb-card p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <Stat label="Matches" value={totals.matches} />
            <Stat label="Runs" value={totals.runs} />
            <Stat label="Average" value={totals.average} />
            <Stat label="Strike rate" value={totals.strike_rate} />
            <Stat label="Wickets" value={totals.wickets} />
            <Stat label="Economy" value={totals.economy} />
            <Stat label="Best figures" value={totals.best} />
            <Stat label="Catches" value={totals.catches} />
          </div>

          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-pb-dim text-xs uppercase font-mono">
                <tr className="border-b border-pb-hairline">
                  <th className="text-left px-3 py-2">Season</th>
                  <th className="text-right px-3 py-2">Matches</th>
                  <th className="text-right px-3 py-2">Runs</th>
                  <th className="text-right px-3 py-2">Avg</th>
                  <th className="text-right px-3 py-2">Wkts</th>
                  <th className="text-right px-3 py-2">Econ</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                    <td className="px-3 py-2">{s.year}</td>
                    <td className="px-3 py-2 text-right">{s.matches}</td>
                    <td className="px-3 py-2 text-right">{s.runs}</td>
                    <td className="px-3 py-2 text-right">{s.average ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{s.wickets}</td>
                    <td className="px-3 py-2 text-right">{s.economy ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xs text-pb-dim uppercase font-mono">{label}</div>
      <div className="text-lg font-semibold">{value ?? '—'}</div>
    </div>
  )
}
