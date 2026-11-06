// Player Cards, make a pack. An admin names a pack, picks how good it is, how many cards it holds, how many each player gets and who
// gets them, and either hands them out now (they are in the players' hands the next time they open their page) or sets them to arrive on
// a day or a run of days, like each day of a Test match. A pack handed out now can be DESIGNED right here as it is made: the words
// under its name, pictures, colours and layout, with the pack redrawn as you go. The quality ladder is the weighting: every step
// guarantees more Rare or better cards and leans harder to Epic and Legendary (services/player_card_pack_kinds.QUALITIES).
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Btn, Card, Field, Select } from '../../lib/presskit'
import { useToast } from '../../contexts/ToastContext'
import { PackArt } from '../../components/cards/PackOpening'
import { QUALITY_STARS } from '../../components/cards/cardTheme'
import { useCardStyle } from '../../components/cards/useCardStyle'
import { ColourRow, ImageSlot, Switch } from './packDesignParts'

const dayLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const newId = () => (globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `${Date.now().toString(16)}-0000-4000-8000-${Math.random().toString(16).slice(2, 14).padEnd(12, '0')}`)
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
const BLANK_DESIGN = { a: null, b: null, on: null, overlay: 0.25, show_name: true, show_logo: true, art_position: 'center', art_size: 'm' }
const API_KEY = { a: 'color_a', b: 'color_b', on: 'color_on' }

// The ladder. Each step says what it guarantees, and how the cards in it are weighted by tier.
function QualityPicker({ qualities, value, onChange }) {
  return (
    <div role="radiogroup" aria-label="Pack quality" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-quality-picker>
      {qualities.map((q) => (
        <button key={q.key} type="button" role="radio" aria-checked={value === q.key} data-quality={q.key} onClick={() => onChange(q.key)}
          className={`text-left rounded-lg border px-3 py-2 transition ${value === q.key ? 'border-pb-accent bg-pb-surface2' : 'border-pb-hairline2 hover:bg-pb-surface2'}`}>
          <span className="flex items-center gap-2">
            <span className="text-sm font-semibold text-pb-text flex-1">{q.label}</span>
            <span aria-hidden className="text-[11px] tracking-widest" style={{ color: 'var(--pb-accent)' }}>{'★'.repeat(QUALITY_STARS[q.key] || 0) || '·'}</span>
          </span>
          <span className="block text-[12px] text-pb-faint">{q.line}</span>
          <span className="block text-[11.5px] text-pb-dim mt-1">At least {q.rare_plus} of 5 Rare or better</span>
          <span className="block text-[11px] text-pb-faint font-mono">Epic {q.odds.epic}% · Legendary {q.odds.legendary}% · Special {q.special_pct}%</span>
        </button>
      ))}
    </div>
  )
}

// A short checklist of the players who can be given a pack.
function PlayerPicker({ players, picked, setPicked }) {
  const [filter, setFilter] = useState('')
  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return players.filter((p) => !q || (p.display_name || '').toLowerCase().includes(q))
  }, [players, filter])
  const toggle = (id) => setPicked((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next })
  return (
    <div data-player-picker>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a player" aria-label="Find a player to give packs to"
          className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm min-w-0 flex-1" />
        <Btn sm onClick={() => setPicked((cur) => new Set([...cur, ...rows.map((p) => p.id)]))}>Add {rows.length === players.length ? 'everyone' : 'these'}</Btn>
        <Btn sm onClick={() => setPicked(new Set())}>Clear</Btn>
      </div>
      <div className="rounded border pb-hairline divide-y divide-pb-hairline max-h-56 overflow-y-auto">
        {rows.length === 0 && <div className="p-3 text-sm text-pb-faint">No players match.</div>}
        {rows.map((p) => (
          <label key={p.id} className="flex items-center gap-2.5 px-3 py-1.5 cursor-pointer text-sm" data-pick-player={p.id}>
            <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} />
            <span className="min-w-0 truncate text-pb-text">{p.display_name}</span>
          </label>
        ))}
      </div>
      <div className="text-[12px] text-pb-faint mt-1.5" data-picked-count>{plural(picked.size, 'player', 'players')} chosen</div>
    </div>
  )
}

