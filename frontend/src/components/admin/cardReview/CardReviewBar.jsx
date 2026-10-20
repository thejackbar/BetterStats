import { useState, useEffect } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { CAP } from '../../../lib/capabilities'
import { Badge } from '../ui'
import { CHOICE_NAME, ChoiceControl } from './shared'

// The bar a club admin sees above the scorecard of a match that is stored twice. It never
// renders for a visitor, a member without the capability, or a match with only one version.
// One click switches the match; the page then follows the choice to the card the site now shows.
export default function CardReviewBar({ gameId }) {
  const { hasCapability } = useAuth()
  const can = hasCapability(CAP.MANAGE_MANUAL_ENTRIES)
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const [pair, setPair] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setPair(null)
    if (!can) return
    api.cardReviewForGame(gameId).then(setPair).catch(() => setPair(null))
  }, [gameId, can])

  if (!can || !pair?.paired) return null
  const viewing = gameId === pair.game_id ? 'Cricket Australia scorecard' : 'club scorecard'

  async function choose(key) {
    if (key === 'hybrid') { navigate(`/admin/card-review/match/${pair.match_id}#hybrid`); return }
    if (key === pair.current) return
    setBusy(true)
    try {
      const res = await api.cardReviewChoose(pair.match_id, key)
      toast.success(`The site now shows the ${CHOICE_NAME[key]}`)
      const next = res.match.effective_game_id
      if (next !== gameId) navigate(location.pathname.replace(gameId, next) + location.search, { replace: true })
      else setPair({ ...pair, current: key, effective_game_id: next })
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div
      className="border-b px-4 py-2.5 text-[12.5px] text-pb-text sm:px-6"
      style={{ background: 'linear-gradient(90deg, rgba(22,199,132,.12), rgba(22,199,132,.04))', borderColor: 'rgba(22,199,132,.3)' }}
      data-testid="card-review-bar"
    >
      <div className="mx-auto flex max-w-[1300px] flex-wrap items-center gap-x-4 gap-y-2">
        <Badge toneKey="ok">Admin only</Badge>
        <span className="min-w-0 flex-1 basis-[260px]">
          This match is stored twice. The site shows the <b>{CHOICE_NAME[pair.current]}</b>.
          {viewing !== (pair.current === 'ca' ? 'Cricket Australia scorecard' : 'club scorecard') && (
            <span className="text-pb-dim"> You are looking at the {viewing} page.</span>
          )}
        </span>
        <ChoiceControl compact value={pair.current} onChange={choose} disabled={busy} labelFor="label" data-testid="bar-choice" />
        <Link to={`/admin/card-review/match/${pair.match_id}`} className="rounded-lg border border-pb-hairline2 px-3 py-1.5 text-[12px] text-pb-dim hover:text-pb-text">
          Compare side by side
        </Link>
      </div>
    </div>
  )
}
