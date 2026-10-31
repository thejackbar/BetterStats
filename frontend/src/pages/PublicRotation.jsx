// Junior Rotation: the parent link (public, no login).
//
// Reached from a link the coach shares (/rotation/:token). It shows who bats
// where and who fields where for the group's recent LOCKED games, and nothing
// else: no ids, no notes, no other groups. Names arrive already shortened to a
// first name and last initial unless the coach turned surnames on, and the
// server answers a bad, switched-off or archived link with the same 404.
import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import LineupSheet, { formatRoundDate } from './admin/betterselect/rotation/LineupSheet'

export default function PublicRotation() {
  const { token } = useParams()
  const [state, setState] = useState('loading') // loading | dead | ok
  const [page, setPage] = useState(null)
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    let alive = true
    api.rotPublic(token)
      .then((d) => { if (alive) { setPage(d); setState('ok') } })
      .catch(() => { if (alive) setState('dead') })
    return () => { alive = false }
  }, [token])

  const round = page && page.rounds[idx]
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <div className="max-w-2xl mx-auto px-4 py-8 sm:py-12">
        {state === 'loading' && <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>}
        {state === 'dead' && (
          <div className="py-20 text-center" data-dead>
            <div className="font-display font-bold text-lg">This link isn’t active</div>
            <p className="text-pb-faint text-sm mt-2">It may have been turned off or replaced. Ask your coach for the current link.</p>
          </div>
        )}
        {state === 'ok' && (
          <>
            <header className="mb-5">
              <div className="font-mono text-[11px] tracking-wide2 text-pb-faint uppercase">{page.club}</div>
              <h1 className="font-display font-bold text-2xl leading-tight mt-1" data-group-name>{page.group.name}</h1>
            </header>
            {page.rounds.length === 0 ? (
              <p className="text-pb-dim text-[14px]" data-no-rounds>No lineup has been shared yet. Check back once your coach has set up this week’s game.</p>
            ) : (
              <>
                <div className="flex flex-wrap gap-1.5 mb-4" data-round-picker>
                  {page.rounds.map((r, i) => (
                    <button key={`${r.date}-${i}`} type="button" onClick={() => setIdx(i)}
                      className={`rounded-full px-3 py-1.5 text-[12.5px] border ${i === idx ? 'bg-pb-accent/12 text-pb-accent border-pb-accent/40' : 'text-pb-dim border-pb-hairline2'}`}>
                      {formatRoundDate(r.date)}
                    </button>
                  ))}
                </div>
                <p className="font-display font-semibold text-[15px] mb-3" data-round-title>{round.label ? `${round.label} · ` : ''}{formatRoundDate(round.date)}</p>
                <LineupSheet batting={round.batting} changes={round.changes} bats={page.group.bats} />
              </>
            )}
            <div className="text-center mt-10 font-mono text-[10px] tracking-wide2 text-pb-faintest">Powered by BetterCricket</div>
          </>
        )}
      </div>
    </div>
  )
}
