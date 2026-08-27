import { useState } from 'react'
import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import VideoThumb from '../../components/marketing/VideoThumb'
import { VideoAdminBar, VideoCardControls, VideoEditorModal } from '../../components/marketing/VideoManager'
import { usePageMeta } from '../../hooks/usePageMeta'
import { useVideos } from '../../hooks/useVideos'
import { VIDEO_EMPTY, VIDEO_INTRO } from '../../data/videos'
import { api } from '../../lib/api'

const SITE = 'https://betterat.cricket'

function VideoCard({ video, canManage, reordering, onEdit, onDeleted, onError, drag }) {
  const inner = (
    <>
      <VideoThumb poster={video.poster} title={video.title} />
      <div className="pt-4">
        {video.module_label && (
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">{video.module_label}</p>
        )}
        <h2 className="font-display font-bold text-[18px] text-pb-text leading-snug mb-1.5 group-hover:text-accent transition-colors">
          {video.title}
        </h2>
        {video.description && (
          <p className="text-pb-dim text-sm leading-relaxed whitespace-pre-line">{video.description}</p>
        )}
      </div>
    </>
  )

  return (
    <div
      className={`group flex flex-col ${reordering ? 'cursor-grab active:cursor-grabbing rounded-lg' : ''}`}
      style={reordering && drag.isDragging ? { opacity: 0.4 } : undefined}
      draggable={reordering}
      onDragStart={reordering ? drag.onDragStart : undefined}
      onDragOver={reordering ? drag.onDragOver : undefined}
      onDrop={reordering ? drag.onDrop : undefined}
      onDragEnd={reordering ? drag.onDragEnd : undefined}
      data-video-slug={video.slug}
    >
      {reordering ? (
        // While reordering the card must not navigate — a drag that ends as a
        // click would otherwise leave the page mid-sort.
        <div aria-hidden="true">{inner}</div>
      ) : (
        <Link to={`/videos/${video.slug}`} className="block" aria-label={`Watch ${video.title}`}>
          {inner}
        </Link>
      )}

      {!reordering && (
        <div className="mt-3 flex items-center gap-4">
          <Link to={`/videos/${video.slug}`} className="font-mono text-[10px] tracking-wide2 font-semibold"
                style={{ color: 'var(--pb-accent)' }}>
            WATCH →
          </Link>
          {/* No file on the server means nothing to download, so the link is
              withdrawn rather than left to hand back a 404. Video files are
              deliberately outside the regular backup, so a restored database
              legitimately reaches this state. */}
          {video.file_present !== false && (
            <a href={`${video.src}?download=1`} download
               className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
              DOWNLOAD
            </a>
          )}
          {video.file_present === false && canManage && (
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">FILE MISSING</span>
          )}
        </div>
      )}

      {canManage && !reordering && (
        <VideoCardControls video={video} onEdit={onEdit} onDeleted={onDeleted} onError={onError} />
      )}
    </div>
  )
}

