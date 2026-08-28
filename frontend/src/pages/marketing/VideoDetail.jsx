import { useState } from 'react'
import { Link, useParams, Navigate } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import VideoThumb from '../../components/marketing/VideoThumb'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import { usePageMeta } from '../../hooks/usePageMeta'
import { useSelfServeTrialGate } from '../../hooks/useSelfServeTrialGate'
import { VideoEditorModal } from '../../components/marketing/VideoManager'
import { useVideos } from '../../hooks/useVideos'
import { videoModuleCta } from '../../lib/videoModule'

const SITE = 'https://betterat.cricket'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * The player itself. A source that will not load (the file has not been
 * uploaded yet, or the browser cannot decode it) shows a plain note in the
 * frame instead of a dead black rectangle, and still offers the download.
 */
function Player({ video }) {
  const [failed, setFailed] = useState(false)

  // `file_present` is false when the row is here but the file is not. That is
  // an ordinary state: video files are deliberately outside the regular
  // backup, so a database restored onto a fresh box has rows whose files are
  // gone. Saying so up front beats waiting for the player to fail.
  if (failed || video.file_present === false) {
    return (
      <div
        className="grid place-items-center rounded-xl border pb-hairline bg-pb-surface2 px-6 text-center"
        style={{ aspectRatio: '16 / 9' }}
      >
        <div>
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Not playing</p>
          <p className="text-pb-dim text-sm max-w-sm leading-relaxed">
            This walkthrough is not available on the server right now. Please check back shortly.
          </p>
        </div>
      </div>
    )
  }

  return (
    <video
      className="w-full rounded-xl border pb-hairline bg-black"
      style={{ aspectRatio: '16 / 9' }}
      src={video.src}
      poster={video.poster}
      controls
      preload="metadata"
      playsInline
      onError={() => setFailed(true)}
    >
      Your browser cannot play this video.{' '}
      <a href={`${video.src}?download=1`} download>Download it instead</a>.
    </video>
  )
}

export default function VideoDetail() {
  const { slug } = useParams()
  const { videos, loading, reload, canManage } = useVideos()
  const [editing, setEditing] = useState(false)
  const video = videos.find((v) => v.slug === slug) || null
  const { trigger: triggerTrial, modalOpen: trialModalOpen, setModalOpen: setTrialModalOpen, defaultTrialDays } =
    useSelfServeTrialGate()

  const pageUrl = video ? `${SITE}/videos/${video.slug}` : ''
  const posterUrl = video?.poster ? `${SITE}${video.poster}` : `${SITE}/og-cover.png`

  // VideoObject + breadcrumb, so a search engine can surface the walkthrough
  // itself rather than just the page it sits on.
  const jsonLd = video
    ? [
        {
          '@context': 'https://schema.org',
          '@type': 'VideoObject',
          name: video.title,
          description: video.description || video.title,
          thumbnailUrl: posterUrl,
          uploadDate: video.date,
          contentUrl: `${SITE}${video.src}`,
          inLanguage: 'en-AU',
          publisher: {
            '@type': 'Organization',
            name: 'BetterSports',
            logo: { '@type': 'ImageObject', url: `${SITE}/og-image.png` },
          },
          url: pageUrl,
        },
        {
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Home', item: `${SITE}/` },
            { '@type': 'ListItem', position: 2, name: 'Videos', item: `${SITE}/videos` },
            { '@type': 'ListItem', position: 3, name: video.title, item: pageUrl },
          ],
        },
      ]
    : undefined

  usePageMeta(
    video
      ? {
          title: `${video.title} | BetterCricket`,
          description: video.description || video.title,
          image: posterUrl,
          url: pageUrl,
          type: 'video.other',
          jsonLd,
        }
      : {},
  )

  if (loading) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text">
        <MarketingNav />
        <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
          <p className="text-pb-faint text-sm">Loading…</p>
        </div>
        <MarketingFooter />
      </div>
    )
  }
  if (!video) return <Navigate to="/videos" replace />

  const others = videos.filter((v) => v.slug !== video.slug)
  const cta = videoModuleCta(video.module_label)

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-3xl mx-auto px-4 py-16 pt-28">
        {/* Breadcrumb */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-8">
          <Link to="/videos" className="hover:text-pb-text transition-colors">VIDEOS</Link>
          <span className="mx-2">›</span>
          <span className="text-pb-faintest">{(video.module_label || 'WALKTHROUGH').toUpperCase()}</span>
        </p>

        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">{formatDate(video.date)}</p>
            {video.module_label && (
              <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest">{video.module_label}</p>
            )}
          </div>
          <h1 className="font-display font-bold text-[32px] md:text-[40px] tracking-tight text-pb-text leading-tight">
            {video.title}
          </h1>
        </div>

        <Player video={video} />

        {/* Download — the point of hosting the file ourselves rather than embedding
            it. Withdrawn when the file is not on the server, since it would
            only ever hand back a 404. */}
        <div className="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
          {video.file_present === false && (
            <p className="text-pb-faint text-xs">This video's file is not on the server.</p>
          )}
          {video.file_present !== false && (
          <a
            href={`${video.src}?download=1`}
            download
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v12" />
              <path d="m7 11 5 5 5-5" />
              <path d="M4 20h16" />
            </svg>
            DOWNLOAD VIDEO
          </a>
          )}
          <p className="text-pb-faint text-xs">
            Keep a copy on the club laptop so whoever takes the job on next has it.
          </p>
          {canManage && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="sm:ml-auto font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
            >
              EDIT THIS VIDEO
            </button>
          )}
        </div>

        {/* Description */}
        {video.description && (
          <p className="mt-10 text-pb-dim leading-relaxed whitespace-pre-line">{video.description}</p>
        )}

        {/* CTA — follows the module the video is filed under. A selection
            walkthrough that ends by pitching BetterStats sends an interested
            visitor to the wrong page. */}
        <div className="mt-16 pb-hairline-t pt-10">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Want this for your club?</p>
          <h2 className="font-display font-bold text-2xl text-pb-text mb-4 tracking-tight">
            {cta.heading}
          </h2>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              onClick={triggerTrial}
              aria-label="Request access"
              className="inline-block px-6 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              REQUEST ACCESS
            </button>
            <Link
              to={cta.to}
              className="inline-block px-6 py-3 border pb-hairline rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors"
            >
              {cta.cta} →
            </Link>
          </div>
        </div>

        {/* More videos */}
        {others.length > 0 && (
          <div className="mt-12 pb-hairline-t pt-8">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-5 uppercase">More walkthroughs</p>
            <div className="grid gap-x-6 gap-y-8 sm:grid-cols-3">
              {others.map((v) => (
                <Link key={v.slug} to={`/videos/${v.slug}`} className="group block">
                  <VideoThumb poster={v.poster} title={v.title} />
                  <p className="mt-2.5 text-sm text-pb-dim group-hover:text-pb-text transition-colors leading-snug">
                    {v.title}
                  </p>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <MarketingFooter />
      {editing && (
        <VideoEditorModal
          video={video}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); reload() }}
        />
      )}
      {trialModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setTrialModalOpen(false)}
        />
      )}
    </div>
  )
}
