import { useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { Field, TextInput, TextArea, Select, Btn } from './ui'

// Shared vocab — mirrors services/crm.py EVENT_TYPES / ALERT_CODES and
// models/db.py::CrmEvent so the two never drift.
export const EVENT_TYPE_OPTIONS = [
  { value: 'call', label: 'Call' },
  { value: 'demo', label: 'Demo' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'review_deal', label: 'Review Deal' },
  { value: 'other', label: 'Other' },
]
export const EVENT_TYPE_LABELS = Object.fromEntries(EVENT_TYPE_OPTIONS.map(o => [o.value, o.label]))
export const eventTypeLabel = (v) => EVENT_TYPE_LABELS[v] || v || 'Event'

export const ALERT_OPTIONS = [
  { value: '', label: 'No alert' },
  { value: 'at_time', label: 'At the time of the event' },
  { value: '5m', label: '5 minutes before' },
  { value: '10m', label: '10 minutes before' },
  { value: '15m', label: '15 minutes before' },
  { value: '30m', label: '30 minutes before' },
  { value: '1h', label: '1 hour before' },
  { value: '2h', label: '2 hours before' },
  { value: '1d', label: '1 day before' },
  { value: '2d', label: '2 days before' },
  { value: '1w', label: '1 week before' },
]
export const ALERT_LABELS = Object.fromEntries(ALERT_OPTIONS.map(o => [o.value, o.label]))
export const alertLabel = (v) => ALERT_LABELS[v] || v

// A small calendar glyph — used on the Kanban card summary + wherever an event
// is listed, to signify a date-based item. Inherits the current text colour.
export function CalendarIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={`inline-block shrink-0 ${className}`} aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  )
}

// datetime-local <input> works in LOCAL time with no zone; the API stores/returns
// a zoned ISO string. These convert between the two.
export function isoToLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export function localInputToIso(local) {
  if (!local) return null
  const d = new Date(local)
  return isNaN(d) ? null : d.toISOString()
}
// A complete, valid default for a new event — the next full hour — so the
// datetime picker never starts in the half-filled state that silently blocks
// submission.
function defaultStartsAt() {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return isoToLocalInput(d.toISOString())
}

const EMPTY = {
  event_type: 'meeting', starts_at: '', title: '', location: '', body: '',
  owner_user_id: '', contact_person_id: '', first_alert: '', second_alert: '',
}

// The Event fields — shared by the card-detail composer, the card-detail inline
// editor, and the standalone Events page. `ownerOptions` = super admins;
// `contactOptions` = [{id, name}] (a deal's linked people, or a chosen club's
// people). `extraTop` lets the standalone page slot a Club picker above the
// fields. Manages its own draft state seeded from `initial`.
export default function EventForm({ initial, ownerOptions = [], contactOptions = [], extraTop,
                                    onSubmit, onCancel, submitLabel = 'Save event', saving }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({
    ...EMPTY,
    ...(initial || {}),
    // Prefill a valid default (next full hour) for a brand-new event so the
    // datetime field is complete out of the box — otherwise a 12-hour-locale
    // browser leaves the AM/PM segment blank, the input reports an empty
    // value, and the form can't be submitted with no obvious reason why.
    starts_at: initial?.starts_at ? isoToLocalInput(initial.starts_at) : defaultStartsAt(),
  }))
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = (e) => {
    e.preventDefault()
    if (!form.starts_at) { toast.error('Pick a date and time for the event'); return }
    onSubmit({
      event_type: form.event_type,
      starts_at: localInputToIso(form.starts_at),
      title: form.title.trim() || null,
      location: form.location.trim() || null,
      body: form.body.trim() || null,
      owner_user_id: form.owner_user_id || null,
      contact_person_id: form.contact_person_id || null,
      first_alert: form.first_alert || null,
      second_alert: form.second_alert || null,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {extraTop}
      <div className="flex flex-wrap gap-3">
        <Field label="Event type" width="150px">
          <Select value={form.event_type} onChange={set('event_type')}>
            {EVENT_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Date & time" width="210px">
          <TextInput type="datetime-local" value={form.starts_at} onChange={set('starts_at')} required />
        </Field>
        <Field label="Title (optional)" width="230px">
          <TextInput value={form.title} onChange={set('title')} placeholder="e.g. Intro demo call" />
        </Field>
        <Field label="Location (optional)" width="200px">
          <TextInput value={form.location} onChange={set('location')} placeholder="e.g. Zoom / clubrooms" />
        </Field>
      </div>
      <div className="flex flex-wrap gap-3">
        {ownerOptions.length > 0 && (
          <Field label="Owner (assigned to)" width="200px">
            <Select value={form.owner_user_id} onChange={set('owner_user_id')}>
              <option value="">Unassigned</option>
              {ownerOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Club contact (optional)" width="220px">
          <Select value={form.contact_person_id} onChange={set('contact_person_id')} disabled={contactOptions.length === 0}>
            <option value="">{contactOptions.length === 0 ? 'No contacts available' : 'None'}</option>
            {contactOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="First alert (optional)" width="200px">
          <Select value={form.first_alert} onChange={set('first_alert')}>
            {ALERT_OPTIONS.map(o => <option key={o.value || 'none'} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Second alert (optional)" width="200px">
          <Select value={form.second_alert} onChange={set('second_alert')}>
            {ALERT_OPTIONS.map(o => <option key={o.value || 'none'} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)">
        <TextArea value={form.body} onChange={set('body')} placeholder="Anything to remember for this event…"
          style={{ minHeight: '80px' }} />
      </Field>
      <div className="flex items-center gap-2">
        <Btn type="submit" variant="primary" sm disabled={saving}>{submitLabel}</Btn>
        {onCancel && <Btn type="button" variant="ghost" sm onClick={onCancel} disabled={saving}>Cancel</Btn>}
      </div>
    </form>
  )
}

// Compact one-liner used on the Kanban card + list rows: "Demo · 5 Aug, 2:30pm".
export function eventSummaryText(ev) {
  if (!ev) return ''
  const when = ev.starts_at ? new Date(ev.starts_at).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  }) : ''
  const label = eventTypeLabel(ev.event_type)
  const title = ev.title ? ` · ${ev.title}` : ''
  return `${label}${title}${when ? ` · ${when}` : ''}`
}
