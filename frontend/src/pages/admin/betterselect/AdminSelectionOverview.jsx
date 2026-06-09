// BetterSelect → Selection INDEX (the screen you land on from the sidebar).
// Rebuilt to the "matchday board" handoff (docs/selection_index_bundle): a
// dense, scannable list of every upcoming team's selection — one compact row
// per fixture, grouped by matchday, with a derived health summary (balance /
// keeper / captain / flags / status), search + status filters, and an inline
// "peek" that expands to the availability breakdown + XI.
//
// Each row links into the builder (/admin/betterselect/select/:id). The health
// summary is derived from the enriched /selection/overview payload (per-player
// skill roles + per-date availability) by summarize() — same rules the balance
// strip uses inside the builder, so the board and the builder agree.
//
// Semantic tints use inline `color-mix` (not Tailwind `/opacity` modifiers):
// the pb-* tokens aren't in channel form, so an alpha modifier emits no CSS.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useToast } from '../../../contexts/ToastContext'
import { useTheme } from '../../../contexts/ThemeContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import { Icon, Avatar, Dot, Tag, RoleChips } from './ui'

const ROLE_CODES = ['BAT', 'ALL', 'BWL', 'WKT']
const tint = (token, pct) => `color-mix(in srgb, ${token} ${pct}%, transparent)`

function shortName(s) {
  if (!s) return '?'
  if (s.includes(',')) return s.split(',')[0].trim()
  const parts = s.trim().split(/\s+/)
  return parts.length > 1 ? parts[parts.length - 1] : s
}

// A compact grade/age badge from the grade (or team) name. Covers the common
// cricket naming patterns; falls back to leading letters.
function gradeBadge(fx) {
  const g = (fx.grade_name || fx.team_name || '').trim()
  if (!g) return '—'
  let m
  if ((m = g.match(/\bunder[\s-]?(\d{1,2})\b/i)) || (m = g.match(/\bu[\s-]?(\d{1,2})\b/i))) return 'U' + m[1]
  if ((m = g.match(/\b(?:over|masters?|o)[\s-]?(\d{2})\b/i))) return 'O' + m[1]
  if (/\bt20\b/i.test(g)) return 'T20'
  if ((m = g.match(/\b(\d+)(st|nd|rd|th)\b/i))) return m[1] + m[2].toLowerCase()
  if (/\b(women|ladies)\b/i.test(g)) { m = g.match(/(\d+)/); return 'W' + (m ? m[1] : '') }
  if ((m = g.match(/\b([A-Z])[\s-]*grade\b/i))) return m[1].toUpperCase()
  return g.replace(/[^A-Za-z0-9]/g, '').slice(0, 3).toUpperCase() || '—'
}

function summarize(fx, defaultTarget) {
  const players = fx.lineup || []
  const target = defaultTarget || 11
  const has = (p, c) => (p.skill_positions || []).includes(c)
  const count = players.length
  const bal = { BAT: 0, ALL: 0, BWL: 0, WKT: 0 }
  const avail = { AVAILABLE: 0, MAYBE: 0, NO_RESPONSE: 0, UNAVAILABLE: 0 }
  const unavailableNames = []
  players.forEach((p) => {
    ROLE_CODES.forEach((c) => { if (has(p, c)) bal[c]++ })
    const a = p.availability || 'NO_RESPONSE'
    avail[a] = (avail[a] || 0) + 1
    if (a === 'UNAVAILABLE') unavailableNames.push(shortName(p.display_name))
  })
  const keeperPresent = bal.WKT > 0
  const capP = players.find((p) => p.is_captain)
  const wkP = players.find((p) => p.is_wicket_keeper)
  const capName = capP ? shortName(capP.display_name) : null
  const wkName = wkP ? shortName(wkP.display_name) : null
  const wkOut = !!(wkP && wkP.availability === 'UNAVAILABLE')
  const bowlers = bal.ALL + bal.BWL

  const flags = []
  if (count > 0 && count < target) flags.push({ tone: 'amber', text: `${target - count} short of XI` })
  if (wkOut) flags.push({ tone: 'red', text: 'Keeper out' })
  unavailableNames.forEach((n) => { if (!(wkOut && n === wkName)) flags.push({ tone: 'red', text: `${n} unavailable` }) })
  if (count >= 8 && !keeperPresent) flags.push({ tone: 'amber', text: 'No keeper named' })
  if (count >= 8 && bowlers < 5) flags.push({ tone: 'amber', text: 'Light on bowling' })
  if (count >= 8 && !capName) flags.push({ tone: 'amber', text: 'No captain named' })

  let status, statusLabel
  if (count === 0) { status = 'progress'; statusLabel = 'Not started' }
  else if (flags.some((f) => f.tone === 'red')) { status = 'attention'; statusLabel = 'Needs attention' }
  else if (count >= target && flags.length === 0) { status = 'ready'; statusLabel = 'Squad set' }
  else if (count >= target) { status = 'review'; statusLabel = 'Ready to review' }
  else { status = 'progress'; statusLabel = 'In progress' }

  return { count, target, bal, bowlers, avail, keeperPresent, capName, wkName, wkOut, flags, status, statusLabel }
}

