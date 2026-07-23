import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterCrmLayout from '../../../components/admin/BetterCrmLayout'
import { PbSpinner } from '../../../lib/presskit'
import { Modal, Field, TextInput, Select, Btn, Pill } from '../../../components/admin/crm/ui'

const ROLES = [
  { key: 'player', label: 'Player' },
  { key: 'parent', label: 'Parent' },
  { key: 'coach', label: 'Coach' },
  { key: 'committee', label: 'Committee' },
  { key: 'volunteer', label: 'Volunteer' },
  { key: 'sponsor_contact', label: 'Sponsor contact' },
  { key: 'donor', label: 'Donor' },
  { key: 'association_official', label: 'Association official' },
  { key: 'school_contact', label: 'School contact' },
  { key: 'council_contact', label: 'Council contact' },
  { key: 'supplier', label: 'Supplier' },
  { key: 'media', label: 'Media' },
  { key: 'other', label: 'Other' },
]
const roleLabel = (k) => ROLES.find(r => r.key === k)?.label || k

function NewPersonModal({ open, onClose, onCreated }) {
  const toast = useToast()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState('other')
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setFullName(''); setEmail(''); setPhone(''); setRole('other') } }, [open])

  const submit = async (e) => {
    e.preventDefault()
    if (!fullName.trim()) return
    setSaving(true)
    try {
      const person = await api.crmCreatePerson({ full_name: fullName.trim(), email: email.trim() || undefined, phone: phone.trim() || undefined })
      await api.crmAddPersonRole(person.id, { role })
      onCreated()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not add contact') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New contact">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Full name"><TextInput autoFocus value={fullName} onChange={e => setFullName(e.target.value)} /></Field>
        <Field label="Email"><TextInput value={email} onChange={e => setEmail(e.target.value)} /></Field>
        <Field label="Phone"><TextInput value={phone} onChange={e => setPhone(e.target.value)} /></Field>
        <Field label="Role">
          <Select value={role} onChange={e => setRole(e.target.value)}>
            {ROLES.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
          </Select>
        </Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Add contact</Btn></div>
      </form>
    </Modal>
  )
}

export default function BetterCrmPeople() {
  const toast = useToast()
  const [people, setPeople] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.crmListPeople(q).then(d => setPeople(d.people || []))
      .catch(e => toast.error(e.message || 'Could not load contacts'))
      .finally(() => setLoading(false))
  }, [q, toast])

  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t) }, [load])

  return (
    <BetterCrmLayout title="Contacts" actions={<Btn variant="primary" sm onClick={() => setShowNew(true)}>New contact</Btn>}>
      <TextInput placeholder="Search by name or email…" value={q} onChange={e => setQ(e.target.value)} className="max-w-sm mb-4 block" />
      {loading ? <PbSpinner message="Loading contacts…" /> : (
        <div className="space-y-2">
          {people.length === 0 && <p className="text-pb-faintest text-sm">No contacts yet.</p>}
          {people.map(p => (
            <div key={p.id} className="pb-card px-4 py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium truncate">{p.full_name}</div>
                <div className="text-[12px] text-pb-faint truncate">{[p.email, p.phone].filter(Boolean).join(' · ') || '—'}</div>
              </div>
              <div className="flex flex-wrap gap-1 justify-end shrink-0 max-w-[45%]">
                {(p.roles || []).map(r => <Pill key={r.id}>{roleLabel(r.role)}</Pill>)}
              </div>
            </div>
          ))}
        </div>
      )}
      <NewPersonModal open={showNew} onClose={() => setShowNew(false)} onCreated={load} />
    </BetterCrmLayout>
  )
}
