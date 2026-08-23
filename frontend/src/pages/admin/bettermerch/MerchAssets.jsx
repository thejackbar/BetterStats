import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { SearchInput } from '../../../components/admin/ui'
import { PbSpinner } from '../../../lib/presskit'
import {
  money, CONDITIONS, ASSET_STATUSES, Btn, Field, TextInput, NumberInput, Select, TextArea, Modal, Pill, Icon,
} from './ui'

const today = () => new Date().toISOString().slice(0, 10)

function dueTone(dateStr) {
  if (!dateStr) return null
  const d = dateStr
  const t = today()
  const soon = new Date(t)
  soon.setDate(soon.getDate() + 30)
  if (d < t) return 'red'
  if (d <= soon.toISOString().slice(0, 10)) return 'amber'
  return null
}

function AssetModal({ asset, onClose, onSaved }) {
  const toast = useToast()
  const edit = !!asset
  const [f, setF] = useState({
    name: asset?.name || '',
    asset_tag: asset?.asset_tag || '',
    purchase_cost: asset?.purchase_cost ?? '',
    purchase_date: asset?.purchase_date || '',
    condition: asset?.condition || 'good',
    service_due_date: asset?.service_due_date || '',
    replace_due_date: asset?.replace_due_date || '',
    status: asset?.status || 'in_service',
    notes: asset?.notes || '',
  })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }))

  const submit = async () => {
    if (!f.name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      const payload = {
        name: f.name.trim(),
        asset_tag: f.asset_tag || null,
        purchase_cost: f.purchase_cost === '' ? null : Number(f.purchase_cost),
        purchase_date: f.purchase_date || null,
        condition: f.condition,
        service_due_date: f.service_due_date || null,
        replace_due_date: f.replace_due_date || null,
        status: f.status,
        notes: f.notes || null,
      }
      if (edit) await api.merchUpdateAsset(asset.id, payload)
      else await api.merchCreateAsset(payload)
      toast.success(edit ? 'Saved' : 'Equipment added')
      onSaved()
    } catch (e) {
      toast.error(e.message || 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const dateCls = 'w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px]'
  return (
    <Modal open wide title={edit ? 'Edit equipment' : 'New equipment'} onClose={onClose}
      footer={<>
        {edit && <Btn variant="danger" onClick={async () => { await api.merchDeleteAsset(asset.id); toast.success('Removed'); onSaved() }}>Remove</Btn>}
        <Btn variant="subtle" onClick={onClose}>Cancel</Btn>
        <Btn variant="primary" onClick={submit} disabled={busy}>{edit ? 'Save' : 'Add'}</Btn>
      </>}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <Field half label="Name"><TextInput value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Bola bowling machine" /></Field>
          <Field half label="Asset tag / serial"><TextInput value={f.asset_tag} onChange={(e) => set('asset_tag', e.target.value)} /></Field>
        </div>
        <div className="flex gap-2">
          <Field half label="Purchase cost"><NumberInput value={f.purchase_cost} onChange={(e) => set('purchase_cost', e.target.value)} placeholder="0.00" /></Field>
          <Field half label="Purchased"><input type="date" className={dateCls} value={f.purchase_date} onChange={(e) => set('purchase_date', e.target.value)} /></Field>
        </div>
        <div className="flex gap-2">
          <Field half label="Condition">
            <Select value={f.condition} onChange={(e) => set('condition', e.target.value)}>
              {CONDITIONS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </Select>
          </Field>
          <Field half label="Status">
            <Select value={f.status} onChange={(e) => set('status', e.target.value)}>
              {ASSET_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </Select>
          </Field>
        </div>
        <div className="flex gap-2">
          <Field half label="Next service due" hint="For cashflow planning"><input type="date" className={dateCls} value={f.service_due_date} onChange={(e) => set('service_due_date', e.target.value)} /></Field>
          <Field half label="Replace by"><input type="date" className={dateCls} value={f.replace_due_date} onChange={(e) => set('replace_due_date', e.target.value)} /></Field>
        </div>
        <Field label="Notes"><TextArea value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Service history, condition notes…" /></Field>
      </div>
    </Modal>
  )
}

function AssetRow({ asset, onEdit }) {
  const sTone = dueTone(asset.service_due_date)
  const rTone = dueTone(asset.replace_due_date)
  return (
    <div className="pb-card p-4 flex items-start justify-between gap-3 cursor-pointer hover:border-pb-accent/40 transition" onClick={() => onEdit(asset)}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-display font-bold text-sm truncate">{asset.name}</h3>
          <Pill tone={asset.condition === 'poor' || asset.condition === 'retired' ? 'red' : 'faint'}>{asset.condition}</Pill>
          {asset.status !== 'in_service' && <Pill tone="amber">{asset.status.replace(/_/g, ' ')}</Pill>}
        </div>
        <div className="text-[11.5px] text-pb-faint mt-1 flex flex-wrap gap-x-3 gap-y-1">
          {asset.asset_tag && <span>#{asset.asset_tag}</span>}
          {asset.purchase_cost != null && <span>{money(asset.purchase_cost)}</span>}
          {asset.service_due_date && <span className={sTone ? (sTone === 'red' ? 'text-pb-red' : 'text-pb-amber') : ''}>service {asset.service_due_date}</span>}
          {asset.replace_due_date && <span className={rTone ? (rTone === 'red' ? 'text-pb-red' : 'text-pb-amber') : ''}>replace {asset.replace_due_date}</span>}
        </div>
        {asset.notes && <p className="text-[11.5px] text-pb-faint mt-1 line-clamp-2">{asset.notes}</p>}
      </div>
      <Icon name="settings" size={16} className="text-pb-faint shrink-0" />
    </div>
  )
}

export default function MerchAssets() {
  const toast = useToast()
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState(null)
  const [q, setQ] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.merchListAssets()
      setAssets(d.assets || [])
    } catch (e) {
      toast.error(e.message || 'Could not load equipment')
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  // A piece of equipment is found by what it is, where it lives, what state it
  // is in or the tag written on it — not only its name.
  const needle = q.trim().toLowerCase()
  const shown = needle
    ? assets.filter(a => [a.name, a.asset_tag, a.location, a.condition, a.status, a.notes]
        .some(v => v && String(v).toLowerCase().includes(needle)))
    : assets

  return (
    <BetterMerchLayout title="Equipment"
      // Search under the heading, with Bookmarks and the primary action beside
      // it on that same line.
      twoRow
      filters={<SearchInput wide value={q} onChange={setQ} placeholder="Search equipment, location, condition…" />}
      actions={<Btn variant="primary" sm icon="plus" onClick={() => setShowNew(true)}>New equipment</Btn>}>
      <p className="text-[12.5px] text-pb-faint mb-4">High-value gear tracked one item at a time — condition plus service and replace dates feed the alerts and your cashflow planning. Bulk gear (a box of balls) lives in <b>Stock</b> instead.</p>
      {loading ? <PbSpinner message="Loading equipment…" /> : assets.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">
          No equipment yet. <button className="text-pb-accent" onClick={() => setShowNew(true)}>Add a bowling machine, covers, sight screen…</button>
        </div>
      ) : shown.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">Nothing matches “{q}”.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {shown.map((a) => <AssetRow key={a.id} asset={a} onEdit={setEditing} />)}
        </div>
      )}
      {showNew && <AssetModal onClose={() => setShowNew(false)} onSaved={() => { setShowNew(false); load() }} />}
      {editing && <AssetModal asset={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
    </BetterMerchLayout>
  )
}
