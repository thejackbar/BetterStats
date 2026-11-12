// One player in the Market: the cards they are after (the ones you hold are marked, and can be picked to give) beside the cards
// they could swap (the ones on your wish list are marked, and can be picked to ask for). One tap carries both picks into the builder.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

function Grid({ cards, picked, onPick, mark, markLabel, ui, testid }) {
  return (
    <div className="grid gap-3" data-grid={testid} style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(112px, 1fr))' }}>
      {cards.map((c) => {
        const on = mark(c)
        return (
          <div key={c.key} data-market-card={c.key} data-marked={on ? 'yes' : 'no'} className="text-center" style={{ opacity: on || testid === 'theirs' ? 1 : 0.5 }}>
            <div style={{ display: 'inline-block', borderRadius: 10, outline: on ? `2px dashed ${ui.accent}` : 'none', outlineOffset: 3 }}>
              <Mini card={c} {...ui} width={104} count={c.tradeable > 1 ? c.tradeable : undefined}
                onClick={on || testid === 'theirs' ? () => onPick(c) : undefined} selected={picked.has(c.key) ? true : undefined} />
            </div>
            {on && <div className="font-mono text-[10px] tracking-wide2 uppercase mt-1" style={{ color: ui.accent }}>{markLabel(c)}</div>}
          </div>
        )
      })}
    </div>
  )
}

export default function MarketPlayer() {
  const { pid } = useParams()
  const { token, club, accent, display, sponsor, basePath } = usePC()
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [give, setGive] = useState(() => new Map())
  const [get, setGet] = useState(() => new Map())
  const navigate = useNavigate()
  useEffect(() => {
    setData(null); setErr(''); setGive(new Map()); setGet(new Map())
    api.availPublicMarketPlayer(token, pid).then(setData).catch((e) => setErr(e?.message || 'That wish list is not available.'))
  }, [token, pid])
  const ui = { club, accent, display, sponsor }
  const flip = (setter) => (card) => setter((m) => { const n = new Map(m); if (n.has(card.key)) n.delete(card.key); else n.set(card.key, card); return n })
  if (err) return <div data-market-player-error className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }}>{err} <Link to={`${basePath}/market`} className="underline">Back to the Market</Link></div>
  if (!data) return <div className="text-sm text-pb-faint" data-market-player-loading>Loading…</div>
  const name = data.player.name
  const first = name.split(',').pop().trim() || name
  const mine = data.wants.filter((c) => c.mine).length
  const theirsOnList = data.theirs.filter((c) => c.on_my_list).length
  const start = () => navigate(`${basePath}/swaps/new`, { state: {
    ask: { player: data.player, cards: [...get.values()] },
    ...(give.size ? { giveList: [...give.values()].map((card) => ({ card, qty: 1 })) } : {}),
  } })
  const btn = { padding: '11px 18px', borderRadius: 12, font: `700 12px ${MONO}`, letterSpacing: 1.3, textTransform: 'uppercase', background: accent, color: onColor(accent), border: 0 }
  return (
    <div data-screen="market-player">
      <PageHead title={name} sub={`${mine > 0 ? `You hold ${mine} of the ${data.wants.length} cards they want. ` : `They want ${data.wants.length} ${data.wants.length === 1 ? 'card' : 'cards'} and you hold none of them. `}${theirsOnList > 0 ? `${theirsOnList} of the cards they could swap ${theirsOnList === 1 ? 'is' : 'are'} on your wish list.` : 'None of the cards they could swap are on your wish list.'}`}
        actions={<Link to={`${basePath}/market`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">Back to the Market</Link>} />
      <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-1" data-wants-head>What {first} wants ({data.wants.length})</h2>
      <p className="text-[12.5px] text-pb-dim mb-3">Cards you hold are outlined. Tap one to put it in the swap.</p>
      {data.wants.length === 0 ? <div className="text-sm text-pb-dim mb-6" data-no-their-wants>Nothing on their list right now.</div>
        : <div className="mb-8"><Grid cards={data.wants} picked={give} onPick={flip(setGive)} mark={(c) => c.mine} markLabel={(c) => `You have ${c.tradeable > 1 ? `×${c.tradeable}` : 'this'}`} ui={ui} testid="wants" /></div>}
      <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-1" data-theirs-head>What {first} could swap ({data.theirs.length})</h2>
      <p className="text-[12.5px] text-pb-dim mb-3">Cards on your wish list are outlined. Tap any card to ask for it.</p>
      {data.theirs.length === 0 ? <div className="text-sm text-pb-dim mb-6" data-no-their-cards>They have no cards to swap yet.</div>
        : <div className="mb-8"><Grid cards={data.theirs} picked={get} onPick={flip(setGet)} mark={(c) => c.on_my_list} markLabel={() => 'On your list'} ui={ui} testid="theirs" /></div>}
      <div data-market-bar className="rounded-2xl border pb-hairline bg-pb-surface p-4 flex items-center gap-3 flex-wrap" style={{ position: 'sticky', bottom: 80 }}>
        <div className="text-sm flex-1 min-w-0" data-market-summary style={{ overflowWrap: 'anywhere' }}>
          {give.size || get.size
            ? `You give ${give.size} ${give.size === 1 ? 'card' : 'cards'}${give.size ? ` (${[...give.values()].map(cardLine).join(', ')})` : ''}. You get ${get.size} ${get.size === 1 ? 'card' : 'cards'}${get.size ? ` (${[...get.values()].map(cardLine).join(', ')})` : ''}.`
            : `Pick the cards to give and the cards to ask for, or start a swap with ${first} and choose there.`}
        </div>
        <button type="button" onClick={start} data-market-start style={btn}>Start a swap with {first}</button>
      </div>
    </div>
  )
}
