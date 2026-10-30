import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Btn, Card, Field, Select } from '../../lib/presskit'
import { useToast } from '../../contexts/ToastContext'
import { CardView, ScaledCard } from '../../components/cards/CardFaces'
import { useCardStyle } from '../../components/cards/useCardStyle'
import { CATEGORIES } from '../../components/cards/CardGallery'
import { PACKS, TIERS } from '../../components/cards/cardTheme'
import PackDesigns from './PackDesigns'
import CreatePacks from './CreatePacks'
import AdminChallenges from './AdminChallenges'

// Player Cards, for the club's admin. Nine tabs: how the cards are being used (Overview), every player and what
// they hold (Players, then a click for their whole collection), what came in lately (Activity), every card that
// exists and how many are out there (All cards), who has opened packs (Packs), an audit of swaps (Swaps), and the
// club's switches (Settings). Everything but Settings only reads.

const TABS = [
  ['overview', 'Overview'], ['players', 'Players'], ['activity', 'Activity'], ['cards', 'All cards'],
  ['packs', 'Packs'], ['designs', 'Pack designs'], ['challenges', 'Challenges'], ['swaps', 'Swaps'], ['settings', 'Settings'],
]
const EXCLUDED = {
  private: 'Hidden from the public site (or removed at their request)',
  junior: 'Junior player, and juniors are switched off',
}
const KIND_LABEL = { century: 'Century', fifty: 'Half century', five_for: 'Five wicket haul', hat_trick: 'Hat-trick', debut: 'Debut', games: 'Games milestone', runs_milestone: 'Runs milestone', wickets_milestone: 'Wickets milestone', dismissals_milestone: 'Dismissals milestone', award: 'Club award' }
const packLabel = (s) => (PACKS[s] || PACKS.weekly).label
const tierLabel = (t) => (TIERS[t] || TIERS.common).label

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : '-')
const fmtWhen = (iso) => (iso ? new Date(iso).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '-')

function Toggle({ on, onChange, label, hint, disabled }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange(!on)}
        className="mt-0.5 relative shrink-0 w-10 h-6 rounded-full transition disabled:opacity-50"
        style={{ background: on ? 'var(--pb-accent)' : 'var(--pb-hairline2, #475569)' }}>
        <span className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all" style={{ left: on ? 18 : 2 }} />
      </button>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-pb-text">{label}</span>
        {hint && <span className="block text-[12.5px] text-pb-faint mt-0.5">{hint}</span>}
      </span>
    </label>
  )
}

function Stat({ label, value, sub }) {
  return (
    <div className="pb-card p-3" data-stat={label}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">{label}</div>
      <div className="font-display font-bold text-2xl text-pb-text mt-1">{value}</div>
      {sub && <div className="text-[11.5px] text-pb-faint mt-0.5">{sub}</div>}
    </div>
  )
}

function Pill({ children, tone }) {
  const color = tone === 'special' ? '#7dd3fc' : (TIERS[tone] || {}).glow || 'var(--pb-faint)'
  return <span className="inline-block px-2 py-0.5 rounded-full text-[10.5px] font-mono uppercase tracking-wide2 border" style={{ borderColor: color, color }}>{children}</span>
}

