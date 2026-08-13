import { useState } from 'react'
import { ROLE_OPTS, BAT_HANDS, BOWLING_OPTS, bowlingLabel, bowlingFromLabel, REGION_OPTS, LEVEL_OPTS } from '../lib/watchlistOptions'

const RECRUITING_FIELDS = [
  ['transfer_preference', 'Transfer preference', 'e.g. North of England preferred'],
  ['visa_status', 'Visa / eligibility', 'e.g. Has ancestry visa'],
  ['agent_contact', 'Agent / representative contact', 'e.g. agent@example.com'],
  ['availability_window', 'Availability', 'e.g. Available from October 2026'],
  ['fee_expectations', 'Fee expectations', 'e.g. £400/week + accommodation'],
]

export default function ScoutCardEditor({ card, onClose, onSave, onRemove, onShare, onUnshare }) {
  const [form, setForm] = useState({
    tags: card.tags || [],
    role: card.role || '',
    batting_hand: card.batting_hand || '',
    bowling_label: bowlingLabel(card.bowling_action, card.bowling_type),
    region: card.region || '',
    level: card.level || '',
    notes: card.notes || '',
    ...Object.fromEntries(RECRUITING_FIELDS.map(([key]) => [key, card[key] || ''])),
  })
  const [tagInput, setTagInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [shareToken, setShareToken] = useState(card.share_token || null)
  const [shareBusy, setShareBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const shareUrl = shareToken ? `${window.location.origin}/betterscout/share/${shareToken}` : null

  const doShare = async () => {
    setShareBusy(true)
    setError(null)
    try {
      const res = await onShare()
      setShareToken(res.share_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setShareBusy(false)
    }
  }

  const doUnshare = async () => {
    setShareBusy(true)
    setError(null)
    try {
      await onUnshare()
      setShareToken(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setShareBusy(false)
    }
  }

  const copyLink = () => {
    navigator.clipboard?.writeText(shareUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const addTag = (e) => {
    e.preventDefault()
    const t = tagInput.trim()
    if (t && !form.tags.includes(t)) setForm((f) => ({ ...f, tags: [...f.tags, t] }))
    setTagInput('')
  }
  const removeTag = (t) => setForm((f) => ({ ...f, tags: f.tags.filter((x) => x !== t) }))

  const save = async () => {
    setSaving(true)
    setError(null)
    const { bowling_action, bowling_type } = bowlingFromLabel(form.bowling_label)
    const { bowling_label, ...rest } = form
    try {
      await onSave({ ...rest, bowling_action, bowling_type })
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="pb-card w-full max-w-lg max-h-[85vh] overflow-y-auto p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-lg">{card.player.name}</h2>
          <button onClick={onClose} className="text-pb-dim hover:text-pb-text">✕</button>
        </div>

        {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}

        <div className="rounded border border-pb-hairline p-3 space-y-2">
          <div className="text-xs text-pb-dim uppercase font-mono">Share</div>
          {!shareToken && (
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-pb-dim">
                Create a read-only link with this player's stats, tags and notes — never the recruiting fields below.
              </p>
              <button onClick={doShare} disabled={shareBusy}
                      className="shrink-0 text-sm px-3 py-1.5 rounded border border-pb-hairline hover:bg-pb-surface2 disabled:opacity-50">
                {shareBusy ? 'Creating…' : 'Create share link'}
              </button>
            </div>
          )}
          {shareToken && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <input readOnly value={shareUrl}
                       className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs font-mono" />
                <button onClick={copyLink} className="shrink-0 text-xs px-2 py-1.5 rounded border border-pb-hairline hover:bg-pb-surface2">
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="flex gap-3 text-xs">
                <button onClick={doShare} disabled={shareBusy} className="text-pb-dim hover:text-pb-text disabled:opacity-50">
                  Regenerate
                </button>
                <button onClick={doUnshare} disabled={shareBusy} className="text-[var(--pb-negative)] hover:underline disabled:opacity-50">
                  Turn off sharing
                </button>
              </div>
            </div>
          )}
        </div>

        <div>
          <label className="block text-xs text-pb-dim uppercase font-mono mb-1">Tags</label>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {form.tags.map((t) => (
              <span key={t} className="text-xs px-2 py-1 rounded-full bg-pb-surface2 flex items-center gap-1">
                {t}
                <button onClick={() => removeTag(t)} className="text-pb-dim hover:text-pb-text">✕</button>
              </span>
            ))}
          </div>
          <form onSubmit={addTag} className="flex gap-2">
            <input value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="Add a tag…"
                   className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm" />
            <button type="submit" className="text-sm px-3 py-1 rounded border border-pb-hairline hover:bg-pb-surface2">Add</button>
          </form>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <select value={form.role} onChange={set('role')} className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              {ROLE_OPTS.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
            </select>
          </Field>
          <Field label="Batting hand">
            <select value={form.batting_hand} onChange={set('batting_hand')} className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              {BAT_HANDS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
          </Field>
          <Field label="Bowling">
            <select value={form.bowling_label} onChange={set('bowling_label')} className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              {BOWLING_OPTS.map(([label]) => <option key={label} value={label}>{label}</option>)}
            </select>
          </Field>
          <Field label="Region">
            <select value={form.region} onChange={set('region')} className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              {REGION_OPTS.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
            </select>
          </Field>
          <Field label="Level">
            <select value={form.level} onChange={set('level')} className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              {LEVEL_OPTS.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
            </select>
          </Field>
        </div>

        <div className="space-y-3">
          {RECRUITING_FIELDS.map(([key, label, placeholder]) => (
            <Field key={key} label={label}>
              <input value={form[key]} onChange={set(key)} placeholder={placeholder}
                     className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
            </Field>
          ))}
          <Field label="Notes">
            <textarea value={form.notes} onChange={set('notes')} rows={3}
                      className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          </Field>
        </div>

        <div className="flex items-center justify-between pt-2">
          <button onClick={onRemove} className="text-sm text-[var(--pb-negative)] hover:underline">
            Remove from this board
          </button>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 rounded border border-pb-hairline text-sm hover:bg-pb-surface2">Cancel</button>
            <button onClick={save} disabled={saving}
                    className="px-3 py-1.5 rounded bg-[var(--pb-accent)] text-black text-sm font-semibold disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs text-pb-dim uppercase font-mono mb-1">{label}</span>
      {children}
    </label>
  )
}
