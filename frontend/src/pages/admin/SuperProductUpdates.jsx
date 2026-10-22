import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { Button, Badge, Note, Empty } from '../../components/admin/ui'

// Better HQ → Comms → Daily Update. At 9am Melbourne time a short, club-facing
// "what's new" note goes into every club's notifications, written by a model from
// the release notes and posted with no review (backend/app/routers/product_updates.py,
// services/product_blast.py). This screen is the control room: the Stop switch,
// a preview of what would go out next, the log of every attempt with what the
// model wrote, and a way to take a post down.

const STATUS = {
  posted: { tone: 'ok', label: 'Posted' },
  skipped: { tone: 'calm', label: 'Nothing to post' },
  blocked: { tone: 'warn', label: 'Held back' },
  failed: { tone: 'block', label: 'Failed' },
  retracted: { tone: 'calm', label: 'Taken down' },
}

const fmtWhen = iso => iso
  ? new Date(iso).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  : ''

function Bullets({ headline, bullets }) {
  return (
    <div>
      {headline && <p className="text-sm font-semibold text-pb-text">{headline}</p>}
      <ul className="mt-1 space-y-1">
        {bullets.map((b, i) => (
          <li key={i} className="text-sm text-pb-dim leading-[1.5]">• {b}</li>
        ))}
      </ul>
    </div>
  )
}

function PreviewCard({ preview }) {
  if (preview.status === 'preview') {
    return (
      <div className="pb-card p-4" data-testid="preview-result">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">
          Preview of the next post · nothing has been sent
        </p>
        <Bullets headline={preview.headline} bullets={preview.bullets} />
        <p className="mt-2 text-xs text-pb-faint">
          Covers {preview.versions.length} release{preview.versions.length === 1 ? '' : 's'}.
        </p>
      </div>
    )
  }
  return (
    <div className="pb-card p-4" data-testid="preview-result">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">
        Preview · nothing has been sent
      </p>
      <p className="text-sm text-pb-dim">
        {preview.status === 'blocked' && 'It would be held back. '}
        {preview.status === 'skipped' && 'It would post nothing. '}
        {preview.status === 'failed' && 'It would fail. '}
        {preview.reason}
      </p>
      {preview.raw_output && (
        <pre className="mt-2 text-[11px] text-pb-faint whitespace-pre-wrap break-words">{preview.raw_output}</pre>
      )}
    </div>
  )
}

function LogRow({ blast, busy, onTakeDown }) {
  const [showRaw, setShowRaw] = useState(false)
  const st = STATUS[blast.status] || STATUS.skipped
  return (
    <div className="pb-card p-4" data-testid="blast-row">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-2">
        <Badge toneKey={st.tone}>{st.label}</Badge>
        <span className="font-mono text-[10.5px] text-pb-faint">{blast.blast_date} · {fmtWhen(blast.created_at)}</span>
        {blast.status === 'posted' && (
          <span className="text-xs text-pb-faint">told {blast.orgs_notified} club{blast.orgs_notified === 1 ? '' : 's'}</span>
        )}
      </div>
      {blast.headline && blast.bullets.length > 0 && (
        <Bullets headline={blast.headline} bullets={blast.bullets} />
      )}
      {blast.reason && <p className="text-sm text-pb-dim">{blast.reason}</p>}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {blast.raw_output && (
          <Button size="sm" variant="quiet" onClick={() => setShowRaw(v => !v)}>
            {showRaw ? 'Hide what the model wrote' : 'What the model wrote'}
          </Button>
        )}
        {blast.status === 'posted' && (
          <Button size="sm" variant="danger" disabled={busy} onClick={() => onTakeDown(blast)}>Take down</Button>
        )}
      </div>
      {showRaw && (
        <pre className="mt-2 text-[11px] text-pb-faint whitespace-pre-wrap break-words">{blast.raw_output}</pre>
      )}
      {blast.versions.length > 0 && showRaw && (
        <p className="mt-2 font-mono text-[10.5px] text-pb-faint">RELEASES: {blast.versions.join(', ')}</p>
      )}
    </div>
  )
}

