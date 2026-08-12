import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { bowlingLabel, BAT_HANDS } from '../lib/watchlistOptions'
import { PLAYER_COLORS, PlayerAvatar, getRowHighlights } from '../components/ScoutUi'

const METRICS = [
  ['matches', 'Matches', true],
  ['runs', 'Runs', true],
  ['average', 'Average', true],
  ['strike_rate', 'Strike rate', true],
  ['wickets', 'Wickets', true],
  ['economy', 'Economy', false],
  ['bowling_average', 'Bowling avg', false],
  ['best', 'Best figures', true],
  ['catches', 'Catches', true],
]

function batHandLabel(code) {
  const found = BAT_HANDS.find(([c]) => c === code)
  return found ? found[1] : null
}

// Standalone public page — no scout login, mirrors ScoutPublicShare.jsx's
// own print pattern (window.print() + a print stylesheet).
export default function ScoutShareComparison() {
  const { token } = useParams()
  const [data, setData] = useState(undefined) // undefined = loading, null = invalid link
  const [error, setError] = useState(null)

  useEffect(() => {
    scoutApi.getSharedComparison(token)
      .then(setData)
      .catch((err) => { setError(err.message); setData(null) })
  }, [token])

  const players = data?.players || []

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
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <span className="font-bold">Better<span className="pb-gradient-text">Scout</span></span>
          <span className="text-xs text-pb-dim uppercase font-mono">Shared comparison</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {data === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}
        {data === null && (
          <div className="pb-card p-6 text-center">
            <p className="font-medium">This share link isn't valid.</p>
            <p className="text-sm text-pb-dim mt-1">It may have expired, or the address is wrong.</p>
          </div>
        )}

        {data && players.length > 0 && (
          <div className="scout-print-area space-y-4">
            <div className="flex items-center justify-between gap-2">
              <h1 className="text-xl font-bold">Player comparison</h1>
              <button onClick={() => window.print()} className="scout-no-print text-sm px-3 py-1.5 rounded border border-pb-hairline hover:bg-pb-surface2">
                Print / Save PDF
              </button>
            </div>

            <div className="pb-card overflow-x-auto">
              <table className="w-full" style={{ tableLayout: 'fixed', minWidth: `${130 + players.length * 140}px` }}>
                <colgroup>
                  <col style={{ width: '130px' }} />
                  {players.map((_, i) => <col key={i} />)}
                </colgroup>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
                    <th className="py-4 pl-4 text-left align-bottom">
                      <span className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Stat</span>
                    </th>
                    {players.map((p, idx) => {
                      const bowl = bowlingLabel(p.bowling_action, p.bowling_type)
                      const chips = [p.role, batHandLabel(p.batting_hand), bowl && bowl !== '—' ? bowl : null].filter(Boolean)
                      return (
                        <th key={p.id} className="py-4 px-3 text-center align-bottom" style={{ borderLeft: '1px solid var(--pb-hairline)' }}>
                          <div className="flex flex-col items-center gap-1.5">
                            <PlayerAvatar name={p.name} photoUrl={p.photo_url} size={42} ringColor={PLAYER_COLORS[idx % PLAYER_COLORS.length]} />
                            <span className="font-semibold text-xs leading-tight" style={{ color: PLAYER_COLORS[idx % PLAYER_COLORS.length] }}>{p.name}</span>
                            <span className="font-mono text-[9px] text-pb-faint uppercase truncate max-w-[110px]">{p.club_name || '—'}</span>
                            {chips.length > 0 && <span className="text-[9.5px] text-pb-faintest leading-tight">{chips.join(' · ')}</span>}
                            {p.tags?.length > 0 && (
                              <div className="flex flex-wrap justify-center gap-1 mt-0.5">
                                {p.tags.map((t) => <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full border border-[var(--pb-accent)] text-[var(--pb-accent)]">{t}</span>)}
                              </div>
                            )}
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map(([key, label, higher], rowIdx) => {
                    const values = players.map((p) => p.stats?.totals?.[key])
                    const highlights = getRowHighlights(values, higher)
                    return (
                      <tr key={key} style={rowIdx > 0 ? { borderTop: '1px solid var(--pb-hairline)' } : {}}>
                        <td className="py-3 pl-4 align-middle"><span className="font-mono text-[10px] tracking-wide text-pb-faint">{label}</span></td>
                        {players.map((p, i) => {
                          const v = values[i]
                          const h = highlights[i]
                          return (
                            <td key={p.id} className="py-3 px-3 text-center align-middle" style={{
                              borderLeft: '1px solid var(--pb-hairline)',
                              background: h === 'best' ? 'rgba(34,197,94,0.14)' : h === 'worst' ? 'rgba(239,68,68,0.14)' : undefined,
                            }}>
                              <span className="font-mono text-[14px] font-bold" style={{
                                color: h === 'best' ? '#86efac' : h === 'worst' ? '#fca5a5' : v != null ? 'var(--pb-text)' : 'var(--pb-faintest)',
                              }}>
                                {v ?? '—'}
                              </span>
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-center text-pb-faintest font-mono text-[10px] tracking-wide2">GREEN = BEST · RED = WORST · ALL TIME</p>
          </div>
        )}
      </main>
    </div>
  )
}