function fmtDay(iso) {
  if (!iso || iso === 'tbc') return 'Date TBC'
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return iso }
}
function daysUntil(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T12:00:00')
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((d - today) / 86400000)
  if (diff <= 0) return 'today'
  if (diff === 1) return 'tomorrow'
  return `in ${diff}d`
}

// status → accent var (drives the left edge, count colour, CTA, status pill)
const STATUS_VAR = { ready: 'var(--pb-accent)', review: 'var(--pb-accent)', attention: 'var(--pb-red)', progress: 'var(--pb-amber)' }
const CTA_TEXT = { ready: '#08110b', review: '#08110b', attention: '#fff', progress: '#1b1205' }
const toneVar = (tone) => (tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)')

const FILTERS = [
  { id: 'all', label: 'All', color: 'var(--pb-accent)' },
  { id: 'attention', label: 'Needs attention', color: 'var(--pb-red)' },
  { id: 'progress', label: 'In progress', color: 'var(--pb-amber)' },
  { id: 'ready', label: 'Ready', color: 'var(--pb-accent)' },
]

// ── Pieces ──────────────────────────────────────────────────────────────────
function Pill({ color, children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-display font-semibold text-[11.5px] whitespace-nowrap ${className}`}
      style={{ color, background: tint(color, 13) }}>{children}</span>
  )
}

function AvailBar({ avail }) {
  const segs = AVAIL_ORDER.filter((s) => avail[s])
  return (
    <div className="flex h-[5px] w-[88px] rounded-full overflow-hidden bg-pb-surface2 shrink-0"
      title={segs.map((s) => `${avail[s]} ${AVAILABILITY[s].label.toLowerCase()}`).join(' · ')}>
      {segs.map((s) => <span key={s} style={{ flexGrow: avail[s], background: AVAILABILITY[s].cssVar, opacity: s === 'NO_RESPONSE' ? 0.45 : 1 }} />)}
    </div>
  )
}

function PlayerRow({ p, n }) {
  const meta = AVAILABILITY[p.availability] || AVAILABILITY.NO_RESPONSE
  const out = p.availability === 'UNAVAILABLE'
  const concern = out || p.availability === 'MAYBE'
  return (
    <div className={`relative flex items-center gap-2 px-2 py-1 rounded-lg min-h-[34px] hover:bg-pb-surface2 ${out ? 'opacity-60' : ''}`}>
      <span className="font-mono text-[11px] font-semibold text-pb-faintest w-[16px] text-right shrink-0 pb-num">{n}</span>
      <span className="w-[3px] self-stretch rounded-full my-0.5 shrink-0" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : meta.cssVar }} />
      <span className="relative shrink-0">
        <Avatar player={p} size={22} />
        <span className="absolute -right-0.5 -bottom-0.5"><Dot status={p.availability} size={8} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span>
      </span>
      <span className="font-display font-semibold text-[13.5px] truncate flex-1 min-w-0">{p.display_name}</span>
      {p.is_captain && <Tag>C</Tag>}{p.is_wicket_keeper && <Tag tone="amber">WK</Tag>}
      {concern
        ? <span className="font-mono text-[10px] font-semibold shrink-0" style={{ color: meta.cssVar }}>{out ? 'Out' : 'Maybe'}</span>
        : p.skill_positions?.length > 0 && <RoleChips roles={p.skill_positions} muted />}
    </div>
  )
}

function FixtureRow({ fx, target, open, onToggle }) {
  const navigate = useNavigate()
  const a = useMemo(() => summarize(fx, target), [fx, target])
  const goBuild = () => navigate(`/admin/betterselect/select/${fx.id}`)

  const opp = fx.opponent_name || fx.label || 'TBC'
  const matchup = fx.home_away === 'BYE' ? 'BYE' : `${fx.home_away === 'HOME' ? 'vs ' : '@ '}${opp}`
  const ha = fx.home_away === 'HOME' ? 'H' : fx.home_away === 'AWAY' ? 'A' : ''
  const squad = fx.team_name || fx.grade_name || 'Team'
  const worst = a.flags.find((f) => f.tone === 'red') || a.flags.find((f) => f.tone === 'amber')
  const extra = a.flags.length - (worst ? 1 : 0)
  const complete = a.count >= a.target
  const cta = a.count === 0 ? 'Build XI' : a.status === 'attention' ? 'Review XI' : 'Edit XI'
  const when = daysUntil(fx.played_on)
  const sv = STATUS_VAR[a.status]

  return (
    <div className="border border-pb-hairline rounded-xl bg-pb-surface overflow-hidden transition-shadow hover:border-pb-hairline2"
      style={{ borderLeftWidth: 3, borderLeftColor: sv, boxShadow: open ? '0 1px 2px rgba(0,0,0,.05), 0 18px 40px -20px rgba(16,20,30,.22)' : 'none' }}>
      {/* Compact row */}
      <div className="flex items-center gap-2.5 px-3 py-2 cursor-pointer hover:bg-pb-surface2" onClick={goBuild}>
        <span className="shrink-0 w-[30px] h-[30px] rounded-lg inline-flex items-center justify-center font-mono font-bold text-[11px] bg-pb-surface2 text-pb-dim">{gradeBadge(fx)}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="font-display font-bold text-[15px] tracking-tight whitespace-nowrap shrink-0">{squad}</span>
            <span className="font-medium text-pb-dim text-[13.5px] truncate min-w-0 hidden sm:inline">{matchup}</span>
          </div>
          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-pb-faint">
            {fx.start_time && <span>{fx.start_time}</span>}
            {fx.start_time && fx.venue && <i className="w-[3px] h-[3px] rounded-full bg-pb-faintest shrink-0" />}
            {fx.venue && <span className="truncate hidden sm:inline">{fx.venue}{ha ? ` (${ha})` : ''}</span>}
            {when && <><i className="w-[3px] h-[3px] rounded-full bg-pb-faintest shrink-0" /><span>{when}</span></>}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {worst && (
            <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-display font-semibold text-[11px] whitespace-nowrap"
              style={{ color: toneVar(worst.tone), background: tint(toneVar(worst.tone), 13) }}>
              {worst.text}{extra > 0 && <em className="not-italic opacity-70 font-mono text-[10px]">+{extra}</em>}
            </span>
          )}
          <span className="font-display font-bold text-[15px] pb-num whitespace-nowrap"
            style={{ color: a.count === 0 ? 'var(--pb-faint)' : complete ? 'var(--pb-accent)' : 'var(--pb-amber)' }}>
            {a.count}<span className="text-xs text-pb-faint font-medium">/{a.target}</span>
          </span>
          <Pill color={sv} className="hidden sm:inline-flex"><span className="w-1.5 h-1.5 rounded-full bg-current" />{a.statusLabel}</Pill>
          <button onClick={(e) => { e.stopPropagation(); onToggle(fx.id) }} title={open ? 'Collapse' : 'Peek'}
            className="shrink-0 w-[30px] h-[30px] rounded-lg inline-flex items-center justify-center text-pb-faintest hover:text-pb-dim hover:bg-pb-surface2">
            <Icon name="chevron" size={16} className="transition-transform" style={{ transform: open ? 'rotate(-90deg)' : 'rotate(90deg)' }} />
          </button>
        </div>
      </div>

      {/* Expanded peek */}
      {open && (
        <div className="border-t pb-hairline">
          {/* Balance + leadership */}
          <div className="flex items-center justify-between gap-4 flex-wrap px-4 py-2 border-b pb-hairline">
            <div className="flex items-center gap-3.5">
              {ROLE_CODES.map((c) => {
                const low = (c === 'BWL' && a.count >= 8 && a.bowlers < 5) || (c === 'WKT' && a.count >= 8 && !a.keeperPresent)
                return (
                  <span key={c} className="inline-flex flex-col items-center font-display">
                    <i className="not-italic text-[9.5px] tracking-wide2 uppercase" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{c === 'WKT' ? 'WK' : c}</i>
                    <b className="text-[16px] leading-none pb-num" style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{a.bal[c]}</b>
                  </span>
                )
              })}
            </div>
            <div className="flex items-center gap-3.5 text-[12.5px]">
              <span className="inline-flex items-center gap-1.5" style={{ color: a.capName ? 'var(--pb-dim)' : 'var(--pb-amber)' }}><Tag tone={a.capName ? 'accent' : 'faint'}>C</Tag>{a.capName || 'None'}</span>
              <span className="inline-flex items-center gap-1.5" style={{ color: a.wkName ? (a.wkOut ? 'var(--pb-red)' : 'var(--pb-dim)') : 'var(--pb-amber)' }}><Tag tone={a.wkName && !a.wkOut ? 'amber' : 'faint'}>WK</Tag>{a.wkName || 'None'}</span>
            </div>
          </div>

          {/* Flags */}
          <div className="flex flex-wrap gap-1.5 px-4 py-2">
            {a.flags.length > 0
              ? a.flags.map((f, i) => (
                <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-display font-semibold text-[11.5px]"
                  style={{ color: toneVar(f.tone), background: tint(toneVar(f.tone), 13) }}>
                  <Icon name={f.tone === 'red' ? 'close' : 'info'} size={12} />{f.text}
                </span>
              ))
              : a.count > 0
                ? <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-display font-semibold text-[11.5px]" style={{ color: 'var(--pb-positive)', background: tint('var(--pb-positive)', 12) }}><Icon name="check" size={12} />Balanced · keeper &amp; captain named</span>
                : <span className="text-[12.5px] text-pb-faint">No players selected yet.</span>}
          </div>

          {/* Availability breakdown */}
          {a.count > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pt-0 pb-0.5">
              {AVAIL_ORDER.map((s) => (
                <span key={s} className="inline-flex items-center gap-1.5 text-[12px] text-pb-dim"><Dot status={s} size={8} /><b className="font-display font-bold text-pb-text pb-num">{a.avail[s] || 0}</b>{AVAILABILITY[s].label}</span>
              ))}
            </div>
          )}

          {/* XI peek */}
          {a.count > 0 && (
            <div className="grid sm:grid-cols-2 gap-x-5 gap-y-0 px-2.5 pt-0.5 pb-1.5">
              {(fx.lineup || []).map((p, i) => <PlayerRow key={p.player_id} p={p} n={p.batting_order ?? i + 1} />)}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-2.5 border-t pb-hairline" style={{ background: 'color-mix(in srgb, var(--pb-surface2) 45%, transparent)' }}>
            <div className="flex items-center gap-2.5 min-w-0">
              <AvailBar avail={a.avail} />
              <span className="text-xs text-pb-dim whitespace-nowrap">{a.count} selected{a.count > a.target ? ` · ${a.count - a.target} in reserve` : ''}</span>
            </div>
            <button onClick={goBuild}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-display font-semibold text-[13px] transition hover:brightness-105 active:scale-[0.98]"
              style={{ background: sv, color: CTA_TEXT[a.status] }}>
              {cta}<Icon name="arrow" size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Screen ──────────────────────────────────────────────────────────────────
export default function AdminSelectionOverview() {
  const toast = useToast()
  const { theme, toggle: toggleTheme } = useTheme()
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [openKeys, setOpenKeys] = useState(() => new Set())

  const load = useCallback(() => {
    setData(null)
    api.bsSelectionOverview().then(setData).catch((e) => { toast.error(e.message); setData({ fixtures: [] }) })
  }, [toast])
  useEffect(() => { load() }, [load])

  const target = data?.default_team_size ?? 11
  const toggle = useCallback((key) => setOpenKeys((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n }), [])

  const withStatus = useMemo(() => (data?.fixtures || []).map((fx) => ({ fx, status: summarize(fx, target).status })), [data, target])
  const counts = useMemo(() => {
    const c = { all: withStatus.length, attention: 0, progress: 0, ready: 0 }
    withStatus.forEach(({ status }) => {
      if (status === 'attention') c.attention++
      else if (status === 'progress') c.progress++
      else c.ready++ // ready + review
    })
    return c
  }, [withStatus])

  const visible = useMemo(() => {
    const s = q.trim().toLowerCase()
    return withStatus.filter(({ fx, status }) => {
      if (filter === 'ready' && !(status === 'ready' || status === 'review')) return false
      if (filter !== 'all' && filter !== 'ready' && status !== filter) return false
      if (s) {
        const hay = `${fx.team_name || ''} ${fx.opponent_name || fx.label || ''} ${fx.grade_name || ''}`.toLowerCase()
        if (!hay.includes(s)) return false
      }
      return true
    })
  }, [withStatus, filter, q])

  const groups = useMemo(() => {
    const map = new Map()
    visible.forEach((v) => { const k = v.fx.played_on || 'tbc'; if (!map.has(k)) map.set(k, []); map.get(k).push(v) })
    return [...map.entries()].map(([day, items]) => ({ day, items, attention: items.filter((i) => i.status === 'attention').length }))
  }, [visible])

  const allOpen = visible.length > 0 && visible.every((v) => openKeys.has(v.fx.id))
  const toggleAll = () => setOpenKeys(allOpen ? new Set() : new Set(visible.map((v) => v.fx.id)))

  const actions = (
    <button onClick={toggleTheme} title="Toggle theme"
      className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-lg bg-pb-surface2 border border-pb-hairline text-pb-dim hover:text-pb-text">
      <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
    </button>
  )

  if (data === null) return <BetterSelectLayout title="Selection" actions={actions}><PbSpinner message="Loading teams…" /></BetterSelectLayout>

  if (!data.fixtures.length) {
    return (
      <BetterSelectLayout title="Selection" actions={actions}>
        <div className="pb-card rounded-xl px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures.{' '}
          <Link to="/admin/betterselect/fixtures" className="text-pb-accent underline">Add or sync fixtures</Link> first.
        </div>
      </BetterSelectLayout>
    )
  }

  return (
    <BetterSelectLayout title="Selection" actions={actions}>
      {/* Intro */}
      <div className="flex items-end justify-between gap-5 flex-wrap mb-3">
        <div>
          <h2 className="font-display font-bold text-[18px] tracking-tight">Upcoming selections</h2>
          <p className="text-[13px] text-pb-dim mt-0.5">{counts.all} {counts.all === 1 ? 'team' : 'teams'} to pick. Open a team to build or edit its XI.</p>
        </div>
        <div className="flex items-center gap-4">
          {counts.attention > 0 && <span className="inline-flex items-center gap-1.5 text-[13px] text-pb-dim"><span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--pb-red)' }} /><b className="font-display font-bold text-pb-red">{counts.attention}</b> need attention</span>}
          <span className="inline-flex items-center gap-1.5 text-[13px] text-pb-dim"><span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--pb-accent)' }} /><b className="font-display font-bold text-pb-text">{counts.ready}</b> ready</span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div className="flex items-center gap-2 bg-pb-surface border border-pb-hairline rounded-lg px-3 h-[34px] text-pb-faint flex-1 min-w-[200px] max-w-[300px] focus-within:border-pb-accent">
          <Icon name="search" size={15} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a team or opponent…"
            className="bg-transparent border-0 outline-none text-pb-text text-sm w-full placeholder:text-pb-faint" />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map((fl) => {
            const n = fl.id === 'all' ? counts.all : counts[fl.id]
            const on = filter === fl.id
            return (
              <button key={fl.id} onClick={() => setFilter(fl.id)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border font-display font-semibold text-[12.5px] transition ${on ? '' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}
                style={on ? { color: fl.color, background: tint(fl.color, 13), borderColor: tint(fl.color, 45) } : undefined}>
                {fl.label}<span className="font-mono text-[11px] opacity-85">{n}</span>
              </button>
            )
          })}
        </div>
        <span className="flex-1" />
        <button onClick={toggleAll} className="inline-flex items-center gap-1.5 text-pb-faint hover:text-pb-accent font-display font-semibold text-[12.5px] whitespace-nowrap">
          <Icon name={allOpen ? 'cols' : 'sheet'} size={14} />{allOpen ? 'Collapse all' : 'Expand all'}
        </button>
        <span className="font-mono text-[11px] text-pb-faintest whitespace-nowrap">{visible.length} of {counts.all}</span>
      </div>

      {/* Grouped list */}
      {groups.length === 0 ? (
        <div className="text-center py-14 text-pb-faint text-sm">
          <b className="block text-pb-text font-display font-bold text-base mb-1">No teams match</b>
          Try a different search or filter.
        </div>
      ) : groups.map((g) => (
        <section key={g.day} className="mb-1.5">
          <div className="sticky top-[57px] z-10 flex items-center gap-3 px-1 pt-2.5 pb-1.5 bg-pb-bg">
            <span className="font-display font-bold text-[13.5px] tracking-tight whitespace-nowrap">{fmtDay(g.day)}</span>
            <span className="font-mono text-[11px] text-pb-faint whitespace-nowrap">{g.items.length} {g.items.length === 1 ? 'team' : 'teams'}</span>
            {g.attention > 0 && <span className="inline-flex items-center gap-1.5 text-[11.5px] text-pb-red font-semibold whitespace-nowrap"><span className="w-1.5 h-1.5 rounded-full bg-current" />{g.attention} need attention</span>}
            <span className="flex-1 h-px bg-pb-hairline min-w-[16px]" />
          </div>
          <div className="flex flex-col gap-1.5">
            {g.items.map(({ fx }) => (
              <FixtureRow key={fx.id} fx={fx} target={target} open={openKeys.has(fx.id)} onToggle={toggle} />
            ))}
          </div>
        </section>
      ))}
    </BetterSelectLayout>
  )
}
