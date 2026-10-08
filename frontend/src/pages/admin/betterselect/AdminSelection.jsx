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
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { useTheme } from '../../../contexts/ThemeContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { availRank } from '../../../lib/availability'
import { Icon, Avatar, Btn, RoleChips, Tag, Empty, QuickAvailModal, playedWithinYears, RuleTags } from './ui'
import { useFilters } from './filters'
import SelectionFilters from './SelectionFilters'
import { DnD } from './selectionDnd'
import { DualRailView, TeamSheetView } from './SelectionViews'
import { AddPlayersSheet, SlotSheet, MobileBar } from './SelectionMobile'
import { useMediaQuery } from '../../../hooks/useMediaQuery'
import { classifyBowl, formBucket, matchesAge, inAnotherXI, alsoIn, alsoInLine, nameMatches } from './selectionMeta'
import { matchesRuleFilter, xiCompliance, hasBlockingRule } from './selectionRules'

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

// What Confirm would write: the named XI in batting order, captain, keeper and
// the call-up cascades. Gaps between slots are not part of it.
const confirmSig = (filled, capId, wkId, demoList) =>
  JSON.stringify([filled.map((id) => [id, id === capId, id === wkId]), demoList])

const DRAFT_DELAY_MS = 600
const DRAFT_RETRY_MS = 5000
const DRAFT_POLL_MS = 8000

// A saved draft laid back onto the board. Anyone no longer in the pool is
// dropped; the server re-judges everything at Confirm.
function restoreDraft(dd, pool, size) {
  const inPool = new Set((pool || []).map((p) => p.id))
  let slots = (dd.slots || []).map((id) => (id && inPool.has(id) ? id : null))
  if (size === 0) slots = slots.filter(Boolean)
  else {
    while (slots.length > size && slots[slots.length - 1] == null) slots.pop()
    while (slots.length < size) slots.push(null)
  }
  const kept = new Set(slots.filter(Boolean))
  const demo = {}
  ;(dd.demotions || []).forEach((x) => {
    if (x.callup_id && kept.has(x.callup_id)) demo[x.player_id] = { fixture_id: x.fixture_id, batting_order: x.batting_order, callupId: x.callup_id }
  })
  return {
    slots,
    cap: kept.has(dd.captain_id) ? dd.captain_id : null,
    wk: kept.has(dd.wicket_keeper_id) ? dd.wicket_keeper_id : null,
    demo,
  }
}

