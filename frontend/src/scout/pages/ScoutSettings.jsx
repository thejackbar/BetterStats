import { useEffect, useState } from 'react'
import { scoutApi } from '../lib/scoutApi'
import { useScoutAuth } from '../contexts/ScoutAuthContext'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { Btn, Segmented } from '../../pages/admin/betterselect/ui'
import { initialsOf } from '../components/ScoutUi'

const ORG_TYPES = [
  { value: '', label: '— none —' },
  { value: 'agency', label: 'Recruiting agency' },
  { value: 'club', label: 'Club (scouting its own pathway)' },
  { value: 'selector', label: 'Selector' },
]
const REGIONS = [
  '', 'WA', 'NSW', 'VIC', 'QLD', 'SA', 'TAS', 'NT', 'ACT',
  'North England', 'South England', 'Midlands', 'Scotland', 'Wales', 'Other/International',
]
const WINDOWS = [
  { value: '1', label: 'Last 1 season' },
  { value: '2', label: 'Last 2 seasons' },
  { value: '5', label: 'Last 5 seasons' },
  { value: 'full', label: 'Full window' },
]
const EXPIRY_OPTIONS = [7, 30, 90, 180, 365]

function Toggle({ on, onChange, disabled }) {
  return (
    <button type="button" disabled={disabled} onClick={() => !disabled && onChange(!on)}
      className="relative shrink-0 transition-colors"
      style={{
        width: 38, height: 21, borderRadius: 999,
        background: on ? 'var(--pb-accent)' : 'var(--pb-surface2)',
        border: `1px solid ${on ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
      }}>
      <span className="absolute rounded-full bg-white transition-transform" style={{
        width: 15, height: 15, top: 2, left: 2,
        transform: on ? 'translateX(17px)' : 'translateX(0)',
      }} />
    </button>
  )
}

function Card({ title, children, className = '' }) {
  return (
    <div className={`pb-card p-4 space-y-3 ${className}`}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{title}</div>
      {children}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">{label}</div>
      {children}
    </label>
  )
}

const inputCls = 'w-full bg-pb-surface2 border border-pb-hairline rounded px-2.5 py-1.5 text-sm'

export default function ScoutSettings() {
  const { user, refetch } = useScoutAuth()
  const isOwner = user?.role === 'owner'
  const [settings, setSettings] = useState(null)
  const [orgName, setOrgName] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)
  const [billing, setBilling] = useState(null)
  const [people, setPeople] = useState(null)
  const [shareLinks, setShareLinks] = useState([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('viewer')
  const [error, setError] = useState(null)

  const load = () => {
    scoutApi.getSettings().then((s) => { setSettings(s); setOrgName(s.org_name) })
    scoutApi.getBilling().then(setBilling)
    scoutApi.listPeople().then(setPeople)
    scoutApi.listShareLinksOrg().then(setShareLinks)
  }
  useEffect(load, [])

  const set = (key, value) => { setSettings((s) => ({ ...s, [key]: value })); setDirty(true) }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await scoutApi.updateSettings({
        name: orgName.trim(),
        org_type: settings.org_type, home_region: settings.home_region,
        refresh_cadence: settings.refresh_cadence, stale_after_weeks: settings.stale_after_weeks,
        default_window: settings.default_window, share_include_notes: settings.share_include_notes,
        share_include_tags: settings.share_include_tags, share_expiry_days: settings.share_expiry_days,
        digest_enabled: settings.digest_enabled, alert_scope: settings.alert_scope,
      })
      setSettings(updated)
      setOrgName(updated.org_name)
      setDirty(false)
      setSavedAt(new Date())
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const invite = async (e) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    try {
      await scoutApi.invitePerson(inviteEmail.trim(), inviteRole)
      setInviteEmail('')
      scoutApi.listPeople().then(setPeople)
    } catch (err) {
      setError(err.message)
    }
  }

  const revokeInvite = async (id) => {
    await scoutApi.revokeInvite(id)
    scoutApi.listPeople().then(setPeople)
  }

  const revokeAll = async () => {
    if (!window.confirm(`Revoke all ${shareLinks.length} live share link(s)? Anyone holding one loses access immediately.`)) return
    await scoutApi.revokeAllShareLinks()
    setShareLinks([])
  }

  const closeOrg = async () => {
    if (!window.confirm('Close this Scout Org? This deletes every watchlist, note and share link — it cannot be undone. Cached club rosters stay, they aren’t yours.')) return
    if (!window.confirm('Really sure? Type nothing further needed — this is the final confirmation.')) return
    await scoutApi.closeOrg()
    window.location.href = '/betterscout/login'
  }

  if (!settings) {
    return <ScoutModuleLayout title="Settings"><p className="text-pb-dim text-sm">Loading…</p></ScoutModuleLayout>
  }

  return (
    <ScoutModuleLayout
      title="Settings"
      caption={`${settings.org_name} · ${billing?.tier_label || ''} plan · ${people ? people.users.length : '…'} seat${people?.users.length === 1 ? '' : 's'}`}
      actions={
        <div className="flex items-center gap-3">
          {savedAt && !dirty && <span className="text-xs text-pb-faint">Last saved {savedAt.toLocaleTimeString()}</span>}
          <Btn variant="primary" onClick={save} disabled={!dirty || saving || !isOwner || !orgName.trim()} title={!isOwner ? 'Only an org owner can change settings.' : undefined}>
            {saving ? 'Saving…' : 'Save changes'}
          </Btn>
        </div>
      }
    >
      <div className="space-y-5 max-w-[1200px]">
        {error && <p className="text-sm text-pb-red">{error}</p>}
        {!isOwner && <p className="text-sm text-pb-amber bg-pb-amber/5 border border-pb-amber/30 rounded-lg px-3 py-2">You're signed in as a viewer — you can see these settings but only an owner can change them.</p>}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left column */}
          <div className="space-y-5">
            <Card title="Organisation">
              <div className="flex items-center gap-3">
                <div className="w-16 h-16 rounded-lg border border-dashed border-pb-hairline2 flex items-center justify-center bg-pb-surface2 shrink-0">
                  <span className="font-mono text-[8px] text-pb-faintest text-center">LOGO</span>
                </div>
                <div className="flex-1 space-y-2">
                  <Field label="Organisation name">
                    <input
                      value={orgName}
                      onChange={(e) => { setOrgName(e.target.value); setDirty(true) }}
                      disabled={!isOwner}
                      className={inputCls}
                    />
                  </Field>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Org type">
                  <select value={settings.org_type} onChange={(e) => set('org_type', e.target.value)} disabled={!isOwner} className={inputCls}>
                    {ORG_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </Field>
                <Field label="Home region">
                  <select value={settings.home_region} onChange={(e) => set('home_region', e.target.value)} disabled={!isOwner} className={inputCls}>
                    {REGIONS.map((r) => <option key={r} value={r}>{r || '— none —'}</option>)}
                  </select>
                </Field>
              </div>
              <p className="text-[11.5px] text-pb-faint">Org type only sets sensible defaults elsewhere — scout orgs never see club-admin data, whatever type this is set to.</p>
            </Card>

            <Card title="Plan & usage">
              <span className="inline-block font-mono text-[10px] uppercase tracking-wide2 px-2 py-1 rounded bg-pb-amber/15 text-pb-amber">Billing not collecting yet</span>
              {billing && (
                <>
                  <div className="flex items-center justify-between text-sm">
                    <span>{billing.tier_label} — {billing.player_cap ? `up to ${billing.player_cap} players` : 'no cap'}</span>
                    <span className="font-mono text-pb-dim">{billing.player_count} / {billing.player_cap ?? '∞'}</span>
                  </div>
                  {billing.player_cap != null && (
                    <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
                      <div className="h-full rounded-full" style={{
                        width: `${Math.min(100, Math.round(100 * billing.player_count / billing.player_cap))}%`,
                        background: billing.at_cap ? 'var(--pb-red)' : 'var(--pb-accent)',
                      }} />
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2">
                    {billing.tiers.map((t) => (
                      <div key={t.key} className="rounded-lg border p-2.5 text-center"
                        style={t.key === billing.tier
                          ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }
                          : { borderColor: 'var(--pb-hairline)' }}>
                        <div className="font-semibold text-[13px]">{t.label}</div>
                        <div className="font-mono text-[10.5px] text-pb-faint mt-0.5">{t.cap ? `${t.cap} players` : 'No cap'}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
              <p className="text-[11.5px] text-pb-faint">Caps are enforced today — a player past your limit is blocked from being added.</p>
              <div className="flex gap-2">
                <Btn variant="soft" sm>Request an upgrade</Btn>
                <Btn variant="ghost" sm>Archive players to free slots</Btn>
              </div>
            </Card>

            <Card title="People">
              <div className="flex items-center justify-between">
                <span className="text-xs text-pb-faint">{people?.users.length ?? 0} member{people?.users.length === 1 ? '' : 's'}</span>
              </div>
              <div className="divide-y divide-pb-hairline -mx-1">
                {people?.users.map((u) => (
                  <div key={u.id} className="flex items-center gap-2.5 px-1 py-2">
                    <span className="w-[30px] h-[30px] rounded-full bg-pb-surface2 border border-pb-hairline2 text-pb-dim font-display font-semibold text-[11px] flex items-center justify-center shrink-0">
                      {initialsOf(u.display_name || u.username)}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{u.display_name || u.username}</div>
                      <div className="text-xs text-pb-faint truncate">{u.email || u.username}</div>
                    </div>
                    <span className={`font-mono text-[9.5px] uppercase px-1.5 py-0.5 rounded ${u.role === 'owner' ? 'bg-pb-accent/15 text-pb-accent' : 'bg-pb-surface2 text-pb-faint'}`}>
                      {u.role}
                    </span>
                  </div>
                ))}
                {people?.invites.map((i) => (
                  <div key={i.id} className="flex items-center gap-2.5 px-1 py-2">
                    <span className="w-[30px] h-[30px] rounded-full border border-dashed border-pb-hairline2 flex items-center justify-center shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{i.email}</div>
                      <div className="text-xs text-pb-faint truncate">
                        Invited {new Date(i.invited_at).toLocaleDateString()} · {i.role === 'owner' ? 'owner' : 'read-only'}{i.expired ? ' · expired' : ''}
                      </div>
                    </div>
                    {isOwner && (
                      <div className="flex items-center gap-1.5">
                        <button onClick={() => { setInviteEmail(i.email); setInviteRole(i.role) }} className="text-xs text-pb-faint hover:text-pb-text underline">Resend</button>
                        <button onClick={() => revokeInvite(i.id)} className="text-xs text-pb-faint hover:text-pb-red">✕</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {isOwner && (
                <form onSubmit={invite} className="flex items-center gap-1.5 pt-1">
                  <input type="email" required placeholder="email@example.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className={`${inputCls} flex-1`} />
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className={inputCls} style={{ width: 110 }}>
                    <option value="viewer">Viewer</option>
                    <option value="owner">Owner</option>
                  </select>
                  <Btn variant="primary" sm type="submit">+ Invite</Btn>
                </form>
              )}
            </Card>
          </div>

          {/* Right column */}
          <div className="space-y-5">
            <Card title="Data & refresh">
              <Field label="Refresh cadence">
                <Segmented options={[{ value: 'daily', label: 'DAILY' }, { value: 'weekly', label: 'WEEKLY' }, { value: 'manual', label: 'MANUAL' }]}
                  value={settings.refresh_cadence} onChange={(v) => isOwner && set('refresh_cadence', v)} sm />
              </Field>
              <Field label="Call a player stale after">
                <select value={settings.stale_after_weeks} onChange={(e) => set('stale_after_weeks', parseInt(e.target.value, 10))} disabled={!isOwner} className={inputCls} style={{ width: 160 }}>
                  {[2, 4, 6, 8, 12].map((w) => <option key={w} value={w}>{w} weeks</option>)}
                </select>
              </Field>
              <p className="text-[11.5px] text-pb-faint">Drives Overview's "going stale" panel.</p>
              <Field label="Default career window">
                <select value={settings.default_window} onChange={(e) => set('default_window', e.target.value)} disabled={!isOwner} className={inputCls} style={{ width: 200 }}>
                  {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
                </select>
              </Field>
              <p className="text-[11.5px] text-pb-faint">BetterScout pulls roughly ten seasons per player and says so wherever a career total is shown.</p>
            </Card>

            <Card title="Sharing defaults">
              <ToggleRow label="Include notes on a shared card" on={settings.share_include_notes} onChange={(v) => set('share_include_notes', v)} disabled={!isOwner} />
              <ToggleRow label="Include tags on a shared card" on={settings.share_include_tags} onChange={(v) => set('share_include_tags', v)} disabled={!isOwner} />
              <ToggleRow label="Include recruiting fields" on={false} disabled note="Visa, fee, agent and availability never leave the org." />
              <Field label="Share links expire after">
                <select value={settings.share_expiry_days ?? ''} onChange={(e) => set('share_expiry_days', e.target.value ? parseInt(e.target.value, 10) : null)} disabled={!isOwner} className={inputCls} style={{ width: 160 }}>
                  <option value="">Never</option>
                  {EXPIRY_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
                </select>
              </Field>
              <div className="flex items-center justify-between pt-1 border-t border-pb-hairline mt-1">
                <span className="text-xs text-pb-dim">{shareLinks.length} link{shareLinks.length === 1 ? '' : 's'} live now</span>
                {isOwner && shareLinks.length > 0 && <Btn variant="danger" sm onClick={revokeAll}>Revoke all</Btn>}
              </div>
            </Card>

            <Card title="Milestone alerts">
              <ToggleRow label="Weekly digest" sub="Monday morning: milestones reached, in reach, form movers" on={settings.digest_enabled} onChange={(v) => set('digest_enabled', v)} disabled={!isOwner} />
              <Field label="Alert me within">
                <select disabled className={inputCls} style={{ width: 200 }}><option>House default</option></select>
              </Field>
              <ToggleRow label="Only players on a watchlist" on={settings.alert_scope === 'watchlisted_only'} onChange={(v) => set('alert_scope', v ? 'watchlisted_only' : 'all_tracked')} disabled={!isOwner} />
              <p className="text-[11.5px] text-pb-faint">Real-time alerts wait on scheduled crawling — see Milestones for the full note.</p>
            </Card>

            {isOwner && (
              <div className="pb-card p-4 space-y-3 border-pb-red/40" style={{ background: 'color-mix(in srgb, var(--pb-red) 4%, transparent)' }}>
                <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-red">Danger zone</div>
                <div className="text-sm font-medium">Close this Scout Org</div>
                <p className="text-[11.5px] text-pb-faint">Deletes watchlists, notes and share links. Cached club rosters stay — they aren't yours.</p>
                <Btn variant="danger" sm onClick={closeOrg}>Close org</Btn>
              </div>
            )}
          </div>
        </div>
      </div>
    </ScoutModuleLayout>
  )
}

function ToggleRow({ label, sub, on, onChange, disabled, note }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="text-sm">{label}</div>
        {sub && <div className="text-[11.5px] text-pb-faint mt-0.5">{sub}</div>}
        {note && <div className="text-[11.5px] text-pb-faint mt-0.5">{note}</div>}
      </div>
      <Toggle on={on} onChange={onChange} disabled={disabled} />
    </div>
  )
}
