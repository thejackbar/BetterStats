import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Button, Badge } from '../ui'
import { fmtDate } from './shared'

// What to do about a club scorecard linked to a game it does not match: look for the game that
// does (other games of the club close in date whose batters and scores really agree), move the link
// to it, say the link is right after all, or say they are two different matches. The same controls
// sit on the pairing list and on the compare page, because a person who opens a mismatched pair to
// look at it must be able to fix it there. `autoFind` asks for the better match at once.
export default function PairingFix({ matchId, autoFind = false, onChanged, onUnlinked, compareLink = false }) {
  const toast = useToast()
  const [cands, setCands] = useState(null)
  const [busy, setBusy] = useState(false)

  async function find() {
    setBusy(true)
    try { setCands((await api.cardReviewCandidates(matchId)).candidates) } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  useEffect(() => { if (autoFind) find() }, [matchId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn, ok, after = onChanged) {
    setBusy(true)
    try { await fn(); toast.success(ok); after() } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <>
      {cands && (
        <div className="mt-3 rounded-lg border border-pb-hairline bg-pb-bg p-3" data-testid="candidates">
          {cands.length === 0 && <div className="text-[12.5px] text-pb-dim">No better match found. Open both cards to decide, or unlink if they are different games.</div>}
          {cands.map(c => (
            <div key={c.game_id} className="flex flex-wrap items-center gap-3 py-1.5">
              <div className="min-w-0 flex-1 text-[13px] text-pb-text">
                {c.grade} v {c.opposition} <span className="font-mono text-[12px] text-pb-dim">· {fmtDate(c.date)}</span>
                <span className="ml-2"><Badge toneKey="ok">{c.shared} of {c.club_batters} batters in common</Badge></span>
                {c.taken_by && <span className="ml-2"><Badge toneKey="warn">Already linked to another club scorecard</Badge></span>}
              </div>
              <Button size="sm" variant="primary" disabled={busy || !!c.taken_by} data-testid="relink"
                onClick={() => act(() => api.cardReviewRelink(matchId, c.game_id), 'Linked to the better match')}>
                Re-link to this match
              </Button>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!cands && <Button size="sm" variant="primary" disabled={busy} onClick={find}>Find a better match</Button>}
        <Button size="sm" disabled={busy} onClick={() => act(() => api.cardReviewPairOk(matchId), 'Marked as the same match')} data-testid="pair-ok">Looks right: keep the link</Button>
        <Button size="sm" disabled={busy} data-testid="unlink" onClick={() => {
          if (confirm('Say these are two different matches? The club scorecard will stand alone and Cricket Australia\'s card will count as its own match. This can be undone.')) {
            act(() => api.cardReviewUnlink(matchId), 'Unlinked. It can be undone from Recent changes.', onUnlinked || onChanged)
          }
        }}>Not the same match: unlink</Button>
        {compareLink && <Button size="sm" as={Link} to={`/admin/card-review/match/${matchId}`} className="ml-auto">Open side by side ›</Button>}
      </div>
    </>
  )
}
