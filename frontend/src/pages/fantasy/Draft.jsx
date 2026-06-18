// Draft — list of draft leagues, then the async draft room. Snake drafts use the
// on-the-clock pick board; auction drafts use the nominate-and-bid room (live lot,
// budget, recent lots). Both end on the post-draft ladder. The data contract is
// fanDraft* (state carries `draft_type` so the room picks the right board).
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, money, Btn, Field, StatTile, ROLE_LABEL, ROLE_ORDER, GREEN, RED } from './ui'
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
  const back = () => { setActive(null); setState(null); setLadder(null) }
  const pick = async (pid) => { try { await api.fanDraftPick(token, active, pid); await refresh(active) } catch (e) { fail(e) } }
  const nominate = async (pid, bid) => { try { await api.fanDraftNominate(token, active, pid, bid); flash('Player nominated.'); await refresh(active) } catch (e) { fail(e) } }
  const bid = async (amt) => { try { await api.fanDraftBid(token, active, amt); await refresh(active) } catch (e) { fail(e) } }

  if (active) {
    return state?.draft_type === 'auction'
      ? <AuctionBoard state={state} ladder={ladder} onBack={back} onNominate={nominate} onBid={bid} />
      : <DraftBoard state={state} ladder={ladder} onBack={back} onPick={pick} />
  }

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

// ── snake draft room ───────────────────────────────────────────────────────────
function DraftBoard({ state, ladder, onBack, onPick }) {
  if (!state) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  const needed = (role) => (state.quota?.[role] || 0) - (state.my_role_counts?.[role] || 0)
  const need = ROLE_ORDER.filter(r => needed(r) > 0).map(r => `${needed(r)} ${ROLE_LABEL[r].toLowerCase()}`).join(', ') || 'nothing'

  return (
    <div>
      <ScreenTitle title="Draft room" back onBack={onBack} />
      {state.status === 'not_started' && <NotStarted />}

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

      {state.status === 'complete' && <DraftComplete ladder={ladder} />}
    </div>
  )
}

