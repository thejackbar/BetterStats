// Players — the player profile (hero, stat tiles, last-5 form chart, upcoming
// fixtures), the two-player compare, and the desktop stats explorer table.
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import {
  Aurora, Avatar, DISP, tintBg, mix, money, pts, Btn, Field,
  ROLE_LABEL, ROLE_SHORT, GREEN, AMBER, RED, CYAN, useFantasy,
} from './ui'
import { ScreenTitle, SectionLabel } from './shell'

const Chip = ({ children, color = 'var(--dim)', bg = 'var(--surface2)', border }) => (
  <span style={{ font: `700 11px ${DISP}`, letterSpacing: '.04em', color, background: bg, border, padding: '3px 8px', borderRadius: 6 }}>{children}</span>
)

// ── Player profile ─────────────────────────────────────────────────────────────
const ProfileTile = ({ label, value, color = 'var(--text)' }) => (
  <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '9px 11px' }}>
    <div style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label}</div>
    <div style={{ font: `700 17px ${DISP}`, color, marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
  </div>
)
const TileGrid = ({ tiles }) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 7 }}>
    {tiles.map(([l, v, color]) => <ProfileTile key={l} label={l} value={v} color={color} />)}
  </div>
)
const signMoney = (n) => `${n > 0 ? '+' : n < 0 ? '−' : ''}$${Math.abs(Number(n || 0)).toFixed(1)}`

