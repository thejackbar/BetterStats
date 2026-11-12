import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, ReferenceArea,
} from 'recharts'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { computeKpis, convertedByCreative, unmappedAds, creativeKey, NO_TAG } from './metaAdsKpi'
import { mergeClubs, stageCounts, applyClubFilters, originCounts, originOf, ORIGINS, ORIGIN_ORDER, STAGES } from './metaAdsClubs'

const DEFAULT_BUDGET = 900
const DEFAULT_LENGTH_DAYS = 30

// ONE campaign, TWO products since the 8-9 Sep 2026 restructure. Both landing
// pages fire the same CompleteRegistration pixel event and are told apart only
// by `content_category`, so nothing on this page shows a conversion count or a
// cost per result without saying which of the two it belongs to — a trial
// signup is a prospective paying club, a webinar registration is somebody who
// watched a form, and averaging them describes neither.
const STREAM_STYLE = {
  trial: {
    accent: 'var(--pb-accent)',
    chip: 'border-violet-500/40 text-violet-300 bg-violet-500/10',
    swatch: 'bg-violet-400',
  },
  webinar: {
    accent: '#38bdf8',
    chip: 'border-sky-500/40 text-sky-300 bg-sky-500/10',
    swatch: 'bg-sky-400',
  },
}
const streamStyle = (s) => STREAM_STYLE[s] || STREAM_STYLE.trial

const TREND_RANGES = [
  { label: '7d', days: 7 },
  { label: '14d', days: 14 },
  { label: '30d', days: 30 },
  { label: 'Lifetime', days: 90 },
]

const SEVERITY_STYLE = {
  critical: { dot: 'bg-red-400', border: 'border-red-500/50', text: 'text-red-300' },
  warning: { dot: 'bg-amber-400', border: 'border-amber-500/50', text: 'text-amber-300' },
  info: { dot: 'bg-sky-400', border: 'border-sky-500/50', text: 'text-sky-300' },
  good: { dot: 'bg-emerald-400', border: 'border-emerald-500/50', text: 'text-emerald-300' },
}

const AD_STATUS_STYLE = {
  winner: { label: 'Winner', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  laggard: { label: 'Laggard', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
  on_track: { label: 'On track', cls: 'bg-pb-surface2 text-pb-faint border-pb-hairline' },
  paused: { label: 'Paused', cls: 'bg-slate-500/15 text-slate-400 border-slate-500/40' },
}

function fmtMoney(n) {
  if (n == null || Number.isNaN(n)) return 'A$0.00'
  return `A$${Number(n).toFixed(2)}`
}
function fmtNum(n) {
  if (n == null) return '0'
  const v = Number(n)
  if (v >= 10000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return Math.round(v).toLocaleString('en-AU')
}
function fmtPct(n) {
  if (n == null) return '–'
  return `${Number(n).toFixed(1)}%`
}
function fmtTime(iso) {
  if (!iso) return 'never'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
    timeZone: 'Australia/Perth',
  }) + ' (Perth)'
}
function fmtDay(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', timeZone: 'Australia/Perth' })
}
// `<input type="datetime-local">` needs "YYYY-MM-DDTHH:mm" in the WALL-CLOCK
// timezone we're editing in (Perth, matching every other timestamp on this
// page) — formatToParts sidesteps toISOString's UTC conversion.
function isoToPerthInput(iso) {
  if (!iso) return ''
  const parts = new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Perth', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date(iso))
  const get = (t) => parts.find((p) => p.type === t)?.value
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
}

// The row's Last seen as a plain YYYY-MM-DD in Perth, the same wall clock
// fmtTime prints it in, so a range typed off what is on screen matches what is
// on screen. Comparing the two date strings keeps both ends of the range
// inclusive with no hour maths, and a row either side of midnight cannot land
// on the wrong day.
function perthDay(iso) {
  if (!iso) return ''
  const parts = new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Perth', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(iso))
  const get = (t) => parts.find((p) => p.type === t)?.value
  return `${get('year')}-${get('month')}-${get('day')}`
}

// Club-name search + an inclusive Last seen date range, shared by the two
// wizard club tables. Filtered in the browser rather than on the wire: both
// tables already hold every row they list (they are a standing follow-up list,
// not a windowed stat), so this is the same call the "Not selected only" and
// "Show tests" toggles beside it already make.
function useClubFilter() {
  const [q, setQ] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const active = Boolean(q.trim() || from || to)
  const clear = useCallback(() => { setQ(''); setFrom(''); setTo('') }, [])
  const apply = useCallback((rows) => {
    const needle = q.trim().toLowerCase()
    return (rows || []).filter((c) => {
      if (needle && !(c.name || '').toLowerCase().includes(needle)) return false
      if (from || to) {
        // A row we hold no Last seen for cannot satisfy a date range, so it
        // drops out rather than being swept in as a maybe.
        const day = perthDay(c.last_at)
        if (!day) return false
        if (from && day < from) return false
        if (to && day > to) return false
      }
      return true
    })
  }, [q, from, to])
  return { q, setQ, from, setFrom, to, setTo, active, clear, apply }
}

const FILTER_INPUT = 'bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 font-mono text-[10px] text-pb-text'

function ClubFilterBar({ filter, placeholder }) {
  const { q, setQ, from, setFrom, to, setTo, active, clear } = filter
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        className={`flex-1 min-w-[11rem] ${FILTER_INPUT} py-1.5 text-[11px]`}
      />
      <label className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wide text-pb-faint">
        Last seen
        <input
          type="date"
          value={from}
          max={to || undefined}
          onChange={(e) => setFrom(e.target.value)}
          aria-label="Last seen from"
          className={FILTER_INPUT}
        />
      </label>
      <label className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wide text-pb-faint">
        to
        <input
          type="date"
          value={to}
          min={from || undefined}
          onChange={(e) => setTo(e.target.value)}
          aria-label="Last seen to"
          className={FILTER_INPUT}
        />
      </label>
      {active && (
        <button
          type="button"
          onClick={clear}
          className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint hover:text-pb-text"
        >
          Clear
        </button>
      )}
    </div>
  )
}

function ChartTooltip({ active, payload, label, money }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-xs shadow-lg">
      {label && <p className="font-mono text-[10px] text-pb-faint mb-1">{fmtDay(label)}</p>}
      {payload.map((p, i) => (
        <p key={i} className="font-mono text-pb-text">
          <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: p.color }} />
          {p.name}: <strong>{money?.has(p.dataKey) ? fmtMoney(p.value) : p.value}</strong>
        </p>
      ))}
    </div>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="pb-card px-3 py-2.5">
      <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{label}</div>
      <div className="font-display text-xl text-pb-text mt-0.5">{value}</div>
      {hint && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{hint}</div>}
    </div>
  )
}

// One Meta token's state in words, and how loud it should be. 'bad' is expired
// or invalid, 'warn' is inside the warn window, 'off' is a deliberately-unset
// token (a state, not an alarm), 'ok' is everything else.
function tokenStatus(t, warnWithin = 14) {
  if (!t) return { level: 'off', text: 'checking…' }
  if (!t.configured) return { level: 'off', text: 'off (not set)' }
  if (!t.checked) return { level: 'off', text: 'status unknown' }
  if (t.valid === false) return { level: 'bad', text: 'EXPIRED / invalid' }
  if (t.never) return { level: 'ok', text: 'valid, never expires' }
  if (t.days_left == null) return { level: 'ok', text: 'valid' }
  if (t.days_left <= warnWithin) {
    return { level: 'warn', text: `expires in ${t.days_left} day${t.days_left === 1 ? '' : 's'}` }
  }
  return { level: 'ok', text: `expires in ${t.days_left} days` }
}

