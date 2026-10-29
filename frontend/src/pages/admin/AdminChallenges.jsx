// Player Cards, challenges: an admin sets a task for every player and says what finishing it pays. Two kinds.
// A SQUAD challenge (stored as `exchange`) is the squad-builder kind (11 Rares, a squad rated 70 or better, 11 different players): the player
// picks cards they hold that meet the rules and keeps every one. A COLLECTION is a list of cards to hold (everyone from a premiership side, every Century card): the
// cards stay with the player. Either way the reward is one or more packs from the club (services/player_card_challenges).
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { Btn, Card, Field, Select } from '../../lib/presskit'
import { useToast } from '../../contexts/ToastContext'
import { Switch } from './packDesignParts'

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
const inputCls = 'w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm'
const premKey = (p) => `${p.season}|${p.grade}`

const BLANK = {
  kind: 'exchange', title: '', blurb: '',
  count: 11, kinds: 'any', tiersOnly: [], minTier: {}, minRating: '', maxPer: '', specialKinds: [],
  premiership: '', keepPlayers: null,
  selType: 'premiership', selPremiership: '', selPlayers: [], selTier: 'rare', selKind: '', need: '',
  quality: 'special', qty: 1, size: 5, packTitle: '',
  maxCompletions: 1, startsOn: '', endsOn: '', active: true, sortOrder: 0,
}

// A saved challenge, read back into the form.
function toForm(c) {
  const r = c.rules || {}
  const rw = c.reward || {}
  const f = {
    ...BLANK, kind: c.kind, title: c.title, blurb: c.blurb || '', maxCompletions: c.max_completions || 1, startsOn: c.starts_on || '', endsOn: c.ends_on || '',
    active: c.active, sortOrder: c.sort_order || 0, quality: rw.quality || 'special', qty: rw.qty || 1, size: rw.size || 5, packTitle: rw.title || '',
  }
  if (c.kind === 'exchange') {
    return {
      ...f, count: r.count || 11, kinds: r.kinds || 'any', tiersOnly: r.tiers_only || [], minTier: r.min_tier || {}, minRating: r.min_rating || '',
      maxPer: r.max_per_player || '', specialKinds: r.special_kinds || [], keepPlayers: r.players?.length ? { ids: r.players, label: r.players_label || `${r.players.length} chosen players` } : null,
    }
  }
  const s = r.selector || {}
  return {
    ...f, selType: s.type || 'premiership', selPremiership: s.type === 'premiership' ? `${s.season || ''}|${s.grade || ''}` : '', selPlayers: s.player_ids || [],
    selTier: s.tier || 'rare', selKind: s.kind || '', need: r.need && r.need < (r.card_keys || []).length ? r.need : '',
  }
}

// The form as the API wants it.
function toBody(f) {
  const body = {
    kind: f.kind, title: f.title, blurb: f.blurb || null, active: f.active, sort_order: Number(f.sortOrder) || 0,
    starts_on: f.startsOn || null, ends_on: f.endsOn || null,
    reward: { quality: f.quality, qty: Number(f.qty) || 1, size: Number(f.size) || 5, ...(f.packTitle.trim() ? { title: f.packTitle.trim() } : {}) },
  }
  if (f.kind === 'exchange') {
    const rules = { count: Number(f.count) || 1, kinds: f.kinds }
    if (f.tiersOnly.length) rules.tiers_only = f.tiersOnly
    const mt = Object.fromEntries(Object.entries(f.minTier).filter(([, n]) => Number(n) > 0).map(([k, n]) => [k, Number(n)]))
    if (Object.keys(mt).length) rules.min_tier = mt
    if (Number(f.minRating) > 0) rules.min_rating = Number(f.minRating)
    if (Number(f.maxPer) > 0) rules.max_per_player = Number(f.maxPer)
    if (f.specialKinds.length) rules.special_kinds = f.specialKinds
    if (f.premiership) { const [season, grade] = f.premiership.split('|'); rules.premiership = { season, grade } }
    else if (f.keepPlayers) { rules.players = f.keepPlayers.ids; rules.players_label = f.keepPlayers.label }
    body.rules = rules
    body.max_completions = Number(f.maxCompletions) || 1
  } else {
    if (f.selType === 'premiership') { const [season, grade] = f.selPremiership.split('|'); body.selector = { type: 'premiership', season: season || '', grade: grade || '' } }
    else if (f.selType === 'players') body.selector = { type: 'players', player_ids: f.selPlayers }
    else if (f.selType === 'tier') body.selector = { type: 'tier', tier: f.selTier }
    else body.selector = { type: 'special_kind', kind: f.selKind }
    if (Number(f.need) > 0) body.need = Number(f.need)
  }
  return body
}

