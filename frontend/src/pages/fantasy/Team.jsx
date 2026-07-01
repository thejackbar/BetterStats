// My Team — the manager's squad: a stat ribbon, the round-lock pill, and the XI
// grouped by role with photo-led rows. With no squad it shows the onboarding
// steps instead. Captain / vice can be set inline while the round is open.
import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import {
  Aurora, StatTile, DISP, tintBg, mix, ROLE_ORDER, ROLE_GROUP, ROLE_LABEL,
  money, pts, Btn, CapBadge, Avatar,
} from './ui'
import { PlayerRow, RowPoints, SectionLabel } from './shell'

const ord = (n) => {
  if (n == null) return ''
  if (n % 100 >= 11 && n % 100 <= 13) return 'th'
  return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'
}
const teamInitials = (name) => (name || 'My XI').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()

export function Onboarding({ manager, season, onBuild }) {
  const steps = [
    ['Build your squad', 'Pick 12 within $100'],
    ['Name your captain', 'Doubles their points'],
    ['Join the clubhouse', 'Play your mates'],
  ]
  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 20, marginBottom: 6 }}>
        <Aurora style={{ inset: '-10% -15% 20%', height: 'auto', bottom: '20%' }} blur={48} />
        <div style={{ position: 'relative', textAlign: 'center', padding: '24px 6px 18px' }}>
          <div style={{ font: `800 30px ${DISP}`, lineHeight: 0.95, textTransform: 'uppercase', color: 'var(--text)' }}>
            Welcome,<br />{(manager?.display_name || 'player').split(/\s+/)[0]}
          </div>
          <div style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 10, lineHeight: 1.5, maxWidth: 280, margin: '10px auto 0' }}>
            You're in for {season?.name || 'this season'}. Three quick steps and you're on the ladder.
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {steps.map(([t, s], i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 13, padding: '13px 14px', borderRadius: 14,
            background: 'var(--surface)', border: '1px solid var(--hairline)', opacity: i === 0 ? 1 : 0.6,
          }}>
            <div style={{
              width: 30, height: 30, borderRadius: 9, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center',
              font: `800 14px ${DISP}`, color: i === 0 ? 'var(--ink)' : 'var(--dim)',
              background: i === 0 ? 'var(--pb-accent, #06B6D4)' : 'var(--surface2)',
            }}>{i + 1}</div>
            <div style={{ flex: 1 }}>
              <div style={{ font: `700 13.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{t}</div>
              <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{s}</div>
            </div>
            {i === 0 && <span style={{ color: 'var(--faint)' }}>{'›'}</span>}
          </div>
        ))}
      </div>
      <div style={{ paddingTop: 16 }}>
        <Btn full onClick={onBuild} style={{ padding: 14, boxShadow: `0 10px 26px -8px ${tintBg(60)}` }}>Build my squad</Btn>
      </div>
    </div>
  )
}

export default function MyTeam({ token, manager, squad, season, round, onChange, flash, fail, nav, desktop }) {
  const [openId, setOpenId] = useState(null)
  const [gwPts, setGwPts] = useState(null)   // player_id -> last-round base points
  const [snapshot, setSnapshot] = useState(null)   // club-ladder snapshot for the desktop rail
  const active = season?.status === 'active'
  const locked = !!round?.locked

  useEffect(() => {
    if (!squad) return
    let on = true
    api.fanRound(token).then(d => {
      if (!on || !d?.mine?.lineup) return
      const m = {}
      d.mine.lineup.forEach(e => { m[e.player_id] = e.points })
      setGwPts(m)
    }).catch(() => {})
    return () => { on = false }
  }, [token, squad])

  useEffect(() => {
    if (!desktop || !squad) return
    let on = true
    api.fanLadder(token).then(d => { if (on) setSnapshot(d.ladder || []) }).catch(() => {})
    return () => { on = false }
  }, [token, desktop, squad])

  if (!squad) return <Onboarding manager={manager} season={season} onBuild={() => nav('pick')} />

  const rank = squad.overall_rank
  const stats = [
    ['Total points', pts(squad.total_points)],
    [squad.last_round ? `GW${squad.last_round.number} pts` : 'GW pts', squad.last_round ? pts(squad.last_round.points) : '—'],
    ['Overall rank', rank ? `${rank}${ord(rank)}` : '—'],
    ['Squad value', squad.value != null ? money(squad.value) : '—'],
    ['In the bank', squad.budget_remaining != null ? money(squad.budget_remaining) : '—'],
    ['Free transfers', squad.free_transfers > 100 ? '∞' : (squad.free_transfers ?? '—')],
  ]

  const captainId = squad.players.find(p => p.is_captain)?.player_id
  const viceId = squad.players.find(p => p.is_vice_captain)?.player_id

  const setCap = async (pid, asVice) => {
    try {
      // Never send the same player as both captain and vice.
      const cap = asVice ? (captainId === pid ? null : captainId) : pid
      const vice = asVice ? pid : (viceId === pid ? null : viceId)
      await api.fanSetCaptain(token, cap, vice)
      flash(asVice ? 'Vice-captain updated.' : 'Captain updated.')
      setOpenId(null)
      await onChange()
    } catch (e) { fail(e) }
  }

  const lockText = round && round.status !== 'scored'
    ? (locked
      ? `Round ${round.number} is locked. You can change your team once it's scored.`
      : `Round ${round.number}${round.lock_at ? ` locks ${new Date(round.lock_at).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}` : ''}.`)
    : null

  const groups = ROLE_ORDER
    .map(role => ({ role, rows: squad.players.filter(p => p.role === role), quota: (season?.rules?.role_quota || {})[role] }))
    .filter(g => g.rows.length)

  const onPlayer = (pid) => setOpenId(openId === pid ? null : pid)
  const actions = (p) => openId === p.player_id && (
    <div style={{ display: 'flex', gap: 6, padding: '7px 2px 2px' }}>
      {active && !locked && !p.is_captain && <Btn variant="soft" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => setCap(p.player_id, false)}>Make captain</Btn>}
      {active && !locked && !p.is_vice_captain && !p.is_captain && <Btn variant="soft" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => setCap(p.player_id, true)}>Make vice</Btn>}
      <Btn variant="ghost" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => nav('player', { playerId: p.player_id })}>View profile</Btn>
    </div>
  )

  const statRibbon = (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${desktop ? 6 : 3}, 1fr)`, gap: desktop ? 10 : 7, padding: desktop ? '16px 0 4px' : '10px 0 4px' }}>
      {stats.map(([label, value]) => <StatTile key={label} label={label} value={value} />)}
    </div>
  )

  if (desktop) {
    return (
      <div>
        {statRibbon}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, paddingTop: 16, alignItems: 'start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)' }}>Your XI · team sheet</div>
              <button onClick={() => nav('pick')} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>{active ? 'Captain ›' : 'Edit squad ›'}</button>
            </div>
            {groups.map(g => (
              <div key={g.role} style={{ display: 'flex', gap: 14, alignItems: 'center', padding: '11px 0', borderTop: '1px solid var(--surface2)' }}>
                <div style={{ width: 88, flex: 'none' }}>
                  <div style={{ font: `700 13px ${DISP}`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text)' }}>{ROLE_GROUP[g.role]}</div>
                  <div style={{ font: `600 10px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 2 }}>{g.rows.length} / {g.quota}</div>
                </div>
                <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 12, flexWrap: 'nowrap', overflowX: 'auto' }}>
                  {g.rows.map(p => <PlayerCard key={p.player_id} p={p} gw={gwPts?.[p.player_id]} onClick={() => nav('player', { playerId: p.player_id })} />)}
                </div>
              </div>
            ))}
          </div>
          <RightRail squad={squad} lockText={lockText} captainId={captainId} gwPts={gwPts} snapshot={snapshot} active={active} locked={locked} nav={nav} />
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* manager tile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '8px 0 4px' }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', font: `800 12px ${DISP}`,
          background: `linear-gradient(135deg, ${mix('var(--pb-accent, #06B6D4)', 80, '#000')}, var(--pb-accent, #06B6D4))`,
        }}>{teamInitials(squad.team_name)}</div>
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ font: `700 15px 'Hanken Grotesk'`, color: 'var(--text)' }}>{squad.team_name}</div>
          <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
            {manager?.display_name}{rank ? ` · ${rank}${ord(rank)} overall` : ''}
          </div>
        </div>
      </div>

      {statRibbon}

      {lockText && (
        <div style={{ margin: '10px 0 2px', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--accent-strong)', background: tintBg(12), border: `1px solid ${tintBg(28)}` }}>
          {lockText}
        </div>
      )}

      <div style={{ paddingTop: 6 }}>
        {groups.map(g => (
          <div key={g.role}>
            <SectionLabel right={<span style={{ font: `600 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{g.rows.length}{g.quota ? ` / ${g.quota}` : ''}</span>}>{ROLE_GROUP[g.role]}</SectionLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {g.rows.map(p => (
                <div key={p.player_id}>
                  <PlayerRow
                    name={p.name} photoUrl={p.photo_url}
                    sub={`${ROLE_LABEL[p.role]} · ${money(p.purchase_price)}`}
                    badge={p.is_captain ? <CapBadge /> : p.is_vice_captain ? <CapBadge vice /> : null}
                    onClick={() => onPlayer(p.player_id)}
                    right={<RowPoints value={gwPts && gwPts[p.player_id] != null ? pts(gwPts[p.player_id]) : '—'} />}
                  />
                  {actions(p)}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, paddingTop: 16 }}>
        <Btn variant="ghost" full onClick={() => nav('pick')}>{active ? 'View / captain' : 'Edit squad'}</Btn>
        {active && <Btn variant="soft" full onClick={() => nav('transfers')}>Transfers</Btn>}
      </div>
    </div>
  )
}

// Desktop team-sheet card: a roomy horizontal card (avatar · name/role · GW
// points) — substantial enough to read well, compact enough that all four role
// groups fit on one screen. C/V badge sits by the name.
function PlayerCard({ p, gw, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: '1 1 auto', minWidth: 230, display: 'flex', alignItems: 'center', gap: 12,
      background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14,
      padding: '13px 15px', cursor: 'pointer', textAlign: 'left',
    }}>
      <Avatar name={p.name} photoUrl={p.photo_url} size={46} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ font: `700 14px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap' }}>{p.name}</span>
          {p.is_captain && <CapBadge />}
          {p.is_vice_captain && <CapBadge vice />}
        </div>
        <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 3, whiteSpace: 'nowrap' }}>{ROLE_LABEL[p.role]} · {money(p.purchase_price)}</div>
      </div>
      <div style={{ textAlign: 'right', flex: 'none' }}>
        <div style={{ font: `700 22px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{gw != null ? pts(gw) : '—'}</div>
        <div style={{ font: `600 8px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 3 }}>pts</div>
      </div>
    </button>
  )
}

function RightRail({ squad, lockText, captainId, gwPts, snapshot, active, locked, nav }) {
  const captain = squad.players.find(p => p.is_captain)
  const capBase = captain && gwPts ? gwPts[captain.player_id] : null
  const chipState = (key) => (squad.chips || []).find(c => c.key === key)?.state
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ background: tintBg(10, 'var(--surface)'), border: `1px solid ${tintBg(30)}`, borderRadius: 14, padding: 15 }}>
        <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--accent-strong)' }}>This round</div>
        {lockText && <div style={{ font: `600 12px 'Hanken Grotesk'`, color: 'var(--text)', marginTop: 6 }}>{lockText}</div>}
        {captain && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginTop: 12, background: 'var(--bg)', border: '1px solid var(--hairline)', borderRadius: 11, padding: '10px 12px' }}>
            <Avatar name={captain.name} photoUrl={captain.photo_url} size={38} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>Captain</div>
              <div style={{ font: `800 15px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{captain.name}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ font: `800 22px ${DISP}`, color: 'var(--text)', lineHeight: 1 }}>{capBase != null ? pts(capBase * 2) : '—'}</div>
              <div style={{ font: `600 8px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>×2</div>
            </div>
          </div>
        )}
        {active && !locked && (
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <ChipBtn label="Wildcard" armed={chipState('wildcard') === 'armed'} onClick={() => nav('chips')} />
            <ChipBtn label="Triple Cap" armed={chipState('triple_captain') === 'armed'} onClick={() => nav('chips')} />
          </div>
        )}
      </div>

      <div>
        <div style={{ font: `700 12px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 9 }}>Club ladder</div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, overflow: 'hidden' }}>
          {(snapshot || []).slice(0, 5).map(r => (
            <div key={r.rank} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 13px', borderBottom: '1px solid var(--surface2)', background: r.you ? tintBg(14) : 'transparent', borderLeft: r.you ? '3px solid var(--pb-accent, #06B6D4)' : '3px solid transparent' }}>
              <span style={{ width: 16, textAlign: 'center', font: `700 14px ${DISP}`, color: r.you ? 'var(--text)' : 'var(--dim)' }}>{r.rank}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{r.team_name}</span>
                {r.you && <span style={{ marginLeft: 6, font: `600 8.5px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #06B6D4)', padding: '1px 5px', borderRadius: 4 }}>YOU</span>}
              </div>
              <span style={{ font: `700 15px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</span>
            </div>
          ))}
          {snapshot && !snapshot.length && <div style={{ padding: 14, font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)' }}>No teams yet.</div>}
        </div>
        <button onClick={() => nav('ladder')} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer', marginTop: 8 }}>Full ladder ›</button>
      </div>
    </div>
  )
}

function ChipBtn({ label, armed, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, textAlign: 'center', borderRadius: 10, padding: 9, cursor: 'pointer',
      font: `700 11px 'Hanken Grotesk'`,
      background: armed ? 'var(--pb-accent, #06B6D4)' : 'var(--bg)', color: armed ? 'var(--ink)' : 'var(--text)',
      border: armed ? 'none' : '1px solid var(--hairline)',
    }}>{label}</button>
  )
}
