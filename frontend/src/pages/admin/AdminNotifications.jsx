import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import {
  Button, Caption, Checkbox, Empty, Note, SectionHeading, SegButtons, TextInput,
} from '../../components/admin/ui'

// Kept in step with services/notification_events.CHANNELS. A channel the server
// stops offering simply stops being drawn, because every row is built from the
// `channels` list the payload carries rather than from a hardcoded pair here.
const WEEKDAYS = [
  ['0', 'Mon'], ['1', 'Tue'], ['2', 'Wed'], ['3', 'Thu'],
  ['4', 'Fri'], ['5', 'Sat'], ['6', 'Sun'],
]

const FREQUENCIES = [
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
]

/** A toggle that saves the moment it is pressed.
 *
 * Deliberately not a form with a Save button: this screen is ~30 independent
 * switches, and asking somebody to remember to save after flicking one is how a
 * setting silently does not take. Each control carries its own in-flight and
 * error state, so one failing write says so where it happened rather than
 * blanking the page.
 */
function Toggle({ checked, onChange, disabled, children, hint }) {
  return (
    <Checkbox checked={checked} onChange={onChange} disabled={disabled} hint={hint}>
      {children}
    </Checkbox>
  )
}

function EventCard({ event, channels, canManage, onRule, onPreference, busy }) {
  const [config, setConfig] = useState(() => ({ ...event.config }))
  useEffect(() => { setConfig({ ...event.config }) }, [event.config])

  const off = !event.enabled
  return (
    <div className="rounded-lg border pb-hairline p-3.5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="text-sm text-pb-text">{event.label}</div>
          <p className="text-[12px] text-pb-dim mt-1 leading-[1.55]">{event.description}</p>
        </div>
        {canManage && (
          <Toggle checked={event.enabled} disabled={busy}
            onChange={v => onRule(event.key, { enabled: v })}>
            {event.enabled ? 'On' : 'Off'}
          </Toggle>
        )}
      </div>

      {canManage && !off && (
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
          {channels.map(c => (
            <Toggle key={c.key} checked={!!event.channels[c.key]} disabled={busy}
              onChange={v => onRule(event.key, { channels: { [c.key]: v } })}>
              {c.label}
            </Toggle>
          ))}
        </div>
      )}

      {canManage && !off && event.config_fields.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-4">
          {event.config_fields.map(f => (
            <div key={f.key} className="max-w-[260px]">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">
                {f.label}
              </label>
              <div className="flex items-center gap-2">
                <TextInput
                  type="number" min={f.minimum} max={f.maximum}
                  value={config[f.key] ?? f.default}
                  onChange={e => setConfig(c => ({ ...c, [f.key]: e.target.value }))}
                  onBlur={() => {
                    const raw = Number(config[f.key])
                    // The server clamps too — this is only so the field shows
                    // what will actually be stored rather than what was typed.
                    const value = Number.isFinite(raw)
                      ? Math.max(f.minimum, Math.min(f.maximum, Math.round(raw)))
                      : f.default
                    setConfig(c => ({ ...c, [f.key]: value }))
                    if (value !== event.config[f.key]) onRule(event.key, { config: { [f.key]: value } })
                  }}
                  disabled={busy}
                  className="w-24"
                />
                <span className="text-[12px] text-pb-faint">{f.unit}</span>
              </div>
              <p className="text-[11.5px] text-pb-faintest mt-1 leading-[1.5]">{f.hint}</p>
            </div>
          ))}
        </div>
      )}

      {/* A person's own opt-out, shown only where they would actually be told.
          Offering it on an event their capabilities keep them out of would be a
          control that could never change anything. */}
      {!off && (
        <div className="mt-3 pt-3 border-t pb-hairline">
          {event.receives ? (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">
                Send to me
              </span>
              {channels.filter(c => event.channels[c.key]).map(c => (
                <Toggle key={c.key} disabled={busy}
                  checked={event.my_channels[c.key] !== false}
                  onChange={v => onPreference(event.key, { [c.key]: v })}>
                  {c.label}
                </Toggle>
              ))}
              {channels.every(c => !event.channels[c.key]) && (
                <span className="text-[12px] text-pb-faintest">No channel is switched on for the club.</span>
              )}
            </div>
          ) : (
            <p className="text-[12px] text-pb-faintest">
              This one goes to the people who can act on it, which does not include you.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default function AdminNotifications() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState(null)

  const load = useCallback(async ({ quiet = false } = {}) => {
    try {
      const d = await api.getNotificationSettings()
      setData(d)
      setError(null)
    } catch (e) {
      if (!quiet) setError(e?.message || 'Could not load notification settings.')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const say = useCallback((message) => {
    setFlash(message)
    setTimeout(() => setFlash(f => (f === message ? null : f)), 2500)
  }, [])

  // Every write re-reads the whole payload rather than patching state locally:
  // a rule and a preference can both change what the OTHER control should draw
  // (switching a channel off at club level withdraws the personal toggle for
  // it), so one source of truth is cheaper than keeping two in step.
  const run = useCallback(async (fn, message) => {
    setBusy(true)
    try {
      await fn()
      await load({ quiet: true })
      if (message) say(message)
      setError(null)
    } catch (e) {
      setError(e?.message || 'That change could not be saved.')
    } finally {
      setBusy(false)
    }
  }, [load, say])

  const onRule = useCallback((key, patch) =>
    run(() => api.putNotificationRule(key, patch), 'Saved'), [run])
  const onPreference = useCallback((key, channels) =>
    run(() => api.putNotificationPreference(key, channels), 'Saved'), [run])
  const onClub = useCallback((patch, message) =>
    run(() => api.patchNotificationSettings(patch), message || 'Saved'), [run])

  const grouped = useMemo(() => {
    if (!data) return []
    return data.categories
      .map(c => ({ ...c, events: data.events.filter(e => e.category === c.key) }))
      .filter(c => c.events.length > 0)
  }, [data])

  const club = data?.club
  const canManage = !!data?.can_manage_club_settings
  const emailedAtAll = data?.my_blanket_optout?.email !== false

  return (
    <AdminLayout
      title="Notifications"
      caption="Choose what the club is told about, and how"
    >
      {error && <Note toneKey="warn" className="mb-4">{error}</Note>}
      {flash && <div className="mb-4"><Note>{flash}</Note></div>}

      {!data ? (
        <Empty>Loading…</Empty>
      ) : (
        <div className="space-y-6 max-w-[860px]">
          {/* Nothing is going anywhere until a provider is configured. Saying so
              here is the difference between "we turned it on and heard nothing"
              and a known state. */}
          {!data.email_provider_live && (
            <Note toneKey="warn" title="Email is not connected yet">
              Notifications are recorded and show in the app, but no email is
              actually being sent — the platform has no email provider configured.
            </Note>
          )}

          {canManage && (
            <section>
              <SectionHeading>The club</SectionHeading>
              <div className="rounded-lg border pb-hairline p-3.5 space-y-4">
                <Toggle checked={club.enabled} disabled={busy}
                  hint="Off means nothing at all is raised, on any channel, for anybody at the club."
                  onChange={v => onClub({ enabled: v }, v ? 'Notifications on' : 'Notifications off')}>
                  Send notifications for {' '}
                  <span className="text-pb-text">this club</span>
                </Toggle>

                {club.enabled && (
                  <>
                    <div className="flex flex-wrap gap-x-6 gap-y-2">
                      <Toggle checked={club.email_enabled} disabled={busy}
                        onChange={v => onClub({ email_enabled: v })}>Email</Toggle>
                      <Toggle checked={club.in_app_enabled} disabled={busy}
                        onChange={v => onClub({ in_app_enabled: v })}>In the app</Toggle>
                    </div>

                    {club.email_enabled && (
                      <div>
                        <Caption>How often the email goes out</Caption>
                        <div className="mt-2 flex flex-wrap items-center gap-3">
                          <SegButtons
                            tabs={FREQUENCIES}
                            value={club.email_frequency}
                            onChange={v => onClub({ email_frequency: v })}
                          />
                          {club.email_frequency === 'weekly' && (
                            <SegButtons
                              tabs={WEEKDAYS.map(([k, l]) => ({ key: k, label: l }))}
                              value={String(club.email_weekday)}
                              onChange={v => onClub({ email_weekday: Number(v) })}
                            />
                          )}
                        </div>
                        <p className="text-[11.5px] text-pb-faintest mt-2 leading-[1.5]">
                          Everything new goes out as one email, not one per thing.
                        </p>
                      </div>
                    )}

                    <div className="pt-1">
                      <Button variant="soft" disabled={busy}
                        onClick={() => run(async () => {
                          const r = await api.runNotificationScanNow()
                          say(r.emitted > 0
                            ? `Found ${r.emitted} thing${r.emitted === 1 ? '' : 's'} to tell you about.`
                            : 'Nothing new to raise right now.')
                        })}>
                        Check now
                      </Button>
                      <p className="text-[11.5px] text-pb-faintest mt-2 leading-[1.5]">
                        Looks for anything new and puts it in the app straight away, so you
                        can see this working rather than waiting for tomorrow. Safe to press
                        twice — nothing is raised more than once. It does not send email.
                      </p>
                    </div>
                  </>
                )}
              </div>
            </section>
          )}

          <section>
            <SectionHeading>What I am sent</SectionHeading>
            <div className="rounded-lg border pb-hairline p-3.5">
              <Toggle checked={emailedAtAll} disabled={busy}
                hint="Turning this off stops every notification email from this club reaching you. It does not change what anybody else is sent."
                onChange={v => onPreference('*', { email: v })}>
                Email me about this club
              </Toggle>
              {data.my_email
                ? <p className="text-[11.5px] text-pb-faintest mt-2">Sent to {data.my_email}.</p>
                : <p className="text-[11.5px] text-pb-faintest mt-2">
                    Your account has no email address, so nothing can be emailed to you.
                  </p>}
            </div>
          </section>

          {!canManage && (
            <Note>
              You can choose what reaches you below. Changing what the club as a whole
              is told about needs the Settings permission.
            </Note>
          )}

          {grouped.map(cat => (
            <section key={cat.key}>
              <SectionHeading>{cat.label}</SectionHeading>
              <div className="space-y-3">
                {cat.events.map(e => (
                  <EventCard
                    key={e.key} event={e} channels={data.channels}
                    canManage={canManage} busy={busy}
                    onRule={onRule} onPreference={onPreference}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </AdminLayout>
  )
}
