// Draft — list of draft leagues, the async draft room (on-the-clock banner, best
// available, recent picks) and the post-draft ladder. Restyle of the original
// draft flow; the data contract (fanDraft*) is unchanged.
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, money, Btn, ROLE_LABEL, ROLE_ORDER } from './ui'
import { ScreenTitle, SectionLabel, PlayerRow } from './shell'
import { LadderRow } from './Ladder'

export default function Draft({ token, flash, fail }) {
  const [leagues, setLeagues] = useState(null)
  const [active, setActive] = useState(null)
  const [state, setState] = useState(null)
  const [ladder, setLadder] = useState(null)

  const loadLeagues = useCallback(() => api.fanDraftLeagues(token).then(d => setLeagues(d.leagues)).catch(() => setLeagues([])), [token])
  useEffect(() => { loadLeagues() }, [loadLeagues])

  const refresh = useCallback(async (id) => {
    try {
      const s = await api.fanDraftState(token, id); setState(s)
      if (s.status === 'complete') setLadder(await api.fanDraftLadder(token, id).catch(() => null))
    } catch (e) { fail(e) }
  }, [token, fail])

  useEffect(() => {
    if (!active || state?.status !== 'in_progress') return
    const t = setInterval(() => refresh(active), 10000)
    return () => clearInterval(t)
  }, [active, state?.status, refresh])

  const enter = async (id) => { setActive(id); setState(null); setLadder(null); await refresh(id) }
  const join = async (id) => { try { await api.fanJoinDraft(token, id); flash('Joined the draft league.'); await loadLeagues() } catch (e) { fail(e) } }
  const pick = async (pid) => { try { await api.fanDraftPick(token, active, pid); await refresh(active) } catch (e) { fail(e) } }

  if (active) return <DraftBoard state={state} ladder={ladder} onBack={() => { setActive(null); setState(null) }} onPick={pick} />

  if (leagues === null) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  return (
    <div>
      <ScreenTitle title="Draft" sub="Snake & auction leagues" />
      {!leagues.length
        ? <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>No draft leagues yet. Your club admin sets these up.</p>
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9, paddingTop: 14 }}>
            {leagues.map(lg => (
              <div key={lg.id} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, padding: '12px 14px' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ font: `700 14px 'Hanken Grotesk'`, color: 'var(--text)' }}>{lg.name}</div>
                  <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 1 }}>{lg.draft_type} · {lg.scoring_type === 'h2h' ? 'head-to-head' : 'total points'} · {lg.members}/{lg.capacity} · {lg.draft_status || 'not started'}</div>
                </div>
                {lg.joined
                  ? <Btn onClick={() => enter(lg.id)} style={{ padding: '8px 14px', fontSize: 12 }}>Open</Btn>
                  : (!lg.draft_status || lg.draft_status === 'scheduled')
                    ? <Btn variant="soft" onClick={() => join(lg.id)} style={{ padding: '8px 14px', fontSize: 12 }}>Join</Btn>
                    : <span style={{ font: `600 11px 'Hanken Grotesk'`, color: 'var(--faintest)' }}>drafting</span>}
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

function DraftBoard({ state, ladder, onBack, onPick }) {
  if (!state) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  const needed = (role) => (state.quota?.[role] || 0) - (state.my_role_counts?.[role] || 0)
  const need = ROLE_ORDER.filter(r => needed(r) > 0).map(r => `${needed(r)} ${ROLE_LABEL[r].toLowerCase()}`).join(', ') || 'nothing'

  return (
    <div>
      <ScreenTitle title="Draft room" back onBack={onBack} />
      {state.status === 'not_started' && <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, padding: 16, font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 14 }}>The draft hasn't started yet. Your admin will kick it off.</div>}

      {state.status === 'in_progress' && (
        <>
          <div style={{ margin: '14px 0 0', background: tintBg(16, 'var(--bg)'), border: `1px solid ${tintBg(40)}`, borderRadius: 13, padding: '13px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--pb-accent, #8C82F0)', boxShadow: '0 0 10px var(--pb-accent, #8C82F0)' }} />
              <span style={{ font: `800 13px ${DISP}`, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text)' }}>
                {state.my_turn ? "You're on the clock" : `On the clock: ${state.on_clock?.manager || '—'}`}
              </span>
            </div>
            <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 6 }}>{state.my_turn ? `Still need: ${need}` : `Round ${state.on_clock?.round ?? ''}`}</div>
          </div>

          {state.my_turn && (
            <>
              <SectionLabel>Best available</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
                {state.available.filter(p => needed(p.role) > 0).slice(0, 60).map(p => (
                  <PlayerRow key={p.player_id} name={p.name} sub={`${ROLE_LABEL[p.role]} · ${money(p.price)}`} avatarSize={32}
                    right={<Btn onClick={() => onPick(p.player_id)} style={{ padding: '6px 12px', fontSize: 11.5 }}>Draft</Btn>} />
                ))}
              </div>
            </>
          )}

          <SectionLabel>Recent picks</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {state.picks.slice().reverse().slice(0, 12).map(pk => (
              <div key={pk.pick} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 2px' }}>
                <span style={{ font: `700 12px ${DISP}`, color: 'var(--faintest)', width: 24, fontVariantNumeric: 'tabular-nums' }}>{pk.pick}.</span>
                <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{pk.player}</span>
                <span style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{pk.manager}{pk.auto ? ' (auto)' : ''}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {state.status === 'complete' && (
        <>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, padding: 14, font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '14px 0' }}>Draft complete. Your squad now scores each round.</div>
          {ladder && (ladder.type === 'h2h'
            ? ladder.ladder.map((r, i) => <LadderRow key={i} r={{ rank: r.rank, team_name: r.team_name, manager: `${r.w}-${r.l}-${r.d}`, points: r.pts, rank_delta: 0 }} compact />)
            : ladder.ladder.map((r, i) => <LadderRow key={i} r={{ ...r, rank_delta: 0 }} compact />))}
        </>
      )}
    </div>
  )
}
