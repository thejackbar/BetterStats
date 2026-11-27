import { Muted, Section, money } from './ui'

// The Teamwear card on the player's page: an open order round, what they owe, and the way in.
// The Kit page itself is /playerdash/:token/kit.
const PHASE = { editable: 'Ordering', waiting: 'Being checked', payment: 'Payment requested', locked: 'With the supplier' }

export function teamwearSummary(t) {
  if (!t) return {}
  if (t.owing > 0) return { text: `${money(t.owing)} to pay`, tone: 'var(--pb-amber)' }
  if (t.open?.length) return { text: 'Order round open', tone: 'var(--pb-amber)' }
  if (t.orders) return { text: t.orders === 1 ? '1 order' : `${t.orders} orders` }
  return t.stock ? { text: 'Kit in stock' } : {}
}

export default function TeamwearCard({ token, data }) {
  const t = data?.teamwear
  if (!t) return null
  return (
    <Section title="Teamwear">
      {t.open?.map(c => (
        <div key={c.name} className="text-sm mb-1.5" data-teamwear-open>
          <b>{c.name}</b> is open for orders{c.closes_at ? ` until ${new Date(c.closes_at).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}` : ''}.
        </div>
      ))}
      {t.active?.map(o => (
        <div key={o.reference} className="text-[13px] text-pb-dim flex justify-between gap-2">
          <span className="min-w-0 truncate">{o.campaign_name || 'Shop order'} · {PHASE[o.phase] || o.phase}</span>
          {o.phase === 'payment' && o.balance > 0 && <span style={{ color: 'var(--pb-amber)' }}>{money(o.balance)}</span>}
        </div>
      ))}
      {!t.open?.length && !t.active?.length && <Muted>{t.stock ? 'Club kit is in stock.' : 'No order round is open.'}</Muted>}
      <a href={`/playerdash/${token}/kit`} data-teamwear-link
        className="inline-flex mt-2.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold"
        style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
        {t.open?.length ? 'Order kit' : t.owing > 0 ? 'View and pay' : 'Teamwear'}
      </a>
    </Section>
  )
}
