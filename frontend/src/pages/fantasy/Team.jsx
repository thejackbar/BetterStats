// My Team — the manager's squad: a stat ribbon, the round-lock pill, and the XI
// grouped by role with photo-led rows. With no squad it shows the onboarding
// steps instead. Captain / vice can be set inline while the round is open.
import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import {
  Aurora, StatTile, DISP, tintBg, mix, ROLE_ORDER, ROLE_GROUP, ROLE_LABEL,
  money, pts, Btn, CapBadge,
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
              background: i === 0 ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)',
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

export default function MyTeam({ token, manager, squad, season, round, onChange, flash, fail, nav }) {
  const [openId, setOpenId] = useState(null)
  const [gwPts, setGwPts] = useState(null)   // player_id -> last-round base points
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
      await api.fanSetCaptain(token, asVice ? captainId : pid, asVice ? pid : viceId)
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

  return (
    <div>
      {/* manager tile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '8px 0 4px' }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', font: `800 12px ${DISP}`,
          background: `linear-gradient(135deg, ${mix('var(--pb-accent, #8C82F0)', 80, '#000')}, var(--pb-accent, #8C82F0))`,
        }}>{teamInitials(squad.team_name)}</div>
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ font: `700 15px 'Hanken Grotesk'`, color: 'var(--text)' }}>{squad.team_name}</div>
          <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
            {manager?.display_name}{rank ? ` · ${rank}${ord(rank)} overall` : ''}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7, padding: '10px 0 4px' }}>
        {stats.map(([label, value]) => <StatTile key={label} label={label} value={value} />)}
      </div>

      {lockText && (
        <div style={{ margin: '10px 0 2px', borderRadius: 10, padding: '9px 12px', font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--accent-strong)', background: tintBg(12), border: `1px solid ${tintBg(28)}` }}>
          {lockText}
        </div>
      )}

      <div style={{ paddingTop: 6 }}>
        {ROLE_ORDER.map(role => {
          const rows = squad.players.filter(p => p.role === role)
          if (!rows.length) return null
          const quota = (season?.rules?.role_quota || {})[role]
          return (
            <div key={role}>
              <SectionLabel right={<span style={{ font: `600 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{rows.length}{quota ? ` / ${quota}` : ''}</span>}>{ROLE_GROUP[role]}</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {rows.map(p => (
                  <div key={p.player_id}>
                    <PlayerRow
                      name={p.name} photoUrl={p.photo_url}
                      sub={`${ROLE_LABEL[p.role]} · ${money(p.purchase_price)}`}
                      badge={p.is_captain ? <CapBadge /> : p.is_vice_captain ? <CapBadge vice /> : null}
                      onClick={() => setOpenId(openId === p.player_id ? null : p.player_id)}
                      right={<RowPoints value={gwPts && gwPts[p.player_id] != null ? pts(gwPts[p.player_id]) : '—'} />}
                    />
                    {openId === p.player_id && (
                      <div style={{ display: 'flex', gap: 6, padding: '7px 2px 2px' }}>
                        {active && !locked && !p.is_captain && <Btn variant="soft" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => setCap(p.player_id, false)}>Make captain</Btn>}
                        {active && !locked && !p.is_vice_captain && !p.is_captain && <Btn variant="soft" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => setCap(p.player_id, true)}>Make vice</Btn>}
                        <Btn variant="ghost" style={{ flex: 1, padding: '8px', fontSize: 12 }} onClick={() => nav('player', { playerId: p.player_id })}>View profile</Btn>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, paddingTop: 16 }}>
        <Btn variant="ghost" full onClick={() => nav('pick')}>{active ? 'View / captain' : 'Edit squad'}</Btn>
        {active && <Btn variant="soft" full onClick={() => nav('transfers')}>Transfers</Btn>}
      </div>
    </div>
  )
}
