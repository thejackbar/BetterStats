// Junior Rotation: a one-page sheet for the clipboard. Its own route with no
// admin chrome, forced to the light theme so it prints black on white whatever
// the screen is set to. The Print button and the back link are left off the
// paper by `.rot-no-print`.
import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../../../lib/api'
import { PbSpinner } from '../../../../lib/presskit'
import LineupSheet, { formatRoundDate, roundToLineup } from './LineupSheet'
import { ROTATION_URL } from '../Rotation'

export default function RotationPrint() {
  const { groupId, roundId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    api.rotGetRound(roundId).then((d) => { if (alive) setData(d) }).catch((e) => { if (alive) setError(e.message || 'Could not load this game.') })
    return () => { alive = false }
  }, [roundId])

  return (
    <div data-theme="light" className="min-h-screen bg-pb-bg text-pb-text">
      <style>{'@media print { .rot-no-print { display: none !important } body { background: #fff !important } }'}</style>
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="rot-no-print flex items-center justify-between gap-3 mb-5">
          <Link to={`${ROTATION_URL}/${groupId}`} className="text-[13px] text-pb-dim underline">Back to the group</Link>
          <button type="button" onClick={() => window.print()} data-print-now
            className="font-display font-semibold text-[13.5px] px-3.5 py-2 rounded-lg bg-pb-accent text-[#08110b]">Print this sheet</button>
        </div>
        {error && <p className="text-pb-red">{error}</p>}
        {!error && !data && <PbSpinner message="Loading…" />}
        {data && (
          <>
            <header className="mb-4">
              <h1 className="font-display font-bold text-2xl leading-tight">{data.group.name}</h1>
              <p className="text-pb-dim text-[14px] mt-0.5">
                {data.round.label ? `${data.round.label} · ` : ''}{formatRoundDate(data.round.round_date)}
                {data.round.status !== 'locked' ? ' · draft' : ''}
              </p>
            </header>
            <LineupSheet {...roundToLineup(data.round, data.group, data.players)} bats={data.group.bats} />
          </>
        )}
      </div>
    </div>
  )
}
