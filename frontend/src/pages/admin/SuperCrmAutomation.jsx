import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import { Modal, Field, TextInput, NumberInput, Select, Btn, Pill } from '../../components/admin/crm/ui'

// Configurable, persistent criteria for the platform pipeline's automatic
// deal creation/stage-promotion (backend: services/crm_rules.py). Every
// trigger here is a genuine integration point in the code (an enquiry
// lands, a score is recomputed, a trial starts…) — what's editable is the
// numeric condition, the target stage, whether it forces the move, and
// whether it's enabled at all.

function RuleFormModal({ open, onClose, trigger, stages, existing, onSaved }) {
  const toast = useToast()
  const [label, setLabel] = useState('')
  const [paramValue, setParamValue] = useState('')
  const [targetStageKey, setTargetStageKey] = useState('')
  const [force, setForce] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setLabel(existing?.label || '')
    setParamValue(trigger?.param_key && existing?.params ? (existing.params[trigger.param_key] ?? '') : '')
    setTargetStageKey(existing?.target_stage_key || stages?.[0]?.key || '')
    setForce(existing?.force || false)
    setEnabled(existing?.enabled ?? true)
  }, [open, existing, trigger, stages])

  if (!open || !trigger) return null

  const submit = async (e) => {
    e.preventDefault()
    if (!label.trim()) { toast.error('Give this rule a label'); return }
    if (!targetStageKey) { toast.error('Choose a target stage'); return }
    const params = trigger.param_key
      ? { [trigger.param_key]: Number(paramValue) }
      : {}
    if (trigger.param_key && (paramValue === '' || Number.isNaN(Number(paramValue)))) {
      toast.error(`${trigger.param_label} needs a number`)
      return
    }
    setSaving(true)
    try {
      if (existing) {
        await api.superCrmUpdateAutomation(existing.id, {
          label, target_stage_key: targetStageKey, params, force, enabled,
        })
      } else {
        await api.superCrmCreateAutomation({
          trigger: trigger.key, label, target_stage_key: targetStageKey, params, force, enabled,
        })
      }
      onSaved()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not save rule') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title={`${existing ? 'Edit' : 'Add'} rule — ${trigger.label}`}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Label" hint="Shown on the rule row — describe what this specific rule is for.">
          <TextInput value={label} onChange={e => setLabel(e.target.value)} placeholder={trigger.label} />
        </Field>
        {trigger.param_key && (
          <Field label={trigger.param_label}>
            <NumberInput value={paramValue} onChange={e => setParamValue(e.target.value)}
              min={trigger.param_key === 'count' ? 1 : undefined} />
          </Field>
        )}
        <Field label="Promotes to stage" hint="The platform pipeline stage this rule creates/advances the deal to.">
          <Select value={targetStageKey} onChange={e => setTargetStageKey(e.target.value)}>
            {(stages || []).map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-[12.5px] text-pb-faint">
          <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
          Force the move (bypass the normal "never move a deal backward" rule)
        </label>
        <label className="flex items-center gap-2 text-[12.5px] text-pb-faint">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          Enabled
        </label>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Save rule</Btn></div>
      </form>
    </Modal>
  )
}

function TriggerSection({ trigger, rules, stages, onEdit, onAdd, onDelete }) {
  const stageName = (key) => stages.find(s => s.key === key)?.name || key
  return (
    <div className="pb-card px-4 py-3">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h3 className="font-display font-bold text-[13.5px]">{trigger.label}</h3>
          <p className="text-[11.5px] text-pb-faint mt-0.5 max-w-2xl">{trigger.description}</p>
        </div>
        <Btn variant="ghost" sm onClick={onAdd}>+ Add rule</Btn>
      </div>
      {rules.length === 0 ? (
        <p className="text-[12px] text-pb-faintest italic">No rules configured — this automation never fires.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-pb-faint border-b border-pb-hairline">
                <th className="py-1.5 pr-3 font-normal">Label</th>
                {trigger.param_key && <th className="py-1.5 pr-3 font-normal">{trigger.param_label}</th>}
                <th className="py-1.5 pr-3 font-normal">Promotes to</th>
                <th className="py-1.5 pr-3 font-normal">Force</th>
                <th className="py-1.5 pr-3 font-normal">Status</th>
                <th className="py-1.5 pr-3 font-normal" />
              </tr>
            </thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.id} className="border-b border-pb-hairline last:border-0">
                  <td className="py-1.5 pr-3">{r.label}</td>
                  {trigger.param_key && <td className="py-1.5 pr-3">{r.params?.[trigger.param_key] ?? '—'}</td>}
                  <td className="py-1.5 pr-3">{stageName(r.target_stage_key)}</td>
                  <td className="py-1.5 pr-3">{r.force ? <Pill tone="amber">force</Pill> : '—'}</td>
                  <td className="py-1.5 pr-3">
                    {r.enabled ? <Pill tone="green">enabled</Pill> : <Pill>disabled</Pill>}
                  </td>
                  <td className="py-1.5 pr-3 text-right whitespace-nowrap">
                    <button onClick={() => onEdit(r)} className="text-pb-faint hover:text-pb-accent text-[11px] mr-3">Edit</button>
                    <button onClick={() => onDelete(r)} className="text-pb-faint hover:text-pb-red text-[11px]">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function SuperCrmAutomation() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null) // { trigger, existing }

  const load = useCallback(() => {
    setLoading(true)
    api.superCrmListAutomation()
      .then(setData)
      .catch(e => toast.error(e.message || 'Could not load automation rules'))
      .finally(() => setLoading(false))
  }, [toast])
  useEffect(() => { load() }, [load])

  const deleteRule = async (rule) => {
    if (!window.confirm(`Delete "${rule.label}"? This can't be undone.`)) return
    try { await api.superCrmDeleteAutomation(rule.id); load() }
    catch (e) { toast.error(e.message || 'Could not delete rule') }
  }

  return (
    <AdminLayout>
      <div className="mb-4">
        <h1 className="font-display font-bold text-xl">BetterCRM — Sales Automation</h1>
        <p className="text-[12.5px] text-pb-faint mt-1 max-w-3xl">
          Every criterion that automatically creates or advances a platform-pipeline deal —
          a Contact-Us enquiry count, an engagement score threshold, a trial or subscription
          event — is configured here, not hardcoded. Disabling every rule for a trigger turns
          that automation off entirely; nothing is ever deleted just by being switched off.
        </p>
      </div>

      {loading || !data ? <PbSpinner message="Loading automation rules…" /> : (
        <div className="space-y-3">
          {data.triggers.map(trigger => (
            <TriggerSection
              key={trigger.key}
              trigger={trigger}
              stages={data.stages}
              rules={data.rules.filter(r => r.trigger === trigger.key)}
              onAdd={() => setModal({ trigger, existing: null })}
              onEdit={(rule) => setModal({ trigger, existing: rule })}
              onDelete={deleteRule}
            />
          ))}
        </div>
      )}

      <RuleFormModal
        open={!!modal}
        onClose={() => setModal(null)}
        trigger={modal?.trigger}
        stages={data?.stages}
        existing={modal?.existing}
        onSaved={load}
      />
    </AdminLayout>
  )
}
