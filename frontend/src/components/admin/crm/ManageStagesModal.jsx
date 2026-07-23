import { useState } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Modal, TextInput, NumberInput, Btn, Pill } from './ui'

// Add/rename/reorder/delete a tracker's own stages — works for any club
// tracker (preset or custom); the platform sales pipeline doesn't expose
// this (its stages are BetterCricket's own, not club-editable).
export default function ManageStagesModal({ open, onClose, pipelineId, stages, onChanged }) {
  const toast = useToast()
  const [newName, setNewName] = useState('')
  const [saving, setSaving] = useState(false)

  if (!open) return null
  const sorted = [...(stages || [])].sort((a, b) => a.position - b.position)

  const addStage = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    setSaving(true)
    try {
      await api.crmAddStage(pipelineId, { name: newName.trim() })
      setNewName('')
      onChanged()
    } catch (e2) { toast.error(e2.message || 'Could not add stage') } finally { setSaving(false) }
  }

  const rename = async (stage, name) => {
    if (!name.trim() || name === stage.name) return
    try { await api.crmUpdateStage(stage.id, { name: name.trim() }); onChanged() }
    catch (e) { toast.error(e.message || 'Could not rename stage') }
  }

  const setProbability = async (stage, value) => {
    try { await api.crmUpdateStage(stage.id, { default_probability: value }); onChanged() }
    catch (e) { toast.error(e.message || 'Could not update probability') }
  }

  const toggleFlag = async (stage, flag) => {
    try { await api.crmUpdateStage(stage.id, { [flag]: !stage[flag] }); onChanged() }
    catch (e) { toast.error(e.message || 'Could not update stage') }
  }

  const move = async (stage, dir) => {
    const idx = sorted.findIndex(s => s.id === stage.id)
    const swapIdx = idx + dir
    if (swapIdx < 0 || swapIdx >= sorted.length) return
    const other = sorted[swapIdx]
    try {
      await Promise.all([
        api.crmUpdateStage(stage.id, { position: other.position }),
        api.crmUpdateStage(other.id, { position: stage.position }),
      ])
      onChanged()
    } catch (e) { toast.error(e.message || 'Could not reorder') }
  }

  const remove = async (stage) => {
    if (!window.confirm(`Delete the "${stage.name}" stage?`)) return
    try { await api.crmDeleteStage(stage.id); onChanged() }
    catch (e) { toast.error(e.message || 'Could not delete stage — move its records out first') }
  }

  return (
    <Modal open={open} onClose={onClose} title="Manage stages" wide>
      <div className="space-y-2 mb-4">
        {sorted.map((s, i) => (
          <div key={s.id} className="pb-card px-3 py-2.5 flex items-center gap-2">
            <div className="flex flex-col gap-0.5 shrink-0">
              <button disabled={i === 0} onClick={() => move(s, -1)}
                className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▲</button>
              <button disabled={i === sorted.length - 1} onClick={() => move(s, 1)}
                className="text-pb-faint hover:text-pb-text disabled:opacity-20 text-[10px] leading-none">▼</button>
            </div>
            <TextInput defaultValue={s.name} onBlur={e => rename(s, e.target.value)} className="flex-1 min-w-0" />
            <div className="flex items-center gap-1 shrink-0">
              <NumberInput defaultValue={s.default_probability} min={0} max={100}
                onBlur={e => setProbability(s, Number(e.target.value))} className="w-16" />
              <span className="text-[11px] text-pb-faint">%</span>
            </div>
            <button onClick={() => toggleFlag(s, 'is_won')} className="shrink-0">
              <Pill tone={s.is_won ? 'green' : 'faint'}>Won</Pill>
            </button>
            <button onClick={() => toggleFlag(s, 'is_lost')} className="shrink-0">
              <Pill tone={s.is_lost ? 'red' : 'faint'}>Lost</Pill>
            </button>
            <button onClick={() => remove(s)} className="text-pb-faintest hover:text-pb-red text-[11px] shrink-0">Delete</button>
          </div>
        ))}
      </div>
      <form onSubmit={addStage} className="flex gap-2">
        <TextInput placeholder="New stage name" value={newName} onChange={e => setNewName(e.target.value)} className="flex-1" />
        <Btn type="submit" variant="ghost" sm disabled={saving}>Add stage</Btn>
      </form>
    </Modal>
  )
}
