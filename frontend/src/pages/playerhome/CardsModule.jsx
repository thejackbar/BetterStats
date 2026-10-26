// "Player Cards" on the player's own page: their own card (turn it over for the figures), the packs they
// have earned and how to earn more, and the card book. Reads its own data, so the page's first paint does
// not wait on it, and keeps the section header's "packs to open" count honest through `onReady`.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { useClubSponsors } from '../../lib/useClubSponsors'
import { cardSponsor, onColor } from '../../components/PlayerTradingCard'
import FlipCard from '../../components/FlipCard'
import CardGallery from '../../components/cards/CardGallery'
import PackOpening, { PackArt } from '../../components/cards/PackOpening'
import { CARD_H, CARD_W, CardInfoBack, CardView, DEFAULT_DISPLAY, ScaledCard } from '../../components/cards/CardFaces'
import { TIERS, PACKS } from '../../components/cards/cardTheme'

const MONO = "'JetBrains Mono', monospace"

function weekdayLabel(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? 'Monday' : d.toLocaleDateString('en-AU', { weekday: 'long' })
}

// What an "open all" found, without listing hundreds of cards.
function AllSummary({ result, club, accent, display, sponsor, onClose }) {
  return (
    <div role="dialog" aria-modal="true" aria-label="Packs opened" data-open-all-summary onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(3,6,10,.9)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, overflowY: 'auto' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 560, textAlign: 'center' }}>
        <div style={{ font: `800 italic 30px ${display}`, textTransform: 'uppercase', letterSpacing: 1.5 }}>{result.opened} {result.opened === 1 ? 'pack' : 'packs'} opened</div>
        <div style={{ font: `600 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.8, margin: '6px 0 14px' }}>{result.total} cards added</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginBottom: 16 }}>
          {Object.entries(result.by_tier || {}).filter(([, n]) => n > 0).map(([t, n]) => (
            <span key={t} data-tier-count={t} style={{ padding: '4px 11px', borderRadius: 999, border: `1px solid ${(TIERS[t] || TIERS.common).glow}`, color: (TIERS[t] || TIERS.common).ink, font: `700 11px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase' }}>{n} {(TIERS[t] || TIERS.common).label}</span>
          ))}
        </div>
        {(result.best || []).length > 0 && <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', opacity: 0.85, marginBottom: 8 }}>Best pulls</div>}
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 10 }}>
          {(result.best || []).map((c) => (
            <ScaledCard key={c.key} width={Math.min(104, (Math.min(window.innerWidth, 560) - 56) / 3)}>
              <CardView card={c} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} />
            </ScaledCard>
          ))}
        </div>
        <button type="button" onClick={onClose} data-open-all-done style={{ marginTop: 18, padding: '12px 22px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>See my card book</button>
      </div>
    </div>
  )
}

