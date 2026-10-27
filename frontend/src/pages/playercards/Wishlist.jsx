// The wish list: the cards a player is after, and who could swap each one right now. Private to the player: nobody else is
// told what is on it. A card someone could swap is a button away from a request for it.
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

function WantRow({ w, ui, onAsk, onRemove, cardHref }) {
  return (
    <div data-want={w.key} className="flex gap-4 items-start rounded-2xl border pb-hairline bg-pb-surface p-3">
      <Link to={cardHref} aria-label={`Open the card page: ${cardLine(w)}`}><Mini card={w} {...ui} width={88} count={1} /></Link>
      <div className="min-w-0 flex-1">
        <Link to={cardHref} className="font-semibold hover:underline" style={{ overflowWrap: 'anywhere' }}>{cardLine(w)}</Link>
        {w.holders.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 mt-2" data-want-holders>
            {w.holders.map((h) => (
              <button key={h.player_id} type="button" data-want-ask={h.player_id} onClick={() => onAsk(w, h)}
                style={{ padding: '7px 12px', borderRadius: 10, border: 0, background: ui.accent, color: onColor(ui.accent), font: `700 12px ${MONO}`, letterSpacing: 0.4 }}>
                Ask {h.name}{h.tradeable > 1 ? ` (×${h.tradeable})` : ''}
              </button>
            ))}
          </div>
        ) : <div className="text-sm text-pb-dim mt-1.5">Nobody has one to swap yet. You will get an email when someone does, if you have those switched on.</div>}
        <button type="button" onClick={() => onRemove(w)} data-want-remove className="text-[12.5px] text-pb-faint underline mt-2">Take off my list</button>
      </div>
    </div>
  )
}

export default function Wishlist() {
  const { token, club, accent, display, sponsor, basePath, loadWants } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const navigate = useNavigate()
  const read = useCallback(() => api.availPublicWants(token).then((d) => { setData(d); setFailed(false) }).catch(() => setFailed(true)), [token])
  useEffect(() => { read() }, [read])
  if (failed) return <div className="text-sm text-pb-faint" data-wants-failed>Your wish list could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-wants-loading>Loading your wish list…</div>
  const ui = { club, accent, display, sponsor }
  const ready = data.wants.filter((w) => w.holders.length > 0)
  const waiting = data.wants.filter((w) => w.holders.length === 0)
  const remove = async (w) => { await api.availPublicRemoveWant(token, w.key); await read(); loadWants() }
  const ask = (w, h) => navigate(`${basePath}/swaps/new`, { state: { ask: { player: { player_id: h.player_id, name: h.name }, card: { ...w, tradeable: h.tradeable } } } })
  const href = (w) => `${basePath}/card/${encodeURIComponent(w.key)}`
  return (
    <div data-screen="wishlist">
      <PageHead title="Wish list" sub="Cards you are after. Only you can see this list. When someone could swap you one, you can ask them from here."
        actions={<Link to={`${basePath}/club`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">Find cards to add</Link>} />
      {data.wants.length === 0 && (
        <div data-no-wants className="rounded-2xl border pb-hairline bg-pb-surface p-6 text-pb-dim">
          <p className="mb-2">Nothing on your list yet.</p>
          <p className="text-sm">Open any card in <Link to={`${basePath}/club`} className="underline">Club cards</Link> and choose Add to wish list.</p>
        </div>
      )}
      {ready.length > 0 && (
        <>
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2" data-want-ready>Someone could swap you these ({ready.length})</h2>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))' }}>
            {ready.map((w) => <WantRow key={w.key} w={w} ui={ui} onAsk={ask} onRemove={remove} cardHref={href(w)} />)}
          </div>
        </>
      )}
      {waiting.length > 0 && (
        <>
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2" data-want-waiting>Still looking ({waiting.length})</h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))' }}>
            {waiting.map((w) => <WantRow key={w.key} w={w} ui={ui} onAsk={ask} onRemove={remove} cardHref={href(w)} />)}
          </div>
        </>
      )}
      <p className="text-[12.5px] text-pb-faint mt-6">{data.wants.length} of {data.limit} places used.</p>
    </div>
  )
}