// The design controls for a pack that does not exist yet. Pictures are held here as files (and shown from a local preview) until the
// pack is made; nothing is sent before then.
function DesignControls({ design, setDesign, files, setFiles, previews }) {
  const set = (patch) => setDesign((d) => ({ ...d, ...patch }))
  return (
    <div className="space-y-3 min-w-0" data-create-design>
      <ImageSlot kind="bg" title="Background" hint="Fills the whole pack. A pack is 2 wide by 3 tall, so tall pictures fit best." url={previews.bg} busy={false}
        onPick={(f) => setFiles((x) => ({ ...x, bg: f }))} onRemove={() => setFiles((x) => ({ ...x, bg: null }))} />
      <ImageSlot kind="art" title="Centre picture" hint="Sits on top of the background. A PNG with a see-through background works best." url={previews.art} busy={false}
        onPick={(f) => setFiles((x) => ({ ...x, art: f }))} onRemove={() => setFiles((x) => ({ ...x, art: null }))} />
      <p className="text-[11.5px] text-pb-faint">PNG, JPEG, WebP or GIF, up to 6 MB. Pictures are resized for you.</p>
      {files.bg && (
        <Field label={`How dark the background is (${Math.round(design.overlay * 100)}%)`}>
          <input type="range" min="0" max="0.8" step="0.05" value={design.overlay} aria-label="How dark the background is" data-design-overlay
            onChange={(e) => set({ overlay: Number(e.target.value) })} className="w-full" />
        </Field>
      )}
      {files.art && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Centre picture sits"><Select value={design.art_position} aria-label="Centre picture position" onChange={(e) => set({ art_position: e.target.value })}><option value="top">Near the top</option><option value="center">In the middle</option><option value="bottom">Near the bottom</option></Select></Field>
          <Field label="Centre picture size"><Select value={design.art_size} aria-label="Centre picture size" onChange={(e) => set({ art_size: e.target.value })}><option value="s">Small</option><option value="m">Medium</option><option value="l">Large</option></Select></Field>
        </div>
      )}
      <div className="space-y-2">
        <ColourRow label="Foil colour" value={design.a} onChange={(v) => set({ a: v })} />
        <ColourRow label="Foil shade" value={design.b} onChange={(v) => set({ b: v })} />
        <ColourRow label="Writing" value={design.on} onChange={(v) => set({ on: v })} />
      </div>
      <Switch on={design.show_name} onChange={(v) => set({ show_name: v })} label="Show the pack's name" hint="Switch off to let the picture speak for itself." />
      <Switch on={design.show_logo} onChange={(v) => set({ show_logo: v })} label="Show the club logo" hint="Only when there is no centre picture." />
    </div>
  )
}

