// BetterStats > Player Dashboard > Your own modules: cards the club writes itself for the
// player's dashboard, like a link page. A link button (tickets, the merch store, a form), an
// announcement, an event with a countdown, or an image banner. Each becomes its own card on the
// dashboard grid; their place is set in Card order below. Every call answers with the whole
// settings payload, which the page keeps (`onCfg`).
import { useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Btn } from '../betterselect/ui'

const KIND_HELP = {
  link: 'A button that opens a web page: event tickets, the merch store, a registration form.',
  text: 'A notice with a title and some text, and a button if you add a link.',
  event: 'An event with its date and a countdown. It drops off the day after, unless you set Show until.',
  image: 'A picture, such as an event poster or a merch photo, that can open a link when tapped.',
}

const EMPTY = { kind: 'link', title: '', body: '', url: '', button_label: '', emoji: '', location: '', event_date: '', event_time: '', show_from: '', show_until: '', enabled: true }

function fromModule(m) {
  const f = { ...EMPTY }
  for (const k of Object.keys(EMPTY)) if (m[k] !== undefined && m[k] !== null) f[k] = m[k]
  return f
}

// What to send: every field, blanks as null so a cleared field is cleared.
function toBody(f) {
  const out = {}
  for (const [k, v] of Object.entries(f)) out[k] = typeof v === 'string' ? (v.trim() === '' ? null : v) : v
  return out
}

function Field({ label, hint, children }) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-pb-faintest">{hint}</span>}
    </div>
  )
}

const inputCls = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest focus:outline-none focus:border-pb-accent'