export default function CardsModule({ token, club, onReady }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [pack, setPack] = useState(null)
  const [owned, setOwned] = useState(() => new Set())
  const [flipped, setFlipped] = useState(false)
  const [busyAll, setBusyAll] = useState(false)
  const [allResult, setAllResult] = useState(null)
  const [err, setErr] = useState('')
  const accent = club?.accent_color || club?.primary_color || '#16c784'
  const display = DEFAULT_DISPLAY
  const sponsor = cardSponsor(useClubSponsors(club?.slug))

  const load = useCallback(() => api.availPublicCards(token)
    .then((d) => { setData(d); onReady?.(d.packs.length) })
    .catch(() => setFailed(true)), [token, onReady])
  useEffect(() => { load() }, [load])

  const mine = useMemo(() => data?.cards.find((c) => c.mine), [data])
  const byWeekly = useMemo(() => {
    const n = {}
    for (const p of data?.packs || []) n[p.source] = (n[p.source] || 0) + 1
    return n
  }, [data])

  const start = (p) => {
    setOwned(new Set((data?.cards || []).map((c) => c.key)))
    setPack(p)
  }
  const close = () => { setPack(null); load() }
  const openNext = async () => {
    // The pack that was just opened is gone; read the list again and go straight on to the next.
    const d = await api.availPublicCards(token)
    setData(d); onReady?.(d.packs.length)
    setOwned(new Set(d.cards.map((c) => c.key)))
    setPack(d.packs[0] || null)
  }
  const openAll = async () => {
    setBusyAll(true); setErr('')
    try {
      setAllResult(await api.availPublicOpenAllCards(token))
    } catch (e) {
      setErr(e?.message || 'Could not open the packs. Try again.')
    } finally {
      setBusyAll(false)
      load()
    }
  }

  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your cards could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your cards…</div>

  const packs = data.packs
  const next = packs[0]
  const handW = 210
  return (
    <div data-cards-module>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        {mine && (
          <div style={{ flex: 'none', margin: '0 auto' }}>
            <div style={{ width: handW, height: handW * (CARD_H / CARD_W) }} data-my-card>
              <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${handW / CARD_W})`, transformOrigin: 'top left' }}>
                <FlipCard width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped((f) => !f)}
                  label={flipped ? 'Showing your card details. Turn it back over' : 'Showing your card. Turn it over for the details'}
                  front={<CardView card={mine} club={club} accent={accent} display={display} sponsor={sponsor} />}
                  back={<CardInfoBack card={mine} club={club} accent={accent} display={display} />} />
              </div>
            </div>
            <div style={{ textAlign: 'center', font: `600 10px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.6, marginTop: 6 }}>Your card. Tap to turn it over</div>
          </div>
        )}

        <div style={{ flex: '1 1 240px', minWidth: 0 }}>
          {packs.length > 0 ? (
            <>
              <div data-packs-ready style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1 }}>
                {packs.length} {packs.length === 1 ? 'pack' : 'packs'} to open
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0 12px' }}>
                {Object.entries(byWeekly).map(([src, n]) => (
                  <span key={src} data-pack-count={src} style={{ padding: '3px 10px', borderRadius: 999, border: '1px solid var(--pb-hairline, rgba(255,255,255,.25))', font: `600 11px ${MONO}`, letterSpacing: 0.8, textTransform: 'uppercase' }}>{n} {(PACKS[src] || PACKS.weekly).label.replace(' pack', '')}</span>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
                <button type="button" onClick={() => start(next)} data-open-pack aria-label="Open a pack"
                  style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}>
                  <div className="cc-float"><PackArt source={next.source} club={club} accent={accent} display={display} width={110} glow /></div>
                </button>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <button type="button" onClick={() => start(next)} style={{ padding: '11px 18px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>Open a pack</button>
                  {packs.length > 1 && (
                    <button type="button" onClick={openAll} disabled={busyAll} data-open-all style={{ padding: '9px 18px', borderRadius: 12, border: '1px solid var(--pb-hairline, rgba(255,255,255,.3))', font: `700 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', opacity: busyAll ? 0.6 : 1 }}>
                      {busyAll ? 'Opening…' : `Open all ${packs.length}`}
                    </button>
                  )}
                </div>
              </div>
              {err && <div role="alert" style={{ marginTop: 8, fontSize: 12.5, color: 'var(--pb-red, #f87171)' }}>{err}</div>}
            </>
          ) : (
            <div data-no-packs>
              <div style={{ font: `800 20px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1 }}>No packs to open</div>
              <div style={{ fontSize: 13, opacity: 0.75, marginTop: 6 }}>Your next weekly pack arrives {weekdayLabel(data.week_resets_at)}.</div>
            </div>
          )}
          <div style={{ fontSize: 12.5, opacity: 0.7, marginTop: 12, lineHeight: 1.5 }} data-how-to-earn>
            More packs: one every week, one for every 25 runs, 2 wickets and 2 dismissals this season, and a Duck Pack when it goes wrong. Specials turn up in packs and are yours for the moments that earn them.
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <CardGallery cards={data.cards} totals={data.totals} club={club} accent={accent} display={display} sponsor={sponsor} />
      </div>

      {pack && <PackOpening key={pack.id} pack={pack} packsLeft={Math.max(0, packs.length - 1)} club={club} accent={accent} display={display} sponsor={sponsor} owned={owned}
        openPack={() => api.availPublicOpenCard(token, pack.id)} onClose={close} onNext={openNext} />}
      {allResult && <AllSummary result={allResult} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => { setAllResult(null); load() }} />}
    </div>
  )
}