export default function Videos() {
  const { videos, setVideos, loading, error, reload, canManage } = useVideos()
  const [editing, setEditing] = useState(null)   // video object, or 'new'
  const [reordering, setReordering] = useState(false)
  const [dragSlug, setDragSlug] = useState(null)
  const [savingOrder, setSavingOrder] = useState(false)
  const [notice, setNotice] = useState(null)

  usePageMeta({
    title: 'Videos — How-to walkthroughs for club admins | BetterCricket',
    description:
      'Step-by-step video walkthroughs of BetterCricket for cricket club administrators. Watch online or download a copy.',
    image: `${SITE}/og-cover.png`,
    url: `${SITE}/videos`,
    jsonLd: videos.length
      ? {
          '@context': 'https://schema.org',
          '@type': 'ItemList',
          name: 'BetterCricket instructional videos',
          url: `${SITE}/videos`,
          itemListElement: videos.map((v, i) => ({
            '@type': 'ListItem', position: i + 1, url: `${SITE}/videos/${v.slug}`, name: v.title,
          })),
        }
      : undefined,
  })

  // Reordering is applied locally first and rolled back if the write fails, so
  // a card stays where it was dropped instead of snapping back for the length
  // of the request.
  const commitOrder = async (next) => {
    const previous = videos
    setVideos(next)
    setSavingOrder(true)
    try {
      await api.adminReorderVideos(next.map((v) => v.id))
    } catch (err) {
      setVideos(previous)
      setNotice(err.message || 'That order did not save.')
    } finally {
      setSavingOrder(false)
    }
  }

  const dragFor = (video) => ({
    isDragging: dragSlug === video.slug,
    onDragStart: (e) => {
      setDragSlug(video.slug)
      e.dataTransfer.effectAllowed = 'move'
      // Firefox will not start a drag without data on the transfer.
      try { e.dataTransfer.setData('text/plain', video.slug) } catch { /* ignore */ }
    },
    // Without preventDefault the drop is refused, so the cursor says no.
    onDragOver: (e) => { if (dragSlug && dragSlug !== video.slug) e.preventDefault() },
    onDrop: (e) => {
      e.preventDefault()
      if (!dragSlug || dragSlug === video.slug) return
      const next = [...videos]
      const from = next.findIndex((v) => v.slug === dragSlug)
      const to = next.findIndex((v) => v.slug === video.slug)
      if (from < 0 || to < 0) return
      next.splice(to, 0, next.splice(from, 1)[0])
      setDragSlug(null)
      commitOrder(next)
    },
    onDragEnd: () => setDragSlug(null),
  })

  const onSaved = () => { setEditing(null); reload() }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-5xl mx-auto px-4 py-16 pt-28">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">{VIDEO_INTRO.eyebrow}</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">
          {VIDEO_INTRO.heading}
        </h1>
        <p className="text-pb-dim text-lg max-w-2xl mb-12">{VIDEO_INTRO.blurb}</p>

        {canManage && (
          <VideoAdminBar
            onAdd={() => setEditing('new')}
            reordering={reordering}
            onToggleReorder={() => { setReordering((r) => !r); setDragSlug(null) }}
            count={videos.length}
            saving={savingOrder}
          />
        )}

        {canManage && videos.some((v) => v.file_present === false) && (
          <p className="mb-6 text-sm text-pb-dim">
            {videos.filter((v) => v.file_present === false).length} video file(s) are missing from the
            server. Video files are not part of the regular backup by design, so after a restore they
            need re-uploading from the originals. Everything else about those entries is intact.
          </p>
        )}
        {notice && <p className="mb-6 text-sm text-pb-dim">{notice}</p>}
        {error && <p className="mb-6 text-sm text-pb-dim">{error}</p>}

        {loading ? (
          <p className="text-pb-faint text-sm">Loading…</p>
        ) : videos.length === 0 ? (
          <p className="text-pb-dim">{canManage ? VIDEO_EMPTY.admin : VIDEO_EMPTY.visitor}</p>
        ) : (
          <div className="grid gap-x-8 gap-y-12 sm:grid-cols-2">
            {videos.map((video) => (
              <VideoCard
                key={video.id}
                video={video}
                canManage={canManage}
                reordering={reordering}
                drag={dragFor(video)}
                onEdit={setEditing}
                onDeleted={reload}
                onError={setNotice}
              />
            ))}
          </div>
        )}

        <p className="mt-16 pb-hairline-t pt-8 text-sm text-pb-faint">
          More walkthroughs are added as they are recorded. If there is a job you would like covered,{' '}
          <Link to="/contact" className="text-pb-dim hover:text-pb-text underline transition-colors">tell us</Link>{' '}
          and we will put it on the list.
        </p>
      </div>

      <MarketingFooter />

      {editing && (
        <VideoEditorModal
          video={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}
    </div>
  )
}
