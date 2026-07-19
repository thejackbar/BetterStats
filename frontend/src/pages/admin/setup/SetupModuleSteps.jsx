/* Setup Wizard — module inline steps (BetterSelect / BetterSocials /
   BetterAdmin comms / BetterIQ / BetterFantasy). Same contract as
   SetupInlineSteps: every action calls the existing module endpoint. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { ProgressBar } from '../../../components/ProgressBar'
import { DoneStrip, FieldLabel, Notice, Spinner, TextInput, WizardButton } from './setupUi'

/* ── BetterSelect: Sync your fixtures ───────────────────────────────────── */

export function FixturesStep({ step, onRefresh }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const sync = async () => {
    setBusy(true)
    setResult(null)
    try {
      const res = await api.bsSyncFixtures()
      if (res?.synced > 0) {
        setResult({ tone: 'good', text: `${res.synced} fixture${res.synced === 1 ? '' : 's'} pulled in.` })
        onRefresh()
      } else {
        setResult({ tone: 'warn', text: res?.detail || 'No upcoming fixtures found yet. Re-run this once your association publishes them.' })
      }
    } catch (e) {
      setResult({ tone: 'bad', text: e?.message || 'Fixture sync failed.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {step.done && <DoneStrip>Fixtures are in. Re-sync any time from the Fixtures page.</DoneStrip>}
      <WizardButton onClick={sync} disabled={busy}>{busy ? <Spinner /> : null} SYNC FIXTURES</WizardButton>
      {result && <Notice tone={result.tone}>{result.text}</Notice>}
    </div>
  )
}

/* ── BetterSelect: Set up your squads ───────────────────────────────────── */

export function SquadsStep({ step, onRefresh }) {
  const [candidates, setCandidates] = useState(null)
  const [ticked, setTicked] = useState({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.bsSeedCandidates({ seasons: 3 }).then((res) => {
      const names = res?.candidates || res?.names || res || []
      const list = Array.isArray(names) ? names.map((c) => (typeof c === 'string' ? { name: c } : c)) : []
      setCandidates(list)
      setTicked(Object.fromEntries(list.map((c) => [c.name, !c.exists])))
    }).catch(() => setCandidates([]))
  }, [])

  const create = async () => {
    const names = Object.entries(ticked).filter(([, v]) => v).map(([k]) => k)
    if (!names.length) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.bsSeedTeams({ names })
      setMsg({ tone: 'good', text: `${res?.created ?? 0} squad${res?.created === 1 ? '' : 's'} created.` })
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not create squads.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {step.done && <DoneStrip>Squads exist. Manage them on the Squads page.</DoneStrip>}
      {candidates === null && <p className="font-mono text-[11px] text-pb-faint">Looking at where your players appeared…</p>}
      {candidates !== null && candidates.length === 0 && (
        <Notice tone="warn">
          No team names found in your recent seasons yet. Run your first full sync, then come
          back, or create squads by hand on the Squads page.
        </Notice>
      )}
      {candidates !== null && candidates.length > 0 && (
        <>
          <FieldLabel>Sides we found in your recent seasons</FieldLabel>
          <ul className="space-y-1.5 max-w-md">
            {candidates.map((c) => (
              <li key={c.name} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id={`squad-${c.name}`}
                  checked={!!ticked[c.name]}
                  disabled={!!c.exists}
                  onChange={(e) => setTicked((t) => ({ ...t, [c.name]: e.target.checked }))}
                />
                <label htmlFor={`squad-${c.name}`} className="font-mono text-[12px] text-pb-text">
                  {c.name}
                  {c.exists ? <span className="text-pb-faintest ml-2">already a squad</span> : null}
                </label>
              </li>
            ))}
          </ul>
          <WizardButton onClick={create} disabled={busy || !Object.values(ticked).some(Boolean)}>
            {busy ? <Spinner /> : null} CREATE SQUADS
          </WizardButton>
        </>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterSelect: Assign players to squads ─────────────────────────────── */

export function AssignPlayersStep({ step, onRefresh }) {
  const [suggest, setSuggest] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.bsAutoAssignSuggest({ seasons: 2, onlyUnassigned: true }).then(setSuggest).catch(() => setSuggest({ suggestions: [] }))
  }, [])
  useEffect(() => { load() }, [load])

  const apply = async () => {
    const suggestions = suggest?.suggestions || []
    if (!suggestions.length) return
    setBusy(true)
    setMsg(null)
    try {
      // Group by target squad — squad-assign takes one squad per call.
      const byTeam = new Map()
      for (const s of suggestions) {
        if (!byTeam.has(s.team_id)) byTeam.set(s.team_id, [])
        byTeam.get(s.team_id).push(s.player_id)
      }
      let updated = 0
      for (const [teamId, playerIds] of byTeam) {
        const res = await api.bsAssignSquad(playerIds, teamId)
        updated += res?.updated || 0
      }
      setMsg({ tone: 'good', text: `${updated} player${updated === 1 ? '' : 's'} assigned.` })
      load()
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not assign players.' })
    } finally {
      setBusy(false)
    }
  }

  const suggestions = suggest?.suggestions || []
  const byTeam = suggestions.reduce((acc, s) => {
    acc[s.team_name] = (acc[s.team_name] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {step.done && <DoneStrip>Players are assigned to squads. Fine-tune on the Squads board.</DoneStrip>}
      {suggest === null && <p className="font-mono text-[11px] text-pb-faint">Working out who plays where…</p>}
      {suggest !== null && suggestions.length === 0 && (
        <Notice tone={step.done ? 'info' : 'warn'}>
          {step.done
            ? 'Nothing left to assign automatically.'
            : 'No suggestions yet. Create your squads first (previous step), then come back.'}
        </Notice>
      )}
      {suggestions.length > 0 && (
        <>
          <FieldLabel>Suggested placements (from where each player actually played)</FieldLabel>
          <ul className="space-y-1 max-w-md">
            {Object.entries(byTeam).map(([team, n]) => (
              <li key={team} className="font-mono text-[12px] text-pb-text">
                {team} <span className="text-pb-faint">gets {n} player{n === 1 ? '' : 's'}</span>
              </li>
            ))}
          </ul>
          {(suggest?.unmatched || []).length > 0 && (
            <p className="font-mono text-[11px] text-pb-faintest">
              {suggest.unmatched.length} player{suggest.unmatched.length === 1 ? '' : 's'} couldn't be matched to a
              squad automatically. You can place them by hand on the Squads board.
            </p>
          )}
          <WizardButton onClick={apply} disabled={busy}>
            {busy ? <Spinner /> : null} ASSIGN {suggestions.length} PLAYER{suggestions.length === 1 ? '' : 'S'}
          </WizardButton>
        </>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterSelect: availability self-serve link ─────────────────────────── */

export function SelfServeStep({ step, onRefresh }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.bsGetSelfService().then(setState).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const setEnabled = async (enabled) => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.bsSetSelfService({ enabled })
      setState(res)
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not update.' })
    } finally {
      setBusy(false)
    }
  }

  const link = state?.path ? `${window.location.origin}${state.path}` : null
  const copy = async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="space-y-4">
      {state?.enabled ? (
        <>
          <DoneStrip>The availability link is live.</DoneStrip>
          {link && (
            <div className="space-y-2 max-w-lg">
              <FieldLabel>Share this with your players</FieldLabel>
              <div className="flex items-center gap-2">
                <TextInput readOnly value={link} className="font-mono text-[11px]" onFocus={(e) => e.target.select()} />
                <WizardButton variant="secondary" onClick={copy}>{copied ? 'COPIED ✓' : 'COPY'}</WizardButton>
              </div>
              <p className="font-mono text-[11px] text-pb-faintest">
                The QR code and ready-made group-chat message live on the Availability page.
                {state?.phone_coverage && state.phone_coverage.total > 0 && (
                  <> {state.phone_coverage.with_phone} of {state.phone_coverage.total} active players have a phone
                  number on file for the PIN check, the player-details import (earlier step) fills the gaps.</>
                )}
              </p>
            </div>
          )}
          <WizardButton variant="secondary" onClick={() => setEnabled(false)} disabled={busy}>TURN OFF</WizardButton>
        </>
      ) : (
        <WizardButton onClick={() => setEnabled(true)} disabled={busy || !state}>
          {busy ? <Spinner /> : null} TURN ON THE AVAILABILITY LINK
        </WizardButton>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterSocials: club website ────────────────────────────────────────── */

export function WebsiteStep({ step, onRefresh }) {
  const [settings, setSettings] = useState(null)
  const [tagline, setTagline] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.webAdminSettings().then((s) => {
      setSettings(s)
      setTagline(s?.tagline || '')
    }).catch(() => {})
  }, [])

  const save = async (enabled) => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.webAdminSaveSettings({ enabled, tagline })
      setSettings(res)
      setMsg({ tone: 'good', text: enabled ? 'Your website is live.' : 'Website switched off.' })
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not update the website.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {settings?.enabled && <DoneStrip>Your club website is on.</DoneStrip>}
      <div className="max-w-lg">
        <FieldLabel>Tagline (shows under your club name)</FieldLabel>
        <TextInput value={tagline} onChange={(e) => setTagline(e.target.value)} placeholder="e.g. Est. 1928 · Home of the Roos" maxLength={200} />
      </div>
      <div className="flex items-center gap-3">
        {settings?.enabled ? (
          <>
            <WizardButton onClick={() => save(true)} disabled={busy}>{busy ? <Spinner /> : null} SAVE TAGLINE</WizardButton>
            <WizardButton variant="secondary" onClick={() => save(false)} disabled={busy}>TURN OFF</WizardButton>
          </>
        ) : (
          <WizardButton onClick={() => save(true)} disabled={busy || !settings}>
            {busy ? <Spinner /> : null} TURN ON YOUR WEBSITE
          </WizardButton>
        )}
      </div>
      <p className="font-mono text-[11px] text-pb-faintest">
        News, honour boards, committee and galleries are all edited from the Website section
        of the admin, add them whenever suits.
      </p>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterAdmin: Connect Square (one connection per club, made in
   BetterMerch, shared with BetterFees) ──────────────────────────────────── */

export function SquareStep({ step, onOpenTool }) {
  const { hasModule } = useAuth()
  const canConnect = hasModule('merch') // the OAuth connect lives on the merch router
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    const fetchStatus = canConnect ? api.merchSquareStatus : api.feeSquareStatus
    fetchStatus().then(setStatus).catch(() => setStatus({ configured: false }))
  }, [canConnect])

  const connect = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.merchSquareConnectUrl()
      if (res?.url) {
        // Off to Square's consent page — the OAuth callback lands back in the
        // admin, where the floating "back to setup" pill brings them home.
        try { sessionStorage.setItem('bs_setup_return', step.key) } catch { /* private mode */ }
        window.location.assign(res.url)
        return
      }
      setMsg({ tone: 'bad', text: 'Could not get a Square sign-in link.' })
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not start the Square connection.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {status === null && <p className="font-mono text-[11px] text-pb-faint">Checking your Square connection…</p>}
      {status?.connected && (
        <DoneStrip>
          Square is connected{status.location_name ? ` (${status.location_name})` : ''} and shared across
          BetterMerch and BetterFees.
        </DoneStrip>
      )}
      {status && !status.connected && !status.configured && (
        <Notice tone="warn">Square isn't configured on the server yet — get in touch and we'll switch it on.</Notice>
      )}
      {status && !status.connected && status.configured && (
        canConnect ? (
          <WizardButton onClick={connect} disabled={busy}>
            {busy ? <Spinner /> : null} CONNECT SQUARE
          </WizardButton>
        ) : (
          <Notice tone="info">
            Square connects once per club through BetterMerch. Open the Square page for the
            connection status and next steps.
          </Notice>
        )
      )}
      {status?.connected && status.needs_location && (
        <Notice tone="warn">Connected, but Square needs a location picked — finish that on the Square page.</Notice>
      )}
      {status?.connected && (
        <WizardButton variant="secondary" onClick={() => onOpenTool(step)}>OPEN SQUARE SETTINGS →</WizardButton>
      )}
      {status && !status.connected && !canConnect && (
        <WizardButton variant="secondary" onClick={() => onOpenTool(step)}>OPEN THE SQUARE PAGE →</WizardButton>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterAdmin: Connect Xero ──────────────────────────────────────────── */

export function XeroStep({ step, onOpenTool }) {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.feeXeroStatus().then(setStatus).catch(() => setStatus({ configured: false }))
  }, [])

  const connect = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.feeXeroConnectUrl()
      if (res?.url) {
        try { sessionStorage.setItem('bs_setup_return', step.key) } catch { /* private mode */ }
        window.location.assign(res.url)
        return
      }
      setMsg({ tone: 'bad', text: 'Could not get a Xero sign-in link.' })
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not start the Xero connection.' })
    } finally {
      setBusy(false)
    }
  }

  const needsFinishing = status?.connected && (status.needs_tenant || status.needs_bank_account)
  return (
    <div className="space-y-4">
      {status === null && <p className="font-mono text-[11px] text-pb-faint">Checking your Xero connection…</p>}
      {status?.connected && (
        <DoneStrip>
          Xero is connected{status.tenant_name ? ` (${status.tenant_name})` : ''}
          {status.bank_account_name ? `, watching ${status.bank_account_name}` : ''}.
        </DoneStrip>
      )}
      {status && !status.connected && !status.configured && (
        <Notice tone="warn">Xero isn't configured on the server yet — get in touch and we'll switch it on.</Notice>
      )}
      {status && !status.connected && status.configured && (
        <WizardButton onClick={connect} disabled={busy}>
          {busy ? <Spinner /> : null} CONNECT XERO
        </WizardButton>
      )}
      {needsFinishing && (
        <Notice tone="warn">
          Connected, but Xero still needs {status.needs_tenant ? 'an organisation' : 'a bank account'} picked —
          finish that on the Xero page.
        </Notice>
      )}
      {status?.connected && (
        <WizardButton variant="secondary" onClick={() => onOpenTool(step)}>OPEN XERO SETTINGS →</WizardButton>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterComms: sender details ────────────────────────────────────────── */

export function CommsStep({ step, onRefresh }) {
  const [replyTo, setReplyTo] = useState('')
  const [footer, setFooter] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.commsGetSettings().then((s) => {
      setReplyTo(s?.reply_to || '')
      setFooter(s?.sender_footer || '')
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [])

  const save = async () => {
    setBusy(true)
    setMsg(null)
    try {
      await api.commsSetSettings({ reply_to: replyTo.trim(), sender_footer: footer.trim() })
      setMsg({ tone: 'good', text: 'Saved.' })
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not save.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {step.done && <DoneStrip>Sender details are set.</DoneStrip>}
      <div className="max-w-lg space-y-3">
        <div>
          <FieldLabel>Reply-to email</FieldLabel>
          <TextInput type="email" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} placeholder="secretary@yourclub.com.au" />
          <p className="font-mono text-[10px] text-pb-faintest mt-1">When a member replies to a club email, it lands here.</p>
        </div>
        <div>
          <FieldLabel>Email footer</FieldLabel>
          <TextInput value={footer} onChange={(e) => setFooter(e.target.value)} placeholder="Your Cricket Club Inc · PO Box 1 Yourtown WA" />
          <p className="font-mono text-[10px] text-pb-faintest mt-1">
            Goes on the bottom of every email. Australian spam rules require the sender's
            identity, so club name plus a contact or postal line is the go.
          </p>
        </div>
      </div>
      <WizardButton onClick={save} disabled={busy || !loaded}>{busy ? <Spinner /> : null} SAVE</WizardButton>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterIQ: opposition prewarm ───────────────────────────────────────── */

export function IqPrewarmStep({ step, onRefresh }) {
  const [options, setOptions] = useState(null)
  const [ticked, setTicked] = useState({})
  const [progress, setProgress] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    api.iqPrewarmOptions().then((o) => {
      setOptions(o)
      setTicked(Object.fromEntries((o?.suggested || []).map((id) => [id, true])))
      if (o?.status === 'running') setProgress(o)
    }).catch(() => setOptions({ grades: [] }))
  }, [])

  const poll = useCallback(async () => {
    try {
      const st = await api.iqPrewarmStatus()
      setProgress(st)
      if (st?.status !== 'running') {
        clearInterval(pollRef.current)
        pollRef.current = null
        if (st?.status === 'done') onRefresh()
      }
    } catch { /* silent */ }
  }, [onRefresh])

  useEffect(() => {
    if (progress?.status === 'running' && !pollRef.current) {
      pollRef.current = setInterval(poll, 5000)
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [progress?.status, poll])

  const start = async () => {
    const gradeIds = Object.entries(ticked).filter(([, v]) => v).map(([k]) => k)
    if (!gradeIds.length) return
    setBusy(true)
    setMsg(null)
    try {
      const st = await api.iqPrewarmStart(gradeIds)
      if (st?.status === 'running') {
        setProgress(st)
      } else {
        setMsg({ tone: 'warn', text: st?.detail || 'Nothing to build yet.' })
      }
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not start.' })
    } finally {
      setBusy(false)
    }
  }

  const running = progress?.status === 'running'
  return (
    <div className="space-y-4">
      {step.done && !running && <DoneStrip>Opposition dossiers are built. Open Opposition Scout and they'll load instantly.</DoneStrip>}
      {options === null && <p className="font-mono text-[11px] text-pb-faint">Loading your grades…</p>}
      {options !== null && !running && (
        (options.grades || []).length === 0 ? (
          <Notice tone="warn">No grades with opponents found yet. Run your first full sync, then come back.</Notice>
        ) : (
          <>
            <FieldLabel>Pick the grades to scout (your busiest three are pre-ticked)</FieldLabel>
            <ul className="space-y-1.5 max-w-md">
              {options.grades.map((g) => (
                <li key={g.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`pw-${g.id}`}
                    checked={!!ticked[g.id]}
                    disabled={!g.opponents}
                    onChange={(e) => setTicked((t) => ({ ...t, [g.id]: e.target.checked }))}
                  />
                  <label htmlFor={`pw-${g.id}`} className="font-mono text-[12px] text-pb-text">
                    {g.name} <span className="text-pb-faintest">{g.opponents} opponent{g.opponents === 1 ? '' : 's'}</span>
                  </label>
                </li>
              ))}
            </ul>
            <WizardButton onClick={start} disabled={busy || !Object.values(ticked).some(Boolean)}>
              {busy ? <Spinner /> : null} START PRE-ANALYSIS
            </WizardButton>
            <p className="font-mono text-[11px] text-pb-faintest">
              Builds one opponent at a time in the background, up to a minute each. You can move
              on, it keeps going.
            </p>
          </>
        )
      )}
      {progress && progress.status !== 'idle' && (
        <div className="space-y-1 max-w-lg">
          <ProgressBar
            pct={progress.total ? Math.round((progress.done / progress.total) * 100) : 0}
            label={
              running
                ? `Scouting ${progress.current || '…'} (${progress.done}/${progress.total})`
                : `Done: ${progress.done}/${progress.total} opponents built`
            }
          />
        </div>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

/* ── BetterFantasy: season + pool ───────────────────────────────────────── */

function fantasyYearDefault() {
  const now = new Date()
  // An Australian season "2026/27" starts around October — from July onward
  // assume the upcoming summer, before that the one still running.
  return now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1
}

export function FantasySeasonStep({ onRefresh }) {
  const [data, setData] = useState(null)
  const [year, setYear] = useState(fantasyYearDefault())
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.fantasyGetSeason().then(setData).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const create = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.fantasyCreateSeason(Number(year))
      setMsg({ tone: 'good', text: res?.created ? `${res.season?.name || 'Season'} created.` : 'That season already exists.' })
      load()
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not create the season.' })
    } finally {
      setBusy(false)
    }
  }

  const y = Number(year) || fantasyYearDefault()
  return (
    <div className="space-y-4">
      {data?.season ? (
        <DoneStrip>{data.season.name} exists. Sign-up link and managers live on the Fantasy pages.</DoneStrip>
      ) : (
        <>
          <div className="max-w-xs">
            <FieldLabel>Season year</FieldLabel>
            <select
              value={y}
              onChange={(e) => setYear(e.target.value)}
              className="w-full bg-pb-bg border pb-hairline rounded px-3 py-2 text-sm text-pb-text focus:outline-none focus:border-pb-accent"
            >
              {[y - 1, y, y + 1].map((opt) => (
                <option key={opt} value={opt}>{opt}/{String((opt + 1) % 100).padStart(2, '0')}</option>
              ))}
            </select>
          </div>
          <WizardButton onClick={create} disabled={busy}>{busy ? <Spinner /> : null} CREATE FANTASY SEASON</WizardButton>
        </>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}

export function FantasyPoolStep({ onRefresh }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.fantasyGetSeason().then(setData).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const build = async () => {
    if (!data?.season?.id) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.fantasyBuildPool(data.season.id)
      setMsg({ tone: 'good', text: `${res?.pool ?? 0} players priced into the pool.` })
      load()
      onRefresh()
    } catch (e) {
      setMsg({ tone: 'bad', text: e?.message || 'Could not build the pool.' })
    } finally {
      setBusy(false)
    }
  }

  const poolCount = data?.counts?.pool || 0
  return (
    <div className="space-y-4">
      {poolCount > 0 && <DoneStrip>{poolCount} players in the pool. Adjust prices on the Pool page.</DoneStrip>}
      {data && !data.season && (
        <Notice tone="warn">Create the fantasy season first (previous step), then build the pool.</Notice>
      )}
      {data?.season && (
        <WizardButton onClick={build} disabled={busy}>
          {busy ? <Spinner /> : null} {poolCount > 0 ? 'RE-BUILD POOL' : 'BUILD PLAYER POOL'}
        </WizardButton>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  )
}
