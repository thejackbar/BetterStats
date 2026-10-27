// Sets and the club: the sets a player can work towards completing, the collectors board (opt in) and what has happened in the
// club's cards this week. Each part shows only when the club has it switched on. Finishing a set earns a banner and nothing else.
import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

function Tabs({ tab }) {
  const { basePath, accent, features } = usePC()
  const tabs = [['sets', '', 'Sets'], ['board', '/board', 'Collectors'], ['week', '/week', 'This week']].filter(([k]) => (k === 'sets' ? features.sets : features[k === 'week' ? 'feed' : 'board']))
  return (
    <div role="tablist" aria-label="Club" className="flex gap-2 mb-5 flex-wrap">
      {tabs.map(([k, to, label]) => (
        <Link key={k} to={`${basePath}/sets${to}`} role="tab" aria-selected={tab === k} data-club-tab={k} className="px-4 py-2 rounded-lg text-sm font-semibold border pb-hairline"
          style={tab === k ? { background: accent, color: onColor(accent), borderColor: accent } : undefined}>{label}</Link>
      ))}
    </div>
  )
}

export function SetsList() {
  const { token, basePath, accent, display } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { api.availPublicSets(token).then(setData).catch(() => setFailed(true)) }, [token])
  if (failed) return <div className="text-sm text-pb-faint" data-sets-failed>Sets could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-sets-loading>Loading sets…</div>
  const groups = [...new Set(data.sets.map((s) => s.group))]
  return (
    <div data-sets-list>
      <p className="text-sm text-pb-dim mb-4 max-w-prose">Work towards completing a set by collecting every card in it. {data.complete > 0 ? `You have finished ${data.complete} ${data.complete === 1 ? 'set' : 'sets'}.` : 'There is no prize for finishing one beyond bragging rights.'}</p>
      {data.sets.length === 0 && <div className="text-sm text-pb-dim" data-no-sets>The club does not have enough cards to make sets yet.</div>}
      {groups.map((g) => (
        <div key={g} className="mb-6">
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2">{g}</h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))' }}>
            {data.sets.filter((s) => s.group === g).map((s) => (
              <Link key={s.key} to={`${basePath}/set/${encodeURIComponent(s.key)}`} data-set={s.key} className="block rounded-2xl border pb-hairline bg-pb-surface p-4 hover:opacity-90" style={{ textDecoration: 'none', color: 'inherit' }}>
                <div className="flex items-start justify-between gap-2">
                  <div style={{ font: `800 20px/1.1 ${display}`, textTransform: 'uppercase' }}>{s.title}</div>
                  {s.complete && <span data-set-complete className="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold" style={{ background: accent, color: onColor(accent), font: `700 10px ${MONO}`, letterSpacing: 1 }}>COMPLETE</span>}
                </div>
                <div className="text-[13px] text-pb-dim mt-1">{s.blurb}</div>
                <div style={{ height: 6, borderRadius: 3, background: 'rgba(148,163,184,.25)', margin: '12px 0 6px', overflow: 'hidden' }}><div style={{ width: `${s.percent}%`, height: '100%', background: accent }} /></div>
                <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint" data-set-progress>{s.owned} of {s.total} · {s.percent}%</div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function Board() {
  const { token, basePath, accent, display, club, sponsor } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const read = () => api.availPublicBoard(token).then(setData).catch(() => setFailed(true))
  useEffect(() => { read() }, [token]) // eslint-disable-line react-hooks/exhaustive-deps
  if (failed) return <div className="text-sm text-pb-faint" data-board-failed>The board could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-board-loading>Loading the board…</div>
  const ui = { club, accent, display, sponsor }
  return (
    <div data-board>
      <p className="text-sm text-pb-dim mb-4 max-w-prose">Players ranked by how much of the club's set they hold. It counts different cards, never copies, so collecting doubles does not move anyone up. Everyone in the club is on it, and only their name, their showcase and their rarest player card are shown. Anyone can leave in Settings.</p>
      {data.me_hidden ? (
        <div data-board-hidden className="rounded-2xl border pb-hairline bg-pb-surface p-4 mb-5 text-sm">You have left the board, so nobody sees where you stand. You can come back in Settings.</div>
      ) : data.me_rank ? (
        <div data-board-me className="text-sm mb-4">You are number <strong>{data.me_rank}</strong> of {data.count}.</div>
      ) : null}
      {data.entries.length === 0 && <div className="text-sm text-pb-dim" data-no-board>Nobody has a card to rank yet.</div>}
      <div className="flex flex-col gap-2">
        {data.entries.map((e) => (
          <div key={e.player_id} data-board-row={e.player_id} className="rounded-2xl border pb-hairline bg-pb-surface p-3 flex flex-wrap gap-3 items-center">
            <div style={{ font: `800 26px/1 ${display}`, width: 36, textAlign: 'center', opacity: 0.8 }}>{e.rank}</div>
            <div className="flex-1 min-w-[160px]">
              <div className="font-semibold" style={{ overflowWrap: 'anywhere' }}>{e.name}</div>
              <div style={{ height: 6, borderRadius: 3, background: 'rgba(148,163,184,.25)', margin: '8px 0 4px', overflow: 'hidden' }}><div style={{ width: `${Math.min(100, e.percent)}%`, height: '100%', background: accent }} /></div>
              <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint">{e.percent}% of the set · {e.held} different cards</div>
            </div>
            {e.rarest && <div title={`Rarest player card: ${cardLine(e.rarest)}`}><div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-1">Rarest</div><Mini card={e.rarest} {...ui} width={54} count={1} /></div>}
            {e.showcase.length > 0 && (
              <div data-board-showcase><div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-1">Showcase</div>
                <div className="flex gap-1.5 flex-wrap">{e.showcase.map((c) => <Link key={c.key} to={`${basePath}/card/${encodeURIComponent(c.key)}`}><Mini card={c} {...ui} width={54} count={1} /></Link>)}</div></div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Week({ limit }) {
  const { token, basePath, accent, display, club, sponsor } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { api.availPublicFeed(token).then(setData).catch(() => setFailed(true)) }, [token])
  if (failed) return <div className="text-sm text-pb-faint" data-feed-failed>The feed could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-feed-loading>Loading…</div>
  const ui = { club, accent, display, sponsor }
  const all = data.events || []
  const events = limit ? all.slice(0, limit) : all
  return (
    <div data-feed>
      {events.length === 0 && <div className="text-sm text-pb-dim" data-no-feed>Nothing yet this week.</div>}
      <div className="flex flex-col gap-2">
        {events.map((e, i) => (
          <div key={i} data-feed-event={e.type} className="rounded-xl border pb-hairline bg-pb-surface p-3 flex gap-3 items-center">
            {e.card && <Link to={`${basePath}/card/${encodeURIComponent(e.card.key)}`}><Mini card={e.card} {...ui} width={46} count={1} /></Link>}
            <div className="min-w-0 flex-1"><div className="text-sm" style={{ overflowWrap: 'anywhere' }}>{e.text}</div><div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mt-0.5">{new Date(e.on).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}</div></div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Sets({ tab = 'sets' }) {
  const { features, basePath } = usePC()
  // A part the club has switched off is not a place to land: go to the first part that is on, or say none is.
  const on = { sets: features.sets, board: features.board, week: features.feed }
  if (!on[tab]) {
    const first = ['sets', 'board', 'week'].find((k) => on[k])
    if (first) return <Navigate to={`${basePath}/sets${first === 'sets' ? '' : `/${first}`}`} replace />
  }
  const sub = { sets: 'Complete sets of cards.', board: 'Who holds the most of the club\'s set.', week: 'What has happened in the club\'s cards in the last seven days.' }[tab]
  return (
    <div data-screen="sets">
      <PageHead title={tab === 'board' ? 'Collectors' : tab === 'week' ? 'This week' : 'Sets'} sub={sub} />
      <Tabs tab={tab} />
      {tab === 'sets' && (features.sets ? <SetsList /> : <NotOn />)}
      {tab === 'board' && (features.board ? <Board /> : <NotOn />)}
      {tab === 'week' && (features.feed ? <Week /> : <NotOn />)}
    </div>
  )
}

function NotOn() {
  return <div className="text-sm text-pb-dim" data-not-on>Your club has this switched off.</div>
}
