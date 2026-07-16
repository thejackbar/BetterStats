/* Setup Wizard — core inline steps (Get your data in group).

   Each step component receives:
   - step      the flow step object ({key, done, skipped, ...})
   - onRefresh re-fetch the flow (call after an action that changes state)

   Every action here goes through the SAME existing endpoint the full admin
   tool uses — the wizard hosts a simpler surface, it doesn't reimplement. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { ProgressBar } from '../../../components/ProgressBar'
import { DoneStrip, FieldLabel, Notice, Spinner, TextInput, WizardButton } from './setupUi'

const NAME_FORMATS = [
  { value: 'last_first', label: 'Smith, John' },
  { value: 'first_last', label: 'John Smith' },
  { value: 'first_initial_last', label: 'J Smith' },
  { value: 'last_first_initial', label: 'Smith J' },
]

/* ── Step: Run your first full sync ─────────────────────────────────────── */

export function FullRebuildStep({ step, onRefresh }) {
  const [orgId, setOrgId] = useState(null)
  const [runningLog, setRunningLog] = useState(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const wasRunning = useRef(false)

  useEffect(() => {
    api.adminGetSettings().then((s) => setOrgId(s?.id)).catch(() => {})
  }, [])

  const fetchLogs = useCallback(async () => {
    if (!orgId) return
    try {
      const logs = await api.getSyncLogs(orgId)
      const latest = (logs || [])[0]
      const running = latest && latest.status === 'running' ? latest : null
      setRunningLog(running)
      if (wasRunning.current && !running) {
        wasRunning.current = false
        onRefresh() // a run just finished — the step may now auto-complete
      }
      if (running) wasRunning.current = true
    } catch { /* silent */ }
  }, [orgId, onRefresh])

  useEffect(() => {
    fetchLogs()
    const id = setInterval(fetchLogs, 4000)
    return () => clearInterval(id)
  }, [fetchLogs])

  const start = async () => {
    setStarting(true)
    setError('')
    try {
      await api.adminHardRefreshOrg()
      wasRunning.current = true
      await fetchLogs()
    } catch (e) {
      setError(e?.message || 'Could not start the sync.')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="space-y-4">
      {step.done && <DoneStrip>Your first full sync has completed. Your club's history is in.</DoneStrip>}
      {runningLog ? (
        <div className="space-y-2">
          <ProgressBar
            pct={runningLog?.stats?.progress_pct ?? 0}
            label={runningLog?.stats?.progress_phase || 'Syncing your club’s history…'}
          />
          <p className="font-mono text-[11px] text-pb-faint">
            This runs in the background. You can keep going with the branding and sponsor
            steps and come back, or leave the site entirely, it keeps running either way.
          </p>
        </div>
      ) : (
        !step.done && (
          <div className="space-y-3">
            <WizardButton onClick={start} disabled={starting || !orgId}>
              {starting ? <Spinner /> : null} START FULL SYNC
            </WizardButton>
            {error && <Notice tone="bad">{error}</Notice>}
          </div>
        )
      )}
      {step.done && !runningLog && (
        <p className="font-mono text-[11px] text-pb-faint">
          Need to pull everything again later (for example after merging players at the
          association's end)? The Full Rebuild button lives on the Sync page.
        </p>
      )}
    </div>
  )
}

/* ── Step: Logo, colours and player names ───────────────────────────────── */

export function BrandingStep({ onRefresh }) {
  const [settings, setSettings] = useState(null)
  const [primary, setPrimary] = useState('#16c784')
  const [accent, setAccent] = useState('#243352')
  const [nameFormat, setNameFormat] = useState('last_first')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [msg, setMsg] = useState(null) // {tone, text}

  useEffect(() => {
    api.adminGetSettings().then((s) => {
      setSettings(s)
      if (s?.primary_color) setPrimary(s.primary_color)
      if (s?.accent_color) setAccent(s.accent_color)
      if (s?.player_name_format) setNameFormat(s.player_name_format)
    }).catch(() => {})
  }, [])

  const uploadLogo = async (file) => {
    if (!file) return
    setUploading(true)
    setMsg(null)
    try {
      const res = await api.adminUploadLogo(file)
      setSettings((s) => ({ ...s, logo_url: res?.logo_url || s?.logo_url || 'uploaded' }))
      setMsg({ tone: 'good', text: 'Logo uploaded.' })
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Upload failed. JPG, PNG, WEBP or GIF up to 2 MB.' })
    } finally {
      setUploading(false)
    }
  }

  const save = async () => {
    setSaving(true)
    setMsg(null)
    try {
      await api.adminPatchSettings({ primary_color: primary, accent_color: accent, player_name_format: nameFormat })
      setMsg({ tone: 'good', text: 'Saved.' })
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not save.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <FieldLabel>Club logo</FieldLabel>
        <div className="flex items-center gap-4">
          {settings?.logo_url ? (
            <img src={settings.logo_url} alt="Club logo" className="w-14 h-14 object-contain rounded border pb-hairline bg-pb-bg" />
          ) : (
            <div className="w-14 h-14 rounded border pb-hairline bg-pb-bg flex items-center justify-center font-mono text-[9px] text-pb-faintest">
              NO LOGO
            </div>
          )}
          <label className="cursor-pointer inline-flex items-center gap-2 font-mono text-[11px] tracking-wide2 border pb-hairline rounded px-4 py-2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2">
            {uploading ? <Spinner /> : null} {settings?.logo_url ? 'REPLACE LOGO' : 'UPLOAD LOGO'}
            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadLogo(e.target.files?.[0])} />
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-md">
        <div>
          <FieldLabel>Primary colour</FieldLabel>
          <div className="flex items-center gap-2">
            <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} className="w-9 h-9 rounded border pb-hairline bg-pb-bg cursor-pointer" />
            <TextInput value={primary} onChange={(e) => setPrimary(e.target.value)} className="font-mono text-[12px]" />
          </div>
        </div>
        <div>
          <FieldLabel>Secondary colour</FieldLabel>
          <div className="flex items-center gap-2">
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} className="w-9 h-9 rounded border pb-hairline bg-pb-bg cursor-pointer" />
            <TextInput value={accent} onChange={(e) => setAccent(e.target.value)} className="font-mono text-[12px]" />
          </div>
        </div>
      </div>

      <div className="max-w-xs">
        <FieldLabel>Player name format</FieldLabel>
        <select
          value={nameFormat}
          onChange={(e) => setNameFormat(e.target.value)}
          className="w-full bg-pb-bg border pb-hairline rounded px-3 py-2 text-sm text-pb-text focus:outline-none focus:border-pb-accent"
        >
          {NAME_FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <WizardButton onClick={save} disabled={saving}>{saving ? <Spinner /> : null} SAVE</WizardButton>
        {msg && <span className={`font-mono text-[11px] ${msg.tone === 'good' ? 'text-pb-positive' : 'text-pb-red'}`}>{msg.text}</span>}
      </div>
    </div>
  )
}

/* ── Step: Add your sponsors ─────────────────────────────────────────────── */

export function SponsorsStep({ onRefresh }) {
  const [sponsors, setSponsors] = useState(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [logoFile, setLogoFile] = useState(null)
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.adminListSponsors().then(setSponsors).catch(() => setSponsors([]))
  }, [])
  useEffect(() => { load() }, [load])

  const add = async () => {
    if (!name.trim()) return
    setAdding(true)
    setMsg(null)
    try {
      const sp = await api.adminCreateSponsor({ name: name.trim(), website_url: url.trim() || null })
      if (logoFile && sp?.id) {
        try { await api.adminUploadSponsorLogo(sp.id, logoFile) } catch { /* sponsor saved; logo can be retried on the Sponsors page */ }
      }
      setName(''); setUrl(''); setLogoFile(null)
      setMsg({ tone: 'good', text: `${sp?.name || 'Sponsor'} added.` })
      load()
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not add the sponsor.' })
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="space-y-4">
      {sponsors && sponsors.length > 0 && (
        <div>
          <FieldLabel>Current sponsors</FieldLabel>
          <ul className="flex flex-wrap gap-2">
            {sponsors.map((s) => (
              <li key={s.id} className="flex items-center gap-2 border pb-hairline rounded px-2.5 py-1.5 bg-pb-bg">
                {s.logo_url && <img src={s.logo_url} alt="" className="w-5 h-5 object-contain" />}
                <span className="font-mono text-[11px] text-pb-text">{s.name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg">
        <div>
          <FieldLabel>Sponsor name</FieldLabel>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. The Corner Bakery" />
        </div>
        <div>
          <FieldLabel>Website (optional)</FieldLabel>
          <TextInput value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </div>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="cursor-pointer inline-flex items-center gap-2 font-mono text-[11px] tracking-wide2 border pb-hairline rounded px-4 py-2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2">
          {logoFile ? `LOGO: ${logoFile.name.slice(0, 24)}` : 'ADD LOGO (OPTIONAL)'}
          <input type="file" accept="image/*" className="hidden" onChange={(e) => setLogoFile(e.target.files?.[0] || null)} />
        </label>
        <WizardButton onClick={add} disabled={adding || !name.trim()}>
          {adding ? <Spinner /> : null} ADD SPONSOR
        </WizardButton>
        {msg && <span className={`font-mono text-[11px] ${msg.tone === 'good' ? 'text-pb-positive' : 'text-pb-red'}`}>{msg.text}</span>}
      </div>
      <p className="font-mono text-[11px] text-pb-faintest">
        Add as many as you like. Reordering and editing lives on the Sponsors page.
      </p>
    </div>
  )
}