function Bars({ daily }) {
  const max = Math.max(1, ...daily.flatMap((d) => [d.specials_added, d.packs_opened, d.swaps]))
  const series = [['packs_opened', 'Packs opened', 'var(--pb-accent)'], ['specials_added', 'Special cards added', '#7dd3fc'], ['swaps', 'Swaps made', '#f59e0b']]
  return (
    <div data-daily>
      <div className="flex items-end gap-1 h-28">
        {daily.map((d) => (
          <div key={d.day} className="flex-1 flex items-end gap-px h-full" title={`${fmtDate(d.day)}: ${d.packs_opened} packs, ${d.specials_added} specials, ${d.swaps} swaps`}>
            {series.map(([k, , c]) => <div key={k} style={{ flex: 1, height: `${(d[k] / max) * 100}%`, minHeight: d[k] ? 3 : 0, background: c, borderRadius: 2 }} />)}
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10.5px] text-pb-faint mt-1"><span>{fmtDate(daily[0]?.day)}</span><span>{fmtDate(daily[daily.length - 1]?.day)}</span></div>
      <div className="flex flex-wrap gap-3 mt-2 text-[12px] text-pb-dim">
        {series.map(([k, l, c]) => <span key={k} className="inline-flex items-center gap-1.5"><i style={{ width: 10, height: 10, background: c, borderRadius: 2, display: 'inline-block' }} />{l}</span>)}
      </div>
    </div>
  )
}

// ── Overview ───────────────────────────────────────────────────────────────────────────────────────────────
function Overview({ ov, activity, go }) {
  const t = ov.totals
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Players in the pool" value={t.players_in_pool} sub={`${t.pool} cards a pack can hold`} />
        <Stat label="Have opened a pack" value={t.players_opened} sub={`${t.players_never_opened} have not`} />
        <Stat label="Opened one this week" value={t.players_opened_7d} />
        <Stat label="Packs opened" value={t.packs_opened} sub={`${t.copies} cards held`} />
        <Stat label="Special cards" value={t.specials} sub={`${t.specials_7d} added this week`} />
        <Stat label="Swaps made" value={t.swaps_done} sub={`${t.swaps} asked, ${t.swaps_open} open`} />
      </div>
      <Card title="The last two weeks">{activity ? <Bars daily={activity.daily} /> : <div className="text-sm text-pb-faint">Loading…</div>}</Card>
      <Card title="Who is collecting" action={<Btn sm onClick={() => go('players')}>All players</Btn>}>
        <div className="divide-y divide-pb-hairline">
          {[...ov.players].filter((p) => p.in_pool).sort((a, b) => b.cards - a.cards).slice(0, 8).map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate text-pb-text">{p.name}</span>
              <span className="text-pb-faint text-[12px]">{p.regular} of {t.pool} players</span>
              <span className="w-12 text-right font-mono text-[12px]">{p.collected_pct}%</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── One player's page ───────────────────────────────────────────────────────────────────────────────────────
function CardGrid({ cards, club, accent, display }) {
  const groups = useMemo(() => {
    const out = [{ label: 'Player cards', cards: cards.filter((c) => c.kind === 'player') }]
    for (const cat of CATEGORIES) out.push({ label: cat.label, cards: cards.filter((c) => c.kind === 'special' && cat.kinds.includes(c.special_kind)) })
    return out.filter((g) => g.cards.length)
  }, [cards])
  return (
    <div className="space-y-5" data-card-grid>
      {groups.map((g) => (
        <div key={g.label}>
          <div className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint mb-2">{g.label} ({g.cards.length})</div>
          <div className="flex flex-wrap gap-3">
            {g.cards.map((c) => (
              <div key={c.key} data-grid-card={c.key} className="relative">
                <ScaledCard width={118}><CardView card={c} club={club} accent={accent} display={display} holo={false} /></ScaledCard>
                {(c.copies || 1) > 1 && <span className="absolute right-1.5 bottom-[22%] px-1.5 rounded-full bg-black/80 border border-white/50 text-white text-[10.5px] font-mono">×{c.copies}</span>}
              </div>
            ))}
          </div>
        </div>
      ))}
      {groups.length === 0 && <div className="text-sm text-pb-faint">No cards.</div>}
    </div>
  )
}

function PlayerPanel({ id, club, onBack }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const { accent, display } = useCardStyle(club)
  useEffect(() => { setD(null); api.getPlayerCardPlayer(id).then(setD).catch((e) => setErr(e?.message || 'Could not load that player.')) }, [id])
  if (err) return <div role="alert" className="text-sm text-pb-red">{err}</div>
  if (!d) return <div className="text-sm text-pb-faint">Loading…</div>
  const tot = d.totals
  return (
    <div className="space-y-4" data-player-panel={id}>
      <div className="flex items-center gap-3 flex-wrap">
        <Btn sm onClick={onBack}>← All players</Btn>
        <h2 className="font-display font-bold text-xl text-pb-text">{d.player.name}</h2>
        {d.player.in_pool ? <Pill tone={d.player.tier}>Rarity {d.player.rarity} {tierLabel(d.player.tier)}</Pill> : <Pill>Not in the card pool</Pill>}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Player cards" value={`${tot.regular_owned} / ${tot.regular_total}`} />
        <Stat label="Special cards" value={`${tot.special_owned} / ${tot.special_total}`} />
        <Stat label="Copies held" value={tot.copies} />
        <Stat label="Packs opened" value={d.packs.by_source.reduce((n, s) => n + s.opened, 0)} sub={`${d.packs.by_source.reduce((n, s) => n + s.waiting, 0)} waiting`} />
      </div>
      <Card title="Their cards"><CardGrid cards={d.cards} club={club} accent={accent} display={display} /></Card>
      <div className="grid md:grid-cols-2 gap-4">
        <Card title="Packs">
          <div className="flex flex-wrap gap-2 mb-3">{d.packs.by_source.map((s) => <Pill key={s.source}>{packLabel(s.source).replace(' pack', '')}: {s.opened} opened{s.waiting ? `, ${s.waiting} waiting` : ''}</Pill>)}</div>
          <div className="divide-y divide-pb-hairline text-[13px]">
            {d.packs.recent.map((p) => (
              <div key={p.id} className="py-1.5 flex justify-between gap-3"><span>{packLabel(p.source)}</span><span className="text-pb-faint">{p.opened_at ? `opened ${fmtWhen(p.opened_at)}` : 'waiting'}</span></div>
            ))}
          </div>
        </Card>
        <Card title="Recently got">
          <div className="divide-y divide-pb-hairline text-[13px]">
            {d.recent_cards.map((c, i) => (
              <div key={i} className="py-1.5 flex justify-between gap-3"><span className="min-w-0 truncate">{c.kind === 'special' ? `${c.player}: ${c.title}` : `${c.player} (${tierLabel(c.tier)})`}</span><span className="text-pb-faint shrink-0">{c.source} · {fmtDate(c.obtained_at)}</span></div>
            ))}
          </div>
        </Card>
      </div>
      <Card title="Their swaps"><SwapTable rows={d.swaps} /></Card>
    </div>
  )
}

// ── Players ───────────────────────────────────────────────────────────────────────────────────────────────────
function Th({ k, sort, setSort, children, right }) {
  const on = sort.key === k
  return (
    <th className={`px-2 py-2 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest cursor-pointer select-none whitespace-nowrap ${right ? 'text-right' : 'text-left'}`} onClick={() => setSort({ key: k, dir: on && sort.dir === 'desc' ? 'asc' : 'desc' })} aria-sort={on ? (sort.dir === 'desc' ? 'descending' : 'ascending') : 'none'}>
      {children}{on ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  )
}

function PlayersTab({ ov, open }) {
  const [q, setQ] = useState('')
  const [only, setOnly] = useState('pool')
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' })
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = ov.players.filter((p) => (only === 'all' || (only === 'pool' ? p.in_pool : !p.in_pool)) && (!needle || (p.name || '').toLowerCase().includes(needle)))
    const dir = sort.dir === 'desc' ? -1 : 1
    const val = (p) => (sort.key === 'name' ? (p.name || '').toLowerCase() : sort.key === 'last' ? (p.last_opened_at || '') : p[sort.key] ?? 0)
    return list.sort((a, b) => (val(a) < val(b) ? -dir : val(a) > val(b) ? dir : 0))
  }, [ov, q, only, sort])
  return (
    <Card title={`Players (${rows.length})`}>
      <div className="flex flex-wrap gap-2 mb-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" aria-label="Find a player" className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm min-w-0 flex-1" />
        <Select value={only} onChange={(e) => setOnly(e.target.value)} className="!w-auto" aria-label="Show">
          <option value="pool">In the card pool</option><option value="out">Not in the pool</option><option value="all">Everyone</option>
        </Select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-players-table>
          <thead><tr>
            <Th k="name" sort={sort} setSort={setSort}>Player</Th>
            <Th k="regular" sort={sort} setSort={setSort} right>Players held</Th>
            <Th k="specials" sort={sort} setSort={setSort} right>Specials</Th>
            <Th k="copies" sort={sort} setSort={setSort} right>Copies</Th>
            <Th k="packs_opened" sort={sort} setSort={setSort} right>Packs opened</Th>
            <Th k="packs_waiting" sort={sort} setSort={setSort} right>Waiting</Th>
            <Th k="last" sort={sort} setSort={setSort}>Last opened</Th>
            <Th k="swaps_done" sort={sort} setSort={setSort} right>Swaps</Th>
          </tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-t border-pb-hairline" data-player-row={p.id}>
                <td className="px-2 py-1.5"><button type="button" onClick={() => open(p.id)} className="text-pb-accent hover:underline text-left" data-open-player={p.id}>{p.name}</button></td>
                <td className="px-2 py-1.5 text-right font-mono">{p.regular} <span className="text-pb-faint text-[11px]">({p.collected_pct}%)</span></td>
                <td className="px-2 py-1.5 text-right font-mono">{p.specials}</td>
                <td className="px-2 py-1.5 text-right font-mono">{p.copies}</td>
                <td className="px-2 py-1.5 text-right font-mono">{p.packs_opened}</td>
                <td className="px-2 py-1.5 text-right font-mono">{p.packs_waiting}</td>
                <td className="px-2 py-1.5 whitespace-nowrap text-pb-dim">{p.last_opened_at ? fmtWhen(p.last_opened_at) : 'Never'}</td>
                <td className="px-2 py-1.5 text-right font-mono">{p.swaps_done}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={8} className="px-2 py-4 text-pb-faint">No players match.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ── Activity ───────────────────────────────────────────────────────────────────────────────────────────────────
// The cards most often on a wish list: demand only, never whose list it is on.
function MostWanted() {
  const [d, setD] = useState(null)
  useEffect(() => { api.getPlayerCardWanted().then(setD).catch(() => setD({ cards: [], total_wants: 0 })) }, [])
  return (
    <Card title="Most wanted cards">
      <p className="text-[12.5px] text-pb-faint mb-3">The cards players have put on their wish lists, most wanted first. You see how many want each card and how many players could swap one now, never whose list it is on.</p>
      {!d ? <div className="text-sm text-pb-faint">Loading…</div> : d.cards.length === 0 ? <div className="text-sm text-pb-faint" data-no-wanted>Nothing on a wish list yet.</div> : (
        <div className="overflow-x-auto"><table className="w-full text-sm" data-most-wanted>
          <thead><tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest"><th className="px-2 py-1">Card</th><th className="px-2 py-1 text-right">Want it</th><th className="px-2 py-1 text-right">Could swap now</th></tr></thead>
          <tbody>{d.cards.map((c) => (
            <tr key={c.key} className="border-t border-pb-hairline">
              <td className="px-2 py-1.5">{c.kind === 'special' ? `${c.player}: ${c.title}` : `${c.player} (${tierLabel(c.tier)})`}</td>
              <td className="px-2 py-1.5 text-right font-mono">{c.wanted_by}</td>
              <td className="px-2 py-1.5 text-right font-mono">{c.could_swap}</td>
            </tr>))}
          </tbody></table></div>
      )}
    </Card>
  )
}

function ActivityTab({ a, open }) {
  if (!a) return <div className="text-sm text-pb-faint">Loading…</div>
  return (
    <div className="space-y-4">
      <MostWanted />
      <Card title="Special cards added lately">
        <div className="overflow-x-auto"><table className="w-full text-sm" data-recent-specials>
          <thead><tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest"><th className="px-2 py-1">Card</th><th className="px-2 py-1">Player</th><th className="px-2 py-1">Happened</th><th className="px-2 py-1">Added</th><th className="px-2 py-1 text-right">Held</th></tr></thead>
          <tbody>{a.recent_specials.map((s) => (
            <tr key={s.id} className="border-t border-pb-hairline">
              <td className="px-2 py-1.5">{s.title} <span className="text-pb-faint text-[11.5px]">({KIND_LABEL[s.kind] || s.kind})</span></td>
              <td className="px-2 py-1.5"><button type="button" className="text-pb-accent hover:underline" onClick={() => open(s.player_id)}>{s.player}</button></td>
              <td className="px-2 py-1.5 text-pb-dim whitespace-nowrap">{fmtDate(s.occurred_on)}</td>
              <td className="px-2 py-1.5 text-pb-dim whitespace-nowrap">{fmtWhen(s.added_at)}</td>
              <td className="px-2 py-1.5 text-right font-mono">{s.held}</td>
            </tr>))}
          </tbody></table></div>
        {a.recent_specials.length === 0 && <div className="text-sm text-pb-faint">None yet. They are made the first time a player opens their cards, or from Settings.</div>}
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Packs opened lately">
          <div className="space-y-2" data-recent-openings>
            {a.recent_openings.map((o) => (
              <div key={o.id} className="text-[13px] border-b border-pb-hairline pb-2">
                <div className="flex justify-between gap-3 flex-wrap">
                  <span><button type="button" className="text-pb-accent hover:underline" onClick={() => open(o.player_id)}>{o.player}</button> opened a {packLabel(o.source).toLowerCase()}</span>
                  <span className="text-pb-faint">{fmtWhen(o.opened_at)}</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-1">{o.cards.map((c, i) => <Pill key={i} tone={c.tier}>{c.kind === 'special' ? `${c.player}: ${c.title}` : `${c.player} ${tierLabel(c.tier)}`}</Pill>)}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="New cards, pulled or swapped in">
          <div className="divide-y divide-pb-hairline text-[13px]" data-recent-cards>
            {a.recent_cards.map((c, i) => (
              <div key={i} className="py-1.5 flex justify-between gap-3">
                <span className="min-w-0"><button type="button" className="text-pb-accent hover:underline" onClick={() => open(c.owner_id)}>{c.owner}</button> got {c.kind === 'special' ? `${c.player}: ${c.title}` : `${c.player} (${tierLabel(c.tier)})`}{c.new_to_owner ? <b className="ml-1.5 text-[10px] font-mono text-pb-positive">NEW</b> : <span className="ml-1.5 text-[10px] font-mono text-pb-faint">double</span>}</span>
                <span className="text-pb-faint shrink-0">{c.source} · {fmtWhen(c.obtained_at)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

// ── All cards ───────────────────────────────────────────────────────────────────────────────────────────────────
const PAGE = 36
function CatalogueTab({ club }) {
  const { accent, display } = useCardStyle(club)
  const [f, setF] = useState({ kind: 'all', special_kind: '', q: '', sort: 'rarity' })
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState({ player: 0, special: 0 })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fetchPage = useCallback((offset, replace) => {
    setBusy(true); setErr('')
    return api.getPlayerCardCatalogue({ ...f, limit: PAGE, offset })
      .then((r) => { setItems((cur) => (replace ? r.items : [...cur, ...r.items])); setTotal(r.total); setCounts(r.counts) })
      .catch((e) => setErr(e?.message || 'Could not load the cards.'))
      .finally(() => setBusy(false))
  }, [f])
  useEffect(() => { const t = setTimeout(() => fetchPage(0, true), f.q ? 250 : 0); return () => clearTimeout(t) }, [fetchPage, f.q])
  const set = (patch) => setF((cur) => ({ ...cur, ...patch }))
  return (
    <Card title={`Every card (${total})`}>
      <div className="flex flex-wrap gap-2 mb-3">
        <input value={f.q} onChange={(e) => set({ q: e.target.value })} placeholder="Find a player or card" aria-label="Find a card" className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm min-w-0 flex-1" />
        <Select value={f.kind} onChange={(e) => set({ kind: e.target.value, special_kind: '' })} className="!w-auto" aria-label="Kind">
          <option value="all">Players and specials</option><option value="player">Player cards ({counts.player})</option><option value="special">Special cards ({counts.special})</option>
        </Select>
        {f.kind === 'special' && (
          <Select value={f.special_kind} onChange={(e) => set({ special_kind: e.target.value })} className="!w-auto" aria-label="Kind of special">
            <option value="">Every kind</option>{Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        )}
        <Select value={f.sort} onChange={(e) => set({ sort: e.target.value })} className="!w-auto" aria-label="Sort">
          <option value="rarity">Rarest first</option><option value="held">Fewest held first</option><option value="recent">Newest first</option><option value="name">A to Z</option>
        </Select>
      </div>
      {err && <div role="alert" className="text-sm text-pb-red mb-2">{err}</div>}
      <div className="flex flex-wrap gap-4" data-catalogue>
        {items.map((c) => (
          <div key={c.key} data-catalogue-card={c.key} style={{ width: 140 }}>
            <ScaledCard width={140}><CardView card={c} club={club} accent={accent} display={display} /></ScaledCard>
            <div className="text-[11.5px] text-pb-dim mt-1.5 leading-tight">{c.held} {c.held === 1 ? 'copy' : 'copies'} · {c.owners} {c.owners === 1 ? 'owner' : 'owners'}</div>
            {c.added_at && <div className="text-[11px] text-pb-faint">added {fmtDate(c.added_at)}</div>}
          </div>
        ))}
      </div>
      {items.length === 0 && !busy && <div className="text-sm text-pb-faint">No cards match.</div>}
      {items.length < total && <div className="mt-4"><Btn onClick={() => fetchPage(items.length, false)} disabled={busy}>{busy ? 'Loading…' : `Show more (${total - items.length} left)`}</Btn></div>}
    </Card>
  )
}

// ── Packs ───────────────────────────────────────────────────────────────────────────────────────────────────────
// The challenges load when their tab first opens, then every save hands back the whole list.
function ChallengesTab() {
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.getPlayerCardChallenges().then(setPayload).catch((e) => setError(e?.message || 'Could not load challenges.')) }, [])
  if (error) return <div role="alert" className="text-sm text-pb-red">{error}</div>
  if (!payload) return <div className="text-sm text-pb-faint">Loading…</div>
  return <AdminChallenges payload={payload} setPayload={setPayload} />
}

function PacksTab({ ov, open }) {
  const pool = ov.players.filter((p) => p.in_pool)
  const opened = pool.filter((p) => p.packs_opened > 0).sort((a, b) => (b.last_opened_at || '').localeCompare(a.last_opened_at || ''))
  const never = pool.filter((p) => p.packs_opened === 0)
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Card title={`Have opened packs (${opened.length})`}>
        <div className="divide-y divide-pb-hairline text-sm" data-openers>
          {opened.map((p) => (
            <div key={p.id} className="py-2 flex items-center gap-3">
              <button type="button" className="text-pb-accent hover:underline min-w-0 truncate text-left flex-1" onClick={() => open(p.id)}>{p.name}</button>
              <span className="font-mono text-[12px]">{p.packs_opened} opened</span>
              <span className="text-pb-faint text-[12px] w-36 text-right">first {fmtDate(p.first_opened_at)}<br />last {fmtDate(p.last_opened_at)}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card title={`Have not opened one (${never.length})`}>
        <div className="divide-y divide-pb-hairline text-sm" data-never-opened>
          {never.map((p) => (
            <div key={p.id} className="py-2 flex items-center gap-3">
              <button type="button" className="text-pb-accent hover:underline min-w-0 truncate text-left flex-1" onClick={() => open(p.id)}>{p.name}</button>
              <span className="text-pb-faint text-[12px]">{p.packs_waiting ? `${p.packs_waiting} waiting` : 'has not visited yet'}</span>
            </div>
          ))}
          {never.length === 0 && <div className="py-2 text-pb-faint">Everyone in the pool has opened a pack.</div>}
        </div>
      </Card>
    </div>
  )
}

// ── Swaps ───────────────────────────────────────────────────────────────────────────────────────────────────────
const STATUS_TONE = { accepted: 'var(--pb-positive)', declined: 'var(--pb-red)', cancelled: 'var(--pb-faint)', countered: 'var(--pb-faint)', pending: 'var(--pb-amber)', expired: 'var(--pb-faint)' }
function SwapTable({ rows }) {
  if (!rows.length) return <div className="text-sm text-pb-faint">No swaps.</div>
  const one = (c) => `${c.kind === 'special' ? `${c.player}: ${c.title}` : `${c.player} (${tierLabel(c.tier)})`}${(c.qty || 1) > 1 ? ` ×${c.qty}` : ''}`
  const line = (list) => (Array.isArray(list) ? list : [list]).map(one).join('; ')
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm" data-swap-table>
      <thead><tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest"><th className="px-2 py-1">When</th><th className="px-2 py-1">Asked</th><th className="px-2 py-1">Gave</th><th className="px-2 py-1">Asked of</th><th className="px-2 py-1">Wanted</th><th className="px-2 py-1">Result</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id} className="border-t border-pb-hairline align-top" data-swap-row={r.status}>
          <td className="px-2 py-1.5 whitespace-nowrap text-pb-dim">{fmtWhen(r.created_at)}</td>
          <td className="px-2 py-1.5">{r.from.name}{r.parent_id && <div className="text-[11px] text-pb-amber" data-swap-changed>a changed swap</div>}{r.note && <div className="text-[11.5px] text-pb-faint italic max-w-[16rem]" data-swap-row-note>“{r.note}”</div>}</td><td className="px-2 py-1.5">{line(r.give)}</td>
          <td className="px-2 py-1.5">{r.to.name}</td><td className="px-2 py-1.5">{line(r.want)}</td>
          <td className="px-2 py-1.5 whitespace-nowrap"><span style={{ color: STATUS_TONE[r.status] }} className="font-semibold capitalize">{r.status}</span>{r.resolved_at && <span className="text-pb-faint text-[11.5px]"> {fmtDate(r.resolved_at)}</span>}</td>
        </tr>))}
      </tbody></table></div>
  )
}

function SwapsTab() {
  const [status, setStatus] = useState('all')
  const [q, setQ] = useState('')
  const [d, setD] = useState(null)
  const [more, setMore] = useState(0)
  useEffect(() => { const t = setTimeout(() => { setD(null); api.getPlayerCardSwaps({ status, q, limit: 50, offset: 0 }).then(setD).catch(() => setD({ swaps: [], counts: {}, total: 0 })) }, q ? 250 : 0); return () => clearTimeout(t) }, [status, q])
  const [extra, setExtra] = useState([])
  useEffect(() => { setExtra([]); setMore(0) }, [status, q])
  const loadMore = async () => { const r = await api.getPlayerCardSwaps({ status, q, limit: 50, offset: 50 * (more + 1) }); setExtra((e) => [...e, ...r.swaps]); setMore((m) => m + 1) }
  const c = d?.counts || {}
  return (
    <Card title="Swap audit">
      <p className="text-[12.5px] text-pb-faint mb-3">Every swap request, whoever asked and however it ended. A request nobody answers lapses after 14 days.</p>
      <div className="flex flex-wrap gap-2 mb-3">
        {[['all', 'All'], ['accepted', `Accepted ${c.accepted ?? ''}`], ['pending', `Open ${c.pending ?? ''}`], ['declined', `Declined ${c.declined ?? ''}`], ['cancelled', `Cancelled ${c.cancelled ?? ''}`], ['countered', `Changed ${c.countered ?? ''}`], ['expired', `Expired ${c.expired ?? ''}`]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setStatus(k)} data-swap-filter={k} className={`px-3 py-1 rounded-full text-[12px] font-semibold border ${status === k ? 'bg-pb-accent text-pb-bg border-transparent' : 'border-pb-hairline2 text-pb-text'}`}>{l.trim()}</button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" aria-label="Find a swap by player" className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1 text-sm min-w-0 flex-1" />
      </div>
      {!d ? <div className="text-sm text-pb-faint">Loading…</div> : <SwapTable rows={[...d.swaps, ...extra]} />}
      {d && d.swaps.length + extra.length < d.total && <div className="mt-3"><Btn onClick={loadMore}>Show more</Btn></div>}
    </Card>
  )
}

// ── Settings ──────────────────────────────────────────────────────────────────────────────────────────────────────
// Which cards get a full-card photo. The photo itself (hero or action shot) is chosen by the kind of card; this is how far it goes.
const PHOTO_CHOICES = [
  ['all', 'Every card that has one (recommended)', 'Every card fills with the player\u2019s hero photo when they have one. Cards of players with only a profile photo show it in a circle.'],
  ['top', 'Special, Epic and Legendary cards only', 'Common and Rare cards show the profile photo in a circle. The rest fill with a photo.'],
  ['specials', 'Special cards only', 'Every regular card shows the profile photo in a circle. Special cards fill with a photo.'],
]
function BigPhotos({ s, saving, save }) {
  const now = s.big_photos || 'all'
  return (
    <Card title="Photos on cards">
      <Field label="Cards that fill with a photo">
        <Select value={now} disabled={saving} onChange={(e) => save({ big_photos: e.target.value })} aria-label="Cards that fill with a photo">
          {PHOTO_CHOICES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
      </Field>
      <p className="text-[12.5px] text-pb-faint mt-2" data-photo-note>{PHOTO_CHOICES.find(([k]) => k === now)?.[2]}</p>
      <p className="text-[12.5px] text-pb-faint mt-2">Every special card, such as a century, a five-for, a debut, a milestone or an award, uses the player\u2019s action shot. Where a player lacks the shot a card wants, it uses the other, then the profile photo. A shot you pinned on a player\u2019s profile is used instead of all this.</p>
    </Card>
  )
}

// What a player starts with. A club on the minimal setting gives the debut card and the latest milestone card; older gifts can be tidied.
function StartingCards({ s, saving, save }) {
  const toast = useToast()
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const check = async () => {
    setBusy(true)
    try { setPreview(await api.trimPlayerCardGifts(false)) } catch (e) { toast?.error?.(e?.message || 'Could not count them.') } finally { setBusy(false) }
  }
  const apply = async () => {
    setBusy(true)
    try { const out = await api.trimPlayerCardGifts(true); setPreview({ ...out, done: true }); toast?.success?.('Starting cards tidied') } catch (e) { toast?.error?.(e?.message || 'Could not tidy them.') } finally { setBusy(false) }
  }
  return (
    <Card title="Starting cards">
      <Field label="Every player starts with">
        <Select value={s.starter_gifts || 'minimal'} disabled={saving} onChange={(e) => save({ starter_gifts: e.target.value })} aria-label="Starting cards">
          <option value="minimal">Their own card, their debut card and their latest milestone card</option>
          <option value="all">Every special card made about them</option>
        </Select>
      </Field>
      <p className="text-[12.5px] text-pb-faint mt-2">A card is only ever added to what a player holds, so a player who already has more keeps them until you tidy them below. Cards a player has swapped away, and anything they pulled from a pack, are never touched.</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span data-trim-check><Btn sm onClick={check} disabled={busy}>{busy && !preview ? 'Counting…' : 'Count what could be tidied'}</Btn></span>
        {preview && !preview.done && preview.cards > 0 && <span data-trim-apply><Btn sm onClick={apply} disabled={busy}>Remove {preview.cards} {preview.cards === 1 ? 'card' : 'cards'} from {preview.players} {preview.players === 1 ? 'player' : 'players'}</Btn></span>}
      </div>
      {preview && (
        <p className="text-sm mt-2" data-trim-result>
          {preview.done ? `Done. Took ${preview.cards} starting ${preview.cards === 1 ? 'card' : 'cards'} back from ${preview.players} ${preview.players === 1 ? 'player' : 'players'}.`
            : preview.cards === 0 ? 'Nothing to tidy. Everyone is already down to the minimal set.'
              : `${preview.cards} starting ${preview.cards === 1 ? 'card' : 'cards'} held by ${preview.players} ${preview.players === 1 ? 'player' : 'players'} would be removed. Their own card, debut and latest milestone stay.`}
        </p>
      )}
    </Card>
  )
}

function SettingsTab({ data, setData }) {
  const toast = useToast()
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('')
  const [only, setOnly] = useState('all')
  const [copied, setCopied] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const s = data.settings

  const save = async (patch) => {
    setSaving(true)
    try { setData(await api.updatePlayerCardSettings(patch)); toast?.success?.('Saved') } catch (e) { toast?.error?.(e?.message || 'Could not save that.') } finally { setSaving(false) }
  }
  const hide = async (p, hidden) => {
    try { setData(await api.setPlayerCardHidden(p.id, hidden)) } catch (e) { toast?.error?.(e?.message || 'Could not change that player.') }
  }
  const findMore = async () => {
    setRefreshing(true)
    try {
      const { made } = await api.refreshPlayerCardSpecials()
      const n = Object.values(made || {}).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0)
      toast?.success?.(n ? 'Special cards updated' : 'No new special cards to make')
    } catch (e) { toast?.error?.(e?.message || 'Could not look through the history.') } finally { setRefreshing(false) }
  }
  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return (data.players || []).filter((p) => {
      if (q && !(p.display_name || '').toLowerCase().includes(q)) return false
      if (only === 'hidden') return p.hidden
      if (only === 'out') return !p.in_pool
      return true
    })
  }, [data, filter, only])
  const link = data.link?.path ? `${window.location.origin}${data.link.path}` : null

  return (
    <div className="space-y-4">
      <Card title="Settings">
        <div className="space-y-4">
          <Toggle on={s.enabled} disabled={saving} onChange={(v) => save({ enabled: v })} label="Player Cards are on"
            hint="Switching them off hides the cards and the packs from your players. Nothing they have collected is lost." />
          <Toggle on={s.alerts_enabled !== false} disabled={saving} onChange={(v) => save({ alerts_enabled: v })} label="Card emails are on"
            hint="Emails to players when a swap is asked of them and when a card on their wish list is available. Every player starts with both off and chooses to switch them on. Players with no email on file, and under 18s, are never emailed." />
          <Toggle on={s.event_packs_enabled !== false} disabled={saving} onChange={(v) => save({ event_packs_enabled: v })} label="Day packs are on"
            hint="Match Day, holiday (Halloween, the Melbourne Cup, Christmas and more), birthday and surprise packs. Players collect one by opening their page that day. Packs you schedule below are not affected by this switch." />
          <Toggle on={s.sets_enabled !== false} disabled={saving} onChange={(v) => save({ sets_enabled: v })} label="Sets are on"
            hint="Groups of cards players work towards completing, such as every century at the club. Nothing is awarded for finishing one." />
          <Toggle on={s.showcase_enabled !== false} disabled={saving} onChange={(v) => save({ showcase_enabled: v })} label="Showcases are on"
            hint="Players can pin up to six cards they hold, shown next to their name on the collectors board." />
          <Toggle on={s.board_enabled !== false} disabled={saving} onChange={(v) => save({ board_enabled: v })} label="The collectors board is on"
            hint="Everyone with a card is listed, ranked by share of the set held (different cards, never copies). A player can leave it in their own settings." />
          <Toggle on={s.feed_enabled !== false} disabled={saving} onChange={(v) => save({ feed_enabled: v })} label="This week at the club is on"
            hint="A short feed on Home of special cards earned, big pulls and swaps agreed. Players can leave their name out of it." />
          <Toggle on={s.include_juniors} disabled={saving} onChange={(v) => save({ include_juniors: v })} label="Include junior players"
            hint="Off by default. When on, juniors have cards and can be pulled from packs. Check with their families first." />
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Weekly packs per player">
              <Select value={s.weekly_packs} disabled={saving} onChange={(e) => save({ weekly_packs: Number(e.target.value) })} aria-label="Weekly packs per player">
                {Array.from({ length: data.max_weekly_packs + 1 }, (_, i) => <option key={i} value={i}>{i === 1 ? '1 (the default)' : i}</option>)}
              </Select>
            </Field>
            <Field label="The week turns over on Monday in">
              <Select value={s.timezone || ''} disabled={saving} onChange={(e) => save({ timezone: e.target.value || null })} aria-label="Timezone">
                <option value="">{`Default (${s.effective_timezone})`}</option>
                {data.timezones.map((t) => <option key={t.id} value={t.id}>{t.label} ({t.id.split('/')[1].replace('_', ' ')})</option>)}
              </Select>
            </Field>
          </div>
          <p className="text-[12.5px] text-pb-faint">A weekly pack that is not opened by the end of the week is gone. Packs earned for runs, wickets and dismissals wait until they are opened.</p>
        </div>
      </Card>
      <BigPhotos s={s} saving={saving} save={save} />
      <StartingCards s={s} saving={saving} save={save} />
      <CreatePacks data={data} setData={setData} />
      <Card title="Where players find them">
        {link ? (
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-[12.5px] bg-pb-surface2 rounded px-2 py-1 break-all min-w-0" data-player-page-link>{link}</code>
            <Btn sm onClick={() => { navigator.clipboard?.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1800) }}>{copied ? 'Copied' : 'Copy link'}</Btn>
          </div>
        ) : <p className="text-sm text-pb-faint">The link appears once the page has loaded.</p>}
        <p className="text-[12.5px] text-pb-faint mt-2">Players pick their name and enter the last 4 digits of their mobile number, as on the availability page. Mobile numbers are kept on the Players page. A player with no number on file cannot sign in until one is added.</p>
      </Card>
      <Card title="Special cards" action={<Btn sm onClick={findMore} disabled={refreshing}>{refreshing ? 'Looking…' : 'Look for new ones'}</Btn>}>
        <p className="text-[12.5px] text-pb-faint">Centuries, half centuries, five-wicket hauls, hat-tricks, debuts, games milestones and club awards each get a card, made from your history and kept up to date as games come in. The player it is for starts with their debut and their latest milestone card (see Starting cards), and everyone else can pull the rest from a pack. Cards are only ever added: a score corrected later does not take one away.</p>
      </Card>
      <Card title={`Players in the card pool (${data.pool.size} of ${data.pool.players})`}>
        <div className="flex flex-wrap gap-2 mb-3">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a player" aria-label="Find a player to hide" className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm min-w-0 flex-1" />
          <Select value={only} onChange={(e) => setOnly(e.target.value)} className="!w-auto" aria-label="Show">
            <option value="all">Everyone</option><option value="hidden">Hidden by us</option><option value="out">Not in the pool</option>
          </Select>
        </div>
        <div className="rounded border pb-hairline divide-y divide-pb-hairline max-h-[420px] overflow-y-auto">
          {rows.length === 0 && <div className="p-4 text-sm text-pb-faint">No players match.</div>}
          {rows.map((p) => (
            <div key={p.id} className="flex items-center gap-3 px-3 py-2" data-card-player={p.id}>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-pb-text truncate">{p.display_name}</div>
                <div className="text-[11.5px] text-pb-faint">
                  {p.excluded ? EXCLUDED[p.excluded] : p.hidden ? 'Hidden by the club' : p.in_pool ? `${p.matches} matches · rarity ${p.rarity} (${p.tier})` : 'No matches yet. Has a card, cannot be pulled from a pack'}
                </div>
              </div>
              {!p.excluded && <Btn sm onClick={() => hide(p, !p.hidden)}>{p.hidden ? 'Show' : 'Hide'}</Btn>}
            </div>
          ))}
        </div>
        <p className="text-[12.5px] text-pb-faint mt-2">Hiding a player takes their card out of every pack and gallery. They keep their own collection, and showing them again brings the card back.</p>
      </Card>
    </div>
  )
}

export default function AdminPlayerCards() {
  const [data, setData] = useState(null) // settings and the club's look
  const [error, setError] = useState('')
  const [tab, setTab] = useState('overview')
  const [ov, setOv] = useState(null)
  const [activity, setActivity] = useState(null)
  const [player, setPlayer] = useState(null)

  useEffect(() => { api.getPlayerCardSettings().then(setData).catch((e) => setError(e?.message || 'Could not load Player Cards.')) }, [])
  useEffect(() => {
    if (!data) return
    api.getPlayerCardOverview().then(setOv).catch(() => setOv({ totals: {}, players: [] }))
    api.getPlayerCardActivity().then(setActivity).catch(() => setActivity({ daily: [], recent_specials: [], recent_cards: [], recent_openings: [] }))
  }, [data?.settings?.enabled, data?.settings?.include_juniors, data?.pool?.size]) // eslint-disable-line react-hooks/exhaustive-deps

  const open = (id) => { setPlayer(id); setTab('players') }
  const body = () => {
    if (tab === 'settings') return <SettingsTab data={data} setData={setData} />
    if (tab === 'cards') return <CatalogueTab club={data.club} />
    if (tab === 'designs') return <PackDesigns data={data} setData={setData} />
    if (tab === 'challenges') return <ChallengesTab />
    if (tab === 'swaps') return <SwapsTab />
    if (!ov) return <div className="text-sm text-pb-faint">Loading…</div>
    if (tab === 'activity') return <ActivityTab a={activity} open={open} />
    if (tab === 'packs') return <PacksTab ov={ov} open={open} />
    if (tab === 'players') return player ? <PlayerPanel id={player} club={data.club} onBack={() => setPlayer(null)} /> : <PlayersTab ov={ov} open={setPlayer} />
    return <Overview ov={ov} activity={activity} go={setTab} />
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-5xl" data-player-cards-admin>
        <h1 className="font-display font-bold text-2xl text-pb-text">Player Cards</h1>
        <p className="text-sm text-pb-faint mt-1 mb-4">
          Every player gets a collectable card of their career figures. Players open packs of other players' cards from their own player page: one pack a week, more for runs, wickets and dismissals, and a Duck Pack when it goes wrong. They can swap doubles with each other.
        </p>
        {error && <div role="alert" className="text-sm text-pb-red mb-4">{error}</div>}
        {!data && !error && <div className="text-sm text-pb-faint">Loading…</div>}
        {data && (
          <>
            <div role="tablist" aria-label="Player Cards" className="flex gap-1.5 flex-wrap mb-4">
              {TABS.map(([k, l]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} data-pc-tab={k} onClick={() => { setTab(k); if (k !== 'players') setPlayer(null) }}
                  className={`px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold border ${tab === k ? 'bg-pb-accent text-pb-bg border-transparent' : 'border-pb-hairline2 text-pb-text hover:bg-pb-surface2'}`}>{l}</button>
              ))}
            </div>
            {body()}
          </>
        )}
      </div>
    </BetterStatsLayout>
  )
}
