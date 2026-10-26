// Transfers — Free / Bank / Cost tiles, an Out → In swap, a same-role shortlist
// to pick the replacement, then confirm. Several players can go out at once: the bank
// shows what the set returns less what the picks cost, and the server checks the budget
// over the whole set. The first transfer of the round is free; further ones cost the
// points hit.
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { StatTile, DISP, tintBg, mix, money, pts, Btn, Avatar, Field, ROLE_LABEL, ROLE_SHORT, ROLE_ORDER, GREEN, RED, AMBER, PriceTag, PriceArrow, MoverChips, byMover, moverEmpty } from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

// What selling a player returns: his price now. A rise since you bought him adds to
// your bank and a fall takes from it (the server sells at the same figure).
const sellValue = (purchase, current) => Math.round(Number(current ?? purchase ?? 0) * 10) / 10

// Players going out are matched to players coming in by role, in the order picked.
// An in-player with no open slot of his role is left out (`prune`).
function pairUp(outs, ins) {
  const used = new Set()
  return outs.map(o => {
    const t = ins.find(i => i.role === o.role && !used.has(i.player_id))
    if (t) used.add(t.player_id)
    return { out: o, tin: t || null }
  })
}
const prune = (outs, ins) => pairUp(outs, ins).map(x => x.tin).filter(Boolean)

// Sortable pool columns. Name runs A to Z first, the figures biggest first.
const SORTS = {
  name: { label: 'Player', get: p => p.name || '' },
  price: { label: 'Price', get: p => Number(p.price) || 0 },
  sel: { label: 'Sel', get: p => Number(p.selected_pct) || 0 },
  total: { label: 'Total', get: p => Number(p.total_points) || 0 },
}
// A picked sort wins; otherwise the mover chips order the list, else the default.
function arrange(list, move, sort, dflt) {
  const base = move === 'all' ? list.slice() : byMover(list.slice(), move)
  const s = sort || (move === 'all' ? dflt : null)
  if (!s) return base
  const get = SORTS[s.key].get
  const dir = s.dir === 'asc' ? 1 : -1
  return base.sort((a, b) => {
    const x = get(a), y = get(b)
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir || (a.name || '').localeCompare(b.name || '')
  })
}