function ModuleForm({ initial, kinds, busy, onSave, onCancel, existing, onImage, onRemoveImage }) {
  const [f, setF] = useState(initial)
  const fileRef = useRef(null)
  const set = (k) => (e) => setF((c) => ({ ...c, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const k = f.kind
  return (
    <form data-custom-form className="rounded-xl border pb-hairline p-3 flex flex-col gap-3"
      onSubmit={(e) => { e.preventDefault(); onSave(toBody(f)) }}>
      <Field label="Kind">
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Kind">
          {kinds.map((o) => (
            <button key={o.key} type="button" role="radio" aria-checked={k === o.key} data-kind-option={o.key}
              onClick={() => setF((c) => ({ ...c, kind: o.key }))}
              className={`px-3 py-1.5 rounded-lg text-[13px] border pb-hairline ${k === o.key ? 'font-semibold' : 'text-pb-dim'}`}
              style={k === o.key ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent)', borderColor: 'transparent' } : undefined}>
              {o.label}
            </button>
          ))}
        </div>
        <span className="text-[11.5px] text-pb-faint">{KIND_HELP[k]}</span>
      </Field>
      <div className="grid gap-3 sm:grid-cols-[1fr_90px]">
        <Field label="Title" hint={k === 'image' ? 'Also read out to people using a screen reader.' : null}>
          <input className={inputCls} value={f.title} onChange={set('title')} maxLength={80} required data-field="title"
            placeholder={k === 'event' ? 'Presentation night' : k === 'link' ? 'Buy club merch' : 'Title'} />
        </Field>
        {k !== 'image' && (
          <Field label="Icon">
            <input className={inputCls} value={f.emoji} onChange={set('emoji')} maxLength={8} placeholder="🎟️" data-field="emoji" />
          </Field>
        )}
      </div>
      {k === 'event' && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Date"><input type="date" className={inputCls} value={f.event_date} onChange={set('event_date')} required data-field="event_date" /></Field>
          <Field label="Start time"><input type="time" className={inputCls} value={f.event_time} onChange={set('event_time')} data-field="event_time" /></Field>
          <Field label="Where"><input className={inputCls} value={f.location} onChange={set('location')} maxLength={120} placeholder="Clubrooms" data-field="location" /></Field>
        </div>
      )}
      <Field label={k === 'text' ? 'Text' : 'Text (optional)'}>
        <textarea className={`${inputCls} min-h-[70px]`} value={f.body} onChange={set('body')} maxLength={1000} required={k === 'text'} data-field="body" />
      </Field>
      <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
        <Field label={k === 'link' ? 'Link' : 'Link (optional)'} hint="A web address, for example https://tickets.yourclub.com.au">
          <input className={inputCls} value={f.url} onChange={set('url')} inputMode="url" required={k === 'link'} placeholder="https://" data-field="url" />
        </Field>
        {k !== 'image' && (
          <Field label="Button text">
            <input className={inputCls} value={f.button_label} onChange={set('button_label')} maxLength={30}
              placeholder={k === 'event' ? 'Get tickets' : k === 'text' ? 'Find out more' : 'Open'} data-field="button_label" />
          </Field>
        )}
      </div>
      {k === 'image' && (
        <Field label="Image" hint="JPG, PNG, WebP or GIF, 5 MB at most. A wide picture works best.">
          {existing?.image_url && <img src={existing.image_url} alt="" className="w-full max-w-xs rounded-lg mb-1.5" />}
          {existing ? (
            <div className="flex flex-wrap gap-2">
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" data-field="image"
                onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ''; if (file) onImage(file) }} />
              <Btn sm disabled={busy} onClick={() => fileRef.current?.click()}>{existing.image_url ? 'Replace image' : 'Upload image'}</Btn>
              {existing.image_url && <Btn sm variant="ghost" disabled={busy} onClick={onRemoveImage}>Remove image</Btn>}
            </div>
          ) : <span className="text-[12px] text-pb-faint">Save first, then upload the image.</span>}
        </Field>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Show from" hint="Blank shows it straight away."><input type="date" className={inputCls} value={f.show_from} onChange={set('show_from')} data-field="show_from" /></Field>
        <Field label="Show until" hint={k === 'event' ? 'Blank takes it down after the event.' : 'Blank keeps it up until you remove it.'}>
          <input type="date" className={inputCls} value={f.show_until} onChange={set('show_until')} data-field="show_until" />
        </Field>
      </div>
      <div className="flex items-center gap-2">
        <input id="custom-enabled" type="checkbox" checked={!!f.enabled} onChange={set('enabled')} data-field="enabled" />
        <label htmlFor="custom-enabled" className="text-[13px]">Show it to players</label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Btn sm variant="primary" type="submit" disabled={busy}>{existing ? 'Save' : 'Add module'}</Btn>
        <Btn sm onClick={onCancel} disabled={busy}>Cancel</Btn>
      </div>
    </form>
  )
}

function Row({ m, busy, onEdit, onToggle, onDelete }) {
  return (
    <div data-custom-row={m.id} className="flex items-start gap-3 py-2.5 border-t pb-hairline first:border-t-0">
      <span aria-hidden="true" className="w-8 text-center text-[20px] leading-none pt-0.5 shrink-0">
        {m.kind === 'image' && m.image_url ? <img src={m.image_url} alt="" className="w-8 h-8 object-cover rounded" /> : (m.emoji || '🔗')}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold break-words">{m.title}</div>
        <div className="text-[12px] text-pb-faint">
          {m.kind_label}
          {m.url ? ` · ${m.click_count} ${m.click_count === 1 ? 'tap' : 'taps'}` : ''}
        </div>
        {m.hidden_reason && (
          <div className="text-[12px] mt-0.5" style={{ color: 'var(--pb-amber)' }} data-custom-hidden>Not showing. {m.hidden_reason}</div>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1">
        <Btn sm disabled={busy} onClick={onToggle}>{m.enabled ? 'Hide' : 'Show'}</Btn>
        <Btn sm disabled={busy} onClick={onEdit}>Edit</Btn>
        <Btn sm variant="ghost" disabled={busy} onClick={onDelete} aria-label={`Remove ${m.title}`}>Remove</Btn>
      </div>
    </div>
  )
}

export default function CustomModulesPanel({ cfg, onCfg }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null) // null | 'new' | module id
  const mods = cfg.custom_modules || []
  const kinds = cfg.custom_kinds || []

  const run = async (fn, ok) => {
    setBusy(true)
    try {
      const next = await fn()
      onCfg(next)
      if (ok) toast.success(ok)
      return next
    } catch (e) {
      toast.error(e.message || 'That did not save')
      return null
    } finally { setBusy(false) }
  }

  const save = async (body) => {
    if (editing === 'new') {
      const next = await run(() => api.createPlayerDashboardCustomModule(body), 'Module added')
      // An image banner stays open so the image can go on straight away.
      if (next) setEditing(body.kind === 'image' && next.created_id ? next.created_id : null)
    } else {
      const next = await run(() => api.updatePlayerDashboardCustomModule(editing, body), 'Saved')
      if (next) setEditing(null)
    }
  }

  const current = editing && editing !== 'new' ? mods.find((m) => m.id === editing) : null

  return (
    <div data-custom-modules className="pt-4 border-t pb-hairline">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Your own modules</div>
      <p className="text-[12px] text-pb-faintest mb-2">
        Add your own cards to the dashboard: a button to event tickets or the merch store, a notice, an event with a countdown, or a poster. Each one is its own card, and you can move it in Card order. Taps on a link are counted here; nobody's name is kept.
      </p>
      {mods.length === 0 && editing !== 'new' && <div className="text-[13px] text-pb-faint mb-2" data-custom-empty>No modules of your own yet.</div>}
      {mods.map((m) => (editing === m.id ? (
        <div key={m.id} className="py-2">
          <ModuleForm initial={fromModule(m)} kinds={kinds} busy={busy} existing={current} onCancel={() => setEditing(null)} onSave={save}
            onImage={(file) => run(() => api.uploadPlayerDashboardCustomModuleImage(m.id, file), 'Image uploaded')}
            onRemoveImage={() => run(() => api.deletePlayerDashboardCustomModuleImage(m.id), 'Image removed')} />
        </div>
      ) : (
        <Row key={m.id} m={m} busy={busy} onEdit={() => setEditing(m.id)}
          onToggle={() => run(() => api.updatePlayerDashboardCustomModule(m.id, { enabled: !m.enabled }))}
          onDelete={() => {
            if (!window.confirm(`Remove "${m.title}" from the Player Dashboard? Its tap count goes with it.`)) return
            run(() => api.deletePlayerDashboardCustomModule(m.id), 'Removed')
            if (editing === m.id) setEditing(null)
          }} />
      )))}
      {editing === 'new' ? (
        <div className="pt-2"><ModuleForm initial={{ ...EMPTY }} kinds={kinds} busy={busy} onCancel={() => setEditing(null)} onSave={save} /></div>
      ) : (
        <div className="pt-2"><Btn sm variant="primary" disabled={busy || !!editing} onClick={() => setEditing('new')} data-add-custom>Add a module</Btn></div>
      )}
    </div>
  )
}
