import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Circle, CircleMarker, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../../lib/api'

// State-scale zoom — close enough to read as "this part of the state"
// without needing a per-state bounding box; centering on the club's own
// coordinates keeps it simple since those are always inside its own state.
const ZOOM = 7
// Used when we only have a boundary polygon (no lat/lng) to pick an initial
// zoom before FitToBoundary refines it — and as the fallback circle's zoom.
const BOUNDARY_ZOOM = 12
// Fallback only — used when we have coordinates but no real boundary
// (still loading, or Nominatim has nothing for this suburb). Not a real
// postcode shape, just a rough "somewhere around here" circle.
const FALLBACK_RADIUS_M = 15000

const BOUNDARY_STYLE = { color: '#10b981', weight: 2, fillColor: '#10b981', fillOpacity: 0.15 }

// Pans/zooms the map to fit a freshly-loaded boundary polygon — GeoJSON's
// own bounds, not the fixed zoom used for the initial render.
function FitToBoundary({ geojson }) {
  const map = useMap()
  useEffect(() => {
    if (!geojson) return
    const bounds = L.geoJSON(geojson).getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] })
  }, [geojson, map])
  return null
}

// `preloadedBoundary` lets a caller that already has the geojson skip the
// internal fetch entirely. `undefined` (the default) means "no preload was
// given, fetch it yourself" — `null` is a real, already-resolved "no
// boundary found" so it must be distinguished from "hasn't loaded yet".
//
// `fetchBoundary` overrides WHERE it self-fetches from, for a caller whose
// user can't reach the Club Directory's super-admin-only /boundary route —
// the Sales Workspace drawer passes its own deal-scoped endpoint. It takes
// the clubId and resolves to the same `{ geojson }` shape.
export default function ClubLocationMap({ clubId, latitude, longitude, postcode, state,
                                          preloadedBoundary, fetchBoundary }) {
  const hasPreload = preloadedBoundary !== undefined
  const [boundary, setBoundary] = useState(hasPreload ? preloadedBoundary : null)
  const [boundaryLoaded, setBoundaryLoaded] = useState(hasPreload)

  useEffect(() => {
    if (hasPreload) { setBoundary(preloadedBoundary); setBoundaryLoaded(true); return }
    setBoundary(null)
    setBoundaryLoaded(false)
    if (!clubId) return
    let cancelled = false
    const load = fetchBoundary || api.mktClubBoundary
    load(clubId)
      .then(d => { if (!cancelled) setBoundary(d?.geojson || null) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setBoundaryLoaded(true) })
    return () => { cancelled = true }
    // fetchBoundary is deliberately not a dependency — a caller declaring it
    // inline would otherwise re-fetch on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clubId, hasPreload, preloadedBoundary])

  const hasPoint = latitude != null && longitude != null
  // A boundary polygon can stand in for a centre point when the club has no
  // lat/lng of its own (common — PlayHQ doesn't always supply coordinates,
  // even when it does supply a suburb/postcode) — same data either way.
  const boundaryCenter = useMemo(() => {
    if (!boundary) return null
    const bounds = L.geoJSON(boundary).getBounds()
    if (!bounds.isValid()) return null
    const c = bounds.getCenter()
    return [c.lat, c.lng]
  }, [boundary])

  if (!hasPoint && !boundaryLoaded) {
    return (
      <div className="pb-card px-3 py-4 text-center font-mono text-[10px] text-pb-faint">
        Loading location…
      </div>
    )
  }
  if (!hasPoint && !boundaryCenter) {
    return (
      <div className="pb-card px-3 py-4 text-center font-mono text-[10px] text-pb-faint">
        No location on file for this club.
      </div>
    )
  }

  const center = hasPoint ? [latitude, longitude] : boundaryCenter
  const zoom = hasPoint ? ZOOM : BOUNDARY_ZOOM
  return (
    <div className="pb-card overflow-hidden">
      <div style={{ height: 260 }}>
        <MapContainer
          center={center}
          zoom={zoom}
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
          ) : hasPoint ? (
            <Circle
              center={center}
              radius={FALLBACK_RADIUS_M}
              pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.18, weight: 1 }}
            />
          ) : null}
          {hasPoint && (
            <CircleMarker
              center={center}
              radius={4}
              pathOptions={{ color: '#10b981', fillColor: '#10b981', fillOpacity: 1, weight: 1 }}
            />
          )}
        </MapContainer>
      </div>
      <div className="px-2 py-1 border-t pb-hairline-t font-mono text-[9px] text-pb-faintest">
        {boundary
          ? <>Suburb boundary for postcode {postcode || '—'}{state ? `, ${state}` : ''} · via OpenStreetMap</>
          : boundaryLoaded
            ? hasPoint
              ? <>No suburb boundary found — approximate area for postcode {postcode || '—'}{state ? `, ${state}` : ''}</>
              : <>Loading boundary…</>
            : <>Loading boundary…</>}
      </div>
    </div>
  )
}