// Token health as ONE small pill in the header, not a section. The CAPI token
// is still covered: its failure is otherwise silent (server-side conversions
// just stop), so either token going bad turns the pill red and the detail for
// both is in the tooltip.
const TOKEN_PILL_TONE = {
  bad: 'text-red-300 border-red-500/40 bg-red-500/10',
  warn: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
  ok: 'text-emerald-300/90 border-emerald-500/30',
  off: 'text-pb-faint border-pb-hairline',
}
function TokenPill({ health }) {
  if (!health) return null
  const warnWithin = health.warn_within_days
  const parts = [['Ads token', health.ads], ['CAPI token', health.capi]]
    .map(([label, t]) => ({ label, t, ...tokenStatus(t, warnWithin) }))
  const levels = parts.map((p) => p.level)
  const level = levels.includes('bad') ? 'bad' : levels.includes('warn') ? 'warn'
    : levels.includes('ok') ? 'ok' : 'off'
  const headline = { bad: 'Token problem', warn: 'Token expiring', ok: 'Tokens OK', off: 'Tokens unknown' }[level]
  const detail = parts
    .map((p) => `${p.label}: ${p.text}${p.t && p.t.error ? ` (${p.t.error})` : ''}`)
    .join('. ')
  return (
    <span
      data-testid="token-pill"
      title={detail}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wide2 ${TOKEN_PILL_TONE[level]}`}
    >
      {headline}
    </span>
  )
}

// One tile of the headline strip: a big number, what it is, which side of the
// Meta / our-database line it comes from, and the caveat as a tooltip. The
// source tag is on every tile because the two are never to be confused.
function KpiTile({ id, label, value, source, hint, caveat, compact = false }) {
  return (
    <div data-testid={`kpi-${id}`} title={caveat} className="pb-card px-3 py-2.5 min-w-0">
      <div className="flex items-baseline justify-between gap-1">
        <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{label}</div>
        <span data-testid={`kpi-${id}-source`} className="font-mono text-[8px] uppercase tracking-wide text-pb-faintest shrink-0">
          {source}
        </span>
      </div>
      <div data-testid={`kpi-${id}-value`} className={`font-display ${compact ? 'text-lg' : 'text-2xl'} text-pb-text mt-0.5 truncate`}>
        {value}
      </div>
      {hint && <div data-testid={`kpi-${id}-hint`} className="font-mono text-[9px] text-pb-faintest mt-0.5 leading-snug">{hint}</div>}
    </div>
  )
}

const SRC_META = 'Meta-reported'
const SRC_OURS = 'Our tracking'

// The whole ask in six tiles: what we spent, how many trials it drove, what
// each cost, how many became paying clubs, what that earned, and the return.
// Everything else on the page is supporting detail for these.
function KpiStrip({ kpis, signupsLoaded }) {
  const k = kpis
  const dash = <span className="text-pb-faintest">&ndash;</span>
  const pending = <span className="text-pb-faintest">&hellip;</span>
  return (
    <div data-testid="kpi-strip" className="mb-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <KpiTile
          id="spend" label="Spend" source={SRC_META}
          value={fmtMoney(k.campaignSpend)}
          hint={k.webinarSpend > 0 ? `${fmtMoney(k.trialSpend)} trial ads, ${fmtMoney(k.webinarSpend)} webinar ads` : undefined}
          caveat="What Meta says the campaign has spent, from the stored snapshot. Respects the counting-since window. Cost per trial and ROAS below use the trial ads' spend only."
        />
        <KpiTile
          id="trials" label="Trial signups" source={SRC_OURS}
          value={k.trials == null ? dash : fmtNum(k.trials)}
          caveat="Our own database's count of real completed registrations attributed to this campaign, plus any manual adjustment. Not Meta's Lead count, and never narrowed by counting-since."
        />
        <KpiTile
          id="cost" label="Cost / trial" source="Spend / signups"
          value={k.costPerTrial != null ? fmtMoney(k.costPerTrial) : dash}
          hint={k.costPerTrial == null ? k.costWhy : 'trial-ad spend / trial signups'}
          caveat="Trial ads' own spend divided by trial signups, all time. The webinar's spend is never charged to the trial."
        />
        <KpiTile
          id="converted" label="Converted to paid" source={SRC_OURS}
          value={k.converted == null ? (signupsLoaded ? dash : pending) : fmtNum(k.converted)}
          hint={k.trackedSignups != null ? `of ${fmtNum(k.trackedSignups)} tracked signups` : undefined}
          caveat="Attributed clubs that now hold a paid module, from the signups table below."
        />
        <KpiTile
          id="revenue" label="Revenue (est.)" source="Converted x value"
          value={k.revenue == null ? (signupsLoaded ? dash : pending) : fmtMoney(k.revenue)}
          hint={k.converted != null ? `${fmtNum(k.converted)} x A$${k.unit}` : undefined}
          caveat={`An estimate, not Stripe takings: paid clubs x A$${k.unit}, the trial stream's value. Webinar registrations are never valued.`}
        />
        <KpiTile
          id="roas" label="ROAS" source="Revenue / spend"
          value={k.roas != null ? `${k.roas.toFixed(2)}x` : dash}
          hint={k.roas == null ? k.roasWhy : 'revenue / trial-ad spend'}
          caveat="Estimated revenue over the trial ads' own spend. Moves as trials convert: a trial that has not paid yet counts as nothing."
        />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mt-2">
        <KpiTile
          id="rate" label="Trial to paid" source={SRC_OURS} compact
          value={k.rate != null ? fmtPct(k.rate * 100) : dash}
          hint={k.rate != null ? `${fmtNum(k.converted)} of ${fmtNum(k.trackedSignups)}` : 'no tracked signups yet'}
          caveat="Paid clubs over the tracked signups they came from. The number the whole plan hinges on."
        />
        {k.showWebinar && (
          <KpiTile
            id="webinar" label="Webinar regs" source={SRC_OURS} compact
            value={fmtNum(k.webinarRegs)}
            hint="kept separate, carries no value"
            caveat="Webinar registrations attributed to this campaign. A different result from a trial signup, so never added to it and never valued in revenue or ROAS."
          />
        )}
      </div>
      {k.windowMismatch && (
        <p data-testid="kpi-window-note" className="font-mono text-[9px] text-amber-300/80 mt-1.5 leading-relaxed">
          Cost per trial and ROAS are withheld: {k.mismatchReason}, so dividing one by the other would read
          better than the truth. Clear &ldquo;counting since&rdquo; to read them.
        </p>
      )}
    </div>
  )
}

// The counting-since seed, shown beside the KPI strip so the active window is
// obvious. It narrows the funnel numbers and Meta's own insights (and so the
// Spend tile). It NEVER narrows real completed registrations.
function CountingSince({ countingSince, editing, input, setInput, saving, onOpen, onApply, onCancel, onClear }) {
  return (
    <div data-testid="counting-since" className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-3">
      {editing ? (
        <>
          <input
            type="datetime-local"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={saving}
            className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 font-mono text-[10px] text-pb-text disabled:opacity-50"
          />
          <button
            onClick={onApply}
            disabled={saving || !input}
            className="font-mono text-[9px] uppercase tracking-wide2 text-pb-accent hover:underline disabled:opacity-50"
          >
            Apply
          </button>
          <button
            onClick={onCancel}
            disabled={saving}
            className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint hover:underline disabled:opacity-50"
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <span className="font-mono text-[10px] text-pb-dim">
            {countingSince
              ? <>Counting since <span data-testid="counting-since-value" className="text-pb-text">{fmtTime(countingSince)}</span></>
              : 'Counting since launch (no reset)'}
          </span>
          <button
            onClick={onOpen}
            disabled={saving}
            className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint hover:text-pb-text hover:underline disabled:opacity-50"
          >
            Reset from&hellip;
          </button>
          {countingSince && (
            <button
              onClick={onClear}
              disabled={saving}
              className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint hover:text-red-300 hover:underline disabled:opacity-50"
            >
              Clear
            </button>
          )}
        </>
      )}
      <span className="font-mono text-[9px] text-pb-faintest">
        Spend and Meta&rsquo;s figures start here. Trial signups always count every real registration.
      </span>
    </div>
  )
}

function InsightRow({ insight }) {
  const style = SEVERITY_STYLE[insight.severity] || SEVERITY_STYLE.info
  return (
    <div className={`flex items-start gap-2.5 py-2 px-3 rounded border-l-2 bg-pb-surface2/30 ${style.border}`}>
      <span className={`shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full ${style.dot}`} />
      <p className="text-xs leading-relaxed">
        <span className={`font-medium ${style.text}`}>{insight.title}.</span>{' '}
        <span className="text-pb-dim">{insight.detail}</span>
      </p>
    </div>
  )
}

// ── Period and scope: ONE control for every on-site panel ─────────────────────
// With a campaign selected the on-site numbers used to be all traffic, and the club
// list went back to the start of the year. The period narrows how far back, the
// scope says whose traffic: the selected campaign (default) or everything.
const PERIODS = [
  { days: 1, label: '24 hours' },
  { days: 7, label: '7 days' },
  { days: 14, label: '14 days' },
  { days: 30, label: '30 days' },
  { days: 730, label: 'Whole campaign' },
]
const periodLabel = (days) => (PERIODS.find((p) => p.days === days) || PERIODS[1]).label.toLowerCase()

