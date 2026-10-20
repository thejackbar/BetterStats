import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

// "Meta ad pack": a zip of ad pictures, ad words, landing links and club
// locations for the clubs the Club Directory filters match. An export only. It
// does not talk to Meta, create an ad or spend anything; the person who uploads
// it into Ads Manager decides that. A club needs a drawn picture to be in it,
// so the row says how many of the matching clubs have one.

const DEBOUNCE_MS = 600
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border border-pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const INPUT = 'bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs text-pb-text w-16 focus:outline-none focus:border-pb-accent'

const num = (n) => Number(n || 0).toLocaleString()

export default function AdPackRow({ filters }) {
  const [limit, setLimit] = useState('50')
  const [offset, setOffset] = useState('0')
  const [radius, setRadius] = useState('15')
  const [campaign, setCampaign] = useState('club-season')
  const [sum, setSum] = useState(null)
  const [err, setErr] = useState('')

  const lim = Math.max(1, Math.min(100, parseInt(limit, 10) || 50))
  const off = Math.max(0, parseInt(offset, 10) || 0)
  const key = JSON.stringify(filters)

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      api.mktAdPackSummary(filters, { limit: lim, offset: off })
        .then((r) => { if (alive) { setSum(r); setErr('') } })
        .catch((e) => { if (alive) { setSum(null); setErr(e.message || 'Could not read the ad pack summary.') } })
    }, DEBOUNCE_MS)
    return () => { alive = false; clearTimeout(t) }
  }, [key, lim, off])   // eslint-disable-line react-hooks/exhaustive-deps

  const ready = sum && sum.in_pack > 0
  const href = ready ? api.mktAdPackUrl(filters, { limit: lim, offset: off, radius_km: radius, campaign }) : undefined

  return (
    <div className="mt-2.5 pt-2.5 border-t pb-hairline" data-testid="adpack-row">
      <div className="flex flex-wrap items-end gap-3">
        <span className="text-[11px] font-semibold text-pb-text self-center">Meta ad pack</span>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">Clubs
          <input className={INPUT} type="number" min="1" max="100" value={limit} data-testid="adpack-limit"
                 onChange={(e) => setLimit(e.target.value)} />
        </label>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">Skip first
          <input className={INPUT} type="number" min="0" value={offset} data-testid="adpack-offset"
                 onChange={(e) => setOffset(e.target.value)} />
        </label>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">Radius (km)
          <input className={INPUT} type="number" min="2" max="80" value={radius} data-testid="adpack-radius"
                 onChange={(e) => setRadius(e.target.value)} />
        </label>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">Campaign name
          <input className={`${INPUT} w-36`} type="text" value={campaign} data-testid="adpack-campaign"
                 onChange={(e) => setCampaign(e.target.value)} />
        </label>
        {ready ? (
          <a className={BTN} href={href} data-testid="adpack-download" target="_blank" rel="noreferrer">
            Download ad pack ({num(sum.in_pack)} clubs)
          </a>
        ) : (
          <button className={BTN} disabled data-testid="adpack-download">Download ad pack</button>
        )}
      </div>
      {sum && (
        <p className="mt-1.5 text-[11px] text-pb-dim" data-testid="adpack-summary">
          {num(sum.matching)} clubs match, <span className="text-pb-text font-semibold">{num(sum.eligible)}</span> have
          pictures and can go in a pack
          {sum.without_location > 0 ? `, ${num(sum.without_location)} of those have no location for geo targeting` : ''}.
          {sum.eligible > 0 && sum.in_pack === 0 ? ' Nothing left after skipping that many.' : ''}
          {sum.matching > 0 && sum.eligible === 0 ? ' None of the matching clubs has a picture yet. Draw pictures in the teaser panel above.' : ''}
        </p>
      )}
      {err && <p className="mt-1.5 text-[11px] text-red-300" data-testid="adpack-error">{err}</p>}
      <p className="mt-1 text-[11px] text-pb-faint">
        A zip to upload into Ads Manager yourself. Nothing is sent to Meta and nothing is spent. Ad pictures and words never name a player.
      </p>
    </div>
  )
}
