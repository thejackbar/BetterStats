// Round insights: the top 10 scorers of a round, the players managers traded in and out most, and the biggest
// price risers and fallers, with a round picker. Past rounds are all here, so the club can step back through the
// season. The open round shows trades so far; points and price moves arrive once it is confirmed.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, money, tintBg, cardSx, Avatar, GREEN, RED, ROLE_SHORT } from './ui'
import { ScreenTitle } from './shell'
import RoundPicker from './RoundPicker'

const Kicker = ({ children }) => (
  <div style={{ font: `700 9.5px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--faint)' }}>{children}</div>
)

// One ranked list card. `rows` is already cut to 10; `value(r)` is the figure on the right, `sub(r)` the small line.
function BoardCard({ title, testid, rows, empty, value, sub, onOpen }) {
  return (
    <div data-testid={testid} style={{ ...cardSx, padding: '12px 14px 6px', borderRadius: 16 }}>
      <Kicker>{title}</Kicker>
      {!rows.length && <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '10px 0 8px' }}>{empty}</p>}
      {rows.map((r, i) => (
        <button key={r.player_id} onClick={() => onOpen(r)} aria-label={`Open ${r.name}`} style={{
          display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', padding: '8px 0', cursor: 'pointer',
          background: 'transparent', border: 'none', borderTop: i ? '1px solid var(--surface2)' : 'none', marginTop: i ? 0 : 6,
        }}>
          <span style={{ width: 18, textAlign: 'center', font: `700 13px ${DISP}`, color: i === 0 ? 'var(--accent-strong)' : 'var(--faint)', fontVariantNumeric: 'tabular-nums' }}>{i + 1}</span>
          <Avatar name={r.name} photoUrl={r.photo_url} size={30} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: `700 13px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</div>
            <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{ROLE_SHORT[r.role] || r.role} · {sub(r)}</div>
          </div>
          {value(r)}
        </button>
      ))}
    </div>
  )
}

const big = (text, color = 'var(--text)') => (
  <span style={{ font: `800 18px ${DISP}`, color, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{text}</span>
)
const mag = (v) => Math.abs(v).toFixed(1)

export default function Insights({ token, desktop, nav }) {
  const [rounds, setRounds] = useState(null)
  const [sel, setSel] = useState(null)        // chosen round number; null = the server's default
  const [cache, setCache] = useState({})      // round number -> insights
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (sel != null && cache[sel]) return
    let on = true
    setFailed(false)
    api.fanRoundInsights(token, sel)
      .then(d => {
        if (!on) return
        setRounds(d.rounds)
        if (d.selected) {
          setCache(c => ({ ...c, [d.selected.number]: d.selected }))
          setSel(prev => prev ?? d.selected.number)
        }
      })
      .catch(() => on && setFailed(true))
    return () => { on = false }
  }, [token, sel, cache])

  const title = <ScreenTitle title="Round insights" sub="Top players, trades and price moves" />
  if (failed && !rounds) return <div>{title}<p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>Insights could not be loaded. Try again in a moment.</p></div>
  if (!rounds) return <div>{title}<p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'`, paddingTop: 16 }}>Loading…</p></div>
  if (!rounds.length) {
    return <div>{title}<p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>Nothing to show yet. Insights start once the first round is open.</p></div>
  }

  const d = sel != null ? cache[sel] : null
  const open = (r) => nav('player', { playerId: r.player_id, from: 'insights' })
  const scored = d?.status === 'scored'
  const waiting = 'Shown once this round is confirmed.'
  const teamsOf = (n) => (d?.teams ? `${n} of ${d.teams} teams` : `${n} ${n === 1 ? 'team' : 'teams'}`)

  const boards = d && [
    <BoardCard key="top" testid="insights-top" title="Top 10 players" rows={d.top_scorers} empty={scored ? 'Nobody scored in this round.' : waiting}
      value={r => big(pts(r.points))} sub={r => `${teamsOf(r.picked_by)} had them`} onOpen={open} />,
    <BoardCard key="in" testid="insights-in" title="Most traded in" rows={d.traded_in} empty="No transfers into this round."
      value={r => big(r.count, GREEN)} sub={r => `${r.price != null ? money(r.price) : 'No price'} · ${r.count === 1 ? '1 team' : `${r.count} teams`}`} onOpen={open} />,
    <BoardCard key="out" testid="insights-out" title="Most traded out" rows={d.traded_out} empty="No transfers out of this round."
      value={r => big(r.count, RED)} sub={r => `${r.price != null ? money(r.price) : 'No price'} · ${r.count === 1 ? '1 team' : `${r.count} teams`}`} onOpen={open} />,
    <BoardCard key="up" testid="insights-risers" title="Biggest price risers" rows={d.risers} empty={scored ? 'No price rises after this round.' : waiting}
      value={r => big(`▲ ${mag(r.move)}`, GREEN)} sub={r => `now ${money(r.price)}`} onOpen={open} />,
    <BoardCard key="down" testid="insights-fallers" title="Biggest price fallers" rows={d.fallers} empty={scored ? 'No price falls after this round.' : waiting}
      value={r => big(`▼ ${mag(r.move)}`, RED)} sub={r => `now ${money(r.price)}`} onOpen={open} />,
  ]

  return (
    <div>
      {title}
      <RoundPicker rounds={rounds} value={sel} onChange={setSel} />
      {d && !scored && (
        <div style={{ background: tintBg(10, 'var(--surface)'), border: `1px solid ${tintBg(30)}`, borderRadius: 12, padding: '9px 12px', marginBottom: 12, font: `500 12px 'Hanken Grotesk'`, color: 'var(--dim)' }}>
          This round is still open. Trades shown are the ones made so far. Top players and price moves come in once it is confirmed.
        </div>
      )}
      {!d && <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>{failed ? 'This round could not be loaded.' : 'Loading…'}</p>}
      {d && (
        desktop ? (
          // Top 10 on the left, the trade and price boards stacked on the right, so the columns stay level.
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>{boards[0]}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>{boards.slice(1)}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>{boards}</div>
        )
      )}
    </div>
  )
}
