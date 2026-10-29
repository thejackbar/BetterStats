// Challenges: sets with a goal and a reward. The club publishes two kinds. An EXCHANGE asks for cards that meet some rules (11 Common
// cards, a squad rated 70 or more) and spends them; a COLLECTION asks you to hold a list of cards (the 2024 A Grade premiers) and
// keeps them. Finishing either pays a reward pack. Below them are a player's own PRIVATE sets: cards they have decided to collect,
// which nobody else sees and which pay nothing.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { PackArt } from '../../components/cards/PackOpening'
import { QUALITY_STARS } from '../../components/cards/cardTheme'
import PageHead from './PageHead'
import { EarnedBanner } from './Sets'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"
const TIER_DOT = { common: '#94a3b8', rare: '#cbd5e1', epic: '#f59e0b', legendary: '#c084fc', special: '#7dd3fc' }

export function RewardChip({ reward }) {
  const { club, accent, display } = usePC()
  return (
    <div className="flex items-center gap-2.5" data-reward>
      <PackArt source="reward" label={reward.title} quality={reward.quality} size={reward.size} club={club} accent={accent} display={display} width={34} />
      <div className="min-w-0">
        <div className="text-[13px] font-semibold">{reward.qty === 1 ? '1 pack' : `${reward.qty} packs`} · {reward.quality_label}</div>
        <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">{reward.size} cards · {'★'.repeat(QUALITY_STARS[reward.quality] || 0) || 'standard'}</div>
      </div>
    </div>
  )
}

function Bar({ percent, accent }) {
  return <div style={{ height: 6, borderRadius: 3, background: 'rgba(148,163,184,.25)', margin: '10px 0 6px', overflow: 'hidden' }}><div style={{ width: `${percent}%`, height: '100%', background: accent }} /></div>
}

