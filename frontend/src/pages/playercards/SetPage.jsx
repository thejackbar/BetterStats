// One set: its progress and its cards, laid out as the club's book (the catalogue read through `set=`). Cards you hold are ticked.
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import CatalogueTab from '../../components/cards/CatalogueTab'
import { api } from '../../lib/api'
import { onColor } from '../../components/PlayerTradingCard'
import PageHead from './PageHead'
import { usePC } from './context'

export default function SetPage() {
  const { key } = useParams()
  const { token, club, accent, display, sponsor, basePath, wants, toggleWant } = usePC()
  const [set, setSet] = useState(null)
  const [err, setErr] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    let live = true
    setSet(null); setErr('')
    api.availPublicSet(token, key).then((s) => { if (live) setSet(s) }).catch((e) => { if (live) setErr(e?.message || 'That set could not be found.') })
    return () => { live = false }
  }, [token, key])
  if (err) return <div data-set-error className="text-sm" style={{ color: 'var(--pb-red, #f87171)' }}>{err} <Link to={`${basePath}/sets`} className="underline">Back to sets</Link></div>
  if (!set) return <div className="text-sm text-pb-faint" data-set-loading>Loading the set…</div>
  const pct = set.total ? Math.round((100 * set.owned) / set.total) : 0
  return (
    <div data-screen="set">
      <PageHead title={set.title} sub={set.blurb} actions={<Link to={`${basePath}/sets`} className="px-4 py-2 rounded-lg border pb-hairline text-sm font-semibold">All sets</Link>} />
      <div className="rounded-2xl border pb-hairline bg-pb-surface p-4 mb-5" data-set-header>
        {set.complete && <div data-set-banner className="mb-3 px-3 py-2 rounded-lg text-sm font-bold" style={{ background: accent, color: onColor(accent) }}>You have the whole set.</div>}
        <div style={{ height: 8, borderRadius: 4, background: 'rgba(148,163,184,.25)', overflow: 'hidden' }}><div style={{ width: `${pct}%`, height: '100%', background: accent }} /></div>
        <div className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint mt-2" data-set-owned>{set.owned} of {set.total} · {pct}%. Cards you hold are ticked.</div>
      </div>
      <CatalogueTab intro={false} panel setKey={key} wants={wants.keys} onToggleWant={toggleWant} cardHref={(c) => `${basePath}/card/${encodeURIComponent(c.key)}`}
        token={token} club={club} accent={accent} display={display} sponsor={sponsor}
        onAsk={(a) => navigate(`${basePath}/swaps/new`, { state: { ask: a } })} />
    </div>
  )
}
