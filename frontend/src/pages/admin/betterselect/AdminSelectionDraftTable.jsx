// BetterSelect → Selection Whiteboard (it was the Draft table; the code keeps the old name).
//
// Every team playing on one matchday side by side, plus the players nobody has
// picked yet. Drag a player from one team to another (or from the pool onto a
// team, or off a team back to the pool) and both sides change at once. It is a
// picking board, not a second copy of the rules: each team is a column of the
// ordinary Selection draft.
//
//   • Edits autosave to each team's own draft (PUT /selection/:id/draft), never
//     to the confirmed XI. A column that someone else changed in the meantime is
//     refused by the server (409) and asks, the same as the single-team board.
//   • Confirm writes one team (PUT /selection/:id). Confirm all writes every
//     team that changed, retrying a team the server refused for a clash until the
//     team the player left has confirmed first.
//   • A locked side can still be changed here: the first change to it (or into
//     it) asks "this side is locked, are you sure?", then unlocks it exactly as
//     the Selection board's Unlock does. Confirm locks it again.
//   • Clash, call-up and rule checks stay where they were: the server judges them
//     at Confirm. The table only stops one player being dropped on a team twice.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { useTheme } from '../../../contexts/ThemeContext'
import { useMediaQuery } from '../../../hooks/useMediaQuery'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { useWeekNames } from '../../../lib/useAvailabilityConfig'
import { PbSpinner } from '../../../lib/presskit'
import { availSortRank, AVAILABILITY, halfStatus, viewStatus, weekFlag } from '../../../lib/availability'
import { useSelectConfig } from '../../../lib/useAvailabilityConfig'
import { Icon, Avatar, Btn, Tag, RuleTags, WeekFlag, playedWithinYears, recencyOf } from './ui'
import { DnD, useDrag } from './selectionDnd'
import { nameMatches, roleLine, spark, formMeta, normGender, unavailableWeeksText, gameDatesLabel, fixtureTabs } from './selectionMeta'
import { xiCompliance, isBlocked } from './selectionRules'
import { confirmSig, restoreDraft } from './selectionDraft'
import { sortTeams, teamNameOf, oppLabelOf, commonPrefixWord, stripPrefix } from './teamOrder'
import { useFitHeight, useBoxHeight, rowDensity, ROW_MIN } from './useFitHeight'
import { sideFit, sideLabel } from '../../../lib/sideSize'
import usePersistedState from '../../../lib/usePersistedState'

const DRAFT_DELAY_MS = 600
const DRAFT_RETRY_MS = 5000
const shortDate = (iso) => { try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) } catch { return iso } }
const tint = (token, pct) => `color-mix(in srgb, ${token} ${pct}%, transparent)`

const sigOf = (c) => JSON.stringify([c.slots, c.cap, c.wk])
const filledOf = (c) => c.slots.filter(Boolean)
const isDirty = (c) => confirmSig(filledOf(c), c.cap, c.wk, []) !== c.baseSig
const demoArray = (c) => Object.entries(c.demo || {}).map(([pid, d]) => ({
  player_id: pid, fixture_id: d.fixture_id, batting_order: d.batting_order, callup_id: d.callupId,
}))

// A side's slots, kept the size the club picks to (or, with no limit, the named
// players plus one open slot to drop on).
function tidySlots(slots, size) {
  const next = slots.slice()
  if (size > 0) {
    while (next.length > size && next[next.length - 1] == null) next.pop()
    while (next.length < size) next.push(null)
    return next
  }
  while (next.length && next[next.length - 1] == null) next.pop()
  next.push(null)
  return next
}

// One team's column, built from the selection payload plus any saved draft.
function buildCol(f, d, dr, fallbackSize) {
  const size = d.default_team_size ?? fallbackSize ?? 11
  const lineup = (d.lineup || []).slice().sort((a, b) => (a.batting_order || 999) - (b.batting_order || 999))
  const count = size > 0 ? Math.max(size, lineup.length) : lineup.length
  let slots = Array(count).fill(null)
  lineup.forEach((l, i) => { if (i < count) slots[i] = l.player_id })
  let cap = lineup.find((l) => l.is_captain)?.player_id ?? null
  let wk = lineup.find((l) => l.is_wicket_keeper)?.player_id ?? null
  const baseSig = confirmSig(slots.filter(Boolean), cap, wk, [])
  let demo = {}
  let fromDraft = null
  // A locked side shows the confirmed XI whatever draft is behind it, as the board does.
  const locked = !!(d.fixture?.locked ?? f.locked)
  const dd = locked ? null : dr?.draft
  if (dd && Array.isArray(dd.slots)) {
    const r = restoreDraft(dd, d.pool, size)
    slots = r.slots; cap = r.cap; wk = r.wk; demo = r.demo
    fromDraft = { version: dr.version || 0, carried: !!dd.seeded_from }
  }
  slots = tidySlots(slots, size)
  const poolById = {}
  ;(d.pool || []).forEach((p) => { poolById[p.id] = p })
  return { fid: f.id, fx: f, data: d, poolById, size, min: d.team_min || 0, slots, cap, wk, demo, baseSig, fromDraft, locked }
}

// ── Which weekend ───────────────────────────────────────────────────────────
// A two-day game is played over two weekends and a player answers each. Beside a
// name, plain text says which weekend is the problem ("W2 ONLY", "W1 OUT",
// "W2 ?"): the shared `WeekFlag` every BetterSelect screen uses, in the colour of
// the card's own dot and edge. Nothing is drawn for a player who has not answered
// a weekend yet, or whose weekends match.

