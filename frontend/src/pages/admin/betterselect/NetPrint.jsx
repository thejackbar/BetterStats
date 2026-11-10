// Net session: a sheet for the clipboard. Its own route with no admin chrome,
// forced to the light theme so it prints black on white whatever the screen is
// set to. The Print button and the back link are left off the paper by
// `.net-no-print`.
//
// A time-slot session prints the grid the way the club's own sheet reads: a time
// down the left, a column per net, one name per row, empty rows left empty so the
// sheet can still be written on. A queue session prints the batting order.
import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import { fmtSlot } from './NetGrid'

const fmtDate = (d) => { try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) } catch { return d || '' } }

function GridSheet({ live }) {
  const grid = live.grid
  const byId = new Map((live.attendees || []).map((a) => [a.id, a]))
  const name = (id) => (byId.get(id) || {}).name || ''
  const unplaced = (grid.no_net || []).map(name).filter(Boolean)
  const sitting = (live.attendees || []).filter((a) => a.bats === false)
  if (!grid.configured) return <p>The nets have not been set up for this session yet.</p>
  return (
    <>
      <table className="w-full border-collapse text-[13px]" data-print-grid>
        <thead>
          <tr>
            <th className="border border-black px-2 py-1.5 text-left w-[64px]">Time</th>
            {grid.nets.map((n) => (
              <th key={n.id} className="border border-black px-2 py-1.5 text-left">
                <div className="text-[14px]">{n.name}</div>
                <div className="font-normal text-[11px] text-pb-dim">{n.catch_all ? 'everyone else' : ''}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.times.map((t, i) => (
            <tr key={i} style={{ height: 30 }}>
              <td className="border border-black px-2 tabular-nums">{fmtSlot(t)}</td>
              {grid.nets.map((n) => {
                const c = n.cells[i] || {}
                return (
                  <td key={n.id} className="border border-black px-2" style={c.repeat ? { fontStyle: 'italic', color: '#555' } : undefined}>
                    {c.attendee_id ? name(c.attendee_id) : ''}{c.repeat ? ' (2nd go)' : ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {grid.nets.some((n) => n.overflow.length > 0) && (
        <p className="mt-3 text-[13px]" data-print-overflow>
          <b>Does not fit before the finish:</b>{' '}
          {grid.nets.flatMap((n) => n.overflow.map((x) => `${name(x)} (${n.name})`)).join(', ')}
        </p>
      )}
      {unplaced.length > 0 && <p className="mt-2 text-[13px]"><b>Not in a net:</b> {unplaced.join(', ')}</p>}
      {sitting.length > 0 && <p className="mt-2 text-[13px]"><b>Not batting:</b> {sitting.map((a) => (a.note ? `${a.name} (${a.note})` : a.name)).join(', ')}</p>}
    </>
  )
}

function QueueSheet({ live }) {
  const waiting = (live.attendees || []).filter((a) => !a.batted && a.bats !== false)
  const done = (live.attendees || []).filter((a) => a.batted)
  const sitting = (live.attendees || []).filter((a) => !a.batted && a.bats === false)
  const nets = (live.settings && live.settings.nets) || 1
  return (
    <div data-print-queue>
      <h2 className="font-display font-bold text-[16px] mb-1">Batting order</h2>
      <ol className="text-[14px]">
        {waiting.map((a, i) => (
          <li key={a.id} className="border-b border-black py-1.5 flex gap-3">
            <span className="w-6 tabular-nums">{i + 1}.</span><span className="flex-1">{a.name}</span>
            {i < nets && <span className="text-[11px] uppercase tracking-wide">net {i + 1}</span>}
          </li>
        ))}
      </ol>
      {waiting.length === 0 && <p className="text-[13px]">Nobody is waiting.</p>}
      {done.length > 0 && <p className="mt-3 text-[13px]"><b>Batted:</b> {done.map((a) => a.name).join(', ')}</p>}
      {sitting.length > 0 && <p className="mt-2 text-[13px]"><b>Not batting:</b> {sitting.map((a) => a.name).join(', ')}</p>}
    </div>
  )
}

export default function NetPrint() {
  const { id } = useParams()
  const [live, setLive] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    api.nmGetSession(id).then((d) => { if (alive) setLive(d) }).catch((e) => { if (alive) setError(e.message || 'Could not load this session.') })
    return () => { alive = false }
  }, [id])

  const auto = live && live.mode === 'auto'
  return (
    <div data-theme="light" className="min-h-screen bg-pb-bg text-pb-text">
      {/* Landscape for the grid: three or four nets do not fit upright. */}
      <style>{`@media print { .net-no-print { display: none !important } body { background: #fff !important } ${auto ? '@page { size: landscape; margin: 12mm }' : '@page { margin: 14mm }'} }`}</style>
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="net-no-print flex items-center justify-between gap-3 mb-5">
          <Link to={`/admin/betterselect/nets/${id}`} className="text-[13px] text-pb-dim underline">Back to the session</Link>
          <button type="button" onClick={() => window.print()} data-print-now
            className="font-display font-semibold text-[13.5px] px-3.5 py-2 rounded-lg bg-pb-accent text-[#08110b]">Print this sheet</button>
        </div>
        {error && <p className="text-pb-red">{error}</p>}
        {!error && !live && <PbSpinner message="Loading…" />}
        {live && (
          <>
            <header className="mb-4">
              <h1 className="font-display font-bold text-2xl leading-tight">{live.label || 'Net session'}</h1>
              <p className="text-pb-dim text-[14px] mt-0.5">
                {fmtDate(live.session_date)}
                {auto && live.grid && live.grid.configured ? ` · first net ${fmtSlot(live.grid.first_time)}${live.grid.finish_time ? `, finish ${fmtSlot(live.grid.finish_time)}` : ''}` : ''}
                {` · ${live.attendee_count} checked in`}
              </p>
            </header>
            {auto ? <GridSheet live={live} /> : <QueueSheet live={live} />}
          </>
        )}
      </div>
    </div>
  )
}
