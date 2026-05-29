import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'

function fmtDate(d) {
  if (!d) return ''
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d }
}
function fmtTitle(f) {
  const opp = f.opponent_name || f.label || 'TBC'
  if (f.home_away === 'BYE') return 'BYE'
  return `${f.home_away === 'AWAY' ? '@ ' : 'vs '}${opp}`
}

// Side-by-side finalised lineups for all upcoming fixtures (KlubPro "Team List").
export default function AdminSelectionOverview() {
  const toast = useToast()
  const [data, setData] = useState(null)

  const load = useCallback(() => {
    setData(null)
    api.bsSelectionOverview().then(setData).catch(e => { toast.error(e.message); setData({ fixtures: [] }) })
  }, [toast])
  useEffect(() => { load() }, [load])

  if (data === null) return <BetterSelectLayout title="Selection"><PbSpinner message="Loading teams…" /></BetterSelectLayout>

  if (!data.fixtures.length) {
    return (
      <BetterSelectLayout title="Selection">
        <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures.{' '}
          <Link to="/admin/betterselect/fixtures" className="text-pb-accent underline">Add or sync fixtures</Link> first.
        </div>
      </BetterSelectLayout>
    )
  }

  return (
    <BetterSelectLayout title="Selection">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">
        Your upcoming teams side by side. Click a fixture to build or edit its XI.
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {data.fixtures.map(f => (
          <Link key={f.id} to={`/admin/betterselect/select/${f.id}`}
            className="pb-card overflow-hidden hover:border-pb-accent/40 transition-colors flex flex-col">
            <div className="px-3 py-2 border-b pb-hairline" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
              <div className="font-semibold text-sm truncate">{fmtTitle(f)}</div>
              <div className="text-[11px] opacity-90">{fmtDate(f.played_on)}{f.round ? ` · R${f.round}` : ''}</div>
            </div>
            <div className="p-3 flex-1">
              {f.lineup.length === 0 ? (
                <div className="text-pb-faintest text-xs py-4 text-center">No XI selected yet</div>
              ) : (
                <ol className="space-y-0.5">
                  {f.lineup.map((p, i) => (
                    <li key={p.player_id} className="flex items-center gap-2 text-sm">
                      <span className="font-mono text-[10px] text-pb-faintest w-4 text-right">{p.batting_order ?? i + 1}</span>
                      <span className="truncate">{p.display_name}</span>
                      {(p.is_captain || p.is_wicket_keeper) && (
                        <span className="font-mono text-[9px] text-pb-accent shrink-0">
                          {[p.is_captain && '(C)', p.is_wicket_keeper && '(WK)'].filter(Boolean).join(' ')}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
            <div className="px-3 py-1.5 border-t pb-hairline font-mono text-[10px] text-pb-faintest">
              {f.lineup.length} selected
            </div>
          </Link>
        ))}
      </div>
    </BetterSelectLayout>
  )
}
