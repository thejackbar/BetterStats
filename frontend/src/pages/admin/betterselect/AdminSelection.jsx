// BetterSelect → Selection. The team-picking "hero feature", rebuilt to the
// design handoff (docs/design_handoff_selection_redesign): one shared selection
// state rendered two toggleable ways —
//   • Dual rail   — Available pool ↔ Selected XI (build the side)
//   • Team sheet  — a numbered batting-order spine drafted from a pool grid
//
// Both are fully bidirectional via the pointer DnD engine (pool→XI, XI→pool to
// remove, drag-to-reorder) PLUS tap/click-to-place (primary on mobile). Player
// rows show the real role + style + a quiet form indicator (roleLine + FormBars)
// instead of the old hardcoded positional hints. The pool filters are expanded
// (availability / bowling / batting-hand / form / a searchable squad picker /
// selection status) on top of the existing search + recency.
//
// Wired to the real selection API + atom kit. Availability colours stay
// semantic (green/amber/red); the club accent is reserved for chrome.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { useTheme } from '../../../contexts/ThemeContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { availRank } from '../../../lib/availability'
import { Icon, Avatar, Btn, RoleChips, Tag, Empty, QuickAvailModal, playedWithinYears } from './ui'
import { useFilters } from './filters'
import SelectionFilters from './SelectionFilters'
import { DnD } from './selectionDnd'
import { DualRailView, TeamSheetView } from './SelectionViews'
import { classifyBowl, formBucket } from './selectionMeta'

// Soft role-band each batting slot prefers — drives auto-fill placement (the
// displayed positional *hints* are gone, but the eligibility model is useful).
function slotAccepts(i) {
  if (i <= 1) return ['BAT', 'WKT']
  if (i <= 4) return ['BAT', 'WKT', 'ALL']
  if (i <= 6) return ['BAT', 'ALL', 'WKT']
  if (i === 7) return ['ALL', 'WKT', 'BWL']
  return ['BWL', 'ALL']
}
function fitsSlot(p, i) {
  return (p.skill_positions || []).some((r) => slotAccepts(i).includes(r))
}

// Longest shared leading word-run across squad names, so a tag reads "2nd XI"
// not "Applecross 2nd XI" without hardcoding the club name.
function commonPrefixWord(names) {
  if (names.length < 2) return ''
  let prefix = names[0]
  for (const n of names.slice(1)) {
    let i = 0
    while (i < prefix.length && i < n.length && prefix[i] === n[i]) i++
    prefix = prefix.slice(0, i)
    if (!prefix) break
  }
  const cut = prefix.lastIndexOf(' ')
  return cut > 0 ? prefix.slice(0, cut + 1) : ''
}
const stripPrefix = (prefix, name) => (prefix && name?.startsWith(prefix) ? name.slice(prefix.length) : name)

// ── Team switcher (which of our teams this fixture is for) ───────────────────
// Seniority rank for ordering a matchday's teams (1 = top team). Prefer the
// explicit Team.sequence; fall back to the first number in the team/grade name
// (mirrors the backend's _guess_sequence); unranked teams sink to the bottom.
function teamSeq(f) {
  if (f?.team_sequence && f.team_sequence > 0) return f.team_sequence
  const m = (f?.team_name || f?.grade_name || '').match(/(\d+)/)
  return m ? parseInt(m[1], 10) : 999
}
const teamNameOf = (f) => f?.team_name || f?.grade_name || f?.opponent_name || f?.label || 'Team'
const oppLabelOf = (f) =>
  f?.home_away === 'BYE' ? 'BYE' : `${f?.home_away === 'AWAY' ? '@ ' : 'vs '}${f?.opponent_name || f?.label || 'TBC'}`

