// One card on a page of its own, at /playerdash/:token/cards/card/:key: the card (turn it over), who could swap one, whether you
// have it, the wish list button, and a link you can send. Anyone signed in to the club's cards can open it; it shows nothing about
// anyone's collection beyond who could swap a copy.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import FlipCard from '../../components/FlipCard'
import { onColor } from '../../components/PlayerTradingCard'
import { api } from '../../lib/api'
import { CARD_H, CARD_W, CardInfoBack, CardView } from '../../components/cards/CardFaces'
import { TIERS } from '../../components/cards/cardTheme'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

export default function CardPage() {
  const { key } = useParams()
  const { token, club, accent, display, sponsor, basePath, wants, toggleWant } = usePC()
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const [flipped, setFlipped] = useState(false)
  const [note, setNote] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    let live = true
    setRes(null); setErr(''); setFlipped(false)
    api.availPublicCard(token, key).then((r) => { if (live) setRes(r) }).catch((e) => { if (live) setErr(e?.message || 'That card could not be found.') })
    return () => { live = false }
  }, [token, key])
  if (err) return <div data-card-page-error className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }}>{err} <Link to={`${basePath}/club`} className="underline">Back to Club cards</Link></div>
  if (!res) return <div className="text-sm text-pb-faint" data-card-page-loading>Loading the card…</div>
  const card = res.card
  const W = 320, k = W / CARD_W
  const onList = wants.keys.has(card.key)
  const tier = TIERS[card.tier] || TIERS.common
  const copy = async () => {
    try { await navigator.clipboard.writeText(`${window.location.origin}${basePath}/card/${encodeURIComponent(card.key)}`); setNote('Link copied. Anyone in the club can open it with their PIN.') } catch { setNote('Copy the address from your browser.') }
  }
  const ask = (h) => navigate(`${basePath}/swaps/new`, { state: { ask: { player: { player_id: h.player_id, name: h.name }, card: { ...card, tradeable: h.tradeable } } } })
  return (
    <div data-screen="card">
      <PageHead title={card.kind === 'special' ? card.title : card.name} sub={card.kind === 'special' ? `${card.name}, special card` : `${tier.label} card`}
        actions={<Link to={`${basePath}/club`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">Club cards</Link>} />
      <div className="flex flex-wrap gap-8 items-start">
        <div style={{ flex: 'none', margin: '0 auto' }}>
          <div style={{ width: W, height: CARD_H * k }} data-card-page-card>
            <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${k})`, transformOrigin: 'top left' }}>
              <FlipCard width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped((f) => !f)}
                label={flipped ? 'Showing the details. Turn the card back over' : 'Showing the card. Turn it over for the details'}
                front={<CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} />}
                back={<CardInfoBack card={card} club={club} accent={accent} display={display} />} />
            </div>
          </div>
          <div className="text-center mt-2" style={{ font: `600 10px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.65 }}>Tap the card to turn it over</div>
        </div>
        <div className="flex-1 min-w-[260px]">
          {res.mine_copies > 0 && <div data-you-have className="rounded-xl border pb-hairline bg-pb-surface px-4 py-3 mb-3 text-sm">You have {res.mine_copies === 1 ? 'this card' : `${res.mine_copies} of this card`}.</div>}
          {card.kind === 'player' && (
            <div className="rounded-xl border pb-hairline bg-pb-surface px-4 py-3 mb-3 text-sm" data-card-rarity>
              <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint block mb-1">Rarity</span>
              <strong style={{ color: tier.ink }}>{tier.label}</strong> · {card.rarity} out of 99. <Link to={`${basePath}/how`} className="underline">How rarity works</Link>
            </div>
          )}
          <div className="rounded-xl border pb-hairline bg-pb-surface p-4 mb-3" data-card-holders>
            <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mb-2">Who could swap one</div>
            {res.holders.length === 0 && <div className="text-sm text-pb-dim">Nobody has pulled this one yet, or they are keeping it.</div>}
            {res.holders.map((h) => (
              <div key={h.player_id} data-holder={h.player_id} className="flex items-center gap-3 py-1.5 border-t pb-hairline first:border-t-0">
                <span className="flex-1 min-w-0" style={{ overflowWrap: 'anywhere' }}>{h.name}{h.tradeable > 1 && <span className="text-pb-faint"> ×{h.tradeable}</span>}</span>
                <button type="button" data-holder-ask={h.player_id} onClick={() => ask(h)} style={{ padding: '7px 14px', borderRadius: 10, border: 0, background: accent, color: onColor(accent), font: `700 11px ${MONO}`, letterSpacing: 1.1, textTransform: 'uppercase' }}>Ask</button>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {res.mine_copies === 0 && (
              <button type="button" onClick={() => toggleWant(card).then(() => setRes((r) => ({ ...r, wanted: !onList })))} data-want-toggle aria-pressed={onList}
                className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold" style={onList ? { background: accent, color: onColor(accent), borderColor: accent } : undefined}>
                {onList ? 'On my wish list' : 'Add to wish list'}
              </button>
            )}
            <button type="button" onClick={copy} data-copy-link className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">Copy link to this card</button>
          </div>
          {note && <div role="status" className="text-[13px] text-pb-dim mt-2" data-copy-note>{note}</div>}
        </div>
      </div>
    </div>
  )
}
