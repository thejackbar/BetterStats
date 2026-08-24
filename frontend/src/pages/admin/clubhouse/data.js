import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { MODULE } from '../../../lib/modules'

// One roll-up for the whole BetterAdmin surface.
//
// Every count in the module — the sidebar badge, the Today row, the Accounts
// KPI, the "owes money" audience — is the same number computed once here. If
// issuing a shirt changes a balance, all of them move together. Nothing is
// denormalised: this fetches the raw lists and derives, so a screen can never
// disagree with the sidebar badge sitting next to it.
//
// The layout mounts on every screen in the module, so the fetch is cached at
// module level with a short TTL rather than repeated per navigation. A screen
// that mutates something calls `refresh()`.

const TTL_MS = 60_000
let _cache = null      // { at, data }
let _inflight = null

// Whole dollars stay whole; anything with cents shows both of them, so a stock
// figure never reads as "$6,840.5".
export const money = n => {
  const v = Number(n || 0)
  const dp = Number.isInteger(v) ? 0 : 2
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`
}

const ok = p => p.then(v => v).catch(() => null)

// Newest first, ignoring merged-away aliases — same rule the Fees screens use.
function newestSeason(seasons) {
  return (seasons || [])
    .filter(s => !s.alias_of)
    .sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))[0] || null
}

async function fetchAll(modules) {
  // Asset alerts are fetched unconditionally: the register is core since
  // migration 279, so a club with no paid module still has equipment coming due.
  const [seasons, merch, campaigns, assetAlerts] = await Promise.all([
    modules.fees ? ok(api.adminListSeasons()) : null,
    modules.merch ? ok(api.merchOverview()) : null,
    modules.comms ? ok(api.commsListCampaigns()) : null,
    ok(api.assetsAlerts()),
  ])

  const season = newestSeason(seasons)
  const fees = season ? await ok(api.feeListMembers(season.id)) : null

  return {
    season,
    fees: fees || null,
    merch: merch || null,
    campaigns: Array.isArray(campaigns) ? campaigns : campaigns?.campaigns || [],
    assetAlerts: assetAlerts || null,
  }
}

// Derived counters — the single definition of each number the UI shows.
export function deriveCounts(data) {
  const summary = data?.fees?.summary || {}
  const alerts = data?.merch?.alerts || {}
  const owing = Number(summary.non_financial || 0)
  const needsTier = Number(summary.needs_tier || 0)
  const reorder = (alerts.low_stock || []).length
  const expiring = (alerts.expiring || []).length
  // From the CORE asset register now, not the merch payload. `merch.alerts
  // .service_due` still rides on the wire as an empty list for one release, so
  // reading it here would silently report zero.
  const serviceDue = (data?.assetAlerts?.service_due || []).length
  const drafts = (data?.campaigns || []).filter(c => (c.status || '').toLowerCase() === 'draft').length
  return {
    owing,
    needsTier,
    owed: Number(summary.total_outstanding || 0),
    people: Number(summary.total_members || 0),
    reorder,
    expiring,
    serviceDue,
    kitOwed: Number(data?.merch?.outstanding_owed || 0),
    stockCost: Number(data?.merch?.stock_value_cost || 0),
    units: Number(data?.merch?.units_on_hand || 0),
    drafts,
    // What Today counts as "needs you" — the same rows it renders.
    needsYou: owing + reorder + expiring + serviceDue + drafts,
  }
}

export function useClubhouseData(modules) {
  const key = `${!!modules.fees}|${!!modules.merch}|${!!modules.comms}`
  const [state, setState] = useState(() => (_cache && Date.now() - _cache.at < TTL_MS ? _cache.data : null))
  const [loading, setLoading] = useState(!state)

  const run = useCallback((force = false) => {
    if (!force && _cache && Date.now() - _cache.at < TTL_MS) { setState(_cache.data); setLoading(false); return }
    if (force) { _cache = null; _inflight = null }
    if (!_inflight) {
      _inflight = fetchAll(modules).then(d => { _cache = { at: Date.now(), data: d }; _inflight = null; return d })
        .catch(() => { _inflight = null; return null })
    }
    setLoading(true)
    return _inflight.then(d => { if (d) setState(d); setLoading(false) })
    // `modules` is a fresh object each render; key covers what actually matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => { run() }, [run])

  return { data: state, counts: deriveCounts(state), loading, refresh: () => run(true) }
}

// Which of the umbrella's modules this club actually holds — the merged
// sidebar hides a whole group rather than showing tools that 402.
export function clubhouseModules(hasModule) {
  return {
    fees: hasModule(MODULE.FEES),
    comms: hasModule(MODULE.COMMS),
    merch: hasModule(MODULE.MERCH),
    crm: hasModule(MODULE.CRM),
  }
}