// A dropdown of the teams playing on this fixture's date (current team shown,
// switch to any other) flanked by ◀ / ▶ to jump one team higher / lower in the
// club hierarchy. The arrows grey out when there's no team above / below.
function TeamSwitcher({ fixtureId, fx, fixtures, navigate, shortTeam }) {
  const dayKey = fx?.played_on || null
  const group = useMemo(() => {
    let g = (fixtures || []).filter((f) => (f.played_on || null) === dayKey)
    // The overview is upcoming-only — inject the current fixture if it's absent
    // (e.g. opening a past fixture directly) so the control stays consistent.
    if (fixtureId && fx && !g.some((f) => f.id === fixtureId)) {
      g = [{ id: fixtureId, team_name: fx.team_name, grade_name: fx.grade_name, team_sequence: fx.team_sequence,
             opponent_name: fx.opponent_name, label: fx.label, home_away: fx.home_away, played_on: fx.played_on }, ...g]
    }
    return g.slice().sort((a, b) => teamSeq(a) - teamSeq(b) || teamNameOf(a).localeCompare(teamNameOf(b)))
  }, [fixtures, dayKey, fixtureId, fx])

  const idx = group.findIndex((f) => f.id === fixtureId)
  const cur = idx >= 0 ? group[idx] : null
  const higher = idx > 0 ? group[idx - 1] : null
  const lower = idx >= 0 && idx < group.length - 1 ? group[idx + 1] : null
  const go = (id) => id && navigate(`/admin/betterselect/select/${id}`)
  const optLabel = (f) => [shortTeam(f), oppLabelOf(f)].filter(Boolean).join(' · ')
  const destName = (f) => shortTeam(f) || oppLabelOf(f)

  if (group.length === 0) return null

  const Arrow = ({ to, side }) => (
    <button type="button" onClick={() => go(to?.id)} disabled={!to}
      title={to ? `${side === 'left' ? 'Higher' : 'Lower'} team: ${destName(to)}` : `No ${side === 'left' ? 'higher' : 'lower'} team today`}
      aria-label={to ? `Switch to ${destName(to)}` : undefined}
      className={`shrink-0 w-[26px] h-[26px] rounded-md inline-flex items-center justify-center border transition ${
        to ? 'border-pb-hairline2 text-pb-dim hover:text-pb-accent hover:border-pb-accent/50' : 'border-pb-hairline text-pb-faintest opacity-40 cursor-not-allowed'
      }`}>
      <Icon name="chevron" size={15} style={{ transform: side === 'left' ? 'rotate(180deg)' : 'none' }} />
    </button>
  )

  return (
    <div className="flex items-center gap-1 min-w-0" title="Team being selected">
      <Arrow to={higher} side="left" />
      {group.length > 1 ? (
        <div className="relative min-w-0">
          <select value={fixtureId} onChange={(e) => go(e.target.value)} title="Switch team for this matchday"
            className="appearance-none bg-pb-surface border border-pb-hairline2 rounded-md pl-2.5 pr-7 py-1 font-display font-bold text-[12.5px] text-pb-text max-w-[210px] truncate cursor-pointer hover:border-pb-accent/50">
            {group.map((f) => <option key={f.id} value={f.id} style={{ color: '#000' }}>{optLabel(f)}</option>)}
          </select>
          <Icon name="chevron" size={12} className="pointer-events-none absolute right-2 top-1/2 text-pb-faint" style={{ transform: 'translateY(-50%) rotate(90deg)' }} />
        </div>
      ) : (
        <span className="font-display font-bold text-[12.5px] text-pb-text max-w-[210px] truncate px-1" title={cur ? optLabel(cur) : ''}>
          {cur ? optLabel(cur) : '—'}
        </span>
      )}
      <Arrow to={lower} side="right" />
    </div>
  )
}

function fmtHeader(fx) {
  if (!fx) return { title: 'Selection', sub: '', kicker: 'Team sheet' }
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
  return { title, sub: bits.join(' · '), kicker: `Team sheet${fx.round ? ` · Round ${fx.round}` : ''}` }
}

const VIEWS = [
  { id: 'rail', name: 'Dual rail', icon: 'cols' },
  { id: 'sheet', name: 'Team sheet', icon: 'sheet' },
]

