// Transfers — Free / Bank / Cost tiles, an Out → In swap, a same-role shortlist
// to pick the replacement, then confirm. The first transfer of the round is free;
// further ones cost the points hit.
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { StatTile, DISP, tintBg, mix, money, Btn, Avatar, Field, ROLE_LABEL, GREEN, RED } from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

const sellValue = (purchase, current) => {
  const profit = Math.max(0, Number(current || 0) - Number(purchase || 0))
  return Math.round((Number(purchase || 0) + profit / 2) * 10) / 10
}

export default function Transfers({ token, squad, pool, rules, round, onChange, flash, fail, nav }) {
  const [out, setOut] = useState(null)
  const [tin, setTin] = useState(null)
  const [search, setSearch] = useState('')
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
                    opacity: over ? 0.35 : 1, background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)', border: on ? 'none' : '1px solid var(--hairline2)',
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