// Who is in a collection or a private set, with a tick for the ones the player holds.
function Members({ members }) {
  const [open, setOpen] = useState(false)
  if (!members?.length) return null
  return (
    <div className="mt-2">
      <button type="button" className="text-[12px] underline text-pb-dim" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-members-toggle>{open ? 'Hide the cards' : 'Show the cards'}</button>
      {open && (
        <ul className="mt-2 grid gap-1 text-[13px]" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))' }} data-members>
          {members.map((m) => (
            <li key={m.key} data-member={m.key} data-held={m.held ? 'yes' : 'no'} className="flex items-center gap-2" style={{ opacity: m.held ? 1 : 0.6 }}>
              <span aria-hidden style={{ width: 8, height: 8, borderRadius: 4, background: TIER_DOT[m.tier] || '#94a3b8', flex: 'none' }} />
              <span className="min-w-0 truncate">{m.name}</span>
              <span aria-label={m.held ? 'Held' : 'Not held'} className="ml-auto">{m.held ? '✓' : ''}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ChallengeCard({ c }) {
  const { basePath, accent, display } = usePC()
  const done = c.finished
  const tag = c.status === 'soon' ? `Starts ${c.starts_on}` : c.status === 'ended' ? 'Ended' : done ? (c.kind === 'exchange' && c.max_completions > 1 ? 'All done' : 'Done') : c.kind === 'exchange' && c.completions > 0 ? `Done ${c.completions} of ${c.max_completions}` : null
  return (
    <div data-challenge={c.id} data-challenge-kind={c.kind} data-done={done ? 'yes' : 'no'} className="rounded-2xl border pb-hairline bg-pb-surface p-4 flex flex-col gap-2" style={{ opacity: c.status !== 'open' && !done ? 0.7 : 1 }}>
      <div className="flex items-start justify-between gap-2">
        <div style={{ font: `800 20px/1.1 ${display}`, textTransform: 'uppercase' }}>{c.title}</div>
        {tag && <span data-challenge-tag className="shrink-0 px-2 py-0.5 rounded-full" style={{ background: done ? accent : 'transparent', color: done ? onColor(accent) : 'inherit', border: done ? 0 : '1px solid rgba(148,163,184,.5)', font: `700 10px ${MONO}`, letterSpacing: 1 }}>{tag.toUpperCase()}</span>}
      </div>
      {c.blurb && <div className="text-[13px] text-pb-dim">{c.blurb}</div>}
      {c.kind === 'exchange' ? (
        <>
          <ul className="flex flex-wrap gap-1.5" data-requirements>
            {c.requirements.map((r) => <li key={r} className="px-2.5 py-1 rounded-full text-[12px] border pb-hairline">{r}</li>)}
          </ul>
          <div className="flex items-center justify-between gap-3 mt-1">
            <RewardChip reward={c.reward} />
            {c.status === 'open' && !done && <Link to={`${basePath}/challenges/${c.id}`} data-challenge-go className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: accent, color: onColor(accent) }}>Build a squad</Link>}
          </div>
        </>
      ) : (
        <>
          <Bar percent={c.percent} accent={accent} />
          <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint" data-challenge-progress>{c.owned} of {c.need === c.total ? c.total : `${c.need} needed from ${c.total}`} · {c.percent}%</div>
          <Members members={c.members} />
          <div className="mt-1"><RewardChip reward={c.reward} /></div>
        </>
      )}
    </div>
  )
}

// A set of the player's own. What to collect is picked, not typed: some players, a premiership side, a tier or a kind of special card.
function SetBuilder({ onMade, onCancel }) {
  const { token, accent } = usePC()
  const [opts, setOpts] = useState(null)
  const [kind, setKind] = useState('premiership')
  const [title, setTitle] = useState('')
  const [pick, setPick] = useState('')
  const [chosen, setChosen] = useState(() => new Set())
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api.availPublicChallengeOptions(token).then(setOpts).catch(() => setErr('The choices could not load. Try again.')) }, [token])
  const players = useMemo(() => (opts?.players || []).filter((p) => !filter.trim() || p.name.toLowerCase().includes(filter.trim().toLowerCase())), [opts, filter])
  const selector = () => {
    if (kind === 'players') return { type: 'players', player_ids: [...chosen] }
    if (kind === 'premiership') { const [season, grade] = pick.split('|'); return { type: 'premiership', season: season || '', grade: grade || '' } }
    if (kind === 'tier') return { type: 'tier', tier: pick }
    return { type: 'special_kind', kind: pick }
  }
  const ready = kind === 'players' ? chosen.size > 0 : !!pick
  const submit = async (e) => {
    e.preventDefault(); if (!ready || busy) return
    setBusy(true); setErr('')
    try { await api.availPublicCreateMySet(token, { title: title.trim() || null, selector: selector() }); onMade() } catch (e2) { setErr(e2?.message || 'That set could not be made.') } finally { setBusy(false) }
  }
  const toggle = (id) => setChosen((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n })
  return (
    <form onSubmit={submit} data-set-builder className="rounded-2xl border pb-hairline bg-pb-surface p-4 mb-4 max-w-2xl">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">Name (optional)
          <input value={title} maxLength={60} onChange={(e) => setTitle(e.target.value)} aria-label="Name of the set" placeholder="My favourites" className="mt-1 w-full rounded-lg border pb-hairline bg-transparent px-3 py-2" />
        </label>
        <label className="block text-sm">What to collect
          <select value={kind} onChange={(e) => { setKind(e.target.value); setPick('') }} aria-label="What to collect" className="mt-1 w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2">
            <option value="premiership">A premiership side</option>
            <option value="players">Players I pick</option>
            <option value="tier">Every card of a tier</option>
            <option value="special_kind">Every special card of a kind</option>
          </select>
        </label>
      </div>
      <div className="mt-3">
        {kind === 'premiership' && (
          <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Premiership" className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2">
            <option value="">Pick a premiership…</option>
            {(opts?.premierships || []).map((p) => <option key={`${p.season}|${p.grade}`} value={`${p.season}|${p.grade}`}>{p.label} ({p.players} players)</option>)}
          </select>
        )}
        {kind === 'tier' && (
          <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Tier" className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2">
            <option value="">Pick a tier…</option>
            {(opts?.tiers || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        )}
        {kind === 'special_kind' && (
          <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Kind of special card" className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2">
            <option value="">Pick a kind…</option>
            {(opts?.special_kinds || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        )}
        {kind === 'players' && (
          <div>
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a player" aria-label="Find a player" className="w-full rounded-lg border pb-hairline bg-transparent px-3 py-2 mb-2" />
            <div className="rounded-lg border pb-hairline max-h-56 overflow-y-auto divide-y divide-pb-hairline" data-set-players>
              {players.map((p) => (
                <label key={p.id} className="flex items-center gap-2.5 px-3 py-1.5 cursor-pointer text-sm"><input type="checkbox" checked={chosen.has(p.id)} onChange={() => toggle(p.id)} /> <span className="truncate">{p.name}</span></label>
              ))}
            </div>
            <div className="text-[12px] text-pb-faint mt-1">{chosen.size} {chosen.size === 1 ? 'player' : 'players'} picked</div>
          </div>
        )}
      </div>
      {err && <div role="alert" className="text-sm mt-2" style={{ color: 'var(--pb-red, #f87171)' }}>{err}</div>}
      <div className="flex gap-2 mt-3">
        <button type="submit" disabled={!ready || busy} data-set-make className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: accent, color: onColor(accent), opacity: !ready || busy ? 0.5 : 1 }}>{busy ? 'Making…' : 'Make the set'}</button>
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-lg text-sm border pb-hairline">Cancel</button>
      </div>
    </form>
  )
}

export default function Challenges() {
  const { token, accent, features, load } = usePC()
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [making, setMaking] = useState(false)
  const read = () => api.availPublicChallenges(token).then((d) => { setData(d); if (d.earned?.length) load() }).catch(() => setFailed(true))
  useEffect(() => { read() }, [token]) // eslint-disable-line react-hooks/exhaustive-deps
  const remove = async (id) => { try { await api.availPublicDeleteMySet(token, id); await read() } catch { setFailed(true) } }
  if (!features.sets) return <div className="text-sm text-pb-dim" data-not-on>Your club has this switched off.</div>
  if (failed) return <div className="text-sm text-pb-faint" data-challenges-failed>Challenges could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-challenges-loading>Loading challenges…</div>
  const exchange = data.challenges.filter((c) => c.kind === 'exchange')
  const collections = data.challenges.filter((c) => c.kind === 'collection')
  return (
    <div data-screen="challenges">
      <PageHead title="Challenges" sub="Hand in cards that meet the rules, or collect a list of cards, and earn a reward pack." />
      <EarnedBanner earned={data.earned} />
      <section className="mb-8" data-section="exchange">
        <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2">Hand in cards</h2>
        <p className="text-sm text-pb-dim mb-3 max-w-prose">The cards you hand in are spent, so this is a good home for doubles. Your own card and your starting cards cannot be handed in.</p>
        {exchange.length === 0 && <div className="text-sm text-pb-dim" data-no-exchange>Your club has not set any of these yet.</div>}
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))' }}>{exchange.map((c) => <ChallengeCard key={c.id} c={c} />)}</div>
      </section>
      <section className="mb-8" data-section="collections">
        <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mb-2">Collect</h2>
        <p className="text-sm text-pb-dim mb-3 max-w-prose">Hold every card on the list and the reward is yours. You keep the cards.</p>
        {collections.length === 0 && <div className="text-sm text-pb-dim" data-no-collections>Your club has not set any of these yet. The Sets screen has the club&rsquo;s own sets, which also pay a pack.</div>}
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))' }}>{collections.map((c) => <ChallengeCard key={c.id} c={c} />)}</div>
      </section>
      <section data-section="my-sets">
        <div className="flex items-center justify-between gap-3 mb-2">
          <h2 className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint">My sets</h2>
          {!making && data.my_sets.length < data.max_my_sets && <button type="button" onClick={() => setMaking(true)} data-new-set className="px-3 py-1.5 rounded-lg text-sm border pb-hairline">New set</button>}
        </div>
        <p className="text-sm text-pb-dim mb-3 max-w-prose">Cards you have decided to collect, such as a premiership side. Only you can see these, and they pay nothing.</p>
        {making && <SetBuilder onMade={() => { setMaking(false); read() }} onCancel={() => setMaking(false)} />}
        {data.my_sets.length === 0 && !making && <div className="text-sm text-pb-dim" data-no-my-sets>You have not made a set yet.</div>}
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))' }}>
          {data.my_sets.map((s) => (
            <div key={s.id} data-my-set={s.id} className="rounded-2xl border pb-hairline bg-pb-surface p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold" style={{ overflowWrap: 'anywhere' }}>{s.title}</div>
                <button type="button" onClick={() => remove(s.id)} aria-label={`Delete ${s.title}`} data-my-set-delete className="text-[12px] underline text-pb-dim">Delete</button>
              </div>
              <Bar percent={s.percent} accent={accent} />
              <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint">{s.owned} of {s.total} · {s.percent}%{s.complete ? ' · complete' : ''}</div>
              <Members members={s.members} />
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
