/* BetterIQ — Selection analysis (the live availability → best-XI loop).
   BetterSelect holds the saved XI; the backend analysis gives us the eligible
   pool (picked XI ∪ in-form promotes ∪ rested). Players set availability here
   and BetterIQ rebuilds the best-available XI client-side (role template +
   value), shows the coming-in/dropping-out diff, live balance and warnings,
   then writes the chosen XI back to BetterSelect (PUT /selection/{id}). */
import { useState, useEffect, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty, Search, Card, Note, PageIntro, Initials, a2 } from './ui'

/* ── role + scoring model (ported from the design, fed by real fields) ─────── */
const ROLE_CHIP = {
  BAT: { c: 'var(--pb-dim)', bg: 'var(--pb-surface2)' },
  WKT: { c: 'var(--pb-amber)', bg: 'color-mix(in srgb, var(--pb-amber) 14%, transparent)' },
  ALL: { c: 'var(--pb-accent)', bg: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' },
  BWL: { c: 'var(--iq-c-wkts)', bg: 'color-mix(in srgb, var(--iq-c-wkts) 14%, transparent)' },
}
function RoleChip({ role }) {
  const c = ROLE_CHIP[role] || ROLE_CHIP.BAT
  return <span className="iq-mono font-bold" style={{ fontSize: 9.5, padding: '2px 6px', borderRadius: 5, color: c.c, background: c.bg }}>{role}</span>
}

const sumInts = (arr) => (arr || []).reduce((a, b) => a + (parseInt(b, 10) || 0), 0)
const AVAIL_SEED = { AVAILABLE: 'available', MAYBE: 'maybe', UNAVAILABLE: 'unavailable' }

// Map a backend analysis player → the shape buildXI works on.
function mapPlayer(p, src) {
  const bowlType = p.bowling_type || ''
  const hasBowl = !!p.bowling_type || (p.recent_wickets || []).some(w => w > 0)
  const form = p.recent_avg != null ? Number(p.recent_avg) : 0
  let role = 'BAT'
  if (p.is_wicket_keeper) role = 'WKT'
  else if (hasBowl && form >= 20) role = 'ALL'
  else if (hasBowl) role = 'BWL'
  return {
    id: p.player_id, name: p.name, role, spin: /SPIN/i.test(bowlType), hasBowl,
    order: p.batting_order != null ? p.batting_order : 99,
    form, runs: sumInts(p.recent_scores), wkts: sumInts(p.recent_wickets),
    bowl_avg: p.vs_opponent?.bowl?.avg ?? 30,
    is_wicket_keeper: !!p.is_wicket_keeper, is_captain: !!p.is_captain,
    availability: p.availability, flags: p.flags, play_updown: p.play_updown,
    autofill_eligible: p.autofill_eligible !== false,
    saved: src === 'pool' ? !!p.in_xi : (src === 'xi' && p.batting_order != null),
  }
}
function buildPool(data) {
  // Prefer the full eligible pool (every selectable squad player) so we can build
  // a best XI from an empty fixture and show all availability. Fall back to the
  // saved XI ∪ promotes ∪ rest for older backends.
  if (data.pool?.length) return data.pool.map(p => mapPlayer(p, 'pool'))
  const seen = new Map()
  const add = (p, src) => { if (p?.player_id && !seen.has(p.player_id)) seen.set(p.player_id, mapPlayer(p, src)) }
  ;(data.players || []).forEach(p => add(p, 'xi'))
  ;(data.promote || []).forEach(p => add(p, 'promote'))
  ;(data.rest || []).forEach(p => add(p, 'rest'))
  return [...seen.values()]
}

const batScore = p => (p.form || 0) * 1.4 + (p.runs || 0) * 0.15
const bowlScore = p => (p.wkts || 0) * 2.0 + (40 - (p.bowl_avg || 40))
const allScore = p => batScore(p) * 0.55 + bowlScore(p) * 0.7
const keeperScore = p => (p.form || 0) + (p.runs || 0) * 0.1
const valueOf = p => p.role === 'WKT' ? keeperScore(p) : p.role === 'BWL' ? bowlScore(p) : p.role === 'ALL' ? allScore(p) : batScore(p)

function buildXI(pool, availMap, includeMaybe, size = 11) {
  const avail = pool.filter(p => availMap[p.id] === 'available' || (includeMaybe && availMap[p.id] === 'maybe'))
  const used = new Set()
  const take = (arr, n) => { const out = []; for (const p of arr) { if (out.length >= n) break; if (!used.has(p.id)) { out.push(p); used.add(p.id) } } return out }
  const byRole = r => avail.filter(p => p.role === r)
  const keeper = take(byRole('WKT').sort((a, b) => keeperScore(b) - keeperScore(a)), 1)
  const bowlers = take(byRole('BWL').sort((a, b) => bowlScore(b) - bowlScore(a)), 3)
  const allr = take(byRole('ALL').sort((a, b) => allScore(b) - allScore(a)), 2)
  const bats = take(byRole('BAT').sort((a, b) => batScore(b) - batScore(a)), 5)
  let xi = [...keeper, ...bowlers, ...allr, ...bats]
  if (xi.length < size) { const rest = avail.filter(p => !used.has(p.id)).sort((a, b) => valueOf(b) - valueOf(a)); xi = xi.concat(take(rest, size - xi.length)) }
  return xi.sort((a, b) => (a.order - b.order) || (batScore(b) - batScore(a)))
}
function balanceOf(xi) {
  const bowlers = xi.filter(p => p.role === 'BWL')
  const allr = xi.filter(p => p.role === 'ALL')
  const contrib = [...bowlers, ...allr]
  const spin = contrib.filter(p => p.spin).length
  return {
    bats: xi.filter(p => p.role === 'BAT').length, allr: allr.length, bowlers: bowlers.length + allr.length,
    keeper: xi.filter(p => p.role === 'WKT').length, pace: contrib.length - spin, spin,
    openers: xi.filter(p => p.order <= 2).length, depth: xi.filter(p => ['BAT', 'WKT', 'ALL'].includes(p.role)).length,
  }
}

/* ── availability tri-state ────────────────────────────────────────────────── */
const AV_OPTS = [{ k: 'available', label: 'In', c: 'var(--pb-brand)' }, { k: 'maybe', label: '?', c: 'var(--pb-amber)' }, { k: 'unavailable', label: 'Out', c: 'var(--pb-red)' }]
function AvailToggle({ value, onChange }) {
  return (
    <div className="inline-flex p-[2px] gap-0.5 shrink-0" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 8 }}>
      {AV_OPTS.map(o => {
        const on = o.k === value
        return (
          <button key={o.k} onClick={() => onChange(o.k)} className="iq-mono font-bold transition"
            style={{ fontSize: 10.5, padding: '3px 9px', borderRadius: 6, color: on ? o.c : 'var(--pb-faint)', background: on ? `color-mix(in srgb, ${o.c} 16%, transparent)` : 'transparent' }}>{o.label}</button>
        )
      })}
    </div>
  )
}

