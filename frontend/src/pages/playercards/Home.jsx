// Home: your card, the packs waiting (open them from here), what is waiting in swaps, and how far through the set you are.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import FlipCard from '../../components/FlipCard'
import { onColor } from '../../components/PlayerTradingCard'
import { PackArt } from '../../components/cards/PackOpening'
import ShareSheet from '../../components/cards/ShareSheet'
import { CARD_H, CARD_W, CardInfoBack, CardView } from '../../components/cards/CardFaces'
import { PACKS } from '../../components/cards/cardTheme'
import PageHead, { ghostBtn } from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"

export function weekdayLabel(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? 'Monday' : d.toLocaleDateString('en-AU', { weekday: 'long' })
}

// The "N packs to open" block, shared by Home and the Packs screen.
export function PackBlock({ big = false }) {
  const { data, club, accent, display, startPack, busyAll, openAll, packErr } = usePC()
  const packs = data.packs
  const next = packs[0]
  const byWeekly = useMemo(() => {
    const n = {}
    for (const p of packs) n[p.source] = (n[p.source] || 0) + 1
    return n
  }, [packs])
  if (!packs.length) {
    return (
      <div data-no-packs>
        <div style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1 }}>No packs to open</div>
        <div className="text-sm text-pb-dim mt-1.5">Your next weekly pack arrives {weekdayLabel(data.week_resets_at)}.</div>
      </div>
    )
  }
  return (
    <div>
      <div data-packs-ready style={{ font: `800 ${big ? 30 : 24}px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1 }}>
        {packs.length} {packs.length === 1 ? 'pack' : 'packs'} to open
      </div>
      <div className="flex flex-wrap gap-1.5 my-2.5">
        {Object.entries(byWeekly).map(([src, n]) => (
          <span key={src} data-pack-count={src} style={{ padding: '3px 10px', borderRadius: 999, border: '1px solid var(--pb-hairline, rgba(255,255,255,.25))', font: `600 11px ${MONO}`, letterSpacing: 0.8, textTransform: 'uppercase' }}>{n} {(PACKS[src] || PACKS.weekly).label.replace(' pack', '')}</span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" onClick={() => startPack(next)} data-open-pack aria-label="Open a pack" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}>
          <div className="cc-float"><PackArt source={next.source} club={club} accent={accent} display={display} width={big ? 130 : 110} glow /></div>
        </button>
        <div className="flex flex-col gap-2">
          <button type="button" onClick={() => startPack(next)} data-open-next style={{ padding: '11px 18px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>Open a pack</button>
          {packs.length > 1 && (
            <button type="button" onClick={openAll} disabled={busyAll} data-open-all style={{ padding: '9px 18px', borderRadius: 12, border: '1px solid var(--pb-hairline, rgba(255,255,255,.3))', font: `700 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', opacity: busyAll ? 0.6 : 1 }}>
              {busyAll ? 'Opening…' : `Open all ${packs.length}`}
            </button>
          )}
        </div>
      </div>
      {packErr && <div role="alert" className="mt-2 text-[12.5px]" style={{ color: 'var(--pb-red, #f87171)' }}>{packErr}</div>}
    </div>
  )
}

export function MyCardHero({ width = 210 }) {
  const { mine, club, accent, display, sponsor } = usePC()
  const [flipped, setFlipped] = useState(false)
  if (!mine) return null
  return (
    <div style={{ flex: 'none' }}>
      <div style={{ width, height: width * (CARD_H / CARD_W) }} data-my-card>
        <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${width / CARD_W})`, transformOrigin: 'top left' }}>
          <FlipCard width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped((f) => !f)}
            label={flipped ? 'Showing your card details. Turn it back over' : 'Showing your card. Turn it over for the details'}
            front={<CardView card={mine} club={club} accent={accent} display={display} sponsor={sponsor} />}
            back={<CardInfoBack card={mine} club={club} accent={accent} display={display} />} />
        </div>
      </div>
      <div className="text-center mt-1.5" style={{ font: `600 10px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.6 }}>Your card. Tap to turn it over</div>
    </div>
  )
}

