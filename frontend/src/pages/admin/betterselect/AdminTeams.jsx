import { useState, useEffect, useCallback } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Btn, Field, Input } from '../../../lib/presskit'

const EMPTY = { name: '', short_name: '', sequence: 0, default_formation: '', is_active: true }

function TeamModal({ team, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({ ...EMPTY, ...(team || {}) }))
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const save = async () => {
    if (!form.name.trim()) { toast.error('Team name is required'); return }
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(),
        short_name: form.short_name || null,
        sequence: Number(form.sequence) || 0,
        default_formation: form.default_formation || null,
        is_active: !!form.is_active,
      }
      const saved = team ? await api.bsUpdateTeam(team.id, payload) : await api.bsCreateTeam(payload)
      toast.success(team ? 'Team updated' : 'Team added')
      onSaved(saved)
    } catch (e) { toast.error('Save failed: ' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4" style={{ backdropFilter: 'blur(2px)' }}>
      <div className="bg-pb-surface pb-card max-w-md w-full mt-16 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline">
          <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">{team ? 'Edit team' : 'New team'}</h3>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text">✕</button>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Name"><Input value={form.name} onChange={set('name')} placeholder="e.g. 1st XI" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Short name"><Input value={form.short_name || ''} onChange={set('short_name')} placeholder="e.g. 1s" /></Field>
            <Field label="Order (1 = top)"><Input type="number" value={form.sequence} onChange={set('sequence')} /></Field>
          </div>
          <Field label="Default formation (optional)"><Input value={form.default_formation || ''} onChange={set('default_formation')} placeholder="e.g. Traditional" /></Field>
          <label className="flex items-center gap-2 text-sm text-pb-faint">
            <input type="checkbox" checked={!!form.is_active} onChange={(e) => setForm(f => ({ ...f, is_active: e.target.checked }))} />
            Active
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t pb-hairline">
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn primary onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>
        </div>
      </div>
    </div>
  )
}

export default function AdminTeams() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canManage = hasCapability(CAP.MANAGE_SELECTIONS)
  const [teams, setTeams] = useState(null)
  const [editing, setEditing] = useState(undefined)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    setTeams(null)
    api.bsListTeams(true).then(setTeams).catch(e => { toast.error(e.message); setTeams([]) })
  }, [toast])

  useEffect(() => { load() }, [load])

  const seed = async () => {
    setSeeding(true)
    try { const r = await api.bsSeedTeams(); toast.success(`Created ${r.created} team(s) from match data`); load() }
    catch (e) { toast.error('Seed failed: ' + e.message) }
    finally { setSeeding(false) }
  }

  const del = async (t) => {
    if (!window.confirm(`Delete team "${t.name}"?`)) return
    try { await api.bsDeleteTeam(t.id); toast.success('Deleted'); load() }
    catch (e) { toast.error('Delete failed: ' + e.message) }
  }

  const actions = canManage && (
    <div className="flex gap-2">
      <Btn onClick={seed} disabled={seeding}>{seeding ? 'Seeding…' : '⤓ Auto-seed'}</Btn>
      <Btn primary onClick={() => setEditing(null)}>+ Add team</Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Teams" actions={actions}>
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">
        Your club’s teams. Auto-seed pulls distinct team names from your match history, or add teams by hand.
        Order sets the hierarchy (1 = top team).
      </p>

      {teams === null ? <PbSpinner message="Loading teams…" /> : (
        <div className="pb-card overflow-hidden">
          {teams.length === 0 && (
            <div className="px-5 py-10 text-center text-pb-faint text-sm">
              No teams yet. {canManage && 'Auto-seed from your data or add one.'}
            </div>
          )}
          {teams.map((t, i) => (
            <div key={t.id} className={`px-5 py-3 flex items-center justify-between gap-3 ${i > 0 ? 'border-t pb-hairline' : ''}`}>
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-mono text-[11px] text-pb-faintest w-6 text-right">{t.sequence || '—'}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm truncate">{t.name}</span>
                    {!t.is_active && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-faintest">inactive</span>}
                    <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded ${t.source === 'auto' ? 'bg-pb-surface2 text-pb-faint' : 'bg-pb-accent/15 text-pb-accent'}`}>
                      {t.source === 'auto' ? 'auto' : 'manual'}
                    </span>
                  </div>
                  {t.default_formation && <div className="text-pb-faint text-xs mt-0.5">{t.default_formation}</div>}
                </div>
              </div>
              {canManage && (
                <div className="flex gap-2 shrink-0">
                  <Btn sm onClick={() => setEditing(t)}>Edit</Btn>
                  <Btn sm danger onClick={() => del(t)}>Delete</Btn>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {editing !== undefined && (
        <TeamModal team={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load() }} />
      )}
    </BetterSelectLayout>
  )
}
