import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Circle, CircleMarker, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../../lib/api'

// State-scale zoom — close enough to read as "this part of the state"
// without needing a per-state bounding box; centering on the club's own
// coordinates keeps it simple since those are always inside its own state.
const ZOOM = 7
// Fallback only — used while the real boundary is loading, or when
// Nominatim has nothing for this suburb. Not a real postcode shape, just a
// rough "somewhere around here" circle.
const FALLBACK_RADIUS_M = 15000

const BOUNDARY_STYLE = { color: '#10b981', weight: 2, fillColor: '#10b981', fillOpacity: 0.15 }

// Pans/zooms the map to fit a freshly-loaded boundary polygon — GeoJSON's
// own bounds, not the fixed state-scale zoom used for the fallback circle.
function FitToBoundary({ geojson }) {
  const map = useMap()
  useEffect(() => {
    if (!geojson) return
    const layer = new L.GeoJSON(geojson)
    const bounds = layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] })
  }, [geojson, map])
  return null
}

export default function ClubLocationMap({ clubId, latitude, longitude, postcode, state }) {
  const [boundary, setBoundary] = useState(null)
  const [boundaryLoaded, setBoundaryLoaded] = useState(false)

  useEffect(() => {
    setBoundary(null)
    setBoundaryLoaded(false)
    if (!clubId) return
    let cancelled = false
    api.mktClubBoundary(clubId)
      .then(d => { if (!cancelled) setBoundary(d?.geojson || null) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setBoundaryLoaded(true) })
    return () => { cancelled = true }
  }, [clubId])

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
      <div style={{ height: 260 }}>
        <MapContainer
          center={center}
          zoom={ZOOM}
          scrollWheelZoom
          dragging
          zoomControl
          doubleClickZoom
          style={{ height: '100%', width: '100%', background: 'var(--pb-surface2)' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {boundary ? (
            <>
              <GeoJSON key={JSON.stringify(boundary)} data={boundary} style={() => BOUNDARY_STYLE} />
              <FitToBoundary geojson={boundary} />
            </>
          ) : (
            <Circle
              center={center}
              radius={FALLBACK_RADIUS_M}
              pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.18, weight: 1 }}
            />
          )}
          <CircleMarker
            center={center}
            radius={4}
            pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 1, weight: 1 }}
          />
        </MapContainer>
      </div>
      <div className="px-2 py-1 border-t pb-hairline-t font-mono text-[9px] text-pb-faintest">
        {boundary
          ? <>Suburb boundary for postcode {postcode || '—'}{state ? `, ${state}` : ''} · via OpenStreetMap</>
          : boundaryLoaded
            ? <>No suburb boundary found — approximate area for postcode {postcode || '—'}{state ? `, ${state}` : ''}</>
            : <>Loading boundary…</>}
      </div>
    </div>
  )
}
