// Transfers — Free / Bank / Cost tiles, an Out → In swap, a same-role shortlist
// to pick the replacement, then confirm. The first transfer of the round is free;
// further ones cost the points hit.
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { StatTile, DISP, tintBg, mix, money, pts, Btn, Avatar, Field, ROLE_LABEL, ROLE_SHORT, ROLE_ORDER, GREEN, RED } from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

const sellValue = (purchase, current) => {
  const profit = Math.max(0, Number(current || 0) - Number(purchase || 0))
  return Math.round((Number(purchase || 0) + profit / 2) * 10) / 10
}

export default function Transfers({ token, squad, pool, rules, round, onChange, flash, fail, nav, desktop }) {
  const [out, setOut] = useState(null)
  const [tin, setTin] = useState(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')   // desktop pool table filter
  const [busy, setBusy] = useState(false)

  const poolById = useMemo(() => Object.fromEntries((pool || []).map(p => [p.player_id, p])), [pool])
  const free = squad?.free_transfers ?? 0
  const hit = rules?.transfer_hit ?? 4
  const locked = !!round?.locked

  if (!squad) return <Empty nav={nav} />

  const outCurrent = out ? (poolById[out.player_id]?.price ?? out.purchase_price) : 0
  const outSell = out ? sellValue(out.purchase_price, outCurrent) : 0
  const bank = Number(squad.budget_remaining || 0)
  const cost = free > 100 ? 'free' : free > 0 ? 'free' : `${hit} pts`

  const shortlist = useMemo(() => {
    if (!out) return []
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    return (pool || [])
      .filter(p => p.role === out.role && !have.has(p.player_id) && (!term || p.name.toLowerCase().includes(term)))
      .sort((a, b) => b.price - a.price)
      .slice(0, 40)
  }, [out, pool, squad, search])

  const afterBank = out && tin ? bank + outSell - Number(tin.price) : null
  const canConfirm = out && tin && afterBank >= -1e-6 && !locked

  const confirm = async () => {
    setBusy(true)
    try {
      const r = await api.fanTransfer(token, out.player_id, tin.player_id)
      flash(r.hit ? `Transfer done. ${r.hit} pt hit.` : 'Transfer done.')
      setOut(null); setTin(null); setSearch('')
      await onChange()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  if (desktop) {
    const have = new Set(squad.players.map(p => p.player_id))
    const term = search.trim().toLowerCase()
    const table = (pool || [])
      .filter(p => (roleFilter === 'all' || p.role === roleFilter) && (!term || p.name.toLowerCase().includes(term)))
      .sort((a, b) => b.total_points - a.total_points)
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
            <Btn disabled={!canConfirm || busy} onClick={confirm} style={{ padding: '9px 18px', fontSize: 13 }}>{busy ? 'Confirming…' : 'Confirm transfer'}</Btn>
          </div>
        </div>
        {locked && <div style={{ padding: '10px 26px', font: `600 11.5px 'Hanken Grotesk'`, color: RED, background: mix(RED, 8) }}>This round has locked. You can transfer again once it's scored.</div>}
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr' }}>
          <div style={{ borderRight: '1px solid var(--hairline)', padding: '18px 20px' }}>
            <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 10 }}>Your squad · tap to sell</div>
            {ROLE_ORDER.map(role => {
              const rows = squad.players.filter(p => p.role === role)
              if (!rows.length) return null
              return (
                <div key={role}>
                  <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', margin: '12px 2px 7px' }}>{ROLE_LABEL[role]}s</div>
                  {rows.map(p => {
                    const sel = out?.player_id === p.player_id
                    return (
                      <button key={p.player_id} onClick={() => { setOut(p); setTin(null) }} style={{
                        display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', padding: '8px 11px', marginBottom: 6, borderRadius: 11, cursor: 'pointer',
                        background: sel ? mix(RED, 10, 'var(--surface)') : 'var(--surface)', border: `1px solid ${sel ? mix(RED, 34) : 'var(--hairline)'}`,
                      }}>
                        <Avatar name={p.name} photoUrl={p.photo_url} size={30} />
                        <span style={{ flex: 1, minWidth: 0, font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
                        <span style={{ font: `600 11px ${DISP}`, color: 'var(--faint)' }}>{money(p.purchase_price)}</span>
                        <span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: RED, border: `1px solid ${mix(RED, 34)}`, padding: '3px 7px', borderRadius: 6 }}>{sel ? 'Out' : 'Sell'}</span>
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
              <div style={{ marginLeft: 'auto', width: 180 }}><Field placeholder="⌕ Search" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '7px 12px', fontSize: 11.5 }} /></div>
            </div>
            {out && <div style={{ font: `600 11px 'Hanken Grotesk'`, color: 'var(--accent-strong)', marginBottom: 8 }}>Replacing {out.name} · pick a {ROLE_LABEL[out.role].toLowerCase()}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.8fr 0.7fr 0.8fr 44px', padding: '0 6px 9px' }}>
              {['Player', 'Role', 'Price', 'Sel', 'Total', ''].map((h, i) => <span key={i} style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: i === 0 ? 'left' : i === 1 ? 'center' : 'right' }}>{h}</span>)}
            </div>
            <div style={{ maxHeight: 520, overflowY: 'auto' }}>
              {table.map(p => {
                const owned = have.has(p.player_id)
                const sel = tin?.player_id === p.player_id
                const ok = out && p.role === out.role && !owned && bank + outSell - Number(p.price) >= -1e-6
                return (
                  <div key={p.player_id} style={{ display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.8fr 0.7fr 0.8fr 44px', alignItems: 'center', padding: '9px 6px', borderTop: '1px solid var(--surface2)', background: sel ? tintBg(12) : 'transparent', opacity: owned ? 0.4 : 1 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}><Avatar name={p.name} photoUrl={p.photo_url} size={28} /><span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span></span>
                    <span style={{ textAlign: 'center', font: `700 9.5px ${DISP}`, color: 'var(--dim)' }}>{ROLE_SHORT[p.role]}</span>
                    <span style={{ textAlign: 'right', font: `600 12px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{money(p.price)}</span>
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

      {locked && (
        <div style={{ margin: '12px 0 0', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: RED, background: mix(RED, 10), border: `1px solid ${mix(RED, 28)}` }}>
          This round has locked. You can transfer again once it's scored.
        </div>
      )}

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
              <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={`${ROLE_LABEL[p.role]} · ${money(p.purchase_price)}`}
                onClick={() => { setOut(p); setTin(null) }}
                right={<span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: RED, border: `1px solid ${mix(RED, 34)}`, padding: '3px 7px', borderRadius: 6 }}>Sell</span>} />
            ))}
          </div>
        </>
      ) : (
        <>
          <SectionLabel right={<button onClick={() => { setOut(null); setTin(null) }} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Change</button>}>
            Replace with · {ROLE_LABEL[out.role].toLowerCase()}s
          </SectionLabel>
          <Field placeholder="⌕ Search…" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '10px 12px', fontSize: 12.5, marginBottom: 8 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {shortlist.map(p => {
              const on = tin?.player_id === p.player_id
              const over = bank + outSell - Number(p.price) < -1e-6
              return (
                <PlayerRow key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={`${ROLE_LABEL[p.role]} · ${money(p.price)}`}
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
          {busy ? 'Confirming…' : canConfirm ? `Confirm transfer · ${cost}` : 'Pick a player out and in'}
        </Btn>
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
            <div style={{ font: `500 9.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{ROLE_LABEL[player.role]} · {money(player.price ?? player.purchase_price)}</div>
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
