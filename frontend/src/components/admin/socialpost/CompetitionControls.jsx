// Controls an association socials workspace uses in place of a club's own data
// sources. A workspace has no club games, players or BetterSelect: every post is
// built from a play.cricket.com.au link, and the link names a whole grade round
// (backend: services/social_competition.py).
import { useState } from 'react'
import { api } from '../../../lib/api'

const BTN = 'px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50'
const BTN_STYLE = { background: 'var(--pb-accent)', color: 'var(--pb-bg)' }

export const COMPETITION_LINK_HELP =
  'Paste a match link or the grade\'s Matches page link from play.cricket.com.au. A match link pulls that match\'s round; a grade link pulls the round it has picked, or the next round if none is picked.'

// One link box, shared by every workspace import so the wording and the PlayHQ
// warning read the same everywhere.
export function CompetitionLinkInput({ onFetch, busy, label = 'Paste a match or grade link', button = 'Fetch' }) {
  const [link, setLink] = useState('')
  const go = () => { const q = link.trim(); if (q) onFetch(q) }
  return (
    <>
      <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-1.5">{label}</p>
      <div className="flex gap-2">
        <input value={link} onChange={(e) => setLink(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()}
          placeholder="play.cricket.com.au match or grade link" aria-label={label}
          className="flex-1 min-w-0 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono placeholder:text-pb-faintest" />
        <button onClick={go} disabled={busy} className={BTN} style={BTN_STYLE}>{busy ? 'Loading…' : button}</button>
      </div>
    </>
  )
}

export function PlayhqNotice({ notice }) {
  if (notice?.kind !== 'playhq') return null
  return (
    <div className="mt-2 p-2.5 rounded border border-amber-400/50 bg-amber-400/10">
      <p className="font-mono text-[9px] text-amber-400 leading-relaxed">{notice.message}</p>
    </div>
  )
}

// Matches Cricket Australia served with no scorecard, left out of the post.
export function SkippedNote({ skipped }) {
  if (!skipped?.length) return null
  return (
    <p className="font-mono text-[9px] mt-1.5 text-amber-400 leading-relaxed" data-testid="competition-skipped">
      Cricket Australia has no scorecard yet for {skipped.join(', ')}, so {skipped.length === 1 ? 'it is' : 'they are'} not in this post. Fetch again later, or add {skipped.length === 1 ? 'it' : 'them'} in Content.
    </p>
  )
}

// Lineup: the round's matches, each with both sides; picking a side loads that
// side's published team as the post's lineup.
export function CompetitionLineupBox({ onPick }) {
  const [state, setState] = useState({ status: null, data: null, notice: null })
  const fetchRound = async (q) => {
    setState({ status: 'loading', data: null, notice: null })
    try {
      const data = await api.getSocialCompetitionLineups(q)
      if (data.kind === 'round') { setState({ status: 'ok', data, notice: null }); return }
      setState({ status: data.kind === 'playhq' ? null : (data.message || 'Could not read that link'), data: null, notice: data.kind === 'playhq' ? data : null })
    } catch (e) {
      setState({ status: e?.message || 'failed', data: null, notice: null })
    }
  }
  const matches = state.data?.matches || []
  return (
    <div className="flex flex-col gap-2" data-testid="competition-lineups">
      <CompetitionLinkInput onFetch={fetchRound} busy={state.status === 'loading'} />
      <PlayhqNotice notice={state.notice} />
      {state.status && state.status !== 'loading' && state.status !== 'ok' && (
        <p className="font-mono text-[9px] text-pb-faint">✗ {state.status}</p>
      )}
      {state.status === 'ok' && (
        <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mt-1">
          {[state.data.grade, state.data.round].filter(Boolean).join(' · ')} · pick a side
        </p>
      )}
      {state.status === 'ok' && !matches.length && (
        <p className="text-pb-faintest text-[11px]">No matches in that round.</p>
      )}
      <div className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto">
        {matches.map((m) => (
          <div key={m.match_id} className="px-3 py-2 rounded-lg border pb-hairline bg-pb-surface2">
            <div className="font-mono text-[9px] text-pb-faint mb-1.5">{[m.date, m.venue].filter(Boolean).join(' · ')}</div>
            <div className="flex flex-wrap gap-1.5">
              {m.teams.map((t) => (
                <button key={t.id} onClick={() => onPick(m, t)} disabled={!t.published}
                  className="flex-1 min-w-0 text-left px-2 py-1.5 rounded border pb-hairline bg-pb-surface hover:border-pb-accent disabled:opacity-50 disabled:cursor-not-allowed">
                  <span className="block text-pb-text text-[12px] truncate">{t.label}</span>
                  <span className="block font-mono text-[9px] text-pb-faint">{t.is_home ? 'Home' : 'Away'}{t.published ? ` · ${t.players.length} named` : ' · not named yet'}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Team of the week: the most players one club may have in the team. 0 is no cap.
export function TotwClubCap({ cap, onChange, busy }) {
  const opts = [0, 1, 2, 3, 4]
  return (
    <div className="mb-4" data-testid="totw-club-cap">
      <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-1.5">Most players from one club</p>
      <div className="flex flex-wrap gap-1.5">
        {opts.map((n) => {
          const on = cap === n
          return (
            <button key={n} type="button" onClick={() => onChange(n)} aria-pressed={on} disabled={busy}
              data-testid={`totw-cap-${n}`}
              className="px-3 min-h-8 rounded border font-mono text-[10px] tracking-wide2 transition-colors disabled:opacity-60"
              style={on
                ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent, var(--pb-bg))', borderColor: 'var(--pb-accent)' }
                : { background: 'transparent', color: 'var(--pb-faint)', borderColor: 'var(--pb-hairline, currentColor)' }}>
              {n === 0 ? 'No limit' : n}
            </button>
          )
        })}
      </div>
      <p className="text-pb-faintest text-[10px] mt-1.5 leading-relaxed">
        {cap > 0
          ? `The best ${cap} from each club make the team first. Anyone past that drops below the rest, so you can still swap them in by hand.`
          : 'The best performers on points, whichever club they play for.'}
      </p>
    </div>
  )
}