export default function CreatePacks({ data, setData }) {
  const toast = useToast()
  const { accent, display } = useCardStyle(data.club)
  const qualities = data.qualities || []
  const sizeLimits = data.pack_size || { default: 5, min: 1, max: 12 }
  const players = useMemo(() => (data.players || []).filter((p) => !p.excluded && !p.hidden), [data.players])
  const [title, setTitle] = useState('')
  const [line, setLine] = useState('')
  const [size, setSize] = useState(sizeLimits.default)
  const [quality, setQuality] = useState('special')
  const [qty, setQty] = useState(1)
  const [audience, setAudience] = useState('all')
  const [picked, setPicked] = useState(() => new Set())
  const [when, setWhen] = useState('now')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [perDay, setPerDay] = useState(true)
  const [designing, setDesigning] = useState(false)
  const [design, setDesign] = useState(BLANK_DESIGN)
  const [files, setFiles] = useState({ bg: null, art: null })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const requestId = useRef(newId())          // one per form fill, so a double click is one gift

  // A local preview of each chosen picture, so the pack shows it before anything is sent.
  const [previews, setPreviews] = useState({ bg: null, art: null })
  useEffect(() => {
    const next = { bg: files.bg ? URL.createObjectURL(files.bg) : null, art: files.art ? URL.createObjectURL(files.art) : null }
    setPreviews(next)
    return () => { Object.values(next).forEach((u) => u && URL.revokeObjectURL(u)) }
  }, [files])

  const sizeOk = Number.isInteger(size) && size >= sizeLimits.min && size <= sizeLimits.max
  const styleSent = useMemo(() => {
    const out = {}
    for (const k of ['a', 'b', 'on']) if (design[k]) out[API_KEY[k]] = design[k]
    if (design.overlay !== BLANK_DESIGN.overlay) out.overlay = design.overlay
    if (!design.show_name) out.show_name = false
    if (!design.show_logo) out.show_logo = false
    if (design.art_position !== BLANK_DESIGN.art_position) out.art_position = design.art_position
    if (design.art_size !== BLANK_DESIGN.art_size) out.art_size = design.art_size
    if (line.trim()) out.line = line.trim()
    return out
  }, [design, line])
  const designed = when === 'now' && (Object.keys(styleSent).length > 0 || !!files.bg || !!files.art)
  const preview = Object.keys(styleSent).length || files.bg || files.art
    ? { ...design, line: line.trim() || null, title: null, background_url: previews.bg, art_url: previews.art } : null

  const recipients = audience === 'all' ? players.length : picked.size
  const ready = title.trim() && sizeOk && (when === 'now' ? recipients > 0 : !!from)
  const q = qualities.find((x) => x.key === quality)
  const maxQty = data.max_gift_qty || 10

  const submit = async (e) => {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true); setDone('')
    try {
      if (when === 'now') {
        const ids = audience === 'players' ? [...picked] : []
        let out
        if (designed) {
          const form = new FormData()
          form.append('title', title.trim()); form.append('quality', quality); form.append('qty', String(qty)); form.append('size', String(size))
          form.append('audience', audience); form.append('player_ids', JSON.stringify(ids)); form.append('request_id', requestId.current)
          form.append('style', JSON.stringify(styleSent))
          if (files.bg) form.append('bg', files.bg)
          if (files.art) form.append('art', files.art)
          out = await api.createPlayerCardGiftDesigned(form)
        } else {
          out = await api.createPlayerCardGift({ title: title.trim(), quality, qty, size, audience, player_ids: ids, request_id: requestId.current })
        }
        const { gift, ...payload } = out
        setData((d) => ({ ...d, ...payload }))
        setDone(`Gave ${plural(gift.packs, 'pack', 'packs')} to ${plural(gift.players, 'player', 'players')}. They find them when they next open their page.`)
        requestId.current = newId()
        setDesign(BLANK_DESIGN); setFiles({ bg: null, art: null }); setLine(''); setDesigning(false)
      } else {
        setData(await api.addPlayerCardEvent({ title: title.trim(), starts_on: from, ends_on: to || null, per_day: perDay, quality }))
        setDone('Scheduled. Players pick one up on each day they open their page.')
      }
      setTitle(''); setFrom(''); setTo('')
    } catch (err) { toast?.error?.(err?.message || 'Could not do that.') } finally { setBusy(false) }
  }
  const removeEvent = async (ev) => {
    try { setData(await api.deletePlayerCardEvent(ev.id)) } catch (err) { toast?.error?.(err?.message || 'Could not remove that.') }
  }
  const qLabel = (k) => qualities.find((x) => x.key === k)?.label || k

  return (
    <Card title="Make a pack">
      <p className="text-[12.5px] text-pb-faint max-w-prose mb-3">Create a pack for any reason, such as a thank you, a win, a Test match or a milestone, and give it out in a minute. Pick how good it is: the better the quality, the more Rare, Epic and Legendary cards you pull and the more often a special card turns up. Make it look the part with your own name, words, pictures and colours. Players open it from their page and keep it until they do.</p>
      <form onSubmit={submit} className="space-y-4" data-create-pack>
        <div className="grid gap-5 sm:grid-cols-[160px_minmax(0,1fr)]">
          <div className="flex flex-col items-center gap-1.5" data-create-preview>
            <PackArt source="custom" label={title.trim() || 'Club pack'} quality={quality} size={sizeOk ? size : sizeLimits.default} design={preview} club={data.club} accent={accent} display={display} width={150} />
            <span className="text-[11.5px] text-pb-faint text-center">{q ? `${q.label} quality` : ''}</span>
          </div>
          <div className="space-y-3 min-w-0">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_110px]">
              <Field label="Name of the pack">
                <input value={title} maxLength={40} onChange={(e) => setTitle(e.target.value)} placeholder="Grand Final winners" aria-label="Name of the pack"
                  className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" />
              </Field>
              <Field label="Cards in the pack">
                <input type="number" inputMode="numeric" min={sizeLimits.min} max={sizeLimits.max} value={Number.isNaN(size) ? '' : size} aria-label="Cards in the pack"
                  onChange={(e) => setSize(e.target.value === '' ? NaN : Number(e.target.value))} className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" />
              </Field>
            </div>
            {!sizeOk && <div role="alert" className="text-[12px]" style={{ color: 'var(--pb-red, #f87171)' }}>A pack holds from {sizeLimits.min} to {sizeLimits.max} cards.</div>}
            {when === 'now' && (
              <Field label="Words under the name">
                <input value={line} maxLength={36} onChange={(e) => setLine(e.target.value)} placeholder="A gift from your club" aria-label="Words under the name"
                  className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" />
              </Field>
            )}
            <Field label="Quality">
              <QualityPicker qualities={qualities} value={quality} onChange={setQuality} />
            </Field>
          </div>
        </div>

        {when === 'now' && (
          <div>
            <button type="button" aria-expanded={designing} data-design-toggle onClick={() => setDesigning((v) => !v)} className="text-sm font-semibold text-pb-accent hover:underline">
              {designing ? 'Hide the design' : 'Design the pack: pictures, colours and layout'}
            </button>
            {designing && <div className="mt-3"><DesignControls design={design} setDesign={setDesign} files={files} setFiles={setFiles} previews={previews} /></div>}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Packs for each player">
            <Select value={qty} aria-label="Packs for each player" onChange={(e) => setQty(Number(e.target.value))}>
              {Array.from({ length: maxQty }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </Field>
          <Field label="Who gets them">
            <Select value={audience} aria-label="Who gets them" onChange={(e) => setAudience(e.target.value)}>
              <option value="all">{`Everyone with a card (${players.length})`}</option>
              <option value="players">Players I choose</option>
            </Select>
          </Field>
        </div>
        {audience === 'players' && <PlayerPicker players={players} picked={picked} setPicked={setPicked} />}

        <fieldset className="space-y-2" data-when>
          <legend className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint mb-1">When</legend>
          <label className="flex items-center gap-2 text-sm"><input type="radio" name="when" checked={when === 'now'} onChange={() => setWhen('now')} data-when-now /> Give them out now</label>
          <label className="flex items-center gap-2 text-sm"><input type="radio" name="when" checked={when === 'later'} onChange={() => setWhen('later')} data-when-later /> Give them to everyone on a day, or each day of a run (a Test match)</label>
          {when === 'later' && (
            <div className="grid gap-3 sm:grid-cols-2 pl-6" data-when-dates>
              <Field label="First day"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="First day" className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" /></Field>
              <Field label="Last day"><input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label="Last day" className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm" /></Field>
              <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={perDay} onChange={(e) => setPerDay(e.target.checked)} data-event-per-day /> One pack on each day (otherwise one for the whole run)</label>
              <p className="text-[12px] text-pb-faint sm:col-span-2">Scheduled packs hold five cards. Give a scheduled pack its own look afterwards in the Pack designs tab.</p>
            </div>
          )}
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Btn type="submit" primary disabled={!ready || busy}>
            {busy ? 'Working…' : when === 'now' ? `Give ${plural(recipients * qty, 'pack', 'packs')} now` : 'Schedule it'}
          </Btn>
          {when === 'now' && recipients > 0 && <span className="text-[12px] text-pb-faint">{plural(qty, 'pack', 'packs')} each to {plural(recipients, 'player', 'players')}{designed ? ', with your design' : ''}</span>}
        </div>
        {done && <div role="status" className="text-sm text-pb-text" data-create-done>{done}</div>}
      </form>

      <h3 className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint mt-6 mb-2">Given lately</h3>
      <div className="rounded border pb-hairline divide-y divide-pb-hairline" data-gift-list>
        {(data.gifts || []).length === 0 && <div className="p-3 text-sm text-pb-faint">Nothing handed out yet.</div>}
        {(data.gifts || []).map((g) => (
          <div key={g.id} className="px-3 py-2" data-gift={g.id}>
            <div className="text-sm text-pb-text">{g.title} <span className="text-pb-faint">· {qLabel(g.quality)} · {g.size || 5} cards</span></div>
            <div className="text-[11.5px] text-pb-faint">{plural(g.packs, 'pack', 'packs')} to {plural(g.players, 'player', 'players')} · {g.opened} opened · {dayLabel(g.created_at.slice(0, 10))}</div>
          </div>
        ))}
      </div>

      <h3 className="font-mono text-[10.5px] tracking-wide2 uppercase text-pb-faint mt-5 mb-2">Scheduled</h3>
      <div className="rounded border pb-hairline divide-y divide-pb-hairline" data-event-list>
        {(data.events || []).length === 0 && <div className="p-3 text-sm text-pb-faint">Nothing scheduled.</div>}
        {(data.events || []).map((ev) => (
          <div key={ev.id} className="flex items-center gap-3 px-3 py-2" data-event={ev.id}>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-pb-text">{ev.title} <span className="text-pb-faint">· {qLabel(ev.quality)}</span></div>
              <div className="text-[11.5px] text-pb-faint">{ev.starts_on === ev.ends_on ? dayLabel(ev.starts_on) : `${dayLabel(ev.starts_on)} to ${dayLabel(ev.ends_on)}`} · {ev.per_day ? 'a pack each day' : 'one pack'}</div>
            </div>
            <Btn sm onClick={() => removeEvent(ev)}>Remove</Btn>
          </div>
        ))}
      </div>
      <p className="text-[12px] text-pb-faint mt-2">A pack already given stays with the player if you remove a scheduled day.</p>
    </Card>
  )
}