// ── auction draft room ───────────────────────────────────────────────────────
function AuctionBoard({ state, ladder, onBack, onNominate, onBid }) {
  if (!state) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  return (
    <div>
      <ScreenTitle title="Auction room" sub="Nominate & bid" back onBack={onBack} />
      {state.status === 'not_started' && <NotStarted />}

      {state.status === 'in_progress' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 7, paddingTop: 14 }}>
            <StatTile label="In the bank" value={money(state.my.remaining)} color={GREEN} />
            <StatTile label="Max bid" value={money(state.my.max_bid)} />
            <StatTile label="Squad" value={`${state.my.filled}/${state.squad_size}`} />
            <StatTile label="Spent" value={money(state.my.spent)} />
          </div>

          {state.lot
            ? <LotCard lot={state.lot} onBid={onBid} />
            : state.my_nomination
              ? <NominatePanel state={state} onNominate={onNominate} />
              : (
                <div style={{ margin: '14px 0 0', ...{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14 }, padding: '14px 16px', font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
                  Waiting for <b style={{ color: 'var(--text)' }}>{state.nominator || '—'}</b> to nominate a player…
                </div>
              )}

          <MySquad my={state.my} />
          <Rosters managers={state.managers} />

          {!!state.picks.length && (
            <>
              <SectionLabel>Recent buys</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                {state.picks.slice().reverse().slice(0, 12).map(pk => (
                  <div key={pk.pick} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 2px' }}>
                    <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{pk.player}</span>
                    <span style={{ font: `700 12px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{money(pk.price)}</span>
                    <span style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', width: 96, textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{pk.manager}{pk.auto ? ' (auto)' : ''}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {state.status === 'complete' && <DraftComplete ladder={ladder} />}
    </div>
  )
}

function LotCard({ lot, onBid }) {
  const left = useCountdown(lot.deadline)
  const [amount, setAmount] = useState(lot.min_next_bid)
  useEffect(() => { setAmount(lot.min_next_bid) }, [lot.player_id, lot.min_next_bid])

  const amt = Number(amount)
  const valid = lot.i_can_bid && amt >= lot.min_next_bid && amt <= lot.max_bid
  const bump = (d) => setAmount(a => Math.min(lot.max_bid, Math.max(lot.min_next_bid, Number(a || 0) + d)))

  let blocked = null
  if (!lot.i_can_bid) {
    blocked = lot.high_bidder_is_me ? "You're the top bidder."
      : lot.max_bid < lot.min_next_bid ? "You can't afford the next bid and still fill your squad."
        : 'You already have enough in this role.'
  }

  return (
    <div style={{ margin: '14px 0 0', background: tintBg(16, 'var(--bg)'), border: `1px solid ${tintBg(40)}`, borderRadius: 14, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--accent-strong)' }}>Up for auction</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, font: `700 12px ${DISP}`, color: left === 'closing…' ? RED : 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--pb-accent, #8C82F0)', boxShadow: '0 0 8px var(--pb-accent, #8C82F0)' }} />
          {left}
        </span>
      </div>
      <div style={{ font: `800 22px ${DISP}`, color: 'var(--text)', marginTop: 8, lineHeight: 1.05 }}>{lot.name}</div>
      <div style={{ font: `600 10.5px 'Hanken Grotesk'`, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 3 }}>
        {ROLE_LABEL[lot.role] || lot.role} · nominated by {lot.nominator}{lot.auto ? ' (auto)' : ''}
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 12 }}>
        <span style={{ font: `800 30px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{money(lot.high_bid)}</span>
        <span style={{ font: `600 12px 'Hanken Grotesk'`, color: 'var(--dim)' }}>top bid · {lot.high_bidder_is_me ? 'you' : (lot.high_bidder || '—')}</span>
      </div>

      {lot.i_can_bid ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
            <Field value={amount} onChange={e => setAmount(e.target.value)} type="number" inputMode="numeric" style={{ flex: 1, padding: '11px 12px' }} />
            <Btn variant="soft" onClick={() => bump(1)} style={{ padding: '11px 13px' }}>+1</Btn>
            <Btn variant="soft" onClick={() => bump(5)} style={{ padding: '11px 13px' }}>+5</Btn>
          </div>
          <Btn full onClick={() => onBid(amt)} disabled={!valid} style={{ marginTop: 8 }}>Bid {money(amt)}</Btn>
          <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 7, textAlign: 'center' }}>Min {money(lot.min_next_bid)} · your max {money(lot.max_bid)}</div>
        </div>
      ) : (
        <div style={{ marginTop: 12, font: `600 12px 'Hanken Grotesk'`, color: lot.high_bidder_is_me ? GREEN : 'var(--faint)' }}>{blocked}</div>
      )}
    </div>
  )
}

function NominatePanel({ state, onNominate }) {
  const [open, setOpen] = useState(Math.max(1, Math.min(1, state.my.max_bid)))
  const [q, setQ] = useState('')
  const needRoles = ROLE_ORDER.filter(r => (state.my.needed?.[r] || 0) > 0)
  const needLabel = needRoles.map(r => `${state.my.needed[r]} ${ROLE_LABEL[r].toLowerCase()}`).join(', ') || 'nothing'
  const ql = q.trim().toLowerCase()
  const list = state.available
    .filter(p => (state.my.needed?.[p.role] || 0) > 0)
    .filter(p => !ql || p.name.toLowerCase().includes(ql))
    .slice(0, 60)
  const ob = Math.max(1, Math.min(Number(open) || 1, state.my.max_bid))

  return (
    <div style={{ margin: '14px 0 0' }}>
      <div style={{ background: tintBg(16, 'var(--bg)'), border: `1px solid ${tintBg(40)}`, borderRadius: 13, padding: '13px 14px' }}>
        <div style={{ font: `800 13px ${DISP}`, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text)' }}>Your nomination</div>
        <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 6 }}>Put a player up for auction. Still need: {needLabel}</div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <span style={{ font: `600 11px 'Hanken Grotesk'`, color: 'var(--faint)', whiteSpace: 'nowrap' }}>Opening bid</span>
        <Field value={open} onChange={e => setOpen(e.target.value)} type="number" inputMode="numeric" style={{ width: 90, padding: '10px 12px' }} />
        <span style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>max {money(state.my.max_bid)}</span>
      </div>

      <div style={{ marginTop: 10 }}>
        <Field value={q} onChange={e => setQ(e.target.value)} placeholder="Search players…" style={{ padding: '11px 14px' }} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto', marginTop: 10 }}>
        {list.length === 0 && <p style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '8px 2px' }}>No available players in a role you still need.</p>}
        {list.map(p => (
          <PlayerRow key={p.player_id} name={p.name} sub={`${ROLE_LABEL[p.role]} · base ${money(p.price)}`} avatarSize={32}
            right={<Btn onClick={() => onNominate(p.player_id, ob)} style={{ padding: '6px 12px', fontSize: 11.5 }}>Nominate</Btn>} />
        ))}
      </div>
    </div>
  )
}

function MySquad({ my }) {
  if (!my.squad?.length) return null
  const sorted = my.squad.slice().sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role))
  return (
    <>
      <SectionLabel>Your squad ({my.filled})</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {sorted.map(p => (
          <PlayerRow key={p.player_id} name={p.name} sub={ROLE_LABEL[p.role] || p.role} avatarSize={30}
            tone="picked" right={<span style={{ font: `700 14px ${DISP}`, color: 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{money(p.price)}</span>} />
        ))}
      </div>
    </>
  )
}

function Rosters({ managers }) {
  if (!managers?.length) return null
  return (
    <>
      <SectionLabel>Managers</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {managers.map(m => (
          <div key={m.manager_id} style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '7px 11px', borderRadius: 11,
            background: m.is_me ? tintBg(12, 'var(--bg)') : 'var(--surface)',
            border: m.is_me ? `1px solid ${tintBg(34)}` : '1px solid var(--hairline)',
          }}>
            <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{m.name}{m.is_me ? ' (you)' : ''}</span>
            <span style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{m.filled} picks</span>
            <span style={{ width: 64, textAlign: 'right', font: `700 12px ${DISP}`, color: m.done ? 'var(--faintest)' : GREEN, fontVariantNumeric: 'tabular-nums' }}>{m.done ? 'full' : money(m.remaining)}</span>
          </div>
        ))}
      </div>
    </>
  )
}

function NotStarted() {
  return <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, padding: 16, font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 14 }}>The draft hasn't started yet. Your admin will kick it off.</div>
}

function DraftComplete({ ladder }) {
  return (
    <>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, padding: 14, font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '14px 0' }}>Draft complete. Your squad now scores each round.</div>
      {ladder && (ladder.type === 'h2h'
        ? ladder.ladder.map((r, i) => <LadderRow key={i} r={{ rank: r.rank, team_name: r.team_name, manager: `${r.w}-${r.l}-${r.d}`, points: r.pts, rank_delta: 0 }} compact />)
        : ladder.ladder.map((r, i) => <LadderRow key={i} r={{ ...r, rank_delta: 0 }} compact />))}
    </>
  )
}

// Live countdown to an ISO deadline, ticking each second.
function useCountdown(deadline) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!deadline) return undefined
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [deadline])
  if (!deadline) return '—'
  const ms = new Date(deadline).getTime() - now
  if (ms <= 0) return 'closing…'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${ss}s`
  return `${ss}s`
}