function Segmented({ options, value, onChange, testPrefix }) {
  return (
    <div role="group" className="inline-flex flex-wrap rounded border border-pb-hairline overflow-hidden">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          aria-pressed={value === o.value}
          data-testid={`${testPrefix}-${o.value}`}
          onClick={() => onChange(o.value)}
          className={`px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide2 ${
            value === o.value ? 'bg-pb-accent text-white' : 'text-pb-dim hover:bg-pb-surface2'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function PeriodScopeBar({ period, onPeriod, scope, onScope, countsFrom }) {
  return (
    <div data-testid="period-scope-bar" className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <Segmented
        testPrefix="period"
        value={period}
        onChange={onPeriod}
        options={PERIODS.map((p) => ({ value: p.days, label: p.label }))}
      />
      <Segmented
        testPrefix="scope"
        value={scope}
        onChange={onScope}
        options={[{ value: 'campaign', label: 'This campaign' }, { value: 'all', label: 'All traffic' }]}
      />
      <span data-testid="scope-note" className="font-mono text-[9px] text-pb-faint">
        {scope === 'campaign'
          ? <>This campaign&rsquo;s visitors only{countsFrom ? <>, from {fmtDay(countsFrom)}</> : ''}.</>
          : 'Every source, including other campaigns, email and organic.'}
      </span>
    </div>
  )
}

const STAGE_BADGE = {
  completed: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
  terms: 'border-amber-500/40 text-amber-300 bg-amber-500/10',
  selected: 'border-violet-500/40 text-violet-300 bg-violet-500/10',
  searched: 'border-sky-500/40 text-sky-300 bg-sky-500/10',
}
const ORIGIN_BADGE = {
  meta: 'border-violet-500/40 text-violet-300 bg-violet-500/10',
  email: 'border-sky-500/40 text-sky-300 bg-sky-500/10',
  google: 'border-blue-500/40 text-blue-300 bg-blue-500/10',
  social: 'border-pink-500/40 text-pink-300 bg-pink-500/10',
  ai: 'border-teal-500/40 text-teal-300 bg-teal-500/10',
  referral: 'border-pb-hairline text-pb-dim',
  campaign_other: 'border-pb-hairline text-pb-dim',
  direct: 'border-pb-hairline text-pb-faint',
  unknown: 'border-pb-hairline text-pb-faintest',
}
// Chips, in the order a follow-up works through them. `terms` is "reached the Terms step and
// has not finished", the clubs worth a call.
const STAGE_CHIPS = [
  { key: 'all', label: 'All' },
  { key: 'completed', label: 'Completed' },
  { key: 'terms', label: 'Reached terms, not finished' },
  { key: 'selected', label: 'Selected a club' },
  { key: 'searched', label: 'Searched only' },
]

function ClubRow({ c, busy, onFlag, onRestore }) {
  return (
    <tr data-testid="club-row" className={`border-b pb-hairline last:border-0 hover:bg-pb-surface2/40 ${c.hidden ? 'opacity-50' : ''}`}>
      <td className="px-2 py-2 text-pb-text font-medium whitespace-nowrap">
        {c.slug ? <a href={`/${c.slug}`} className="hover:underline">{c.name}</a> : c.name}
      </td>
      <td className="px-2 py-2">
        <span data-testid="club-stage" className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase whitespace-nowrap ${STAGE_BADGE[c.stage]}`}>
          {STAGES[c.stage].label}
        </span>
      </td>
      <td className="px-2 py-2" title={c.origin?.detail || 'No page view of this club\'s visitor on record'}>
        <span data-testid="club-origin" className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] whitespace-nowrap ${ORIGIN_BADGE[originOf(c)]}`}>
          {c.origin?.label || 'Unknown'}
        </span>
      </td>
      <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{c.email || '–'}</td>
      <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{fmtTime(c.last_at)}</td>
      <td className="px-2 py-2 text-right whitespace-nowrap">
        {c.hidden ? (
          <button type="button" disabled={busy} onClick={onRestore} className="font-mono text-[9px] uppercase text-pb-faint hover:text-pb-text disabled:opacity-40">
            Restore
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={onFlag}
            title="Hide this row from the list (doesn't affect the Sales Pipeline)"
            className="font-mono text-[9px] uppercase text-pb-faint hover:text-red-300 disabled:opacity-40"
          >
            Flag as test
          </button>
        )}
      </td>
    </tr>
  )
}

// The follow-up list: every club that typed into the trial page in the chosen period, one row
// each, with the furthest stage it reached. It was two tables (selected, searched) that said the
// same club twice; they fold on the club name. Always stacked in view, never behind a tab, and
// an empty or failed list says so (it was lost once to a tab that opened on the funnel).
function ClubsPanel({ selected, searched, scope, onScope, period, failed, busyKey, onFlag, onRestore }) {
  const filter = useClubFilter()
  const [stage, setStage] = useState('all')
  const [origin, setOrigin] = useState('all')
  const [showHidden, setShowHidden] = useState(false)
  const [limit, setLimit] = useState(40)
  const rows = useMemo(() => mergeClubs(selected, searched), [selected, searched])
  const visible = rows.filter((r) => !r.hidden)
  const hidden = rows.filter((r) => r.hidden)
  const counts = stageCounts(visible)
  const origins = originCounts(visible)
  const searchedRows = filter.apply(visible)
  const shown = applyClubFilters(searchedRows, { stage, origin })
  const shownHidden = showHidden ? filter.apply(hidden) : []
  const loading = !failed && (selected == null || searched == null)
  const outside = selected?.outside_campaign || 0
  const unnamed = selected?.anonymous || 0
  return (
    <div data-testid="clubs-panel" className="pb-card p-4 mb-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
          Clubs that typed in their club, and how far they got
        </div>
        <span className="font-mono text-[10px] text-pb-faintest flex items-center gap-2">
          <span data-testid="clubs-count">{shown.length} of {visible.length} club{visible.length === 1 ? '' : 's'}, {periodLabel(period)}</span>
          {hidden.length > 0 && (
            <button type="button" onClick={() => setShowHidden((v) => !v)} className="px-1.5 py-0.5 rounded-full border border-pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-dim uppercase">
              {showHidden ? 'Hide' : 'Show'} {hidden.length} test{hidden.length === 1 ? '' : 's'}
            </button>
          )}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 my-2.5">
        {STAGE_CHIPS.map((chip) => (
          <button
            key={chip.key}
            type="button"
            aria-pressed={stage === chip.key}
            data-testid={`club-chip-${chip.key}`}
            onClick={() => { setStage(chip.key); setLimit(40) }}
            className={`px-2 py-1 rounded-full border font-mono text-[10px] ${
              stage === chip.key ? 'border-pb-accent bg-pb-accent/15 text-pb-text' : 'border-pb-hairline text-pb-dim hover:border-pb-dim'
            }`}
          >
            {chip.label} <span data-testid={`club-chip-count-${chip.key}`} className="opacity-70">{counts[chip.key]}</span>
          </button>
        ))}
        <label className="flex items-center gap-1.5 ml-1 font-mono text-[10px] text-pb-dim">
          Where from
          <select
            data-testid="club-origin-filter"
            value={origin}
            onChange={(e) => { setOrigin(e.target.value); setLimit(40) }}
            className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 font-mono text-[10px] text-pb-text"
          >
            <option value="all">All sources ({visible.length})</option>
            {ORIGIN_ORDER.filter((k) => origins[k]).map((k) => (
              <option key={k} value={k}>{ORIGINS[k]} ({origins[k]})</option>
            ))}
          </select>
        </label>
      </div>

      <ClubFilterBar filter={filter} placeholder="Search club name" />

      {failed && (
        <p data-testid="lists-failed" className="font-mono text-[10px] text-red-300 bg-red-500/10 border border-red-500/20 rounded px-3 py-2 mb-3">
          Could not load the club list. Refresh the page to try again.
        </p>
      )}
      {loading && <p className="text-xs text-pb-faint">Loading&hellip;</p>}

      {!failed && !loading && rows.length === 0 && (
        <p data-testid="clubs-empty" className="text-xs text-pb-faint">
          No club typed into the trial page {scope === 'campaign' ? 'from this campaign ' : ''}in the last {periodLabel(period)}.
        </p>
      )}
      {!failed && !loading && rows.length > 0 && shown.length === 0 && shownHidden.length === 0 && (
        <p data-testid="clubs-no-match" className="text-xs text-pb-faint">No club matches those filters.</p>
      )}

      {(shown.length > 0 || shownHidden.length > 0) && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                <th className="px-2 py-2">Club</th>
                <th className="px-2 py-2">Stage</th>
                <th className="px-2 py-2">Where from</th>
                <th className="px-2 py-2">Contact email</th>
                <th className="px-2 py-2">Last seen</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, limit).map((c) => (
                <ClubRow key={c.key} c={c} busy={busyKey === c.key} onFlag={() => onFlag(c)} />
              ))}
              {shownHidden.map((c) => (
                <ClubRow key={'hidden-' + c.key} c={c} busy={busyKey === c.key} onRestore={() => onRestore(c)} />
              ))}
            </tbody>
          </table>
          {shown.length > limit && (
            <button type="button" data-testid="clubs-more" onClick={() => setLimit((n) => n + 40)} className="mt-2 font-mono text-[10px] text-pb-faint hover:text-pb-text hover:underline">
              Show {Math.min(40, shown.length - limit)} more of {shown.length - limit}
            </button>
          )}
        </div>
      )}

      {scope === 'campaign' && outside > 0 && (
        <p data-testid="clubs-outside" className="font-mono text-[9px] text-pb-faint mt-3">
          {outside} more club{outside === 1 ? '' : 's'} started in this period from other traffic (another campaign, email or organic) and
          {outside === 1 ? ' is' : ' are'} not listed.{' '}
          <button type="button" onClick={() => onScope('all')} className="text-pb-accent hover:underline">Show all traffic</button>
        </p>
      )}
      {unnamed > 0 && (
        <p data-testid="clubs-unnamed" className="font-mono text-[9px] text-pb-faintest mt-1">
          {unnamed} club selection{unnamed === 1 ? '' : 's'} in this period could not be named (picked before the club was captured on the beacon).
        </p>
      )}
      <p className="font-mono text-[9px] text-pb-faintest mt-3">
        One row per club, with the furthest stage it reached and where it came from, read from its UTM tags, ad click id and
        referrer. &ldquo;Direct&rdquo; means none of those: a typed address, a bookmark, or an app that hides the referrer (a shared
        link can sit here). &ldquo;Reached terms, not finished&rdquo; is the list worth a call. &ldquo;Flag as test&rdquo; hides a row here and doesn&rsquo;t touch the Sales Pipeline.
      </p>
    </div>
  )
}

// The on-site side of the ad click for the SELECTED campaign (the Usage page has the all-traffic one).
function TrafficCard({ data, scope, period }) {
  // Nothing to draw until a real answer arrives; an unexpected shape must not take the page down.
  if (!data || !data.meta || !data.conversion) return null
  const who = scope === 'campaign' ? 'Campaign visitors' : 'Meta visitors'
  return (
    <div data-testid="traffic-card" className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-3">
        On-site traffic, our own visit tracking, {periodLabel(period)}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
        <Stat label={who} value={fmtNum(data.meta.visitors)} hint="site-tracked, not Meta's own count" />
        <Stat label="Facebook" value={fmtNum(data.meta.facebook)} />
        <Stat label="Instagram" value={fmtNum(data.meta.instagram)} />
        <Stat label="Paid clicks" value={fmtNum(data.meta.paid)} />
        <Stat label="Reached pricing/contact" value={fmtNum(data.conversion.reached_intent)} hint={`${data.conversion.pct}% of ${who.toLowerCase()}`} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1.5">Top ad creatives (by visitor)</div>
          {data.creatives.length === 0 ? (
            <p className="text-xs text-pb-faint">No tagged creatives seen in this period.</p>
          ) : (
            <table className="w-full text-xs">
              <tbody>
                {data.creatives.slice(0, 6).map((c, i) => (
                  <tr key={i} className="border-b pb-hairline last:border-0">
                    <td className="py-1.5 pr-2 text-pb-text">{c.content || '(untagged)'}</td>
                    <td className="py-1.5 text-right text-pb-dim whitespace-nowrap">{fmtNum(c.visitors)} visitors</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>
          <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1.5">Where the clicks land</div>
          {data.landing.length === 0 ? (
            <p className="text-xs text-pb-faint">No landing pages recorded in this period.</p>
          ) : (
            <table className="w-full text-xs">
              <tbody>
                {data.landing.slice(0, 6).map((l, i) => (
                  <tr key={i} className="border-b pb-hairline last:border-0">
                    <td className="py-1.5 pr-2 text-pb-text">{l.label || l.page}</td>
                    <td className="py-1.5 text-right text-pb-dim whitespace-nowrap">{fmtNum(l.visitors)} visitors</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <p className="font-mono text-[9px] text-pb-faintest mt-3">
        From our own visit tracking (not Meta's). Full breakdown for all traffic on the{' '}
        <a href="/admin/usage" className="text-accent hover:underline">Usage</a> page.
      </p>
    </div>
  )
}

function FunnelChart({ stages, title = 'Funnel: impressions to a completed registration' }) {
  if (!stages?.length) return null
  const top = stages[0]?.value || 0
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-3">
        {title}
      </div>
      <div className="space-y-2.5">
        {stages.map((s, i) => {
          const widthPct = top ? Math.max(2, (s.value / top) * 100) : 0
          const fillOpacity = 0.3 + 0.7 * (top ? s.value / top : 0)
          const dropSevere = i > 0 && s.pct_of_prev < 20 && (stages[i - 1]?.value || 0) >= 2
          return (
            <div key={s.key}>
              {i > 0 && (
                <div className={`font-mono text-[9px] pl-1 mb-1 ${dropSevere ? 'text-red-400' : 'text-pb-faintest'}`}>
                  &darr; {fmtPct(s.pct_of_prev)} continued from &ldquo;{stages[i - 1].label}&rdquo;
                </div>
              )}
              <div className="flex items-center gap-3">
                <div className="w-40 sm:w-52 shrink-0 text-xs text-pb-text truncate" title={s.label}>{s.label}</div>
                <div className="flex-1 h-5 bg-pb-surface2 rounded overflow-hidden">
                  <div
                    className="h-full bg-pb-accent rounded"
                    style={{ width: `${widthPct}%`, opacity: fillOpacity }}
                  />
                </div>
                <div className="w-16 shrink-0 text-right font-mono text-xs text-pb-text">{fmtNum(s.value)}</div>
                <div className="w-14 shrink-0 text-right font-mono text-[10px] text-pb-faint">{fmtPct(s.pct_of_top)}</div>
              </div>
              {s.note && (
                <div data-testid="funnel-note" className="pl-1 mt-1 font-mono text-[9px] text-pb-faintest">{s.note}</div>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-3 mt-1.5 font-mono text-[9px] text-pb-faintest">
        <div className="w-40 sm:w-52 shrink-0" />
        <div className="flex-1" />
        <div className="w-16 shrink-0 text-right">count</div>
        <div className="w-14 shrink-0 text-right">of top</div>
      </div>
    </div>
  )
}

function RangePicker({ value, onChange }) {
  return (
    <div className="inline-flex rounded border border-pb-hairline overflow-hidden">
      {TREND_RANGES.map((r) => (
        <button
          key={r.days}
          onClick={() => onChange(r.days)}
          className={`px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide2 ${
            value === r.days ? 'bg-pb-accent text-white' : 'text-pb-dim hover:bg-pb-surface2'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

// The markers every time-series chart carries, shared by both chart kinds so
// the two can't disagree about what a reader is looking at:
//
//   • a dashed line on each deliberate campaign change. A chart that plots
//     straight through the 8 Sep restructure invites a reading it can't
//     support — a 40% drop printed over a deliberate 40% budget cut.
//   • a shaded band over the trailing 7 days. Meta attributes a conversion to
//     the date of the CLICK across a 7-day window, so those days always
//     under-report and fill in afterwards. They are drawn, not hidden — they
//     are real, just not finished.
// RETURNS AN ARRAY, NEVER A FRAGMENT, and that is not a style preference.
// Recharts finds its reference lines and areas by walking `React.Children` of
// the chart and reading each child's `type`. React.Children flattens an ARRAY
// but treats a Fragment as ONE opaque child, so a fragment-wrapped marker is
// silently dropped: the chart renders perfectly, with no error, and simply has
// no marker on it. Found by running the browser suite, which reported zero
// marker lines against code that reads as though it draws them.
function chartMarkers({ data, annotations, provisionalFrom }) {
  const dates = (data || []).map((d) => d.date)
  const marks = (annotations || []).filter((a) => dates.includes(a.date))
  const firstProvisional = provisionalFrom ? dates.find((d) => d >= provisionalFrom) : null
  const lastDate = dates[dates.length - 1]
  const out = []
  // Pushed first so the band paints underneath the series rather than over it.
  if (firstProvisional && lastDate && firstProvisional !== lastDate) {
    out.push(
      <ReferenceArea
        key="provisional"
        x1={firstProvisional}
        x2={lastDate}
        fill="var(--pb-faint, #64748b)"
        fillOpacity={0.14}
        strokeOpacity={0}
        ifOverflow="extendDomain"
      />
    )
  }
  for (const a of marks) {
    out.push(
      <ReferenceLine
        key={a.date}
        x={a.date}
        stroke="#f59e0b"
        strokeDasharray="4 3"
        strokeWidth={1.5}
        ifOverflow="extendDomain"
        label={{ value: '▼', position: 'top', fill: '#f59e0b', fontSize: 9 }}
      />
    )
  }
  return out
}

function TrendChart({ title, data, dataKey, kind = 'line', color = '#3b82f6', money,
                      annotations, provisionalFrom }) {
  const markers = chartMarkers({ data, annotations, provisionalFrom })
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">{title}</div>
      <div style={{ width: '100%', height: 170 }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">No data yet.</div>
        ) : kind === 'bar' ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip money={money} />} />
              {markers}
              <Bar dataKey={dataKey} name={title} fill={color} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip money={money} />} />
              {markers}
              <Line type="monotone" dataKey={dataKey} name={title} stroke={color} strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

// The key under the trend charts. Only drawn for the markers actually on
// screen, so a campaign with no recorded changes gets no legend it can't use.
function ChartLegend({ annotations, days, provisionalDays }) {
  if (!days.length) return null
  const shown = (annotations || []).filter((a) => a.date >= days[0] && a.date <= days[days.length - 1])
  return (
    <div className="font-mono text-[9px] text-pb-faintest mt-2 space-y-1">
      {shown.map((a) => (
        <p key={a.date}>
          <span className="text-amber-400">▼ {fmtDay(a.date)} — {a.label}.</span>{' '}
          {a.detail}
        </p>
      ))}
      {provisionalDays > 0 && (
        <p>
          <span className="inline-block w-2.5 h-2 align-middle mr-1" style={{ background: 'var(--pb-faint, #64748b)', opacity: 0.25 }} />
          The shaded last {provisionalDays} days are still settling — Meta attributes a conversion to the
          date of the click over a {provisionalDays}-day window, so recent figures only ever go up.
          Nothing on this page raises an alert off them.
        </p>
      )}
    </div>
  )
}

function AdTrendMini({ adId, days, annotations }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setErr('')
    api.metaAdsAdHistory(adId, days)
      .then((d) => { if (alive) setRows(d.days || []) })
      .catch((e) => { if (alive) setErr(e.message || "Could not load this ad's trend.") })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [adId, days])

  if (loading) return <p className="text-xs text-pb-faint px-1 py-2">Loading trend&hellip;</p>
  if (err) return <p className="text-xs text-red-400 px-1 py-2">{err}</p>
  // An ad that has ended, or one paused before it ever spent, legitimately has
  // no daily rows in this window. Say so rather than drawing an empty chart.
  if (rows.length === 0) return <p className="text-xs text-pb-faint px-1 py-2">No daily history recorded for this ad in the last {days} days.</p>

  const provisionalFrom = rows.find((d) => d.provisional)?.date || null
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
      <TrendChart title="Daily spend" data={rows} dataKey="spend" kind="bar" color="var(--pb-accent)" money={new Set(['spend'])} annotations={annotations} provisionalFrom={provisionalFrom} />
      <TrendChart title="Daily link CTR" data={rows} dataKey="link_ctr" kind="line" color="#3b82f6" annotations={annotations} provisionalFrom={provisionalFrom} />
    </div>
  )
}

