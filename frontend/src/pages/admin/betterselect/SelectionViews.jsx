// The two Selection board views over one shared selection state:
//   • DualRailView — "build the side": Available pool ↔ Selected XI, two
//     balanced columns with a flow divider; a sticky Pool⇄XI switcher on mobile.
//   • TeamSheetView — "finesse & assess": a numbered batting-order spine you
//     draft into from a grid of pool cards.
//
// Both consume a `vm` (view model) the screen builds (slots, pool, actions) and
// the pointer DnD engine (selectionDnd). Player rows show the real role + style
// + a quiet form indicator (selectionMeta.roleLine / FormBars) — never the old
// hardcoded positional hints.
import { useState } from 'react'
import { Icon, Avatar, Dot, Tag } from './ui'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import { useDrag } from './selectionDnd'
import { roleLine, formMeta, spark } from './selectionMeta'

const ROLE_CODES = ['BAT', 'ALL', 'BWL', 'WKT']
const ROLE_LBL = { BAT: 'BAT', ALL: 'ALL', BWL: 'BWL', WKT: 'WK' }

/* ── Form indicator — quiet last-4 sparkline + word ──────────────────────── */
function FormBars({ p, h = 14, w = 3, gap = 2 }) {
  const bars = spark(p.recent)
  const fm = formMeta(p)
  if (!bars.length) return null
  const tok = fm?.token || 'var(--pb-dim)'
  return (
    <span className="inline-flex items-end" style={{ gap, height: h }} title={`Recent: ${(p.recent || []).join(', ')}`}>
      {bars.map((v, i) => (
        <span key={i} style={{ width: w, height: Math.round(h * v), borderRadius: 1, background: tok, opacity: 0.4 + 0.6 * (bars.length > 1 ? i / (bars.length - 1) : 1) }} />
      ))}
    </span>
  )
}
function FormWord({ p }) {
  const fm = formMeta(p)
  if (!fm) return null
  return <span className="font-mono text-[9.5px] font-semibold tracking-wide" style={{ color: fm.token }}>{fm.label}</span>
}
function FormInline({ p }) {
  const fm = formMeta(p)
  const bars = spark(p.recent)
  if (!fm && !bars.length) return null
  return <span className="inline-flex items-center gap-1.5"><FormBars p={p} h={12} />{fm && <FormWord p={p} />}</span>
}

/* ── Availability proportional mini-bar ──────────────────────────────────── */
function AvailMini({ players }) {
  const tally = {}
  players.forEach((p) => { const s = p.availability || 'NO_RESPONSE'; tally[s] = (tally[s] || 0) + 1 })
  const segs = AVAIL_ORDER.filter((s) => tally[s])
  return (
    <div className="flex h-[5px] w-[92px] rounded-full overflow-hidden bg-pb-surface2"
      title={segs.map((s) => `${tally[s]} ${AVAILABILITY[s].label.toLowerCase()}`).join(' · ')}>
      {segs.map((s) => <span key={s} style={{ flexGrow: tally[s], background: AVAILABILITY[s].cssVar, opacity: s === 'NO_RESPONSE' ? 0.5 : 1 }} />)}
    </div>
  )
}

