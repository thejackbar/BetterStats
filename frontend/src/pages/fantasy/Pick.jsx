// Pick / Edit squad — the builder: budget tiles, role filter pills, search + sort,
// the pool list (picked = accent ✓, open = +), and a captain / vice picker. While
// the season is live this becomes a captain editor (swaps go through Transfers).
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import {
  StatTile, DISP, tintBg, money, Btn, Field, CapBadge, Avatar,
  ROLE_ORDER, ROLE_LABEL, GREEN,
} from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

export default function Pick({ token, pool, rules, squad, season, onSaved, fail, nav, flash }) {
  const active = season?.status === 'active'
  if (active && squad) return <CaptainEditor token={token} squad={squad} onSaved={onSaved} fail={fail} flash={flash} nav={nav} />
  return <Builder token={token} pool={pool} rules={rules} squad={squad} onSaved={onSaved} fail={fail} nav={nav} />
}

function Builder({ token, pool, rules, squad, onSaved, fail, nav }) {
  const quota = rules?.role_quota || { keeper: 1, batter: 4, allrounder: 3, bowler: 4 }
  const budget = rules?.budget ?? 100
  const size = rules?.squad_size ?? 12
  const [picked, setPicked] = useState(() => {
    const init = {}
    ;(squad?.players || []).forEach(p => { init[p.player_id] = { ...p, price: p.purchase_price } })
    return init
  })
  const [teamName, setTeamName] = useState(squad?.team_name || '')
  const [filter, setFilter] = useState('batter')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('price')
  const [poolOpen, setPoolOpen] = useState(true)
  const [busy, setBusy] = useState(false)

  const chosen = Object.values(picked)
  const spend = chosen.reduce((s, p) => s + Number(p.price || p.current_price || 0), 0)
  const left = budget - spend
  const byRole = (r) => chosen.filter(p => p.role === r).length

  const list = useMemo(() => {
    const term = search.trim().toLowerCase()
    let l = term ? (pool || []).filter(p => p.name.toLowerCase().includes(term)) : (pool || []).filter(p => p.role === filter)
    l = [...l]
    if (sort === 'price') l.sort((a, b) => b.price - a.price)
    else if (sort === 'price_asc') l.sort((a, b) => a.price - b.price)
    else if (sort === 'points') l.sort((a, b) => b.total_points - a.total_points)
    else l.sort((a, b) => a.name.localeCompare(b.name))
    return l
  }, [pool, filter, search, sort])

  const toggle = (pp) => setPicked(cur => {
    const next = { ...cur }
    if (next[pp.player_id]) { delete next[pp.player_id]; return next }
    if (chosen.length >= size) return cur
    if (byRole(pp.role) >= (quota[pp.role] || 0)) return cur
    if (Number(pp.price) > left + 1e-6) return cur
    next[pp.player_id] = { player_id: pp.player_id, name: pp.name, role: pp.role, price: pp.price, photo_url: pp.photo_url, is_captain: false, is_vice_captain: false }
    return next
  })
  // Captain and vice are one each, and a single player can't be both — clear the
  // opposite flag on the player being set (this was the squad-save 400).
  const setCap = (pid, key) => setPicked(cur => {
    const other = key === 'is_captain' ? 'is_vice_captain' : 'is_captain'
    const next = {}
    for (const [id, p] of Object.entries(cur)) {
      const target = id === pid
      next[id] = { ...p, [key]: target ? !p[key] : false, [other]: target ? false : p[other] }
    }
    return next
  })

  const quotaOk = ROLE_ORDER.every(r => byRole(r) === (quota[r] || 0))
  const hasCap = chosen.some(p => p.is_captain)
  const valid = chosen.length === size && quotaOk && left >= -1e-6 && hasCap

  const save = async () => {
    setBusy(true)
    try {
      await api.fanSaveSquad(token, {
        team_name: teamName,
        picks: chosen.map(p => ({ player_id: p.player_id, is_captain: !!p.is_captain, is_vice_captain: !!p.is_vice_captain })),
      })
      await onSaved()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div>
      <ScreenTitle title="Build squad" sub={`${size}-man · ${money(budget)} budget`} back onBack={() => nav('team')} />

      <div style={{ display: 'flex', gap: 7, padding: '14px 0 0' }}>
        <div style={{ flex: 1 }}><StatTile label="In the bank" value={money(left)} color={left < 0 ? '#ef5b5b' : GREEN} /></div>
        <div style={{ flex: 1 }}><StatTile label="Picked" value={`${chosen.length} / ${size}`} /></div>
        <div style={{ flex: 1 }}><StatTile label="Spent" value={money(spend)} /></div>
      </div>

      <div style={{ padding: '14px 0 0' }}>
        <Field placeholder="Team name" value={teamName} onChange={e => setTeamName(e.target.value)} />
      </div>

      <div style={{ display: 'flex', gap: 6, padding: '12px 0 0' }}>
        {ROLE_ORDER.map(r => {
          const on = filter === r
          return (
            <button key={r} onClick={() => setFilter(r)} style={{
              flex: 1, textAlign: 'center', borderRadius: 10, padding: '7px 4px', border: 'none', cursor: 'pointer',
              font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`,
              background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)',
            }}>
              {ROLE_LABEL[r].replace('Wicketkeeper', 'Keeper')}<br /><span style={{ opacity: 0.75 }}>{byRole(r)}/{quota[r] || 0}</span>
            </button>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, padding: '12px 0 0' }}>
        <Field placeholder="⌕ Search players…" value={search} onChange={e => setSearch(e.target.value)} style={{ padding: '10px 12px', fontSize: 12.5 }} />
        <select value={sort} onChange={e => setSort(e.target.value)} style={{
          background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '10px 12px',
          font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--dim)', outline: 'none',
        }}>
          <option value="price">Price ▾</option>
          <option value="price_asc">Price ▴</option>
          <option value="points">Points</option>
          <option value="name">Name</option>
        </select>
      </div>

      <button onClick={() => setPoolOpen(o => !o)} style={{
        display: 'flex', alignItems: 'center', width: '100%', background: 'none', border: 'none', cursor: 'pointer',
        padding: '14px 2px 7px',
      }}>
        <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)' }}>Player pool · {list.length}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--faint)', font: `700 11px 'Hanken Grotesk'` }}>{poolOpen ? 'Hide ▾' : 'Show ▸'}</span>
      </button>

      {poolOpen && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {list.map(pp => {
            const on = !!picked[pp.player_id]
            const blocked = !on && (chosen.length >= size || byRole(pp.role) >= (quota[pp.role] || 0) || Number(pp.price) > left + 1e-6)
            return (
              <PlayerRow
                key={pp.player_id} name={pp.name} photoUrl={pp.photo_url}
                sub={`${ROLE_LABEL[pp.role]} · ${money(pp.price)}`}
                tone={on ? 'picked' : 'plain'}
                onClick={blocked ? undefined : () => toggle(pp)}
                right={<span style={{
                  width: 26, height: 26, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  font: `800 ${on ? 13 : 16}px 'Hanken Grotesk'`, opacity: blocked ? 0.35 : 1,
                  background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)',
                  color: on ? 'var(--ink)' : 'var(--dim)', border: on ? 'none' : '1px solid var(--hairline2)',
                }}>{on ? '✓' : '+'}</span>}
              />
            )
          })}
        </div>
      )}

      {chosen.length > 0 && (
        <div style={{ marginTop: 14, ...{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14 }, padding: 12 }}>
          <div style={{ font: `600 10px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 8 }}>Captain & vice</div>
          {chosen.map(p => (
            <div key={p.player_id} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '4px 0' }}>
              <Avatar name={p.name} photoUrl={p.photo_url} size={26} />
              <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
              {['is_captain', 'is_vice_captain'].map(key => {
                const on = p[key]
                return (
                  <button key={key} onClick={() => setCap(p.player_id, key)} style={{
                    width: 28, height: 28, borderRadius: 8, border: 'none', cursor: 'pointer', font: `800 11px ${DISP}`,
                    background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--faint)',
                  }}>{key === 'is_captain' ? 'C' : 'V'}</button>
                )
              })}
            </div>
          ))}
        </div>
      )}

      <div style={{ paddingTop: 16 }}>
        <Btn full disabled={!valid || busy} onClick={save}>
          {busy ? 'Saving…' : valid ? 'Save squad · full, captained, in budget' : `${chosen.length}/${size} · pick a full, captained, in-budget squad`}
        </Btn>
      </div>
    </div>
  )
}