function Tile({ to, title, children, accent, tag }) {
  const inner = (
    <div className="rounded-2xl border pb-hairline bg-pb-surface p-4 h-full" data-tile={tag}>
      <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mb-2">{title}</div>
      {children}
    </div>
  )
  return to ? <Link to={to} className="block hover:opacity-90" style={{ textDecoration: 'none', color: 'inherit' }}>{inner}</Link> : inner
}

export default function Home() {
  const { data, failed, mine, club, accent, display, sponsor, basePath, swapsWaiting, wants } = usePC()
  const [share, setShare] = useState(null)
  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your cards could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your cards…</div>
  const t = data.totals || {}
  return (
    <div data-screen="home">
      <PageHead title="Home" sub={`${club?.name || 'Your club'}'s cards, packs and swaps.`}
        actions={mine && <button type="button" onClick={() => setShare(mine)} data-share-mine style={ghostBtn}>Share my card</button>} />
      <div className="flex flex-wrap gap-6 items-start rounded-2xl border pb-hairline bg-pb-surface p-5">
        {mine && <div className="mx-auto sm:mx-0"><MyCardHero /></div>}
        <div className="flex-1 min-w-[240px]">
          <PackBlock />
          <div className="text-[12.5px] text-pb-dim mt-4 leading-relaxed" data-how-to-earn>
            More packs: one every week, one for every 25 runs, 2 wickets and 2 dismissals this season, and a Duck Pack when it goes wrong.{' '}
            <Link to={`${basePath}/how`} className="underline">How it works</Link>
          </div>
        </div>
      </div>
      <div className="grid gap-3 mt-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))' }}>
        <Tile to={`${basePath}/swaps`} title="Swaps" tag="swaps">
          <div style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase' }}>{swapsWaiting ? `${swapsWaiting} asking you` : 'Nothing waiting'}</div>
          <div className="text-sm text-pb-dim mt-1">{swapsWaiting ? 'Open them to accept or decline.' : 'Swap any cards you hold with another player.'}</div>
        </Tile>
        <Tile to={`${basePath}/book`} title="Your collection" tag="collection">
          <div className="flex gap-6">
            <div><div style={{ font: `800 24px/1 ${display}` }}>{t.regular_owned ?? 0} <span className="text-pb-faint text-lg">/ {t.regular_total ?? 0}</span></div><div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mt-1">Players</div></div>
            {(t.special_total > 0) && <div><div style={{ font: `800 24px/1 ${display}` }}>{t.special_owned ?? 0} <span className="text-pb-faint text-lg">/ {t.special_total}</span></div><div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mt-1">Specials</div></div>}
          </div>
          <div style={{ height: 6, borderRadius: 3, background: 'rgba(148,163,184,.25)', marginTop: 12, overflow: 'hidden' }}>
            <div style={{ width: `${t.regular_total ? Math.round(((t.regular_owned || 0) / t.regular_total) * 100) : 0}%`, height: '100%', background: accent }} />
          </div>
        </Tile>
        <Tile to={`${basePath}/wishlist`} title="Wish list" tag="wishlist">
          <div style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase' }}>{wants.ready ? `${wants.ready} could be yours` : wants.count ? `${wants.count} on your list` : 'Nothing on it yet'}</div>
          <div className="text-sm text-pb-dim mt-1">{wants.ready ? 'Someone has a copy you could ask for.' : 'Add the cards you are after and see who has them.'}</div>
        </Tile>
        <Tile to={`${basePath}/club`} title="Club cards" tag="club">
          <div style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase' }}>Every card in the club</div>
          <div className="text-sm text-pb-dim mt-1">Search, sort, and see who could swap you a copy.</div>
        </Tile>
      </div>
      {share && <ShareSheet card={share} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => setShare(null)} />}
    </div>
  )
}