export default function Transfers({ token, squad, pool, rules, round, onChange, flash, fail, nav, desktop }) {
  const [outs, setOuts] = useState([])                   // squad players being sold
  const [ins, setIns] = useState([])                     // pool players coming in
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')   // pool filter
  const [move, setMove] = useState('all')                // price movers: all | up | down
  const [sort, setSort] = useState(null)                 // { key, dir } once a column is picked
  const [step, setStep] = useState('sell')               // phone: sell | buy
  const [busy, setBusy] = useState(false)

  const poolById = useMemo(() => Object.fromEntries((pool || []).map(p => [p.player_id, p])), [pool])
  const free = squad?.free_transfers ?? 0
  const hit = rules?.transfer_hit ?? 4
  const locked = !!round?.locked
  // Transfers made after the round locked wait for it to be scored (see QueuedList).
  const queuedAll = squad?.queued_transfers || []
  const pendingQ = queuedAll.filter(q => q.status === 'pending')
  const cancelledQ = queuedAll.filter(q => q.status === 'cancelled')
  const queuedOut = new Set(pendingQ.map(q => q.out_player_id))
  const queuedIn = new Set(pendingQ.map(q => q.in_player_id))

  const pairs = pairUp(outs, ins)
  const openRoles = new Set(pairs.filter(x => !x.tin).map(x => x.out.role))
  const inIds = new Set(ins.map(p => p.player_id))

  const shortlist = useMemo(() => {
    if (!outs.length || !squad) return []
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    const roles = new Set(outs.map(o => o.role))
    const l = (pool || [])
      .filter(p => roles.has(p.role) && (roleFilter === 'all' || !roles.has(roleFilter) || p.role === roleFilter)
        && !have.has(p.player_id) && !queuedIn.has(p.player_id) && (!term || p.name.toLowerCase().includes(term)))
    return arrange(l, move, sort, { key: 'price', dir: 'desc' }).slice(0, 40)
  }, [outs, pool, squad, search, move, sort, roleFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!squad) return <Empty nav={nav} />

  const sellOf = (o) => sellValue(o.purchase_price, poolById[o.player_id]?.price ?? o.price ?? o.purchase_price)
  const bank = Number(squad.budget_remaining || 0)
  const sellTotal = outs.reduce((a, o) => a + sellOf(o), 0)
  const inTotal = ins.reduce((a, p) => a + Number(p.price), 0)
  // The bank as it will stand once everything picked goes through.
  const projected = Math.round((bank + sellTotal - inTotal) * 10) / 10
  const swapCount = Math.max(1, outs.length)
  const hitPts = free > 100 ? 0 : Math.max(0, swapCount - free) * hit
  const cost = locked ? 'queued' : hitPts === 0 ? 'free' : `${hitPts} pts`
  const lockMsg = locked
    ? `Round ${round?.number ?? ''} has locked, so your XI and captain are frozen until it's scored. A transfer you make now is queued: it happens once the round is scored, at the prices then, and counts for Round ${round?.next_number ?? 'next'}. If you can't afford it at those prices it is cancelled.`
    : null

  // While a round is locked the prices are about to move, so the bank is checked when the
  // transfers happen (and the server warns); otherwise the whole set has to fit now.
  const canConfirm = pairs.length > 0 && pairs.every(x => x.tin) && (locked || projected >= -1e-6)
    && pairs.every(x => !queuedOut.has(x.out.player_id) && !queuedIn.has(x.tin.player_id))
  const cancelQueued = async (id) => {
    setBusy(true)
    try { await api.fanCancelQueuedTransfer(token, id); flash('Queued transfer cancelled.'); await onChange() }
    catch (e) { fail(e) } finally { setBusy(false) }
  }

  const toggleOut = (p) => {
    if (queuedOut.has(p.player_id)) return
    const was = outs.some(o => o.player_id === p.player_id)
    const next = was ? outs.filter(o => o.player_id !== p.player_id) : [...outs, p]
    setOuts(next)
    setIns(prune(next, ins))
    // Keep the pool on a role the manager is replacing.
    if (!was && roleFilter !== 'all' && !next.some(o => o.role === roleFilter)) setRoleFilter(p.role)
  }
  const clearAll = () => { setOuts([]); setIns([]); setStep('sell') }
  const canPick = (p) => !outs.length ? false
    : inIds.has(p.player_id) || (openRoles.has(p.role) && projected - Number(p.price) >= -1e-6)
  const toggleIn = (p) => {
    if (inIds.has(p.player_id)) { setIns(ins.filter(x => x.player_id !== p.player_id)); return }
    if (!outs.length) { flash('Tap a player to sell first.'); return }
    if (!openRoles.has(p.role)) {
      flash(outs.some(o => o.role === p.role)
        ? `Every ${ROLE_LABEL[p.role].toLowerCase()} you are selling already has a replacement.`
        : 'Transfers are like-for-like by role.')
      return
    }
    if (projected - Number(p.price) < -1e-6) return
    setIns(prune(outs, [...ins, p]))
  }
  const effSort = sort || (move === 'all' ? { key: desktop ? 'total' : 'price', dir: 'desc' } : null)
  const toggleSort = (key) => setSort(effSort?.key === key
    ? { key, dir: effSort.dir === 'desc' ? 'asc' : 'desc' }
    : { key, dir: key === 'name' ? 'asc' : 'desc' })

  const confirm = async () => {
    setBusy(true)
    try {
      const n = pairs.length
      const r = await api.fanTransfers(token, pairs.map(x => ({ out_player_id: x.out.player_id, in_player_id: x.tin.player_id })))
      flash(r.queued
        ? (r.warning || (n > 1 ? `${n} transfers queued. They happen once Round ${r.after_round} is scored.` : `Queued. It happens once Round ${r.after_round} is scored.`))
        : `${n > 1 ? `${n} transfers done` : 'Transfer done'}.${r.hit ? ` ${r.hit} pt hit.` : ''}`)
      setOuts([]); setIns([]); setSearch(''); setStep('sell')
      await onChange()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  const bankColor = projected < -1e-6 ? RED : GREEN
  const confirmLabel = locked
    ? (pairs.length > 1 ? `Queue ${pairs.length} transfers` : 'Queue transfer')
    : (pairs.length > 1 ? `Confirm ${pairs.length} transfers` : 'Confirm transfer')

  if (desktop) {
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    const filtered = (pool || [])
      .filter(p => (roleFilter === 'all' || p.role === roleFilter) && (!term || p.name.toLowerCase().includes(term)))
    const table = arrange(filtered, move, sort, { key: 'total', dir: 'desc' })
    const COLS = '2fr 0.7fr 0.8fr 0.7fr 0.8fr 44px'
    const sortHead = (key, i) => {
      const on = effSort?.key === key
      return (
        <button key={key} onClick={() => toggleSort(key)} title={`Sort by ${SORTS[key].label.toLowerCase()}`} aria-label={`Sort by ${SORTS[key].label.toLowerCase()}`}
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: i === 0 ? 'left' : 'right', font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: on ? 'var(--accent-strong)' : 'var(--faint)' }}>
          {SORTS[key].label}{on ? (effSort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
        </button>
      )
    }
    return (
      <div style={{ background: 'var(--bg)', border: '1px solid var(--hairline)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--frame-shadow)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '15px 26px', background: 'linear-gradient(180deg,var(--grad-top),var(--bg))', borderBottom: '1px solid var(--hairline)' }}>
          <div style={{ font: `800 18px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>Transfers</div>
          <div style={{ display: 'flex', gap: 8, marginLeft: 14 }}>
            <BarChip label="Free" value={free > 100 ? '∞' : free} />
            <BarChip label="Bank" value={money(projected)} color={bankColor} note={outs.length ? `now ${money(bank)}` : null} />
            <BarChip label="Value" value={money(squad.value ?? 0)} />
            <BarChip label="Cost" value={cost === 'free' ? '0 pts' : cost} />
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <Btn disabled={!canConfirm || busy} onClick={confirm} style={{ padding: '9px 18px', fontSize: 13 }}>{busy ? 'Confirming…' : confirmLabel}</Btn>
          </div>
        </div>
        {lockMsg && <div style={{ padding: '10px 26px', font: `600 11.5px 'Hanken Grotesk'`, color: AMBER, background: mix(AMBER, 10) }}>{lockMsg}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr' }}>
          <div style={{ borderRight: '1px solid var(--hairline)', padding: '18px 20px' }}>
            <QueuedList items={pendingQ} cancelled={cancelledQ} onCancel={cancelQueued} busy={busy} />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)' }}>Your squad · tap to sell</div>
              {outs.length > 0 && <button onClick={clearAll} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Clear ({outs.length})</button>}
            </div>
            {!outs.length && <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '-4px 2px 4px' }}>Tap more than one player to sell several at once.</div>}
            {ROLE_ORDER.map(role => {
              const rows = squad.players.filter(p => p.role === role)
              if (!rows.length) return null
              return (
                <div key={role}>
                  <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', margin: '12px 2px 7px' }}>{ROLE_LABEL[role]}s</div>
                  {rows.map(p => {
                    const sel = outs.some(o => o.player_id === p.player_id)
                    const qd = queuedOut.has(p.player_id)
                    return (
                      <button key={p.player_id} aria-pressed={sel} onClick={qd ? undefined : () => toggleOut(p)} style={{
                        display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', padding: '8px 11px', marginBottom: 6, borderRadius: 11, cursor: 'pointer',
                        background: sel ? mix(RED, 10, 'var(--surface)') : 'var(--surface)', border: `1px solid ${sel ? mix(RED, 34) : 'var(--hairline)'}`,
                      }}>
                        <Avatar name={p.name} photoUrl={p.photo_url} size={30} />
                        <span style={{ flex: 1, minWidth: 0, font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
                        <span style={{ font: `600 11px ${DISP}`, color: 'var(--faint)' }} title={`Bought for ${money(p.purchase_price)}`}>{money(poolById[p.player_id]?.price ?? p.price ?? p.purchase_price)}<PriceArrow change={poolById[p.player_id]?.price_change ?? p.price_change} /></span>
                        <span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: qd ? AMBER : RED, border: `1px solid ${mix(qd ? AMBER : RED, 34)}`, padding: '3px 7px', borderRadius: 6 }}>{qd ? 'Queued' : sel ? 'Out' : 'Sell'}</span>
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
          <div style={{ padding: '18px 22px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)' }}>Player pool</div>
              <div style={{ display: 'flex', gap: 5, marginLeft: 6 }}>
                {[['all', 'All'], ['batter', 'BAT'], ['allrounder', 'AR'], ['keeper', 'WK'], ['bowler', 'BWL']].map(([k, l]) => {
                  const on = roleFilter === k
                  return <button key={k} onClick={() => setRoleFilter(k)} style={{ font: `${on ? 700 : 600} 10px 'Hanken Grotesk'`, color: on ? 'var(--ink)' : 'var(--dim)', background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', padding: '5px 10px', borderRadius: 7, border: 'none', cursor: 'pointer' }}>{l}</button>
                })}
              </div>
              <div style={{ marginLeft: 8 }}><MoverChips value={move} onChange={setMove} /></div>
              <div style={{ marginLeft: 'auto', width: 180 }}><Field placeholder="⌕ Search" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '7px 12px', fontSize: 11.5 }} /></div>
            </div>
            <SwapSummary pairs={pairs} onRemoveIn={(p) => setIns(ins.filter(x => x.player_id !== p.player_id))} />
            {outs.length > 0 && !locked && projected < -1e-6 && <div style={{ font: `600 11px 'Hanken Grotesk'`, color: RED, marginBottom: 8 }}>{money(Math.abs(projected))} over budget. Sell another player or pick cheaper replacements.</div>}
            {move !== 'all' && !table.length && <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '6px 2px' }}>{moverEmpty(move)}</p>}
            <div style={{ display: 'grid', gridTemplateColumns: COLS, padding: '0 6px 9px' }}>
              {sortHead('name', 0)}
              <span style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: 'center' }}>Role</span>
              {sortHead('price', 2)}
              {sortHead('sel', 3)}
              {sortHead('total', 4)}
              <span />
            </div>
            <div style={{ maxHeight: 520, overflowY: 'auto' }}>
              {table.map(p => {
                const owned = have.has(p.player_id) || queuedIn.has(p.player_id)
                const sel = inIds.has(p.player_id)
                const ok = canPick(p) && !owned
                return (
                  <div key={p.player_id} style={{ display: 'grid', gridTemplateColumns: COLS, alignItems: 'center', padding: '9px 6px', borderTop: '1px solid var(--surface2)', background: sel ? tintBg(12) : 'transparent', opacity: owned ? 0.4 : 1 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}><Avatar name={p.name} photoUrl={p.photo_url} size={28} /><span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span></span>
                    <span style={{ textAlign: 'center', font: `700 9.5px ${DISP}`, color: 'var(--dim)' }}>{ROLE_SHORT[p.role]}</span>
                    <span style={{ textAlign: 'right', font: `600 12px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{money(p.price)}<PriceArrow change={p.price_change} /></span>
                    <span style={{ textAlign: 'right', font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{p.selected_pct ?? 0}%</span>
                    <span style={{ textAlign: 'right', font: `700 13px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{pts(p.total_points)}</span>
                    <span style={{ textAlign: 'right' }}>
                      <button onClick={() => toggleIn(p)} disabled={owned || (outs.length > 0 && !ok)} style={{ width: 26, height: 26, borderRadius: 8, cursor: owned ? 'default' : 'pointer', font: `800 ${sel ? 13 : 15}px 'Hanken Grotesk'`, opacity: owned || (outs.length > 0 && !ok) ? 0.35 : 1, background: sel ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: sel ? 'var(--ink)' : 'var(--dim)', border: sel ? 'none' : '1px solid var(--hairline2)' }}>{sel ? '✓' : '+'}</button>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const buying = step === 'buy' && outs.length > 0
  const shortRoles = [...new Set(outs.map(o => o.role))]
  return (
    <div>
      <ScreenTitle title="Transfers" back onBack={() => nav('team')} />

      <div style={{ display: 'flex', gap: 7, padding: '14px 0 0' }}>
        <div style={{ flex: 1 }}><StatTile label="Free" value={free > 100 ? '∞' : free} /></div>
        <div style={{ flex: 1 }}><StatTile label={outs.length ? 'Bank after' : 'Bank'} value={money(projected)} color={bankColor} /></div>
        <div style={{ flex: 1 }}><StatTile label="Cost" value={cost} color={cost === 'free' ? GREEN : 'var(--text)'} /></div>
      </div>

      {lockMsg && (
        <div style={{ margin: '12px 0 0', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: AMBER, background: mix(AMBER, 10), border: `1px solid ${mix(AMBER, 28)}` }}>
          {lockMsg}
        </div>
      )}
      <QueuedList items={pendingQ} cancelled={cancelledQ} onCancel={cancelQueued} busy={busy} />

      {!buying ? (
        <>
          <SectionLabel right={outs.length > 0 && <button onClick={clearAll} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Clear ({outs.length})</button>}>Your squad · tap to sell</SectionLabel>
          {!outs.length && <p style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '0 2px 8px' }}>Tap more than one player to sell several at once.</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {squad.players.map(p => {
              const qd = queuedOut.has(p.player_id)
              const sel = outs.some(o => o.player_id === p.player_id)
              return (
                <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} tone={sel ? 'picked' : 'plain'} sub={<>{ROLE_LABEL[p.role]} · sells for <PriceTag price={sellValue(p.purchase_price, poolById[p.player_id]?.price ?? p.price)} change={poolById[p.player_id]?.price_change ?? p.price_change} /> · bought {money(p.purchase_price)}</>}
                  onClick={qd ? undefined : () => toggleOut(p)}
                  right={<span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: qd ? AMBER : RED, border: `1px solid ${mix(qd ? AMBER : RED, 34)}`, padding: '3px 7px', borderRadius: 6 }}>{qd ? 'Queued' : sel ? 'Out' : 'Sell'}</span>} />
              )
            })}
          </div>
          <div style={{ paddingTop: 16 }}>
            <Btn full disabled={!outs.length} onClick={() => setStep('buy')}>
              {outs.length ? `Next: pick ${outs.length > 1 ? `${outs.length} replacements` : 'a replacement'}` : 'Pick who is leaving'}
            </Btn>
          </div>
        </>
      ) : (
        <>
          <div style={{ paddingTop: 14 }}><SwapSummary pairs={pairs} onRemoveIn={(p) => setIns(ins.filter(x => x.player_id !== p.player_id))} /></div>
          <SectionLabel right={<button onClick={() => setStep('sell')} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Change</button>}>
            Replace with · {shortRoles.map(r => ROLE_LABEL[r].toLowerCase()).join(', ')}
          </SectionLabel>
          <Field placeholder="⌕ Search…" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '10px 12px', fontSize: 12.5, marginBottom: 8 }} />
          {shortRoles.length > 1 && (
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 8 }}>
              {[['all', 'All'], ...shortRoles.map(r => [r, ROLE_SHORT[r]])].map(([k, l]) => {
                const on = roleFilter === k || (k === 'all' && !shortRoles.includes(roleFilter))
                return <button key={k} onClick={() => setRoleFilter(k)} style={{ font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`, color: on ? 'var(--ink)' : 'var(--dim)', background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', padding: '6px 11px', borderRadius: 8, border: 'none', cursor: 'pointer' }}>{l}</button>
              })}
            </div>
          )}
          <div style={{ marginBottom: 8 }}><MoverChips value={move} onChange={setMove} /></div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap', marginBottom: 8 }}>
            <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', marginRight: 2 }}>Sort</span>
            {Object.entries(SORTS).map(([k, v]) => {
              const on = effSort?.key === k
              return <button key={k} onClick={() => toggleSort(k)} aria-label={`Sort by ${v.label.toLowerCase()}`} style={{ font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`, color: on ? 'var(--ink)' : 'var(--dim)', background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', padding: '6px 11px', borderRadius: 8, border: 'none', cursor: 'pointer' }}>{k === 'name' ? 'Name' : v.label}{on ? (effSort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</button>
            })}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {!shortlist.length && move !== 'all' && <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '6px 2px' }}>{moverEmpty(move)}</p>}
            {shortlist.map(p => {
              const on = inIds.has(p.player_id)
              const blocked = !canPick(p)
              return (
                <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={<>{ROLE_LABEL[p.role]} · <PriceTag price={p.price} change={p.price_change} /> · {p.selected_pct ?? 0}% selected · {pts(p.total_points)} pts</>}
                  tone={on ? 'picked' : 'plain'} onClick={blocked ? undefined : () => toggleIn(p)}
                  right={<span style={{
                    width: 26, height: 26, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', font: `800 ${on ? 13 : 16}px 'Hanken Grotesk'`,
                    opacity: blocked ? 0.35 : 1, background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)', border: on ? 'none' : '1px solid var(--hairline2)',
                  }}>{on ? '✓' : '+'}</span>} />
              )
            })}
          </div>
          <div style={{ paddingTop: 16 }}>
            <Btn full disabled={!canConfirm || busy} onClick={confirm}>
              {busy ? 'Confirming…' : canConfirm ? `${locked ? (pairs.length > 1 ? `Queue ${pairs.length} transfers for next round` : 'Queue transfer for next round') : confirmLabel} · ${cost}` : projected < -1e-6 ? `${money(Math.abs(projected))} over budget` : 'Pick a replacement for each player'}
            </Btn>
          </div>
        </>
      )}
    </div>
  )
}

// Each player going out beside the player coming in for him (or the role still to fill).
// Tap a pick to take him out of the set.
function SwapSummary({ pairs, onRemoveIn }) {
  if (!pairs.length) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 10 }} data-testid="swap-summary">
      {pairs.map(({ out, tin }) => (
        <div key={out.player_id} style={{ display: 'flex', alignItems: 'center', gap: 8, font: `600 11.5px 'Hanken Grotesk'` }}>
          <span style={{ color: RED, minWidth: 0, flex: '0 1 40%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{out.name}</span>
          <span style={{ color: 'var(--accent-strong)' }}>→</span>
          {tin
            ? <button onClick={() => onRemoveIn(tin)} title="Remove this pick" style={{ minWidth: 0, flex: 1, textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)', font: 'inherit', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tin.name} <span style={{ color: 'var(--faint)' }}>{money(tin.price)} ✕</span></button>
            : <span style={{ color: 'var(--accent-strong)' }}>pick a {ROLE_LABEL[out.role].toLowerCase()}</span>}
        </div>
      ))}
    </div>
  )
}

// Transfers waiting for the locked round to be scored, with a way to withdraw each, and
// any that were cancelled this week with the reason (it cost too much once prices moved).
function QueuedList({ items, cancelled, onCancel, busy }) {
  if (!items.length && !cancelled.length) return null
  return (
    <div style={{ margin: '14px 0 4px' }}>
      <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 7 }}>Queued transfers</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(q => (
          <div key={q.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 11px', borderRadius: 11, background: mix(AMBER, 8, 'var(--surface)'), border: `1px solid ${mix(AMBER, 28)}` }}>
            <div style={{ flex: 1, minWidth: 0, font: `600 12px 'Hanken Grotesk'`, color: 'var(--text)' }}>
              {q.in_name} <span style={{ color: 'var(--faint)' }}>in for</span> {q.out_name}
              <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 2 }}>Happens once Round {q.after_round} is scored</div>
            </div>
            <button disabled={busy} onClick={() => onCancel(q.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: RED, font: `700 11px 'Hanken Grotesk'` }}>Cancel</button>
          </div>
        ))}
        {cancelled.map(q => (
          <div key={q.id} style={{ padding: '8px 11px', borderRadius: 11, background: 'var(--surface)', border: '1px solid var(--hairline)', font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
            {q.in_name} for {q.out_name} did not happen. {q.reason}
          </div>
        ))}
      </div>
    </div>
  )
}

function BarChip({ label, value, color = 'var(--text)', note }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11, padding: '7px 13px' }}>
      <span style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label} </span>
      <span style={{ font: `700 14px ${DISP}`, color }}>{value}</span>
      {note && <span style={{ font: `500 9.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginLeft: 6 }}>{note}</span>}
    </div>
  )
}

function Empty({ nav }) {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--faint)' }}>
      <p style={{ font: `500 13px 'Hanken Grotesk'` }}>Build a squad first.</p>
      <button onClick={() => nav('pick')} style={{ marginTop: 8, background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>Pick your squad →</button>
    </div>
  )
}
