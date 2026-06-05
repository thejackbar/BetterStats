import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

function initials(name) {
  return (name || '').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

function CommitteeBody({ slug }) {
  const { site } = useWebsite()
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)

  usePageMeta({ title: `Committee — ${site.name}`, url: `https://betterstats.cricket/${slug}/website/committee` })

  useEffect(() => {
    let cancelled = false
    api.webGetCommittee(slug)
      .then(d => { if (!cancelled) { setMembers(d.members || []); setLoading(false) } })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug])

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="font-display font-extrabold text-3xl text-pb-text mb-1">Committee</h1>
      <p className="text-pb-faint text-sm mb-8">Meet the people who run {site.name}</p>

      {members.length === 0 ? (
        <p className="text-pb-faint py-12 text-center">No committee members listed yet.</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {members.map(m => (
            <div key={m.id} className="rounded-xl border pb-hairline bg-pb-surface p-5 text-center">
              <div className="w-20 h-20 mx-auto rounded-full overflow-hidden bg-pb-surface2 flex items-center justify-center">
                {m.photo_url
                  ? <img src={m.photo_url} alt={m.name} className="w-full h-full object-cover" />
                  : <span className="font-display font-bold text-xl text-pb-faint">{initials(m.name)}</span>}
              </div>
              <div className="mt-3 font-mono text-[10px] tracking-wide2 uppercase" style={{ color: 'var(--pb-accent)' }}>{m.role}</div>
              <div className="font-display font-bold text-pb-text mt-0.5">{m.name}</div>
              {m.bio && <p className="text-[12px] text-pb-faint mt-2 leading-relaxed">{m.bio}</p>}
              <div className="mt-3 flex items-center justify-center gap-3 text-[12px]">
                {m.email && <a href={`mailto:${m.email}`} className="text-pb-faint hover:text-pb-accent">Email</a>}
                {m.phone && <a href={`tel:${m.phone}`} className="text-pb-faint hover:text-pb-accent">{m.phone}</a>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function WebsiteCommittee() {
  const { clubSlug } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="committee">
      <CommitteeBody slug={clubSlug} />
    </WebsiteChrome>
  )
}