export function PlayerProfile({ token, playerId, season, onBack, nav, desktop }) {
  const { club } = useFantasy()
  const [p, setP] = useState(null)
  const [err, setErr] = useState(false)
  useEffect(() => { setP(null); setErr(false); api.fanPlayer(token, playerId).then(setP).catch(() => setErr(true)) }, [token, playerId])

  if (err) return <div><ScreenTitle title="Player" back onBack={onBack} /><p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>Couldn't load this player.</p></div>
  if (!p) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>

  const ss = p.season_stats || {}
  const career = p.career_stats || {}
  const max5 = Math.max(1, ...(p.last5 || []).map(f => f.points))
  const active = season?.status === 'active'
  const pc = Number(p.price_change || 0)
  const pcColor = pc > 0 ? GREEN : pc < 0 ? RED : 'var(--text)'
  const hasCareer = (career.matches ?? 0) > 0 || (career.seasons ?? 0) > 0

  // Fantasy scoring breakdown the manager cares about: total, the weekly average,
  // last round, form, ownership and the season's price move.
  const fantasyTiles = [
    ['Total pts', pts(p.total_points)],
    ['Avg / round', pts(p.weekly_avg ?? 0)],
    ['Last round', pts(p.last_round_points)],
    ['Form', p.form],
    ['Selected', `${p.selected_pct}%`],
    ['Price change', signMoney(pc), pcColor],
  ]
  const seasonTiles = [
    ['Matches', ss.matches ?? 0],
    ['Runs', ss.runs ?? 0],
    ['50s / 100s', `${ss.fifties ?? 0} / ${ss.hundreds ?? 0}`],
    ['Wickets', ss.wickets ?? 0],
    ['Catches', ss.catches ?? 0],
    ['Price', money(p.price)],
  ]
  const careerTiles = [
    ['Seasons', career.seasons ?? 0],
    ['Matches', career.matches ?? 0],
    ['Runs', career.runs ?? 0],
    ['Wickets', career.wickets ?? 0],
    ['50s / 100s', `${career.fifties ?? 0} / ${career.hundreds ?? 0}`],
    ['Catches', career.catches ?? 0],
  ]

  const hero = (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '10px 0 16px' }}>
      <Aurora style={{ inset: '-40% -20% auto', height: '160%' }} blur={46} blobs={[
        { c: 'var(--pb-accent, #8C82F0)', a: 'bfcAuroraA', s: 18, pos: { width: '55%', height: '60%', left: '6%', top: '0' } },
        { c: CYAN, a: 'bfcAuroraB', s: 22, pos: { width: '50%', height: '55%', right: '2%', top: '6%' } },
      ]} />
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={onBack} aria-label="Back" style={{ width: 30, height: 30, borderRadius: '50%', cursor: 'pointer', background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `700 16px 'Hanken Grotesk'` }}>{'‹'}</button>
          <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.16em', textTransform: 'uppercase', color: 'var(--faint)' }}>Player profile</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14 }}>
          <Avatar name={p.name} photoUrl={p.photo_url} size={64} />
          <div>
            <div style={{ font: `800 23px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)', lineHeight: 1 }}>{p.name}</div>
            <div style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 4 }}>{ROLE_LABEL[p.role]}{p.team ? ` · ${p.team}` : club?.name ? ` · ${club.name}` : ''}</div>
            <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
              <Chip color="var(--accent-strong)" bg={tintBg(14)} border={`1px solid ${tintBg(30)}`}>{money(p.price)}</Chip>
              <Chip color={GREEN} bg={mix(GREEN, 12)} border={`1px solid ${mix(GREEN, 26)}`}>Form {p.form}</Chip>
              <Chip>{p.selected_pct}% owned</Chip>
            </div>
          </div>
        </div>
      </div>
    </div>
  )

  const chartBlock = !!(p.last5 || []).length && (
    <>
      <SectionLabel>Last 5 rounds</SectionLabel>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 96, padding: '8px 0 0' }}>
        {p.last5.map(f => {
          const h = Math.max(6, Math.round((f.points / max5) * 56))
          const hi = f.points >= max5 * 0.6
          return (
            <div key={f.round} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, height: '100%', justifyContent: 'flex-end' }}>
              <div style={{ font: `700 11px ${DISP}`, color: 'var(--text)' }}>{pts(f.points)}</div>
              <div style={{ width: '100%', display: 'flex', alignItems: 'flex-end', height: 56 }}>
                <div style={{ width: '100%', height: h, borderRadius: 5, background: hi ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)' }} />
              </div>
              <div style={{ font: `600 9px 'Hanken Grotesk'`, color: 'var(--faint)' }}>R{f.round}</div>
            </div>
          )
        })}
      </div>
    </>
  )

  const upcomingBlock = !!(p.fixtures || []).length && (
    <>
      <SectionLabel>Upcoming</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {p.fixtures.map(x => (
          <div key={x.round} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 12px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11 }}>
            <span style={{ font: `700 11px ${DISP}`, color: 'var(--dim)', width: 30 }}>R{x.round}</span>
            <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{x.name || `Round ${x.round}`}</span>
            <Difficulty d={x.difficulty} />
          </div>
        ))}
      </div>
    </>
  )

  const transferBtn = <Btn full onClick={() => nav(active ? 'transfers' : 'pick')}>Transfer in · {money(p.price)}</Btn>

  const statSections = (
    <>
      <SectionLabel>Fantasy points</SectionLabel>
      <TileGrid tiles={fantasyTiles} />
      <SectionLabel>This season</SectionLabel>
      <TileGrid tiles={seasonTiles} />
      {hasCareer && (
        <>
          <SectionLabel>Career{career.seasons ? ` · ${career.seasons} season${career.seasons === 1 ? '' : 's'}` : ''}</SectionLabel>
          <TileGrid tiles={careerTiles} />
        </>
      )}
    </>
  )

  if (desktop) {
    return (
      <div style={{ maxWidth: 1080, margin: '0 auto' }}>
        {hero}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 22, alignItems: 'start', paddingTop: 4 }}>
          <div>{statSections}</div>
          <div>
            {chartBlock}
            {upcomingBlock}
            <div style={{ paddingTop: 16 }}>{transferBtn}</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      {hero}
      {statSections}
      {chartBlock}
      {upcomingBlock}
      <div style={{ paddingTop: 16 }}>{transferBtn}</div>
    </div>
  )
}

function Difficulty({ d }) {
  const map = { easy: ['Easy', GREEN], even: ['Even', AMBER], hard: ['Hard', RED] }
  const [label, color] = map[d] || map.even
  return <span style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color, background: mix(color, 14), padding: '3px 8px', borderRadius: 5 }}>{label}</span>
}

// ── Compare ─────────────────────────────────────────────────────────────────
export function Compare({ token, pool, nav }) {
  const [aId, setAId] = useState(null)
  const [bId, setBId] = useState(null)
  const [a, setA] = useState(null)
  const [b, setB] = useState(null)
  useEffect(() => { if (aId) api.fanPlayer(token, aId).then(setA).catch(() => {}); else setA(null) }, [token, aId])
  useEffect(() => { if (bId) api.fanPlayer(token, bId).then(setB).catch(() => {}); else setB(null) }, [token, bId])

  const rows = useMemo(() => {
    if (!a || !b) return []
    const high = (x) => Math.max(0, ...(x.last5 || []).map(f => f.points))
    return [
      ['Total points', a.total_points, b.total_points],
      ['Form · 5-rd', a.form, b.form],
      ['Selected by', a.selected_pct, b.selected_pct],
      ['This round', a.last_round_points, b.last_round_points],
      ['Recent high', high(a), high(b)],
      ['Price', a.price, b.price],
    ]
  }, [a, b])

  return (
    <div>
      <ScreenTitle title="Compare" back onBack={() => nav('stats')} />
      <div style={{ display: 'flex', gap: 8, padding: '14px 0' }}>
        <PoolPick pool={pool} value={aId} onChange={setAId} placeholder="Player A" />
        <PoolPick pool={pool} value={bId} onChange={setBId} placeholder="Player B" />
      </div>
      {!a || !b ? (
        <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>Pick two players to compare.</p>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'stretch', paddingBottom: 6 }}>
            <Head p={a} />
            <div style={{ display: 'flex', alignItems: 'center', font: `800 14px ${DISP}`, color: 'var(--faint)', padding: '0 8px' }}>VS</div>
            <Head p={b} cyan />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {rows.map(([label, av, bv]) => {
              const aLead = Number(av) > Number(bv), bLead = Number(bv) > Number(av)
              const fmt = (v) => label === 'Price' ? money(v) : label === 'Selected by' ? `${v}%` : pts(v)
              return (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CmpCell v={fmt(av)} lead={aLead} />
                  <div style={{ width: 96, textAlign: 'center', font: `600 9px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label}</div>
                  <CmpCell v={fmt(bv)} lead={bLead} cyan />
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

const Head = ({ p, cyan }) => (
  <div style={{ flex: 1, textAlign: 'center' }}>
    <div style={{ margin: '0 auto', width: 52, height: 52 }}><Avatar name={p.name} photoUrl={p.photo_url} size={52} /></div>
    <div style={{ font: `800 14px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)', marginTop: 8 }}>{p.name}</div>
    <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: cyan ? '#22a8c4' : 'var(--faint)' }}>{ROLE_LABEL[p.role]} · {money(p.price)}</div>
  </div>
)
const CmpCell = ({ v, lead, cyan }) => (
  <div style={{
    flex: 1, textAlign: 'center', font: `700 15px ${DISP}`, padding: '7px 0', borderRadius: 8,
    color: lead ? (cyan ? '#22a8c4' : 'var(--accent-strong)') : 'var(--text)',
    background: lead ? (cyan ? 'color-mix(in srgb, #22D3EE 12%, transparent)' : tintBg(12)) : 'var(--surface)',
    border: lead ? 'none' : '1px solid var(--hairline)',
  }}>{v}</div>
)

function PoolPick({ pool, value, onChange, placeholder }) {
  return (
    <select value={value || ''} onChange={e => onChange(e.target.value || null)} style={{
      flex: 1, minWidth: 0, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '10px 12px',
      font: `600 12.5px 'Hanken Grotesk'`, color: value ? 'var(--text)' : 'var(--faint)', outline: 'none',
    }}>
      <option value="">{placeholder}</option>
      {(pool || []).map(p => <option key={p.player_id} value={p.player_id}>{p.name}</option>)}
    </select>
  )
}

// ── Stats explorer ─────────────────────────────────────────────────────────────
const SORTS = { total: (a, b) => b.total_points - a.total_points, gw: (a, b) => (b.last_round_points || 0) - (a.last_round_points || 0), price: (a, b) => b.price - a.price, sel: (a, b) => (b.selected_pct || 0) - (a.selected_pct || 0), name: (a, b) => a.name.localeCompare(b.name) }

export function StatsExplorer({ pool, nav }) {
  const [role, setRole] = useState('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('total')

  const list = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (pool || [])
      .filter(p => (role === 'all' || p.role === role) && (!term || p.name.toLowerCase().includes(term)))
      .sort(SORTS[sort])
  }, [pool, role, search, sort])

  return (
    <div>
      <ScreenTitle title="All players" right={<button onClick={() => nav('compare')} style={{ background: 'var(--surface2)', border: '1px solid var(--hairline2)', borderRadius: 9, padding: '6px 11px', font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--dim)', cursor: 'pointer' }}>Compare</button>} />

      <div style={{ display: 'flex', gap: 5, padding: '14px 0 0', flexWrap: 'wrap' }}>
        {[['all', 'All'], ['batter', 'BAT'], ['bowler', 'BWL'], ['allrounder', 'AR'], ['keeper', 'WK']].map(([k, l]) => {
          const on = role === k
          return <button key={k} onClick={() => setRole(k)} style={{ font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`, color: on ? 'var(--ink)' : 'var(--dim)', background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', padding: '6px 11px', borderRadius: 8, border: 'none', cursor: 'pointer' }}>{l}</button>
        })}
      </div>
      <div style={{ display: 'flex', gap: 8, padding: '10px 0 4px' }}>
        <Field placeholder="⌕ Search" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '9px 12px', fontSize: 12 }} />
        <select value={sort} onChange={e => setSort(e.target.value)} style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 9, padding: '9px 12px', font: `600 12px 'Hanken Grotesk'`, color: 'var(--dim)', outline: 'none' }}>
          <option value="total">Total</option><option value="gw">GW</option><option value="price">Price</option><option value="sel">Sel%</option><option value="name">Name</option>
        </select>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.9fr 0.7fr 0.6fr 0.7fr', gap: 0, padding: '12px 4px 8px', borderBottom: '1px solid var(--hairline)' }}>
        {['Player', 'Role', 'Price', 'Sel%', 'GW', 'Total'].map((h, i) => (
          <span key={h} style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: i === 0 ? 'left' : i === 1 ? 'center' : 'right' }}>{h}</span>
        ))}
      </div>
      <div>
        {list.map(p => (
          <button key={p.player_id} onClick={() => nav('player', { playerId: p.player_id, from: 'stats' })} style={{
            display: 'grid', gridTemplateColumns: '2fr 0.7fr 0.9fr 0.7fr 0.6fr 0.7fr', gap: 0, alignItems: 'center',
            width: '100%', textAlign: 'left', padding: '10px 4px',
            border: 'none', borderBottom: '1px solid var(--surface2)', background: 'none', cursor: 'pointer',
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
              <Avatar name={p.name} photoUrl={p.photo_url} size={28} />
              <span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
            </span>
            <span style={{ textAlign: 'center', font: `700 9.5px ${DISP}`, letterSpacing: '.06em', color: 'var(--dim)' }}>{ROLE_SHORT[p.role]}</span>
            <span style={{ textAlign: 'right', font: `600 12px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{money(p.price)}</span>
            <span style={{ textAlign: 'right', font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', fontVariantNumeric: 'tabular-nums' }}>{p.selected_pct ?? 0}%</span>
            <span style={{ textAlign: 'right', font: `600 12.5px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(p.last_round_points)}</span>
            <span style={{ textAlign: 'right', font: `700 13.5px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{pts(p.total_points)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
