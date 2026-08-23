import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterCrmLayout from '../../../components/admin/BetterCrmLayout'
import { PbSpinner } from '../../../lib/presskit'
import { Modal, Field, TextInput, Btn, Pill } from '../../../components/admin/crm/ui'

function AddCustomModal({ open, onClose, onAdded }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) setName('') }, [open])

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      await api.crmAddTracker({ name: name.trim() })
      onAdded()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not create tracker') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Custom tracker">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name" hint="e.g. Facility hire enquiries, Merchandise pre-orders. Anything worth tracking stage-by-stage.">
          <TextInput autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Facility Hire" />
        </Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Create tracker</Btn></div>
      </form>
    </Modal>
  )
}

export default function BetterCrmHome() {
  const toast = useToast()
  const navigate = useNavigate()
  const [catalogue, setCatalogue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCustom, setShowCustom] = useState(false)

  const load = useCallback(() => {
    api.crmTrackerCatalogue().then(setCatalogue).catch(e => toast.error(e.message || 'Could not load trackers')).finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const addPreset = async (key) => {
    try {
      const pipeline = await api.crmAddTracker({ template_key: key })
      load()
      navigate(`/admin/crm/${pipeline.id}`)
    } catch (e) { toast.error(e.message || 'Could not add tracker') }
  }

  const reactivateCustom = async (id) => {
    try { await api.crmReactivateTracker(id); load() } catch (e) { toast.error(e.message || 'Could not reactivate') }
  }

  const removeTracker = async (id) => {
    if (!window.confirm('Remove this tracker? Its records stay saved. You can add it back any time.')) return
    try { await api.crmRemoveTracker(id); load() } catch (e) { toast.error(e.message || 'Could not remove tracker') }
  }

  if (loading) return <BetterCrmLayout title="BetterCRM"><PbSpinner message="Loading…" /></BetterCrmLayout>
  if (!catalogue) return <BetterCrmLayout title="BetterCRM" />

  const activePresets = catalogue.presets.filter(p => p.active)
  const availablePresets = catalogue.presets.filter(p => !p.active)
  const activeCustom = catalogue.custom.filter(c => c.active)
  const inactiveCustom = catalogue.custom.filter(c => !c.active)
  const hasAny = activePresets.length > 0 || activeCustom.length > 0

  return (
    <BetterCrmLayout title="BetterCRM">
      <div className="space-y-8">
        {hasAny && (
          <section>
            <h2 className="font-display font-bold text-sm text-pb-faint uppercase tracking-wide mb-3">Your trackers</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {activePresets.map(p => (
                <div key={p.pipeline_id} className="pb-card p-4 flex flex-col gap-2">
                  <button onClick={() => navigate(`/admin/crm/${p.pipeline_id}`)} className="text-left flex-1">
                    <div className="font-display font-bold text-sm mb-1">{p.label}</div>
                    <div className="text-[12.5px] text-pb-faint">{p.blurb}</div>
                  </button>
                  <div className="flex justify-end">
                    <button onClick={() => removeTracker(p.pipeline_id)} className="text-[11px] text-pb-faintest hover:text-pb-red">Remove</button>
                  </div>
                </div>
              ))}
              {activeCustom.map(c => (
                <div key={c.id} className="pb-card p-4 flex flex-col gap-2">
                  <button onClick={() => navigate(`/admin/crm/${c.id}`)} className="text-left flex-1">
                    <div className="font-display font-bold text-sm mb-1">{c.name}</div>
                    <Pill>Custom</Pill>
                  </button>
                  <div className="flex justify-end">
                    <button onClick={() => removeTracker(c.id)} className="text-[11px] text-pb-faintest hover:text-pb-red">Remove</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="font-display font-bold text-sm text-pb-faint uppercase tracking-wide mb-1">Add a tracker</h2>
          <p className="text-[12.5px] text-pb-faint mb-3">
            Optional: only turn on what your club actually does. Not every club runs sponsorship, grants or alumni fundraising.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {availablePresets.map(p => (
              <div key={p.key} className="pb-card p-4 flex flex-col gap-2 border-dashed">
                <div className="font-display font-bold text-sm">{p.label}</div>
                <div className="text-[12.5px] text-pb-faint flex-1">{p.blurb}</div>
                <Btn variant="ghost" sm onClick={() => addPreset(p.key)}>Add</Btn>
              </div>
            ))}
            {inactiveCustom.map(c => (
              <div key={c.id} className="pb-card p-4 flex flex-col gap-2 border-dashed">
                <div className="font-display font-bold text-sm">{c.name}</div>
                <Pill>Custom · removed</Pill>
                <Btn variant="ghost" sm onClick={() => reactivateCustom(c.id)}>Reactivate</Btn>
              </div>
            ))}
            <div className="pb-card p-4 flex flex-col gap-2 border-dashed items-start justify-center">
              <div className="text-[12.5px] text-pb-faint">Something else worth tracking?</div>
              <Btn variant="ghost" sm onClick={() => setShowCustom(true)}>+ Custom tracker</Btn>
            </div>
          </div>
        </section>
      </div>
      <AddCustomModal open={showCustom} onClose={() => setShowCustom(false)} onAdded={load} />
    </BetterCrmLayout>
  )
}
