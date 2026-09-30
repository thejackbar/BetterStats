// Saved-template pieces for the BetterPosts editor: the dialog that names (or
// updates) a template on the way to saving it, the header menu that opens any
// saved template in one click, and the label that says whether they have
// reached the club's server.
//
// The state and the network calls live in AdminSocialPost; these only draw.
import { useEffect, useRef, useState } from 'react'

export function timeAgo(iso) {
  const t = iso ? new Date(iso).getTime() : NaN
  if (!Number.isFinite(t)) return ''
  const mins = Math.round((Date.now() - t) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} hr ago`
  const days = Math.round(hrs / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

const SYNC_TEXT = {
  ok: 'Saved to your club. Any admin with BetterPosts access sees these.',
  offline: "Couldn't reach the server, so this is only the copy on this browser. It will sync next time it can.",
  partial: 'Some changes have not reached the server yet. They will retry next time you open BetterPosts.',
}

// One line under a template list. Draws nothing while the first load is running
// so a working setup never flashes a warning.
export function TemplateSyncNote({ state }) {
  const text = SYNC_TEXT[state?.state]
  if (!text) return null
  const bad = state.state !== 'ok'
  return (
    <div data-testid="template-sync" data-state={state.state}
      className={`text-[10px] leading-snug ${bad ? 'text-pb-red' : 'text-pb-faint'}`}>
      {text}{bad && state.message ? ` (${state.message})` : ''}
    </div>
  )
}

// Naming a template, and choosing whether this is a new one or an update of the
// one that is open. Without the second choice every re-save became another
// copy, and the only way to keep improved work was to keep piling up duplicates.
export function SaveTemplateDialog({ open, defaultName, activeName, saving, error, onSave, onClose }) {
  const [name, setName] = useState(defaultName || '')
  const input = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    setName(activeName || defaultName || '')
    const id = setTimeout(() => input.current?.select(), 30)
    return () => clearTimeout(id)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape' && !saving) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, saving, onClose])
  if (!open) return null

  const submit = (asNew) => { if (!saving) onSave({ name, asNew }) }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4" style={{ background: 'rgba(0,0,0,0.55)' }}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !saving) onClose() }}>
      <div role="dialog" aria-label="Save as template" data-testid="save-template-dialog"
        className="w-full max-w-[420px] pb-card p-5 flex flex-col gap-3 bg-pb-surface border pb-hairline rounded-xl">
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Save as template</h2>
        <p className="text-[12px] text-pb-dim leading-relaxed">
          Keeps this layout, your colours, font and background, any blocks you have added and, for an event poster, its wording and photo. It is saved to your club, so anyone who edits your posts can use it.
        </p>
        {activeName && (
          <p data-testid="save-template-hint" className="text-[11px] text-pb-faint leading-relaxed">
            You started from <span className="text-pb-text">“{activeName}”</span>. <span className="text-pb-text">Save as new</span> leaves it exactly as it is. <span className="text-pb-text">Update</span> replaces it with what is on screen now.
          </p>
        )}
        <input ref={input} value={name} onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(true) }}
          placeholder="Template name" maxLength={80} data-testid="save-template-name"
          className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-[13px] text-pb-text" />
        {error && <div data-testid="save-template-error" className="text-pb-red text-[11px] leading-snug">{error}</div>}
        <div className="flex flex-wrap gap-2 justify-end pt-1">
          <button onClick={onClose} disabled={saving}
            className="px-3 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text disabled:opacity-50">CANCEL</button>
          {activeName && (
            <button onClick={() => submit(false)} disabled={saving} data-testid="save-template-update"
              className="px-3 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-dim hover:text-pb-text hover:border-pb-accent disabled:opacity-50">
              UPDATE “{activeName.length > 18 ? `${activeName.slice(0, 17)}…` : activeName}”
            </button>
          )}
          <button onClick={() => submit(true)} disabled={saving} data-testid="save-template-new"
            className="px-3.5 h-8 rounded-md font-mono text-[10px] tracking-wide2 disabled:opacity-60"
            style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
            {saving ? 'SAVING…' : activeName ? 'SAVE AS NEW' : 'SAVE TEMPLATE'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Every saved template one click away from the editor's header.
export function TemplatesMenu({ templates, activeKey, layoutLabel, syncState, onApply, onDelete }) {
  const [open, setOpen] = useState(false)
  const wrap = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div ref={wrap} className="relative">
      <button onClick={() => setOpen((o) => !o)} data-testid="templates-menu-button" aria-expanded={open}
        title="Open one of your saved templates"
        className="px-3 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-dim hover:text-pb-text hover:border-pb-accent transition-colors">
        MY TEMPLATES ({templates.length})
      </button>
      {open && (
        <div data-testid="templates-menu"
          className="absolute right-0 top-[38px] z-40 w-[300px] max-h-[380px] overflow-y-auto rounded-lg border pb-hairline bg-pb-surface p-1.5 shadow-xl">
          {templates.length === 0 && (
            <div className="px-2.5 py-3 text-[11px] text-pb-faint leading-relaxed">
              Nothing saved yet. Build a post, then press <span className="text-pb-text">Save as template</span>.
            </div>
          )}
          {templates.map((t) => (
            <div key={t.key} data-testid="template-row"
              className={`group flex items-center gap-1 rounded-md ${activeKey === t.key ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'}`}>
              <button onClick={() => { onApply(t); setOpen(false) }} className="flex-1 min-w-0 text-left px-2.5 py-2">
                <div className="text-[12px] text-pb-text truncate">
                  {activeKey === t.key && <span style={{ color: 'var(--pb-accent)' }}>● </span>}{t.name}
                </div>
                <div className="font-mono text-[9px] text-pb-faint truncate">
                  {[layoutLabel(t), t.unsynced ? 'not synced yet' : timeAgo(t.updated_at)].filter(Boolean).join(' · ')}
                </div>
              </button>
              <button onClick={() => onDelete(t.key)} title="Delete template" aria-label={`Delete ${t.name}`}
                className="w-7 h-7 shrink-0 grid place-items-center text-pb-faint hover:text-pb-red text-xs">✕</button>
            </div>
          ))}
          {syncState?.state && syncState.state !== 'ok' && syncState.state !== 'loading' && (
            <div className="px-2.5 py-2 border-t pb-hairline mt-1"><TemplateSyncNote state={syncState} /></div>
          )}
        </div>
      )}
    </div>
  )
}
