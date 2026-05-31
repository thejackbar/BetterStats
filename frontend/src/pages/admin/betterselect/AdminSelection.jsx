// BetterSelect → Selection. The "batting-order slots" board from the design
// handoff (docs/design_handoff_betterselect/prototype/bs-selection-c.jsx):
// the available pool on the left (wider), the XI as numbered 1..N slots on the
// right. Click a pool player to fill the focused/next slot, right-click for the
// next empty, or drag onto a specific slot. Captain/keeper toggles live on each
// filled slot. Auto-fill tops up empty slots with the best available player.
//
// Recreated with the real API + atom kit. Semantic availability colours
// (green/amber/red) are fixed; the club accent is reserved for chrome.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY, availRank } from '../../../lib/availability'
import {
  Icon, Avatar, AvailDot, RoleChips, Tag, Btn, Segmented, Search, Chip, Empty, QuickAvailModal,
  RecencySelect, playedWithinYears,
} from './ui'

const FORMATS = [
  { value: 11, label: '11' },
  { value: 12, label: '12' },
  { value: 13, label: '13' },
  { value: 0, label: 'No limit' },
]

// Soft positional hints + which roles "fit" each slot (drives suggestions).
const POS_HINTS = ['Opener', 'Opener', 'First drop', 'Top order', 'Top order', 'Middle order', 'Middle order', 'All-rounder', 'Lower order', 'Tail', 'Tail', '12th', '13th']
function slotAccepts(i) {
  if (i <= 1) return ['BAT', 'WKT']
  if (i <= 4) return ['BAT', 'WKT', 'ALL']
  if (i <= 6) return ['BAT', 'ALL', 'WKT']
  if (i === 7) return ['ALL', 'WKT', 'BWL']
  return ['BWL', 'ALL']
}
function fitsSlot(p, i) {
  const acc = slotAccepts(i)
  return (p.skill_positions || []).some((r) => acc.includes(r))
}
const ROLE_CHIPS = ['BAT', 'BWL', 'ALL', 'WKT']
const ROLE_LABEL = { BAT: 'BAT', BWL: 'BWL', ALL: 'ALL', WKT: 'WK' }

