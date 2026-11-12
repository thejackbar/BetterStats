// Market: what the club is after. Your cards that other players want come first (so you can see what you hold that is worth
// something to someone), then every player with a visible wish list, the ones whose list lines up with your cards at the top.
// A player's page shows their list against yours and starts a swap in one tap.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"
const chip = { padding: '2px 9px', borderRadius: 999, fontSize: 11.5, fontWeight: 700, border: '1px solid var(--pb-hairline, rgba(255,255,255,.25))' }

function Demand({ list, focus, ui, basePath }) {
  const focused = useRef(null)
  useEffect(() => { if (focused.current) focused.current.scrollIntoView({ block: 'center' }) }, [focus, list])
  if (!list.length) return <div data-no-demand className="rounded-2xl border pb-hairline bg-pb-surface p-5 text-sm text-pb-dim mb-6">None of your cards are on a wish list you can see yet. When another player adds a card you hold, it shows up here.</div>
  return (
    <div className="grid gap-3 mb-6" data-demand-list style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))' }}>
      {list.map((c) => (
        <div key={c.key} ref={focus === c.key ? focused : null} data-demand={c.key} data-focused={focus === c.key ? 'yes' : undefined}
          className="flex gap-3 rounded-xl border bg-pb-surface p-3" style={{ borderColor: focus === c.key ? ui.accent : 'var(--pb-hairline, rgba(255,255,255,.18))', borderWidth: focus === c.key ? 2 : 1 }}>
          <Mini card={c} {...ui} width={84} count={1} />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold" style={{ overflowWrap: 'anywhere' }}>{cardLine(c)}</div>
            <div className="text-[12.5px] text-pb-dim">You hold {c.tradeable} {c.tradeable === 1 ? 'copy' : 'copies'}</div>
            <div className="text-[12.5px] mt-1.5" data-demand-wanters>
              Wanted by{' '}
              {c.wanted_by.map((w, i) => (
                <span key={w.player_id}>{i > 0 && ', '}<Link to={`${basePath}/market/${w.player_id}`} className="underline font-semibold" data-wanter={w.player_id}>{w.name}</Link></span>
              ))}
              {c.hidden > 0 && <span className="text-pb-faint">{c.wanted_by.length > 0 ? ' and ' : ''}{c.hidden} {c.hidden === 1 ? 'player who keeps' : 'players who keep'} their list private</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Market() {
  const { token, club, accent, display, sponsor, basePath } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [q, setQ] = useState('')
  const [params] = useSearchParams()
  useEffect(() => { api.availPublicMarket(token).then(setData).catch(() => setFailed(true)) }, [token])
  const ui = { club, accent, display, sponsor }
  const shown = useMemo(() => {
    if (!data) return []
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return data.players.filter((p) => words.every((w) => p.name.toLowerCase().includes(w)))
  }, [data, q])
  if (failed) return <div className="text-sm text-pb-faint" data-market-failed>The Market could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-market-loading>Loading the Market…</div>
  return (
    <div data-screen="market">
      <PageHead title="Market" sub="See what other players are after. Your cards that someone wants are shown first, and a player's page lines their wish list up against yours so you can plan swaps that lead you to the cards you want."
        actions={<Link to={`${basePath}/wishlist`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">My wish list{data.my_wants ? ` (${data.my_wants})` : ''}</Link>} />
      <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2" data-market-demand-head>Your cards in demand ({data.demand.length})</h2>
      <Demand list={data.demand} focus={params.get('card')} ui={ui} basePath={basePath} />
      <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2" data-market-players-head>Wish lists ({data.players.length})</h2>
      {data.players.length === 0 ? (
        <div data-no-wishers className="rounded-2xl border pb-hairline bg-pb-surface p-5 text-sm text-pb-dim">Nobody has a wish list the club can see yet. Add cards to yours from Club cards and others will find you here.</div>
      ) : (
        <>
          {data.my_wants === 0 && <p data-market-hint className="text-sm text-pb-dim mb-3">Your own wish list is empty, so there is no match against it yet. Add the cards you are after and the players who hold them rise to the top.</p>}
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" aria-label="Find a player" data-market-search className="w-full max-w-sm mb-3 bg-pb-surface border pb-hairline rounded-lg px-3 py-2 text-sm" />
          <div className="flex flex-col gap-2" data-market-players>
            {shown.map((p) => (
              <Link key={p.player_id} to={`${basePath}/market/${p.player_id}`} data-market-player={p.player_id} data-swap-possible={p.swap_possible ? 'yes' : 'no'}
                className="flex items-center gap-3 flex-wrap rounded-xl border pb-hairline bg-pb-surface px-4 py-3">
                <span className="font-semibold min-w-0 flex-1" style={{ overflowWrap: 'anywhere' }}>{p.name}</span>
                <span className="text-[12.5px] text-pb-dim">wants {p.wants} {p.wants === 1 ? 'card' : 'cards'}</span>
                {p.they_want_mine > 0 && <span data-chip="they-want" style={{ ...chip, background: accent, color: onColor(accent), borderColor: accent }}>{p.they_want_mine} of yours</span>}
                {p.i_want_theirs > 0 && <span data-chip="i-want" style={chip}>{p.i_want_theirs} you want</span>}
                {p.swap_possible && <span data-chip="swap" style={{ font: `700 10px ${MONO}`, letterSpacing: 1.1, textTransform: 'uppercase', color: accent }}>Swap possible</span>}
              </Link>
            ))}
            {shown.length === 0 && <div className="text-sm text-pb-dim" data-no-market-match>No player matches that.</div>}
          </div>
        </>
      )}
    </div>
  )
}
