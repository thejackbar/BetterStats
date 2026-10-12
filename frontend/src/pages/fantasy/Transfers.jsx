// Transfers — Free / Bank / Cost tiles, an Out → In swap, a same-role shortlist
// to pick the replacement, then confirm. The first transfer of the round is free;
// further ones cost the points hit.
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { StatTile, DISP, tintBg, mix, money, pts, Btn, Avatar, Field, ROLE_LABEL, ROLE_SHORT, ROLE_ORDER, GREEN, RED, AMBER, PriceTag, PriceArrow, MoverChips, byMover, moverEmpty } from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

// What selling a player returns: his price now. A rise since you bought him adds to
// your bank and a fall takes from it (the server sells at the same figure).
const sellValue = (purchase, current) => Math.round(Number(current ?? purchase ?? 0) * 10) / 10

export default function Transfers({ token, squad, pool, rules, round, onChange, flash, fail, nav, desktop }) {
  const [out, setOut] = useState(null)
  const [tin, setTin] = useState(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')   // desktop pool table filter
  const [move, setMove] = useState('all')                // price movers: all | up | down
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

  const shortlist = useMemo(() => {
    if (!out || !squad) return []
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    const l = (pool || [])
      .filter(p => p.role === out.role && !have.has(p.player_id) && !queuedIn.has(p.player_id) && (!term || p.name.toLowerCase().includes(term)))
    return (move === 'all' ? l.sort((a, b) => b.price - a.price) : byMover(l, move)).slice(0, 40)
  }, [out, pool, squad, search, move]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!squad) return <Empty nav={nav} />

  const outCurrent = out ? (poolById[out.player_id]?.price ?? out.price ?? out.purchase_price) : 0
  const outSell = out ? sellValue(out.purchase_price, outCurrent) : 0
  const bank = Number(squad.budget_remaining || 0)
  const cost = locked ? 'queued' : free > 100 ? 'free' : free > 0 ? 'free' : `${hit} pts`
  const lockMsg = locked
    ? `Round ${round?.number ?? ''} has locked, so your XI and captain are frozen until it's scored. A transfer you make now is queued: it happens once the round is scored, at the prices then, and counts for Round ${round?.next_number ?? 'next'}. If you can't afford it at those prices it is cancelled.`
    : null

  const afterBank = out && tin ? bank + outSell - Number(tin.price) : null
  // While a round is locked the prices are about to move, so the bank is checked when the
  // transfer happens (and the server warns); otherwise it has to fit now.
  const canConfirm = out && tin && !queuedOut.has(out.player_id) && !queuedIn.has(tin.player_id) && (locked || afterBank >= -1e-6)
  const cancelQueued = async (id) => {
    setBusy(true)
    try { await api.fanCancelQueuedTransfer(token, id); flash('Queued transfer cancelled.'); await onChange() }
    catch (e) { fail(e) } finally { setBusy(false) }
  }

  const confirm = async () => {
    setBusy(true)
    try {
      const r = await api.fanTransfer(token, out.player_id, tin.player_id)
      flash(r.queued
        ? (r.warning || `Queued. It happens once Round ${r.after_round} is scored.`)
        : r.hit ? `Transfer done. ${r.hit} pt hit.` : 'Transfer done.')
      setOut(null); setTin(null); setSearch('')
      await onChange()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  if (desktop) {
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    const filtered = (pool || [])
      .filter(p => (roleFilter === 'all' || p.role === roleFilter) && (!term || p.name.toLowerCase().includes(term)))
    const table = move === 'all' ? filtered.sort((a, b) => b.total_points - a.total_points) : byMover(filtered, move)
    const pick = (p) => {
      if (have.has(p.player_id)) return
      if (!out) { flash('Tap a player to sell first.'); return }
      if (p.role !== out.role) { flash('Transfers are like-for-like by role.'); return }
      if (bank + outSell - Number(p.price) < -1e-6) return
      setTin(p)
    }
    return (
      <div style={{ background: 'var(--bg)', border: '1px solid var(--hairline)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--frame-shadow)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '15px 26px', background: 'linear-gradient(180deg,var(--grad-top),var(--bg))', borderBottom: '1px solid var(--hairline)' }}>
          <div style={{ font: `800 18px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>Transfers</div>
          <div style={{ display: 'flex', gap: 8, marginLeft: 14 }}>
            <BarChip label="Free" value={free > 100 ? '∞' : free} />
            <BarChip label="Bank" value={money(bank)} color={GREEN} />
            <BarChip label="Value" value={money(squad.value ?? 0)} />
            <BarChip label="Cost" value={cost === 'free' ? '0 pts' : cost} />
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <Btn disabled={!canConfirm || busy} onClick={confirm} style={{ padding: '9px 18px', fontSize: 13 }}>{busy ? 'Confirming…' : locked ? 'Queue transfer' : 'Confirm transfer'}</Btn>
          </div>
        </div>
        {lockMsg && <div style={{ padding: '10px 26px', font: `600 11.5px 'Hanken Grotesk'`, color: AMBER, background: mix(AMBER, 10) }}>{lockMsg}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr' }}>
          <div style={{ borderRight: '1px solid var(--hairline)', padding: '18px 20px' }}>
            <QueuedList items={pendingQ} cancelled={cancelledQ} onCancel={cancelQueued} busy={busy} />
            <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 10 }}>Your squad · tap to sell</div>
            {ROLE_ORDER.map(role => {
              const rows = squad.players.filter(p => p.role === role)
              if (!rows.length) return null
              return (
                <div key={role}>
                  <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', margin: '12px 2px 7px' }}>{ROLE_LABEL[role]}s</div>
                  {rows.map(p => {
                    const sel = out?.player_id === p.player_id
                    const qd = queuedOut.has(p.player_id)
                    return (
                      <button key={p.player_id} onClick={qd ? undefined : () => { setOut(p); setTin(null) }} style={{
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
            {out && <div style={{ font: `600 11px 'Hanken Grotesk'`, color: 'var(--accent-strong)', marginBottom: 8 }}>Replacing {out.name} · pick a {ROLE_LABEL[out.role].toLowerCase()}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.8fr 0.7fr 0.8fr 44px', padding: '0 6px 9px' }}>
              {['Player', 'Role', 'Price', 'Sel', 'Total', ''].map((h, i) => <span key={i} style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: i === 0 ? 'left' : i === 1 ? 'center' : 'right' }}>{h}</span>)}
            </div>
            <div style={{ maxHeight: 520, overflowY: 'auto' }}>
              {table.map(p => {
                const owned = have.has(p.player_id) || queuedIn.has(p.player_id)
                const sel = tin?.player_id === p.player_id
                const ok = out && p.role === out.role && !owned && bank + outSell - Number(p.price) >= -1e-6
                return (
                  <div key={p.player_id} style={{ display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.8fr 0.7fr 0.8fr 44px', alignItems: 'center', padding: '9px 6px', borderTop: '1px solid var(--surface2)', background: sel ? tintBg(12) : 'transparent', opacity: owned ? 0.4 : 1 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}><Avatar name={p.name} photoUrl={p.photo_url} size={28} /><span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span></span>
                    <span style={{ textAlign: 'center', font: `700 9.5px ${DISP}`, color: 'var(--dim)' }}>{ROLE_SHORT[p.role]}</span>
                    <span style={{ textAlign: 'right', font: `600 12px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{money(p.price)}<PriceArrow change={p.price_change} /></span>
                    <span style={{ textAlign: 'right', font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{p.selected_pct ?? 0}%</span>
                    <span style={{ textAlign: 'right', font: `700 13px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{pts(p.total_points)}</span>
                    <span style={{ textAlign: 'right' }}>
                      <button onClick={() => pick(p)} disabled={owned || (out && !ok)} style={{ width: 26, height: 26, borderRadius: 8, cursor: owned ? 'default' : 'pointer', font: `800 ${sel ? 13 : 15}px 'Hanken Grotesk'`, opacity: owned || (out && !ok) ? 0.35 : 1, background: sel ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: sel ? 'var(--ink)' : 'var(--dim)', border: sel ? 'none' : '1px solid var(--hairline2)' }}>{sel ? '✓' : '+'}</button>
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

  return (
    <div>
      <ScreenTitle title="Transfers" back onBack={() => nav('team')} />

      <div style={{ display: 'flex', gap: 7, padding: '14px 0 0' }}>
        <div style={{ flex: 1 }}><StatTile label="Free" value={free > 100 ? '∞' : free} /></div>
        <div style={{ flex: 1 }}><StatTile label="Bank" value={money(bank)} color={GREEN} /></div>
        <div style={{ flex: 1 }}><StatTile label="Cost" value={cost} color={cost === 'free' ? GREEN : 'var(--text)'} /></div>
      </div>

      {lockMsg && (
        <div style={{ margin: '12px 0 0', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: AMBER, background: mix(AMBER, 10), border: `1px solid ${mix(AMBER, 28)}` }}>
          {lockMsg}
        </div>
      )}
      <QueuedList items={pendingQ} cancelled={cancelledQ} onCancel={cancelQueued} busy={busy} />

      {/* Out → In swap */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 0 0' }}>
        <SwapCard tone="out" label="Out" player={out} placeholder="Pick who's leaving" />
        <div style={{ font: `800 15px ${DISP}`, color: 'var(--accent-strong)' }}>→</div>
        <SwapCard tone="in" label="In" player={tin} placeholder="Pick a replacement" />
      </div>

      {!out ? (
        <>
          <SectionLabel>Your squad · tap to sell</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {squad.players.map(p => (
              <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={<>{ROLE_LABEL[p.role]} · sells for <PriceTag price={sellValue(p.purchase_price, poolById[p.player_id]?.price ?? p.price)} change={poolById[p.player_id]?.price_change ?? p.price_change} /> · bought {money(p.purchase_price)}</>}
                onClick={queuedOut.has(p.player_id) ? undefined : () => { setOut(p); setTin(null) }}
                right={<span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: queuedOut.has(p.player_id) ? AMBER : RED, border: `1px solid ${mix(queuedOut.has(p.player_id) ? AMBER : RED, 34)}`, padding: '3px 7px', borderRadius: 6 }}>{queuedOut.has(p.player_id) ? 'Queued' : 'Sell'}</span>} />
            ))}
          </div>
        </>
      ) : (
        <>
          <SectionLabel right={<button onClick={() => { setOut(null); setTin(null) }} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Change</button>}>
            Replace with · {ROLE_LABEL[out.role].toLowerCase()}s
          </SectionLabel>
          <Field placeholder="⌕ Search…" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '10px 12px', fontSize: 12.5, marginBottom: 8 }} />
          <div style={{ marginBottom: 8 }}><MoverChips value={move} onChange={setMove} /></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {!shortlist.length && move !== 'all' && <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '6px 2px' }}>{moverEmpty(move)}</p>}
            {shortlist.map(p => {
              const on = tin?.player_id === p.player_id
              const over = bank + outSell - Number(p.price) < -1e-6
              return (
                <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={<>{ROLE_LABEL[p.role]} · <PriceTag price={p.price} change={p.price_change} /></>}
                  tone={on ? 'picked' : 'plain'} onClick={over ? undefined : () => setTin(p)}
                  right={<span style={{
                    width: 26, height: 26, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', font: `800 ${on ? 13 : 16}px 'Hanken Grotesk'`,
                    opacity: over ? 0.35 : 1, background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)', border: on ? 'none' : '1px solid var(--hairline2)',
                  }}>{on ? '✓' : '+'}</span>} />
              )
            })}
          </div>
        </>
      )}

      <div style={{ paddingTop: 16 }}>
        <Btn full disabled={!canConfirm || busy} onClick={confirm}>
          {busy ? 'Confirming…' : canConfirm ? (locked ? 'Queue transfer for next round' : `Confirm transfer · ${cost}`) : 'Pick a player out and in'}
        </Btn>
      </div>
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

function BarChip({ label, value, color = 'var(--text)' }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11, padding: '7px 13px' }}>
      <span style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label} </span>
      <span style={{ font: `700 14px ${DISP}`, color }}>{value}</span>
    </div>
  )
}

function SwapCard({ tone, label, player, placeholder }) {
  const accent = tone === 'in'
  return (
    <div style={{
      flex: 1, borderRadius: 13, padding: '11px 12px',
      background: accent ? tintBg(12, 'var(--surface)') : mix(RED, 9, 'var(--surface)'),
      border: `1px solid ${accent ? tintBg(32) : mix(RED, 28)}`,
    }}>
      <div style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: accent ? 'var(--accent-strong)' : RED }}>{label}</div>
      {player ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 7 }}>
          <Avatar name={player.name} photoUrl={player.photo_url} size={30} />
          <div style={{ minWidth: 0 }}>
            <div style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{player.name}</div>
            <div style={{ font: `500 9.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{ROLE_LABEL[player.role]} · <PriceTag price={player.price ?? player.purchase_price} change={player.price_change} /></div>
          </div>
        </div>
      ) : (
        <div style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 9 }}>{placeholder}</div>
      )}
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
