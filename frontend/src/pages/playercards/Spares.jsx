// Spares: the cards a player holds more of than they keep, in one place. Pick several and offer them to someone in one go, and
// mark the ones they are open to swapping, which tells them how many players want each (a number, never names).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import CardGallery from '../../components/cards/CardGallery'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

export default function Spares() {
  const { token, club, accent, display, sponsor, basePath } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [picked, setPicked] = useState(() => new Map())
  const [err, setErr] = useState('')
  const navigate = useNavigate()
  const read = useCallback(() => api.availPublicSpares(token).then((d) => { setData(d); setFailed(false) }).catch(() => setFailed(true)), [token])
  useEffect(() => { read() }, [read])
  const toggle = (card) => setPicked((m) => {
    const next = new Map(m)
    if (next.has(card.key)) next.delete(card.key); else next.set(card.key, { card, qty: 1 })
    return next
  })
  const setQty = (card, qty) => setPicked((m) => new Map(m).set(card.key, { card, qty: Math.max(1, Math.min(qty, card.spare || 1)) }))
  const marked = useMemo(() => new Set(picked.keys()), [picked])
  const setOpen = async (card, on) => {
    setErr('')
    try { await api.availPublicSetSpareOpen(token, card.key, on); await read() } catch (e) { setErr(e?.message || 'That did not work.') }
  }
  if (failed) return <div className="text-sm text-pb-faint" data-spares-failed>Your spares could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-spares-loading>Loading your spares…</div>
  const chosen = [...picked.values()]
  const offer = () => navigate(`${basePath}/swaps/new`, { state: { giveList: chosen.map(({ card, qty }) => ({ card, qty })) } })
  const btn = { padding: '11px 18px', borderRadius: 12, font: `700 12px ${MONO}`, letterSpacing: 1.3, textTransform: 'uppercase' }
  return (
    <div data-screen="spares">
      <PageHead title="Spares" sub="A spare is a copy beyond the one you keep. Tick the ones you are happy to move and offer them to someone." />
      {data.cards.length === 0 ? (
        <div data-no-spares className="rounded-2xl border pb-hairline bg-pb-surface p-6 text-pb-dim">You have no spares yet. When you pull a card you already hold, the extra copy turns up here.</div>
      ) : (
        <>
          <div className="text-[12px] font-mono tracking-wide2 uppercase text-pb-faint mb-3" data-spares-total>{data.total} {data.total === 1 ? 'spare' : 'spares'} across {data.cards.length} {data.cards.length === 1 ? 'card' : 'cards'}</div>
          <CardGallery browse cards={data.cards} club={club} accent={accent} display={display} sponsor={sponsor} marked={marked}
            onAction={toggle} actionLabel={(c) => (picked.has(c.key) ? 'Take out of this offer' : 'Add to an offer')} />
          {chosen.length > 0 && (
            <div data-spares-offer className="rounded-2xl border pb-hairline bg-pb-surface p-4 mt-4" style={{ position: 'sticky', bottom: 80 }}>
              <div className="text-sm font-semibold mb-2">{chosen.reduce((n, r) => n + r.qty, 0)} {chosen.reduce((n, r) => n + r.qty, 0) === 1 ? 'card' : 'cards'} picked</div>
              {chosen.map(({ card, qty }) => (
                <div key={card.key} className="flex items-center gap-2 text-sm py-1" data-spare-picked={card.key}>
                  <span className="flex-1 min-w-0" style={{ overflowWrap: 'anywhere' }}>{cardLine(card)}</span>
                  {card.spare > 1 && (
                    <span className="inline-flex items-center gap-1">
                      <button type="button" aria-label={`Fewer: ${cardLine(card)}`} disabled={qty <= 1} onClick={() => setQty(card, qty - 1)} className="w-7 h-7 rounded border pb-hairline">−</button>
                      <span className="font-mono text-xs w-12 text-center">{qty} of {card.spare}</span>
                      <button type="button" aria-label={`More: ${cardLine(card)}`} disabled={qty >= card.spare} onClick={() => setQty(card, qty + 1)} className="w-7 h-7 rounded border pb-hairline">+</button>
                    </span>
                  )}
                </div>
              ))}
              <button type="button" onClick={offer} data-spares-offer-go style={{ ...btn, background: accent, color: onColor(accent), marginTop: 10 }}>Offer these to someone</button>
            </div>
          )}
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mt-8 mb-1">Open to offers</h2>
          <p className="text-sm text-pb-dim mb-3 max-w-prose">Switch it on for a spare and you will see how many other players want that card. They are never named, and nobody is told you are open.</p>
          {err && <div role="alert" className="text-sm mb-2" style={{ color: 'var(--pb-red, #f87171)' }}>{err}</div>}
          <div className="flex flex-col gap-2" data-open-list>
            {data.cards.map((c) => (
              <div key={c.key} data-open-row={c.key} className="flex items-center gap-3 rounded-xl border pb-hairline bg-pb-surface p-2.5">
                <Mini card={c} club={club} accent={accent} display={display} sponsor={sponsor} width={52} count={1} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold" style={{ overflowWrap: 'anywhere' }}>{cardLine(c)}</div>
                  <div className="text-[12.5px] text-pb-dim" data-open-note>
                    {c.spare} {c.spare === 1 ? 'spare' : 'spares'}{c.open ? ` · ${c.wanted_by} ${c.wanted_by === 1 ? 'player wants' : 'players want'} this card` : ''}
                  </div>
                </div>
                <label className="inline-flex items-center gap-2 text-sm shrink-0">
                  <input type="checkbox" checked={c.open} onChange={(e) => setOpen(c, e.target.checked)} data-open-toggle={c.key} className="w-5 h-5" />
                  <span>Open</span>
                </label>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