export default function SuperProductUpdates() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [preview, setPreview] = useState(null)
  const [notice, setNotice] = useState('')

  const load = () => api.superProductUpdates()
    .then(d => { setData(d); setError('') })
    .catch(e => setError(e.message || 'Could not load the daily update'))

  useEffect(() => { load() }, [])

  // While a backfill runs, keep the progress fresh. It is one model call per day,
  // so it takes a while; the notes are saved as it goes.
  const backfillRunning = !!data?.backfill?.running
  useEffect(() => {
    if (!backfillRunning) return undefined
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [backfillRunning])

  const run = async (key, fn) => {
    setBusy(key)
    setNotice('')
    try {
      await fn()
    } catch (e) {
      setError(e.message || 'That did not work')
    } finally {
      setBusy('')
    }
  }

  const setPaused = paused => run('control', async () => {
    await api.superProductUpdatesControl(paused)
    await load()
  })

  const doPreview = () => run('preview', async () => {
    setPreview(await api.superProductUpdatesPreview())
  })

  const runNow = () => {
    if (!window.confirm('Post today\'s update to every club now? It goes out exactly as the 9am run would.')) return
    return run('run', async () => {
      const r = await api.superProductUpdatesRun()
      setNotice(r.status === 'posted'
        ? `Posted. ${r.orgs_notified} club${r.orgs_notified === 1 ? '' : 's'} told.`
        : r.status === 'already_posted'
          ? 'Today already has a post.'
          : r.reason || 'Nothing was posted.')
      await load()
    })
  }

  const startBackfill = () => {
    if (!window.confirm('Write a note for every past day in the release history? Nothing is sent to any club. The notes only appear on the What\'s New page. It makes one request per day, so it takes a while.')) return
    return run('backfill', async () => {
      await api.superProductUpdatesBackfill()
      await load()
    })
  }

  const takeDown = blast => {
    if (!window.confirm('Take this post down? It is removed from every club\'s notifications.')) return
    return run(blast.id, async () => {
      await api.superProductUpdatesTakeDown(blast.id)
      await load()
    })
  }

  const paused = !!data?.paused

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <div className="mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">Daily Update</h1>
          <p className="text-pb-faint text-sm mt-1">
            A short note on new features and fixes, posted to every club's notifications at 9am Melbourne
            time. It is written from the release notes and leaves out the technical detail. Nothing is
            reviewed before it goes out, so read a preview before you start it.
          </p>
        </div>

        {error && <Note toneKey="block">{error}</Note>}
        {!data && !error && <Empty>Loading…</Empty>}

        {data && (
          <>
            <div className="pb-card p-4 mb-4" data-testid="control-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge toneKey={paused ? 'warn' : 'ok'}>{paused ? 'Stopped' : 'Running'}</Badge>
                    <span className="text-sm text-pb-dim">
                      {paused
                        ? 'Nothing is posted while this is stopped.'
                        : 'The next post is at 9am Melbourne time, on a day with something to say.'}
                    </span>
                  </div>
                </div>
                <Button
                  variant={paused ? 'primary' : 'secondary'}
                  disabled={busy === 'control'}
                  onClick={() => setPaused(!paused)}
                >
                  {paused ? 'Start daily updates' : 'Stop daily updates'}
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="soft" disabled={busy === 'preview'} onClick={doPreview}>
                  {busy === 'preview' ? 'Writing a preview…' : 'Preview the next post'}
                </Button>
                <Button
                  variant="secondary"
                  disabled={paused || busy === 'run'}
                  title={paused ? 'Start the daily updates first' : undefined}
                  onClick={runNow}
                >
                  Run now
                </Button>
              </div>
              {paused && (
                <p className="mt-2 text-xs text-pb-faint">Run now is off while the updates are stopped.</p>
              )}
              <p className="mt-2 text-xs text-pb-faint">
                Looks at releases from the last {data.max_age_days} days that have not been covered yet.
              </p>
            </div>

            <div className="pb-card p-4 mb-4" data-testid="backfill-card">
              <p className="text-sm font-semibold text-pb-text">History</p>
              <p className="mt-1 text-sm text-pb-dim">
                Fill the What's New page with a note for every past day in the release history.
                Nothing is sent to any club.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button variant="soft" disabled={backfillRunning || busy === 'backfill'} onClick={startBackfill}>
                  {backfillRunning ? 'Backfilling…' : 'Backfill history'}
                </Button>
                {backfillRunning && (
                  <span className="text-xs text-pb-faint" data-testid="backfill-progress">
                    Day {data.backfill.done} of {data.backfill.total}
                    {data.backfill.current ? ` (${data.backfill.current})` : ''}
                  </span>
                )}
              </div>
              {!backfillRunning && Object.keys(data.backfill?.stored || {}).length > 0 && (
                <p className="mt-2 text-xs text-pb-faint" data-testid="backfill-stored">
                  Stored so far: {data.backfill.stored.posted || 0} notes, {data.backfill.stored.skipped || 0} quiet days
                  {data.backfill.stored.blocked ? `, ${data.backfill.stored.blocked} held back` : ''}.
                </p>
              )}
              {data.backfill?.error && !backfillRunning && (
                <p className="mt-2 text-xs text-pb-faint">Last problem: {data.backfill.error}</p>
              )}
            </div>

            {notice && <Note toneKey="accent" className="mb-4">{notice}</Note>}
            {preview && <div className="mb-4"><PreviewCard preview={preview} /></div>}

            <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-2">Log</h2>
            {data.blasts.length === 0 && <Empty>Nothing has run yet.</Empty>}
            <div className="space-y-3">
              {data.blasts.map(b => (
                <LogRow key={b.id} blast={b} busy={busy === b.id} onTakeDown={takeDown} />
              ))}
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
