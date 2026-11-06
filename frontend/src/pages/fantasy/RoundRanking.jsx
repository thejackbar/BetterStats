// Round winners: who topped each scored round, the full table for any round, and how many rounds each team
// has won. Every round already scored is here, so the club can walk back through the season round by round.
// A tie for first is a shared win. Opened from the Ladder screen's "Round winners" tab.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, tintBg, cardSx, AMBER } from './ui'
import RoundPicker from './RoundPicker'

const CHIP_LABEL = { wildcard: 'Wildcard', free_hit: 'Free hit', bench_boost: 'Bench boost', triple_captain: 'Triple captain' }

const winnerNames = (ws) => ws.map(w => w.team_name).join(' and ')

const Kicker = ({ children, color = 'var(--faint)' }) => (
  <div style={{ font: `700 9.5px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color }}>{children}</div>
)

function WinnerCard({ round }) {
  const ws = round.winners || []
  if (!ws.length) {
    return (
      <div data-testid="round-winner" style={{ ...cardSx, padding: 16 }}>
        <Kicker>Round {round.number} winner</Kicker>
        <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--dim)', margin: '8px 0 0' }}>No winner. Nobody scored in this round.</p>
      </div>
    )
  }
  const shared = ws.length > 1
  return (
    <div data-testid="round-winner" style={{ background: tintBg(10, 'var(--surface)'), border: `1px solid ${tintBg(32)}`, borderRadius: 16, padding: 16 }}>
      <Kicker color={AMBER}>{shared ? `Round ${round.number} shared win` : `Round ${round.number} winner`}</Kicker>
      {ws.map(w => (
        <div key={w.squad_id} style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
          <span aria-hidden style={{ fontSize: 22, lineHeight: 1 }}>🏆</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: `800 17px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {w.team_name}{w.you && <span style={{ marginLeft: 8, font: `700 9px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #06B6D4)', padding: '1px 5px', borderRadius: 4, verticalAlign: 'middle' }}>YOU</span>}
            </div>
            <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>
              {w.manager}{w.chip ? ` · ${CHIP_LABEL[w.chip] || w.chip}` : ''}
            </div>
          </div>
          <div style={{ font: `800 26px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(w.points)}</div>
        </div>
      ))}
      {round.margin != null && (
        <div style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 10 }}>
          {pts(round.margin)} {round.margin === 1 ? 'point' : 'points'} clear of second.
        </div>
      )}
    </div>
  )
}

