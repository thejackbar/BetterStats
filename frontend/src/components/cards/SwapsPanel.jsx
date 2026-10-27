// Swapping cards with another player of the club. Any card a player holds can go (their own card stays theirs); a
// request is as many cards each way as the player likes (one for four, six for two), and nothing moves until the
// person asked says yes. The builder walks it through: who, which of their cards, which of yours, each a tap to
// add and a tap to take out again, with a count where a card is held more than once. The server checks it all
// again when the request is answered, and moves all of it or none of it, so a stale request is told so instead
// of taking a card that is no longer there.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { onColor } from '../PlayerTradingCard'
import { CardView, ScaledCard } from './CardFaces'
import { Modal } from './CardGallery'
import { TIERS } from './cardTheme'

const MONO = "'JetBrains Mono', monospace"
const btn = { padding: '9px 16px', borderRadius: 10, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', font: `700 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase' }

const cardLine = (c) => (c ? (c.kind === 'special' ? `${c.name}: ${c.title}` : `${c.name}, ${(TIERS[c.tier] || TIERS.common).label}`) : 'A card')
const totalOf = (list) => (list || []).reduce((n, c) => n + (c.qty || 1), 0)
// A side of a request in a sentence: the cards by name when there are one or two, else how many.
const sideLine = (list) => {
  if (!list || list.length === 0) return 'nothing'
  if (list.length <= 2) return list.map((c) => `${cardLine(c)}${(c.qty || 1) > 1 ? ` ×${c.qty}` : ''}`).join(' and ')
  return `${totalOf(list)} cards`
}
const ago = (iso) => {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`
}

function Mini({ card, club, accent, display, sponsor, selected, onClick, label, width = 104, count }) {
  const inner = <ScaledCard width={width}><CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} /></ScaledCard>
  const badge = (n) => n > 1 && <span data-card-count style={{ position: 'absolute', right: 4, bottom: '22%', padding: '1px 6px', borderRadius: 999, background: '#0b1018', border: '1px solid rgba(255,255,255,.5)', color: '#fff', font: `700 10px ${MONO}` }}>×{n}</span>
  if (!onClick) return <div style={{ position: 'relative' }} aria-label={label || cardLine(card)}>{inner}{badge(count)}</div>
  return (
    <button type="button" onClick={onClick} aria-pressed={!!selected} aria-label={label || cardLine(card)} data-swap-card={card.key}
      style={{ position: 'relative', padding: 0, border: 0, background: 'none', cursor: 'pointer', borderRadius: width * 0.08, outline: selected ? `3px solid ${accent}` : 'none', outlineOffset: 2, opacity: selected === false ? 0.55 : 1 }}>
      {inner}
      {badge(count ?? card.tradeable)}
      {selected && <span aria-hidden style={{ position: 'absolute', left: 4, top: 4, width: 20, height: 20, borderRadius: 10, background: accent, color: onColor(accent), font: `800 12px ${MONO}`, display: 'grid', placeItems: 'center' }}>✓</span>}
    </button>
  )
}

// A grid of cards to pick from, any number of them, with a search and a "show more" because a collection can
// run to hundreds. `chosen` is the map of what is picked so far (key to { card, qty }).
const PICK_PAGE = 24
function CardPick({ cards, chosen, onToggle, ui, label }) {
  const [q, setQ] = useState('')
  const [shown, setShown] = useState(PICK_PAGE)
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? cards.filter((c) => `${c.name} ${c.title || ''}`.toLowerCase().includes(needle)) : cards
  }, [cards, q])
  return (
    <div data-card-pick={label}>
      {cards.length > 8 && (
        <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PICK_PAGE) }} placeholder="Find a card" aria-label={`Find a card: ${label}`}
          style={{ width: '100%', boxSizing: 'border-box', marginBottom: 8, background: 'rgba(255,255,255,.08)', border: '1px solid rgba(255,255,255,.25)', borderRadius: 10, padding: '9px 12px', color: '#fff', fontSize: 15 }} />
      )}
      {list.length === 0 && <div style={{ fontSize: 13, opacity: 0.7 }}>No card matches.</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {list.slice(0, shown).map((c) => <Mini key={c.key} card={c} {...ui} selected={chosen.size ? chosen.has(c.key) : undefined} onClick={() => onToggle(c)} />)}
      </div>
      {list.length > shown && <button type="button" onClick={() => setShown((n) => n + PICK_PAGE)} style={{ ...btn, marginTop: 10 }}>Show more ({list.length - shown} left)</button>}
    </div>
  )
}

// What has been picked on one side, one line a card with a count to change (a card held three times can go
// once, twice or all three) and a way to take it back out.
function Tray({ chosen, onQty, onRemove, label }) {
  if (!chosen.size) return null
  const rows = [...chosen.values()]
  const total = rows.reduce((n, r) => n + r.qty, 0)
  const step = { width: 30, height: 30, borderRadius: 8, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', fontSize: 16, lineHeight: 1 }
  return (
    <div data-swap-tray={label} style={{ marginTop: 10, border: '1px solid rgba(255,255,255,.18)', borderRadius: 12, padding: '6px 10px' }}>
      <div style={{ font: `600 10px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', opacity: 0.7, padding: '4px 0' }}>{total} {total === 1 ? 'card' : 'cards'} picked</div>
      {rows.map(({ card, qty }) => (
        <div key={card.key} data-swap-picked={card.key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderTop: '1px solid rgba(255,255,255,.08)' }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13, overflowWrap: 'anywhere' }}>{cardLine(card)}</span>
          {card.tradeable > 1 && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <button type="button" aria-label={`Fewer: ${cardLine(card)}`} data-qty-down disabled={qty <= 1} onClick={() => onQty(card, qty - 1)} style={{ ...step, opacity: qty <= 1 ? 0.4 : 1 }}>−</button>
              <span data-qty style={{ minWidth: 38, textAlign: 'center', font: `700 12px ${MONO}` }}>{qty} of {card.tradeable}</span>
              <button type="button" aria-label={`More: ${cardLine(card)}`} data-qty-up disabled={qty >= card.tradeable} onClick={() => onQty(card, qty + 1)} style={{ ...step, opacity: qty >= card.tradeable ? 0.4 : 1 }}>+</button>
            </span>
          )}
          <button type="button" aria-label={`Take out: ${cardLine(card)}`} data-swap-remove onClick={() => onRemove(card)} style={{ ...step, fontSize: 13 }}>✕</button>
        </div>
      ))}
    </div>
  )
}

