import { Link } from 'react-router-dom'
import { reviewPerformers, defaultHeadlines } from '../../../social/roundReviewPost'
import { pulledComps, LEADER_TABLES } from '../../../lib/performanceRound'

// The Round Review Data step (Association Socials): pick a round saved in the
// Performance Tracker and the grades to show, then what the open layout needs
// (headlines, a player, a leaderboard, milestone filters, a ladder). Figures
// always come from the round as the tracker read it; only the words are typed.
const INPUT = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-sm text-pb-text'
const LABEL = 'font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1'
const CHIP = (on) => `px-2 py-1 rounded-full border text-xs ${on ? 'border-pb-accent text-pb-accent' : 'pb-hairline text-pb-faint'}`

const SCOPES = [['match', 'In the match'], ['season', 'Season'], ['career', 'Career']]
const STATS = [['batting', 'Batting'], ['bowling', 'Bowling'], ['fielding', 'Fielding'], ['games', 'Games']]

function toggle(list, all, key) {
  const cur = list || all
  const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
  return next.length === all.length ? undefined : next
}

export default function RoundReviewControls({ layout, rounds, round, status, opts, season, onPickRound, onOpts }) {
  if (rounds === null) return <p className="text-[11px] text-pb-dim">Reading your tracked rounds…</p>
  if (!rounds.length) {
    return (
      <p className="text-[11px] text-pb-dim leading-relaxed">
        No rounds tracked yet. <Link to="/admin/performance" className="underline">Open the Performance Tracker</Link>, add a grade from a match link and pull the round.
      </p>
    )
  }
  const comps = round ? pulledComps(round.data) : []
  const keys = opts.grades && opts.grades.length ? opts.grades : null
  const perf = round ? reviewPerformers(round, null, keys) : []
  const headlines = Array.isArray(opts.headlines) ? opts.headlines : (round ? defaultHeadlines(round, keys) : [])
  const ladders = comps.filter(c => (c.pull.ladder || []).length)
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
          {comps.length > 1 && layout !== 'RV8' && (
            <div>
              <span className={LABEL}>GRADES ON THE POST</span>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Grades on the post">
                {comps.map(c => {
                  const on = !keys || keys.includes(c.key)
                  return <button key={c.key} type="button" aria-pressed={on} className={CHIP(on)}
                    onClick={() => onOpts({ grades: toggle(keys, comps.map(x => x.key), c.key) })}>{c.name}</button>
                })}
              </div>
            </div>
          )}
          <label className="min-w-0"><span className={LABEL}>HEADING (OPTIONAL)</span>
            <input className={INPUT} value={opts.title || ''} placeholder="Leave blank for the layout's own" onChange={(e) => onOpts({ title: e.target.value })} />
          </label>
          {layout === 'RV1' && (
            <>
              <label className="min-w-0"><span className={LABEL}>HEADLINES (ONE PER LINE)</span>
                <textarea className={INPUT} rows={5} value={headlines.join('\n')} aria-label="Round wrap headlines"
                  onChange={(e) => onOpts({ headlines: e.target.value.split('\n') })} />
              </label>
              {Array.isArray(opts.headlines) && (
                <button type="button" className="self-start text-[11px] text-pb-faint underline" onClick={() => onOpts({ headlines: null })}>Use the round's own headlines</button>
              )}
              <label className="min-w-0"><span className={LABEL}>CALL TO ACTION</span>
                <input className={INPUT} value={opts.cta || ''} placeholder="Full wrap on the podcast this week" onChange={(e) => onOpts({ cta: e.target.value })} />
              </label>
            </>
          )}
          {layout === 'RV3' && (
            <label className="min-w-0"><span className={LABEL}>PLAYER OF THE ROUND</span>
              <select className={INPUT} value={opts.potrKey || perf[0]?.key || ''} onChange={(e) => onOpts({ potrKey: e.target.value })} aria-label="Player of the round">
                {perf.map(p => <option key={p.key} value={p.key}>{p.name} ({p.team}) {p.line}, {p.comp}</option>)}
              </select>
            </label>
          )}
          {layout === 'RV6' && (
            <label className="min-w-0"><span className={LABEL}>LEADERBOARD</span>
              <select className={INPUT} value={opts.board || 'runs'} onChange={(e) => onOpts({ board: e.target.value })} aria-label="Leaderboard">
                {LEADER_TABLES.map(([label, key]) => <option key={key} value={key}>{label}</option>)}
              </select>
              {!season && <span className="text-[11px] text-pb-dim">Reading the season…</span>}
            </label>
          )}
          {layout === 'RV7' && (
            <div className="flex flex-col gap-2">
              <span className={LABEL}>MILESTONES TO SHOW</span>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Milestone kind">
                {SCOPES.map(([k, label]) => <button key={k} type="button" aria-pressed={!opts.scopes || opts.scopes.includes(k)} className={CHIP(!opts.scopes || opts.scopes.includes(k))}
                  onClick={() => onOpts({ scopes: toggle(opts.scopes, SCOPES.map(x => x[0]), k) })}>{label}</button>)}
              </div>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Milestone stat">
                {STATS.map(([k, label]) => <button key={k} type="button" aria-pressed={!opts.stats || opts.stats.includes(k)} className={CHIP(!opts.stats || opts.stats.includes(k))}
                  onClick={() => onOpts({ stats: toggle(opts.stats, STATS.map(x => x[0]), k) })}>{label}</button>)}
              </div>
              {!season && <span className="text-[11px] text-pb-dim">Reading season and career milestones…</span>}
              <span className="text-[11px] text-pb-faint">Up to eight fit on the post: hundreds, hat-tricks and career marks come first.</span>
            </div>
          )}
          {layout === 'RV8' && ladders.length > 0 && (
            <label className="min-w-0"><span className={LABEL}>LADDER</span>
              <select className={INPUT} value={opts.ladder || ladders[0].key} onChange={(e) => onOpts({ ladder: e.target.value })} aria-label="Ladder">
                {ladders.map(c => <option key={c.key} value={c.key}>{c.name}</option>)}
              </select>
            </label>
          )}
          <p className="text-[11px] text-pb-faint leading-relaxed">Scores, figures and crests come from the round as the tracker read it. Pull it again there to update them.</p>
        </>
      )}
    </div>
  )
}
