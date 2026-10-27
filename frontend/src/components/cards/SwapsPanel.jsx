// Swapping cards with another player of the club. Any card a player holds can go (their own card stays theirs); a
// request is one card for one card, and nothing moves until the person asked says yes. The builder walks it through
// in three taps: who, which of their cards, which of yours. The server checks it all again when the request is
// answered, so a stale request is told so instead of taking a card that is no longer there.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { onColor } from '../PlayerTradingCard'
import { CardView, ScaledCard } from './CardFaces'
import { Modal } from './CardGallery'
import { TIERS } from './cardTheme'

const MONO = "'JetBrains Mono', monospace"
const btn = { padding: '9px 16px', borderRadius: 10, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', font: `700 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase' }

const cardLine = (c) => (c ? (c.kind === 'special' ? `${c.name}: ${c.title}` : `${c.name}, ${(TIERS[c.tier] || TIERS.common).label}`) : 'A card')
const ago = (iso) => {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`
}

function Mini({ card, club, accent, display, sponsor, selected, onClick, label, width = 104 }) {
  const inner = <ScaledCard width={width}><CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} /></ScaledCard>
  if (!onClick) return <div style={{ position: 'relative' }} aria-label={label || cardLine(card)}>{inner}</div>
  return (
    <button type="button" onClick={onClick} aria-pressed={!!selected} aria-label={label || cardLine(card)} data-swap-card={card.key}
      style={{ position: 'relative', padding: 0, border: 0, background: 'none', cursor: 'pointer', borderRadius: width * 0.08, outline: selected ? `3px solid ${accent}` : 'none', outlineOffset: 2, opacity: selected === false ? 0.55 : 1 }}>
      {inner}
      {card.tradeable > 1 && <span style={{ position: 'absolute', right: 4, bottom: '22%', padding: '1px 6px', borderRadius: 999, background: '#0b1018', border: '1px solid rgba(255,255,255,.5)', color: '#fff', font: `700 10px ${MONO}` }}>×{card.tradeable}</span>}
    </button>
  )
}

// A grid of cards to pick one from, with a search and a "show more", because a collection can run to hundreds.
const PICK_PAGE = 24
function CardPick({ cards, selectedKey, onPick, ui, label }) {
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
        {list.slice(0, shown).map((c) => <Mini key={c.key} card={c} {...ui} selected={selectedKey ? selectedKey === c.key : undefined} onClick={() => onPick(c)} />)}
      </div>
      {list.length > shown && <button type="button" onClick={() => setShown((n) => n + PICK_PAGE)} style={{ ...btn, marginTop: 10 }}>Show more ({list.length - shown} left)</button>}
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <div style={{ textAlign: 'center' }}>
          <Mini card={swap.give} {...ui} />
          <div style={{ font: `600 9.5px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', opacity: 0.7, marginTop: 4 }}>{incoming ? 'You would get' : 'You give'}</div>
        </div>
        <span aria-hidden style={{ fontSize: 22, opacity: 0.7 }}>⇄</span>
        <div style={{ textAlign: 'center' }}>
          <Mini card={swap.want} {...ui} />
          <div style={{ font: `600 9.5px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', opacity: 0.7, marginTop: 4 }}>{incoming ? 'You give' : 'You get'}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginLeft: 'auto' }}>
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
    </div>
  )
}

function Builder({ token, board, give: preGive, club, accent, display, sponsor, onClose, onSent }) {
  const [player, setPlayer] = useState(null)
  const [theirs, setTheirs] = useState(null)
  const [want, setWant] = useState(null)
  const [give, setGive] = useState(preGive || null)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const ui = { club, accent, display, sponsor }
  const people = useMemo(() => board.people.filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase())), [board.people, q])

  const pick = async (p) => {
    setPlayer(p); setWant(null); setTheirs(null); setErr('')
    try { setTheirs((await api.availPublicSwapPlayer(token, p.player_id)).cards) } catch (e) { setErr(e?.message || 'Could not load their cards.') }
  }
  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.availPublicAskSwap(token, { to_player_id: player.player_id, give_key: give.key, want_key: want.key })
      onSent()
    } catch (e) {
      setErr(e?.message || 'Could not send that.')
    } finally { setBusy(false) }
  }
  const step = !player ? 1 : !want ? 2 : !give ? 3 : 4
  const h = { font: `700 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.8, margin: '14px 0 8px' }
  return (
    <Modal label="Start a swap" onClose={onClose} zIndex={85}>
      <div data-swap-builder onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 560, padding: '52px 14px 28px', boxSizing: 'border-box', color: '#fff' }}>
        <button type="button" onClick={onClose} aria-label="Close" style={{ position: 'fixed', right: 14, top: 14, width: 38, height: 38, borderRadius: 19, border: '1px solid rgba(255,255,255,.3)', background: 'rgba(255,255,255,.08)', color: '#fff' }}>✕</button>
        <div style={{ font: `800 italic 26px ${display}`, textTransform: 'uppercase', letterSpacing: 1, textAlign: 'center' }}>Start a swap</div>
        <div style={{ textAlign: 'center', fontSize: 12.5, opacity: 0.75, marginTop: 4 }}>One of your cards for one of theirs. They have to say yes.</div>

        {board.mine.length === 0 && !preGive && <p data-no-doubles style={{ textAlign: 'center', marginTop: 18 }}>You have no cards to offer yet. Open a pack and whatever you pull can go in a swap. Your own card always stays yours.</p>}

        {(board.mine.length > 0 || preGive) && (
          <>
            <div style={h}>1. Who with</div>
            {player ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <strong>{player.name}</strong>
                <button type="button" onClick={() => { setPlayer(null); setWant(null) }} style={{ ...btn, padding: '5px 10px' }}>Change</button>
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
            <div style={h}>2. The card you want</div>
            {!theirs && !err && <div style={{ fontSize: 13, opacity: 0.7 }}>Loading…</div>}
            {theirs && theirs.length === 0 && <div style={{ fontSize: 13, opacity: 0.7 }}>They have no card to offer just now.</div>}
            {theirs && theirs.length > 0 && <CardPick cards={theirs} selectedKey={want?.key} onPick={setWant} ui={ui} label="theirs" />}
          </>
        )}

        {player && want && !preGive && (
          <>
            <div style={h}>3. The card you give</div>
            <CardPick cards={board.mine} selectedKey={give?.key} onPick={setGive} ui={ui} label="yours" />
          </>
        )}

        {step === 4 && (
          <div data-swap-confirm style={{ marginTop: 18, textAlign: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
              <div><Mini card={give} {...ui} /><div style={{ font: `600 9.5px ${MONO}`, textTransform: 'uppercase', opacity: 0.7, marginTop: 4 }}>You give</div></div>
              <span aria-hidden style={{ fontSize: 24 }}>⇄</span>
              <div><Mini card={want} {...ui} /><div style={{ font: `600 9.5px ${MONO}`, textTransform: 'uppercase', opacity: 0.7, marginTop: 4 }}>You get</div></div>
            </div>
            <button type="button" disabled={busy} onClick={send} data-swap-send style={{ ...btn, marginTop: 16, padding: '12px 22px', background: accent, color: onColor(accent), border: 0 }}>{busy ? 'Sending…' : `Ask ${player.name}`}</button>
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
        Swap any card you hold for any card another player holds. Nothing moves until the other player says yes, and they can say no. Your own card always stays yours. Requests lapse after {board.expires_days} days.
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
              {s.status === 'accepted' ? 'Swapped with' : s.status === 'declined' ? (s.direction === 'out' ? 'Declined by' : 'You declined') : 'Cancelled with'} <strong>{s.other.name}</strong>: {cardLine(s.give)} for {cardLine(s.want)} · {ago(s.resolved_at || s.created_at)}
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
