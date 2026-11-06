// The club's whole set of cards, to look through without holding any of it and without starting a swap. It is the
// card book (CardGallery) with the server laying out each window of it: every player's card, then the special cards
// in stacks, searchable and sortable like your own. Each card says how many other players could swap a copy, and a
// card held up lists them, each with an Ask button that opens a swap request with that player and card chosen.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../PlayerTradingCard'
import CardGallery from './CardGallery'
import CardPanel from './CardPanel'

const MONO = "'JetBrains Mono', monospace"

function Holders({ token, card, accent, onAsk, wants, onToggleWant, cardHref }) {
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let live = true
    setRes(null); setErr('')
    api.availPublicCatalogueHolders(token, card.key).then((r) => { if (live) setRes(r) }).catch((e) => { if (live) setErr(e?.message || 'Could not look that up.') })
    return () => { live = false }
  }, [token, card.key])
  const box = { border: '1px solid rgba(255,255,255,.22)', borderRadius: 12, padding: 12, background: 'rgba(255,255,255,.05)', color: '#fff', textAlign: 'left' }
  if (err) return <div role="alert" style={{ ...box, color: '#fecaca', fontSize: 13 }}>{err}</div>
  if (!res) return <div style={{ ...box, fontSize: 13, opacity: 0.8 }}>Looking for who has it…</div>
  return (
    <div data-holders style={box}>
      {res.mine_copies > 0 && <div data-you-have style={{ fontSize: 13, marginBottom: 8 }}>You have {res.mine_copies === 1 ? 'this card' : `${res.mine_copies} of this card`}.</div>}
      <div style={{ font: `700 10.5px ${MONO}`, letterSpacing: 1.3, textTransform: 'uppercase', opacity: 0.8, marginBottom: 6 }}>Who could swap one</div>
      {res.holders.length === 0 && <div data-no-holders style={{ fontSize: 13, opacity: 0.85 }}>Nobody has pulled this one yet, or they are keeping it.</div>}
      {res.holders.map((h) => (
        <div key={h.player_id} data-holder={h.player_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderTop: '1px solid rgba(255,255,255,.1)' }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 14, overflowWrap: 'anywhere' }}>{h.name}{h.tradeable > 1 && <span style={{ opacity: 0.65 }}> ×{h.tradeable}</span>}</span>
          <button type="button" data-holder-ask={h.player_id} onClick={() => onAsk(h)}
            style={{ padding: '7px 14px', borderRadius: 10, border: 0, background: accent, color: onColor(accent), font: `700 11px ${MONO}`, letterSpacing: 1.1, textTransform: 'uppercase' }}>Ask</button>
        </div>
      ))}
      {(onToggleWant || cardHref) && (
        <div className="flex flex-wrap gap-2 mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,.1)' }}>
          {onToggleWant && res.mine_copies === 0 && (
            <button type="button" data-want-toggle aria-pressed={wants?.has(card.key)} onClick={() => onToggleWant(card)}
              style={{ padding: '7px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,.35)', background: wants?.has(card.key) ? accent : 'rgba(255,255,255,.08)', color: wants?.has(card.key) ? onColor(accent) : '#fff', font: `700 11px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase' }}>
              {wants?.has(card.key) ? 'On my wish list' : 'Add to wish list'}
            </button>
          )}
          {cardHref && <Link to={cardHref(card)} data-card-page-link style={{ padding: '7px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,.35)', color: '#fff', font: `700 11px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', textDecoration: 'none' }}>Card page</Link>}
        </div>
      )}
    </div>
  )
}

// A wide screen has room for the card beside the book; anything narrower holds it up over the book.
function useWide(min = 1360) {
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.innerWidth >= min)
  useEffect(() => {
    const fit = () => setWide(window.innerWidth >= min)
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [min])
  return wide
}

export default function CatalogueTab({ token, club, accent, display, sponsor, onAsk, intro = true, panel = false, wants, onToggleWant, cardHref, setKey }) {
  const wide = useWide()
  const [held, setHeld] = useState(null)
  const [state, setState] = useState({ items: [], total: 0, counts: {}, loading: true })
  const [err, setErr] = useState('')
  const seq = useRef(0)
  // Latest answer wins: a slow reply to an old search must not replace a newer one.
  const onQuery = useCallback(async (params) => {
    const n = ++seq.current
    setState((s) => ({ ...s, loading: true })); setErr('')
    try {
      const r = await api.availPublicCatalogue(token, setKey ? { ...params, set: setKey } : params)
      if (n === seq.current) setState({ items: r.items, total: r.total, counts: r.counts, loading: false })
    } catch (e) {
      if (n === seq.current) { setState((s) => ({ ...s, loading: false })); setErr(e?.message || 'Could not load the cards.') }
    }
  }, [token, setKey])
  const remote = useMemo(() => ({ ...state, onQuery }), [state, onQuery])
  const holders = (card, close) => <Holders key={card.key} token={token} card={card} accent={accent} wants={wants} onToggleWant={onToggleWant} cardHref={cardHref} onAsk={(h) => { close(); onAsk({ player: { player_id: h.player_id, name: h.name }, card: { ...card, tradeable: h.tradeable } }) }} />
  return (
    <div data-catalogue>
      {intro && (
        <p style={{ fontSize: 13, opacity: 0.8, margin: '0 0 10px', lineHeight: 1.5 }}>
          Every card in the club, held or not. Hold one up to see who could swap you a copy.
        </p>
      )}
      {err && <div role="alert" data-catalogue-error style={{ fontSize: 13, color: '#fecaca', margin: '0 0 8px' }}>{err}</div>}
      <div data-catalogue-layout style={panel && wide ? { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 340px', gap: 24, alignItems: 'start' } : undefined}>
        <CardGallery remote={remote} club={club} accent={accent} display={display} sponsor={sponsor} onHold={panel && wide ? setHeld : undefined}
          viewerExtra={(card, close) => holders(card, close)} />
        {panel && wide && (held
          ? <CardPanel card={held} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => setHeld(null)} extra={holders(held, () => setHeld(null))} />
          : <aside data-card-panel-empty className="rounded-2xl border pb-hairline p-5 text-sm text-pb-dim" style={{ position: 'sticky', top: 16 }}>Tap a card to hold it up here, turn it over, and see who could swap you a copy.</aside>)}
      </div>
    </div>
  )
}
