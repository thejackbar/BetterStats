// One squad challenge: its rules, the reward, and a squad built from the cards the player holds. Nothing is taken from the player: the
// cards stay in their collection. The rules are checked by the server as the squad changes, so what this screen says is what the server
// will do. Each card counts once, and cards used the last time the challenge was finished are not offered again.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { Mini, cardLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { RewardChip } from './Challenges'
import { usePC } from './context'
import { CATEGORIES, ROLE_FILTERS } from '../../components/cards/CardGallery'
import { DEFAULT_FILTERS, RATING_MAX, RATING_MIN, SORTS, chipCounts, clampRating, filterChallengeCards, hasCardRules, ratingNarrowed } from './challengeFilters'

const MONO = "'JetBrains Mono', monospace"
const TIERS = [['all', 'All'], ['special', 'Special'], ['legendary', 'Legendary'], ['epic', 'Epic'], ['rare', 'Rare'], ['common', 'Common']]

export default function ChallengePage() {
  const { id } = useParams()
  const { token, basePath, club, accent, display, sponsor, load } = usePC()
  const [ch, setCh] = useState(null)
  const [err, setErr] = useState('')
  const [picked, setPicked] = useState(() => new Map())      // key -> card
  const [verdict, setVerdict] = useState(null)
  const [f, setF] = useState(DEFAULT_FILTERS)
  const [loText, setLoText] = useState(String(RATING_MIN))
  const [hiText, setHiText] = useState(String(RATING_MAX))
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const sent = useRef(0)

  const read = () => api.availPublicChallenge(token, id).then((c) => { setCh(c); setErr('') }).catch((e) => setErr(e?.message || 'That challenge could not be found.'))
  useEffect(() => { setCh(null); setPicked(new Map()); setVerdict(null); setResult(null); read() }, [token, id]) // eslint-disable-line react-hooks/exhaustive-deps
  // A challenge with rules about single cards (only batters, only Rare and up, named players) starts showing just the cards that fit.
  const cardRules = hasCardRules(ch?.rules)
  useEffect(() => { setF({ ...DEFAULT_FILTERS, fits: cardRules }); setLoText(String(RATING_MIN)); setHiText(String(RATING_MAX)) }, [id, cardRules])
  const set = (patch) => setF((cur) => ({ ...cur, ...patch }))
  // The rating boxes take any typing; the filter only moves once a box holds a number, and a low end above the high end swaps them.
  const commitRating = (loRaw, hiRaw) => {
    let lo = clampRating(loRaw, RATING_MIN); let hi = clampRating(hiRaw, RATING_MAX)
    if (lo > hi) [lo, hi] = [hi, lo]
    set({ lo, hi })
    return [lo, hi]
  }
  const settleRating = () => { const [lo, hi] = commitRating(loText, hiText); setLoText(String(lo)); setHiText(String(hi)) }
  const clearFilters = () => { setF({ ...DEFAULT_FILTERS, fits: cardRules }); setLoText(String(RATING_MIN)); setHiText(String(RATING_MAX)) }

  const selection = useMemo(() => [...picked.keys()].map((key) => ({ key })), [picked])
  const total = selection.length

  // Ask the server which rules the squad meets, a moment after the last change.
  useEffect(() => {
    if (!ch || result) return undefined
    if (!selection.length) { setVerdict(null); return undefined }
    const mine = ++sent.current
    const t = setTimeout(() => {
      api.availPublicCheckChallenge(token, id, selection).then((v) => { if (sent.current === mine) setVerdict(v) }).catch((e) => { if (sent.current === mine) setErr(e?.message || 'Those cards could not be checked.') })
    }, 250)
    return () => clearTimeout(t)
  }, [selection, ch, token, id, result])

  const toggle = (card) => setPicked((cur) => { const next = new Map(cur); if (next.has(card.key)) next.delete(card.key); else next.set(card.key, card); return next })
  const reset = () => { setPicked(new Map()); setVerdict(null) }
  const submit = async () => {
    setBusy(true); setErr('')
    try { const out = await api.availPublicSubmitChallenge(token, id, selection); setResult(out); setPicked(new Map()); load(); read() } catch (e) { setErr(e?.message || 'That could not be finished.') } finally { setBusy(false) }
  }

  const shown = useMemo(() => (ch ? filterChallengeCards(ch.cards, f, ch.rules) : []), [ch, f])
  const counts = useMemo(() => chipCounts(ch?.cards || []), [ch])

  if (err && !ch) return <div data-challenge-error className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }}>{err} <Link to={`${basePath}/challenges`} className="underline">Back to challenges</Link></div>
  if (!ch) return <div className="text-sm text-pb-faint" data-challenge-loading>Loading the challenge…</div>
  const ui = { club, accent, display, sponsor }
  const finished = ch.completions >= ch.max_completions
  const ready = verdict?.ok && total > 0
  return (
    <div data-screen="challenge">
      <PageHead title={ch.title} sub={ch.blurb || 'Pick cards you hold that meet the rules. You keep every card.'} actions={<Link to={`${basePath}/challenges`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">All challenges</Link>} />
      {result && (
        <div data-challenge-done role="status" className="rounded-2xl border p-4 mb-5" style={{ borderColor: accent }}>
          <div className="font-bold">Challenge complete.</div>
          <div className="text-sm mt-1">You used {result.used} {result.used === 1 ? 'card' : 'cards'} and earned {result.packs} {result.reward.quality_label} reward {result.packs === 1 ? 'pack' : 'packs'}. Every card is still yours. <Link to={`${basePath}/packs`} className="underline">Open {result.packs === 1 ? 'it' : 'them'}</Link>.</div>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="order-2 lg:order-1 min-w-0">
          {finished && !result && <div className="text-sm text-pb-dim mb-3" data-challenge-finished>You have done this challenge{ch.max_completions > 1 ? ` ${ch.completions} of ${ch.max_completions} times` : ''}.</div>}
          <div className="flex flex-col gap-2 mb-3" data-challenge-filters>
            <div className="flex flex-wrap items-center gap-2">
              <input value={f.q} onChange={(e) => set({ q: e.target.value })} placeholder="Find a card: a player, century, a season" aria-label="Find a card" data-filter-search className="rounded-lg border pb-hairline bg-transparent px-3 py-1.5 text-sm min-w-0 flex-1 basis-48" />
              <label className="flex items-center gap-1.5 text-[12.5px] text-pb-dim">
                <span>Sort</span>
                <select value={f.sort} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort" data-filter-sort className="rounded-lg border pb-hairline bg-transparent px-2 py-1.5 text-sm">
                  {SORTS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                </select>
              </label>
            </div>
            <Chips label="Tier" name="tier" value={f.tier} onPick={(v) => set({ tier: v })} accent={accent} options={TIERS.map(([k, label]) => ({ key: k, label }))} />
            {(counts.player > 0 && counts.special > 0) && (
              <Chips label="Type" name="type" value={f.type} onPick={(v) => set({ type: v })} accent={accent}
                options={[{ key: 'all', label: 'All cards' }, { key: 'player', label: 'Players', n: counts.player }, { key: 'special', label: 'Specials', n: counts.special },
                  ...CATEGORIES.filter((c) => counts.cats[c.key]).map((c) => ({ key: c.key, label: c.label, n: counts.cats[c.key] }))]} />
            )}
            {Object.keys(counts.roles).length > 0 && (
              <Chips label="Role" name="role" value={f.role} onPick={(v) => set({ role: v })} accent={accent}
                options={[{ key: '', label: 'Any role' }, ...ROLE_FILTERS.filter(([k]) => counts.roles[k]).map(([k, label]) => ({ key: k, label, n: counts.roles[k] })),
                  ...(counts.none ? [{ key: 'none', label: 'No role recorded', n: counts.none }] : [])]} />
            )}
            <div className="flex flex-wrap items-center gap-2 text-[12.5px]" data-filter-rating>
              <span className="text-pb-dim">Rating</span>
              <input type="number" inputMode="numeric" min={RATING_MIN} max={RATING_MAX} value={loText} aria-label="Lowest rating"
                onChange={(e) => { setLoText(e.target.value); if (e.target.value !== '') commitRating(e.target.value, hiText) }} onBlur={settleRating}
                data-rating-lo className="w-16 rounded-lg border pb-hairline bg-transparent px-2 py-1.5 text-sm" />
              <span className="text-pb-faint">to</span>
              <input type="number" inputMode="numeric" min={RATING_MIN} max={RATING_MAX} value={hiText} aria-label="Highest rating"
                onChange={(e) => { setHiText(e.target.value); if (e.target.value !== '') commitRating(loText, e.target.value) }} onBlur={settleRating}
                data-rating-hi className="w-16 rounded-lg border pb-hairline bg-transparent px-2 py-1.5 text-sm" />
              {ratingNarrowed(f) && counts.special > 0 && <span className="text-pb-faint" data-rating-note>Special cards have no rating, so they are hidden while the range is set.</span>}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
              {cardRules && (
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={f.fits} onChange={(e) => set({ fits: e.target.checked })} data-filter-fits />
                  <span>Only cards that fit the rules</span>
                </label>
              )}
              <span className="font-mono text-[11px] text-pb-faint" data-filter-count>{shown.length === ch.cards.length ? `${ch.cards.length} ${ch.cards.length === 1 ? 'card' : 'cards'}` : `Showing ${shown.length} of ${ch.cards.length}`}</span>
              {JSON.stringify(f) !== JSON.stringify({ ...DEFAULT_FILTERS, fits: cardRules }) && <button type="button" onClick={clearFilters} data-filter-clear className="underline text-pb-dim">Clear filters</button>}
            </div>
          </div>
          {ch.cards.length === 0 && <div className="text-sm text-pb-dim" data-no-spendable>You have no cards to pick from yet, or you used them all last time. Open some packs and come back.</div>}
          {ch.cards.length > 0 && shown.length === 0 && <div className="text-sm text-pb-dim" data-no-match>No cards match these filters. <button type="button" onClick={clearFilters} className="underline">Clear filters</button></div>}
          <div className="flex flex-wrap gap-3" data-challenge-cards>
            {shown.map((c) => {
              const on = picked.has(c.key)
              return (
                <div key={c.key} className="flex flex-col items-center gap-1" data-challenge-card={c.key}>
                  <Mini card={c} {...ui} width={92} selected={on ? true : undefined} onClick={() => toggle(c)} label={`${cardLine(c)}${on ? ', picked' : ''}`} />
                  {on && <span className="font-mono text-[10px] tracking-wide2 uppercase" data-card-picked>Picked</span>}
                </div>
              )
            })}
          </div>
        </div>
        <aside className="order-1 lg:order-2 min-w-0 lg:sticky lg:top-4 self-start" data-challenge-side>
          <div className="rounded-2xl border pb-hairline bg-pb-surface p-4">
            <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mb-2">Rules</div>
            <ul className="flex flex-col gap-1.5 text-sm" data-checklist>
              {(verdict?.checks || ch.requirements.map((label, i) => ({ id: `r${i}`, label, ok: false, have: null, need: null }))).map((c) => (
                <li key={c.id} data-check={c.id} data-check-ok={c.ok ? 'yes' : 'no'} className="flex items-start gap-2">
                  <span aria-hidden style={{ width: 18, height: 18, borderRadius: 9, flex: 'none', display: 'grid', placeItems: 'center', font: `800 11px ${MONO}`, background: c.ok ? accent : 'transparent', color: c.ok ? onColor(accent) : 'inherit', border: c.ok ? 0 : '1px solid rgba(148,163,184,.6)' }}>{c.ok ? '✓' : ''}</span>
                  <span className="flex-1">{c.label}</span>
                  {c.have != null && c.need != null && <span className="font-mono text-[11px] text-pb-faint">{c.have}/{c.need}</span>}
                </li>
              ))}
            </ul>
            {verdict?.rating != null && <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mt-2" data-rating>Squad rating {verdict.rating}</div>}
            <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mt-4 mb-2">Reward</div>
            <RewardChip reward={ch.reward} />
            <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mt-4 mb-1" data-picked-total>{total} {total === 1 ? 'card' : 'cards'} picked</div>
            {selection.length > 0 && (
              <ul className="flex flex-col gap-1 text-[13px] mb-3" data-picked-list>
                {[...picked.values()].map((card) => (
                  <li key={card.key} data-picked-row={card.key} className="flex items-center gap-2">
                    <span className="flex-1 min-w-0 truncate">{cardLine(card)}</span>
                    <button type="button" aria-label={`Remove: ${cardLine(card)}`} onClick={() => toggle(card)} className="w-7 h-7 rounded border pb-hairline">−</button>
                  </li>
                ))}
              </ul>
            )}
            {err && <div role="alert" className="text-sm mb-2" style={{ color: 'var(--pb-red, #f87171)' }}>{err}</div>}
            <div className="text-[12px] text-pb-faint mb-2">You keep every card you pick.</div>
            <div className="flex gap-2">
              <button type="button" disabled={!ready || busy || finished || ch.status !== 'open'} onClick={submit} data-handin className="flex-1 px-4 py-2.5 rounded-lg text-sm font-semibold" style={{ background: accent, color: onColor(accent), opacity: !ready || finished || ch.status !== 'open' ? 0.45 : 1 }}>{busy ? 'Finishing…' : 'Finish the challenge'}</button>
              {selection.length > 0 && <button type="button" onClick={reset} className="px-3 py-2.5 rounded-lg text-sm border pb-hairline">Clear</button>}
            </div>
            {ch.status !== 'open' && <div className="text-[12px] text-pb-faint mt-2">{ch.status === 'soon' ? 'This has not started yet.' : 'This has ended.'}</div>}
          </div>
        </aside>
      </div>
    </div>
  )
}

// One row of filter chips. Declared at module level so typing elsewhere does not remount it.
function Chips({ label, name, value, onPick, options, accent }) {
  return (
    <div role="tablist" aria-label={label} data-filter-row={name} className="flex gap-1.5 flex-wrap">
      {options.map((o) => (
        <button key={o.key || 'any'} type="button" role="tab" aria-selected={value === o.key} data-filter={`${name}:${o.key || 'any'}`} {...(name === 'tier' ? { 'data-tier-filter': o.key } : {})} onClick={() => onPick(o.key)}
          className="px-3 py-1.5 rounded-full text-[12.5px] font-semibold border pb-hairline" style={value === o.key ? { background: accent, color: onColor(accent), borderColor: accent } : undefined}>
          {o.label}{o.n != null && <span className="opacity-60 ml-1">{o.n}</span>}
        </button>
      ))}
    </div>
  )
}
