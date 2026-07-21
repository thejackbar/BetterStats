import { MapContainer, TileLayer, Circle, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// State-scale zoom — close enough to read as "this part of the state"
// without needing a per-state bounding box; centering on the club's own
// coordinates keeps it simple since those are always inside its own state.
const ZOOM = 7
// There's no real postcode-boundary data in the app (would need a separate
// ABS geospatial dataset) — this is a lightly-shaded approximation of "the
// postcode area", centred on the club's own coordinates, not an exact shape.
const HIGHLIGHT_RADIUS_M = 15000

export default function ClubLocationMap({ latitude, longitude, postcode, state }) {
  if (latitude == null || longitude == null) {
    return (
      <div className="pb-card px-3 py-4 text-center font-mono text-[10px] text-pb-faint">
        No location on file for this club.
      </div>
    )
  }
  const center = [latitude, longitude]
  return (
    <div className="pb-card overflow-hidden">
      <div style={{ height: 180 }}>
        <MapContainer
          center={center}
          zoom={ZOOM}
          scrollWheelZoom={false}
          dragging={false}
          zoomControl={false}
          doubleClickZoom={false}
          style={{ height: '100%', width: '100%', background: 'var(--pb-surface2)' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Circle
            center={center}
            radius={HIGHLIGHT_RADIUS_M}
            pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.18, weight: 1 }}
          />
          <CircleMarker
            center={center}
            radius={4}
            pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 1, weight: 1 }}
          />
        </MapContainer>
      </div>
      <div className="px-2 py-1 border-t pb-hairline-t font-mono text-[9px] text-pb-faintest">
        Approximate area for postcode {postcode || '—'}{state ? `, ${state}` : ''}
      </div>
    </div>
  )
}