export default function AdminSelection() {
  const fmt = useAdminNameFormat()
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  // ToastProvider hands out a NEW `toast` object on every render, and showing a
  // toast re-renders it. `load` must not depend on that object, or every toast
  // below (a call-up, a back to back pick, "marked unavailable") re-ran load(),
  // reloaded the fixture and wiped the unsaved XI, losing the pick it announced.
  const toastRef = useRef(toast)
  toastRef.current = toast
  const { theme, toggle: toggleTheme } = useTheme()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const canEditRef = useRef(canEdit)
  canEditRef.current = canEdit

  const [data, setData] = useState(null)
  const [slots, setSlots] = useState([])
  const [capId, setCapId] = useState(null)
  const [wkId, setWkId] = useState(null)
  const [focus, setFocus] = useState(null)
  const [format, setFormat] = useState(11)
  const [saving, setSaving] = useState(false)
  // The confirmed XI as loaded; "unconfirmed changes" is the board differing
  // from it. Derived, so putting someone back where they were reads as clean.
  const [baseSig, setBaseSig] = useState(null)
  // Autosave of the unconfirmed side (a draft row, apart from the confirmed XI).
  const [draftStatus, setDraftStatus] = useState('idle')   // idle | saving | saved | error
  const [draftInfo, setDraftInfo] = useState(null)         // { at, by } when a draft was restored or saved
  const loadedFor = useRef(null)          // fixture the board's state belongs to
  const draftOnServer = useRef(false)     // a draft row exists for loadedFor
  const draftServerSig = useRef('')       // board state the server's draft matches
  const draftPending = useRef(null)       // { fixtureId, body|null, sig } waiting for the debounce
  const draftTimer = useRef(null)
  const draftInflight = useRef(null)      // the write in flight: confirm and reload wait for it
  const draftBusy = useRef(0)             // writes in flight (the poll leaves them alone)
  const draftVersion = useRef(0)          // server draft version this board last saw (0 = none)
  // Another selector changed, confirmed or discarded the draft while this board
  // held unsent changes: { theirs: { draft, version, by, at } | null }. Autosave
  // stops until it is settled.
  const [draftConflict, setDraftConflict] = useState(null)
  const pollDraft = useRef(() => {})
  const [yearsF, setYearsF] = useState(3)
  const [sort, setSort] = useState('squad')
  const [availEdit, setAvailEdit] = useState(null)
  // Phone only. `panel` is which of Pool / XI the bottom bar has up; the two
  // sheets are the "add players" search and one batting-order row's actions.
  const isPhone = useMediaQuery('(max-width: 1023px)')
  const [panel, setPanel] = useState('xi')
  const [addOpen, setAddOpen] = useState(false)
  const [slotOpen, setSlotOpen] = useState(null)
  const [showSheet, setShowSheet] = useState(false)
  const [copied, setCopied] = useState(false)
  const [allFixtures, setAllFixtures] = useState([])
  const [prevXI, setPrevXI] = useState(null)
  // Which fixture we've already offered the eligible-only pool for. A ref, not
  // state: it must not re-trigger a render, and it has to survive the reload
  // that follows a save.
  const autoFiltered = useRef(null)
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
    loadedFor.current = null
    // A draft write still in flight (just switched fixture, or just confirmed)
    // must land before we read, or we read the draft it is about to replace.
    Promise.resolve(draftInflight.current).catch(() => {})
      .then(() => Promise.all([
        api.bsGetSelection(fixtureId),
        canEditRef.current ? api.bsGetSelectionDraft(fixtureId).catch(() => ({ draft: null })) : { draft: null },
      ]))
      .then(([d, dr]) => {
        const size = d.default_team_size ?? 11
        const lineup = (d.lineup || []).slice().sort((a, b) => (a.batting_order || 999) - (b.batting_order || 999))
        const count = size > 0 ? Math.max(size, lineup.length) : lineup.length
        const init = Array(count).fill(null)
        lineup.forEach((l, i) => { if (i < count) init[i] = l.player_id })
        let cap = lineup.find((l) => l.is_captain)?.player_id ?? null
        let wk = lineup.find((l) => l.is_wicket_keeper)?.player_id ?? null
        setBaseSig(confirmSig(init.filter(Boolean), cap, wk, []))

        // An autosaved draft replaces the confirmed XI on the board.
        let slotsInit = init
        let demo = {}
        const dd = dr?.draft
        draftOnServer.current = false
        draftVersion.current = 0
        setDraftInfo(null)
        setDraftConflict(null)
        if (dd && Array.isArray(dd.slots)) {
          const r = restoreDraft(dd, d.pool, size)
          slotsInit = r.slots
          cap = r.cap
          wk = r.wk
          demo = r.demo
          draftOnServer.current = true
          draftVersion.current = dr.version || 0
          setDraftInfo({ at: dr.updated_at, by: dr.updated_by })
        }
        draftServerSig.current = JSON.stringify([slotsInit, cap, wk, demo])
        setData(d)
        setSlots(slotsInit)
        setCapId(cap)
        setWkId(wk)
        setFormat(size)
        setFocus(slotsInit.findIndex((x) => x == null))
        setDemotions(demo)
        setDraftStatus('idle')
        loadedFor.current = fixtureId
      })
      .catch((e) => { toastRef.current.error(e.message); setData({ pool: [], lineup: [], fixture: null }) })
  }, [fixtureId])

  // Send the pending draft change now. `leaving` marks a page that is going
  // away, so the request is allowed to outlive it. Writes are chained so a
  // delete can never overtake the save before it.
  const flushDraft = useCallback((leaving) => {
    clearTimeout(draftTimer.current)
    draftTimer.current = null
    const p = draftPending.current
    if (!p) return draftInflight.current
    draftPending.current = null
    const opts = leaving ? { keepalive: true } : {}
    draftBusy.current += 1
    const task = Promise.resolve(draftInflight.current).catch(() => {})
      // The version is read when the write is sent, so a save queued behind
      // another of ours carries the version that one produced.
      .then(() => (p.body
        ? api.bsSaveSelectionDraft(p.fixtureId, { ...p.body, base_version: draftVersion.current }, opts)
        : api.bsDiscardSelectionDraft(p.fixtureId, draftVersion.current, opts)))
      .then((r) => {
        draftBusy.current -= 1
        if (loadedFor.current !== p.fixtureId) return
        draftVersion.current = p.body ? (r?.version || 0) : 0
        draftServerSig.current = p.sig
        draftOnServer.current = !!p.body
        setDraftStatus(draftPending.current ? 'saving' : 'saved')
        setDraftInfo(p.body ? { at: new Date().toISOString(), by: null } : null)
      })
      .catch((e) => {
        draftBusy.current -= 1
        if (loadedFor.current !== p.fixtureId) return
        if (e.status === 409 && e.detail?.code === 'draft_conflict') {
          // Someone else got there first. Nothing was overwritten; ask which wins.
          const t = e.detail
          setDraftStatus('idle')
          setDraftConflict({ theirs: t.draft ? { draft: t.draft, version: t.version, by: t.updated_by, at: t.updated_at } : null })
          return
        }
        setDraftStatus('error')
        // A dropped connection or a 5xx is worth another go; a refusal is not.
        if ((!e.status || e.status >= 500) && !draftPending.current) {
          draftPending.current = p
          draftTimer.current = setTimeout(() => flushDraft(false), DRAFT_RETRY_MS)
        }
      })
    draftInflight.current = task
    return task
  }, [])

  // Leaving the board (another fixture, another screen, closing the tab) must
  // not lose the last change still waiting on the debounce.
  useEffect(() => {
    const onHide = () => { if (document.visibilityState === 'hidden') flushDraft(true) }
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('pagehide', onHide)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('pagehide', onHide)
      flushDraft(true)
    }
  }, [fixtureId, flushDraft])

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
    // Fees + training. Single-choice rather than checkboxes because "shown
    // both ways" is just no filter, and each has a third real answer —
    // unknown — for a club whose modules can't say.
    { key: 'fees', type: 'single' }, { key: 'training', type: 'single' },
    // Age. Single-choice for the same reason: "under 16 and everyone else"
    // is no filter at all, and the pool's age is already the club's own
    // answer (see services/player_age.py) — this only reads it.
    { key: 'age', type: 'single' },
    // The club's association rules — clear / has a problem / ineligible.
    { key: 'rules', type: 'single' },
  ], [])
  const filters = useFilters(facets)
  const { values, search } = filters

  // A rule the club made BLOCKING means the pool should be suggesting players
  // who can actually be picked, so eligible-only is applied for you the first
  // time each fixture is opened. From then on it is an ordinary filter pill:
  // clear it to see everyone, and it stays cleared until you move to another
  // fixture. Warnings are deliberately still shown — a warning is the
  // selector's to weigh, not ours to hide.
  useEffect(() => {
    if (!data || autoFiltered.current === fixtureId) return
    autoFiltered.current = fixtureId
    if (!hasBlockingRule(data.rules) || values.rules) return
    filters.setValue('rules', 'eligible')
  }, [data, fixtureId])  // eslint-disable-line react-hooks/exhaustive-deps

  // Players marked inactive are not pickable, so they stay out of the pool (the
  // Squads board does the same). One already in the saved XI still shows in
  // their slot. The count is passed down so the pool can say who is missing.
  const available = useMemo(() => (data?.pool || []).filter((p) => !usedIds.has(p.id) && !p.is_inactive), [data, usedIds])
  const inactiveHidden = useMemo(() => (data?.pool || []).filter((p) => p.is_inactive && !usedIds.has(p.id)).length, [data, usedIds])
  const pool = useMemo(() => {
    let list = available
    if (search.trim()) list = list.filter((p) => nameMatches(p.display_name, search))
    if (values.role?.length) list = list.filter((p) => (p.skill_positions || []).some((r) => values.role.includes(r)))
    if (values.avail?.length) list = list.filter((p) => values.avail.includes(p.availability || 'NO_RESPONSE'))
    if (values.bowling?.length) list = list.filter((p) => values.bowling.includes(classifyBowl(p)))
    if (values.hand?.length) list = list.filter((p) => values.hand.includes(p.batting_hand))
    if (values.form?.length) list = list.filter((p) => { const b = formBucket(p); return b && values.form.includes(b) })
    if (values.squad?.length) list = list.filter((p) => values.squad.some((s) => (p.squads || []).includes(s)))
    if (values.hideUnavail) list = list.filter((p) => p.availability !== 'UNAVAILABLE')
    // is_financial / trained_recently are tri-state: true, false, or null when
    // neither BetterFees nor Net Manager could answer and nobody has said by
    // hand. "Unknown" is a filter in its own right — it's the list of people
    // the club still has to chase.
    if (values.fees === 'owing') list = list.filter((p) => p.is_financial === false)
    else if (values.fees === 'financial') list = list.filter((p) => p.is_financial === true)
    else if (values.fees === 'unknown') list = list.filter((p) => p.is_financial == null)
    if (values.training === 'trained') list = list.filter((p) => p.trained_recently === true)
    else if (values.training === 'missing') list = list.filter((p) => p.trained_recently === false)
    else if (values.training === 'unknown') list = list.filter((p) => p.trained_recently == null)
    if (values.age) list = list.filter((p) => matchesAge(p, values.age))
    // The club's own association rules. Only offered when the club has one
    // bearing on this fixture — SelectionFilters drops the group otherwise.
    if (values.rules) list = list.filter((p) => matchesRuleFilter(p, values.rules))
    // A name typed into search is someone the selector is looking for, so the
    // "Played ≤ N yrs" window does not hide them. It only trims the browse list.
    // (Players marked inactive stay out either way: see `available`.)
    if (yearsF && !search.trim()) list = list.filter((p) => playedWithinYears(p.last_played, yearsF))
    if (values.status === 'unselected') list = list.filter((p) => !inAnotherXI(p))
    else if (values.status === 'clash') list = list.filter((p) => inAnotherXI(p))
    const sorters = {
      squad: cmp,
      form: (a, b) => (b.score ?? 0) - (a.score ?? 0) || (a.display_name || '').localeCompare(b.display_name || ''),
      name: (a, b) => (a.display_name || '').localeCompare(b.display_name || ''),
    }
    return list.slice().sort(sorters[sort] || cmp)
  }, [available, search, values, yearsF, sort, cmp])

  const filled = slots.filter(Boolean)
  const count = filled.length
  // Only a cascade whose displaced player really left this XI AND whose call-up
  // is still named: the one definition Confirm sends and "unconfirmed" compares.
  const demoList = useMemo(
    () => Object.entries(demotions)
      .filter(([displacedId, d]) => !filled.includes(displacedId) && filled.includes(d.callupId))
      .map(([displacedId, d]) => ({ player_id: displacedId, fixture_id: d.fixture_id, batting_order: d.batting_order })),
    [demotions, slots],  // eslint-disable-line react-hooks/exhaustive-deps
  )
  const dirty = baseSig !== null && confirmSig(filled, capId, wkId, demoList) !== baseSig
  const draftSig = JSON.stringify([slots, capId, wkId, demotions])

  // Autosave. Every change to the side is written to the draft after a short
  // pause; getting back to the confirmed XI removes the draft. Nothing here
  // touches the confirmed lineup, which is what the rest of the app reads.
  useEffect(() => {
    if (!canEdit || data === null || loadedFor.current !== fixtureId || draftConflict) return
    if (dirty ? draftSig === draftServerSig.current : !draftOnServer.current) return
    draftPending.current = {
      fixtureId,
      sig: draftSig,
      body: dirty ? {
        slots, captain_id: capId, wicket_keeper_id: wkId,
        demotions: Object.entries(demotions).map(([pid, d]) => ({
          player_id: pid, fixture_id: d.fixture_id, batting_order: d.batting_order, callup_id: d.callupId,
        })),
      } : null,
    }
    setDraftStatus('saving')
    clearTimeout(draftTimer.current)
    draftTimer.current = setTimeout(() => flushDraft(false), DRAFT_DELAY_MS)
  }, [draftSig, dirty, data, fixtureId, canEdit, draftConflict])  // eslint-disable-line react-hooks/exhaustive-deps

  // Take another selector's draft onto the board.
  const adoptDraft = (t) => {
    const r = restoreDraft(t.draft, data?.pool, format)
    setSlots(r.slots)
    setCapId(r.cap)
    setWkId(r.wk)
    setDemotions(r.demo)
    setFocus(r.slots.findIndex((x) => x == null))
    draftServerSig.current = JSON.stringify([r.slots, r.cap, r.wk, r.demo])
    draftOnServer.current = true
    draftVersion.current = t.version || 0
    setDraftInfo({ at: t.at, by: t.by })
    setDraftConflict(null)
  }

  // Look for another selector's changes while the board is open. Left alone
  // while a write of ours is waiting or in flight, and while a conflict is
  // already on screen. A board with nothing unsent just takes the new draft; one
  // with unsent changes of its own is asked about it (the Draft strip).
  pollDraft.current = async () => {
    if (!canEdit || data === null || loadedFor.current !== fixtureId || draftConflict || saving) return
    if (draftPending.current || draftBusy.current) return
    let r
    try { r = await api.bsGetSelectionDraft(fixtureId) } catch { return }
    if (loadedFor.current !== fixtureId || draftPending.current || draftBusy.current) return
    if ((r.version || 0) === draftVersion.current) return
    const theirs = r.draft ? { draft: r.draft, version: r.version, by: r.updated_by, at: r.updated_at } : null
    if (draftSig === draftServerSig.current) {
      if (theirs) { adoptDraft(theirs); toastRef.current.info(`${theirs.by || 'Someone'} changed the draft. Showing their version.`) }
      else { load(); toastRef.current.info('The draft was confirmed or discarded by someone else.') }
    } else setDraftConflict({ theirs })
  }
  useEffect(() => {
    if (!canEdit) return undefined
    const tick = () => { if (document.visibilityState === 'visible') pollDraft.current() }
    const t = setInterval(tick, DRAFT_POLL_MS)
    document.addEventListener('visibilitychange', tick)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', tick) }
  }, [canEdit, fixtureId])

  // The conflict choices. "Mine" keeps this board and saves it over theirs;
  // "theirs" replaces this board with the draft that is on the server.
  const keepMine = () => {
    draftVersion.current = draftConflict?.theirs?.version || 0
    draftOnServer.current = !!draftConflict?.theirs
    setDraftConflict(null)   // the autosave effect re-runs and sends this board
  }
  const useTheirs = () => {
    const t = draftConflict?.theirs
    if (t) adoptDraft(t)
    else { setDraftConflict(null); load() }
  }
  const target = format || 0
  const offCount = target > 0 && count !== target

  // ── Slot mutations (plain fns — DnD always calls the latest onDrop) ────────
  const placeInSlot = (slotIdx, playerId) => {
    setSlots((prev) => { const n = [...prev]; const ex = n.indexOf(playerId); if (ex !== -1) n[ex] = null; n[slotIdx] = playerId; return n })
    setFocus(slots.findIndex((x, i) => i > slotIdx && x == null))
  }
  const swapSlots = (from, to) => {
    if (from === to) return
    setSlots((prev) => { const n = [...prev]; const m = n[from]; n[from] = n[to]; n[to] = m; return n })
  }
  const tapPlayer = (p) => {
    if (!canEdit) return
    // A clash blocks the pick unless this is a higher grade calling the player
    // up from a lower one (clash_blocks=false) — then the pick is allowed and
    // they're dropped from the lower XI when we save.
    if (p.clash_blocks) { toast.error(`${fmt(p.display_name)} is already picked for ${p.clash.join(', ')} that day`); return }
    if (p.clash?.length > 0) toast.info(`Calling ${fmt(p.display_name)} up from ${p.clash.join(', ')} — they'll be dropped there when you save`)
    else if (alsoIn(p).length > 0) toast.info(`${fmt(p.display_name)} is also in ${alsoInLine(p)} that day. Adding to both.`)
    else if (p.availability === 'UNAVAILABLE') toast.info(`${fmt(p.display_name)} is marked unavailable — adding anyway`)
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
    setFocus(slots.findIndex((x) => x == null))
  }
  const removeAt = (i) => {
    setSlots((prev) => { const n = [...prev]; const id = n[i]; n[i] = null; if (id === capId) setCapId(null); if (id === wkId) setWkId(null); return n })
    setFocus(i)
  }
  const toggleCap = (id) => { setCapId((c) => (c === id ? null : id)) }
  const toggleWk = (id) => { setWkId((c) => (c === id ? null : id)) }
  const clearXI = () => {
    if (!canEdit) return
    setSlots((prev) => prev.map(() => null)); setCapId(null); setWkId(null); setFocus(0)
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
        if (p.clash?.length > 0) toast.info(`Calling ${fmt(p.display_name)} up from ${p.clash.join(', ')} — they'll be dropped there when you save`)
        else if (alsoIn(p).length > 0) toast.info(`${fmt(p.display_name)} is also in ${alsoInLine(p)} that day. Adding to both.`)
        else if (p.availability === 'UNAVAILABLE') toast.info(`${fmt(p.display_name)} is marked unavailable — adding anyway`)
        placeInSlot(tgt.idx, p.id)
        // Cascade: a call-up that bumps a regular sends that regular down to the
        // team below, into the called-up player's vacated slot.
        const src = callUpSource(p)
        if (src && displacedId && displacedId !== p.id) {
          setDemotions((m) => ({ ...m, [displacedId]: { fixture_id: src.fixture_id, batting_order: src.batting_order, callupId: p.id } }))
          const dn = fmt(poolById[displacedId]?.display_name) || 'Player'
          toast.info(`${dn} drops to ${src.team_name || 'the team below'} in ${fmt(p.display_name)}'s place — saved together`)
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
    // Auto-fill never puts anyone in two games; a player in another XI that day
    // (clash or a back to back game) is picked by hand.
    const okToPick = (p) => p && !inAnotherXI(p) && p.availability !== 'UNAVAILABLE'
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
      if (!window.confirm(`You have ${count} player${count === 1 ? '' : 's'} for a ${target}-a-side match — ${diff}.\n\nConfirm anyway?`)) return
    }
    // A warning-level rule is the selector's to weigh, so it asks rather than
    // refuses. A blocking one never gets this far — the server decides, and
    // its answer comes back below.
    const { warnings } = xiCompliance(data?.rules, poolById, filled)
    if (warnings.length) {
      const lines = warnings.slice(0, 6).map((w) => `• ${w.player ? w.player + ' — ' : ''}${w.detail}`).join('\n')
      const more = warnings.length > 6 ? `\n…and ${warnings.length - 6} more` : ''
      if (!window.confirm(`This side breaks ${warnings.length} club rule${warnings.length === 1 ? '' : 's'}:\n\n${lines}${more}\n\nConfirm anyway?`)) return
    }
    setSaving(true)
    try {
      // Drop any draft write still waiting: confirming replaces the draft, and
      // one landing after it would bring the draft back.
      clearTimeout(draftTimer.current)
      draftPending.current = null
      await Promise.resolve(draftInflight.current).catch(() => {})
      const players = filled.map((id, i) => ({ player_id: id, batting_order: i + 1, is_captain: id === capId, is_wicket_keeper: id === wkId }))
      const r = await api.bsSetSelection(fixtureId, players, demoList)
      toast.success(`Confirmed ${r.count} player${r.count === 1 ? '' : 's'}`)
      load()
    } catch (e) {
      // A blocking rule comes back as a structured 409 listing exactly what
      // broke, which is more use than "save failed".
      const breaches = e?.detail?.breaches || e?.data?.detail?.breaches
      if (breaches?.length) toast.error(`Can't save — ${breaches.join('; ')}`)
      else toast.error(e.message.includes('Already selected') ? e.message : 'Save failed: ' + e.message)
    } finally { setSaving(false) }
  }

  // Throw the unconfirmed changes away and go back to the confirmed XI.
  const discardDraft = async () => {
    if (!window.confirm('Discard your unconfirmed changes and go back to the confirmed XI?')) return
    clearTimeout(draftTimer.current)
    draftPending.current = null
    try {
      await Promise.resolve(draftInflight.current).catch(() => {})
      await api.bsDiscardSelectionDraft(fixtureId, draftVersion.current)
      load()
    } catch (e) {
      if (e.status === 409 && e.detail?.code === 'draft_conflict') {
        const t = e.detail
        setDraftConflict({ theirs: t.draft ? { draft: t.draft, version: t.version, by: t.updated_by, at: t.updated_at } : null })
      } else toast.error('Could not discard: ' + e.message)
    }
  }

  const { title, sub, kicker } = fmtHeader(fx)
  // The same verdict the board's rule strip shows, for the shareable sheet.
  const sheetRules = xiCompliance(data?.rules, poolById, filled)
  const lineupText = () => {
    const lines = filled.map((id, i) => {
      const p = poolById[id]
      const tags = [id === capId && '(C)', id === wkId && '(WK)'].filter(Boolean).join(' ')
      return `${i + 1}. ${fmt(p?.display_name) || '—'}${tags ? ' ' + tags : ''}`
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
      yearsF={yearsF} setYearsF={setYearsF} count={pool.length} total={available.length}
      inactiveHidden={inactiveHidden} flags={data?.flags} rules={data?.rules} />
  )

  const vm = {
    title, sub, kicker, teamName, contextLeft, filterBar, squadShort, canEdit,
    poolById, pool, slots, capId, wkId, focus, format, count, target, balance,
    rules: data?.rules,
    filledSet: usedIds, canAutofill, hasPrev,
    available, view, isPhone, panel, setPanel,
    openAdd: (i) => { if (i != null) setFocus(i); setAddOpen(true) },
    openSlot: (i) => setSlotOpen(i),
    changeFormat, tapPlayer, placeInSlot, removeAt, swapSlots, setFocus, toggleCap, toggleWk,
    autofill: () => fillEmpty(false), fillLastWeek: () => fillEmpty(true), clearXI, setAvailEdit,
  }

  const headerLeft = <ViewToggle value={view} onChange={setView} />
  const confirmLabel = saving ? 'Confirming…' : dirty ? `Confirm${count ? ` (${count})` : ''}` : 'Confirmed'
  const actions = (
    <div className="flex items-center gap-2.5">
      {/* The site's own top bar already carries the theme toggle on a phone. */}
      <button onClick={toggleTheme} title="Toggle theme"
        className="max-md:hidden inline-flex items-center justify-center w-[34px] h-[34px] rounded-lg bg-pb-surface2 border border-pb-hairline text-pb-dim hover:text-pb-text">
        <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
      </button>
      <Btn variant="soft" sm icon="share" onClick={() => setShowSheet(true)} disabled={count === 0}><span className="hidden sm:inline">Share</span></Btn>
      {/* Below `lg` Confirm lives in the bar pinned to the bottom of the screen. */}
      {canEdit && <Btn variant="primary" sm icon="check" className="max-lg:hidden" onClick={save} disabled={saving || !dirty}>{confirmLabel}</Btn>}
    </div>
  )

  return (
    <BetterSelectLayout title="Selection" headerLeft={headerLeft} actions={actions}>
      {canEdit && draftConflict && (
        <div role="alert" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2 text-[12px] text-pb-text"
          style={{ borderColor: 'var(--pb-amber)', background: 'color-mix(in srgb, var(--pb-amber) 10%, var(--pb-surface))' }}>
          <span className="min-w-0 flex-1 basis-60">
            <span className="font-semibold">{draftConflict.theirs ? `${draftConflict.theirs.by || 'Someone else'} changed this draft.` : 'This draft was confirmed or discarded by someone else.'}</span>{' '}
            {draftConflict.theirs
              ? 'Your changes are not saved yet. Use their version, or keep yours and save over it.'
              : 'Your changes are not saved yet. Go back to the confirmed XI, or keep yours as a new draft.'}
          </span>
          <span className="flex shrink-0 items-center gap-3">
            <button type="button" onClick={useTheirs} className="font-display font-semibold text-pb-accent hover:underline">
              {draftConflict.theirs ? 'Use their version' : 'Use confirmed XI'}
            </button>
            <button type="button" onClick={keepMine} className="font-display font-semibold text-pb-accent hover:underline">Keep mine</button>
          </span>
        </div>
      )}
      {canEdit && dirty && !draftConflict && (
        <div role="status" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-pb-hairline bg-pb-surface px-3 py-2 text-[12px] text-pb-dim">
          <span className="min-w-0 flex-1 basis-60">
            <span className="font-semibold text-pb-text">Draft.</span>{' '}
            {draftStatus === 'error'
              ? 'Your changes are not saving yet. Keep this page open until this clears.'
              : draftStatus === 'saving'
                ? 'Saving your changes…'
                : 'Your changes are saved as you go, so you can leave and come back.'}
            <span className="max-sm:hidden">
              {' '}The confirmed XI stays as it was until you press Confirm.
              {draftInfo?.by && draftInfo.at && !saving ? ` Last saved by ${draftInfo.by}.` : ''}
            </span>
          </span>
          <button type="button" onClick={discardDraft} disabled={saving}
            className="shrink-0 font-display font-semibold text-pb-accent hover:underline disabled:opacity-50">
            Discard changes
          </button>
        </div>
      )}
      {/* Room for the pinned bar on a phone, so the last row is not under it. */}
      <div className="max-lg:pb-24">
        <DnD onDrop={onDrop}>
          {view === 'sheet' ? <TeamSheetView vm={vm} /> : <DualRailView vm={vm} />}
        </DnD>
      </div>

      <MobileBar vm={vm} confirm={canEdit && (
        <Btn variant="primary" icon="check" className="min-h-[44px] shrink-0" onClick={save} disabled={saving || !dirty}>{confirmLabel}</Btn>
      )} />
      {canEdit && addOpen && <AddPlayersSheet vm={vm} onClose={() => setAddOpen(false)} />}
      {canEdit && slotOpen != null && <SlotSheet vm={vm} idx={slotOpen} onClose={() => setSlotOpen(null)} />}

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
                    <span className="flex-1 text-[13.5px] truncate">
                      {fmt(p?.display_name)}{id === capId && <> <Tag>C</Tag></>}{id === wkId && <> <Tag tone="amber">WK</Tag></>}
                      {' '}<RuleTags player={p} />
                    </span>
                    <RoleChips roles={p?.skill_positions} muted />
                  </div>
                )
              })}
              {count === 0 && <div className="p-4"><Empty>No players selected.</Empty></div>}
              {offCount && <div className="px-4 py-2 text-[12px] text-pb-amber">{count > target ? `${count - target} over` : `${target - count} short of`} your {target}-a-side format.</div>}
              {/* Club rules, on the sheet as well as the board — this is the
                  copy that gets sent to a captain, so it should not be the one
                  place a problem is invisible. */}
              {sheetRules.blocking.concat(sheetRules.warnings).map((w, i) => (
                <div key={i} className="px-4 py-1.5 text-[12px]"
                  style={{ color: sheetRules.blocking.includes(w) ? 'var(--pb-red)' : 'var(--pb-amber)' }}>
                  {w.player ? `${w.player} — ` : ''}{w.detail}
                </div>
              ))}
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