function TableRow({ r }) {
  const base = { display: 'flex', alignItems: 'center', gap: 11 }
  const rank = (
    <span style={{ width: 24, textAlign: 'center', font: `700 16px ${DISP}`, color: r.you ? 'var(--text)' : 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{r.rank}</span>
  )
  const body = (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ font: `700 13.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {r.winner && <span aria-label="Round winner" style={{ marginRight: 5 }}>🏆</span>}
        {r.team_name}
        {r.you && <span style={{ marginLeft: 6, font: `700 9px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #06B6D4)', padding: '1px 5px', borderRadius: 4, verticalAlign: 'middle' }}>YOU</span>}
      </div>
      <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: r.you ? 'var(--accent-strong)' : 'var(--faint)' }}>
        {r.manager}{r.chip ? ` · ${CHIP_LABEL[r.chip] || r.chip}` : ''}{r.transfer_hit ? ` · -${r.transfer_hit} transfer hit` : ''}
      </div>
    </div>
  )
  const points = <span style={{ minWidth: 50, textAlign: 'right', font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</span>
  if (r.you) {
    return <div style={{ ...base, padding: '11px 12px', margin: '3px 0', borderRadius: 13, background: tintBg(14, 'var(--bg)'), border: `1px solid ${tintBg(40)}` }}>{rank}{body}{points}</div>
  }
  return <div style={{ ...base, padding: '10px 12px', borderBottom: '1px solid var(--surface2)' }}>{rank}{body}{points}</div>
}

export default function RoundRanking({ token, desktop }) {
  const [list, setList] = useState(null)
  const [sel, setSel] = useState(null)
  const [tables, setTables] = useState({})

  useEffect(() => {
    let on = true
    api.fanRoundWinners(token).then(d => {
      if (!on) return
      setList(d)
      // Open on the latest scored round.
      setSel(prev => prev ?? (d.rounds.length ? d.rounds[d.rounds.length - 1].number : null))
    }).catch(() => on && setList({ rounds: [], tally: [], failed: true }))
    return () => { on = false }
  }, [token])

  useEffect(() => {
    if (sel == null || tables[sel]) return
    let on = true
    api.fanRoundRanking(token, sel)
      .then(d => on && setTables(t => ({ ...t, [sel]: d })))
      .catch(() => on && setTables(t => ({ ...t, [sel]: { failed: true } })))
    return () => { on = false }
  }, [token, sel, tables])

  if (!list) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  const rounds = list.rounds || []
  if (!rounds.length) {
    return (
      <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>
        {list.failed ? 'Round winners could not be loaded. Try again in a moment.' : 'No round has been scored yet. Winners show up here as each round is confirmed.'}
      </p>
    )
  }

  const cur = rounds.find(r => r.number === sel) || null
  const table = cur ? tables[cur.number] : null
  const picker = <RoundPicker rounds={rounds} value={sel} onChange={setSel} />

  const ranking = table && !table.failed ? table.ranking || [] : null
  const main = (
    <div>
      {picker}
      {cur && <WinnerCard round={table && !table.failed ? table : cur} />}
      <div style={{ ...cardSx, padding: '4px 4px 8px', marginTop: 14, borderRadius: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '11px 12px 6px' }}>
          <span style={{ width: 24, font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: 'center' }}>#</span>
          <span style={{ flex: 1, font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>Team</span>
          <span style={{ minWidth: 50, textAlign: 'right', font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>Round pts</span>
        </div>
        {ranking == null && <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'`, padding: '8px 12px' }}>{table?.failed ? 'This round could not be loaded.' : 'Loading…'}</p>}
        {ranking && ranking.map(r => <TableRow key={r.squad_id} r={r} />)}
      </div>
    </div>
  )

  const history = (
    <div>
      <div style={{ ...cardSx, padding: '12px 14px 6px', borderRadius: 16 }}>
        <Kicker>Round by round</Kicker>
        <div data-testid="round-history" style={{ marginTop: 6 }}>
          {[...rounds].reverse().map(r => (
            <button key={r.number} onClick={() => setSel(r.number)} aria-label={`Show round ${r.number}`} style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', padding: '9px 0', cursor: 'pointer',
              background: 'transparent', border: 'none', borderBottom: '1px solid var(--surface2)',
            }}>
              <span style={{ width: 28, font: `700 13px ${DISP}`, color: r.number === sel ? 'var(--accent-strong)' : 'var(--faint)' }}>R{r.number}</span>
              <span style={{ flex: 1, minWidth: 0, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.winners.length ? winnerNames(r.winners) : 'No winner'}
              </span>
              {r.winners.length > 0 && <span style={{ font: `700 13px ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.top_points)}</span>}
            </button>
          ))}
        </div>
      </div>
      {list.tally?.length > 0 && (
        <div style={{ ...cardSx, padding: '12px 14px 6px', borderRadius: 16, marginTop: 14 }}>
          <Kicker>Most round wins</Kicker>
          <div data-testid="round-tally" style={{ marginTop: 6 }}>
            {list.tally.map(t => (
              <div key={t.squad_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderBottom: '1px solid var(--surface2)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {t.team_name}{t.you && <span style={{ marginLeft: 6, font: `700 9px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #06B6D4)', padding: '1px 5px', borderRadius: 4, verticalAlign: 'middle' }}>YOU</span>}
                  </div>
                  <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>Rounds {t.rounds.join(', ')}</div>
                </div>
                <span style={{ font: `800 18px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{t.wins}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )

  if (desktop) {
    return <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 22, alignItems: 'start' }}>{main}<div style={{ paddingTop: 14 }}>{history}</div></div>
  }
  return <div>{main}<div style={{ marginTop: 18 }}>{history}</div></div>
}