function ViewToggle({ value, onChange }) {
  return (
    <div className="inline-flex p-[3px] gap-0.5 bg-pb-surface2 rounded-lg border border-pb-hairline" role="tablist" aria-label="Selection view">
      {VIEWS.map((v) => {
        const on = v.id === value
        return (
          <button key={v.id} type="button" role="tab" aria-selected={on} title={`${v.name} view`} onClick={() => onChange(v.id)}
            className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 font-display font-semibold text-[13px] whitespace-nowrap transition ${on ? 'bg-pb-surface text-pb-accent shadow-sm' : 'text-pb-faint hover:text-pb-text'}`}>
            <Icon name={v.icon} size={15} /><span className="hidden md:inline">{v.name}</span>
          </button>
        )
      })}
    </div>
  )
}

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const { theme, toggle: toggleTheme } = useTheme()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [slots, setSlots] = useState([])
  const [capId, setCapId] = useState(null)
  const [wkId, setWkId] = useState(null)
  const [focus, setFocus] = useState(null)
  const [format, setFormat] = useState(11)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [yearsF, setYearsF] = useState(3)
  const [sort, setSort] = useState('squad')
  const [availEdit, setAvailEdit] = useState(null)
  const [showSheet, setShowSheet] = useState(false)
  const [copied, setCopied] = useState(false)
  const [allFixtures, setAllFixtures] = useState([])
  const [prevXI, setPrevXI] = useState(null)
  // Pending cascades: displacedPlayerId → { fixture_id, batting_order, callupId }.
  // When a call-up bumps a regular out of this XI, that regular drops into the
  // team below (the called-up player's vacated slot) on save.
  const [demotions, setDemotions] = useState({})
  const [view, setView] = useState(() => {
    const v = localStorage.getItem('bs-view'); return v === 'sheet' || v === 'rail' ? v : 'rail'
  })
  useEffect(() => { localStorage.setItem('bs-view', view) }, [view])

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
        setDemotions({})
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

  // Default (Squad order) comparator: tier → form score → availability → name.
  const cmp = useCallback((a, b) => {
    const at = a.tier ?? 99, bt = b.tier ?? 99
    if (at !== bt) return at - bt
    const sa = a.score ?? 0, sb = b.score ?? 0
    if (sa !== sb) return sb - sa
    const r = availRank(a.availability) - availRank(b.availability)
    if (r !== 0) return r
    return (a.display_name || '').localeCompare(b.display_name || '')
  }, [])

  // Squad facet options (short label + pool count for the searchable picker).
  const squadPrefix = useMemo(() => {
    const names = new Set()
    ;(data?.pool || []).forEach((p) => (p.squads || []).forEach((s) => names.add(s)))
    return commonPrefixWord([...names])
  }, [data])
  const squadShort = useCallback((name) => stripPrefix(squadPrefix, name) || name, [squadPrefix])
  const squadOptions = useMemo(() => {
    const counts = {}
    ;(data?.pool || []).forEach((p) => (p.squads || []).forEach((s) => { counts[s] = (counts[s] || 0) + 1 }))
    return Object.keys(counts)
      .map((n) => ({ value: n, label: squadShort(n), count: counts[n] }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [data, squadShort])

  // Shorten team names for the switcher + heading ("Applecross 3rd XI" → "3rd
  // XI") by stripping the shared club prefix across all our teams' fixtures.
  const teamPrefix = useMemo(
    () => commonPrefixWord(allFixtures.map((f) => f.team_name || f.grade_name).filter(Boolean)),
    [allFixtures]
  )
  const shortTeam = useCallback((f) => {
    const n = f?.team_name || f?.grade_name
    return n ? (stripPrefix(teamPrefix, n) || n) : null
  }, [teamPrefix])

  const facets = useMemo(() => [
    { key: 'squad', type: 'multi' }, { key: 'avail', type: 'multi' }, { key: 'role', type: 'multi' },
    { key: 'bowling', type: 'multi' }, { key: 'hand', type: 'multi' }, { key: 'form', type: 'multi' },
    { key: 'status', type: 'single' }, { key: 'hideUnavail', type: 'bool' },
  ], [])
  const filters = useFilters(facets)
  const { values, search } = filters

  const available = useMemo(() => (data?.pool || []).filter((p) => !usedIds.has(p.id)), [data, usedIds])
  const pool = useMemo(() => {
    let list = available
    if (search.trim()) list = list.filter((p) => (p.display_name || '').toLowerCase().includes(search.trim().toLowerCase()))
    if (values.role?.length) list = list.filter((p) => (p.skill_positions || []).some((r) => values.role.includes(r)))
    if (values.avail?.length) list = list.filter((p) => values.avail.includes(p.availability || 'NO_RESPONSE'))
    if (values.bowling?.length) list = list.filter((p) => values.bowling.includes(classifyBowl(p)))
    if (values.hand?.length) list = list.filter((p) => values.hand.includes(p.batting_hand))
    if (values.form?.length) list = list.filter((p) => { const b = formBucket(p); return b && values.form.includes(b) })
    if (values.squad?.length) list = list.filter((p) => values.squad.some((s) => (p.squads || []).includes(s)))
    if (values.hideUnavail) list = list.filter((p) => p.availability !== 'UNAVAILABLE')
    if (yearsF) list = list.filter((p) => playedWithinYears(p.last_played, yearsF))
    if (values.status === 'unselected') list = list.filter((p) => !(p.clash?.length > 0))
    else if (values.status === 'clash') list = list.filter((p) => p.clash?.length > 0)
    const sorters = {
      squad: cmp,
      form: (a, b) => (b.score ?? 0) - (a.score ?? 0) || (a.display_name || '').localeCompare(b.display_name || ''),
      name: (a, b) => (a.display_name || '').localeCompare(b.display_name || ''),
    }
    return list.slice().sort(sorters[sort] || cmp)
  }, [available, search, values, yearsF, sort, cmp])

  const filled = slots.filter(Boolean)
  const count = filled.length
  const target = format || 0
  const offCount = target > 0 && count !== target

  // ── Slot mutations (plain fns — DnD always calls the latest onDrop) ────────
  const markDirty = () => setDirty(true)

  const placeInSlot = (slotIdx, playerId) => {
    setSlots((prev) => { const n = [...prev]; const ex = n.indexOf(playerId); if (ex !== -1) n[ex] = null; n[slotIdx] = playerId; return n })
    markDirty()
    setFocus(slots.findIndex((x, i) => i > slotIdx && x == null))
  }
  const swapSlots = (from, to) => {
    if (from === to) return
    setSlots((prev) => { const n = [...prev]; const m = n[from]; n[from] = n[to]; n[to] = m; return n })
    markDirty()
  }
  const tapPlayer = (p) => {
    if (!canEdit) return
    // A clash blocks the pick unless this is a higher grade calling the player
    // up from a lower one (clash_blocks=false) — then the pick is allowed and
    // they're dropped from the lower XI when we save.
    if (p.clash_blocks) { toast.error(`${p.display_name} is already picked for ${p.clash.join(', ')} that day`); return }
    if (p.clash?.length > 0) toast.info(`Calling ${p.display_name} up from ${p.clash.join(', ')} — they'll be dropped there when you save`)
    else if (p.availability === 'UNAVAILABLE') toast.info(`${p.display_name} is marked unavailable — adding anyway`)
    setSlots((prev) => {
      const next = [...prev]
      const existing = next.indexOf(p.id)
      if (existing !== -1) next[existing] = null
      const t = focus != null && next[focus] == null ? focus : next.indexOf(null)
      if (t === -1) {
        if (format === 0) { next.push(p.id); return next }
        toast.error('All slots are full — increase the side size to add more.')
        return prev
      }
      next[t] = p.id
      return next
    })
    markDirty()
    setFocus(slots.findIndex((x) => x == null))
  }
  const removeAt = (i) => {
    setSlots((prev) => { const n = [...prev]; const id = n[i]; n[i] = null; if (id === capId) setCapId(null); if (id === wkId) setWkId(null); return n })
    markDirty()
    setFocus(i)
  }
  const toggleCap = (id) => { setCapId((c) => (c === id ? null : id)); markDirty() }
  const toggleWk = (id) => { setWkId((c) => (c === id ? null : id)); markDirty() }
  const clearXI = () => {
    if (!canEdit) return
    setSlots((prev) => prev.map(() => null)); setCapId(null); setWkId(null); setFocus(0); markDirty()
  }

  // The lower-grade XI a call-up would come from (its fixture + the player's
  // slot there), so a bumped regular can take that slot. clash_blocks=false means
  // every clashing XI is strictly lower grade, so any clash_detail entry is a
  // valid call-up source; prefer the closest grade below this one.
  const callUpSource = useCallback((p) => {
    if (!p || p.clash_blocks || !(p.clash?.length > 0)) return null
    const cands = (p.clash_detail || []).filter((d) => d && d.fixture_id)
    if (!cands.length) return null
    return cands.slice().sort((a, b) => (a.seq ?? 999) - (b.seq ?? 999))[0]
  }, [])

  // Drop semantics shared by both views.
  const onDrop = (tgt, item) => {
    if (!canEdit) return
    if (tgt.kind === 'slot') {
      if (item.kind === 'pool') {
        const p = item.player
        if (p.clash_blocks) return
        const displacedId = slots[tgt.idx]   // who held the slot before this drop
        if (p.clash?.length > 0) toast.info(`Calling ${p.display_name} up from ${p.clash.join(', ')} — they'll be dropped there when you save`)
        else if (p.availability === 'UNAVAILABLE') toast.info(`${p.display_name} is marked unavailable — adding anyway`)
        placeInSlot(tgt.idx, p.id)
        // Cascade: a call-up that bumps a regular sends that regular down to the
        // team below, into the called-up player's vacated slot.
        const src = callUpSource(p)
        if (src && displacedId && displacedId !== p.id) {
          setDemotions((m) => ({ ...m, [displacedId]: { fixture_id: src.fixture_id, batting_order: src.batting_order, callupId: p.id } }))
          const dn = poolById[displacedId]?.display_name || 'Player'
          toast.info(`${dn} drops to ${src.team_name || 'the team below'} in ${p.display_name}'s place — saved together`)
        }
      } else if (item.kind === 'slot') swapSlots(item.idx, tgt.idx)
    } else if (tgt.kind === 'pool' && item.kind === 'slot') {
      removeAt(item.idx)
    }
  }

  // Auto-fill empty slots (own squad → grade below → grade above), optionally
  // seeding from last week's XI first. Unchanged tier discipline.
  const fillEmpty = (useLastWeek) => {
    if (!canEdit) return
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
    if (useLastWeek && prevXI) {
      if (!capId && prevXI.captain_id && poolById[prevXI.captain_id]) setCapId(prevXI.captain_id)
      if (!wkId && prevXI.wicket_keeper_id && poolById[prevXI.wicket_keeper_id]) setWkId(prevXI.wicket_keeper_id)
    }
    markDirty()
  }

  const changeFormat = async (size) => {
    setFormat(size)
    setSlots((prev) => {
      if (size === 0) return prev.filter(Boolean)
      const next = prev.slice(0, size)
      while (next.length < size) next.push(null)
      const kept = new Set(next.filter(Boolean))
      if (capId && !kept.has(capId)) setCapId(null)
      if (wkId && !kept.has(wkId)) setWkId(null)
      return next
    })
    if (canEdit) { try { await api.bsSetDefaultTeamSize(size) } catch (e) { toast.error('Could not save side size: ' + e.message) } }
  }

  const pickAvail = async (status) => {
    const p = availEdit
    setAvailEdit(null)
    if (!p || !fx?.played_on) { if (!fx?.played_on) toast.error('No fixture date to set availability against'); return }
    setData((d) => ({ ...d, pool: d.pool.map((x) => (x.id === p.id ? { ...x, availability: status } : x)) }))
    try { await api.bsSetAvailability({ player_id: p.id, date: fx.played_on, status }) }
    catch (e) { toast.error('Could not update availability: ' + e.message); load() }
  }

  const save = async () => {
    if (offCount) {
      const diff = count > target ? `${count - target} too many` : `${target - count} too few`
      if (!window.confirm(`You have ${count} player${count === 1 ? '' : 's'} for a ${target}-a-side match — ${diff}.\n\nSave anyway?`)) return
    }
    setSaving(true)
    try {
      const players = filled.map((id, i) => ({ player_id: id, batting_order: i + 1, is_captain: id === capId, is_wicket_keeper: id === wkId }))
      // Only cascade a demotion when the displaced player really left this XI AND
      // the call-up that bumped them is still named (so the lower slot is freed).
      const demoList = Object.entries(demotions)
        .filter(([displacedId, d]) => !filled.includes(displacedId) && filled.includes(d.callupId))
        .map(([displacedId, d]) => ({ player_id: displacedId, fixture_id: d.fixture_id, batting_order: d.batting_order }))
      const r = await api.bsSetSelection(fixtureId, players, demoList)
      toast.success(`Saved ${r.count} player${r.count === 1 ? '' : 's'}`)
      setDirty(false)
      load()
    } catch (e) {
      toast.error(e.message.includes('Already selected') ? e.message : 'Save failed: ' + e.message)
    } finally { setSaving(false) }
  }

  const { title, sub, kicker } = fmtHeader(fx)
  const lineupText = () => {
    const lines = filled.map((id, i) => {
      const p = poolById[id]
      const tags = [id === capId && '(C)', id === wkId && '(WK)'].filter(Boolean).join(' ')
      return `${i + 1}. ${p?.display_name || '—'}${tags ? ' ' + tags : ''}`
    })
    return `${title}${sub ? '\n' + sub : ''}\n\n${lines.join('\n')}`
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
          teamName: (fx?.home_away === 'AWAY' ? fx?.away_team : fx?.home_team) || '',
        },
      },
    })
  }

  const balance = useMemo(() => {
    const has = (id, code) => (poolById[id]?.skill_positions || []).includes(code)
    const b = { BAT: 0, ALL: 0, BWL: 0, WKT: 0 }
    filled.forEach((id) => { ['BAT', 'ALL', 'BWL', 'WKT'].forEach((c) => { if (has(id, c)) b[c] += 1 }) })
    const bowlers = filled.filter((id) => has(id, 'BWL') || has(id, 'ALL')).length
    return { ...b, lightBowling: count >= 8 && bowlers < 5, hasKeeper: filled.some((id) => has(id, 'WKT')) }
  }, [filled, poolById, count])

  if (data === null) return <BetterSelectLayout title="Selection"><PbSpinner message="Loading selection…" /></BetterSelectLayout>

  const canAutofill = format > 0 && slots.some((x) => x == null)
  const hasPrev = (prevXI?.player_ids?.length || 0) > 0

  const teamName = shortTeam(fx)
  const contextLeft = (
    <div className="flex items-center gap-2.5 min-w-0">
      <Link to="/admin/betterselect/selection" className="text-[11px] text-pb-faint hover:text-pb-text whitespace-nowrap">← All teams</Link>
      {fx && <TeamSwitcher fixtureId={fixtureId} fx={fx} fixtures={allFixtures} navigate={navigate} shortTeam={shortTeam} />}
    </div>
  )

  const filterBar = (
    <SelectionFilters filters={filters} sort={sort} setSort={setSort} squadOptions={squadOptions}
      yearsF={yearsF} setYearsF={setYearsF} count={pool.length} total={available.length} />
  )

  const vm = {
    title, sub, kicker, teamName, contextLeft, filterBar, squadShort, canEdit,
    poolById, pool, slots, capId, wkId, focus, format, count, target, balance,
    filledSet: usedIds, canAutofill, hasPrev,
    changeFormat, tapPlayer, placeInSlot, removeAt, swapSlots, setFocus, toggleCap, toggleWk,
    autofill: () => fillEmpty(false), fillLastWeek: () => fillEmpty(true), clearXI, setAvailEdit,
  }

  const headerLeft = <ViewToggle value={view} onChange={setView} />
  const actions = (
    <div className="flex items-center gap-2.5">
      <button onClick={toggleTheme} title="Toggle theme"
        className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-lg bg-pb-surface2 border border-pb-hairline text-pb-dim hover:text-pb-text">
        <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
      </button>
      <Btn variant="soft" sm icon="share" onClick={() => setShowSheet(true)} disabled={count === 0}><span className="hidden sm:inline">Share</span></Btn>
      {canEdit && <Btn variant="primary" sm icon="check" onClick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : dirty ? `Save${count ? ` (${count})` : ''}` : 'Saved'}</Btn>}
    </div>
  )

  return (
    <BetterSelectLayout title="Selection" headerLeft={headerLeft} actions={actions}>
      <DnD onDrop={onDrop}>
        {view === 'sheet' ? <TeamSheetView vm={vm} /> : <DualRailView vm={vm} />}
      </DnD>

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