function AdCard({ ad, maxCostPerLpv, selected, onSelect, trendDays, annotations }) {
  const style = AD_STATUS_STYLE[ad.status] || AD_STATUS_STYLE.on_track
  const stream = streamStyle(ad.stream)
  const paused = ad.status === 'paused'
  const barPct = ad.cost_per_lpv && maxCostPerLpv ? Math.min(100, (ad.cost_per_lpv / maxCostPerLpv) * 100) : 0
  const barColor = paused ? 'bg-slate-500' : ad.status === 'winner' ? 'bg-emerald-500' : ad.status === 'laggard' ? 'bg-red-500' : 'bg-pb-accent'

  return (
    <div className={`pb-card border overflow-hidden ${selected ? 'border-pb-accent' : 'border-pb-hairline'} ${paused ? 'opacity-70' : ''}`}>
      <button onClick={onSelect} className="w-full text-left p-3.5 hover:bg-pb-surface2/40">
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="text-sm font-medium text-pb-text">{ad.name}</div>
          <div className="shrink-0 flex items-center gap-1">
            {/* Which of the two products this ad sells — the split every
                result figure on this page turns on. */}
            <span
              className={`px-1.5 py-0.5 rounded-full border text-[9px] font-mono uppercase ${stream.chip}`}
              title={ad.destination ? `Lands on ${ad.destination}` : undefined}
            >
              {ad.stream}
            </span>
            <span className={`px-1.5 py-0.5 rounded-full border text-[9px] font-mono uppercase ${style.cls}`}>
              {style.label}
            </span>
          </div>
        </div>
        {ad.ends_on && (
          <p className="font-mono text-[9px] text-pb-faintest mb-1.5">
            Runs to {fmtDay(ad.ends_on)} &mdash; a dated event, so it stops being relevant after that.
          </p>
        )}
        <p className="text-xs text-pb-dim mb-2.5 leading-relaxed">{ad.note}</p>
        <div className="grid grid-cols-3 gap-x-3 gap-y-1 font-mono text-[10px] text-pb-faint mb-2">
          <div>Spend <span className="text-pb-text">{fmtMoney(ad.spend)}</span></div>
          <div>Link CTR <span className="text-pb-text">{fmtPct(ad.link_ctr)}</span></div>
          <div>LPVs <span className="text-pb-text">{fmtNum(ad.landing_page_views)}</span></div>
          <div>Cost/LPV <span className="text-pb-text">{ad.cost_per_lpv != null ? fmtMoney(ad.cost_per_lpv) : '–'}</span></div>
          <div>Leads <span className="text-pb-text">{fmtNum(ad.leads)}</span></div>
          <div>Cost/Lead <span className="text-pb-text">{ad.cost_per_lead != null ? fmtMoney(ad.cost_per_lead) : '–'}</span></div>
        </div>
        {ad.cost_per_lpv != null && (
          <div className="h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
            <div className={`h-full ${barColor}`} style={{ width: `${Math.max(4, barPct)}%` }} />
          </div>
        )}
        <div className="font-mono text-[9px] text-pb-faintest mt-2">
          {selected ? 'Hide trend over time' : 'Click for trend over time'}
        </div>
      </button>
      {selected && (
        <div className="border-t pb-hairline px-3.5 pb-3.5">
          <AdTrendMini adId={ad.ad_id} days={trendDays} annotations={annotations} />
        </div>
      )}
    </div>
  )
}