// While the season is live the squad is fixed (transfers handle swaps); this lets
// the manager change the captain and vice.
function CaptainEditor({ token, squad, onSaved, fail, flash, nav }) {
  const [busy, setBusy] = useState(false)
  const cap = squad.players.find(p => p.is_captain)?.player_id
  const vice = squad.players.find(p => p.is_vice_captain)?.player_id
  const set = async (pid, asVice) => {
    if (asVice && cap === pid) return   // can't make the captain the vice; pick a new captain first
    if (!asVice && cap === pid) return  // already captain
    setBusy(true)
    try {
      // Never send the same player as both captain and vice.
      const captainId = asVice ? cap : pid
      const viceId = asVice ? pid : (vice === pid ? null : vice)
      await api.fanSetCaptain(token, captainId, viceId)
      flash(asVice ? 'Vice-captain updated.' : 'Captain updated.')
      await onSaved()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  return (
    <div>
      <ScreenTitle title="Captain" sub="Season's live · swap via transfers" back onBack={() => nav('team')} />
      <div style={{ margin: '14px 0 2px', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--accent-strong)', background: tintBg(12), border: `1px solid ${tintBg(28)}` }}>
        Pick your captain (×2) and vice. Make player swaps on the Transfers screen.
      </div>
      <SectionLabel>Your squad</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {ROLE_ORDER.flatMap(r => squad.players.filter(p => p.role === r)).map(p => (
          <PlayerRow
            key={p.player_id} name={p.name} photoUrl={p.photo_url} sub={ROLE_LABEL[p.role]}
            badge={p.is_captain ? <CapBadge /> : p.is_vice_captain ? <CapBadge vice /> : null}
            right={
              <span style={{ display: 'flex', gap: 6 }}>
                <button disabled={busy} onClick={() => set(p.player_id, false)} style={capBtn(p.is_captain)}>C</button>
                <button disabled={busy} onClick={() => set(p.player_id, true)} style={capBtn(p.is_vice_captain)}>V</button>
              </span>
            }
          />
        ))}
      </div>
      <div style={{ paddingTop: 16 }}><Btn variant="soft" full onClick={() => nav('transfers')}>Go to transfers</Btn></div>
    </div>
  )
}

const capBtn = (on) => ({
  width: 28, height: 28, borderRadius: 8, border: 'none', cursor: 'pointer', font: `800 11px ${DISP}`,
  background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--faint)',
})
