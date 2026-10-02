import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { validateImageFile } from '../../lib/validation'
import ImageEditorModal from '../../components/ImageEditorModal'
import { useToast } from '../../contexts/ToastContext'
import { clearClubSponsors } from '../../lib/useClubSponsors'

export default function AdminSponsors() {
  const toast = useToast()
  const [sponsors, setSponsors] = useState([])
  // Tier and spot definitions from the server, plus this club's tier names.
  const [meta, setMeta] = useState(null)
  const [labelDraft, setLabelDraft] = useState({})
  const [labelSaving, setLabelSaving] = useState(false)
  // Section names: [{ key, default_label, where, name, sponsor_id }] plus the unsaved draft.
  const [sections, setSections] = useState([])
  const [sectionDraft, setSectionDraft] = useState({})
  const [sectionSaving, setSectionSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Add form
  const [addName, setAddName] = useState('')
  const [addUrl, setAddUrl] = useState('')
  const [addTier, setAddTier] = useState('silver')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState(null)

  // Edit state: { [id]: { name, website_url } }
  const [editing, setEditing] = useState({})
  const [saving, setSaving] = useState({})

  // Reorder
  const [dirty, setDirty] = useState(false)
  const [reordering, setReordering] = useState(false)
  const dragItem = useRef(null)
  const dragOver = useRef(null)

  // Logo upload state: { [id]: uploading|error|null }
  const [logoState, setLogoState] = useState({})
  const [flash, setFlash] = useState(null)

  // Editor: { sponsorId, source } when open
  const [editor, setEditor] = useState(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const [data, settings, secs] = await Promise.all([
        api.adminListSponsors(), api.adminGetSponsorSettings(), api.adminGetSectionNames(),
      ])
      setSponsors(data)
      setMeta(settings)
      setLabelDraft(settings.tier_labels || {})
      applySections(secs)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function showFlash(msg) {
    setFlash(msg)
    setTimeout(() => setFlash(null), 3000)
  }

  async function handleAdd(e) {
    e.preventDefault()
    if (!addName.trim()) return
    setAdding(true)
    setAddError(null)
    try {
      const s = await api.adminCreateSponsor({ name: addName.trim(), website_url: addUrl.trim() || null, tier: addTier })
      setSponsors(prev => [...prev, s])
      clearClubSponsors()
      setAddName('')
      setAddUrl('')
      showFlash('Sponsor added')
    } catch (e) {
      setAddError(e.message)
    } finally {
      setAdding(false)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this sponsor?')) return
    try {
      await api.adminDeleteSponsor(id)
      setSponsors(prev => prev.filter(s => s.id !== id))
      showFlash('Sponsor deleted')
    } catch (e) {
      toast.error(e.message)
    }
  }

  function startEdit(sponsor) {
    setEditing(prev => ({ ...prev, [sponsor.id]: { name: sponsor.name, website_url: sponsor.website_url || '' } }))
  }

  function cancelEdit(id) {
    setEditing(prev => { const n = { ...prev }; delete n[id]; return n })
  }

  async function saveEdit(id) {
    const vals = editing[id]
    if (!vals || !vals.name.trim()) return
    setSaving(prev => ({ ...prev, [id]: true }))
    try {
      const updated = await api.adminPatchSponsor(id, { name: vals.name.trim(), website_url: vals.website_url.trim() || null })
      setSponsors(prev => prev.map(s => s.id === id ? { ...s, ...updated } : s))
      cancelEdit(id)
      showFlash('Saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSaving(prev => { const n = { ...prev }; delete n[id]; return n })
    }
  }

  async function handleLogoUpload(id, file) {
    setLogoState(prev => ({ ...prev, [id]: 'uploading' }))
    try {
      const updated = await api.adminUploadSponsorLogo(id, file)
      setSponsors(prev => prev.map(s => s.id === id ? { ...s, ...updated } : s))
      setLogoState(prev => { const n = { ...prev }; delete n[id]; return n })
      showFlash('Logo uploaded')
    } catch (e) {
      setLogoState(prev => ({ ...prev, [id]: e.message }))
    }
  }

  async function handleLogoDelete(id) {
    try {
      const updated = await api.adminDeleteSponsorLogo(id)
      setSponsors(prev => prev.map(s => s.id === id ? { ...s, ...updated } : s))
      showFlash('Logo removed')
    } catch (e) {
      toast.error(e.message)
    }
  }

  function applySections(view) {
    setSections(view.sections || [])
    setSectionDraft(Object.fromEntries((view.sections || []).map(x => [x.key, { name: x.name || '', sponsor_id: x.sponsor_id || '' }])))
  }

  async function saveSections() {
    setSectionSaving(true)
    try {
      // A section with no name and no sponsor is sent too, and the server drops it.
      const body = Object.fromEntries(Object.entries(sectionDraft).map(([k, v]) => [k, {
        name: v.name.trim() || null, sponsor_id: v.sponsor_id || null,
      }]))
      applySections(await api.adminPutSectionNames(body))
      clearClubSponsors()
      showFlash('Section names saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSectionSaving(false)
    }
  }

  const tierLabel = (key) => (meta?.tier_labels?.[key]) || key
  const defaultSpots = (tier) => meta?.tiers?.find(t => t.key === tier)?.default_placements || []

  async function patchSponsor(id, body, doneMsg) {
    try {
      const updated = await api.adminPatchSponsor(id, body)
      setSponsors(prev => prev.map(s => s.id === id ? { ...s, ...updated } : s))
      clearClubSponsors()
      if (doneMsg) showFlash(doneMsg)
    } catch (e) {
      toast.error(e.message)
    }
  }

  // A spot toggled back to what the tier already does is not an override, so
  // send null and let the sponsor follow its tier for that spot again.
  function toggleSpot(sponsor, spot) {
    const on = sponsor.placements.includes(spot)
    const tierDefault = defaultSpots(sponsor.tier).includes(spot)
    const next = !on
    patchSponsor(sponsor.id, { placements: { [spot]: next === tierDefault ? null : next } })
  }

  async function saveLabels() {
    setLabelSaving(true)
    try {
      const settings = await api.adminPutSponsorSettings({ tier_labels: labelDraft })
      setMeta(settings)
      setLabelDraft(settings.tier_labels || {})
      clearClubSponsors()
      showFlash('Tier names saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLabelSaving(false)
    }
  }

  // Drag-and-drop reorder
  function onDragStart(index) {
    dragItem.current = index
  }

  function onDragEnter(index) {
    dragOver.current = index
    if (dragItem.current === null || dragItem.current === index) return
    setSponsors(prev => {
      const next = [...prev]
      const dragged = next.splice(dragItem.current, 1)[0]
      next.splice(index, 0, dragged)
      dragItem.current = index
      return next
    })
    setDirty(true)
  }

  function onDragEnd() {
    dragItem.current = null
    dragOver.current = null
  }

  async function saveOrder() {
    setReordering(true)
    try {
      await api.adminReorderSponsors(sponsors.map((s, i) => ({ id: s.id, display_order: i + 1 })))
      setDirty(false)
      showFlash('Order saved')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setReordering(false)
    }
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-2xl">
        <div className="flex items-center justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Sponsors</h1>
          {dirty && (
            <button
              onClick={saveOrder}
              disabled={reordering}
              className="px-4 py-1.5 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-50"
            >
              {reordering ? 'Saving…' : 'Save order'}
            </button>
          )}
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Pick a tier for each sponsor. The tier decides where they show, and you can switch any spot on or off for one sponsor.
          The bottom bar shows up to 6 logos, biggest tier first. Drag rows to set the order within a tier.
        </p>

        {flash && (
          <div className="mb-4 px-4 py-2 rounded bg-green-500/10 text-green-400 text-sm font-mono">{flash}</div>
        )}
        {error && (
          <div className="mb-4 text-red-400 text-sm">{error}</div>
        )}

        {/* Sponsor list */}
        {!loading && (
          <div className="pb-card overflow-hidden mb-6">
            {sponsors.length === 0 && (
              <div className="px-4 py-8 text-center font-mono text-[11px] text-pb-faint">
                No sponsors yet. Add one below.
              </div>
            )}
            {sponsors.map((sponsor, i) => {
              const isEditing = !!editing[sponsor.id]
              const logoUploading = logoState[sponsor.id] === 'uploading'
              const logoErr = logoState[sponsor.id] && logoState[sponsor.id] !== 'uploading' ? logoState[sponsor.id] : null

              return (
                <div
                  key={sponsor.id}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragEnter={() => onDragEnter(i)}
                  onDragEnd={onDragEnd}
                  onDragOver={e => e.preventDefault()}
                  className={`${i > 0 ? 'pb-hairline-t' : ''} px-4 py-3 cursor-grab active:cursor-grabbing`}
                >
                  <div className="flex items-start gap-3">
                    {/* Drag handle */}
                    <span className="text-pb-faintest mt-1 select-none text-xs">⠿</span>

                    {/* Logo thumbnail */}
                    <div className="shrink-0 w-16 h-10 flex items-center justify-center bg-pb-surface2 rounded overflow-hidden">
                      {sponsor.logo_url ? (
                        <img src={sponsor.logo_url} alt={sponsor.name} className="max-w-full max-h-full object-contain" />
                      ) : (
                        <span className="text-pb-faintest font-mono text-[9px]">NO LOGO</span>
                      )}
                    </div>

                    {/* Info / edit fields */}
                    <div className="flex-1 min-w-0">
                      {isEditing ? (
                        <div className="space-y-1.5">
                          <input
                            value={editing[sponsor.id].name}
                            onChange={e => setEditing(prev => ({ ...prev, [sponsor.id]: { ...prev[sponsor.id], name: e.target.value } }))}
                            placeholder="Sponsor name"
                            className="w-full px-2 py-1 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                          />
                          <input
                            value={editing[sponsor.id].website_url}
                            onChange={e => setEditing(prev => ({ ...prev, [sponsor.id]: { ...prev[sponsor.id], website_url: e.target.value } }))}
                            placeholder="https://example.com"
                            className="w-full px-2 py-1 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEdit(sponsor.id)}
                              disabled={saving[sponsor.id]}
                              className="px-3 py-1 text-xs rounded bg-pb-accent text-white disabled:opacity-50"
                            >
                              {saving[sponsor.id] ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              onClick={() => cancelEdit(sponsor.id)}
                              className="px-3 py-1 text-xs rounded border pb-hairline text-pb-faint hover:text-pb-text"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="text-pb-text text-sm font-medium truncate">{sponsor.name}</div>
                          {sponsor.website_url && (
                            <a
                              href={sponsor.website_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-pb-faint text-[11px] hover:text-pb-accent truncate block"
                            >
                              {sponsor.website_url}
                            </a>
                          )}
                          {!sponsor.logo_url && (
                            <span className="text-amber-400 text-[10px] font-mono block">No logo: shown by name in the sponsor list only</span>
                          )}
                          {meta && (
                            <div className="mt-2 space-y-1.5">
                              <select
                                aria-label={`Tier for ${sponsor.name}`}
                                value={sponsor.tier}
                                onChange={e => patchSponsor(sponsor.id, { tier: e.target.value }, 'Tier saved')}
                                className="px-2 py-1 text-xs bg-pb-bg border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent"
                              >
                                {meta.tiers.map(t => (
                                  <option key={t.key} value={t.key}>{tierLabel(t.key)}</option>
                                ))}
                              </select>
                              <div className="flex flex-wrap items-center gap-1.5">
                                {meta.placements.map(p => {
                                  const on = sponsor.placements.includes(p.key)
                                  const overridden = sponsor.placement_overrides?.[p.key] !== undefined
                                  return (
                                    <button
                                      key={p.key}
                                      type="button"
                                      aria-pressed={on}
                                      onClick={() => toggleSpot(sponsor, p.key)}
                                      title={overridden ? 'Set by hand. Click to change.' : 'Follows the tier. Click to switch it.'}
                                      className={`font-mono text-[10px] px-2 py-0.5 rounded border ${
                                        on ? 'bg-pb-accent/15 border-pb-accent text-pb-text' : 'pb-hairline text-pb-faint'
                                      }`}
                                    >
                                      {p.label}{overridden ? ' *' : ''}
                                    </button>
                                  )
                                })}
                                {Object.keys(sponsor.placement_overrides || {}).length > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => patchSponsor(sponsor.id, { placements: null }, 'Back to the tier defaults')}
                                    className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline"
                                  >
                                    Reset to tier
                                  </button>
                                )}
                              </div>
                              {sponsor.placements.includes('dashboard') && !sponsor.logo_url && (
                                <span className="text-amber-400 text-[10px] font-mono block">Add a logo for the dashboard slot and the bottom bar</span>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {/* Actions */}
                    {!isEditing && (
                      <div className="flex flex-col gap-1 shrink-0">
                        <button
                          onClick={() => startEdit(sponsor)}
                          className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline"
                        >
                          EDIT
                        </button>

                        {/* Logo upload */}
                        <label className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline cursor-pointer text-center">
                          {logoUploading ? 'UPLOADING…' : (sponsor.logo_url ? 'REPLACE' : 'LOGO')}
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/svg+xml,image/webp"
                            className="hidden"
                            onChange={e => {
                              const f = e.target.files?.[0]
                              e.target.value = ''
                              if (!f) return
                              const err = validateImageFile(f)
                              if (err) {
                                setLogoState(prev => ({ ...prev, [sponsor.id]: err }))
                                return
                              }
                              setEditor({ sponsorId: sponsor.id, source: f })
                            }}
                          />
                        </label>

                        {sponsor.logo_url && (
                          <button
                            onClick={() => setEditor({ sponsorId: sponsor.id, source: sponsor.logo_url })}
                            className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline"
                          >
                            EDIT
                          </button>
                        )}

                        {sponsor.logo_url && (
                          <button
                            onClick={() => handleLogoDelete(sponsor.id)}
                            className="font-mono text-[10px] text-red-400 hover:text-red-300 px-2 py-1 rounded border border-red-400/30"
                          >
                            RM LOGO
                          </button>
                        )}

                        <button
                          onClick={() => handleDelete(sponsor.id)}
                          className="font-mono text-[10px] text-red-400 hover:text-red-300 px-2 py-1 rounded border border-red-400/30"
                        >
                          DELETE
                        </button>
                      </div>
                    )}
                  </div>

                  {logoErr && (
                    <p className="mt-1 text-red-400 text-[10px] font-mono">{logoErr}</p>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Add new sponsor */}
        <div className="pb-card px-4 py-4">
          <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">Add Sponsor</h2>
          <form onSubmit={handleAdd} className="space-y-2">
            <input
              value={addName}
              onChange={e => setAddName(e.target.value)}
              placeholder="Sponsor name"
              required
              className="w-full px-3 py-2 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
            />
            <input
              value={addUrl}
              onChange={e => setAddUrl(e.target.value)}
              placeholder="Website URL (optional)"
              type="url"
              className="w-full px-3 py-2 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
            />
            {meta && (
              <label className="flex items-center gap-2 text-xs text-pb-faint">
                Tier
                <select
                  value={addTier}
                  onChange={e => setAddTier(e.target.value)}
                  className="px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent"
                >
                  {meta.tiers.map(t => (
                    <option key={t.key} value={t.key}>{tierLabel(t.key)}</option>
                  ))}
                </select>
              </label>
            )}
            {addError && <p className="text-red-400 text-xs">{addError}</p>}
            <button
              type="submit"
              disabled={adding || !addName.trim()}
              className="px-4 py-2 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-40"
            >
              {adding ? 'Adding…' : 'Add Sponsor'}
            </button>
          </form>
          <p className="mt-3 text-pb-faintest text-[11px]">
            After adding, use the LOGO button on the row to upload a logo image. A sponsor without a logo is named in the sponsor list but left out of the bottom bar and the dashboard slot.
          </p>
        </div>

        {/* Tier names */}
        {meta && (
          <div className="pb-card px-4 py-4 mt-6">
            <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-1">Tier names</h2>
            <p className="text-pb-faintest text-[11px] mb-3">
              Rename the tiers to suit your club. Leave one blank to use the standard name. Default spots: {meta.tiers.map(t =>
                `${tierLabel(t.key)} (${t.default_placements.map(k => meta.placements.find(p => p.key === k)?.label).join(', ')})`
              ).join('; ')}.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {meta.tiers.map(t => (
                <label key={t.key} className="text-xs text-pb-faint">
                  {t.default_label}
                  <input
                    value={labelDraft[t.key] ?? ''}
                    onChange={e => setLabelDraft(prev => ({ ...prev, [t.key]: e.target.value }))}
                    maxLength={40}
                    placeholder={t.default_label}
                    className="mt-1 w-full px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                  />
                </label>
              ))}
            </div>
            <button
              type="button"
              onClick={saveLabels}
              disabled={labelSaving}
              className="mt-3 px-4 py-1.5 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-50"
            >
              {labelSaving ? 'Saving…' : 'Save names'}
            </button>
          </div>
        )}

        {/* Section names */}
        {sections.length > 0 && (
          <div className="pb-card px-4 py-4 mt-6" data-testid="section-names">
            <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-1">Section names</h2>
            <p className="text-pb-faintest text-[11px] mb-3">
              Put a sponsor's name on a section of your public site, for example Fantasy becomes "Froth Fantasy Cricket".
              The new name shows in the menu, the page heading and the page's shared link. Link a sponsor and their logo shows
              as "Presented by" on that page. Web addresses stay the same. Leave a name blank to keep the standard one.
            </p>
            <div className="space-y-3">
              {sections.map(sec => {
                const d = sectionDraft[sec.key] || { name: '', sponsor_id: '' }
                return (
                  <div key={sec.key} className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2 items-end">
                    <label className="text-xs text-pb-faint min-w-0">
                      <span className="block truncate">{sec.default_label} <span className="text-pb-faintest">· {sec.where}</span></span>
                      <input
                        value={d.name}
                        onChange={e => setSectionDraft(prev => ({ ...prev, [sec.key]: { ...prev[sec.key], name: e.target.value } }))}
                        maxLength={60}
                        placeholder={sec.default_label}
                        aria-label={`Name for ${sec.default_label}`}
                        className="mt-1 w-full px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent"
                      />
                    </label>
                    <label className="text-xs text-pb-faint min-w-0">
                      Presented by
                      <select
                        value={d.sponsor_id}
                        onChange={e => setSectionDraft(prev => ({ ...prev, [sec.key]: { ...prev[sec.key], sponsor_id: e.target.value } }))}
                        aria-label={`Sponsor for ${sec.default_label}`}
                        className="mt-1 w-full px-2 py-1.5 text-sm bg-pb-bg border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent"
                      >
                        <option value="">No sponsor</option>
                        {sponsors.map(s => (
                          <option key={s.id} value={s.id}>{s.name}{s.logo_url ? '' : ' (no logo)'}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )
              })}
            </div>
            <button
              type="button"
              onClick={saveSections}
              disabled={sectionSaving}
              className="mt-3 px-4 py-1.5 rounded text-sm font-medium bg-pb-accent text-white disabled:opacity-50"
            >
              {sectionSaving ? 'Saving…' : 'Save section names'}
            </button>
          </div>
        )}

        <ImageEditorModal
          open={!!editor}
          source={editor?.source}
          title="Edit Sponsor Logo"
          aspect={null}
          outputType="image/png"
          outputName="sponsor-logo.png"
          onCancel={() => setEditor(null)}
          onApply={async (file) => {
            const sponsorId = editor?.sponsorId
            setEditor(null)
            if (sponsorId) await handleLogoUpload(sponsorId, file)
          }}
        />
      </div>
    </BetterStatsLayout>
  )
}