function Checks({ options, value, onChange, label, name }) {
  const toggle = (k) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k])
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={label} data-checks={name}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value.includes(o.key)} data-check={o.key} onClick={() => toggle(o.key)}
          className={`px-2.5 py-1 rounded-full text-[12px] border ${value.includes(o.key) ? 'bg-pb-accent text-pb-bg border-transparent font-semibold' : 'border-pb-hairline2 text-pb-text hover:bg-pb-surface2'}`}>{o.label}</button>
      ))}
    </div>
  )
}

function PlayerChoice({ players, value, onChange }) {
  const [q, setQ] = useState('')
  const rows = useMemo(() => players.filter((p) => !q.trim() || p.name.toLowerCase().includes(q.trim().toLowerCase())), [players, q])
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return (
    <div data-challenge-players>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" aria-label="Find a player" className={inputCls} />
      <div className="mt-2 max-h-48 overflow-y-auto rounded border pb-hairline divide-y divide-pb-hairline2">
        {rows.length === 0 && <div className="p-3 text-[12.5px] text-pb-faint">No players match.</div>}
        {rows.map((p) => (
          <label key={p.id} className="flex items-center gap-2 px-2.5 py-1.5 text-sm cursor-pointer hover:bg-pb-surface2">
            <input type="checkbox" checked={value.includes(p.id)} onChange={() => toggle(p.id)} data-challenge-player={p.id} />
            <span className="min-w-0 truncate">{p.name}</span>
          </label>
        ))}
      </div>
      <div className="text-[11.5px] text-pb-faint mt-1">{plural(value.length, 'player', 'players')} picked</div>
    </div>
  )
}

