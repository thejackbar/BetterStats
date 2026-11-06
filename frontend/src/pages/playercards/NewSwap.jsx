// The swap builder as a page of its own: who with, the cards you want, the cards you give. Arrives with a card already
// chosen from My cards (state.give) or from the club's set or a search (state.ask: the person and the card).
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { Builder } from '../../components/cards/SwapsPanel'
import PageHead from './PageHead'
import { usePC } from './context'

export default function NewSwap() {
  const { token, club, accent, display, sponsor, basePath, loadSwaps } = usePC()
  const [board, setBoard] = useState(null)
  const [failed, setFailed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const state = location.state || {}
  useEffect(() => { api.availPublicSwaps(token).then(setBoard).catch(() => setFailed(true)) }, [token])
  if (failed) return <div className="text-sm text-pb-faint" data-swaps-failed>Swaps could not load. Reload to try again.</div>
  if (!board) return <div className="text-sm text-pb-faint" data-swaps-loading>Loading swaps…</div>
  const leave = () => navigate(`${basePath}/swaps`)
  return (
    <div data-screen="new-swap">
      <PageHead title={state.counter ? 'Change the swap' : 'Start a swap'} />
      <Builder inline token={token} board={board} give={state.give || null} giveList={state.giveList || null} prefill={state.ask || null} counter={state.counter || null} club={club} accent={accent} display={display} sponsor={sponsor}
        onClose={leave} onSent={() => { loadSwaps(); navigate(`${basePath}/swaps/sent`, { state: { sent: true } }) }} />
    </div>
  )
}
