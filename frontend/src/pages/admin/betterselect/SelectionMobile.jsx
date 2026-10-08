// The Selection board's phone pieces. The board was built for a desk: two
// columns, a 14px grip to drag with, three 26px buttons on every row, and a
// "Tap a player in the pool" hint that sent you to another tab to search. On a
// phone that meant switching panels to find someone, switching back to see where
// they went, and dragging with a thumb to change a batting order.
//
//   • AddPlayersSheet — search the whole club and add in one place, without
//     leaving the XI. Stays open so a side can be built in a run of taps.
//   • SlotSheet       — everything a batting-order row can do, in 52px buttons.
//   • MobileBar       — pinned to the bottom: Pool / XI switch (or Add) + Confirm.
//   • BottomSheet     — the shared shell, sized to the VISUAL viewport so the
//     on-screen keyboard does not cover the list.
//
// Every one of these is below `lg` only; the desk layout is untouched.
import { useState, useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { AVAILABILITY, availRank } from '../../../lib/availability'
import { Icon, Avatar, Dot, Tag } from './ui'
import { roleLine, nameMatches, alsoInLine, dropInLine } from './selectionMeta'
import { FlagTags, RuleNotes, AgeTag } from './SelectionViews'

// The part of the screen that is actually visible. With the keyboard up, a phone
// browser leaves the layout viewport alone and shrinks only this, so a sheet
// pinned to `bottom: 0` of the layout would sit behind the keyboard.
function useVisualViewport() {
  const read = () => {
    const v = typeof window !== 'undefined' ? window.visualViewport : null
    return v ? { h: Math.round(v.height), top: Math.round(v.offsetTop) } : { h: typeof window !== 'undefined' ? window.innerHeight : 800, top: 0 }
  }
  const [vp, setVp] = useState(read)
  useEffect(() => {
    const v = window.visualViewport
    const on = () => setVp(read())
    v?.addEventListener('resize', on)
    v?.addEventListener('scroll', on)
    window.addEventListener('resize', on)
    return () => {
      v?.removeEventListener('resize', on)
      v?.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
    }
  }, [])
  return vp
}

export function BottomSheet({ title, subtitle, onClose, tall = false, children, footer, testId }) {
  const vp = useVisualViewport()
  // The page behind must not scroll while a sheet is up.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={title} data-testid={testId}
      onClick={onClose}
      style={{ position: 'fixed', left: 0, right: 0, top: vp.top, height: vp.h, zIndex: 60 }}
      className="flex items-end bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()}
        className={`w-full flex flex-col bg-pb-surface rounded-t-2xl border border-b-0 border-pb-hairline2 shadow-2xl overflow-hidden ${tall ? 'h-[calc(100%-12px)]' : 'max-h-[88%]'}`}>
        <div className="flex items-center gap-3 px-4 py-3 border-b pb-hairline shrink-0">
          <div className="flex-1 min-w-0">
            <div className="font-display font-bold text-[17px] truncate">{title}</div>
            {subtitle && <div className="text-[12px] text-pb-dim truncate">{subtitle}</div>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close"
            className="w-10 h-10 -mr-2 inline-flex items-center justify-center text-pb-faint hover:text-pb-text"><Icon name="close" size={18} /></button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto pb-scroll overscroll-contain">{children}</div>
        {footer && <div className="shrink-0 border-t pb-hairline px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

/* ── Search the club and add to the XI ───────────────────────────────────── */
function AddRow({ p, onAdd }) {
  const fmt = useAdminNameFormat()
  const meta = AVAILABILITY[p.availability] || AVAILABILITY.NO_RESPONSE
  const blocked = p.clash?.length > 0 && p.clash_blocks
  const callUp = p.clash?.length > 0 && !p.clash_blocks
  return (
    <button type="button" onClick={() => onAdd(p)} disabled={blocked} data-add-row
      className={`w-full text-left flex items-center gap-3 px-4 py-2.5 min-h-[60px] border-b pb-hairline transition-colors ${blocked ? 'opacity-50' : 'active:bg-pb-surface2'}`}>
      <span className="relative shrink-0">
        <Avatar player={p} size={38} noLink />
        <span className="absolute -right-px -bottom-px"><Dot status={p.availability} size={11} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
      </span>
      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-1.5 min-w-0">
          <span className="text-[15px] font-semibold truncate">{fmt(p.display_name)}</span>
          <AgeTag p={p} /><FlagTags p={p} />
        </span>
        <span className="block text-[12px] text-pb-dim truncate">
          <span style={{ color: p.availability === 'NO_RESPONSE' ? undefined : meta.cssVar }}>{meta.label}</span>
          {' · '}{roleLine(p)}
        </span>
        {blocked
          ? <span className="block text-[11px] text-pb-red truncate">⛔ Picked for {p.clash.join(', ')}</span>
          : callUp
            ? <span className="block text-[11px] text-pb-amber truncate">↑ Call-up from {p.clash.join(', ')}</span>
            : alsoInLine(p)
              ? <span className="block text-[11px] text-pb-amber truncate">Also in {alsoInLine(p)}</span>
              : dropInLine(p)
                ? <span className="block text-[11px] text-pb-accent truncate" data-drop-in>↓ {dropInLine(p)}</span>
                : null}
        <RuleNotes p={p} />
      </span>
      {!blocked && (
        <span className="shrink-0 w-9 h-9 rounded-full inline-flex items-center justify-center bg-pb-accent/12 text-pb-accent"><Icon name="plus" size={16} /></span>
      )}
    </button>
  )
}

export function AddPlayersSheet({ vm, onClose }) {
  const fmt = useAdminNameFormat()
  const [q, setQ] = useState('')
  const [hideUnavail, setHideUnavail] = useState(false)
  const [note, setNote] = useState(null)
  const lastTapped = useRef(null)
  const inputRef = useRef(null)
  const full = vm.target > 0 && vm.count >= vm.target

  // Search reaches everyone not yet picked, ignoring the pool's own filters and
  // its "played within N years" window: a name typed in is someone the selector
  // is looking for. With nothing typed it is the pool as the Pool tab shows it.
  const list = useMemo(() => {
    let rows = q.trim()
      ? vm.available.filter((p) => nameMatches(p.display_name, q))
        .sort((a, b) => availRank(a.availability) - availRank(b.availability) || (a.display_name || '').localeCompare(b.display_name || ''))
      : vm.pool
    if (hideUnavail) rows = rows.filter((p) => p.availability !== 'UNAVAILABLE')
    return rows
  }, [q, vm.available, vm.pool, hideUnavail])

  // Say where the tap landed, once the board has actually taken it.
  useEffect(() => {
    const p = lastTapped.current
    if (!p) return
    const at = vm.slots.indexOf(p.id)
    if (at === -1) return
    lastTapped.current = null
    setNote(`${fmt(p.display_name)} added at ${at + 1}`)
  }, [vm.slots]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!note) return undefined
    const t = setTimeout(() => setNote(null), 2600)
    return () => clearTimeout(t)
  }, [note])

  const add = (p) => { lastTapped.current = p; vm.tapPlayer(p) }

  return (
    <BottomSheet tall testId="add-players-sheet" onClose={onClose}
      title="Add players"
      subtitle={`${vm.count}${vm.target > 0 ? ` / ${vm.target}` : ''} picked${full ? ' · side is full' : ''}`}
      footer={<button type="button" onClick={onClose} data-add-done
        className="w-full min-h-[48px] rounded-xl font-display font-semibold text-[14.5px] bg-pb-accent text-pb-bg">
        Done{vm.count ? ` (${vm.count}${vm.target > 0 ? `/${vm.target}` : ''})` : ''}
      </button>}>
      <div className="sticky top-0 z-10 bg-pb-surface px-4 pt-3 pb-2 border-b pb-hairline">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-pb-faint pointer-events-none"><Icon name="search" size={16} /></span>
          <input ref={inputRef} autoFocus type="text" role="searchbox" inputMode="search" enterKeyHint="search"
            autoComplete="off" autoCorrect="off" spellCheck={false}
            value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name…" aria-label="Search players"
            className="w-full h-12 pl-10 pr-10 rounded-xl bg-pb-surface2 border border-pb-hairline2 text-[16px] text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-pb-accent" />
          {q && (
            <button type="button" onClick={() => { setQ(''); inputRef.current?.focus() }} aria-label="Clear search"
              className="absolute right-1 top-1/2 -translate-y-1/2 w-10 h-10 inline-flex items-center justify-center text-pb-faint"><Icon name="close" size={16} /></button>
          )}
        </div>
        <div className="flex items-center gap-2 mt-2 text-[12px] text-pb-faint min-h-[32px]">
          <button type="button" onClick={() => setHideUnavail((v) => !v)} aria-pressed={hideUnavail}
            className={`rounded-full border px-3 py-1.5 text-[12px] font-medium ${hideUnavail ? 'border-pb-accent text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim'}`}>
            Hide unavailable
          </button>
          <span className="ml-auto pb-num" data-add-count>{list.length} {q.trim() ? 'found' : 'in the pool'}</span>
        </div>
        {note && <div role="status" data-add-note className="mt-2 rounded-lg px-3 py-2 text-[12.5px] font-medium" style={{ background: 'color-mix(in srgb, var(--pb-positive) 14%, var(--pb-surface))', color: 'var(--pb-positive)' }}>✓ {note}</div>}
      </div>
      {list.map((p) => <AddRow key={p.id} p={p} onAdd={add} />)}
      {list.length === 0 && (
        <div className="px-6 py-10 text-center text-pb-faint text-[13.5px]">
          {q.trim() ? `Nobody called “${q.trim()}” is left to pick.` : 'Nobody in the pool.'}
          {!q.trim() && vm.available.length > 0 && <div className="mt-1 text-[12px]">Type a name to search everyone not yet picked.</div>}
        </div>
      )}
    </BottomSheet>
  )
}

/* ── One batting-order row's actions ─────────────────────────────────────── */
function SheetAction({ icon, rotate, children, onClick, disabled, danger, on, to }) {
  const cls = `w-full flex items-center gap-3.5 px-4 min-h-[54px] text-left text-[15px] font-medium border-b pb-hairline transition-colors ${disabled ? 'opacity-35' : 'active:bg-pb-surface2'} ${danger ? 'text-pb-red' : on ? 'text-pb-accent' : 'text-pb-text'}`
  const inner = <><Icon name={icon} size={18} className="shrink-0" style={rotate ? { transform: `rotate(${rotate}deg)` } : undefined} /><span className="flex-1 min-w-0 truncate">{children}</span></>
  if (to) return <Link to={to} className={cls}>{inner}</Link>
  return <button type="button" onClick={onClick} disabled={disabled} className={cls}>{inner}</button>
}

export function SlotSheet({ vm, idx, onClose }) {
  const fmt = useAdminNameFormat()
  const id = vm.slots[idx]
  const p = id ? vm.poolById[id] : null
  if (!p) return null
  const isCap = vm.capId === id
  const isWk = vm.wkId === id
  const done = (fn) => () => { fn(); onClose() }
  const last = vm.slots.length - 1
  return (
    <BottomSheet testId="slot-sheet" onClose={onClose}
      title={fmt(p.display_name)} subtitle={`Batting ${idx + 1}${isCap ? ' · captain' : ''}${isWk ? ' · keeper' : ''}`}>
      <SheetAction icon="arrow" rotate={-90} disabled={idx === 0} onClick={done(() => vm.swapSlots(idx, idx - 1))}>{idx === 0 ? 'Move up (already batting first)' : `Move up to ${idx}`}</SheetAction>
      <SheetAction icon="arrow" rotate={90} disabled={idx >= last} onClick={done(() => vm.swapSlots(idx, idx + 1))}>{idx >= last ? 'Move down (already last)' : `Move down to ${idx + 2}`}</SheetAction>
      <SheetAction icon="flag" on={isCap} onClick={done(() => vm.toggleCap(id))}>{isCap ? 'Remove as captain' : 'Make captain'}</SheetAction>
      <SheetAction icon="player" on={isWk} onClick={done(() => vm.toggleWk(id))}>{isWk ? 'Remove as keeper' : 'Make wicket-keeper'}</SheetAction>
      <SheetAction icon="availability" onClick={done(() => vm.setAvailEdit(p))}>Change availability</SheetAction>
      <SheetAction icon="player" to={`/admin/betterselect/players?player=${p.id}`}>Open profile</SheetAction>
      <SheetAction icon="trash" danger onClick={done(() => vm.removeAt(idx))}>Take out of the XI</SheetAction>
    </BottomSheet>
  )
}

/* ── The pinned bottom bar ───────────────────────────────────────────────── */
export const MOBILE_BAR_PX = 68

export function MobileBar({ vm, confirm }) {
  // The Team sheet's bar is "Add players", which a view-only user cannot use, so
  // there is nothing to pin. (The Pool / XI switch is for everyone.)
  const show = !(vm.view === 'sheet' && !vm.canEdit)
  // Toasts sit above this bar rather than over its Confirm button.
  useEffect(() => {
    if (!show) return undefined
    document.documentElement.style.setProperty('--pb-bottom-bar', `${MOBILE_BAR_PX}px`)
    return () => document.documentElement.style.removeProperty('--pb-bottom-bar')
  }, [show])
  if (!show) return null
  const seg = (id, label, extra) => (
    <button type="button" key={id} role="tab" aria-selected={vm.panel === id} onClick={() => vm.setPanel(id)}
      className={`flex-1 min-w-0 min-h-[44px] rounded-lg font-display font-semibold text-[13.5px] px-2 truncate ${vm.panel === id ? 'bg-pb-accent/14 text-pb-accent' : 'text-pb-faint'}`}>
      {label}{extra != null && <span className="font-mono text-[11.5px] ml-1.5 opacity-80">{extra}</span>}
    </button>
  )
  return (
    <div data-mobile-bar
      className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-pb-surface border-t pb-hairline px-3 pt-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] flex items-center gap-2"
      style={{ minHeight: MOBILE_BAR_PX }}>
      {vm.view === 'sheet'
        ? (
          <button type="button" onClick={() => vm.openAdd()} disabled={!vm.canEdit} data-bar-add
            className="flex-1 min-w-0 min-h-[44px] inline-flex items-center justify-center gap-2 rounded-lg border border-pb-hairline2 font-display font-semibold text-[13.5px] text-pb-text disabled:opacity-40">
            <Icon name="plus" size={15} /> Add players <span className="font-mono text-[11.5px] text-pb-faint">{vm.count}{vm.target > 0 ? `/${vm.target}` : ''}</span>
          </button>
        )
        : (
          <div className="flex-1 min-w-0 grid grid-cols-2 gap-1 p-1 rounded-xl bg-pb-surface2 border border-pb-hairline" role="tablist" aria-label="Pool or XI">
            {seg('pool', 'Pool', vm.pool.length)}
            {seg('xi', 'XI', `${vm.count}${vm.target > 0 ? `/${vm.target}` : ''}`)}
          </div>
        )}
      {confirm}
    </div>
  )
}