/* ── picker ────────────────────────────────────────────────────────────────── */
function LineupPicker({ rows, onPick }) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? rows.filter(r => (r.opponent_name || '').toLowerCase().includes(t) || (r.team_name || '').toLowerCase().includes(t)) : rows
  }, [q, rows])
  if (!rows.length) return <Empty>No saved lineups yet. Pick a team for a fixture in BetterSelect, then analyse it here.</Empty>
  return (
    <div>
      <Search value={q} onChange={setQ} placeholder="Search fixtures…" className="mb-4 max-w-sm" />
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map(r => (
          <button key={r.fixture_id} onClick={() => onPick(r.fixture_id)} className="iq-card text-left p-4 transition hover:brightness-110">
            <div className="font-semibold truncate">{r.team_name || 'Team'} <span className="text-pb-faint">vs</span> {r.opponent_name || 'TBC'}</div>
            <div className="text-pb-faintest text-[11px] mt-1 flex flex-wrap gap-x-2 iq-mono">
              {r.played_on && <span>{r.played_on}</span>}
              {r.home_away && <span className="uppercase">{r.home_away}</span>}
              {r.lineup_count > 0 ? <span>· {r.lineup_count} picked</span> : <span style={{ color: 'var(--pb-accent)' }}>· needs selecting</span>}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── interactive analysis ──────────────────────────────────────────────────── */
function Analysis({ data, fixtureId, onNavigate }) {
  const pool = useMemo(() => buildPool(data), [data])
  const poolById = useMemo(() => Object.fromEntries(pool.map(p => [p.id, p])), [pool])
  const size = data.team_size_target || 11

  const [availMap, setAvailMap] = useState(() => Object.fromEntries(pool.map(p => [p.id, AVAIL_SEED[p.availability] || 'maybe'])))
  const [includeMaybe, setIncludeMaybe] = useState(false)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendErr, setSendErr] = useState('')
  const [poolQ, setPoolQ] = useState('')

  // Saved XI (from BetterSelect) and the auto-suggested best-available XI.
  const savedIds = useMemo(() => new Set(pool.filter(p => p.saved).map(p => p.id)), [pool])
  const suggested = useMemo(() => buildXI(pool, availMap, includeMaybe, size), [pool, availMap, includeMaybe, size])
  const suggestedIds = useMemo(() => suggested.map(p => p.id), [suggested])

  // Working XI the user edits: seed from the saved lineup, or the suggested best
  // XI when nothing's saved — so an empty fixture still opens with a full side to
  // tweak (helps pick a team from scratch). State is keyed by fixture (remount).
  const [xiIds, setXiIds] = useState(() => {
    const saved = pool.filter(p => p.saved).sort((a, b) => a.order - b.order).map(p => p.id)
    if (saved.length) return saved
    const seed = Object.fromEntries(pool.map(p => [p.id, AVAIL_SEED[p.availability] || 'maybe']))
    return buildXI(pool, seed, false, size).map(p => p.id)
  })

  const inXi = useMemo(() => new Set(xiIds), [xiIds])
  const xi = useMemo(() => xiIds.map(id => poolById[id]).filter(Boolean), [xiIds, poolById])
  const bal = useMemo(() => balanceOf(xi), [xi])
  const counts = useMemo(() => { const c = { available: 0, maybe: 0, unavailable: 0 }; Object.values(availMap).forEach(v => { c[v] = (c[v] || 0) + 1 }); return c }, [availMap])

  const addToXi = (id) => { setXiIds(ids => ids.includes(id) ? ids : [...ids, id]); setSent(false) }
  const removeFromXi = (id) => { setXiIds(ids => ids.filter(x => x !== id)); setSent(false) }
  const toggleXi = (id) => (inXi.has(id) ? removeFromXi(id) : addToXi(id))
  const useSuggested = () => { setXiIds(suggestedIds); setSent(false) }
  const setAvail = (id, v) => { setAvailMap(m => ({ ...m, [id]: v })); setSent(false); setSendErr('') }

  const comingIn = xi.filter(p => !savedIds.has(p.id))
  const droppingOut = pool.filter(p => p.saved && !inXi.has(p.id)).map(p => ({ ...p, reason: availMap[p.id] === 'unavailable' ? 'Unavailable' : 'Left out' }))
  const suggestedNotPicked = suggested.filter(p => !inXi.has(p.id))
  const fromScratch = savedIds.size === 0

  const warnings = []
  if (xi.length !== size) warnings.push({ tone: xi.length < size ? 'amber' : 'red', text: xi.length < size ? `${size - xi.length} spot${size - xi.length > 1 ? 's' : ''} still open (${xi.length}/${size}).` : `${xi.length}/${size} picked — one too many.` })
  if (bal.keeper < 1) warnings.push({ tone: 'red', text: 'No specialist keeper in the XI — name one or accept a part-timer behind the stumps.' })
  if (bal.bowlers < 4) warnings.push({ tone: 'amber', text: `Only ${bal.bowlers} bowling options — a thin attack if a bowler has an off day.` })
  if (bal.spin < 1) warnings.push({ tone: 'amber', text: 'No frontline spinner in the XI.' })
  if (bal.openers < 2) warnings.push({ tone: 'red', text: 'Fewer than two recognised top-order openers.' })
  if (bal.depth < 7) warnings.push({ tone: 'amber', text: 'Batting depth thins below 7 — a top-order collapse would expose the tail.' })

  const send = async () => {
    setSending(true); setSendErr('')
    try {
      const byId = Object.fromEntries((data.players || []).map(p => [p.player_id, p]))
      const payload = xiIds.map((id, i) => {
        const p = poolById[id] || {}
        return { player_id: id, batting_order: i + 1, is_captain: !!byId[id]?.is_captain, is_wicket_keeper: p.is_wicket_keeper || !!byId[id]?.is_wicket_keeper }
      })
      await api.bsSetSelection(fixtureId, payload)
      setSent(true)
    } catch (e) {
      setSendErr(e?.message || 'Could not send to BetterSelect (needs selection permission).')
    } finally { setSending(false) }
  }

  const fx = data.fixture || {}
  const balChips = [
    { label: 'Specialist bats', value: bal.bats, warn: bal.bats < 4 },
    { label: 'All-rounders', value: bal.allr },
    { label: 'Bowling options', value: bal.bowlers, warn: bal.bowlers < 4 },
    { label: 'Pace / spin', value: `${bal.pace} / ${bal.spin}`, warn: bal.spin < 1 },
    { label: 'Keeper', value: bal.keeper, warn: bal.keeper < 1 },
    { label: 'Openers', value: bal.openers, warn: bal.openers < 2 },
  ]

  const pq = poolQ.trim().toLowerCase()
  const poolView = pq ? pool.filter(p => p.name.toLowerCase().includes(pq)) : pool

  return (
    <div className="iq-fade">
      <PageIntro>Pick the XI here — start from the saved BetterSelect team or, on an empty fixture, from the suggested best available side. Add or remove anyone, set availability to re-rank, then send the XI back to BetterSelect.</PageIntro>

      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-2"><div className="iq-eyebrow whitespace-nowrap" style={{ color: 'var(--pb-accent)' }}>Selection</div><Tag tone="accent">Synced · BetterSelect</Tag></div>
          <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(22px,2.6vw,30px)' }}>{fx.team_name || 'Team'} vs {fx.opponent_name || 'TBC'}</h2>
          <div className="text-pb-faint text-[12px] mt-1 iq-mono flex flex-wrap gap-x-2">{[fx.played_on, fx.home_away, fx.grade_name, fx.venue].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="flex items-center gap-2.5">
          <Btn variant="ghost" sm icon="fixtures" onClick={() => onNavigate('/admin/betteriq/preview' + (fixtureId ? `?fixture=${fixtureId}` : ''))}>Match preview</Btn>
          <Btn variant="primary" sm icon={sent ? 'check' : 'share'} disabled={sending} onClick={send}>{sent ? 'Sent to BetterSelect' : sending ? 'Sending…' : 'Send XI to BetterSelect'}</Btn>
        </div>
      </div>
      {sendErr && <div className="mb-4 text-[12.5px] flex items-center gap-2" style={{ color: 'var(--pb-red)' }}><Icon name="info" size={14} />{sendErr}</div>}

      <Card accent eyebrow="the read" title={fromScratch ? 'Suggested XI from scratch' : (comingIn.length === 0 && droppingOut.length === 0 ? 'Saved XI is the best available' : `${comingIn.length + droppingOut.length} change${comingIn.length + droppingOut.length > 1 ? 's' : ''} vs saved`)} className="mb-5">
        <div className="iq-display font-bold leading-snug" style={{ fontSize: 'clamp(15px,1.8vw,20px)', letterSpacing: '-0.01em', maxWidth: 760 }}>
          {fromScratch
            ? 'No XI was saved, so we loaded the best available side from your eligible squad. Add or remove players, set availability, then send it to BetterSelect.'
            : (comingIn.length || droppingOut.length)
              ? `${droppingOut.map(p => p.name).join(' & ') || '—'} out; ${comingIn.map(p => p.name).join(' & ') || '—'} in.`
              : (data.verdict || 'Everyone available is already in the best side — no changes needed.')}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px] items-start">
        <Card eyebrow={`your XI · ${xi.length}/${size}`} title="Selected XI"
          right={<Btn variant="soft" sm icon="refresh" onClick={useSuggested}>Use suggested XI</Btn>}>
          {xi.length === 0 ? <Empty>No players picked. Use the suggested XI, or add players from availability below.</Empty> : (
            <div className="space-y-0.5">
              {xi.map((p, i) => {
                const isNew = !savedIds.has(p.id)
                const out = availMap[p.id] === 'unavailable'
                return (
                  <div key={p.id} className="group flex items-center gap-3 px-2 py-2.5" style={{ borderRadius: 9, background: isNew ? 'color-mix(in srgb, var(--pb-brand) 9%, transparent)' : i % 2 ? 'transparent' : 'var(--pb-surface2)' }}>
                    <span className="iq-num text-pb-faint w-5 text-center shrink-0">{i + 1}</span>
                    <Initials name={p.name} size={32} tone={isNew ? 'accent' : undefined} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2"><span className="font-semibold text-[14px] whitespace-nowrap">{p.name}</span>{isNew && <Tag tone="win">In</Tag>}{out && <Tag tone="red">Out</Tag>}{p.spin && <span className="iq-mono text-pb-faint" style={{ fontSize: 9 }}>spin</span>}</div>
                      <div className="text-pb-faint text-[11.5px] iq-num">form {a2(p.form)}</div>
                    </div>
                    <RoleChip role={p.role} />
                    <span className="iq-num text-pb-dim text-[12.5px] w-10 text-right shrink-0 hidden sm:block">{p.role === 'BWL' ? `${p.wkts}w` : `${p.runs}r`}</span>
                    <button onClick={() => removeFromXi(p.id)} title="Remove from XI" className="shrink-0 transition" style={{ color: 'var(--pb-faint)', padding: 4, borderRadius: 6 }}
                      onMouseEnter={e => { e.currentTarget.style.color = 'var(--pb-red)'; e.currentTarget.style.background = 'color-mix(in srgb, var(--pb-red) 12%, transparent)' }}
                      onMouseLeave={e => { e.currentTarget.style.color = 'var(--pb-faint)'; e.currentTarget.style.background = 'transparent' }}>
                      <Icon name="close" size={14} />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
          {suggestedNotPicked.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2" style={{ color: 'var(--pb-accent)' }}>Suggested to add</div>
              <div className="flex flex-wrap gap-2">
                {suggestedNotPicked.map(p => (
                  <button key={p.id} onClick={() => addToXi(p.id)}
                    className="iq-display font-semibold text-[12px] inline-flex items-center gap-1.5 transition" style={{ padding: '5px 10px', borderRadius: 8, background: 'var(--pb-surface2)', color: 'var(--pb-dim)', border: '1px solid var(--pb-hairline2)' }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--pb-accent)'; e.currentTarget.style.color = 'var(--pb-accent)' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--pb-hairline2)'; e.currentTarget.style.color = 'var(--pb-dim)' }}>
                    <span style={{ fontSize: 14, lineHeight: 1 }}>+</span>{p.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {droppingOut.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2" style={{ color: 'var(--pb-red)' }}>Dropped from the saved XI</div>
              {droppingOut.map(p => <div key={p.id} className="text-[13px] py-0.5">{p.name} <span className="text-pb-faint text-[11.5px]">· {p.reason}</span></div>)}
            </div>
          )}
        </Card>

        <div className="space-y-5">
          <Card eyebrow="composition" title="Balance">
            <div className="grid grid-cols-2 gap-2.5">
              {balChips.map(b => (
                <div key={b.label} className="px-3 py-2.5" style={{ background: 'var(--pb-surface2)', borderRadius: 10, border: `1px solid ${b.warn ? 'color-mix(in srgb, var(--pb-amber) 38%, transparent)' : 'var(--pb-hairline)'}` }}>
                  <div className="iq-headline iq-num" style={{ fontSize: 21, color: b.warn ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b.value}</div>
                  <div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>{b.label}</div>
                </div>
              ))}
            </div>
            {warnings.length === 0
              ? <div className="flex items-center gap-2 mt-3.5 text-[13px]" style={{ color: 'var(--pb-brand)' }}><Icon name="check" size={15} />Well balanced for this fixture.</div>
              : <div className="space-y-2 mt-3.5">{warnings.map((w, i) => <div key={i} className="flex gap-2 text-[12.5px] leading-snug"><Icon name="info" size={14} className="mt-0.5 shrink-0" style={{ color: w.tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)' }} /><span>{w.text}</span></div>)}</div>}
          </Card>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-9 mb-4">
        <h2 className="iq-display font-bold text-[19px]" style={{ letterSpacing: '-0.01em' }}>Squad availability <span className="text-pb-faint text-[14px] font-normal">({pool.length})</span></h2>
        <div className="flex items-center gap-3">
          <Search value={poolQ} onChange={setPoolQ} placeholder="Find a player…" className="max-w-[200px]" />
          <label className="flex items-center gap-2 text-[12.5px] text-pb-dim cursor-pointer select-none whitespace-nowrap">
            <input type="checkbox" checked={includeMaybe} onChange={e => setIncludeMaybe(e.target.checked)} style={{ accentColor: 'var(--pb-accent)', width: 15, height: 15 }} />
            Suggest "maybe" players
          </label>
        </div>
      </div>
      <Card>
        <div className="grid gap-x-8 gap-y-1 lg:grid-cols-2">
          {poolView.map(p => {
            const on = inXi.has(p.id)
            return (
              <div key={p.id} className="flex items-center gap-2.5 py-2" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
                <button onClick={() => toggleXi(p.id)} title={on ? 'Remove from XI' : 'Add to XI'}
                  className="iq-mono font-bold shrink-0 transition" style={{ fontSize: 9.5, width: 34, padding: '4px 0', textAlign: 'center', borderRadius: 7,
                    border: `1px solid ${on ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`,
                    color: on ? 'var(--pb-accent)' : 'var(--pb-faint)',
                    background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}>
                  {on ? '✓XI' : '+XI'}
                </button>
                <Initials name={p.name} size={30} tone={on ? 'accent' : undefined} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><span className="font-medium text-[13.5px] truncate">{p.name}</span>{p.play_updown && <span className="iq-mono text-pb-faintest" style={{ fontSize: 8.5 }}>{p.play_updown === 'up' ? '↑ up' : '↓ down'}</span>}</div>
                  <div className="text-pb-faint text-[11px] iq-num">form {a2(p.form)}{p.flags?.includes('dormant') ? ' · dormant' : ''}</div>
                </div>
                <RoleChip role={p.role} />
                <AvailToggle value={availMap[p.id]} onChange={v => setAvail(p.id, v)} />
              </div>
            )
          })}
          {poolView.length === 0 && <Empty className="py-2">No players match.</Empty>}
        </div>
        <Note>Every eligible squad player (incl. promotion / drop-down options) — availability is seeded from BetterSelect. "+XI" adds a player; availability re-ranks the suggested XI. "Send XI" writes your selected order back to BetterSelect.</Note>
      </Card>
    </div>
  )
}

/* ── main ──────────────────────────────────────────────────────────────────── */
export default function SelectionAnalysis() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [fixtureId, setFixtureId] = useState(searchParams.get('fixture') || null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => { api.iqSelectionLineups().then(setRows).catch(() => setRows([])) }, [])
  useEffect(() => {
    if (!fixtureId) { setData(null); return }
    let alive = true
    setData(null); setErr(false)
    api.iqSelectionAnalysis(fixtureId).then(d => { if (alive) setData(d) }).catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [fixtureId])

  const pick = (id) => { setFixtureId(id); setSearchParams({ fixture: id }, { replace: true }) }
  const clear = () => { setFixtureId(null); setData(null); setSearchParams({}, { replace: true }) }

  if (!fixtureId) {
    return (
      <IQLayout>
        <PageIntro>BetterSelect picks the team — BetterIQ checks the balance, rebuilds the best available side as availability changes, and justifies the pick. Choose a fixture with a saved lineup.</PageIntro>
        {rows === null ? <div className="iq-card p-5 iq-pulse text-pb-faint text-sm">Loading lineups…</div> : <LineupPicker rows={rows} onPick={pick} />}
      </IQLayout>
    )
  }

  return (
    <IQLayout actions={<Btn variant="ghost" sm icon="back" onClick={clear}>Change fixture</Btn>}>
      {data === null && !err && <div className="iq-card p-5 iq-pulse text-pb-faint text-sm">Analysing the XI…</div>}
      {err && <div className="iq-card p-5"><Empty>Couldn't load this lineup. It may have been removed — pick another fixture.</Empty></div>}
      {/* Even with nothing saved we can still help — the eligible pool lets us
          build a best XI from scratch. Only truly empty pools dead-end. */}
      {data && !(data.pool?.length || data.players?.length || data.promote?.length) && (
        <Card title={`${data.fixture?.team_name || 'Team'} vs ${data.fixture?.opponent_name || 'TBC'}`}>
          <Empty>No eligible players found for this fixture's grade.</Empty>
          <p className="text-pb-faint text-sm mt-2">Check the squad and player registrations in BetterSelect, then come back to build the XI.</p>
        </Card>
      )}
      {data && !!(data.pool?.length || data.players?.length || data.promote?.length) && (
        <Analysis key={fixtureId} data={data} fixtureId={fixtureId} onNavigate={(to) => navigate(to)} />
      )}
    </IQLayout>
  )
}
