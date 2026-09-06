import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import {
  Button, TextInput, Field, Note, Caption, StatCard, TableWrap, TableHead,
  TableRow, Cell, Badge, SegButtons, Empty,
} from '../../components/admin/ui'
import { useToast } from '../../contexts/ToastContext'

const HISTORY_COLS = 'minmax(160px,1fr) 180px 110px 90px 90px'
const HISTORY_MIN_W = 660

const PHASES = {
  starting: 'Getting started',
  seasons: 'Working out which seasons you played',
  matches: 'Bringing your matches across',
  records: 'Copying your record book',
  done: 'Finished',
}

function pct(done, total) {
  if (!total) return 0
  return Math.min(100, Math.round((done / total) * 100))
}

function Bar({ value }) {
  return (
    <div className="h-2 w-full rounded-full overflow-hidden"
         style={{ background: 'var(--pb-surface2)' }}>
      <div className="h-full rounded-full transition-all"
           style={{ width: `${value}%`, background: 'var(--pb-accent)' }} />
    </div>
  )
}

export default function AdminCricketStatzImport() {
  const toast = useToast()
  const [url, setUrl] = useState('')
  const [checking, setChecking] = useState(false)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)
  const [imports, setImports] = useState([])
  const [records, setRecords] = useState([])
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState('import')
  const [undoing, setUndoing] = useState(null)
  const pollRef = useRef(null)

  const running = status?.import?.status === 'running'

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.csStatus()
      setStatus(s)
      if (s?.club_id && !url) setUrl(`https://www2.cricketstatz.com/ss/w?club=${s.club_id}`)
      return s
    } catch { return null }
  }, [url])

  const loadRest = useCallback(async () => {
    try { setImports((await api.csImports()).imports || []) } catch { /* listed on next load */ }
    try { setRecords((await api.csRecords()).records || []) } catch { /* ditto */ }
  }, [])

  useEffect(() => { loadStatus(); loadRest() }, [])   // eslint-disable-line

  // While an import runs, poll it — it can be several thousand matches, so the
  // request that starts it returns immediately and progress is read from here.
  useEffect(() => {
    if (!running) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return undefined
    }
    pollRef.current = setInterval(async () => {
      const s = await loadStatus()
      if (s?.import?.status !== 'running') loadRest()
    }, 2500)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [running, loadStatus, loadRest])

  async function check() {
    setChecking(true); setError(''); setPreview(null)
    try {
      setPreview(await api.csInspect(url))
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not read that address.')
    } finally { setChecking(false) }
  }

  async function start() {
    setStarting(true); setError('')
    try {
      await api.csStartImport(url)
      toast?.success?.('Import started — this page will keep you posted.')
      await loadStatus()
    } catch (e) {
      setError(e?.detail || e?.message || 'Could not start the import.')
    } finally { setStarting(false) }
  }

  async function undo(id) {
    if (!window.confirm(
      'Remove every match and record this import brought across?\n\n'
      + 'Players and seasons are kept — only the imported matches and record '
      + 'boards go.')) return
    setUndoing(id)
    try {
      const r = await api.csUndo(id)
      toast?.success?.(`Removed ${r.matches_removed} matches and ${r.records_removed} record boards.`)
      await loadStatus(); await loadRest()
    } catch (e) {
      toast?.error?.(e?.detail || 'Could not undo that import.')
    } finally { setUndoing(null) }
  }

  const p = status?.import?.progress || {}
  const done = status?.import?.status === 'complete'

  return (
    <BetterStatsLayout
      title="Import from CricketStatz"
      caption="Bring your whole club history across from your own CricketStatz site"
    >
      <div className="max-w-4xl space-y-4">
        <SegButtons
          value={tab}
          onChange={setTab}
          tabs={[
            { key: 'import', label: 'Import' },
            { key: 'records', label: `Record book${records.length ? ` (${records.length})` : ''}` },
            { key: 'history', label: `Past imports${imports.length ? ` (${imports.length})` : ''}` },
          ]}
        />

        {tab === 'import' && (
          <>
            <div className="pb-card p-4 space-y-3">
              <Field label="Your CricketStatz stats page">
                <TextInput
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www2.cricketstatz.com/ss/w?mode=104&club=93931"
                  disabled={running}
                />
              </Field>
              <Caption>
                Open your club's stats page on CricketStatz and copy the address
                from your browser. It carries your club number, which is all we
                need.
              </Caption>
              <div className="flex flex-wrap gap-2">
                <Button onClick={check} disabled={!url || checking || running}>
                  {checking ? 'Checking…' : 'Check this site'}
                </Button>
                {preview && (
                  <Button variant="primary" onClick={start} disabled={starting || running}>
                    {starting ? 'Starting…' : 'Import everything'}
                  </Button>
                )}
              </div>
              {error && <Note toneKey="block">{error}</Note>}
            </div>

            {preview && (
              <div className="pb-card p-4 space-y-3">
                <div className="font-semibold">{preview.club_name || 'That club'}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="Matches found" value={
                    preview.truncated ? `${preview.matches_found}+` : preview.matches_found} />
                  <StatCard label="Earliest" value={preview.earliest?.slice(0, 4) || '—'} />
                  <StatCard label="Latest" value={preview.latest?.slice(0, 4) || '—'} />
                  <StatCard label="Record boards" value={preview.record_reports} />
                </div>
                {preview.truncated && (
                  <Note>
                    CricketStatz caps one list at 999 matches, so there are more
                    than this. The import walks your history season by season,
                    which picks up every one of them.
                  </Note>
                )}
                {!!preview.teams?.length && (
                  <Caption>Teams: {preview.teams.slice(0, 8).join(', ')}
                    {preview.teams.length > 8 ? ` and ${preview.teams.length - 8} more` : ''}
                  </Caption>
                )}
                <Note>
                  A full history can take a while — it reads every match's
                  scorecard one at a time, gently, so we are not hammering
                  someone else's server. You can leave this page; it keeps
                  running.
                </Note>
              </div>
            )}

            {status?.import && (
              <div className="pb-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">
                    {status.import.club_name || 'Import'}
                  </div>
                  <Badge toneKey={
                    status.import.status === 'complete' ? 'ok'
                      : status.import.status === 'error' ? 'block' : 'accent'}>
                    {status.import.status === 'running'
                      ? (PHASES[status.import.phase] || 'Working')
                      : status.import.status}
                  </Badge>
                </div>

                {running && (
                  <>
                    <Bar value={p.matches_total
                      ? pct(p.matches_done, p.matches_total)
                      : pct(p.seasons_done, p.seasons_total)} />
                    <Caption>
                      {p.seasons_total
                        ? `Season ${p.seasons_done} of ${p.seasons_total}`
                        : 'Working out your seasons'}
                      {p.matches_total ? ` · ${p.matches_done} of ${p.matches_total} matches` : ''}
                    </Caption>
                  </>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="Matches" value={p.matches_done || 0} />
                  <StatCard label="Scorecards" value={p.scorecards || 0} />
                  <StatCard label="Players" value={p.players || 0} />
                  <StatCard label="Record boards" value={p.records || 0} />
                </div>

                {status.import.error && <Note toneKey="block">{status.import.error}</Note>}
                {done && (
                  <Note toneKey="ok">
                    Your history is in. It now shows on your players' profiles,
                    your records and everywhere else the rest of your stats do.
                  </Note>
                )}
                {!!p.notes?.length && (
                  <details>
                    <summary className="cursor-pointer text-sm">
                      {p.notes.length} thing{p.notes.length === 1 ? '' : 's'} we
                      could not read
                    </summary>
                    <ul className="mt-2 text-sm space-y-1">
                      {p.notes.slice(0, 50).map((n, i) => <li key={i}>{n}</li>)}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </>
        )}

        {tab === 'records' && (
          records.length === 0
            ? <Empty>Your record book arrives with your first import.</Empty>
            : <RecordBook records={records} />
        )}

        {tab === 'history' && (
          imports.length === 0
            ? <Empty>Nothing imported yet.</Empty>
            : (
              <TableWrap>
                <TableHead cols={HISTORY_COLS} minWidth={HISTORY_MIN_W}>
                  <Cell head first>Club</Cell>
                  <Cell head>Started</Cell>
                  <Cell head>Status</Cell>
                  <Cell head num>Matches</Cell>
                  <Cell head last />
                </TableHead>
                {imports.map((i) => (
                  <TableRow key={i.id} cols={HISTORY_COLS} minWidth={HISTORY_MIN_W}>
                    <Cell first>{i.club_name || i.club_id}</Cell>
                    <Cell>{i.started_at ? new Date(i.started_at).toLocaleDateString() : '—'}</Cell>
                    <Cell>
                      <Badge toneKey={
                        i.undone_at ? 'calm'
                          : i.status === 'complete' ? 'ok'
                            : i.status === 'error' ? 'block' : 'accent'}>
                        {i.undone_at ? 'undone' : i.status}
                      </Badge>
                    </Cell>
                    <Cell num>{i.matches}</Cell>
                    <Cell last>
                      {!i.undone_at && i.status !== 'running' && (
                        <Button variant="quiet-danger" size="sm" onClick={() => undo(i.id)}
                                disabled={undoing === i.id}>
                          {undoing === i.id ? 'Removing…' : 'Undo'}
                        </Button>
                      )}
                    </Cell>
                  </TableRow>
                ))}
              </TableWrap>
            )
        )}
      </div>
    </BetterStatsLayout>
  )
}

function RecordBook({ records }) {
  const sections = [...new Set(records.map((r) => r.section || 'other'))]
  const [open, setOpen] = useState(records[0]?.mode ?? null)
  return (
    <div className="space-y-4">
      <Note>
        These are your records as CricketStatz worked them out, kept as they
        were. BetterCricket also works out its own from the scorecards it now
        holds, so the two can be compared rather than silently blended.
      </Note>
      {sections.map((section) => (
        <div key={section} className="space-y-2">
          <div className="text-xs uppercase tracking-wide opacity-70">{section}</div>
          {records.filter((r) => (r.section || 'other') === section).map((r) => (
            <div key={r.mode} className="pb-card p-3">
              <button
                type="button"
                className="w-full text-left flex items-center justify-between gap-2"
                onClick={() => setOpen(open === r.mode ? null : r.mode)}
                aria-expanded={open === r.mode}
              >
                <span className="font-medium">{r.title}</span>
                <span className="text-sm opacity-70">{r.row_count}</span>
              </button>
              {open === r.mode && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr>
                        {(r.headers || []).map((h, i) => (
                          <th key={i} className="text-left pr-3 pb-1 font-medium opacity-70">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(r.rows || []).slice(0, 50).map((row, i) => (
                        <tr key={i}>
                          {(row.values || []).map((v, j) => (
                            <td key={j} className="pr-3 py-1 whitespace-nowrap">{v}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