function fmtHeader(fx) {
  if (!fx) return { title: 'Selection', sub: '' }
  const us = fx.home_away === 'AWAY' ? (fx.away_team || 'Us') : (fx.home_team || 'Us')
  const opp = fx.opponent_name || fx.label || 'TBC'
  const title = fx.home_away === 'BYE' ? 'BYE' : `${us} vs ${opp}`
  const bits = []
  if (fx.round) bits.push(`Round ${fx.round}`)
  if (fx.played_on) {
    try { bits.push(new Date(fx.played_on + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })) }
    catch { bits.push(fx.played_on) }
  }
  if (fx.start_time) bits.push(fx.start_time)
  if (fx.venue) bits.push(`${fx.venue}${fx.home_away === 'AWAY' ? ' (A)' : fx.home_away === 'HOME' ? ' (H)' : ''}`)
  return { title, sub: bits.join(' · ') }
}

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [slots, setSlots] = useState([])     // [playerId|null], length = slot count
  const [capId, setCapId] = useState(null)
  const [wkId, setWkId] = useState(null)
  const [focus, setFocus] = useState(null)
  const [format, setFormat] = useState(11)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [search, setSearch] = useState('')
  const [roleF, setRoleF] = useState(null)
  const [availOnly, setAvailOnly] = useState(false)
  const [squadF, setSquadF] = useState('')          // '' = any squad
  const [yearsF, setYearsF] = useState(3)           // recency: played within N yrs (0 = any)
  const [selStatusF, setSelStatusF] = useState('')  // '' | 'unselected' | 'clash'
  const [showFilters, setShowFilters] = useState(false)
  const [availEdit, setAvailEdit] = useState(null) // player object for quick-update modal
  const [showSheet, setShowSheet] = useState(false)
  const [copied, setCopied] = useState(false)
  const [allFixtures, setAllFixtures] = useState([])
  const [prevXI, setPrevXI] = useState(null) // { player_ids, captain_id, wicket_keeper_id, source_* }

  const dragId = useRef(null)       // pool player being dragged
  const dragSlot = useRef(null)     // slot index being dragged (reorder)

  const load = useCallback(() => {
    setData(null)
    api.bsGetSelection(fixtureId)
      .then((d) => {
        setData(d)
        const size = d.default_team_size ?? 11
        const lineup = (d.lineup || []).slice().sort((a, b) => (a.batting_order || 999) - (b.batting_order || 999))
        const count = size > 0 ? Math.max(size, lineup.length) : lineup.length
        const init = Array(count).fill(null)
        lineup.forEach((l, i) => { if (i < count) init[i] = l.player_id })
        setSlots(init)
        setCapId(lineup.find((l) => l.is_captain)?.player_id ?? null)
        setWkId(lineup.find((l) => l.is_wicket_keeper)?.player_id ?? null)
        setFormat(size)
        setFocus(init.findIndex((x) => x == null))
        setDirty(false)
      })
      .catch((e) => { toast.error(e.message); setData({ pool: [], lineup: [], fixture: null }) })
  }, [fixtureId, toast])

  useEffect(() => { load() }, [load])
  useEffect(() => { api.bsSelectionOverview().then((d) => setAllFixtures(d.fixtures || [])).catch(() => {}) }, [])
  useEffect(() => { setPrevXI(null); api.bsPreviousXI(fixtureId).then(setPrevXI).catch(() => setPrevXI(null)) }, [fixtureId])

  const fx = data?.fixture
  const poolById = useMemo(() => {
    const m = {}
    ;(data?.pool || []).forEach((p) => { m[p.id] = p })
    return m
  }, [data])
  const usedIds = useMemo(() => new Set(slots.filter(Boolean)), [slots])

  // Comparator: autofill tier (own-squad → grade below → grade above), then
  // composite form score, then availability, then name. Tier/score come from
  // the backend; ineligibles (null tier) sink to the bottom.
  const cmp = useCallback((a, b) => {
    const at = a.tier ?? 99, bt = b.tier ?? 99
    if (at !== bt) return at - bt
    const sa = a.score ?? 0, sb = b.score ?? 0
    if (sa !== sb) return sb - sa
    const r = availRank(a.availability) - availRank(b.availability)
    if (r !== 0) return r
    return (a.display_name || '').localeCompare(b.display_name || '')
  }, [])

  const squadOptions = useMemo(() => {
    const s = new Set()
    ;(data?.pool || []).forEach((p) => (p.squads || []).forEach((sq) => s.add(sq)))
    return [...s].sort()
  }, [data])


  const pool = useMemo(() => {
    let list = (data?.pool || []).filter((p) => !usedIds.has(p.id))
    if (search.trim()) list = list.filter((p) => (p.display_name || '').toLowerCase().includes(search.trim().toLowerCase()))
    if (roleF) list = list.filter((p) => (p.skill_positions || []).includes(roleF))
    if (availOnly) list = list.filter((p) => p.availability === 'AVAILABLE')
    if (squadF) list = list.filter((p) => (p.squads || []).includes(squadF))
    if (yearsF) list = list.filter((p) => playedWithinYears(p.last_played, yearsF))
    if (selStatusF === 'unselected') list = list.filter((p) => !(p.clash?.length > 0))
    else if (selStatusF === 'clash') list = list.filter((p) => p.clash?.length > 0)
    return list.slice().sort(cmp)
  }, [data, usedIds, search, roleF, availOnly, squadF, yearsF, selStatusF, cmp])

  const activeFilters = (squadF ? 1 : 0) + (yearsF ? 1 : 0) + (selStatusF ? 1 : 0)

  const filled = slots.filter(Boolean)
  const count = filled.length
  const target = format || 0
  const offCount = target > 0 && count !== target

  // ── Slot mutations ────────────────────────────────────────────────────────
  const markDirty = () => setDirty(true)

  const placeInSlot = (slotIdx, playerId) => {
    setSlots((prev) => {
      const next = [...prev]
      const existing = next.indexOf(playerId)
      if (existing !== -1) next[existing] = null
      next[slotIdx] = playerId
      return next
    })
    markDirty()
    setFocus((f) => {
      // advance focus to the next empty slot after this one
      const after = slots.findIndex((x, i) => i > slotIdx && x == null)
      return after
    })
  }

  const tapPlayer = (p) => {
    if (!canEdit) return
    if (p.clash?.length > 0) { toast.error(`${p.display_name} is already picked for ${p.clash.join(', ')} that day`); return }
    setSlots((prev) => {
      const next = [...prev]
      const existing = next.indexOf(p.id)
      if (existing !== -1) next[existing] = null
      let target = focus != null && next[focus] == null ? focus : next.indexOf(null)
      if (target === -1) {
        if (format === 0) { next.push(p.id); return next }  // no-limit: append
        toast.error('All slots are full — increase the side size to add more.')
        return prev
      }
      next[target] = p.id
      return next
    })
    markDirty()
    setFocus(() => slots.findIndex((x) => x == null && x !== undefined))
  }

  const addNext = (p) => { // right-click → next empty
    if (!canEdit || p.clash?.length > 0) return
    setSlots((prev) => {
      const next = [...prev]
      if (next.indexOf(p.id) !== -1) return prev
      const t = next.indexOf(null)
      if (t === -1) { if (format === 0) { next.push(p.id); return next } return prev }
      next[t] = p.id
      return next
    })
    markDirty()
  }

  const removeAt = (i) => {
    setSlots((prev) => { const n = [...prev]; const id = n[i]; n[i] = null; if (id === capId) setCapId(null); if (id === wkId) setWkId(null); return n })
    markDirty()
    setFocus(i)
  }

  const onDropSlot = (i) => {
    if (dragId.current) { placeInSlot(i, dragId.current); dragId.current = null }
    else if (dragSlot.current != null) {
      const from = dragSlot.current
      dragSlot.current = null
      if (from === i) return
      setSlots((prev) => { const next = [...prev]; const moved = next[from]; next[from] = next[i]; next[i] = moved; return next })
      markDirty()
    }
  }

  const toggleCap = (id) => { setCapId((c) => (c === id ? null : id)); markDirty() }
  const toggleWk = (id) => { setWkId((c) => (c === id ? null : id)); markDirty() }

  // Per-slot suggestion: best autofill-eligible candidate that fits the slot's
  // role band (openers for 1-2, bowlers for 9-11, etc.). Same tier discipline
  // as fillEmpty — never proposes a women's-grade player for a men's fixture
  // or a 1st XI regular for a 6th XI sheet.
  const suggestMap = useMemo(() => {
    const out = {}
    const taken = new Set(slots.filter(Boolean))
    const eligible = (data?.pool || []).filter((p) =>
      p.autofill_eligible && !taken.has(p.id) && !(p.clash?.length > 0) && p.availability !== 'UNAVAILABLE'
    )
    slots.forEach((id, i) => {
      if (id) return
      const fit = eligible.filter((p) => !taken.has(p.id) && fitsSlot(p, i)).sort(cmp)
      const any = eligible.filter((p) => !taken.has(p.id)).sort(cmp)
      const pick = fit[0] || any[0]
      if (pick) { out[i] = pick; taken.add(pick.id) }
    })
    return out
  }, [slots, data, cmp])

  // Fill empty slots. With `useLastWeek`, seed position-by-position from the
  // previous XI first (skipping anyone now unavailable/clashing/already in),
  // then top up remaining gaps with the best available player.
  //
  // Tier discipline: own-squad players fill first; only when that pool is
  // exhausted do we dip into the grade below (promotion candidates), then the
  // grade above (drop-down candidates). A player carried over from last week
  // who's no longer eligible (e.g. they've moved squads) stays put — we don't
  // tear last week's XI apart, but we don't bring more like them in either.
  const fillEmpty = (useLastWeek) => {
    if (!canEdit) return
    // No-limit has no fixed slots to fill — autofill would be meaningless.
    if (format === 0) { toast.error('Set a side size (11/12/13) to auto-fill'); return }
    const okToPick = (p) => p && !(p.clash?.length > 0) && p.availability !== 'UNAVAILABLE'
    setSlots((prev) => {
      const next = [...prev]
      const taken = new Set(next.filter(Boolean))
      if (useLastWeek && prevXI?.player_ids?.length) {
        prevXI.player_ids.forEach((pid, i) => {
          if (i >= next.length || next[i]) return
          const p = poolById[pid]
          if (p && !taken.has(pid) && okToPick(p)) { next[i] = pid; taken.add(pid) }
        })
      }
      const eligible = (data?.pool || []).filter((p) => p.autofill_eligible && okToPick(p))
      for (const tier of [1, 2, 3]) {
        if (next.every(Boolean)) break
        const tierPool = eligible.filter((p) => p.tier === tier)
        if (!tierPool.length) continue
        next.forEach((id, i) => {
          if (id) return
          const fit = tierPool.filter((p) => !taken.has(p.id) && fitsSlot(p, i)).sort(cmp)
          const any = tierPool.filter((p) => !taken.has(p.id)).sort(cmp)
          const pick = fit[0] || any[0]
          if (pick) { next[i] = pick.id; taken.add(pick.id) }
        })
      }
      return next
    })
    // Carry captain/keeper from last week if those slots are otherwise unset.
    if (useLastWeek && prevXI) {
      if (!capId && prevXI.captain_id && poolById[prevXI.captain_id]) setCapId(prevXI.captain_id)
      if (!wkId && prevXI.wicket_keeper_id && poolById[prevXI.wicket_keeper_id]) setWkId(prevXI.wicket_keeper_id)
    }
    markDirty()
  }

  // ── Format (persisted club default) ──────────────────────────────────────
  const changeFormat = async (size) => {
    setFormat(size)
    setSlots((prev) => {
      if (size === 0) return prev.filter(Boolean) // collapse to filled
      const next = prev.slice(0, size)
      while (next.length < size) next.push(null)
      // drop cap/wk if they fell off the end
      const kept = new Set(next.filter(Boolean))
      if (capId && !kept.has(capId)) setCapId(null)
      if (wkId && !kept.has(wkId)) setWkId(null)
      return next
    })
    if (canEdit) { try { await api.bsSetDefaultTeamSize(size) } catch (e) { toast.error('Could not save side size: ' + e.message) } }
  }

  // ── Availability quick-update ────────────────────────────────────────────
  const pickAvail = async (status) => {
    const p = availEdit
    setAvailEdit(null)
    if (!p || !fx?.played_on) { if (!fx?.played_on) toast.error('No fixture date to set availability against'); return }
    setData((d) => ({ ...d, pool: d.pool.map((x) => (x.id === p.id ? { ...x, availability: status } : x)) }))
    try { await api.bsSetAvailability({ player_id: p.id, date: fx.played_on, status }) }
    catch (e) { toast.error('Could not update availability: ' + e.message); load() }
  }

  // ── Save ─────────────────────────────────────────────────────────────────
  const save = async () => {
    if (offCount) {
      const diff = count > target ? `${count - target} too many` : `${target - count} too few`
      if (!window.confirm(`You have ${count} player${count === 1 ? '' : 's'} for a ${target}-a-side match — ${diff}.\n\nSave anyway?`)) return
    }
    setSaving(true)
    try {
      const players = filled.map((id, i) => ({ player_id: id, batting_order: i + 1, is_captain: id === capId, is_wicket_keeper: id === wkId }))
      const r = await api.bsSetSelection(fixtureId, players)
      toast.success(`Saved ${r.count} player${r.count === 1 ? '' : 's'}`)
      setDirty(false)
      load()
    } catch (e) {
      toast.error(e.message.includes('Already selected') ? e.message : 'Save failed: ' + e.message)
    } finally { setSaving(false) }
  }

  // ── Share ────────────────────────────────────────────────────────────────
  const lineupText = () => {
    const head = fmtHeader(fx)
    const lines = filled.map((id, i) => {
      const p = poolById[id]
      const tags = [id === capId && '(C)', id === wkId && '(WK)'].filter(Boolean).join(' ')
      return `${i + 1}. ${p?.display_name || '—'}${tags ? ' ' + tags : ''}`
    })
    return `${head.title}${head.sub ? '\n' + head.sub : ''}\n\n${lines.join('\n')}`
  }
  const copyLineup = async () => {
    try { await navigator.clipboard.writeText(lineupText()); setCopied(true); setTimeout(() => setCopied(false), 1800) }
    catch { toast.error('Copy failed — select and copy manually') }
  }
  const openSocial = () => {
    navigate('/admin/social-post', {
      state: {
        teamSheet: {
          players: filled.map((id) => {
            const p = poolById[id]
            return { player_id: id, role: (p?.skill_positions?.[0]) || p?.player_role || 'BAT', is_captain: id === capId, is_wicket_keeper: id === wkId }
          }),
          match: { round: fx?.round || '', venue: fx?.venue || '', date: fx?.played_on || '', time: fx?.start_time || '' },
          opponent: { name: fx?.opponent_name || '' },
        },
      },
    })
  }

  // ── Team balance ─────────────────────────────────────────────────────────
  const balance = useMemo(() => {
    const has = (id, code) => (poolById[id]?.skill_positions || []).includes(code)
    const b = { BAT: 0, ALL: 0, BWL: 0, WKT: 0 }
    filled.forEach((id) => { ['BAT', 'ALL', 'BWL', 'WKT'].forEach((c) => { if (has(id, c)) b[c] += 1 }) })
    const bowlers = filled.filter((id) => has(id, 'BWL') || has(id, 'ALL')).length
    return { ...b, lightBowling: count >= 8 && bowlers < 5, hasKeeper: filled.some((id) => has(id, 'WKT')) }
  }, [filled, poolById, count])

  if (data === null) return <BetterSelectLayout title="Selection"><PbSpinner message="Loading selection…" /></BetterSelectLayout>

  const { title, sub } = fmtHeader(fx)
  // Auto-fill only applies to fixed-size sides with empty slots — never No Limit.
  const canAutofill = format > 0 && slots.some((x) => x == null)
  const capOk = capId && filled.includes(capId)
  const wkOk = wkId && filled.includes(wkId)

  const hasPrev = (prevXI?.player_ids?.length || 0) > 0
  const actions = canEdit && (
    <div className="flex gap-2">
      {canAutofill && hasPrev && <Btn variant="ghost" sm icon="bolt" onClick={() => fillEmpty(true)} title="Seed empty slots from last week's XI, then top up">Fill from last week</Btn>}
      {canAutofill && <Btn variant="ghost" sm icon="bolt" onClick={() => fillEmpty(false)}>Auto-fill</Btn>}
      <Btn variant="soft" sm icon="share" onClick={() => setShowSheet(true)} disabled={count === 0}>Share</Btn>
      <Btn variant="primary" sm icon="check" onClick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : dirty ? `Save XI (${count})` : 'Saved'}</Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Selection" actions={actions}>
      {/* Context bar — fixture identity + side size + count (accent banner = legit white-label) */}
      <div className="rounded-lg px-5 py-3 mb-3" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
        <div className="flex items-center justify-between gap-3">
          <Link to="/admin/betterselect/selection" className="text-[11px] opacity-80 hover:opacity-100">← All teams</Link>
          {allFixtures.length > 1 && (
            <select value={fixtureId} onChange={(e) => navigate(`/admin/betterselect/select/${e.target.value}`)}
              className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[11px] text-pb-text max-w-[55%]">
              {allFixtures.map((f) => (
                <option key={f.id} value={f.id} style={{ color: '#000' }}>
                  {(f.home_away === 'AWAY' ? '@ ' : 'vs ') + (f.opponent_name || f.label || 'TBC')}{f.played_on ? ` · ${f.played_on}` : ''}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2 mt-1">
          <div>
            <h2 className="font-display font-bold text-xl leading-tight text-pb-text">{title}</h2>
            {sub && <div className="text-sm text-pb-faint">{sub}</div>}
          </div>
          <div className="flex items-center gap-2">
            <Segmented value={format} onChange={changeFormat} sm options={FORMATS} />
            <span className="font-mono text-xs font-bold px-2.5 py-1 rounded-full"
              style={{ background: offCount ? 'var(--pb-amber)' : 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: offCount ? '#1b1205' : 'var(--pb-accent)' }}>
              {count}{target > 0 ? ` / ${target}` : ''} picked
            </span>
          </div>
        </div>
      </div>

      {/* Team-balance strip */}
      <div className="pb-card px-4 py-2.5 mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        {['BAT', 'ALL', 'BWL', 'WKT'].map((c) => {
          const low = (c === 'BWL' && balance.lightBowling) || (c === 'WKT' && !balance.hasKeeper)
          return (
            <span key={c} className="inline-flex items-center gap-1.5 text-[13px]">
              <span className="font-mono text-[10px] tracking-wide2" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{ROLE_LABEL[c]}</span>
              <b className="pb-num" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{balance[c]}</b>
            </span>
          )
        })}
        <span className="h-4 w-px bg-pb-hairline2" />
        <span className="inline-flex items-center gap-1.5 text-[12px]" style={{ color: capOk ? 'var(--pb-text)' : 'var(--pb-faint)' }}>
          <Tag tone={capOk ? 'accent' : 'faint'}>C</Tag>{capOk ? (poolById[capId]?.display_name || 'Captain') : 'No captain'}
        </span>
        <span className="inline-flex items-center gap-1.5 text-[12px]" style={{ color: wkOk ? 'var(--pb-text)' : 'var(--pb-amber)' }}>
          <Tag tone={wkOk ? 'amber' : 'faint'}>WK</Tag>{wkOk ? (poolById[wkId]?.display_name || 'Keeper') : 'No keeper named'}
        </span>
        {balance.lightBowling && <span className="ml-auto text-[12px] text-pb-amber inline-flex items-center gap-1.5"><Icon name="info" size={13} /> Light on bowling</span>}
      </div>

      {/* Body: pool (left, wider) + numbered slots (right) */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* POOL */}
        <div className="pb-card flex flex-col min-h-0">
          <div className="px-3 py-2.5 border-b pb-hairline flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Search value={search} onChange={setSearch} placeholder="Search players…" className="flex-1 min-w-[160px]" />
              {ROLE_CHIPS.map((r) => <Chip key={r} label={ROLE_LABEL[r]} active={roleF === r} onClick={() => setRoleF(roleF === r ? null : r)} />)}
              <Chip label="Available only" active={availOnly} onClick={() => setAvailOnly(!availOnly)} />
              <Btn variant={showFilters || activeFilters ? 'soft' : 'ghost'} sm icon="filter" onClick={() => setShowFilters((v) => !v)}>
                {activeFilters ? `Filters (${activeFilters})` : 'Filters'}
              </Btn>
            </div>
            {showFilters && (
              <div className="flex flex-wrap items-center gap-3 pt-1.5 border-t pb-hairline">
                {squadOptions.length > 0 && (
                  <label className="inline-flex items-center gap-1.5 text-[11.5px] text-pb-faint">
                    Squad
                    <select value={squadF} onChange={(e) => setSquadF(e.target.value)}
                      className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent">
                      <option value="">Any</option>
                      {squadOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </label>
                )}
                <span className="inline-flex items-center gap-1.5 text-[11.5px] text-pb-faint">
                  Recency <RecencySelect value={yearsF} onChange={setYearsF} />
                </span>
                <span className="inline-flex items-center gap-1 text-[11.5px] text-pb-faint">
                  Status
                  <Chip label="Unselected" active={selStatusF === 'unselected'} onClick={() => setSelStatusF(selStatusF === 'unselected' ? '' : 'unselected')} />
                  <Chip label="In another XI" active={selStatusF === 'clash'} onClick={() => setSelStatusF(selStatusF === 'clash' ? '' : 'clash')} />
                </span>
                {activeFilters > 0 && <button onClick={() => { setSquadF(''); setYearsF(0); setSelStatusF('') }} className="text-[11.5px] text-pb-accent hover:underline">Clear</button>}
              </div>
            )}
          </div>
          <div className="overflow-auto flex-1 p-2 flex flex-col gap-1 pb-scroll max-h-[60vh] lg:max-h-[calc(100vh-360px)]">
            {pool.map((p) => {
              const clash = p.clash?.length > 0
              const meta = AVAILABILITY[p.availability] || AVAILABILITY.NO_RESPONSE
              return (
                <div key={p.id}
                  draggable={canEdit && !clash}
                  onDragStart={() => { dragId.current = p.id }}
                  onDragEnd={() => { dragId.current = null }}
                  onClick={() => tapPlayer(p)}
                  onContextMenu={(e) => { e.preventDefault(); addNext(p) }}
                  className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border border-pb-hairline ${clash ? 'opacity-50 cursor-not-allowed' : canEdit ? 'cursor-pointer hover:border-pb-accent/40' : ''}`}
                  style={{ background: p.availability === 'NO_RESPONSE' || !p.availability ? 'var(--pb-surface2)' : `color-mix(in srgb, ${meta.cssVar} 7%, var(--pb-surface2))` }}>
                  <AvailDot player={p} status={p.availability} onEdit={canEdit ? setAvailEdit : undefined} />
                  <Avatar player={p} size={28} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate">{p.display_name}</div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <RoleChips roles={p.skill_positions} muted />
                      {p.availability_reason && <span className="text-[10.5px] text-pb-faint truncate">{p.availability_reason}</span>}
                    </div>
                  </div>
                  {p.squads?.[0] && <Tag tone={p.squad_match ? 'accent' : 'faint'}>{p.squads[0]}</Tag>}
                  {clash
                    ? <span className="font-mono text-[9px] text-pb-red whitespace-nowrap">⛔ {p.clash.join(', ')}</span>
                    : canEdit && <span className="text-pb-faintest"><Icon name="arrow" size={16} /></span>}
                </div>
              )
            })}
            {pool.length === 0 && <div className="p-4"><Empty>No players match.</Empty></div>}
          </div>
        </div>

        {/* SLOTS */}
        <div className="pb-card flex flex-col min-h-0">
          <div className="px-4 py-2.5 border-b pb-hairline flex items-center justify-between">
            <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">Batting order</h3>
            <span className="font-mono text-[11px] text-pb-faint pb-num">{count}{target > 0 ? `/${target}` : ''}</span>
          </div>
          <div className="overflow-auto flex-1 p-2 flex flex-col gap-1 pb-scroll max-h-[60vh] lg:max-h-[calc(100vh-360px)]">
            {slots.map((id, i) => {
              const p = id ? poolById[id] : null
              const isFocus = focus === i
              const sug = !id ? suggestMap[i] : null
              return (
                <div key={i}
                  onDragOver={(e) => { if (canEdit) e.preventDefault() }}
                  onDrop={() => canEdit && onDropSlot(i)}
                  onClick={() => !id && setFocus(i)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors"
                  style={{
                    borderColor: isFocus && !id ? 'var(--pb-accent)' : 'var(--pb-hairline)',
                    borderStyle: id ? 'solid' : 'dashed',
                    background: id ? 'var(--pb-surface2)' : isFocus ? 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' : 'transparent',
                  }}>
                  <span className="font-mono text-xs text-pb-faintest w-5 text-right shrink-0">{i + 1}</span>
                  {p ? (
                    <>
                      <span draggable={canEdit} onDragStart={() => { dragSlot.current = i }} onDragEnd={() => { dragSlot.current = null }} className={canEdit ? 'cursor-grab text-pb-faintest shrink-0' : 'hidden'}><Icon name="grip" size={13} /></span>
                      <AvailDot player={p} status={p.availability} onEdit={canEdit ? setAvailEdit : undefined} />
                      <Avatar player={p} size={24} />
                      <div className="flex-1 min-w-0 flex items-center gap-1.5">
                        <span className="text-[13px] font-medium truncate">{p.display_name}</span>
                        {id === capId && <Tag>C</Tag>}{id === wkId && <Tag tone="amber">WK</Tag>}
                        <span className="text-[10px] text-pb-faintest hidden xl:inline">{POS_HINTS[i] || ''}</span>
                      </div>
                      {canEdit && (
                        <div className="flex items-center gap-1 shrink-0">
                          <button onClick={() => toggleCap(id)} title="Captain" className={`w-6 h-6 rounded text-[10px] font-bold font-mono ${id === capId ? 'bg-pb-accent text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>C</button>
                          <button onClick={() => toggleWk(id)} title="Wicket-keeper" className={`w-6 h-6 rounded text-[10px] font-bold font-mono ${id === wkId ? 'bg-pb-amber text-pb-bg' : 'bg-pb-surface text-pb-faint hover:text-pb-text'}`}>WK</button>
                          <button onClick={() => removeAt(i)} title="Remove" className="w-6 h-6 rounded text-pb-faintest hover:text-pb-red hover:bg-pb-red/10"><Icon name="close" size={13} /></button>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="flex-1 flex items-center gap-2 min-w-0">
                      <span className="text-[11px] text-pb-faintest">{POS_HINTS[i] || 'Empty'}</span>
                      {sug && (
                        isFocus ? (
                          <button onClick={(e) => { e.stopPropagation(); placeInSlot(i, sug.id) }} disabled={!canEdit}
                            className="ml-auto inline-flex items-center gap-1.5 text-[11.5px] text-pb-accent hover:underline">
                            <Icon name="plus" size={13} /> {sug.display_name}
                          </button>
                        ) : (
                          <span className="ml-auto text-[11px] text-pb-faint truncate">try {sug.display_name}</span>
                        )
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {format === 0 && (
              <div onClick={() => toast.info ? toast.info('Tap a player in the pool to add') : null}
                className="px-2.5 py-3 rounded-lg border border-dashed border-pb-hairline2 text-center text-[11.5px] text-pb-faintest">
                Tap a player to add to the order
              </div>
            )}
          </div>
        </div>
      </div>

      {availEdit && (
        <QuickAvailModal player={availEdit} dateLabel={fx?.played_on} current={availEdit.availability}
          onPick={pickAvail} onClose={() => setAvailEdit(null)} />
      )}

      {showSheet && (
        <div onClick={() => setShowSheet(false)} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div onClick={(e) => e.stopPropagation()} className="w-[420px] max-w-full max-h-[85%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
            <div className="px-[18px] py-4 border-b pb-hairline flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Team sheet</div>
                <div className="font-display font-bold text-[17px] mt-0.5 truncate">{title}</div>
                {sub && <div className="text-[12px] text-pb-dim">{sub}</div>}
              </div>
              <button onClick={() => setShowSheet(false)} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
            </div>
            <div className="overflow-auto flex-1 pb-scroll">
              {filled.map((id, i) => {
                const p = poolById[id]
                return (
                  <div key={id} className="flex items-center gap-3 px-4 py-2 border-b pb-hairline">
                    <span className="font-mono text-xs text-pb-faintest w-5 text-right">{i + 1}</span>
                    <Avatar player={p} size={26} />
                    <span className="flex-1 text-[13.5px] truncate">{p?.display_name}{id === capId && <> <Tag>C</Tag></>}{id === wkId && <> <Tag tone="amber">WK</Tag></>}</span>
                    <RoleChips roles={p?.skill_positions} muted />
                  </div>
                )
              })}
              {count === 0 && <div className="p-4"><Empty>No players selected.</Empty></div>}
              {offCount && <div className="px-4 py-2 text-[12px] text-pb-amber">{count > target ? `${count - target} over` : `${target - count} short of`} your {target}-a-side format.</div>}
            </div>
            <div className="px-4 py-3 border-t pb-hairline flex items-center gap-2">
              <Btn variant="soft" sm icon="check" onClick={copyLineup}>{copied ? 'Copied!' : 'Copy lineup as text'}</Btn>
              <Btn variant="primary" sm icon="share" onClick={openSocial} disabled={count === 0}>Open in social post</Btn>
            </div>
          </div>
        </div>
      )}
    </BetterSelectLayout>
  )
}
