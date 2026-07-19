import { useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Centred on Australia — nearly all traffic is Australian club cricket, and
// the map still pans/zooms freely to anywhere a point lands.
const AU_CENTER = [-25.6, 134.4]
const AU_ZOOM = 4

function fmtAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// Visitor-count → dot radius, log-scaled so one huge city doesn't swallow
// everyone else on screen.
function radiusFor(visitors) {
  return Math.min(22, 6 + Math.log2(Math.max(1, visitors)) * 3.2)
}

export default function VisitorMap({ points, loading }) {
  const withCoords = useMemo(() => (points || []).filter(p => p.lat != null && p.lng != null), [points])

  return (
    <div className="pb-card overflow-hidden">
      <div style={{ height: 360 }}>
        <MapContainer
          center={AU_CENTER}
          zoom={AU_ZOOM}
          minZoom={2}
          scrollWheelZoom={false}
          style={{ height: '100%', width: '100%', background: 'var(--pb-surface2)' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {withCoords.map((p, i) => (
            <CircleMarker
              key={`${p.lat}-${p.lng}-${i}`}
              center={[p.lat, p.lng]}
              radius={radiusFor(p.visitors)}
              pathOptions={{
                color: p.is_online ? '#10b981' : 'var(--pb-accent)',
                fillColor: p.is_online ? '#10b981' : 'var(--pb-accent)',
                fillOpacity: p.is_online ? 0.55 : 0.32,
                weight: p.is_online ? 2 : 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -4]}>
                <div className="font-mono text-[11px]">
                  <div className="font-bold">{p.city || p.region || p.country || 'Unknown'}</div>
                  {p.region && p.city && <div>{p.region}</div>}
                  <div>{p.visitors} visitor{p.visitors === 1 ? '' : 's'} · {p.views} views</div>
                  <div>{p.is_online ? 'Active now' : `Last seen ${fmtAgo(p.last_seen)}`}</div>
                </div>
              </Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      {!loading && withCoords.length === 0 && (
        <div className="py-3 text-center font-mono text-[10px] text-pb-faint border-t pb-hairline-t">
          No located visitors in this window yet.
        </div>
      )}
    </div>
  )
}
