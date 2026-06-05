import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

function EntryRow({ entry, slug }) {
  const name = entry.player_id
    ? <Link to={`/players/${entry.player_id}`} className="text-pb-text hover:text-pb-accent">{entry.name}</Link>
    : <span className="text-pb-text">{entry.name}</span>
  return (
    <div className="flex items-baseline gap-3 py-2 pb-hairline-t break-inside-avoid">
      {entry.year != null && (
        <span className="font-mono text-[12px] text-pb-faint w-12 shrink-0 tabular-nums">{entry.year}</span>
      )}
      <div className="flex-1 min-w-0">
        <span className="font-medium">{name}</span>
        {entry.detail && <span className="text-pb-faint text-sm"> — {entry.detail}</span>}
      </div>
    </div>
  )
}

function OfficeBearers({ slug, office }) {
  if (!office || !office.entries?.length) return null
  return (
    <section className="rounded-xl border pb-hairline bg-pb-surface p-5 sm:p-6 mb-8">
      <h2 className="font-display font-bold text-xl text-pb-text">Office Bearers</h2>
      <p className="text-pb-faint text-sm mt-0.5 mb-3">{office.season}</p>
      <div className="grid sm:grid-cols-2 gap-x-8">
        {office.entries.map((e, i) => (
          <div key={i} className="flex items-baseline justify-between gap-3 py-2 pb-hairline-t first:border-t-0 sm:[&:nth-child(2)]:border-t-0">
            <span className="font-mono text-[11px] tracking-wide2 uppercase text-pb-faint">{e.position_title}</span>
            <span className="text-pb-text text-sm font-medium text-right">
              {e.player_id
                ? <Link to={`/players/${e.player_id}`} className="hover:text-pb-accent">{e.name}</Link>
                : e.name}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

function HonoursBody({ slug }) {
  const { site } = useWebsite()
  const [boards, setBoards] = useState([])
  const [office, setOffice] = useState(null)
  const [loading, setLoading] = useState(true)

  usePageMeta({ title: `Honours — ${site.name}`, url: `https://betterstats.cricket/${slug}/website/honours` })

  useEffect(() => {
    let cancelled = false
    api.webGetHonours(slug)
      .then(d => { if (!cancelled) { setBoards(d.boards || []); setOffice(d.office_bearers || null); setLoading(false) } })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug])

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="font-display font-extrabold text-3xl text-pb-text mb-1">Honours</h1>
      <p className="text-pb-faint text-sm mb-8">{site.name}</p>

      <OfficeBearers slug={slug} office={office} />

      {boards.length === 0 && !office ? (
        <p className="text-pb-faint py-12 text-center">No honour boards yet.</p>
      ) : (
        <div className="space-y-8">
          {boards.map(board => (
            <section key={board.id} className="rounded-xl border pb-hairline bg-pb-surface p-5 sm:p-6">
              <h2 className="font-display font-bold text-xl text-pb-text">{board.title}</h2>
              {board.description && <p className="text-pb-faint text-sm mt-1 mb-3">{board.description}</p>}
              <div
                className={`mt-3 ${board.columns > 1 ? 'max-sm:!columns-1' : ''}`}
                style={board.columns > 1 ? { columnCount: board.columns, columnGap: '1.75rem' } : undefined}
              >
                {board.entries.length === 0
                  ? <p className="text-pb-faintest text-sm py-2">No entries yet.</p>
                  : board.entries.map((e, i) => <EntryRow key={e.id || `a${i}`} entry={e} slug={slug} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export default function WebsiteHonours() {
  const { clubSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="honours">
      <HonoursBody slug={clubSlug} />
    </WebsiteChrome>
  )
}
