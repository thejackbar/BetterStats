import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import WebsiteChrome, { useWebsite } from '../../components/website/WebsiteChrome'
import { PbSpinner } from '../../lib/presskit'
import { usePageMeta } from '../../hooks/usePageMeta'

function Lightbox({ image, onClose, onPrev, onNext }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') onPrev()
      if (e.key === 'ArrowRight') onNext()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, onPrev, onNext])

  return (
    <div className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4" onClick={onClose}>
      <button onClick={(e) => { e.stopPropagation(); onPrev() }} className="absolute left-4 text-white/70 hover:text-white text-4xl px-3">‹</button>
      <figure className="max-w-5xl max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
        <img src={image.image_url} alt={image.caption || ''} className="max-h-[82vh] w-auto mx-auto object-contain rounded" />
        {image.caption && <figcaption className="text-white/80 text-center text-sm mt-3">{image.caption}</figcaption>}
      </figure>
      <button onClick={(e) => { e.stopPropagation(); onNext() }} className="absolute right-4 text-white/70 hover:text-white text-4xl px-3">›</button>
      <button onClick={onClose} className="absolute top-4 right-4 text-white/70 hover:text-white text-2xl">✕</button>
    </div>
  )
}

function AlbumView({ slug, albumId }) {
  const { site } = useWebsite()
  const [album, setAlbum] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lightbox, setLightbox] = useState(null)  // index

  usePageMeta({ title: album ? `${album.title} — ${site.name}` : `Gallery — ${site.name}` })

  useEffect(() => {
    let cancelled = false
    api.webGetAlbum(slug, albumId)
      .then(d => { if (!cancelled) { setAlbum(d); setLoading(false) } })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug, albumId])

  if (loading) return <div className="max-w-5xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>
  if (!album) return <div className="max-w-5xl mx-auto px-4 py-20 text-center text-pb-faint">Album not found.</div>

  const images = album.images || []
  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <Link to={`/${slug}/website/gallery`} className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-accent">← ALL ALBUMS</Link>
      <h1 className="font-display font-extrabold text-3xl text-pb-text mt-3">{album.title}</h1>
      {album.description && <p className="text-pb-faint text-sm mt-1">{album.description}</p>}

      {images.length === 0 ? (
        <p className="text-pb-faint py-12 text-center">No photos in this album yet.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mt-6">
          {images.map((img, i) => (
            <button
              key={img.id}
              onClick={() => setLightbox(i)}
              className="aspect-square rounded-lg overflow-hidden bg-pb-surface2 group"
            >
              <img src={img.image_url} alt={img.caption || ''} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
            </button>
          ))}
        </div>
      )}

      {lightbox != null && images[lightbox] && (
        <Lightbox
          image={images[lightbox]}
          onClose={() => setLightbox(null)}
          onPrev={() => setLightbox((lightbox - 1 + images.length) % images.length)}
          onNext={() => setLightbox((lightbox + 1) % images.length)}
        />
      )}
    </div>
  )
}

function AlbumsGrid({ slug }) {
  const { site } = useWebsite()
  const [albums, setAlbums] = useState([])
  const [loading, setLoading] = useState(true)

  usePageMeta({ title: `Gallery — ${site.name}`, url: `https://betterat.cricket/${slug}/website/gallery` })

  useEffect(() => {
    let cancelled = false
    api.webGetGallery(slug)
      .then(d => { if (!cancelled) { setAlbums(d.albums || []); setLoading(false) } })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug])

  if (loading) return <div className="max-w-5xl mx-auto px-4 py-16"><PbSpinner message="Loading…" /></div>

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h1 className="font-display font-extrabold text-3xl text-pb-text mb-1">Gallery</h1>
      <p className="text-pb-faint text-sm mb-8">Photos from around {site.name}</p>

      {albums.length === 0 ? (
        <p className="text-pb-faint py-12 text-center">No photo albums yet.</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {albums.map(a => (
            <Link key={a.id} to={`/${slug}/website/gallery/${a.id}`} className="group block rounded-xl overflow-hidden border pb-hairline bg-pb-surface hover:border-pb-accent transition-colors">
              <div className="aspect-[4/3] bg-pb-surface2 overflow-hidden">
                {a.cover_image_url
                  ? <img src={a.cover_image_url} alt="" loading="lazy" className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform" />
                  : <div className="w-full h-full flex items-center justify-center text-pb-faintest font-mono text-[11px]">EMPTY</div>}
              </div>
              <div className="p-4">
                <h3 className="font-display font-bold text-pb-text group-hover:text-pb-accent transition-colors">{a.title}</h3>
                <p className="text-[12px] text-pb-faint mt-0.5">{a.image_count} photo{a.image_count === 1 ? '' : 's'}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export default function WebsiteGallery() {
  const { clubSlug, albumId } = useParams()
  return (
    <WebsiteChrome slug={clubSlug} active="gallery">
      {albumId ? <AlbumView slug={clubSlug} albumId={albumId} /> : <AlbumsGrid slug={clubSlug} />}
    </WebsiteChrome>
  )
}
