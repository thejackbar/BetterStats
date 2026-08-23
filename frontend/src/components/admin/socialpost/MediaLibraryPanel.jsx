// Photos panel — the club media library, player headshots, and club marks.
//
// Uploads are club-scoped and reusable (see "Backend work" in the README): this
// component expects the list from the API and reports new files upward.
//
// Props:
//   assets            [{ id, name, url }]  from GET /social/media
//   onUpload(files)   File[] => void       POST /social/media, optimistic add
//   onUseAsset(asset) picks it for the selected image block, or adds a new one
//   onAddEmptyFrame() adds an image block with no source
//   players           roster (for headshot blocks)
//   onAddPlayerPhoto(playerId)
//   onAddBrandLockup()
//   sponsors          [{ name, url }] from the brand kit
//   onAddSponsor(sponsor)
//   club              { name, logo_url } from api.adminGetSettings()
import { useState } from 'react'

const TABS = [
  { key: 'uploads', label: 'Uploads' },
  { key: 'players', label: 'Players' },
  { key: 'club', label: 'Club' },
]

const stripe = 'repeating-linear-gradient(135deg, var(--pb-surface2) 0 6px, var(--pb-hairline) 6px 12px)'

export default function MediaLibraryPanel({
  assets = [], onUpload, onUseAsset, onAddEmptyFrame,
  players = [], onAddPlayerPhoto,
  onAddBrandLockup, sponsors = [], onAddSponsor, club,
}) {
  const [tab, setTab] = useState('uploads')
  const [dragOver, setDragOver] = useState(false)

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex gap-0.5 p-[3px] rounded-lg bg-pb-surface2 border pb-hairline">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex-1 py-1.5 rounded-md font-mono text-[9px] tracking-wide2 uppercase transition-colors ${
              tab === t.key ? 'bg-pb-surface text-pb-text' : 'text-pb-faint hover:text-pb-dim'
            }`}>{t.label}</button>
        ))}
      </div>

      {tab === 'uploads' && (
        <div className="flex flex-col gap-3">
          <label
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); onUpload(Array.from(e.dataTransfer.files || [])) }}
            className={`block p-[18px] rounded-lg border border-dashed text-center text-[11px] leading-relaxed cursor-pointer transition-colors ${
              dragOver ? 'border-pb-accent text-pb-text' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'
            }`}
            style={{ background: 'var(--pb-surface2)' }}
          >
            Drop images here, or click to upload
            <span className="block font-mono text-[9px] text-pb-faint mt-1">PNG · JPG · WEBP: kept in the club library</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple className="sr-only"
              onChange={e => { onUpload(Array.from(e.target.files || [])); e.target.value = '' }} />
          </label>

          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Club library</span>
            <span className="font-mono text-[9px] text-pb-faintest">{assets.length} in library</span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {assets.map(a => (
              <button key={a.id} title={a.name} onClick={() => onUseAsset(a)}
                className="relative aspect-square rounded-lg border pb-hairline overflow-hidden hover:border-pb-accent transition-colors"
                style={a.url ? { background: `center/cover no-repeat url(${a.url})` } : { background: stripe }}>
                <span className="absolute inset-x-0 bottom-0 px-1.5 py-1 text-left font-mono text-[7.5px] leading-tight text-pb-dim"
                  style={{ background: 'linear-gradient(transparent, rgba(7,9,15,.9))' }}>{a.name}</span>
              </button>
            ))}
          </div>

          <button onClick={onAddEmptyFrame}
            className="py-2 rounded-md border pb-hairline font-mono text-[10px] text-pb-dim hover:text-pb-text transition-colors">
            + Empty image frame
          </button>
        </div>
      )}

      {tab === 'players' && (
        <div>
          <p className="text-[11px] leading-relaxed text-pb-dim mb-2.5">
            Headshots from player profiles. The block stays linked, so the photo updates when the profile does.
          </p>
          <div className="grid grid-cols-3 gap-2">
            {players.map(p => {
              const name = p.display_name || p.name || ''
              return (
                <button key={p.id} onClick={() => onAddPlayerPhoto(p.id)}
                  className="aspect-square rounded-lg border pb-hairline overflow-hidden hover:border-pb-accent transition-colors grid place-items-end p-1"
                  style={p.photo_url ? { background: `center/cover no-repeat url(${p.photo_url})` } : { background: stripe }}>
                  <span className="font-mono text-[8px] text-pb-dim text-left leading-tight">{name}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {tab === 'club' && (
        <div className="flex flex-col gap-3">
          <button onClick={onAddBrandLockup}
            className="w-full flex items-center gap-2.5 p-2.5 rounded-lg border pb-hairline bg-pb-surface2 text-pb-text text-[11px] hover:border-pb-accent transition-colors">
            {club?.logo_url
              ? <img src={club.logo_url} alt="" className="w-[26px] h-[26px] rounded object-contain shrink-0" />
              : <span className="w-[26px] h-[26px] rounded grid place-items-center font-mono text-[11px] font-bold shrink-0"
                  style={{ background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)' }}>
                  {(club?.name || 'C').slice(0, 2).toUpperCase()}
                </span>}
            Add the club lockup
          </button>

          <div>
            <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-2">Sponsor logos</div>
            <div className="flex flex-col gap-1.5">
              {sponsors.map((sp, i) => (
                <button key={i} onClick={() => onAddSponsor(sp)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-md border pb-hairline bg-pb-surface2 text-[11px] text-pb-dim hover:border-pb-accent transition-colors">
                  {sp.url
                    ? <img src={sp.url} alt="" className="w-6 h-6 rounded object-contain shrink-0" />
                    : <span className="w-6 h-6 rounded shrink-0" style={{ background: stripe }} />}
                  {sp.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
