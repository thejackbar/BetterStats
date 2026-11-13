// One player in the Market: their pile (the spares they have flagged), the cards they are after (the ones you hold are marked, and can
// be picked to give), and the rest of the cards they could swap (the ones on your wish list are marked, and can be picked to ask for).
// A card they hold a spare of is tagged Double. One tap carries both picks into the builder.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

// `mark(card)` outlines a card, `labels(card)` is the line under it, `pickable(card)` says whether it can be tapped.
function Grid({ cards, picked, onPick, mark, labels, pickable, dim, ui, testid }) {
  return (
    <div className="grid gap-3" data-grid={testid} style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(112px, 1fr))' }}>
      {cards.map((c) => {
        const on = mark(c)
        const can = pickable(c)
        const lines = labels(c)
        return (
          <div key={c.key} data-market-card={c.key} data-marked={on ? 'yes' : 'no'} data-spare={c.spare > 0 ? 'yes' : undefined} className="text-center" style={{ opacity: dim && !on ? 0.5 : 1 }}>
            <div style={{ display: 'inline-block', borderRadius: 10, outline: on ? `2px dashed ${ui.accent}` : 'none', outlineOffset: 3 }}>
              <Mini card={c} {...ui} width={104} count={c.tradeable > 1 ? c.tradeable : undefined}
                onClick={can ? () => onPick(c) : undefined} selected={picked.has(c.key) ? true : undefined} />
            </div>
            {lines.length > 0 && <div className="font-mono text-[10px] tracking-wide2 uppercase mt-1" style={{ color: ui.accent }} data-market-labels>{lines.join(' · ')}</div>}
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
  const [doublesOnly, setDoublesOnly] = useState(false)
  const navigate = useNavigate()
  useEffect(() => {
    setData(null); setErr(''); setGive(new Map()); setGet(new Map()); setDoublesOnly(false)
    api.availPublicMarketPlayer(token, pid).then(setData).catch((e) => setErr(e?.message || 'That player is not available.'))
  }, [token, pid])
  const ui = { club, accent, display, sponsor }
  const flip = (setter) => (card) => setter((m) => { const n = new Map(m); if (n.has(card.key)) n.delete(card.key); else n.set(card.key, card); return n })
  if (err) return <div data-market-player-error className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }}>{err} <Link to={`${basePath}/market`} className="underline">Back to the Market</Link></div>
  if (!data) return <div data-market-player-loading className="text-sm text-pb-faint">Loading…</div>
  const name = data.player.name
  const first = name.split(',').pop().trim() || name
  const mine = data.wants.filter((c) => c.mine).length
  const theirsOnList = data.theirs.filter((c) => c.on_my_list).length
  const rest = data.pile.length ? data.theirs.filter((c) => !c.piled) : data.theirs
  const restShown = doublesOnly ? rest.filter((c) => c.spare > 0) : rest
  const doubles = rest.filter((c) => c.spare > 0).length
  const start = () => navigate(`${basePath}/swaps/new`, { state: {
    ask: { player: data.player, cards: [...get.values()] },
    ...(give.size ? { giveList: [...give.values()].map((card) => ({ card, qty: 1 })) } : {}),
  } })
  const tags = (c) => [c.on_my_list && 'On your list', c.piled ? 'In pile' : c.spare > 0 && 'Double'].filter(Boolean)
  const btn = { padding: '11px 18px', borderRadius: 12, font: `700 12px ${MONO}`, letterSpacing: 1.3, textTransform: 'uppercase', background: accent, color: onColor(accent), border: 0 }
  const sub = [
    data.wants_private ? `${first} keeps their wish list private.` : mine > 0 ? `You hold ${mine} of the ${data.wants.length} cards they want.` : `They want ${data.wants.length} ${data.wants.length === 1 ? 'card' : 'cards'} and you hold none of them.`,
    theirsOnList > 0 ? `${theirsOnList} of the cards they could swap ${theirsOnList === 1 ? 'is' : 'are'} on your wish list.` : 'None of the cards they could swap are on your wish list.',
  ].join(' ')
  return (
    <div data-screen="market-player">
      <PageHead title={name} sub={sub} actions={<Link to={`${basePath}/market`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">Back to the Market</Link>} />
      {data.pile.length > 0 && (
        <>
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-1" data-pile-head>{first}'s pile ({data.pile.length})</h2>
          <p className="text-[12.5px] text-pb-dim mb-3">Spares {first} has flagged as happy to swap. Cards on your wish list are outlined. Tap any card to ask for it.</p>
          <div className="mb-8"><Grid cards={data.pile} picked={get} onPick={flip(setGet)} mark={(c) => c.on_my_list} labels={tags} pickable={() => true} ui={ui} testid="pile" /></div>
        </>
      )}
      {!data.wants_private && (
        <>
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-1" data-wants-head>What {first} wants ({data.wants.length})</h2>
          <p className="text-[12.5px] text-pb-dim mb-3">Cards you hold are outlined. Tap one to put it in the swap.</p>
          {data.wants.length === 0 ? <div className="text-sm text-pb-dim mb-6" data-no-their-wants>Nothing on their list right now.</div>
            : <div className="mb-8"><Grid cards={data.wants} picked={give} onPick={flip(setGive)} mark={(c) => c.mine} labels={(c) => (c.mine ? [`You have ${c.tradeable > 1 ? `×${c.tradeable}` : 'this'}`] : [])} pickable={(c) => c.mine} dim ui={ui} testid="wants" /></div>}
        </>
      )}
      <div className="flex items-center gap-3 flex-wrap mb-1">
        <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint" data-theirs-head>{data.pile.length ? `Everything else ${first} could swap` : `What ${first} could swap`} ({rest.length})</h2>
        {doubles > 0 && doubles < rest.length && (
          <button type="button" role="switch" aria-checked={doublesOnly} onClick={() => setDoublesOnly((v) => !v)} data-doubles-toggle
            className="px-3 py-1 rounded-full text-[12px] font-semibold border pb-hairline" style={doublesOnly ? { background: accent, color: onColor(accent), borderColor: accent } : undefined}>
            Doubles only <span style={{ opacity: 0.7 }}>{doubles}</span>
          </button>
        )}
      </div>
      <p className="text-[12.5px] text-pb-dim mb-3">Cards on your wish list are outlined, and a Double is a card {first} has a spare of. Tap any card to ask for it.</p>
      {rest.length === 0 ? <div className="text-sm text-pb-dim mb-6" data-no-their-cards>{data.pile.length ? 'Nothing else to swap.' : 'They have no cards to swap yet.'}</div>
        : <div className="mb-8"><Grid cards={restShown} picked={get} onPick={flip(setGet)} mark={(c) => c.on_my_list} labels={tags} pickable={() => true} ui={ui} testid="theirs" /></div>}
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
