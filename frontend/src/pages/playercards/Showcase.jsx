// Showcase: up to six cards to pin up. The club sees them on the collectors board; only cards you hold can be pinned, and one you
// swap away drops off by itself.
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import CardGallery from '../../components/cards/CardGallery'
import { cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

export default function Showcase() {
  const { token, data, club, accent, display, sponsor } = usePC()
  const [pinned, setPinned] = useState(null) // the keys, in order
  const [max, setMax] = useState(6)
  const [saved, setSaved] = useState(true)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  useEffect(() => { api.availPublicShowcase(token).then((r) => { setPinned(r.cards.map((c) => c.key)); setMax(r.max) }).catch(() => setErr('Your showcase could not load. Reload to try again.')) }, [token])
  const mine = useMemo(() => (data?.cards || []).map((c) => ({ ...c, tradeable: c.copies || 1 })), [data])
  const byKey = useMemo(() => new Map(mine.map((c) => [c.key, c])), [mine])
  if (err) return <div className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }} role="alert">{err}</div>
  if (!pinned || !data) return <div className="text-sm text-pb-faint" data-showcase-loading>Loading…</div>
  const toggle = (card) => {
    setMsg(''); setSaved(false)
    setPinned((keys) => (keys.includes(card.key) ? keys.filter((k) => k !== card.key) : keys.length >= max ? keys : [...keys, card.key]))
  }
  const move = (i, d) => {
    const next = [...pinned]; const j = i + d
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    setPinned(next); setSaved(false); setMsg('')
  }
  const save = async () => {
    setErr(''); setMsg('')
    try { await api.availPublicPutShowcase(token, pinned); setSaved(true); setMsg('Saved. The club can see these on the collectors board.') } catch (e) { setErr(e?.message || 'That did not save. Try again.') }
  }
  const btn = { padding: '9px 14px', borderRadius: 10, border: '1px solid var(--pb-hairline, rgba(255,255,255,.3))', font: `700 11px ${MONO}`, letterSpacing: 1.1, textTransform: 'uppercase' }
  return (
    <div data-screen="showcase">
      <PageHead title="Showcase" sub={`Pin up to ${max} cards you are proud of. The club sees them next to your name on the collectors board.`}
        actions={<button type="button" onClick={save} disabled={saved} data-showcase-save style={{ ...btn, background: saved ? undefined : accent, color: saved ? undefined : onColor(accent), opacity: saved ? 0.6 : 1 }}>Save showcase</button>} />
      {msg && <div role="status" className="text-sm mb-3" data-showcase-msg>{msg}</div>}
      <div className="rounded-2xl border pb-hairline bg-pb-surface p-4 mb-5" data-showcase-pinned>
        <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mb-2">{pinned.length} of {max} pinned</div>
        {pinned.length === 0 && <div className="text-sm text-pb-dim">Nothing pinned. Tap the plus on a card below.</div>}
        {pinned.map((k, i) => (
          <div key={k} data-pin={k} className="flex items-center gap-2 py-1.5 text-sm border-t pb-hairline first:border-t-0">
            <span className="font-mono text-xs w-6 text-pb-faint">{i + 1}</span>
            <span className="flex-1 min-w-0" style={{ overflowWrap: 'anywhere' }}>{byKey.get(k) ? cardLine(byKey.get(k)) : 'A card'}</span>
            <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)} className="w-8 h-8 rounded border pb-hairline">↑</button>
            <button type="button" aria-label="Move down" disabled={i === pinned.length - 1} onClick={() => move(i, 1)} className="w-8 h-8 rounded border pb-hairline">↓</button>
            <button type="button" aria-label="Unpin" data-unpin onClick={() => toggle(byKey.get(k) || { key: k })} className="w-8 h-8 rounded border pb-hairline">✕</button>
          </div>
        ))}
      </div>
      <CardGallery browse cards={mine} club={club} accent={accent} display={display} sponsor={sponsor} marked={new Set(pinned)}
        onAction={toggle} actionLabel={(c) => (pinned.includes(c.key) ? 'Unpin this card' : 'Pin this card')} />
    </div>
  )
}