// One conversion stream's headline: what it produced, what each one cost, and
// what it spent to do it. NEVER a shared total with the other stream — the two
// results are different things at different prices and adding them together
// produces a number that describes neither.
// Why a since-the-change cost per result is being withheld, in the words a
// reader can act on. Silence with no reason reads as a bug; a number we can't
// stand behind is worse than either.
const WITHHELD_COPY = {
  partial_window: 'not enough daily history held yet to measure this',
  no_results_yet: 'no results since the change yet',
  no_spend_yet: 'no spend since the change yet',
}

// The stretch since the last deliberate change, measured on its own.
//
// LIFETIME AND SINCE-THE-CHANGE ARE DIFFERENT QUESTIONS, and for the trial they
// give very different answers: its lifetime spend is mostly the campaign that
// ran before the restructure, while the webinar has no pre-change history at
// all. Reading one stream's lifetime cost against the other's is comparing two
// campaigns, so both are shown and each says which it is.
function SinceChange({ since }) {
  if (!since) return null
  const cpr = since.cost_per_result
  const reason = WITHHELD_COPY[since.withheld_reason]
  return (
    <div
      data-testid="stream-since-change"
      className="mt-2 pt-2 border-t pb-hairline-t"
    >
      <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">
        Since the {fmtDay(since.since)} change
      </div>
      <div className="flex items-baseline gap-2 mt-0.5">
        <div data-testid="stream-since-cpr" className="font-display text-lg text-pb-text">
          {cpr != null ? fmtMoney(cpr) : <span className="text-pb-faintest text-sm">&mdash;</span>}
        </div>
        <div className="font-mono text-[10px] text-pb-dim">
          {cpr != null
            ? <>each &middot; {fmtNum(since.results)} from {fmtMoney(since.spend)}</>
            : <span className="text-pb-faintest">{reason || 'not measurable yet'}</span>}
        </div>
      </div>
      {cpr == null && since.spend > 0 && (
        <div className="font-mono text-[9px] text-pb-faintest mt-0.5">
          {fmtMoney(since.spend)} spent, {fmtNum(since.results)} result{since.results === 1 ? '' : 's'} so far.
        </div>
      )}
      {since.provisional && (
        <div data-testid="stream-since-provisional" className="font-mono text-[9px] text-amber-300/80 mt-1 leading-relaxed">
          Provisional. Meta credits a conversion to the day of the click and back-fills for
          7 days, so results here are still arriving — the spend is settled, the cost per
          result is a ceiling that will come down.
        </div>
      )}
    </div>
  )
}

