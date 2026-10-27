// Swaps: the requests asking you, the ones you asked, and the history. Starting one, or finding a card to ask for, goes
// to the full screen builder.
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import { FindCards, RequestCard, ago, sideLine } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

const MONO = "'JetBrains Mono', monospace"
const btn = { padding: '11px 18px', borderRadius: 12, font: `700 12px ${MONO}`, letterSpacing: 1.3, textTransform: 'uppercase' }

export default function Swaps({ tab = 'asking' }) {
  const { token, club, accent, display, sponsor, basePath, load, loadSwaps } = usePC()
  const [board, setBoard] = useState(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const [msg, setMsg] = useState(location.state?.sent ? 'Swap request sent.' : '')

  const read = useCallback(() => api.availPublicSwaps(token, { history: tab === 'history' }).then((b) => { setBoard(b); setFailed(false) }).catch(() => setFailed(true)), [token, tab])
  useEffect(() => { read() }, [read])

  const answer = async (id, action) => {
    setBusy(true); setMsg('')
    try {
      await api.availPublicAnswerSwap(token, id, action)
      setMsg(action === 'accept' ? 'Swapped. The new cards are in your book.' : action === 'decline' ? 'Declined.' : 'Cancelled.')
      load()
    } catch (e) {
      setMsg(e?.message || 'That did not work.')
    } finally {
      setBusy(false)
      read(); loadSwaps()
    }
  }

  if (failed) return <div className="text-sm text-pb-faint" data-swaps-failed>Swaps could not load. Reload to try again.</div>
  if (!board) return <div className="text-sm text-pb-faint" data-swaps-loading>Loading swaps…</div>
  const ui = { club, accent, display, sponsor, busy, answer, onCounter: (sw) => navigate(`${basePath}/swaps/new`, { state: { counter: sw } }) }
  const tabs = [['', 'Asking you', board.incoming.length, 'asking'], ['/sent', 'You asked', board.outgoing.length, 'sent'], ['/history', 'History', 0, 'history']]
  const offerable = board.mine.reduce((n, c) => n + c.tradeable, 0)
  const list = tab === 'asking' ? board.incoming : tab === 'sent' ? board.outgoing : []
  return (
    <div data-screen="swaps">
      <PageHead title="Swaps" sub={`Swap any cards you hold for any cards another player holds, as many each way as you like. Nothing moves until they say yes. Requests lapse after ${board.expires_days} days.`}
        actions={<><span data-doubles-count className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint">{offerable === 0 ? 'No cards to offer yet' : `${offerable} ${offerable === 1 ? 'card' : 'cards'} you could offer`}</span>
          <Link to={`${basePath}/swaps/new`} data-swap-start style={{ ...btn, background: accent, color: onColor(accent) }}>Start a swap</Link></>} />
      <FindCards token={token} onAsk={(a) => navigate(`${basePath}/swaps/new`, { state: { ask: a } })} {...ui} />
      {msg && <div role="status" data-swap-msg className="text-sm mb-3">{msg}</div>}
      <div role="tablist" aria-label="Swaps" className="flex gap-2 mb-4 flex-wrap">
        {tabs.map(([to, label, n, key]) => (
          <Link key={key} to={`${basePath}/swaps${to}`} role="tab" aria-selected={tab === key} data-swaps-tab={key}
            className="px-4 py-2 rounded-lg text-sm font-semibold border pb-hairline" style={tab === key ? { background: accent, color: onColor(accent), borderColor: accent } : undefined}>
            {label}{n > 0 ? ` ${n}` : ''}
          </Link>
        ))}
      </div>
      {tab !== 'history' && (
        <div className="flex flex-col gap-3">
          {list.map((s) => <RequestCard key={s.id} swap={s} {...ui} />)}
          {list.length === 0 && <div className="text-sm text-pb-dim" data-no-requests>{tab === 'asking' ? 'No swap requests open.' : 'You have not asked anyone for a swap.'}</div>}
        </div>
      )}
      {tab === 'history' && (
        <div data-history>
          {board.recent.length === 0 && <div className="text-sm text-pb-dim" data-no-history>No finished swaps yet.</div>}
          {board.recent.map((s) => (
            <div key={s.id} data-swap-recent data-status={s.status} className="rounded-xl border pb-hairline bg-pb-surface p-3 mb-2 text-[13.5px]">
              <div>
                <strong>{s.status === 'accepted' ? 'Swapped with' : s.status === 'declined' ? (s.direction === 'out' ? 'Declined by' : 'You declined') : s.status === 'countered' ? (s.direction === 'out' ? 'Changed by' : 'You changed it for') : 'Cancelled with'} {s.other.name}</strong>
                <span className="text-pb-faint"> · {ago(s.resolved_at || s.created_at)}</span>
              </div>
              <div className="text-pb-dim mt-0.5">{s.direction === 'out' ? 'You gave' : 'You got'} {sideLine(s.give)}; {s.direction === 'out' ? 'you got' : 'you gave'} {sideLine(s.want)}.</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