/* ── Shared fixture / balance / size chrome ──────────────────────────────── */
function SizePicker({ value, onChange }) {
  const opts = [[11, '11'], [12, '12'], [13, '13'], [0, 'No limit']]
  return (
    <div className="inline-flex p-[3px] gap-0.5 bg-pb-surface2 rounded-lg border border-pb-hairline whitespace-nowrap">
      {opts.map(([v, l]) => (
        <button key={v} type="button" onClick={() => onChange(v)}
          className={`rounded-md font-display font-semibold text-xs px-2.5 py-1 transition ${v === value ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>{l}</button>
      ))}
    </div>
  )
}
function PickPill({ count, target }) {
  const off = target > 0 && count !== target
  return (
    <span className="font-mono text-xs font-bold px-2.5 py-1 rounded-full whitespace-nowrap"
      style={{ background: off ? 'var(--pb-amber)' : 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: off ? '#1b1205' : 'var(--pb-accent)' }}>
      {count}{target > 0 ? ` / ${target}` : ''} picked
    </span>
  )
}

export function FixtureBar({ vm }) {
  return (
    <div className="rounded-xl px-4 py-2.5 mb-2.5 border"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 9%, var(--pb-surface))', borderColor: 'color-mix(in srgb, var(--pb-accent) 26%, transparent)' }}>
      <div className="flex items-center justify-between gap-3">{vm.contextLeft}</div>
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end sm:justify-between gap-x-3 gap-y-2 mt-1">
        <div className="min-w-0">
          {vm.teamName && <div className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.16em] text-pb-accent leading-none mb-1">{vm.teamName}</div>}
          <h2 className="font-display font-bold text-[20px] leading-tight break-words">{vm.title}</h2>
          {vm.sub && <div className="text-[13.5px] text-pb-dim mt-0.5">{vm.sub}</div>}
        </div>
        {vm.canEdit && (
          <div className="flex flex-wrap items-center gap-2.5">
            <SizePicker value={vm.format} onChange={vm.changeFormat} />
            <PickPill count={vm.count} target={vm.target} />
          </div>
        )}
      </div>
    </div>
  )
}

export function BalanceStrip({ vm }) {
  const b = vm.balance
  const cap = vm.capId && vm.filledSet.has(vm.capId) ? vm.poolById[vm.capId]?.display_name : null
  const wk = vm.wkId && vm.filledSet.has(vm.wkId) ? vm.poolById[vm.wkId]?.display_name : null
  return (
    <div className="pb-card rounded-xl px-4 py-2 mb-2.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[13px]">
      {ROLE_CODES.map((c) => {
        const low = (c === 'BWL' && b.lightBowling) || (c === 'WKT' && !b.hasKeeper)
        return (
          <span key={c} className="inline-flex items-center gap-1.5">
            <span className="font-mono text-[10px] tracking-wide2" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{ROLE_LBL[c]}</span>
            <b className="pb-num" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b[c]}</b>
          </span>
        )
      })}
      <span className="h-4 w-px bg-pb-hairline2" />
      <span className="inline-flex items-center gap-1.5 text-[12px]" style={{ color: cap ? 'var(--pb-text)' : 'var(--pb-faint)' }}>
        <Tag tone={cap ? 'accent' : 'faint'}>C</Tag>{cap || 'No captain'}
      </span>
      <span className="inline-flex items-center gap-1.5 text-[12px]" style={{ color: wk ? 'var(--pb-text)' : 'var(--pb-amber)' }}>
        <Tag tone={wk ? 'amber' : 'faint'}>WK</Tag>{wk || 'No keeper named'}
      </span>
      {b.lightBowling && <span className="ml-auto text-[12px] text-pb-amber inline-flex items-center gap-1.5"><Icon name="info" size={13} /> Light on bowling</span>}
    </div>
  )
}

/* ── Captain / keeper / remove control cluster ───────────────────────────── */
function SlotControls({ vm, id, idx }) {
  if (!vm.canEdit) return null
  return (
    <div className="flex items-center gap-1 shrink-0">
      <button onClick={(e) => { e.stopPropagation(); vm.toggleCap(id) }} title="Captain"
        className={`w-[26px] h-[26px] rounded-md text-[10px] font-bold font-mono ${id === vm.capId ? 'bg-pb-accent text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>C</button>
      <button onClick={(e) => { e.stopPropagation(); vm.toggleWk(id) }} title="Wicket-keeper"
        className={`w-[26px] h-[26px] rounded-md text-[10px] font-bold font-mono ${id === vm.wkId ? 'bg-pb-amber text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>WK</button>
      <button onClick={(e) => { e.stopPropagation(); vm.removeAt(idx) }} title="Remove"
        className="w-[26px] h-[26px] rounded-md flex items-center justify-center text-pb-faintest hover:text-pb-red hover:bg-pb-red/10"><Icon name="close" size={14} /></button>
    </div>
  )
}

/* ══ Dual rail ══════════════════════════════════════════════════════════════ */
function DualCard({ p, kind, idx, vm, drag }) {
  const meta = AVAILABILITY[p.availability] || AVAILABILITY.NO_RESPONSE
  const unavail = p.availability === 'UNAVAILABLE'
  const clash = p.clash?.length > 0
  // A call-up (higher grade taking a player from a lower XI) stays pickable;
  // only a same/higher-grade clash blocks.
  const callUp = clash && !p.clash_blocks
  const blocked = unavail || (clash && p.clash_blocks)
  const dragItem = kind === 'pool' ? { kind: 'pool', player: p } : { kind: 'slot', idx, player: p }
  const interactive = vm.canEdit && !blocked
  return (
    <div className={`group relative shrink-0 flex items-center gap-2.5 pl-3.5 pr-3 py-1.5 rounded-xl border bg-pb-surface2 overflow-hidden transition-colors ${blocked ? 'opacity-50 cursor-not-allowed' : interactive ? 'cursor-pointer hover:border-pb-accent/45' : ''} border-pb-hairline`}
      {...(kind === 'pool' && interactive ? drag.bind(dragItem) : {})}
      onClick={kind === 'pool' && interactive ? drag.clickGuard(() => vm.tapPlayer(p)) : undefined}>
      <span className="absolute left-0 top-0 bottom-0 w-1" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : meta.cssVar }} />
      {kind === 'slot' && vm.canEdit && (
        <span {...drag.bind(dragItem)} className="cursor-grab text-pb-faintest shrink-0" style={{ touchAction: 'none' }} title="Drag to reorder / off"><Icon name="grip" size={14} /></span>
      )}
      <span className="relative shrink-0">
        <Avatar player={p} size={34} />
        <span className="absolute -right-px -bottom-px"><Dot status={p.availability} size={10} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[14px] font-semibold truncate">{p.display_name}</span>
          {p.id === vm.capId && <Tag>C</Tag>}{p.id === vm.wkId && <Tag tone="amber">WK</Tag>}
          {p.squads?.[0] && (kind === 'pool') && <Tag tone={p.squad_match ? 'accent' : 'faint'}>{vm.squadShort(p.squads[0])}</Tag>}
        </div>
        <div className="text-[12px] text-pb-dim mt-0.5 truncate">{roleLine(p)}</div>
        {clash
          ? (callUp
              ? <div className="text-[11px] text-pb-amber mt-0.5 truncate">↑ Call-up from {p.clash.join(', ')}</div>
              : <div className="text-[11px] text-pb-red mt-0.5 truncate">⛔ Picked for {p.clash.join(', ')}</div>)
          : p.availability_reason && <div className="text-[11px] text-pb-faint mt-0.5 truncate">{p.availability_reason}</div>}
      </div>
      {kind === 'pool' ? (
        <div className="flex flex-col items-end gap-0.5 shrink-0">
          <FormBars p={p} h={16} />
          <FormWord p={p} />
        </div>
      ) : <FormBars p={p} h={16} />}
      {kind === 'pool'
        ? (!blocked && <span className="text-pb-faintest shrink-0 group-hover:text-pb-accent"><Icon name="arrow" size={16} /></span>)
        : <SlotControls vm={vm} id={p.id} idx={idx} />}
    </div>
  )
}

function DualSlot({ i, id, vm, drag }) {
  const p = id ? vm.poolById[id] : null
  const isFocus = vm.focus === i
  const hovered = drag.hover === 'slot:' + i
  return (
    <div className="flex items-stretch gap-2 shrink-0">
      <span className="font-display font-bold text-[18px] text-pb-faintest w-[22px] flex items-center justify-center shrink-0 pb-num">{i + 1}</span>
      <div className="flex-1 min-w-0" data-drop-kind="slot" data-drop-idx={i} onClick={() => !p && vm.canEdit && vm.setFocus(i)}>
        {p
          ? <DualCard p={p} kind="slot" idx={i} vm={vm} drag={drag} />
          : (
            <div className={`flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-dashed min-h-[50px] text-[13px] transition-colors ${hovered ? 'border-pb-accent text-pb-accent bg-pb-accent/10 border-solid' : isFocus ? 'border-pb-accent text-pb-accent bg-pb-accent/[0.06]' : 'border-pb-hairline2 text-pb-faintest'}`}>
              <Icon name="plus" size={15} /><span>{isFocus ? 'Tap a player in the pool' : hovered ? 'Drop here' : 'Open slot'}</span>
            </div>
          )}
      </div>
    </div>
  )
}

export function DualRailView({ vm }) {
  const drag = useDrag()
  const [mpanel, setMpanel] = useState('pool')
  const poolHover = drag.hover === 'pool'

  return (
    <div>
      <FixtureBar vm={vm} />
      <BalanceStrip vm={vm} />

      {/* Mobile Pool ⇄ XI switcher */}
      <div className="grid grid-cols-2 gap-1.5 sticky top-[56px] z-20 mb-3 p-1.5 pb-card rounded-xl lg:hidden">
        <button onClick={() => setMpanel('pool')}
          className={`inline-flex items-center justify-center gap-1.5 py-2.5 rounded-lg font-display font-semibold text-[13.5px] ${mpanel === 'pool' ? 'bg-pb-accent/14 text-pb-accent' : 'text-pb-faint'}`}><Icon name="player" size={15} />Available pool</button>
        <button onClick={() => setMpanel('xi')}
          className={`inline-flex items-center justify-center gap-1.5 py-2.5 rounded-lg font-display font-semibold text-[13.5px] ${mpanel === 'xi' ? 'bg-pb-accent/14 text-pb-accent' : 'text-pb-faint'}`}><Icon name="selection" size={15} />Your XI · {vm.count}/{vm.target || '∞'}</button>
      </div>

      <div className="grid items-start gap-3.5 lg:gap-0 lg:grid-cols-[minmax(0,1fr)_56px_minmax(0,1fr)]">
        {/* Pool */}
        <section className={`pb-card rounded-xl flex flex-col min-h-0 min-w-0 ${mpanel === 'pool' ? '' : 'hidden'} lg:flex`}>
          <header className="px-4 py-3 border-b pb-hairline flex flex-col gap-2.5">
            <div className="flex items-center justify-between gap-2.5">
              <h3 className="font-display font-bold text-[15px]">Available pool</h3>
              <div className="flex items-center gap-2.5"><AvailMini players={vm.pool} /><span className="font-mono text-[11px] text-pb-faint pb-num">{vm.pool.length}</span></div>
            </div>
            {vm.filterBar}
          </header>
          <div data-drop-kind="pool"
            className={`flex flex-col gap-1.5 p-2 overflow-auto pb-scroll max-h-none lg:max-h-[calc(100vh-300px)] rounded-b-xl ${poolHover ? 'bg-pb-red/[0.06] shadow-[inset_0_0_0_2px_color-mix(in_srgb,var(--pb-red)_35%,transparent)]' : ''}`}>
            {vm.pool.map((p) => <DualCard key={p.id} p={p} kind="pool" vm={vm} drag={drag} />)}
            {vm.pool.length === 0 && <div className="p-4 text-pb-faint text-sm">No players match.</div>}
            {poolHover && <div className="sticky bottom-1.5 mx-auto mt-1.5 px-3.5 py-1.5 rounded-full text-xs text-pb-red bg-pb-surface border border-dashed border-pb-red/40">Drop here to remove from XI</div>}
          </div>
        </section>

        {/* Flow divider */}
        <div className="hidden lg:flex flex-col items-center self-stretch py-16 gap-2" aria-hidden="true">
          <span className="flex-1 w-px" style={{ background: 'linear-gradient(var(--pb-hairline), transparent)' }} />
          <span className="w-[30px] h-[30px] rounded-full inline-flex items-center justify-center text-pb-accent" style={{ background: 'color-mix(in srgb, var(--pb-accent) 12%, var(--pb-surface))', border: '1px solid color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}><Icon name="arrow" size={15} /></span>
          <span className="flex-1 w-px" style={{ background: 'linear-gradient(transparent, var(--pb-hairline))' }} />
        </div>

        {/* XI */}
        <section className={`pb-card rounded-xl flex flex-col min-h-0 min-w-0 ${mpanel === 'xi' ? '' : 'hidden'} lg:flex`}>
          <header className="px-4 py-3 border-b pb-hairline flex items-center justify-between">
            <h3 className="font-display font-bold text-[15px]">Selected XI <span className="text-pb-faint font-medium text-[13px]">· batting order</span></h3>
            {vm.canEdit && (
              <div className="flex items-center gap-2">
                {vm.canAutofill && vm.hasPrev && <button onClick={vm.fillLastWeek} title="Seed empty slots from last week's XI, then top up" className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="bolt" size={13} />Last week</button>}
                {vm.canAutofill && <button onClick={vm.autofill} className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="bolt" size={13} />Auto-fill</button>}
                <button onClick={vm.clearXI} className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="reset" size={13} />Clear</button>
              </div>
            )}
          </header>
          <div className="flex flex-col gap-1.5 p-2 overflow-auto pb-scroll max-h-none lg:max-h-[calc(100vh-300px)]">
            {vm.slots.map((id, i) => <DualSlot key={i} i={i} id={id} vm={vm} drag={drag} />)}
            {vm.format === 0 && <div className="px-4 py-3 rounded-xl border border-dashed border-pb-hairline2 text-center text-[12px] text-pb-faintest">Tap a player to add to the order</div>}
          </div>
        </section>
      </div>
    </div>
  )
}

/* ══ Team sheet ═════════════════════════════════════════════════════════════ */
function SheetRow({ i, id, vm, drag }) {
  const p = id ? vm.poolById[id] : null
  const isFocus = vm.focus === i
  const hovered = drag.hover === 'slot:' + i
  const zebra = p && i % 2 === 1
  return (
    <div data-drop-kind="slot" data-drop-idx={i} onClick={() => !p && vm.canEdit && vm.setFocus(i)}
      className={`flex items-center gap-3 px-4 sm:px-5 min-h-[50px] py-1.5 border-b border-pb-hairline transition-colors ${!p ? 'cursor-pointer' : ''} ${hovered ? 'bg-pb-accent/10 shadow-[inset_3px_0_0_var(--pb-accent)]' : isFocus && !p ? 'bg-pb-accent/[0.06] shadow-[inset_3px_0_0_var(--pb-accent)]' : zebra ? 'bg-pb-surface2/45' : ''}`}>
      <span className="font-display font-bold text-[25px] leading-none w-7 text-center shrink-0 pb-num tracking-tight" style={{ color: p ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>{i + 1}</span>
      {p ? (
        <>
          {vm.canEdit && <span {...drag.bind({ kind: 'slot', idx: i, player: p })} className="cursor-grab text-pb-faintest shrink-0" style={{ touchAction: 'none' }} title="Drag to reorder / off"><Icon name="grip" size={15} /></span>}
          <span className="relative shrink-0">
            <Avatar player={p} size={34} />
            <span className="absolute -right-px -bottom-px"><Dot status={p.availability} size={11} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-display font-semibold text-[16.5px] tracking-tight truncate">{p.display_name}</span>
              {id === vm.capId && <Tag>C</Tag>}{id === vm.wkId && <Tag tone="amber">WK</Tag>}
            </div>
            <div className="flex items-center gap-2 mt-0.5 min-w-0">
              <span className="text-[12.5px] text-pb-dim truncate">{roleLine(p)}</span>
              <span className="shrink-0"><FormInline p={p} /></span>
            </div>
          </div>
          <SlotControls vm={vm} id={id} idx={i} />
        </>
      ) : (
        <span className="flex-1 font-display text-[14px]" style={{ color: isFocus ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>
          {isFocus ? 'Tap a card below to draft here' : hovered ? 'Drop to draft' : 'Open slot'}
        </span>
      )}
    </div>
  )
}

function TrayCard({ p, vm, drag }) {
  const meta = AVAILABILITY[p.availability] || AVAILABILITY.NO_RESPONSE
  const unavail = p.availability === 'UNAVAILABLE'
  const clash = p.clash?.length > 0
  const callUp = clash && !p.clash_blocks
  const blocked = unavail || (clash && p.clash_blocks)
  const interactive = vm.canEdit && !blocked
  return (
    <div className={`group relative flex items-center gap-3 pl-4 pr-3 py-2.5 rounded-xl border border-pb-hairline bg-pb-surface2 overflow-hidden transition-colors ${blocked ? 'opacity-50 cursor-not-allowed' : interactive ? 'cursor-pointer hover:border-pb-accent/45' : ''}`}
      {...(interactive ? drag.bind({ kind: 'pool', player: p }) : {})}
      onClick={interactive ? drag.clickGuard(() => vm.tapPlayer(p)) : undefined}>
      <span className="absolute left-0 top-0 bottom-0 w-1" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : meta.cssVar }} />
      <span className="relative shrink-0">
        <Avatar player={p} size={34} />
        <span className="absolute -right-px -bottom-px"><Dot status={p.availability} size={10} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[13.5px] font-semibold truncate">{p.display_name}</span>
          {p.squads?.[0] && <Tag tone={p.squad_match ? 'accent' : 'faint'}>{vm.squadShort(p.squads[0])}</Tag>}
        </div>
        <div className="text-[11.5px] text-pb-dim mt-0.5 truncate">{roleLine(p)}</div>
        {clash
          ? (callUp
              ? <div className="text-[10.5px] text-pb-amber mt-0.5 truncate">↑ Call-up from {p.clash.join(', ')}</div>
              : <div className="text-[10.5px] text-pb-red mt-0.5 truncate">⛔ Picked for {p.clash.join(', ')}</div>)
          : <div className="mt-1"><FormInline p={p} /></div>}
      </div>
      {!blocked && <span className="text-pb-faintest shrink-0 group-hover:text-pb-accent transition-colors"><Icon name="plus" size={14} /></span>}
    </div>
  )
}

export function TeamSheetView({ vm }) {
  const drag = useDrag()
  const b = vm.balance
  const poolHover = drag.hover === 'pool'
  const cap = vm.capId && vm.filledSet.has(vm.capId) ? vm.poolById[vm.capId]?.display_name : null
  const wk = vm.wkId && vm.filledSet.has(vm.wkId) ? vm.poolById[vm.wkId]?.display_name : null

  return (
    <div>
      {/* Masthead */}
      <div className="px-5 sm:px-6 py-3.5 rounded-t-2xl border border-b-0 pb-hairline"
        style={{ background: 'linear-gradient(180deg, color-mix(in srgb, var(--pb-accent) 14%, var(--pb-surface)), var(--pb-surface))' }}>
        {vm.contextLeft && <div className="flex items-center gap-3 mb-3">{vm.contextLeft}</div>}
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end sm:justify-between gap-x-7 gap-y-3">
        <div className="min-w-0 sm:flex-1 flex flex-col gap-0.5">
          <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-pb-accent">{vm.teamName || vm.kicker}</div>
          <h2 className="font-display font-bold tracking-tight leading-tight m-0 break-words" style={{ fontSize: 'clamp(21px, 2.4vw, 26px)' }}>{vm.title}</h2>
          {vm.sub && <div className="text-[13px] text-pb-dim">{vm.sub}</div>}
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {vm.canEdit && <SizePicker value={vm.format} onChange={vm.changeFormat} />}
          <div className="font-display flex items-baseline gap-1"><b className="text-[38px] leading-none text-pb-accent font-bold pb-num">{vm.count}</b><span className="text-[17px] text-pb-faint">/ {vm.target || '∞'}</span></div>
          <div className="hidden sm:flex gap-3.5 font-display">
            {ROLE_CODES.map((c) => {
              const low = (c === 'BWL' && b.lightBowling) || (c === 'WKT' && !b.hasKeeper)
              return (
                <span key={c} className="flex flex-col items-center">
                  <i className="not-italic text-[12px] tracking-wide2 uppercase" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{ROLE_LBL[c]}</i>
                  <b className="text-[24px] leading-none pb-num" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b[c]}</b>
                </span>
              )
            })}
          </div>
        </div>
        </div>
      </div>

      {/* The sheet */}
      <div className="rounded-b-2xl border border-t-0 pb-hairline bg-pb-surface overflow-hidden mb-4">
        <div className="flex items-center justify-between px-5 py-2.5" style={{ borderBottom: '2px solid var(--pb-hairline2)' }}>
          <span className="font-display font-bold text-[15px] tracking-tight">Batting order</span>
          {vm.canEdit && (
            <div className="flex items-center gap-2">
              {vm.canAutofill && vm.hasPrev && <button onClick={vm.fillLastWeek} title="Seed empty slots from last week's XI, then top up" className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="bolt" size={13} />Last week</button>}
              {vm.canAutofill && <button onClick={vm.autofill} className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="bolt" size={13} />Auto-fill</button>}
              <button onClick={vm.clearXI} className="inline-flex items-center gap-1.5 border border-pb-hairline2 text-pb-dim hover:text-pb-text rounded-lg px-2.5 py-1.5 text-[12px] font-display"><Icon name="reset" size={13} />Clear</button>
            </div>
          )}
        </div>
        <div>
          {vm.slots.map((id, i) => <SheetRow key={i} i={i} id={id} vm={vm} drag={drag} />)}
          {vm.format === 0 && <div className="px-5 py-4 text-center text-[12.5px] text-pb-faintest">Tap a card below to add to the order</div>}
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 px-5 py-2.5 text-[13px]" style={{ borderTop: '2px solid var(--pb-hairline2)' }}>
          <span className="inline-flex items-center gap-1.5" style={{ color: cap ? 'var(--pb-text)' : 'var(--pb-faint)' }}><Tag tone={cap ? 'accent' : 'faint'}>C</Tag>{cap || 'No captain named'}</span>
          <span className="inline-flex items-center gap-1.5" style={{ color: wk ? 'var(--pb-text)' : 'var(--pb-amber)' }}><Tag tone={wk ? 'amber' : 'faint'}>WK</Tag>{wk || 'No keeper named'}</span>
          {b.lightBowling && <span className="inline-flex items-center gap-1.5 text-pb-amber"><Icon name="info" size={13} /> Light on bowling</span>}
        </div>
      </div>

      {/* Draft pool */}
      <div className="pb-card rounded-2xl p-4 sm:p-[18px]">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-3.5">
          <div className="flex items-baseline gap-2.5">
            <h3 className="font-display font-bold text-[16px] tracking-tight m-0">Draft pool</h3>
            <span className="font-mono text-[11.5px] text-pb-faint hidden sm:inline">tap a card to draft · or drag up onto a slot</span>
          </div>
          <div className="w-full sm:w-[min(440px,100%)]">{vm.filterBar}</div>
        </div>
        <div data-drop-kind="pool"
          className={`grid gap-2.5 rounded-xl ${poolHover ? 'bg-pb-red/[0.05] shadow-[inset_0_0_0_2px_color-mix(in_srgb,var(--pb-red)_35%,transparent)]' : ''}`}
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(232px, 1fr))' }}>
          {vm.pool.map((p) => <TrayCard key={p.id} p={p} vm={vm} drag={drag} />)}
          {vm.pool.length === 0 && <div className="p-4 text-pb-faint text-sm">No players match.</div>}
        </div>
        {poolHover && <div className="mt-2.5 mx-auto w-max px-3.5 py-1.5 rounded-full text-xs text-pb-red bg-pb-surface border border-dashed border-pb-red/40">Drop here to remove from the XI</div>}
      </div>
    </div>
  )
}