function StreamCard({ stream, children }) {
  const style = streamStyle(stream.stream)
  const ended = stream.ended
  const since = stream.since_change
  return (
    <div
      data-testid={`stream-card-${stream.stream}`}
      className="pb-card px-3.5 py-3 border-l-2"
      style={{ borderLeftColor: style.accent }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{stream.label}</div>
        <span
          className={`shrink-0 px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase ${style.chip}`}
          title={`Pixel content_category: ${stream.content_category}`}
        >
          {stream.content_category}
        </span>
      </div>
      <div className="flex items-baseline gap-2 mt-0.5">
        <div data-testid="stream-results" className="font-display text-2xl text-pb-text">{fmtNum(stream.results)}</div>
        <div data-testid="stream-cpr" className="font-mono text-[11px] text-pb-dim">
          {stream.cost_per_result != null
            ? <>{fmtMoney(stream.cost_per_result)} each{since ? ' all time' : ''}</>
            : <span className="text-pb-faintest">no cost per result yet</span>}
        </div>
      </div>
      <div className="font-mono text-[9px] text-pb-faintest mt-1">
        {fmtMoney(stream.spend)} spent {since ? 'all time ' : ''}on {stream.ad_count} ad{stream.ad_count === 1 ? '' : 's'}
        {ended
          ? <> &middot; <span className="text-pb-faint">finished {fmtDay(stream.ends_on)}</span></>
          : stream.active_ad_count === 0
            ? <> &middot; <span className="text-pb-faint">none live</span></>
            : ''}
      </div>
      {stream.stream === 'webinar' && stream.unattributed_results > 0 && (
        <div className="font-mono text-[9px] text-amber-300/80 mt-1 leading-relaxed">
          +{stream.unattributed_results} more registered carrying no campaign tag. The ad&rsquo;s own body
          text has a plain link with no UTMs on it, so some genuinely ad-driven registrations arrive
          untagged. The real cost per result sits somewhere below {fmtMoney(stream.cost_per_result)}.
        </div>
      )}
      {!stream.carries_value && (
        <div className="font-mono text-[9px] text-pb-faintest mt-1">
          Carries no value — excluded from revenue and ROAS.
        </div>
      )}
      <SinceChange since={since} />
      {children}
    </div>
  )
}

// Per-creative results keyed on utm_content, the identifier that outlives the
// ad it was built on, so a creative can be compared across a rebuild in Ads
// Manager and across campaigns. Each row keeps its two result counts apart.
//
// Converted and ROAS are joined in from the signups report by the same tag, so
// the table says which creative produces PAYING clubs, not just sign-ups. ROAS
// is paid clubs x the trial's value over the creative's own spend, so a
// creative that has not converted anyone yet reads 0.00x, not a dash.
function CreativeTable({ creatives, ads, signupRows, unit }) {
  const rows = (creatives || []).filter((c) => c.spend > 0 || c.results > 0)
  if (!rows.length) return null
  const convertedMap = Array.isArray(signupRows) ? convertedByCreative(signupRows) : null
  const unmapped = unmappedAds(ads)
  const unmappedSpend = unmapped.reduce((n, a) => n + (a.spend || 0), 0)
  return (
    <div data-testid="creative-table" className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-3">
        Creative performance (by utm_content)
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
              <th className="px-2 py-2">Creative</th>
              <th className="px-2 py-2">Sells</th>
              <th className="px-2 py-2 text-right" title="Meta-reported">Spend</th>
              <th className="px-2 py-2 text-right" title="Meta-reported">LPVs</th>
              <th className="px-2 py-2 text-right" title="Our tracking">Trial signups</th>
              <th className="px-2 py-2 text-right" title="Our tracking">Webinar regs</th>
              <th className="px-2 py-2 text-right" title="Spend divided by this creative's own results">Cost / result</th>
              <th className="px-2 py-2 text-right" title="Our tracking: attributed clubs that now hold a paid module">Converted</th>
              <th className="px-2 py-2 text-right" title={`Converted x A$${unit} over this creative's own spend`}>ROAS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const style = streamStyle(c.stream)
              const converted = convertedMap ? (convertedMap[creativeKey(c.utm_content)] || 0) : null
              const roas = converted != null && c.spend > 0 ? (converted * unit) / c.spend : null
              return (
                <tr data-testid="creative-row" key={c.utm_content} className="border-b pb-hairline last:border-0 hover:bg-pb-surface2/40">
                  <td className="px-2 py-2 text-pb-text font-medium whitespace-nowrap">
                    {c.utm_content}
                    {c.ad_name && <div className="font-mono text-[9px] text-pb-faintest">{c.ad_name}</div>}
                  </td>
                  <td className="px-2 py-2">
                    <span className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase ${style.chip}`}>
                      {c.stream}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right text-pb-dim font-mono whitespace-nowrap">{fmtMoney(c.spend)}</td>
                  <td className="px-2 py-2 text-right text-pb-dim font-mono">{fmtNum(c.landing_page_views)}</td>
                  <td className="px-2 py-2 text-right font-mono text-pb-text">{c.trial_signups || '–'}</td>
                  <td className="px-2 py-2 text-right font-mono text-pb-text">{c.webinar_registrations || '–'}</td>
                  <td className="px-2 py-2 text-right font-mono text-pb-text whitespace-nowrap">
                    {c.cost_per_result != null ? fmtMoney(c.cost_per_result) : '–'}
                  </td>
                  <td data-testid="creative-converted" className="px-2 py-2 text-right font-mono text-pb-text">
                    {converted == null ? '–' : converted > 0 ? <span className="text-emerald-400">{converted}</span> : 0}
                  </td>
                  <td data-testid="creative-roas" className="px-2 py-2 text-right font-mono text-pb-text whitespace-nowrap">
                    {roas == null ? '–' : `${roas.toFixed(2)}x`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {unmapped.length > 0 && (
        <p data-testid="unmapped-ads" className="font-mono text-[9px] text-amber-300/80 mt-3 leading-relaxed">
          {unmapped.length} ad{unmapped.length === 1 ? '' : 's'} ({fmtMoney(unmappedSpend)} spent) ha{unmapped.length === 1 ? 's' : 've'} no
          utm_content on record: {unmapped.map((a) => a.name).join(', ')}. Their spend sits in the
          &ldquo;{NO_TAG}&rdquo; row, and their signups file under whatever tag the ad&rsquo;s URL carries,
          so neither Converted nor ROAS can be read per ad until each ad&rsquo;s tag is added to AD_DESTINATIONS.
        </p>
      )}
      <p className="font-mono text-[9px] text-pb-faintest mt-3">
        Spend and LPVs are Meta-reported, per ad, mapped to the creative tag on its destination URL. The result
        columns are our tracking, counted from the tag on the registration itself, and kept apart because a
        trial signup and a webinar registration are not the same result. &ldquo;Cost / result&rdquo; divides
        a creative&rsquo;s own spend by its own results, so compare within a stream rather than across.
        Converted counts clubs that now hold a paid module, and ROAS values each at A${unit} (the trial&rsquo;s
        value; webinar registrations are never valued).
      </p>
    </div>
  )
}

export default function SuperMetaAds() {
  const [summary, setSummary] = useState(null)
  const [tokenHealth, setTokenHealth] = useState(null)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const [adjustments, setAdjustments] = useState([])
  const [adjNote, setAdjNote] = useState('')
  const [adjusting, setAdjusting] = useState(false)
  const [showAdjLog, setShowAdjLog] = useState(false)

  const [onsite, setOnsite] = useState(null)
  const [adSignups, setAdSignups] = useState(null)
  const [registrationFunnel, setRegistrationFunnel] = useState(null)
  const [selectedClubs, setSelectedClubs] = useState(null)
  const [searchedClubs, setSearchedClubs] = useState(null)
  const [busySelectionKey, setBusySelectionKey] = useState('')
  // One period and one scope for every on-site panel below the money. It opens on ALL traffic
  // for the last 7 days (a list going back to July is not a follow-up list); "This campaign"
  // narrows it to the selected campaign's visitors.
  const [period, setPeriod] = useState(7)
  const [scope, setScope] = useState('all')
  const [panelsNonce, setPanelsNonce] = useState(0)

  const [trendDays, setTrendDays] = useState(14)
  const [selectedAdId, setSelectedAdId] = useState(null)
  const [showAllInsights, setShowAllInsights] = useState(false)
  const [listsFailed, setListsFailed] = useState(false)
  const [showCharts, setShowCharts] = useState(false)

  const [campaigns, setCampaigns] = useState([])
  const [activeCampaignId, setActiveCampaignId] = useState('')
  const [switchingCampaign, setSwitchingCampaign] = useState(false)

  const [editingSince, setEditingSince] = useState(false)
  const [sinceInput, setSinceInput] = useState('')
  const [savingSince, setSavingSince] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.metaAdsSummary()
      .then((s) => { setSummary(s); setError('') })
      .catch((e) => setError(e.message || 'Could not load the Meta Ads dashboard.'))
      .finally(() => setLoading(false))
    api.metaAdsLeadAdjustments().then((d) => setAdjustments(d.adjustments || [])).catch(() => {})
    api.metaAdsAdSignups().then(setAdSignups).catch(() => {})
    setPanelsNonce((n) => n + 1)   // the funnel, club list and traffic card re-read for the new campaign / cutoff
    api.metaAdsCampaigns()
      .then((d) => { setCampaigns(d.campaigns || []); setActiveCampaignId(d.active_campaign_id || '') })
      .catch(() => {})
    api.metaAdsTokenHealth().then(setTokenHealth).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  // The funnel, the club list and the traffic card for the chosen period and scope. A response
  // that arrives after the person has already moved on is dropped (`live`), so a slow 30-day
  // answer cannot overwrite the 7-day one on screen.
  useEffect(() => {
    let live = true
    setListsFailed(false)
    const fail = () => { if (live) setListsFailed(true) }
    api.metaAdsRegistrationFunnel(Math.min(period, 90), scope).then((d) => { if (live) setRegistrationFunnel(d.funnel || []) }).catch(() => {})
    api.metaAdsSelectedClubs(period, scope).then((d) => { if (live) setSelectedClubs(d) }).catch(fail)
    api.metaAdsSearchedClubs(period, scope).then((d) => { if (live) setSearchedClubs(d) }).catch(fail)
    api.metaAdsOnsite(Math.min(period, 365), scope).then((d) => { if (live) setOnsite(d) }).catch(() => {})
    return () => { live = false }
  }, [period, scope, panelsNonce])

  // Hide/unhide is keyed on the normalised club name and shared by both lists, so refresh both.
  const toggleSelection = useCallback((c, call) => {
    setBusySelectionKey(c.key || c.name)
    call(c.key || c.name, period, scope)
      .then(setSelectedClubs)
      .then(() => api.metaAdsSearchedClubs(period, scope).then(setSearchedClubs))
      .catch(() => {})
      .finally(() => setBusySelectionKey(''))
  }, [period, scope])
  const hideSelection = useCallback((c) => toggleSelection(c, api.metaAdsHideSelection), [toggleSelection])
  const unhideSelection = useCallback((c) => toggleSelection(c, api.metaAdsUnhideSelection), [toggleSelection])

  useEffect(() => {
    setHistoryLoading(true)
    api.metaAdsHistory(trendDays)
      .then((h) => setHistory(h.days || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [trendDays])

  const adjustLeads = async (delta) => {
    setAdjusting(true)
    setError('')
    try {
      const data = await api.metaAdsAdjustLeads(delta, adjNote)
      setSummary(data)
      setAdjNote('')
      const d = await api.metaAdsLeadAdjustments()
      setAdjustments(d.adjustments || [])
    } catch (e) {
      setError(e.message || 'Could not adjust the lead count.')
    } finally {
      setAdjusting(false)
    }
  }

  const refresh = async () => {
    setRefreshing(true)
    setError('')
    try {
      const data = await api.metaAdsRefresh()
      if (data.error) {
        setError(data.error.message)
      } else {
        setSummary(data)
        const h = await api.metaAdsHistory(trendDays)
        setHistory(h.days || [])
      }
      // The pull just exercised the token, and /refresh busts the server-side
      // health cache — re-read it so a just-replaced token flips the chip.
      api.metaAdsTokenHealth().then(setTokenHealth).catch(() => {})
    } catch (e) {
      setError(e.message || 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }

  const changeCampaign = async (cid) => {
    if (!cid || cid === activeCampaignId) return
    setSwitchingCampaign(true)
    setError('')
    try {
      await api.metaAdsSetCampaign(cid)
      setActiveCampaignId(cid)
      load()  // re-pull every panel for the newly-selected campaign
    } catch (e) {
      setError(e.message || 'Could not switch campaign.')
    } finally {
      setSwitchingCampaign(false)
    }
  }

  // "Counting since" cutoff — excludes data from before it out of the
  // on-site funnel/table numbers and Meta's own campaign insights. The
  // "Free trial registrations" KPI is deliberately never affected by it
  // (see meta_ads.get_registration_count).
  const openSinceEditor = () => {
    setSinceInput(isoToPerthInput(summary?.counting_since) || '2026-07-28T06:00')
    setEditingSince(true)
  }

  const applySince = async () => {
    if (!sinceInput) return
    setSavingSince(true)
    setError('')
    try {
      await api.metaAdsSetCountingSince(`${sinceInput}:00+08:00`)
      setEditingSince(false)
      load()  // re-pull every panel now the cutoff has changed
      const h = await api.metaAdsHistory(trendDays)
      setHistory(h.days || [])
    } catch (e) {
      setError(e.message || 'Could not set the counting-since cutoff.')
    } finally {
      setSavingSince(false)
    }
  }

  const clearSince = async () => {
    setSavingSince(true)
    setError('')
    try {
      await api.metaAdsSetCountingSince(null)
      setEditingSince(false)
      load()
      const h = await api.metaAdsHistory(trendDays)
      setHistory(h.days || [])
    } catch (e) {
      setError(e.message || 'Could not clear the counting-since cutoff.')
    } finally {
      setSavingSince(false)
    }
  }

  const budget = summary?.campaign_budget ?? DEFAULT_BUDGET
  const lengthDays = summary?.campaign_length_days ?? DEFAULT_LENGTH_DAYS

  const header = (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {/* Not "Trials Campaign" any more: since 8-9 Sep this one campaign runs
            a free-trial ad and a webinar ad side by side, and naming it after
            one of them is how a reader starts assuming every number below is
            about that one. */}
        <h1 className="text-xl font-semibold text-pb-text">Meta Ads HQ</h1>
        <div className="flex flex-wrap items-center gap-2 mt-1">
          {campaigns.length > 0 ? (
            <select
              value={activeCampaignId}
              onChange={(e) => changeCampaign(e.target.value)}
              disabled={switchingCampaign}
              title="Which campaign the dashboard tracks (saved to the platform — no redeploy)"
              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm text-pb-text max-w-[340px] disabled:opacity-50"
            >
              {!campaigns.some((c) => c.id === activeCampaignId) && activeCampaignId && (
                <option value={activeCampaignId}>{activeCampaignId} (current)</option>
              )}
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.effective_status && c.effective_status !== 'ACTIVE'
                    ? ` — ${c.effective_status.toLowerCase().replace(/_/g, ' ')}` : ''}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-sm text-pb-dim">{activeCampaignId || 'campaign'}</span>
          )}
          <span className="text-sm text-pb-dim">&middot; ~{lengthDays} days from launch</span>
          {switchingCampaign && <span className="font-mono text-[10px] text-pb-faint">switching&hellip;</span>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <TokenPill health={tokenHealth} />
        <span className="font-mono text-[10px] text-pb-faint">
          Last updated {fmtTime(summary?.last_updated)}
        </span>
        <button
          onClick={refresh}
          disabled={refreshing || loading}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border border-pb-accent text-pb-text hover:bg-pb-accent/10 disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh now'}
        </button>
      </div>
    </div>
  )

  if (loading) {
    return (
      <AdminLayout>
        <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
          {header}
          <p className="text-sm text-pb-dim">Loading…</p>
        </div>
      </AdminLayout>
    )
  }

  const tokenConfigured = summary?.token_configured
  const campaign = summary?.campaign
  const insights = summary?.insights || []
  const ads = summary?.ads || []
  const streams = summary?.streams || []
  const unattributedSpend = summary?.unattributed_spend || 0
  const undatedTrialResults = summary?.undated_trial_results || 0
  const annotations = summary?.annotations || []
  const provisionalDays = summary?.attribution_window_days || 0
  // The first date inside Meta's click-attribution window, computed from the
  // series itself so the shaded band lines up with real rows rather than with
  // a date the chart may not hold.
  const provisionalFrom = history.find((d) => d.provisional)?.date || null
  const trialStream = streams.find((s) => s.stream === 'trial')
  const webinarStream = streams.find((s) => s.stream === 'webinar')
  const signupRows = adSignups ? adSignups.rows : null
  const kpis = computeKpis({
    trialStream, webinarStream, campaign, signupRows, countingSince: summary?.counting_since,
    unattributedSpend: summary?.unattributed_spend || 0,
  })
  const hasFunnel = !!registrationFunnel?.some((st) => st.value > 0)
  // A stream that has never had an ad or a result is not shown: a webinar card reading 0 on a
  // trial-only campaign is noise.
  const activeStreams = streams.filter((st) => st.stream === 'trial' || (st.ad_count || 0) > 0 || (st.results || 0) > 0)
  const maxCostPerLpv = ads.reduce((m, a) => (a.cost_per_lpv != null && a.cost_per_lpv > m ? a.cost_per_lpv : m), 0)

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        {header}

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        <CountingSince
          countingSince={summary?.counting_since}
          editing={editingSince}
          input={sinceInput}
          setInput={setSinceInput}
          saving={savingSince}
          onOpen={openSinceEditor}
          onApply={applySince}
          onCancel={() => setEditingSince(false)}
          onClear={clearSince}
        />

        {!tokenConfigured ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-text font-medium">Meta access token not configured</p>
            <p className="text-sm text-pb-dim mt-2 max-w-xl mx-auto">
              Add <code className="font-mono text-xs bg-pb-surface2 px-1.5 py-0.5 rounded">META_ACCESS_TOKEN</code> (and
              the other <code className="font-mono text-xs bg-pb-surface2 px-1.5 py-0.5 rounded">META_*</code> vars) to
              the backend&rsquo;s environment, then come back and click Refresh now. See the setup runbook for how to
              generate a system-user token with <code className="font-mono text-xs">ads_read</code> +{' '}
              <code className="font-mono text-xs">read_insights</code>.
            </p>
          </div>
        ) : !campaign ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">
              Campaign is live but hasn&rsquo;t spent yet &mdash; check back after it starts delivering, or click
              Refresh now.
            </p>
          </div>
        ) : (
          <>
            <KpiStrip kpis={kpis} signupsLoaded={!!adSignups} />

            {/* A campaign restarted under the same Meta id counts only what happened from
                its restart date. Said out loud, with what it left out, so "1 trial signup"
                never hides the earlier ones silently. */}
            {summary?.counts_from && (
              <p data-testid="counts-from-note" className="font-mono text-[9px] text-pb-faint -mt-1 mb-3 leading-relaxed">
                Restarted: counting registrations and spend from {fmtTime(summary.counts_from)}.
                {(summary.registrations_excluded?.before_restart || 0) > 0 && (
                  <> {summary.registrations_excluded.before_restart} earlier registration{summary.registrations_excluded.before_restart === 1 ? '' : 's'} from this campaign
                  {summary.registrations_excluded.before_restart === 1 ? ' is' : ' are'} from before the restart and not counted.</>
                )}
                {(summary.registrations_excluded?.other_traffic || 0) > 0 && (
                  <span data-testid="other-traffic-note"> {summary.registrations_excluded.other_traffic} other registration{summary.registrations_excluded.other_traffic === 1 ? '' : 's'} finished
                  since then from outside this campaign (organic, our email or another campaign). {summary.registrations_excluded.other_traffic === 1 ? 'It is' : 'They are'} real but
                  not in Free trial signups or cost per trial, because no ad brought {summary.registrations_excluded.other_traffic === 1 ? 'it' : 'them'}. The club list below says where each came from.</span>
                )}
                {(summary.registrations_excluded?.undated || 0) > 0 && (
                  <> {summary.registrations_excluded.undated} more carry no signup date, so cannot be placed, and are not counted.</>
                )}
              </p>
            )}

            {/* Headlines — short, worst-first, only fires on something worth
                a glance. Capped so this stays a quick scan, not a report. */}
            {insights.length > 0 && (
              <div className="mb-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                  Headlines
                </div>
                <div className="space-y-1.5">
                  {(showAllInsights ? insights : insights.slice(0, 3)).map((insight, i) => (
                    <InsightRow key={i} insight={insight} />
                  ))}
                </div>
                {insights.length > 3 && (
                  <button
                    onClick={() => setShowAllInsights((s) => !s)}
                    className="mt-1.5 font-mono text-[9px] text-pb-faint hover:underline"
                  >
                    {showAllInsights ? 'Show fewer' : `+${insights.length - 3} more`}
                  </button>
                )}
              </div>
            )}

            {/* Campaign-wide delivery, all Meta-reported. Whole-campaign figures
                (money out, and how far it reached), so no stream split. Spend
                itself is the first tile of the strip above; this keeps the
                plan it is measured against. Every RESULT figure is split by
                stream, in the cards below. */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-2">
              <Stat
                label="Budget used (Meta-reported)"
                value={`${Math.min(100, Math.round((campaign.spend / budget) * 100))}%`}
                hint={`${fmtMoney(campaign.spend)} of ${fmtMoney(budget)} plan`}
              />
              <Stat
                label="Cost per LPV (Meta-reported, both)"
                value={campaign.cost_per_lpv != null ? fmtMoney(campaign.cost_per_lpv) : '–'}
              />
              <Stat
                label="Landing page views (Meta-reported)"
                value={fmtNum(campaign.landing_page_views)}
                hint={`${fmtNum(campaign.link_clicks)} link clicks`}
              />
            </div>

            {/* THE SPLIT. One campaign now sells two things — a free trial and
                a webinar seat — and both landing pages fire the SAME pixel
                event, told apart only by content_category. There is deliberately
                no combined "registrations" total anywhere on this page: the two
                cost very different amounts and only one of them is worth money. */}
            {activeStreams.length > 0 && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-1 items-start">
                <div className="space-y-2">
                {activeStreams.map((s) => (
                  <StreamCard key={s.stream} stream={s}>
                    {s.stream === 'trial' && (
                      <>
                        <div className="font-mono text-[9px] text-pb-faintest mt-1">
                          {fmtNum(campaign.registrations)} tracked
                          {campaign.leads_adjustment ? `, ${campaign.leads_adjustment > 0 ? '+' : ''}${campaign.leads_adjustment} manual` : ''}
                          {' '}&middot;{' '}
                          <span title="Meta counts a Lead the moment someone picks a club, not when they finish registering, and it can shift on its own. The figure above is our own database's count of real completed registrations.">
                            {fmtNum(campaign.leads)} Meta-reported leads
                          </span>
                        </div>
                        <div className="flex items-center gap-1 mt-1.5">
                          <button
                            onClick={() => adjustLeads(-1)}
                            disabled={adjusting}
                            title="Remove one trial registration (e.g. spam or duplicate)"
                            className="w-5 h-5 flex items-center justify-center rounded border border-pb-hairline text-pb-dim hover:bg-pb-surface2 disabled:opacity-50 font-mono text-xs leading-none"
                          >
                            &minus;
                          </button>
                          <button
                            onClick={() => adjustLeads(1)}
                            disabled={adjusting}
                            title="Add one trial registration our own tracking didn't capture (e.g. a manually onboarded club)"
                            className="w-5 h-5 flex items-center justify-center rounded border border-pb-hairline text-pb-dim hover:bg-pb-surface2 disabled:opacity-50 font-mono text-xs leading-none"
                          >
                            +
                          </button>
                          <button
                            onClick={() => setShowAdjLog((s2) => !s2)}
                            className="font-mono text-[9px] text-pb-faint hover:underline ml-1"
                          >
                            {showAdjLog ? 'hide log' : `log (${adjustments.length})`}
                          </button>
                        </div>
                      </>
                    )}
                  </StreamCard>
                ))}
                </div>
                <div className="space-y-3">
                  {activeStreams.filter((st) => (st.impressions || 0) > 0).map((st) => (
                    <FunnelChart key={st.stream} stages={st.funnel} title={`${st.label}: impressions to a registration`} />
                  ))}
                </div>
              </div>
            )}

            {undatedTrialResults > 0 && (
              <p data-testid="undated-trial-results" className="font-mono text-[9px] text-amber-300/80 mb-1">
                {fmtNum(undatedTrialResults)} attributed trial signup{undatedTrialResults === 1 ? '' : 's'} carry
                no recorded signup date, so {undatedTrialResults === 1 ? 'it counts' : 'they count'} in the
                all-time figure and in neither since-the-change one. The since figure is a floor.
              </p>
            )}

            {unattributedSpend > 0.5 && (
              <p data-testid="unattributed-spend" className="font-mono text-[9px] text-amber-300/80 mb-1">
                {fmtMoney(unattributedSpend)} of campaign spend isn&rsquo;t accounted for by any ad row
                (a deleted ad, most likely). It sits in neither cost-per-result figure above rather than
                being quietly charged to one of them.
              </p>
            )}

            {unattributedSpend < -0.5 && (
              <p data-testid="stale-spend" className="font-mono text-[9px] text-amber-300/80 mb-1">
                The ads listed add up to {fmtMoney(-unattributedSpend)} more than the campaign&rsquo;s own spend, so some ad rows are older
                than the last refresh. Cost per trial and ROAS are withheld until they agree. Press Refresh now.
              </p>
            )}

            {showAdjLog && (
              <div className="pb-card p-3 mb-2">
                <input
                  type="text"
                  value={adjNote}
                  onChange={(e) => setAdjNote(e.target.value)}
                  placeholder="Optional note for the next +/- (e.g. duplicate, spam, converted to a paying club)"
                  className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 font-mono text-[11px] text-pb-text mb-2"
                />
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1">Adjustment history</div>
                {adjustments.length === 0 ? (
                  <p className="text-xs text-pb-faint">No manual adjustments yet.</p>
                ) : (
                  <ul className="space-y-1 max-h-40 overflow-y-auto">
                    {adjustments.map((a, i) => (
                      <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                        <span className={a.delta > 0 ? 'text-emerald-400 font-mono' : 'text-red-400 font-mono'}>
                          {a.delta > 0 ? `+${a.delta}` : a.delta}
                        </span>
                        {a.counted === false && (
                          <span data-testid="adjustment-not-counted" className="font-mono text-[9px] text-pb-faintest">
                            before the restart, not counted
                          </span>
                        )}
                        <span className="font-mono text-[10px] text-pb-faintest">{fmtTime(a.created_at)}</span>
                        {a.created_by_email && <span className="text-pb-faint">{a.created_by_email}</span>}
                        {a.note && <span className="text-pb-dim">{a.note}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="w-full bg-pb-surface2 rounded-full h-1.5 mb-4 overflow-hidden">
              <div
                className="h-full bg-pb-accent"
                style={{ width: `${Math.min(100, (campaign.spend / budget) * 100)}%` }}
              />
            </div>

            {/* WHERE IT'S COMING FROM, for the SELECTED campaign. One period and one scope drive the
                club list, the wizard funnel and the traffic card. The list leads and is never behind
                a tab or a toggle: it is the follow-up list (it was lost once to a tab). */}
            <div data-testid="demand-section" className="mt-6 mb-3">
              <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                Where it&rsquo;s coming from
              </div>
              <PeriodScopeBar period={period} onPeriod={setPeriod} scope={scope} onScope={setScope} countsFrom={summary?.counts_from} />
            </div>

            <ClubsPanel
              selected={selectedClubs}
              searched={searchedClubs}
              scope={scope}
              onScope={setScope}
              period={period}
              failed={listsFailed}
              busyKey={busySelectionKey}
              onFlag={hideSelection}
              onRestore={unhideSelection}
            />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4 items-start">
              {hasFunnel ? (
                <FunnelChart
                  stages={registrationFunnel}
                  title={`Registration wizard: where visitors drop off (${periodLabel(period)})`}
                />
              ) : (
                <div data-testid="wizard-empty" className="pb-card p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                    Registration wizard: where visitors drop off ({periodLabel(period)})
                  </div>
                  <p className="text-xs text-pb-faint">No one reached the wizard {scope === 'campaign' ? 'from this campaign ' : ''}in this period.</p>
                </div>
              )}
              <TrafficCard data={onsite} scope={scope} period={period} />
            </div>

            {/* The ads: the table says which creative produces paying clubs, the
                cards beneath carry each ad's Winner / Laggard status and the
                click-to-drill-down trend. */}
            <CreativeTable creatives={summary?.creatives} ads={ads} signupRows={signupRows} unit={kpis.unit} />

            <div className="mb-4">
              <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                Ad-by-ad performance
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {ads.map((ad) => (
                  <AdCard
                    key={ad.ad_id}
                    ad={ad}
                    maxCostPerLpv={maxCostPerLpv}
                    selected={selectedAdId === ad.ad_id}
                    onSelect={() => setSelectedAdId((cur) => (cur === ad.ad_id ? null : ad.ad_id))}
                    trendDays={trendDays}
                    annotations={annotations}
                  />
                ))}
              </div>
            </div>

            {/* Trend charts — true daily figures (not cumulative-to-date), each on its own axis */}
            <div className="mb-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
                  Daily trends {showCharts && historyLoading && <span className="text-pb-faintest normal-case">loading&hellip;</span>}
                </div>
                <div className="flex items-center gap-2">
                  {showCharts && <RangePicker value={trendDays} onChange={setTrendDays} />}
                  <button
                    data-testid="toggle-charts"
                    onClick={() => setShowCharts((v) => !v)}
                    className="px-2.5 py-1 rounded border border-pb-hairline font-mono text-[10px] uppercase tracking-wide2 text-pb-dim hover:bg-pb-surface2"
                  >
                    {showCharts ? 'Hide daily charts' : 'Show daily charts'}
                  </button>
                </div>
              </div>
              {showCharts && (<>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <TrendChart title="Spend per day" data={history} dataKey="spend" kind="bar" color="var(--pb-accent)" money={new Set(['spend'])} annotations={annotations} provisionalFrom={provisionalFrom} />
                <TrendChart title="Link CTR per day" data={history} dataKey="link_ctr" kind="line" color="#3b82f6" annotations={annotations} provisionalFrom={provisionalFrom} />
                <TrendChart title="Cost per LPV per day" data={history} dataKey="cost_per_lpv" kind="line" color="#f59e0b" money={new Set(['cost_per_lpv'])} annotations={annotations} provisionalFrom={provisionalFrom} />
                <TrendChart title="Leads per day (Meta-reported)" data={history} dataKey="leads" kind="bar" color="#a78bfa" annotations={annotations} provisionalFrom={provisionalFrom} />
              </div>
              <ChartLegend
                annotations={annotations}
                days={history.map((d) => d.date)}
                provisionalDays={provisionalDays}
              />
              </>)}
            </div>

            {/* Ad-driven self-serve signups joined to their engagement
                score — which ads produced clubs that actually use the thing. */}
            {adSignups && (
              <div className="pb-card p-4 mb-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                  <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
                    Signups: the attributable-revenue record (our tracking)
                  </div>
                  {/* Divided by the TRIAL stream's own spend, not the campaign's.
                      Using campaign spend here charged every trial signup with
                      the webinar ad's spend too, which quietly overstated it by
                      whatever the webinar was costing that week. */}
                  {adSignups.rows.length > 0 && trialStream?.spend > 0 && (
                    <span className="font-mono text-[10px] text-pb-faintest">
                      {fmtMoney(trialStream.spend / Math.max(1, adSignups.rows.filter((r) => r.signup_source === 'self_serve_ad').length))} per ad-driven signup, at trial-ad spend only
                    </span>
                  )}
                </div>

                {adSignups.rows.length === 0 ? (
                  <p className="text-xs text-pb-faint">
                    No self-serve signups yet. Once the /trial page is live and the campaign is running,
                    every club that registers itself lands here with its ad attribution and
                    engagement score.
                  </p>
                ) : (
                  <>
                    {adSignups.campaigns.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-3">
                        {adSignups.campaigns.map((c) => (
                          <span key={c.campaign} className="px-2 py-1 rounded border pb-hairline font-mono text-[10px] text-pb-dim">
                            <span className="text-pb-text">{c.campaign || '(untagged)'}</span>
                            {' '}&middot; {fmtNum(c.signups)} signup{c.signups === 1 ? '' : 's'}
                            {c.converted > 0 && <span className="text-emerald-400"> &middot; {c.converted} paid</span>}
                            {c.avg_engagement != null && <> &middot; avg score {c.avg_engagement}</>}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                            <th className="px-2 py-2">Club</th>
                            <th className="px-2 py-2">Signed up</th>
                            <th className="px-2 py-2">Source</th>
                            <th className="px-2 py-2">Campaign / creative</th>
                            <th className="px-2 py-2">Modules</th>
                            <th className="px-2 py-2">Paid?</th>
                            <th className="px-2 py-2 text-right">Lead score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {adSignups.rows.map((r) => (
                            <tr key={r.org_id} className="border-b pb-hairline last:border-0 hover:bg-pb-surface2/40">
                              <td className="px-2 py-2 text-pb-text font-medium whitespace-nowrap">
                                {r.slug ? <a href={`/${r.slug}`} className="hover:underline">{r.name}</a> : r.name}
                              </td>
                              <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{r.signed_up_at ? fmtTime(r.signed_up_at) : '–'}</td>
                              <td className="px-2 py-2">
                                <span className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase ${
                                  r.signup_source === 'self_serve_ad'
                                    ? 'border-violet-500/40 text-violet-300 bg-violet-500/10'
                                    : 'border-pb-hairline text-pb-faint'
                                }`}>
                                  {r.signup_source === 'self_serve_ad' ? (r.click_source || 'ad') : 'organic'}
                                </span>
                              </td>
                              <td className="px-2 py-2 text-pb-dim">
                                {[r.utm_campaign, r.utm_content].filter(Boolean).join(' / ') || '–'}
                              </td>
                              <td className="px-2 py-2 text-pb-dim">
                                {r.converted_to_paid
                                  ? <span className="text-emerald-400">{r.paid_modules.length} paid</span>
                                  : `${r.trial_modules.length} on trial`}
                              </td>
                              <td data-testid="signup-paid" className="px-2 py-2">
                                {r.converted_to_paid ? (
                                  <>
                                    <span className="inline-block px-1.5 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 font-mono text-[9px] uppercase">
                                      Paid
                                    </span>
                                    {r.paid_modules.length > 0 && (
                                      <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{r.paid_modules.join(', ')}</div>
                                    )}
                                  </>
                                ) : (
                                  <span className="inline-block px-1.5 py-0.5 rounded-full border border-pb-hairline text-pb-faint font-mono text-[9px] uppercase">
                                    Trial
                                  </span>
                                )}
                              </td>
                              <td className="px-2 py-2 text-right">
                                {r.engagement_score == null ? (
                                  <span className="font-mono text-[10px] text-pb-faintest">not yet scored</span>
                                ) : (
                                  <span className={`font-display font-bold ${
                                    r.engagement_score >= 70 ? 'text-red-400'
                                      : r.engagement_score >= 40 ? 'text-amber-400'
                                      : 'text-pb-dim'
                                  }`}>
                                    {r.engagement_score}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="font-mono text-[9px] text-pb-faintest mt-3">
                      Lead score is the cached engagement score (rescored nightly, or on demand from
                      the Club Directory). A club with no directory row yet shows
                      &ldquo;not yet scored&rdquo;.
                    </p>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