function ChallengeForm({ payload, initial, editingId, onSaved, onCancel }) {
  const toast = useToast()
  const [f, setF] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (patch) => setF((cur) => ({ ...cur, ...patch }))
  const tierOpts = (payload.tiers || [])
  const premiers = payload.premierships || []
  const lim = payload.limits || {}
  const isEx = f.kind === 'exchange'
  const quality = (payload.qualities || []).find((q) => q.key === f.quality)

  const save = async () => {
    setBusy(true); setErr('')
    try {
      const body = toBody(f)
      const out = editingId ? await api.updatePlayerCardChallenge(editingId, body) : await api.createPlayerCardChallenge(body)
      toast?.success?.(editingId ? 'Challenge saved' : 'Challenge published')
      onSaved(out)
    } catch (e) { setErr(e?.message || 'Could not save that.') } finally { setBusy(false) }
  }

  return (
    <Card title={editingId ? 'Change this challenge' : 'New challenge'}>
      <div className="space-y-4" data-challenge-form>
        {!editingId && (
          <div role="radiogroup" aria-label="Kind of challenge" className="grid gap-2 sm:grid-cols-2">
            {[['exchange', 'Squad', 'Players pick cards they hold that meet your rules, like 11 Rares or a squad rated 70. They keep every card.'],
              ['collection', 'Collection', 'Players hold a list of cards you pick, like a premiership side. They keep the cards.']].map(([k, l, d]) => (
              <button key={k} type="button" role="radio" aria-checked={f.kind === k} data-challenge-kind={k} onClick={() => set({ kind: k })}
                className={`text-left rounded-lg border px-3 py-2 ${f.kind === k ? 'border-pb-accent bg-pb-surface2' : 'border-pb-hairline2 hover:bg-pb-surface2'}`}>
                <span className="block text-sm font-semibold text-pb-text">{l}</span>
                <span className="block text-[12px] text-pb-faint">{d}</span>
              </button>
            ))}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name"><input value={f.title} maxLength={60} onChange={(e) => set({ title: e.target.value })} aria-label="Challenge name" placeholder={isEx ? 'Rare squad' : 'The 2019 premiers'} className={inputCls} /></Field>
          <Field label="A line of detail (optional)"><input value={f.blurb} maxLength={200} onChange={(e) => set({ blurb: e.target.value })} aria-label="Challenge detail" className={inputCls} /></Field>
        </div>

        {isEx ? (
          <div className="space-y-3" data-exchange-rules>
            <div className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint">What the cards must be</div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Cards in the squad"><input type="number" min="1" max={lim.count || 30} value={f.count} onChange={(e) => set({ count: e.target.value })} aria-label="Cards in the squad" className={inputCls} /></Field>
              <Field label="Kind of card">
                <Select value={f.kinds} aria-label="Kind of card" onChange={(e) => set({ kinds: e.target.value })}>
                  <option value="any">Any card</option><option value="players">Player cards only</option><option value="specials">Special cards only</option>
                </Select>
              </Field>
              <Field label="Squad rated at least"><input type="number" min="0" max="99" value={f.minRating} onChange={(e) => set({ minRating: e.target.value })} aria-label="Squad rating" placeholder="No minimum" className={inputCls} /></Field>
            </div>
            <Field label="Only these tiers (none picked means any)"><Checks name="tiers" label="Tiers allowed" options={tierOpts} value={f.tiersOnly} onChange={(v) => set({ tiersOnly: v })} /></Field>
            <Field label="At least this many of a tier">
              <div className="flex flex-wrap gap-3">
                {tierOpts.map((t) => (
                  <label key={t.key} className="flex items-center gap-1.5 text-[12.5px] text-pb-text">
                    <span className="w-16">{t.label}</span>
                    <input type="number" min="0" max={f.count || 30} value={f.minTier[t.key] || ''} aria-label={`Minimum ${t.label} cards`} data-min-tier={t.key}
                      onChange={(e) => set({ minTier: { ...f.minTier, [t.key]: e.target.value } })} className="w-16 bg-pb-surface2 border border-pb-hairline2 rounded px-2 py-1 text-sm" />
                  </label>
                ))}
              </div>
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Cards of the same player, at most">
                <input type="number" min="1" value={f.maxPer} onChange={(e) => set({ maxPer: e.target.value })} aria-label="Cards of one player" placeholder="No limit (1 means all different players)" className={inputCls} />
              </Field>
              <Field label="Only players from a premiership side">
                <Select value={f.premiership} aria-label="Premiership side" onChange={(e) => set({ premiership: e.target.value, keepPlayers: null })}>
                  <option value="">{f.keepPlayers ? f.keepPlayers.label : 'Anyone'}</option>
                  {premiers.map((p) => <option key={premKey(p)} value={premKey(p)}>{p.label} ({plural(p.players, 'player', 'players')})</option>)}
                </Select>
              </Field>
            </div>
            {(payload.special_kinds || []).length > 0 && (
              <Field label="Special cards of these kinds only (none picked means any)"><Checks name="special-kinds" label="Special kinds" options={payload.special_kinds} value={f.specialKinds} onChange={(v) => set({ specialKinds: v })} /></Field>
            )}
            <Field label="Times one player can complete it (with different cards each time)"><input type="number" min="1" max={lim.completions || 10} value={f.maxCompletions} onChange={(e) => set({ maxCompletions: e.target.value })} aria-label="Times it can be completed" className="w-24 bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" /></Field>
          </div>
        ) : (
          <div className="space-y-3" data-collection-rules>
            <div className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint">What players collect</div>
            <Field label="The cards are">
              <Select value={f.selType} aria-label="What to collect" onChange={(e) => set({ selType: e.target.value })}>
                <option value="premiership">Players from a premiership side</option><option value="players">Players I pick</option>
                <option value="tier">Every card of a tier</option><option value="special_kind">Every special card of a kind</option>
              </Select>
            </Field>
            {f.selType === 'premiership' && (
              <Field label="Which side">
                <Select value={f.selPremiership} aria-label="Premiership side" onChange={(e) => set({ selPremiership: e.target.value })}>
                  <option value="">Pick a premiership</option>
                  {premiers.map((p) => <option key={premKey(p)} value={premKey(p)}>{p.label} ({plural(p.players, 'player', 'players')})</option>)}
                </Select>
                {premiers.length === 0 && <span className="block text-[12px] text-pb-faint mt-1">No premierships are recorded for the club yet. Add them under the players' honours.</span>}
              </Field>
            )}
            {f.selType === 'players' && <PlayerChoice players={payload.players || []} value={f.selPlayers} onChange={(v) => set({ selPlayers: v })} />}
            {f.selType === 'tier' && (
              <Field label="Which tier"><Select value={f.selTier} aria-label="Tier to collect" onChange={(e) => set({ selTier: e.target.value })}>{tierOpts.filter((t) => t.key !== 'special').map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</Select></Field>
            )}
            {f.selType === 'special_kind' && (
              <Field label="Which kind"><Select value={f.selKind} aria-label="Special card kind" onChange={(e) => set({ selKind: e.target.value })}><option value="">Pick a kind</option>{(payload.special_kinds || []).map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}</Select></Field>
            )}
            <Field label="Cards needed (leave empty for all of them)"><input type="number" min="1" value={f.need} onChange={(e) => set({ need: e.target.value })} aria-label="Cards needed" className="w-32 bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" /></Field>
            <p className="text-[12px] text-pb-faint">The list of cards is fixed when you publish. Players who join the side later are not added; make a new challenge for them.</p>
          </div>
        )}

        <div className="space-y-3" data-challenge-reward>
          <div className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint">What it pays</div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Quality of pack">
              <Select value={f.quality} aria-label="Reward pack quality" onChange={(e) => set({ quality: e.target.value })}>{(payload.qualities || []).map((q) => <option key={q.key} value={q.key}>{q.label}</option>)}</Select>
            </Field>
            <Field label="Packs"><input type="number" min="1" max={lim.reward_qty || 5} value={f.qty} onChange={(e) => set({ qty: e.target.value })} aria-label="Reward packs" className={inputCls} /></Field>
            <Field label="Cards in each"><input type="number" min={lim.pack_size?.min || 1} max={lim.pack_size?.max || 12} value={f.size} onChange={(e) => set({ size: e.target.value })} aria-label="Cards in each reward pack" className={inputCls} /></Field>
          </div>
          {quality && <div className="text-[12px] text-pb-faint">{quality.line}. At least {quality.rare_plus} of 5 Rare or better.</div>}
          <Field label="Name on the pack (optional)"><input value={f.packTitle} maxLength={40} onChange={(e) => set({ packTitle: e.target.value })} aria-label="Reward pack name" placeholder="Challenge reward" className={inputCls} /></Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Opens (optional)"><input type="date" value={f.startsOn} onChange={(e) => set({ startsOn: e.target.value })} aria-label="Opens on" className={inputCls} /></Field>
          <Field label="Closes (optional)"><input type="date" value={f.endsOn} onChange={(e) => set({ endsOn: e.target.value })} aria-label="Closes on" className={inputCls} /></Field>
          <Field label="Order in the list"><input type="number" min="0" max="1000" value={f.sortOrder} onChange={(e) => set({ sortOrder: e.target.value })} aria-label="Order" className={inputCls} /></Field>
        </div>
        <Switch on={f.active} onChange={(v) => set({ active: v })} label="Shown to players" hint="Switch off to hide it without losing it." />

        {err && <div role="alert" className="text-sm text-pb-red" data-challenge-error>{err}</div>}
        <div className="flex flex-wrap gap-2">
          <span data-challenge-save><Btn primary onClick={save} disabled={busy || !f.title.trim()}>{busy ? 'Saving…' : editingId ? 'Save changes' : 'Publish challenge'}</Btn></span>
          <Btn onClick={onCancel} disabled={busy}>Cancel</Btn>
        </div>
      </div>
    </Card>
  )
}

function rewardLine(rw) {
  if (!rw) return ''
  return `${plural(rw.qty || 1, 'pack', 'packs')} of ${rw.size || 5} (${rw.quality || 'special'})`
}

export default function AdminChallenges({ payload, setPayload }) {
  const toast = useToast()
  const [form, setForm] = useState(null) // { initial, id }
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState('')

  const remove = async (id) => {
    setBusy(id)
    try { const out = await api.deletePlayerCardChallenge(id); setPayload(out); setConfirm(null); toast?.success?.('Challenge removed') } catch (e) { toast?.error?.(e?.message || 'Could not remove that.') } finally { setBusy('') }
  }
  const list = payload.challenges || []
  return (
    <div className="space-y-4" data-admin-challenges>
      <Card title="Challenges">
        <p className="text-[12.5px] text-pb-faint max-w-prose">Set players a task and pay them a pack for finishing it. A <strong>squad</strong> challenge asks them to pick cards they hold that meet your rules (11 Rares, a squad rated 70, 11 different players). A <strong>collection</strong> asks them to hold a list of cards (everyone from a premiership side). In both, players keep every card. If a squad challenge can be done more than once, the cards used last time can't be used again. Players also make private sets of their own; those pay nothing.</p>
        {!form && <div className="mt-3"><span data-challenge-new><Btn primary onClick={() => setForm({ initial: BLANK, id: null })}>New challenge</Btn></span></div>}
      </Card>

      {form && (
        <ChallengeForm key={form.id || 'new'} payload={payload} initial={form.initial} editingId={form.id}
          onSaved={(out) => { setPayload(out); setForm(null) }} onCancel={() => setForm(null)} />
      )}

      <Card title={`Published (${list.length})`}>
        {list.length === 0 && <div className="text-sm text-pb-faint" data-challenge-empty>No challenges yet. Make one and players will see it under Challenges in their cards.</div>}
        <div className="divide-y divide-pb-hairline2">
          {list.map((c) => (
            <div key={c.id} className="py-3 first:pt-0 last:pb-0" data-challenge-row={c.id}>
              <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-pb-text">{c.title} <span className="ml-1 text-[10.5px] font-mono uppercase tracking-wide2 text-pb-faint">{c.kind}</span>{!c.active && <span className="ml-2 text-[10.5px] font-mono uppercase text-pb-red">Hidden</span>}</div>
                  {c.blurb && <div className="text-[12.5px] text-pb-faint">{c.blurb}</div>}
                  <div className="text-[12.5px] text-pb-dim mt-0.5">{(c.requirements || []).join(' · ')}</div>
                  <div className="text-[12px] text-pb-faint mt-0.5">Pays {rewardLine(c.reward)} · done {plural(c.completions || 0, 'time', 'times')} by {plural(c.players_done || 0, 'player', 'players')}{c.starts_on || c.ends_on ? ` · ${c.starts_on || 'now'} to ${c.ends_on || 'no end'}` : ''}</div>
                </div>
                <div className="flex flex-wrap gap-1.5 shrink-0">
                  <span data-challenge-edit={c.id}><Btn sm onClick={() => setForm({ initial: toForm(c), id: c.id })} disabled={!!busy}>Change</Btn></span>
                  {confirm === c.id
                    ? <><span data-challenge-confirm-delete={c.id}><Btn sm danger onClick={() => remove(c.id)} disabled={busy === c.id}>Yes, remove</Btn></span><Btn sm onClick={() => setConfirm(null)}>Keep</Btn></>
                    : <span data-challenge-delete={c.id}><Btn sm onClick={() => setConfirm(c.id)} disabled={!!busy}>Remove</Btn></span>}
                </div>
              </div>
              {confirm === c.id && <div className="text-[12px] text-pb-faint mt-1">What players already completed stays on record and the packs they earned stay theirs.</div>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
