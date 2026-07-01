// Pick Squad — the builder: budget tiles, your picked squad up top (with quick
// remove + captain / vice controls), then the role-filtered pool (picked = accent
// ✓, open = +). On desktop the squad sits in a left rail beside a wide pool grid.
// While the season is live this becomes a captain editor (swaps go through
// Transfers).
import { useMemo, useState } from 'react'
import { api } from '../../lib/api'
import {
  StatTile, DISP, tintBg, money, Btn, Field, CapBadge,
  ROLE_ORDER, ROLE_LABEL, GREEN,
} from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'

export default function Pick({ token, pool, rules, squad, season, onSaved, fail, nav, flash, desktop }) {
  const active = season?.status === 'active'
  if (active && squad) return <CaptainEditor token={token} squad={squad} onSaved={onSaved} fail={fail} flash={flash} nav={nav} />
  return <Builder token={token} pool={pool} rules={rules} squad={squad} onSaved={onSaved} fail={fail} nav={nav} desktop={desktop} />
}

// A small control cluster (Captain · Vice · remove) for a picked-squad row.
function SquadControls({ p, onCap, onRemove }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      {['is_captain', 'is_vice_captain'].map(key => {
        const on = p[key]
        return (
          <button key={key} onClick={() => onCap(p.player_id, key)} aria-label={key === 'is_captain' ? 'Captain' : 'Vice-captain'} style={{
            width: 28, height: 28, borderRadius: 8, border: 'none', cursor: 'pointer', font: `800 11px ${DISP}`,
            background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--faint)',
          }}>{key === 'is_captain' ? 'C' : 'V'}</button>
        )
      })}
      <button onClick={() => onRemove(p.player_id)} aria-label="Remove from squad" style={{
        width: 28, height: 28, borderRadius: 8, cursor: 'pointer', font: `700 15px 'Hanken Grotesk'`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)',
      }}>×</button>
    </span>
  )
}

function Builder({ token, pool, rules, squad, onSaved, fail, nav, desktop }) {
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
  const chosenByRole = ROLE_ORDER.flatMap(r => chosen.filter(p => p.role === r))
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
  const remove = (pid) => setPicked(cur => { const next = { ...cur }; delete next[pid]; return next })
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

  const saveLabel = busy ? 'Saving…' : valid ? 'Save squad · full, captained, in budget' : `${chosen.length}/${size} · pick a full, captained, in-budget squad`

  // ── reusable blocks (shared by the mobile stack and the desktop two-pane) ──
  const tiles = (
    <div style={{ display: 'flex', gap: 7 }}>
      <div style={{ flex: 1 }}><StatTile label="In the bank" value={money(left)} color={left < 0 ? '#ef5b5b' : GREEN} /></div>
      <div style={{ flex: 1 }}><StatTile label="Picked" value={`${chosen.length} / ${size}`} /></div>
      <div style={{ flex: 1 }}><StatTile label="Spent" value={money(spend)} /></div>
    </div>
  )

  const nameField = <Field placeholder="Team name" value={teamName} onChange={e => setTeamName(e.target.value)} />
  const saveBtn = <Btn full disabled={!valid || busy} onClick={save}>{saveLabel}</Btn>

  // Your squad — the quick way to see who's in and drop them, in the same
  // photo-led row format as the pool. C / V set the captain and vice inline.
  const squadSection = (
    <div>
      <SectionLabel right={<span style={{ font: `600 10.5px 'Hanken Grotesk'`, color: chosen.length === size ? GREEN : 'var(--faint)' }}>{chosen.length} / {size}</span>}>Your squad</SectionLabel>
      {chosen.length === 0 ? (
        <div style={{ borderRadius: 12, padding: '14px 14px', background: 'var(--surface)', border: '1px dashed var(--hairline2)', font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
          Tap players in the pool to add them. They'll show here so you can drop or captain them fast.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {chosenByRole.map(p => (
            <PlayerRow
              key={p.player_id} name={p.name} photoUrl={p.photo_url}
              sub={`${ROLE_LABEL[p.role]} · ${money(p.price)}`}
              tone="picked"
              badge={p.is_captain ? <CapBadge /> : p.is_vice_captain ? <CapBadge vice /> : null}
              right={<SquadControls p={p} onCap={setCap} onRemove={remove} />}
            />
          ))}
        </div>
      )}
    </div>
  )

  const roleFilter = (
    <div style={{ display: 'flex', gap: 6 }}>
      {ROLE_ORDER.map(r => {
        const on = filter === r
        return (
          <button key={r} onClick={() => setFilter(r)} style={{
            flex: 1, textAlign: 'center', borderRadius: 10, padding: '7px 4px', border: 'none', cursor: 'pointer',
            font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`,
            background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--dim)',
          }}>
            {ROLE_LABEL[r].replace('Wicketkeeper', 'Keeper')}<br /><span style={{ opacity: 0.75 }}>{byRole(r)}/{quota[r] || 0}</span>
          </button>
        )
      })}
    </div>
  )

  const searchSort = (
    <div style={{ display: 'flex', gap: 8 }}>
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
  )

  const poolList = (
    <div style={desktop
      ? { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 }
      : { display: 'flex', flexDirection: 'column', gap: 7 }}>
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
              background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)',
              color: on ? 'var(--ink)' : 'var(--dim)', border: on ? 'none' : '1px solid var(--hairline2)',
            }}>{on ? '✓' : '+'}</span>}
          />
        )
      })}
    </div>
  )

  if (desktop) {
    return (
      <div>
        <ScreenTitle title="Pick Squad" sub={`${size}-man · ${money(budget)} budget`} back onBack={() => nav('team')} />
        <div style={{ display: 'grid', gridTemplateColumns: '420px 1fr', gap: 22, alignItems: 'start', paddingTop: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {tiles}
            {nameField}
            {saveBtn}
            {squadSection}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {roleFilter}
            {searchSort}
            <SectionLabel>Player pool · {list.length}</SectionLabel>
            {poolList}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <ScreenTitle title="Pick Squad" sub={`${size}-man · ${money(budget)} budget`} back onBack={() => nav('team')} />

      <div style={{ padding: '14px 0 0' }}>{tiles}</div>
      <div style={{ padding: '12px 0 0' }}>{nameField}</div>
      <div style={{ paddingTop: 12 }}>{saveBtn}</div>

      <div style={{ paddingTop: 6 }}>{squadSection}</div>

      <div style={{ padding: '14px 0 0' }}>{roleFilter}</div>
      <div style={{ padding: '12px 0 0' }}>{searchSort}</div>

      <button onClick={() => setPoolOpen(o => !o)} style={{
        display: 'flex', alignItems: 'center', width: '100%', background: 'none', border: 'none', cursor: 'pointer',
        padding: '14px 2px 7px',
      }}>
        <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)' }}>Player pool · {list.length}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--faint)', font: `700 11px 'Hanken Grotesk'` }}>{poolOpen ? 'Hide ▾' : 'Show ▸'}</span>
      </button>

      {poolOpen && poolList}

      <div style={{ paddingTop: 16 }}>{saveBtn}</div>
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
  background: on ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)', color: on ? 'var(--ink)' : 'var(--faint)',
})
