import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'

// Click-to-cycle order and per-status display.
const CYCLE = ['NO_RESPONSE', 'AVAILABLE', 'UNAVAILABLE', 'MAYBE']
const META = {
  AVAILABLE:   { g: '✓', cls: 'bg-pb-accent/20 text-pb-accent border-pb-accent/40' },
  UNAVAILABLE: { g: '✕', cls: 'bg-pb-red/20 text-pb-red border-pb-red/40' },
  MAYBE:       { g: '?', cls: 'bg-amber-400/20 text-amber-300 border-amber-400/40' },
  NO_RESPONSE: { g: '–', cls: 'bg-pb-surface2 text-pb-faintest border-pb-hairline' },
}

function fmtDay(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d }
}

export default function AdminAvailability() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const [data, setData] = useState(null)
  const [avail, setAvail] = useState({}) // {playerId: {date: {status}}}

  const load = useCallback(() => {
    setData(null)
    api.bsAvailabilityMatrix()
      .then(d => { setData(d); setAvail(d.availability || {}) })
      .catch(e => { toast.error(e.message); setData({ dates: [], players: [], availability: {} }) })
  }, [toast])

  useEffect(() => { load() }, [load])

  const cycle = async (pid, date, cur) => {
    if (!canEdit) return
    const next = CYCLE[(CYCLE.indexOf(cur) + 1) % CYCLE.length]
    setAvail(a => ({ ...a, [pid]: { ...(a[pid] || {}), [date]: { status: next } } }))
    try {
      await api.bsSetAvailability({ player_id: pid, date, status: next })
    } catch (e) {
      toast.error('Save failed: ' + e.message)
      setAvail(a => ({ ...a, [pid]: { ...(a[pid] || {}), [date]: { status: cur } } }))
    }
  }

  if (data === null) return <BetterSelectLayout title="Availability"><PbSpinner message="Loading availability…" /></BetterSelectLayout>

  if (!data.dates.length) {
    return (
      <BetterSelectLayout title="Availability">
        <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures to collect availability for.{' '}
          <Link to="/admin/betterselect/fixtures" className="text-pb-accent underline">Add or sync fixtures</Link> first.
        </div>
      </BetterSelectLayout>
    )
  }

  return (
    <BetterSelectLayout title="Availability">
      <p className="text-pb-faint text-sm mb-3 max-w-2xl">
        {canEdit ? 'Click a cell to cycle: ' : 'Read-only — '}
        <span className="text-pb-accent">✓ available</span> ·{' '}
        <span className="text-pb-red">✕ unavailable</span> ·{' '}
        <span className="text-amber-300">? maybe</span> ·{' '}
        <span className="text-pb-faintest">– no response</span>.
        One answer covers every fixture that day; two-day games show both weekends.
      </p>

      <div className="pb-card overflow-auto">
        <table className="border-collapse text-sm w-full">
          <thead>
            <tr>
              <th className="sticky left-0 z-20 bg-pb-surface2 text-left px-3 py-2 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint min-w-[160px]">
                Player
              </th>
              {data.dates.map(d => (
                <th key={d.date} className="px-2 py-2 border-l pb-hairline bg-pb-surface2 align-top min-w-[112px]">
                  <div className="font-semibold text-pb-text text-xs">{fmtDay(d.date)}</div>
                  <div className="mt-1 space-y-0.5">
                    {d.fixtures.map((f, fi) => (
                      <div key={fi} className="text-[10px] text-pb-faint truncate max-w-[104px]" title={f.opponent_name || f.label || ''}>
                        {f.two_day && <span className="text-amber-300">{f.role === 'day1' ? 'D1 ' : 'D2 '}</span>}
                        {f.home_away === 'AWAY' ? '@' : f.home_away === 'BYE' ? '' : 'v'} {f.opponent_name || f.label || 'TBC'}
                      </div>
                    ))}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.players.map(p => (
              <tr key={p.id}>
                <td className="sticky left-0 z-10 bg-pb-surface px-3 py-1.5 whitespace-nowrap border-t pb-hairline">
                  <span className="text-sm">{p.display_name}</span>
                  {p.player_role && <span className="ml-2 font-mono text-[9px] text-pb-faintest uppercase">{p.player_role}</span>}
                </td>
                {data.dates.map(d => {
                  const st = avail[p.id]?.[d.date]?.status || 'NO_RESPONSE'
                  const m = META[st]
                  return (
                    <td key={d.date} className="px-1.5 py-1.5 border-l border-t pb-hairline text-center">
                      <button
                        onClick={() => cycle(p.id, d.date, st)}
                        disabled={!canEdit}
                        className={`w-9 h-7 rounded border text-sm transition-transform active:scale-90 ${m.cls} ${canEdit ? 'cursor-pointer' : 'cursor-default'}`}
                        title={st}
                      >{m.g}</button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BetterSelectLayout>
  )
}