// ── A player card (a team's slot, and the pool) ──────────────────────────────
function PlayerCard({ p, kind, col, idx, density = 'full', alsoIn, ctx, drag }) {
  const fmt = useAdminNameFormat()
  const shown = viewStatus(p, ctx.weekByPlayer[p.id])
  const meta = AVAILABILITY[shown] || AVAILABILITY.NO_RESPONSE
  const slot = kind === 'slot'
  const dense = slot && density !== 'full'
  const tight = slot && density === 'tight'
  const barred = isBlocked(p)
  const c = slot ? ctx.cols[col] : null
  const isCap = slot && c.cap === p.id
  const isWk = slot && c.wk === p.id
  const item = slot ? { kind: 'slot', col, idx, player: p } : { kind: 'pool', player: p }
  const fm = formMeta(p)
  const bars = !slot || !dense ? spark(p.recent) : []
  const out = p.availability === 'UNAVAILABLE'
  return (
    <div data-player-card={p.id} data-density={slot ? density : undefined}
      {...(ctx.canEdit ? drag.bind(item) : {})}
      onClick={!slot && ctx.canEdit ? drag.clickGuard(() => ctx.tapPool(p)) : undefined}
      className={`group relative flex items-center gap-2 pl-3 pr-2 rounded-lg border bg-pb-surface2 overflow-hidden transition-colors select-none ${slot ? 'h-full min-h-0' : 'shrink-0 py-1.5'} ${ctx.canEdit ? 'cursor-grab' : ''} ${barred ? 'border-pb-red/45' : 'border-pb-hairline'} hover:border-pb-accent/45`}>
      <span className="absolute left-0 top-0 bottom-0 w-1" style={{ background: shown === 'NO_RESPONSE' ? 'var(--pb-faintest)' : meta.cssVar }} />
      <Avatar player={p} size={tight ? 20 : dense ? 24 : 30} noLink />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 min-w-0">
          <span className={`${tight ? 'text-[12.5px]' : 'text-[13px]'} font-semibold truncate ${out ? 'opacity-70' : ''}`}>{fmt(p.display_name)}</span>
          {isCap && <Tag>C</Tag>}{isWk && <Tag tone="amber">WK</Tag>}
          {alsoIn && <Tag tone="amber" title={`Also named in ${alsoIn}`}>×2</Tag>}
          <RuleTags player={p} />
          {/* "W2 OUT" says more than "OUT" where a weekend is the reason. */}
          {weekFlag(ctx.weekByPlayer[p.id])
            ? <WeekFlag days={ctx.weekByPlayer[p.id]} />
            : out && <span className="font-mono text-[9.5px] font-semibold shrink-0" style={{ color: meta.cssVar }}>OUT</span>}
        </div>
        {!tight && (
          <div className="flex items-center gap-1.5 min-w-0">
            <span className={`${dense ? 'text-[11px]' : 'text-[11.5px]'} text-pb-dim truncate`} title={roleLine(p)}>{roleLine(p)}</span>
            {!slot && p.squads?.[0] && <Tag tone={p.squad_match ? 'accent' : 'faint'} className="shrink-0">{ctx.squadShort(p.squads[0])}</Tag>}
            {!slot && bars.length > 0 && fm && <span className="font-mono text-[9.5px] font-semibold shrink-0 ml-auto" style={{ color: fm.token }}>{fm.label}</span>}
          </div>
        )}
      </div>
      {slot && ctx.canEdit && (
        <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 rounded-md bg-pb-surface2 pl-1" onPointerDown={(e) => e.stopPropagation()}>
          <button type="button" title="Captain" onClick={() => ctx.toggleCap(col, p.id)}
            className={`w-[22px] h-[22px] rounded text-[9.5px] font-bold font-mono ${isCap ? 'bg-pb-accent text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>C</button>
          <button type="button" title="Wicket-keeper" onClick={() => ctx.toggleWk(col, p.id)}
            className={`w-[22px] h-[22px] rounded text-[9.5px] font-bold font-mono ${isWk ? 'bg-pb-amber text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>WK</button>
          <button type="button" title="Back to the pool" aria-label={`Remove ${p.display_name}`} onClick={() => ctx.removeAt(col, idx)}
            className="w-[22px] h-[22px] rounded flex items-center justify-center text-pb-faintest hover:text-pb-red hover:bg-pb-red/10"><Icon name="close" size={12} /></button>
        </div>
      )}
    </div>
  )
}

function SlotRow({ col, idx, id, density, ctx, drag }) {
  const c = ctx.cols[col]
  const p = id ? (c.poolById[id] || ctx.merged[id]) : null
  const hovered = drag.hover === `slot:${col}:${idx}`
  const others = id ? ctx.order.filter((f) => f !== col && ctx.cols[f].slots.includes(id)) : []
  const alsoIn = others.map((f) => ctx.shortTeam(ctx.cols[f].fx)).join(', ')
  return (
    <div className="flex items-stretch gap-1.5" style={{ flex: '1 1 0', minHeight: ROW_MIN, maxHeight: density === 'full' ? 64 : undefined }}
      data-drop-kind="slot" data-drop-col={col} data-drop-idx={idx} data-slot-row={idx}>
      <span className="font-display font-bold text-[12px] text-pb-faintest w-[16px] flex items-center justify-center shrink-0 pb-num">{idx + 1}</span>
      <div className="flex-1 min-w-0">
        {p ? <PlayerCard p={p} kind="slot" col={col} idx={idx} density={density} alsoIn={alsoIn} ctx={ctx} drag={drag} /> : (
          <div className={`h-full min-h-0 flex items-center justify-center rounded-lg border border-dashed text-[11.5px] transition-colors ${hovered ? 'border-pb-accent border-solid text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-faintest'}`}>
            {hovered ? 'Drop here' : 'Open'}
          </div>
        )}
      </div>
    </div>
  )
}

// ── One team ────────────────────────────────────────────────────────────────
function TeamColumn({ col, density, listRef, ctx, drag }) {
  const c = ctx.cols[col]
  const fx = c.fx
  const filled = filledOf(c)
  const dirty = isDirty(c)
  const status = ctx.status[col]
  const conflict = ctx.conflicts[col]
  const target = c.size
  const off = sideFit(filled.length, target, c.min).off
  const hasKeeper = filled.some((id) => (c.poolById[id]?.skill_positions || []).includes('WKT')) || (c.wk && filled.includes(c.wk))
  const bowlers = filled.filter((id) => { const r = c.poolById[id]?.skill_positions || []; return r.includes('BWL') || r.includes('ALL') }).length
  const rules = xiCompliance(c.data.rules, c.poolById, filled)
  const active = ctx.activeFid === col
  const hovered = drag.hover === `col:${col}`
  const flags = []
  if (filled.length >= 8 && !hasKeeper) flags.push({ tone: 'amber', text: 'No keeper' })
  if (filled.length >= 8 && bowlers < 5) flags.push({ tone: 'amber', text: 'Light bowling' })
  if (rules.blocking.length) flags.push({ tone: 'red', text: `${rules.blocking.length} rule${rules.blocking.length === 1 ? '' : 's'} to fix`, title: rules.blocking.map((w) => `${w.player ? w.player + ': ' : ''}${w.detail}`).join('\n') })
  if (rules.warnings.length) flags.push({ tone: 'amber', text: `${rules.warnings.length} to check`, title: rules.warnings.map((w) => `${w.player ? w.player + ': ' : ''}${w.detail}`).join('\n') })
  return (
    <section data-team-col={col} data-drop-kind="col" data-drop-col={col}
      className={`flex-1 basis-0 min-w-[212px] min-h-0 flex flex-col rounded-xl border bg-pb-surface transition-colors ${hovered ? 'border-pb-accent' : active ? 'border-pb-accent/60' : 'border-pb-hairline'}`}
      style={hovered ? { background: tint('var(--pb-accent)', 6) } : undefined}>
      <header className="px-2.5 pt-2 pb-1.5 border-b pb-hairline cursor-pointer" onClick={() => ctx.setActiveFid(col)} title="Click a player in the pool to add them to this team">
        <div className="flex items-center gap-1.5 min-w-0">
          <h3 className="font-display font-bold text-[14px] truncate min-w-0 flex-1" title={teamNameOf(fx)}>{ctx.shortTeam(fx)}</h3>
          <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap"
            style={{ background: off ? 'var(--pb-amber)' : tint('var(--pb-accent)', 18), color: off ? '#1b1205' : 'var(--pb-accent)' }}>
            {filled.length}{target > 0 ? `/${target}` : ''}{c.min > 0 ? ` · min ${c.min}` : ''}
          </span>
        </div>
        <div className="text-[11.5px] text-pb-faint truncate" title={`${oppLabelOf(fx)}${fx.start_time ? ' · ' + fx.start_time : ''}${fx.venue ? ' · ' + fx.venue : ''}`}>
          {oppLabelOf(fx)}{fx.start_time ? ` · ${fx.start_time}` : ''}
        </div>
        {fx.end_on && fx.end_on > fx.played_on && (
          <div className="text-[11px] font-semibold truncate" style={{ color: 'var(--pb-amber)' }} data-two-day-header title={`Played over two weekends. A ${ctx.weekNames.w1} or ${ctx.weekNames.w2} tag beside a name is that player's answer for that weekend.`}>
            {ctx.day === fx.end_on
              ? `Two-day · ${ctx.weekNames.w2}, from ${shortDate(fx.played_on)}`
              : `Two-day · ${shortDate(fx.played_on)} + ${shortDate(fx.end_on)}`}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-1 mt-1 min-h-[22px]">
          {flags.map((f, i) => (
            <span key={i} title={f.title} className="px-1.5 py-px rounded-full font-display font-semibold text-[10.5px] whitespace-nowrap"
              style={{ color: f.tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)', background: tint(f.tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)', 13) }}>{f.text}</span>
          ))}
          <span className="flex-1" />
          {ctx.canEdit && dirty && (
            <>
              <span className="text-[10.5px] font-semibold" style={{ color: status === 'error' ? 'var(--pb-red)' : 'var(--pb-amber)' }} data-draft-status={status || 'idle'}>
                {status === 'error' ? 'Not saving' : status === 'saving' ? 'Saving…' : status === 'saved' ? 'Draft saved' : 'Draft'}
              </span>
              <button type="button" title="Back to the confirmed XI" aria-label={`Discard changes to ${ctx.shortTeam(fx)}`} onClick={(e) => { e.stopPropagation(); ctx.discard(col) }}
                className="w-[22px] h-[22px] rounded inline-flex items-center justify-center text-pb-faint hover:text-pb-text hover:bg-pb-surface2"><Icon name="reset" size={12} /></button>
              <button type="button" data-confirm-col={col} onClick={(e) => { e.stopPropagation(); ctx.confirmOne(col) }} disabled={ctx.busy}
                className="px-2 py-0.5 rounded-md font-display font-semibold text-[11.5px] bg-pb-accent text-[#08110b] disabled:opacity-40">Confirm</button>
            </>
          )}
          {c.locked && !dirty && filled.length > 0
            ? <span className="text-[10.5px] font-semibold text-pb-faint inline-flex items-center gap-1" data-locked-col={col} title="Locked. Change anyone and you will be asked to unlock it."><Icon name="lock" size={11} />Locked</span>
            : !dirty && filled.length > 0 && <span className="text-[10.5px] font-semibold text-pb-faint inline-flex items-center gap-1"><Icon name="check" size={11} />Confirmed</span>}
          <Link to={`/admin/betterselect/select/${fx.id}`} onClick={(e) => e.stopPropagation()} title="Open this team in the full Selection board" aria-label={`Open ${ctx.shortTeam(fx)}`}
            className="w-[22px] h-[22px] rounded inline-flex items-center justify-center text-pb-faint hover:text-pb-accent hover:bg-pb-surface2"><Icon name="arrow" size={12} /></Link>
        </div>
      </header>
      {conflict && (
        <div role="alert" className="px-2.5 py-1.5 text-[11.5px] border-b pb-hairline" style={{ background: tint('var(--pb-amber)', 10) }}>
          <b>{conflict.theirs ? `${conflict.theirs.by || 'Someone else'} changed this draft.` : 'This draft was confirmed or discarded elsewhere.'}</b>{' '}
          <button type="button" onClick={() => ctx.useTheirs(col)} className="font-semibold text-pb-accent hover:underline">{conflict.theirs ? 'Use theirs' : 'Use confirmed XI'}</button>
          {' · '}
          <button type="button" onClick={() => ctx.keepMine(col)} className="font-semibold text-pb-accent hover:underline">Keep mine</button>
        </div>
      )}
      <div ref={listRef} className="flex-1 min-h-0 flex flex-col gap-1 p-1.5 overflow-y-auto pb-scroll" data-team-list={col}>
        {c.slots.map((id, i) => <SlotRow key={i} col={col} idx={i} id={id} density={density} ctx={ctx} drag={drag} />)}
      </div>
    </section>
  )
}

// ── The pool ────────────────────────────────────────────────────────────────
function PoolColumn({ ctx, drag }) {
  const hovered = drag.hover === 'pool'
  const { q, setQ, hideOut, setHideOut, squad, setSquad, gender, setGender } = ctx.filters
  const activeTeam = ctx.activeFid && ctx.cols[ctx.activeFid] ? ctx.shortTeam(ctx.cols[ctx.activeFid].fx) : null
  return (
    // Pinned to the left of the scrolling board (sticky, so the team columns slide
    // under it): the pool is where a drag starts and ends, so it must stay in
    // view however far the teams are scrolled. Its tint is mixed into the surface
    // colour, never transparent, or the columns would show through.
    <section data-pool-col data-autoscroll-skip data-drop-kind="pool"
      className={`sticky left-0 z-10 w-[270px] shrink-0 min-h-0 flex flex-col rounded-xl border bg-pb-surface shadow-[6px_0_14px_-8px_rgba(0,0,0,0.4)] transition-colors ${hovered ? 'border-pb-red/50' : 'border-pb-hairline'}`}
      style={hovered ? { background: 'color-mix(in srgb, var(--pb-red) 5%, var(--pb-surface))' } : undefined}>
      <header className="px-2.5 pt-2 pb-2 border-b pb-hairline flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-display font-bold text-[14px]">Pool</h3>
          <span className="font-mono text-[11px] text-pb-faint pb-num" data-pool-count>{ctx.pool.length} of {ctx.poolTotal}</span>
        </div>
        <div className="flex items-center gap-2 bg-pb-surface2 border border-pb-hairline rounded-lg px-2.5 h-[30px] text-pb-faint focus-within:border-pb-accent">
          <Icon name="search" size={13} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player…" aria-label="Find a player"
            className="bg-transparent border-0 outline-none text-pb-text text-[13px] w-full placeholder:text-pb-faint" />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {ctx.squadOptions.length > 0 && (
            <select value={squad} onChange={(e) => setSquad(e.target.value)} aria-label="Squad"
              className="bg-pb-surface2 border border-pb-hairline rounded-md text-[11.5px] px-1.5 py-1 text-pb-dim max-w-[110px]">
              <option value="" style={{ color: '#000' }}>All squads</option>
              {ctx.squadOptions.map((s) => <option key={s} value={s} style={{ color: '#000' }}>{ctx.squadShort(s)}</option>)}
            </select>
          )}
          {ctx.showGender && (
            <select value={gender} onChange={(e) => setGender(e.target.value)} aria-label="Gender"
              className="bg-pb-surface2 border border-pb-hairline rounded-md text-[11.5px] px-1.5 py-1 text-pb-dim">
              <option value="" style={{ color: '#000' }}>All genders</option>
              <option value="male" style={{ color: '#000' }}>Men</option>
              <option value="female" style={{ color: '#000' }}>Women</option>
            </select>
          )}
          <label className="inline-flex items-center gap-1 text-[11.5px] text-pb-dim cursor-pointer">
            <input type="checkbox" checked={hideOut} onChange={(e) => setHideOut(e.target.checked)} />Hide unavailable
          </label>
        </div>
        {ctx.canEdit && activeTeam && <div className="text-[11px] text-pb-faint">Click a player to add them to <b className="text-pb-text">{activeTeam}</b>, or drag onto any team.</div>}
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto pb-scroll p-1.5 flex flex-col gap-1" data-pool-list>
        {ctx.pool.map((p) => <PlayerCard key={p.id} p={p} kind="pool" ctx={ctx} drag={drag} />)}
        {ctx.pool.length === 0 && <div className="p-3 text-pb-faint text-[13px]">No players match.</div>}
        {hovered && <div className="sticky bottom-1 mx-auto mt-1 px-3 py-1 rounded-full text-[11.5px] text-pb-red bg-pb-surface border border-dashed border-pb-red/40">Drop here to take them out</div>}
      </div>
    </section>
  )
}

// ── The board ───────────────────────────────────────────────────────────────
function Board({ ctx, isPhone }) {
  const drag = useDrag()
  // Measured here, not on the screen: the board only exists once the day has
  // loaded, and the height is from where it starts to the bottom of the window.
  const [fitRef, fitH] = useFitHeight({ enabled: !isPhone, bottom: 20 })
  const [listRef, listH] = useBoxHeight()
  const maxSlots = Math.max(1, ...ctx.order.map((f) => ctx.cols[f].slots.length))
  const density = rowDensity(listH, maxSlots)
  return (
    <div ref={fitRef} data-draft-table data-autoscroll-x data-fit={fitH != null ? 'on' : 'off'} style={fitH != null ? { height: fitH } : undefined}
      className="flex gap-2.5 overflow-x-auto pb-1 items-stretch">
      <PoolColumn ctx={ctx} drag={drag} />
      {ctx.order.map((f, i) => <TeamColumn key={f} col={f} density={density} listRef={i === 0 ? listRef : undefined} ctx={ctx} drag={drag} />)}
    </div>
  )
}

const fmtDay = (iso) => {
  if (!iso) return 'Date TBC'
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return iso }
}

// ── Screen ──────────────────────────────────────────────────────────────────
export default function AdminSelectionDraftTable() {
  const { hasCapability, canEditCap } = useAuth()
  const toast = useToast()
  const toastRef = useRef(toast)
  const weekNames = useWeekNames()
  toastRef.current = toast
  const { theme, toggle: toggleTheme } = useTheme()
  const canEdit = canEditCap(CAP.SELECT_SELECTION, CAP.MANAGE_SELECTIONS)
  const isPhone = useMediaQuery('(max-width: 1023px)')
  const [params, setParams] = useSearchParams()

  const [overview, setOverview] = useState(null)
  const [cols, setCols] = useState(null)            // { [fixtureId]: column }
  const [order, setOrder] = useState([])            // fixture ids, top team first
  const [status, setStatusMap] = useState({})       // { [fid]: idle | saving | saved | error }
  const [conflicts, setConflicts] = useState({})    // { [fid]: { theirs } }
  const [tick, setTick] = useState(0)               // a draft write landed: re-judge the board against it
  const [busy, setBusy] = useState(false)
  const [activeFid, setActiveFid] = useState(null)
  const [q, setQ] = useState('')
  // How far back a player may have last played to be listed is a club setting (Settings, Players listed).
  const years = useSelectConfig().playedYears?.selection ?? 3
  const [hideOut, setHideOut] = useState(false)
  const [squad, setSquad] = useState('')
  const [gender, setGender] = useState('')
  // The same remembered Show juniors choice Availability, Fixtures and Selection use.
  // Whether junior grades show is a Settings choice now, not a switch on this screen.
  const [showJuniors] = usePersistedState('select.juniors', false, (v) => typeof v === 'boolean')

  const colsRef = useRef(cols)
  colsRef.current = cols
  const gen = useRef(0)                             // which load the board belongs to
  const savers = useRef({})                         // per team: the autosave machinery
  const saver = (fid) => (savers.current[fid] ??= { timer: null, pending: null, inflight: null, version: 0, serverSig: '', onServer: false })
  const setStatus = (fid, v) => setStatusMap((m) => (m[fid] === v ? m : { ...m, [fid]: v }))

  // ── Loading ───────────────────────────────────────────────────────────────
  useEffect(() => {
    api.bsSelectionOverview({ hideJuniors: !showJuniors }).then(setOverview)
      .catch((e) => { toastRef.current.error(e.message); setOverview({ fixtures: [] }) })
  }, [showJuniors])

  const days = useMemo(() => {
    const m = new Map()
    ;(overview?.fixtures || []).forEach((f) => fixtureTabs(f).forEach((k) => m.set(k, (m.get(k) || 0) + 1)))
    // A two-day game adds its second weekend, so dates are put in order ('tbc' last).
    return [...m.entries()].sort(([a], [b]) => (a === 'tbc') - (b === 'tbc') || (a < b ? -1 : a > b ? 1 : 0)).map(([day, n]) => ({ day, n }))
  }, [overview])
  const wanted = params.get('date')
  const day = wanted && days.some((d) => d.day === wanted) ? wanted : days[0]?.day || null

  const attachSaver = (col) => {
    const s = saver(col.fid)
    clearTimeout(s.timer)
    s.pending = null
    s.version = col.fromDraft?.version || 0
    s.onServer = !!col.fromDraft
    s.serverSig = sigOf(col)
  }

  const loadCol = useCallback(async (f) => {
    const [d, dr] = await Promise.all([
      api.bsGetSelection(f.id),
      canEdit ? api.bsGetSelectionDraft(f.id).catch(() => ({ draft: null })) : { draft: null },
    ])
    return buildCol(f, d, dr, overview?.default_team_size)
  }, [canEdit, overview])

  // ── Draft autosave, one per team ──────────────────────────────────────────
  const flush = useCallback((fid, leaving) => {
    const s = saver(fid)
    clearTimeout(s.timer)
    s.timer = null
    const p = s.pending
    if (!p) return s.inflight
    s.pending = null
    const mine = gen.current
    const opts = leaving ? { keepalive: true } : {}
    const task = Promise.resolve(s.inflight).catch(() => {})
      .then(() => (p.body
        ? api.bsSaveSelectionDraft(fid, { ...p.body, base_version: s.version }, opts)
        : api.bsDiscardSelectionDraft(fid, s.version, opts)))
      .then((r) => {
        if (gen.current !== mine) return
        s.version = p.body ? (r?.version || 0) : 0
        s.serverSig = p.sig
        s.onServer = !!p.body
        setStatus(fid, s.pending ? 'saving' : 'saved')
        setTick((t) => t + 1)
      })
      .catch((e) => {
        if (gen.current !== mine) return
        if (e.status === 409 && e.detail?.code === 'draft_conflict') {
          const t = e.detail
          setStatus(fid, 'idle')
          setConflicts((m) => ({ ...m, [fid]: { theirs: t.draft ? { draft: t.draft, version: t.version, by: t.updated_by } : null } }))
          return
        }
        if (e.status === 409 && e.detail?.code === 'locked') {
          // Locked by someone else since this board loaded. The change stays on the
          // board; the next edit asks to unlock, then it saves.
          setStatus(fid, 'idle')
          setCols((prev) => (prev?.[fid] ? { ...prev, [fid]: { ...prev[fid], locked: true } } : prev))
          return
        }
        setStatus(fid, 'error')
        if ((!e.status || e.status >= 500) && !s.pending) {
          s.pending = p
          s.timer = setTimeout(() => flush(fid, false), DRAFT_RETRY_MS)
        }
      })
    s.inflight = task
    return task
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!overview || !day) return undefined
    // Anything still waiting out the pause for the day we are leaving goes first.
    Object.keys(savers.current).forEach((fid) => flush(fid, false))
    const mine = ++gen.current
    const fixtures = sortTeams((overview.fixtures || []).filter((f) => fixtureTabs(f).includes(day)))
    setCols(null)
    setConflicts({})
    setStatusMap({})
    // A draft write still in flight for the day we are leaving lands first.
    Promise.all(Object.values(savers.current).map((s) => Promise.resolve(s.inflight).catch(() => {})))
      .then(() => Promise.all(fixtures.map(loadCol)))
      .then((list) => {
        if (gen.current !== mine) return
        savers.current = {}
        const next = {}
        list.forEach((c) => { next[c.fid] = c; attachSaver(c) })
        setOrder(list.map((c) => c.fid))
        setActiveFid(list[0]?.fid || null)
        setCols(next)
      })
      .catch((e) => { if (gen.current === mine) { toastRef.current.error(e.message); setCols({}); setOrder([]) } })
    return undefined
  }, [overview, day, loadCol])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!canEdit || !cols) return
    order.forEach((fid) => {
      const c = cols[fid]
      if (!c || conflicts[fid] || c.locked) return
      const s = saver(fid)
      const dirty = isDirty(c)
      const sig = sigOf(c)
      if (dirty ? sig === s.serverSig : !s.onServer) {
        // Back to what the server holds: a change still waiting is stale.
        if (s.pending) { s.pending = null; clearTimeout(s.timer); setStatus(fid, 'saved') }
        return
      }
      s.pending = {
        sig,
        body: dirty ? { slots: c.slots, captain_id: c.cap, wicket_keeper_id: c.wk, demotions: demoArray(c) } : null,
      }
      setStatus(fid, 'saving')
      clearTimeout(s.timer)
      s.timer = setTimeout(() => flush(fid, false), DRAFT_DELAY_MS)
    })
  }, [cols, conflicts, tick, canEdit, order, flush])

  // Leaving the screen (another day, another page, closing the tab) must not
  // lose a change still waiting out the pause.
  useEffect(() => {
    const all = (leaving) => Object.keys(savers.current).forEach((fid) => flush(fid, leaving))
    const onHide = () => { if (document.visibilityState === 'hidden') all(true) }
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('pagehide', onHide)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('pagehide', onHide)
      all(true)
    }
  }, [flush])

  // ── Editing ───────────────────────────────────────────────────────────────
  const merged = useMemo(() => {
    const m = {}
    order.forEach((f) => Object.values(cols?.[f]?.poolById || {}).forEach((p) => { if (!m[p.id]) m[p.id] = p }))
    return m
  }, [cols, order])

  const edit = (fn) => setCols((prev) => (prev ? fn(prev) : prev))
  const put = (prev, fid, patch) => ({ ...prev, [fid]: { ...prev[fid], ...patch } })
  const leave = (c, id) => ({ cap: c.cap === id ? null : c.cap, wk: c.wk === id ? null : c.wk })
  const nameOf = (id) => merged[id]?.display_name || 'Player'

  // Judged on the team they are going INTO: the pool card shows today only, but a
  // two-day team's own answer is the worse of both weeks.
  const warnPick = (p, fid) => {
    const t = (fid && colsRef.current?.[fid]?.poolById?.[p.id]) || p
    if (t.availability === 'UNAVAILABLE') toastRef.current.info(`${p.display_name} is marked unavailable${unavailableWeeksText(t.availability_days, weekNames)}. Adding anyway.`)
  }

  // A locked side is changed only after the selector says yes. The prompt comes
  // first, then the change goes on the board, then the side is unlocked (the same
  // POST the Selection board's Unlock sends); autosave skips a locked column, so
  // nothing is sent to it until the unlock has landed.
  const unlocking = useRef({})
  const unlockCols = async (fids) => {
    fids.forEach((f) => { unlocking.current[f] = true })
    try {
      await Promise.all(fids.map((f) => api.bsUnlockSelection(f)))
      setCols((prev) => (prev ? fids.reduce((acc, f) => (acc[f] ? put(acc, f, { locked: false }) : acc), prev) : prev))
    } catch (e) {
      toastRef.current.error('Could not unlock: ' + e.message)
      await Promise.all(fids.map((f) => reloadCol(f).catch(() => {})))
    } finally { fids.forEach((f) => { delete unlocking.current[f] }) }
  }
  const guarded = (fids, apply) => {
    const cur = colsRef.current
    const locked = [...new Set(fids)].filter((f) => cur?.[f]?.locked && !unlocking.current[f])
    if (!locked.length) { apply(); return }
    const names = locked.map((f) => ctxShort(cur[f].fx))
    const one = names.length === 1
    if (!window.confirm(`${names.join(' and ')} ${one ? 'is' : 'are'} locked. Are you sure you want to change ${one ? 'it' : 'them'}?\n\nThe side will be unlocked until you confirm it again.`)) return
    apply()
    unlockCols(locked)
  }

  const placeIn = (fid, idx, id) => {
    const p = merged[id]
    if (!p) return
    const target = colsRef.current?.[fid]
    if (!target || !target.poolById[id]) {
      toastRef.current.error(`${p.display_name} is not in the pool for ${ctxShort(target?.fx)}`)
      return
    }
    if (target.slots.includes(id) || idx < 0 || idx >= target.slots.length) return
    guarded([fid], () => {
      edit((prev) => {
        const c = prev[fid]
        if (!c || idx < 0 || idx >= c.slots.length) return prev
        if (c.slots.includes(id)) return prev
        const slots = c.slots.slice()
        const displaced = slots[idx]
        slots[idx] = id
        return put(prev, fid, { slots: tidySlots(slots, c.size), ...(displaced ? leave(c, displaced) : {}) })
      })
      warnPick(p, fid)
    })
  }

  const removeAt = (fid, idx) => {
    if (!colsRef.current?.[fid]?.slots[idx]) return
    guarded([fid], () => edit((prev) => {
      const c = prev[fid]
      const id = c?.slots[idx]
      if (!id) return prev
      const slots = c.slots.slice()
      slots[idx] = null
      return put(prev, fid, { slots: tidySlots(slots, c.size), ...leave(c, id) })
    }))
  }

  // Move a player from one slot to another, in the same team or across. An
  // occupied target swaps. A player can sit in a team once, so a move that would
  // double someone up is refused.
  const moveSlot = (fromFid, fromIdx, toFid, toIdx) => {
    const cur = colsRef.current
    const a = cur?.[fromFid], b = cur?.[toFid]
    if (!a || !b || (fromFid === toFid && fromIdx === toIdx)) return
    const x = a.slots[fromIdx]
    const y = b.slots[toIdx]
    if (!x) return
    if (fromFid !== toFid) {
      if (!b.poolById[x]) { toastRef.current.error(`${nameOf(x)} is not in the pool for ${ctxShort(b.fx)}`); return }
      if (y && !a.poolById[y]) { toastRef.current.error(`${nameOf(y)} is not in the pool for ${ctxShort(a.fx)}`); return }
      if (b.slots.includes(x)) { toastRef.current.error(`${nameOf(x)} is already in ${ctxShort(b.fx)}`); return }
      if (y && a.slots.includes(y)) { toastRef.current.error(`${nameOf(y)} is already in ${ctxShort(a.fx)}`); return }
    }
    guarded([fromFid, toFid], () => {
      edit((prev) => {
        const pa = prev[fromFid], pb = prev[toFid]
        if (fromFid === toFid) {
          const slots = pa.slots.slice()
          ;[slots[fromIdx], slots[toIdx]] = [slots[toIdx], slots[fromIdx]]
          return put(prev, fromFid, { slots })
        }
        const sa = pa.slots.slice(), sb = pb.slots.slice()
        sa[fromIdx] = y || null
        sb[toIdx] = x
        let next = put(prev, fromFid, { slots: tidySlots(sa, pa.size), ...leave(pa, x) })
        next = put(next, toFid, { slots: tidySlots(sb, pb.size), ...(y ? leave(pb, y) : {}) })
        return next
      })
      const p = merged[x]
      if (p && fromFid !== toFid) warnPick(p, toFid)
    })
  }

  const firstOpen = (fid) => {
    const c = colsRef.current?.[fid]
    return c ? c.slots.indexOf(null) : -1
  }

  const tapPool = (p) => {
    if (!canEdit) return
    const fid = activeFid
    if (!fid || !colsRef.current?.[fid]) return
    const idx = firstOpen(fid)
    if (idx === -1) { toastRef.current.error(`${ctxShort(colsRef.current[fid].fx)} is full. Take someone out first.`); return }
    placeIn(fid, idx, p.id)
  }

  const onDrop = (tgt, item) => {
    if (!canEdit) return
    const id = item.player?.id
    if (tgt.kind === 'pool') { if (item.kind === 'slot') removeAt(item.col, item.idx); return }
    const fid = tgt.col
    if (!fid || !colsRef.current?.[fid]) return
    setActiveFid(fid)
    const idx = tgt.kind === 'slot' ? tgt.idx : firstOpen(fid)
    if (idx == null || idx < 0) {
      if (item.kind === 'slot' && item.col === fid) return
      toastRef.current.error(`${ctxShort(colsRef.current[fid].fx)} is full. Drop on a player to swap, or take someone out first.`)
      return
    }
    if (item.kind === 'pool') {
      if (colsRef.current[fid].slots.includes(id)) return
      placeIn(fid, idx, id)
    } else moveSlot(item.col, item.idx, fid, idx)
  }

  const toggleCap = (fid, id) => guarded([fid], () => edit((prev) => put(prev, fid, { cap: prev[fid].cap === id ? null : id })))
  const toggleWk = (fid, id) => guarded([fid], () => edit((prev) => put(prev, fid, { wk: prev[fid].wk === id ? null : id })))

  // ── Names ─────────────────────────────────────────────────────────────────
  const teamPrefix = useMemo(
    () => commonPrefixWord(order.map((f) => cols?.[f]?.fx.team_name || cols?.[f]?.fx.grade_name).filter(Boolean)),
    [cols, order])
  const ctxShort = useCallback((f) => {
    const n = f?.team_name || f?.grade_name
    return n ? (stripPrefix(teamPrefix, n) || n) : teamNameOf(f)
  }, [teamPrefix])
  const squadPrefix = useMemo(() => {
    const names = new Set()
    Object.values(merged).forEach((p) => (p.squads || []).forEach((s) => names.add(s)))
    return commonPrefixWord([...names])
  }, [merged])
  const squadShort = useCallback((n) => stripPrefix(squadPrefix, n) || n, [squadPrefix])
  const squadOptions = useMemo(() => {
    const names = new Set()
    Object.values(merged).forEach((p) => (p.squads || []).forEach((s) => names.add(s)))
    return [...names].sort((a, b) => squadShort(a).localeCompare(squadShort(b)))
  }, [merged, squadShort])

  // ── The pool: everyone not named in a team ────────────────────────────────
  const named = useMemo(() => {
    const s = new Set()
    order.forEach((f) => (cols?.[f]?.slots || []).forEach((id) => id && s.add(id)))
    return s
  }, [cols, order])
  // Each player's two weeks, from any team on the day that is a two-day game
  // (its pool carries `availability_days`). Empty on a day with no such game.
  const weekByPlayer = useMemo(() => {
    const m = {}
    order.forEach((f) => {
      const c = cols?.[f]
      if (!c || !(c.fx?.end_on && c.fx.end_on > c.fx.played_on)) return
      Object.values(c.poolById || {}).forEach((p) => { if (!m[p.id] && Array.isArray(p.availability_days)) m[p.id] = p.availability_days })
    })
    return m
  }, [cols, order])
  // The shared pool answers "can they play TODAY": the first team's pool may be
  // the two-day game, whose status is the worse of both weeks, which would mark
  // a player OUT for one-day teams they are free for. The open weekend is what the pool shows; the chips show both.
  // Which weekend is open: the second tab of a two-day game reads W2.
  const weekIdx = useMemo(() => {
    for (const f of order) {
      const x = cols?.[f]?.fx
      if (x?.end_on && x.end_on > x.played_on) return x.end_on === day ? 1 : 0
    }
    return 0
  }, [cols, order, day])
  const unnamed = useMemo(() => Object.values(merged)
    .filter((p) => !named.has(p.id) && !p.is_inactive)
    .map((p) => (weekByPlayer[p.id] ? { ...p, availability: weekByPlayer[p.id][weekIdx]?.status || p.availability } : p)), [merged, named, weekByPlayer, weekIdx])
  // Offered only when the pool holds both: a control that can only answer "nobody" is worse than none.
  const showGender = useMemo(() => new Set(unnamed.map((p) => normGender(p.gender)).filter(Boolean)).size > 1, [unnamed])
  const pool = useMemo(() => {
    let list = unnamed
    if (q.trim()) list = list.filter((p) => nameMatches(p.display_name, q))
    if (squad) list = list.filter((p) => (p.squads || []).includes(squad))
    if (gender) list = list.filter((p) => normGender(p.gender) === gender)
    if (hideOut) list = list.filter((p) => p.availability !== 'UNAVAILABLE')
    // A name typed into search is someone being looked for, so the recency window
    // only trims the browse list.
    if (years && !q.trim()) list = list.filter((p) => playedWithinYears(recencyOf(p), years))
    // The shared availability sort (lib/availability `availSortRank`): free ONE
    // weekend of a two-day game and away the other leads. The pool judges the open
    // weekend (`availability`), which would read the away weekend as OUT and sink
    // them, so the per-weekend answers are what lead. Ordering only.
    const rank = (p) => availSortRank(p.availability, weekByPlayer[p.id])
    return list.slice().sort((a, b) =>
      rank(a) - rank(b)
      || (b.score ?? 0) - (a.score ?? 0)
      || (a.display_name || '').localeCompare(b.display_name || ''))
  }, [unnamed, q, squad, gender, hideOut, years, weekByPlayer])

  // ── Confirm ───────────────────────────────────────────────────────────────
  const dirtyIds = order.filter((f) => cols?.[f] && isDirty(cols[f]))

  const writeConfirm = async (fid) => {
    const c = colsRef.current[fid]
    const s = saver(fid)
    // Confirming replaces the draft: one landing after it would bring it back.
    clearTimeout(s.timer)
    s.pending = null
    await Promise.resolve(s.inflight).catch(() => {})
    const players = filledOf(c).map((id, i) => ({ player_id: id, batting_order: i + 1, is_captain: id === c.cap, is_wicket_keeper: id === c.wk }))
    await api.bsSetSelection(fid, players, [], { lock: true })
    const fresh = await loadCol(c.fx)
    attachSaver(fresh)
    setStatusMap((m) => ({ ...m, [fid]: 'idle' }))
    setCols((prev) => (prev ? { ...prev, [fid]: fresh } : prev))
  }

  const askFirst = (ids) => {
    const lines = []
    ids.forEach((fid) => {
      const c = colsRef.current[fid]
      const n = filledOf(c).length
      const name = ctxShort(c.fx)
      if (sideFit(n, c.size, c.min).off) lines.push(`• ${name}: ${n} player${n === 1 ? '' : 's'} for a ${sideLabel(c.size, c.min)} match`)
      const { warnings } = xiCompliance(c.data.rules, c.poolById, filledOf(c))
      warnings.slice(0, 4).forEach((w) => lines.push(`• ${name}: ${w.player ? w.player + ', ' : ''}${w.detail}`))
    })
    if (!lines.length) return true
    return window.confirm(`Check before confirming:\n\n${lines.slice(0, 12).join('\n')}${lines.length > 12 ? `\n…and ${lines.length - 12} more` : ''}\n\nConfirm anyway?`)
  }

  const refusal = (e) => {
    const breaches = e?.detail?.breaches || e?.data?.detail?.breaches
    if (breaches?.length) return `Can't save, ${breaches.join('; ')}`
    return e.message
  }

  const confirmOne = async (fid) => {
    if (!canEdit || busy || !askFirst([fid])) return
    setBusy(true)
    try {
      await writeConfirm(fid)
      toast.success(`Confirmed ${ctxShort(colsRef.current[fid].fx)}`)
    } catch (e) {
      toast.error(e.message.includes('Already selected')
        ? `${e.message}. Confirm the team they are leaving first, or use Confirm all.`
        : `Could not confirm: ${refusal(e)}`)
    } finally { setBusy(false) }
  }

  // Every changed team. A team the server refuses because a player is still in
  // another confirmed XI waits for the others: the team they are leaving
  // confirms first and the retry goes through.
  const confirmAll = async () => {
    if (!canEdit || busy || !dirtyIds.length || !askFirst(dirtyIds)) return
    setBusy(true)
    let waiting = dirtyIds.slice()
    const done = []
    const failed = []
    try {
      let progress = true
      while (waiting.length && progress) {
        progress = false
        const again = []
        for (const fid of waiting) {
          try { await writeConfirm(fid); done.push(fid); progress = true }
          catch (e) {
            if (String(e.message).includes('Already selected')) again.push(fid)
            else failed.push(`${ctxShort(colsRef.current[fid].fx)}: ${refusal(e)}`)
          }
        }
        waiting = again
      }
      waiting.forEach((fid) => failed.push(`${ctxShort(colsRef.current[fid].fx)}: a player is still in another confirmed XI that day`))
      if (done.length) toast.success(`Confirmed ${done.length} team${done.length === 1 ? '' : 's'}`)
      if (failed.length) toast.error(`Not confirmed. ${failed.join('; ')}`)
    } finally { setBusy(false) }
  }

  const reloadCol = async (fid) => {
    const fresh = await loadCol(colsRef.current[fid].fx)
    attachSaver(fresh)
    setStatusMap((m) => ({ ...m, [fid]: 'idle' }))
    setConflicts((m) => { const n = { ...m }; delete n[fid]; return n })
    setCols((prev) => (prev ? { ...prev, [fid]: fresh } : prev))
  }

  const discard = async (fid) => {
    if (!window.confirm('Discard your unconfirmed changes to this team and go back to its confirmed XI?')) return
    const s = saver(fid)
    clearTimeout(s.timer)
    s.pending = null
    try {
      await Promise.resolve(s.inflight).catch(() => {})
      await api.bsDiscardSelectionDraft(fid, s.version)
      await reloadCol(fid)
    } catch (e) {
      if (e.status === 409 && e.detail?.code === 'draft_conflict') {
        const t = e.detail
        setConflicts((m) => ({ ...m, [fid]: { theirs: t.draft ? { draft: t.draft, version: t.version, by: t.updated_by } : null } }))
      } else toast.error('Could not discard: ' + e.message)
    }
  }

  // The two ways out of a conflict: take what is on the server, or keep this
  // board and save it over.
  const useTheirs = async (fid) => {
    const t = conflicts[fid]?.theirs
    if (!t) { await reloadCol(fid); return }
    const c = colsRef.current[fid]
    const r = restoreDraft(t.draft, c.data.pool, c.size)
    const next = { ...c, slots: tidySlots(r.slots, c.size), cap: r.cap, wk: r.wk, demo: r.demo, fromDraft: { version: t.version || 0 } }
    attachSaver(next)
    setConflicts((m) => { const n = { ...m }; delete n[fid]; return n })
    setCols((prev) => (prev ? { ...prev, [fid]: next } : prev))
  }
  const keepMine = (fid) => {
    const s = saver(fid)
    s.version = conflicts[fid]?.theirs?.version || 0
    s.onServer = !!conflicts[fid]?.theirs
    setConflicts((m) => { const n = { ...m }; delete n[fid]; return n })
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const actions = (
    <button onClick={toggleTheme} title="Toggle theme"
      className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-lg bg-pb-surface2 border border-pb-hairline text-pb-dim hover:text-pb-text">
      <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
    </button>
  )

  if (overview === null || (day && cols === null)) {
    return <BetterSelectLayout title="Selection Whiteboard" actions={actions} wide><PbSpinner message="Loading the whiteboard…" /></BetterSelectLayout>
  }
  if (!days.length) {
    return (
      <BetterSelectLayout title="Selection Whiteboard" actions={actions} wide>
        <div className="pb-card rounded-xl px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures. <Link to="/admin/betterselect/fixtures" className="text-pb-accent underline">Add or sync fixtures</Link> first.
        </div>
      </BetterSelectLayout>
    )
  }
  if (isPhone) {
    return (
      <BetterSelectLayout title="Selection Whiteboard" actions={actions} wide>
        <div className="pb-card rounded-xl px-5 py-8 text-center text-sm text-pb-dim">
          <b className="block text-pb-text font-display text-base mb-1">The Selection Whiteboard needs a wider screen</b>
          Teams sit side by side here, so it is built for a laptop or a tablet held sideways.{' '}
          <Link to="/admin/betterselect/selection" className="text-pb-accent underline">Back to Selection</Link>
        </div>
      </BetterSelectLayout>
    )
  }

  const ctx = {
    weekNames,
    cols, order, merged, status, conflicts, canEdit, busy, activeFid, setActiveFid,
    shortTeam: ctxShort, squadShort, squadOptions, pool, poolTotal: unnamed.length, showGender, weekByPlayer, day,
    filters: { q, setQ, hideOut, setHideOut, squad, setSquad, gender, setGender },
    tapPool, removeAt, toggleCap, toggleWk, confirmOne, discard, useTheirs, keepMine,
  }

  return (
    <BetterSelectLayout title="Selection Whiteboard" actions={actions} wide>
      <div className="flex items-end justify-between gap-x-5 gap-y-2 flex-wrap mb-3">
        <div className="min-w-0">
          <h2 className="font-display font-bold text-[18px] tracking-tight">Selection Whiteboard</h2>
          <p className="text-[13px] text-pb-dim mt-0.5">
            Every team for the day side by side. Drag a player from one team to another, or into and out of the pool. Changes save as drafts until you confirm.
          </p>
          {Object.keys(weekByPlayer).length > 0 && (
            <p className="text-[12px] text-pb-faint mt-0.5 max-w-[70ch]" data-week-legend>
              A coloured dot and <b className="font-mono">{weekNames.w2} ONLY</b> mean free one weekend of a two-day game, away the other. Colours and names are in Settings.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link to="/admin/betterselect/selection" className="inline-flex items-center gap-1.5 text-[12.5px] text-pb-faint hover:text-pb-accent font-display font-semibold">
            <Icon name="list" size={14} />List view
          </Link>
          {canEdit && (
            <Btn variant="primary" sm icon="check" onClick={confirmAll} disabled={busy || dirtyIds.length === 0}>
              {busy ? 'Confirming…' : dirtyIds.length ? `Confirm all (${dirtyIds.length})` : 'All confirmed'}
            </Btn>
          )}
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto pb-2 mb-1" role="tablist" aria-label="Matchday">
        {days.map((d) => {
          const on = d.day === day
          return (
            <button key={d.day} type="button" role="tab" aria-selected={on} data-day={d.day}
              onClick={() => setParams(d.day === days[0].day ? {} : { date: d.day })}
              className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-full border font-display font-semibold text-[12.5px] transition ${on ? '' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}
              style={on ? { color: 'var(--pb-accent)', background: tint('var(--pb-accent)', 13), borderColor: tint('var(--pb-accent)', 45) } : undefined}>
              {fmtDay(d.day === 'tbc' ? null : d.day)}<span className="font-mono text-[11px] opacity-80">{d.n}</span>
            </button>
          )
        })}
      </div>

      <DnD onDrop={onDrop}>
        <Board ctx={ctx} isPhone={isPhone} />
      </DnD>
    </BetterSelectLayout>
  )
}
