// The club's whole set of cards, to look through without holding any of it and without starting a swap. It is the
// card book (CardGallery) with the server laying out each window of it: every player's card, then the special cards
// in stacks, searchable and sortable like your own. Each card says how many other players could swap a copy, and a
// card held up lists them, each with an Ask button that opens a swap request with that player and card chosen.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { onColor } from '../PlayerTradingCard'
import CardGallery from './CardGallery'

const MONO = "'JetBrains Mono', monospace"

function Holders({ token, card, accent, onAsk }) {
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
    </div>
  )
}

export default function CatalogueTab({ token, club, accent, display, sponsor, onAsk }) {
  const [state, setState] = useState({ items: [], total: 0, counts: {}, loading: true })
  const [err, setErr] = useState('')
  const seq = useRef(0)
  // Latest answer wins: a slow reply to an old search must not replace a newer one.
  const onQuery = useCallback(async (params) => {
    const n = ++seq.current
    setState((s) => ({ ...s, loading: true })); setErr('')
    try {
      const r = await api.availPublicCatalogue(token, params)
      if (n === seq.current) setState({ items: r.items, total: r.total, counts: r.counts, loading: false })
    } catch (e) {
      if (n === seq.current) { setState((s) => ({ ...s, loading: false })); setErr(e?.message || 'Could not load the cards.') }
    }
  }, [token])
  const remote = useMemo(() => ({ ...state, onQuery }), [state, onQuery])
  return (
    <div data-catalogue>
      <p style={{ fontSize: 13, opacity: 0.8, margin: '0 0 10px', lineHeight: 1.5 }}>
        Every card in the club, held or not. Hold one up to see who could swap you a copy.
      </p>
      {err && <div role="alert" data-catalogue-error style={{ fontSize: 13, color: '#fecaca', margin: '0 0 8px' }}>{err}</div>}
      <CardGallery remote={remote} club={club} accent={accent} display={display} sponsor={sponsor}
        viewerExtra={(card, close) => <Holders key={card.key} token={token} card={card} accent={accent} onAsk={(h) => { close(); onAsk({ player: { player_id: h.player_id, name: h.name }, card: { ...card, tradeable: h.tradeable } }) }} />} />
    </div>
  )
}
