import { useToast } from '../../../../contexts/ToastContext'
import { Btn } from '../ui'

// The medal's voting link, shown the way the availability link is: the link and
// a copy button, nothing else. It is one portal for the whole medal. A player
// finds their name, enters their PIN, and is taken to the next game they played
// that is open for voting and that they have not voted on, so there is no
// per-team or per-game link to hand out.
export function voteUrl(token) {
  return new URL(`/vote/${token}`, window.location.origin).toString()
}

// `onEnable` is passed for people who can switch the link on; without it the
// notice only says it is off.
export default function ShareVotePanel({ settings, onEnable, busy }) {
  const toast = useToast()
  const url = settings?.enabled && settings?.token ? voteUrl(settings.token) : ''

  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast.success('Link copied') }
    catch { toast.error('Copy failed. Select and copy manually.') }
  }

  if (!url) {
    return (
      <div className="pb-card px-4 py-3 mb-4 flex flex-wrap items-center gap-3 text-[12.5px] text-pb-amber" data-vote-link-off>
        <span className="flex-1 min-w-[220px]">
          The voting link is off, so players can't vote yet. Admins can still enter ballots by hand.
        </span>
        {onEnable && <Btn sm variant="primary" onClick={onEnable} disabled={busy}>Turn on voting link</Btn>}
      </div>
    )
  }

  return (
    <div className="pb-card px-4 py-3 mb-4" data-vote-link>
      <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Voting link</label>
      <div className="flex flex-wrap items-center gap-2">
        <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Voting link"
          className="flex-1 min-w-[220px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
        <Btn sm onClick={copy}>Copy link</Btn>
      </div>
    </div>
  )
}
