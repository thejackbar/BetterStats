import { Link } from 'react-router-dom'
import { reviewPerformers, defaultHeadlines } from '../../../social/roundReviewPost'

// The Round Review Data step (Association Socials): pick a round saved in the
// Performance Tracker, then adjust what the posts say. Figures always come from
// the round as the tracker read it; only the words here are typed.
const INPUT = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-sm text-pb-text'
const LABEL = 'font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1'

export default function RoundReviewControls({ rounds, round, status, opts, onPickRound, onOpts }) {
  if (rounds === null) return <p className="text-[11px] text-pb-dim">Reading your tracked rounds…</p>
  if (!rounds.length) {
    return (
      <p className="text-[11px] text-pb-dim leading-relaxed">
        No rounds tracked yet. <Link to="/admin/performance" className="underline">Open the Performance Tracker</Link>, paste a match link for each competition and pull the round.
      </p>
    )
  }
  const perf = round ? reviewPerformers(round) : []
  const headlines = Array.isArray(opts.headlines) ? opts.headlines : (round ? defaultHeadlines(round) : [])
  return (
    <div className="flex flex-col gap-3" data-testid="round-review-controls">
      <label className="min-w-0"><span className={LABEL}>ROUND</span>
        <select className={INPUT} value={round?.id || ''} onChange={(e) => onPickRound(e.target.value)} aria-label="Tracked round">
          {!round && <option value="">Pick a round</option>}
          {rounds.map(r => <option key={r.id} value={r.id}>{r.round_label || 'Untitled round'}{r.round_date ? ` · ${r.round_date}` : ''}</option>)}
        </select>
      </label>
      {status && <p className="text-[11px] text-red-500">{status}</p>}
      {round && (
        <>
          <label className="min-w-0"><span className={LABEL}>HEADING (OPTIONAL)</span>
            <input className={INPUT} value={opts.title || ''} placeholder="Leave blank for the layout's own" onChange={(e) => onOpts({ title: e.target.value })} />
          </label>
          <label className="min-w-0"><span className={LABEL}>ROUND WRAP HEADLINES (ONE PER LINE)</span>
            <textarea className={INPUT} rows={5} value={headlines.join('\n')} aria-label="Round wrap headlines"
              onChange={(e) => onOpts({ headlines: e.target.value.split('\n') })} />
          </label>
          {Array.isArray(opts.headlines) && (
            <button type="button" className="self-start text-[11px] text-pb-faint underline" onClick={() => onOpts({ headlines: null })}>Use the round's own headlines</button>
          )}
          <label className="min-w-0"><span className={LABEL}>CALL TO ACTION (ROUND WRAP)</span>
            <input className={INPUT} value={opts.cta || ''} placeholder="Full wrap on the podcast this week" onChange={(e) => onOpts({ cta: e.target.value })} />
          </label>
          <label className="min-w-0"><span className={LABEL}>PLAYER OF THE ROUND</span>
            <select className={INPUT} value={opts.potrKey || perf[0]?.key || ''} onChange={(e) => onOpts({ potrKey: e.target.value })} aria-label="Player of the round">
              {perf.map(p => <option key={p.key} value={p.key}>{p.name} ({p.team}) {p.line}, {p.comp}</option>)}
            </select>
          </label>
          <p className="text-[11px] text-pb-faint leading-relaxed">Scores, figures, crests and next week's match of the round come from the round as the tracker read it. Pull it again there to update them.</p>
        </>
      )}
    </div>
  )
}