function Side({ cards, label, ...ui }) {
  return (
    <div data-swap-side={label}>
      <div style={{ font: `600 9.5px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', opacity: 0.7, marginBottom: 6 }}>{label} · {totalOf(cards)} {totalOf(cards) === 1 ? 'card' : 'cards'}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {cards.map((c) => <Mini key={c.key} card={c} {...ui} count={c.qty} width={cards.length > 3 ? 84 : 104} />)}
      </div>
    </div>
  )
}

function Request({ swap, ...ui }) {
  const incoming = swap.direction === 'in'
  return (
    <div data-swap-request={swap.id} style={{ border: '1px solid var(--pb-hairline, rgba(255,255,255,.2))', borderRadius: 14, padding: 12 }}>
      <div style={{ fontSize: 13, marginBottom: 8 }}>
        {incoming
          ? <><strong>{swap.other.name}</strong> wants to swap with you</>
          : <>Waiting for <strong>{swap.other.name}</strong></>}
        <span style={{ opacity: 0.6 }}> · {ago(swap.created_at)}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Side cards={swap.give} label={incoming ? 'You would get' : 'You give'} {...ui} />
        <div aria-hidden style={{ fontSize: 20, opacity: 0.7, textAlign: 'center' }}>⇅</div>
        <Side cards={swap.want} label={incoming ? 'You give' : 'You get'} {...ui} />
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        {incoming ? (
          <>
            <button type="button" disabled={ui.busy} onClick={() => ui.answer(swap.id, 'accept')} data-swap-accept style={{ ...btn, background: ui.accent, color: onColor(ui.accent), border: 0 }}>Accept</button>
            <button type="button" disabled={ui.busy} onClick={() => ui.answer(swap.id, 'decline')} data-swap-decline style={btn}>Decline</button>
          </>
        ) : (
          <button type="button" disabled={ui.busy} onClick={() => ui.answer(swap.id, 'cancel')} data-swap-cancel style={btn}>Cancel</button>
        )}
      </div>
    </div>
  )
}

function Builder({ token, board, give: preGive, club, accent, display, sponsor, onClose, onSent }) {
  const [player, setPlayer] = useState(null)
  const [theirs, setTheirs] = useState(null)
  const [want, setWant] = useState(() => new Map())
  const [give, setGive] = useState(() => {
    const held = preGive && (board.mine.find((c) => c.key === preGive.key) || { ...preGive, tradeable: 1 })
    return new Map(held ? [[held.key, { card: held, qty: 1 }]] : [])
  })
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const ui = { club, accent, display, sponsor }
  const people = useMemo(() => board.people.filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase())), [board.people, q])

  // Tap a card to add it (one copy), tap it again to take it out; the tray changes the count.
  const toggle = (set) => (card) => set((m) => {
    const next = new Map(m)
    if (next.has(card.key)) next.delete(card.key); else next.set(card.key, { card, qty: 1 })
    return next
  })
  const setQty = (set) => (card, qty) => set((m) => new Map(m).set(card.key, { card, qty: Math.max(1, Math.min(qty, card.tradeable || 1)) }))
  const remove = (set) => (card) => set((m) => { const next = new Map(m); next.delete(card.key); return next })
  const asList = (m) => [...m.values()].map((r) => ({ key: r.card.key, qty: r.qty }))

  const pick = async (p) => {
    setPlayer(p); setWant(new Map()); setTheirs(null); setErr('')
    try { setTheirs((await api.availPublicSwapPlayer(token, p.player_id)).cards) } catch (e) { setErr(e?.message || 'Could not load their cards.') }
  }
  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.availPublicAskSwap(token, { to_player_id: player.player_id, give: asList(give), want: asList(want) })
      onSent()
    } catch (e) {
      setErr(e?.message || 'Could not send that.')
    } finally { setBusy(false) }
  }
  const ready = !!player && want.size > 0 && give.size > 0
  const h = { font: `700 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.8, margin: '14px 0 8px' }
  return (
    <Modal label="Start a swap" onClose={onClose} zIndex={85}>
      <div data-swap-builder onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 560, padding: '52px 14px 28px', boxSizing: 'border-box', color: '#fff' }}>
        <button type="button" onClick={onClose} aria-label="Close" style={{ position: 'fixed', right: 14, top: 14, width: 38, height: 38, borderRadius: 19, border: '1px solid rgba(255,255,255,.3)', background: 'rgba(255,255,255,.08)', color: '#fff' }}>✕</button>
        <div style={{ font: `800 italic 26px ${display}`, textTransform: 'uppercase', letterSpacing: 1, textAlign: 'center' }}>Start a swap</div>
        <div style={{ textAlign: 'center', fontSize: 12.5, opacity: 0.75, marginTop: 4 }}>As many cards each way as you like: one for four, six for two. They have to say yes.</div>

        {board.mine.length === 0 && !preGive && <p data-no-doubles style={{ textAlign: 'center', marginTop: 18 }}>You have no cards to offer yet. Open a pack and whatever you pull can go in a swap. Your own card always stays yours.</p>}

        {(board.mine.length > 0 || preGive) && (
          <>
            <div style={h}>1. Who with</div>
            {player ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <strong>{player.name}</strong>
                <button type="button" onClick={() => { setPlayer(null); setWant(new Map()) }} style={{ ...btn, padding: '5px 10px' }}>Change</button>
              </div>
            ) : (
              <>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" aria-label="Find a player" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,.08)', border: '1px solid rgba(255,255,255,.25)', borderRadius: 10, padding: '10px 12px', color: '#fff', fontSize: 15 }} />
                <div style={{ marginTop: 8, maxHeight: 260, overflowY: 'auto', borderRadius: 10, border: '1px solid rgba(255,255,255,.18)' }}>
                  {people.length === 0 && <div style={{ padding: 14, fontSize: 13, opacity: 0.7 }}>{board.people.length ? 'No one by that name.' : 'No one has a card to swap yet.'}</div>}
                  {people.map((p) => (
                    <button key={p.player_id} type="button" onClick={() => pick(p)} data-swap-player={p.player_id} style={{ display: 'flex', width: '100%', justifyContent: 'space-between', padding: '11px 14px', background: 'none', border: 0, borderBottom: '1px solid rgba(255,255,255,.1)', color: '#fff', textAlign: 'left' }}>
                      <span>{p.name}</span><span style={{ opacity: 0.65, font: `600 11px ${MONO}` }}>{p.tradeable} {p.tradeable === 1 ? 'card' : 'cards'}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {player && (
          <>
            <div style={h}>2. The cards you want from {player.name}</div>
            {!theirs && !err && <div style={{ fontSize: 13, opacity: 0.7 }}>Loading…</div>}
            {theirs && theirs.length === 0 && <div style={{ fontSize: 13, opacity: 0.7 }}>They have no card to offer just now.</div>}
            {theirs && theirs.length > 0 && <CardPick cards={theirs} chosen={want} onToggle={toggle(setWant)} ui={ui} label="theirs" />}
            <Tray chosen={want} onQty={setQty(setWant)} onRemove={remove(setWant)} label="theirs" />
          </>
        )}

        {player && want.size > 0 && (
          <>
            <div style={h}>3. The cards you give{preGive ? ' (add more if you like)' : ''}</div>
            <CardPick cards={board.mine} chosen={give} onToggle={toggle(setGive)} ui={ui} label="yours" />
            <Tray chosen={give} onQty={setQty(setGive)} onRemove={remove(setGive)} label="yours" />
          </>
        )}

        {ready && (
          <div data-swap-confirm style={{ marginTop: 18, textAlign: 'center' }}>
            <div style={{ fontSize: 13, marginBottom: 10 }}>You give <strong>{totalOf([...give.values()])}</strong> for <strong>{totalOf([...want.values()])}</strong> from {player.name}.</div>
            <button type="button" disabled={busy} onClick={send} data-swap-send style={{ ...btn, padding: '12px 22px', background: accent, color: onColor(accent), border: 0 }}>{busy ? 'Sending…' : `Ask ${player.name}`}</button>
          </div>
        )}
        {err && <div role="alert" data-swap-error style={{ marginTop: 12, textAlign: 'center', color: '#fecaca', fontSize: 13 }}>{err}</div>}
      </div>
    </Modal>
  )
}

export default function SwapsPanel({ token, club, accent, display, sponsor, offer, onOfferDone, onChanged }) {
  const [board, setBoard] = useState(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [build, setBuild] = useState(false)

  const load = useCallback(() => api.availPublicSwaps(token).then((b) => { setBoard(b); return b }).catch(() => setFailed(true)), [token])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (offer) setBuild(true) }, [offer])

  const answer = async (id, action) => {
    setBusy(true); setMsg('')
    try {
      await api.availPublicAnswerSwap(token, id, action)
      setMsg(action === 'accept' ? 'Swapped. The new card is in your book.' : action === 'decline' ? 'Declined.' : 'Cancelled.')
      onChanged?.()
    } catch (e) {
      setMsg(e?.message || 'That did not work.')
    } finally {
      setBusy(false)
      load()
    }
  }

  if (failed) return <div className="text-sm text-pb-faint">Swaps could not load. Reload to try again.</div>
  if (!board) return <div className="text-sm text-pb-faint" data-swaps-loading>Loading swaps…</div>
  const ui = { club, accent, display, sponsor, busy, answer }
  const offerable = board.mine.reduce((n, c) => n + c.tradeable, 0)
  return (
    <div data-swaps-panel>
      <p style={{ fontSize: 13, opacity: 0.8, margin: '0 0 10px', lineHeight: 1.5 }}>
        Swap any cards you hold for any cards another player holds, as many each way as you like. Nothing moves until the other player says yes, and they can say no. Your own card always stays yours. Requests lapse after {board.expires_days} days.
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <button type="button" onClick={() => setBuild(true)} data-swap-start style={{ ...btn, padding: '11px 18px', background: accent, color: onColor(accent), border: 0 }}>Start a swap</button>
        <span data-doubles-count style={{ font: `600 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', opacity: 0.75 }}>{offerable === 0 ? 'No cards to offer yet' : `${offerable} ${offerable === 1 ? 'card' : 'cards'} you could offer`}</span>
      </div>
      {msg && <div role="status" data-swap-msg style={{ fontSize: 13, marginBottom: 10 }}>{msg}</div>}

      {board.incoming.length > 0 && <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', margin: '4px 0 8px', color: 'var(--pb-amber, #fbbf24)' }}>Asking you ({board.incoming.length})</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{board.incoming.map((s) => <Request key={s.id} swap={s} {...ui} />)}</div>
      {board.outgoing.length > 0 && <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', margin: '16px 0 8px', opacity: 0.8 }}>You asked ({board.outgoing.length})</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{board.outgoing.map((s) => <Request key={s.id} swap={s} {...ui} />)}</div>
      {board.incoming.length + board.outgoing.length === 0 && <div style={{ fontSize: 13, opacity: 0.7 }} data-no-requests>No swap requests open.</div>}

      {board.recent.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.8, marginBottom: 6 }}>Lately</div>
          {board.recent.map((s) => (
            <div key={s.id} data-swap-recent style={{ fontSize: 12.5, opacity: 0.8, padding: '4px 0' }}>
              {s.status === 'accepted' ? 'Swapped with' : s.status === 'declined' ? (s.direction === 'out' ? 'Declined by' : 'You declined') : 'Cancelled with'} <strong>{s.other.name}</strong>: {sideLine(s.give)} for {sideLine(s.want)} · {ago(s.resolved_at || s.created_at)}
            </div>
          ))}
        </div>
      )}

      {build && <Builder token={token} board={board} give={offer || null} club={club} accent={accent} display={display} sponsor={sponsor}
        onClose={() => { setBuild(false); onOfferDone?.() }}
        onSent={() => { setBuild(false); onOfferDone?.(); setMsg('Swap request sent.'); load(); onChanged?.() }} />}
    </div>
  )
}
