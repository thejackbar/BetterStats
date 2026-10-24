import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'

// The club teaser crawl's rate and hours, with how far through the directory it
// is. It writes through the General Settings PATCH (the one place these two
// settings are validated) and reads back GET /marketing/teaser/status. The Stop
// switch above it on the Club Directory page also stops this crawl, so the panel
// says so rather than adding a second stop control that could disagree.

const POLL_MS = 15000
const RENDER_POLL_MS = 3000
const RENDER_BATCH = 50

const STATE = {
  off:           { label: 'Off',           dot: 'bg-pb-faint',  text: 'text-pb-dim',
                   why: 'Nothing is being pulled. Set a rate and save to start.' },
  stopped:       { label: 'Stopped',       dot: 'bg-red-400',   text: 'text-red-300',
                   why: 'The crawler is stopped. Press Start crawling above to let this run.' },
  outside_hours: { label: 'Outside hours', dot: 'bg-amber-400', text: 'text-amber-300',
                   why: 'Waiting for the hours to open.' },
  idle:          { label: 'Caught up',     dot: 'bg-emerald-400', text: 'text-emerald-300',
                   why: 'Every club is up to date. It looks again in a few minutes.' },
  running:       { label: 'Running',       dot: 'bg-emerald-400', text: 'text-emerald-300',
                   why: 'Pulling the next clubs due.' },
}

// What the worker's last pass found, in the words the panel uses.
const WORKER_SAID = {
  worked: 'pulled clubs', idle: 'nothing due', off: 'switched off', stopped: 'stopped',
  outside_window: 'outside its hours', trouble: 'Cricket Australia errors, backing off', error: 'the pass failed',
}

const INPUT = 'bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs text-pb-text w-20 focus:outline-none focus:border-pb-accent'
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border border-pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_ACCENT = 'px-3 py-1.5 rounded text-xs font-semibold bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 disabled:opacity-50'

const hh = (h) => `${String(h).padStart(2, '0')}:00`
const num = (n) => Number(n || 0).toLocaleString()

// A moment in Perth time, the clock the crawl's hours are set in: "Sat 24 Oct, 14:32".
export const perthWhen = (iso) => new Date(iso).toLocaleString('en-AU', {
  timeZone: 'Australia/Perth', weekday: 'short', day: 'numeric', month: 'short',
  hour: '2-digit', minute: '2-digit', hour12: false,
})

export function agoText(iso, now = Date.now()) {
  const secs = Math.round((now - new Date(iso).getTime()) / 1000)
  if (secs < 0) return 'in the future'
  if (secs < 90) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 90) return `${mins} minutes ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 48) return `${hrs} hours ago`
  return `${Math.round(hrs / 24)} days ago`
}

// The error a bad value would come back with, checked here first so a typo does
// not need a round trip. The server checks the same bounds again.
export function draftProblem(edit, st) {
  const rate = Number(edit.rate)
  if (edit.rate === '' || !Number.isFinite(rate)) return 'Enter a rate in calls per second.'
  if (rate < st.min_rate || rate > st.max_rate) return `The rate must be between ${st.min_rate} and ${st.max_rate}.`
  const start = Number(edit.start), end = Number(edit.end)
  if (!Number.isInteger(start) || start < 0 || start > 23) return 'The opening hour must be 0 to 23.'
  if (!Number.isInteger(end) || end < 1 || end > 24) return 'The closing hour must be 1 to 24.'
  if (start >= end) return 'The hours must open before they close.'
  return ''
}

export default function TeaserCrawlPanel() {
  const [st, setSt] = useState(null)
  const [edit, setEdit] = useState(null)   // null = showing what is saved
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [loadErr, setLoadErr] = useState('')

  const load = useCallback(async () => {
    try {
      setSt(await api.mktTeaserStatus())
      setLoadErr('')
    } catch (e) { setLoadErr(e.message || 'Could not read the crawl status.') }
  }, [])

  const rendering = !!st?.images?.running
  useEffect(() => {
    load()
    const t = setInterval(() => { if (!document.hidden) load() }, rendering ? RENDER_POLL_MS : POLL_MS)
    return () => clearInterval(t)
  }, [load, rendering])

  if (!st) {
    return loadErr
      ? <div className="rounded-lg border border-pb-hairline bg-pb-surface2 px-3 py-2 mb-2.5 text-xs text-red-300">{loadErr}</div>
      : null
  }

  const saved = { rate: st.rate ? String(st.rate) : '', start: String(st.window_start), end: String(st.window_end) }
  const shown = edit || saved
  const dirty = !!edit && (edit.rate !== saved.rate || edit.start !== saved.start || edit.end !== saved.end)
  const problem = dirty ? draftProblem(edit, st) : ''
  const s = STATE[st.state] || STATE.off
  const p = st.progress
  const est = st.estimate
  const set = (k, v) => { setMsg(''); setErr(''); setEdit({ ...shown, [k]: v }) }

  const save = async () => {
    if (problem || !dirty) return
    const rate = Number(edit.rate)
    if (!st.rate && !window.confirm(
      `Start pulling club teasers from Cricket Australia at about ${rate} calls a second, `
      + `between ${hh(Number(edit.start))} and ${hh(Number(edit.end))} Perth time?`)) return
    setBusy('save'); setMsg(''); setErr('')
    try {
      await api.superUpdateGeneralSettings({
        club_teaser_calls_per_second: rate,
        club_teaser_window_start: Number(edit.start),
        club_teaser_window_end: Number(edit.end),
      })
      setEdit(null)
      setMsg('Saved. The crawl picks it up within a couple of minutes.')
      await load()
    } catch (e) { setErr(e.message || 'Could not save.') } finally { setBusy('') }
  }

  const turnOff = async () => {
    setBusy('off'); setMsg(''); setErr('')
    try {
      await api.superUpdateGeneralSettings({ club_teaser_calls_per_second: null })
      setEdit(null)
      setMsg('Switched off. Nothing more is pulled once the club in flight finishes.')
      await load()
    } catch (e) { setErr(e.message || 'Could not switch it off.') } finally { setBusy('') }
  }

  const img = st.images
  const draw = async () => {
    setBusy('draw'); setMsg(''); setErr('')
    try {
      const r = await api.mktTeaserRender(RENDER_BATCH)
      setMsg(r.started ? `Drawing up to ${RENDER_BATCH} pictures. This updates as they finish.`
                       : 'A batch is already being drawn.')
      await load()
    } catch (e) { setErr(e.message || 'Could not start drawing.') } finally { setBusy('') }
  }

  const achieved = p.calls_last_hour ? (p.calls_last_hour / 3600).toFixed(2) : null

  return (
    <div className="rounded-lg border border-pb-hairline bg-pb-surface2 px-3 py-2.5 mb-2.5" data-testid="teaser-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${s.dot}`} />
        <span className="text-xs font-semibold text-pb-text">Club teaser crawl</span>
        <span className={`text-xs font-semibold ${s.text}`} data-testid="teaser-state">{s.label}</span>
        <span className="text-xs text-pb-dim">{s.why}</span>
      </div>

      <div className="flex flex-wrap items-end gap-3 mt-2.5">
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">
          Calls per second
          <input className={INPUT} type="number" inputMode="decimal" step="0.25"
                 min={st.min_rate} max={st.max_rate} data-testid="teaser-rate"
                 value={shown.rate} placeholder="off"
                 onChange={(e) => set('rate', e.target.value)} />
        </label>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">
          Opens (Perth hour)
          <input className={INPUT} type="number" min="0" max="23" step="1" data-testid="teaser-start"
                 value={shown.start} onChange={(e) => set('start', e.target.value)} />
        </label>
        <label className="text-[11px] text-pb-dim flex flex-col gap-1">
          Closes (Perth hour)
          <input className={INPUT} type="number" min="1" max="24" step="1" data-testid="teaser-end"
                 value={shown.end} onChange={(e) => set('end', e.target.value)} />
        </label>
        <button className={BTN_ACCENT} data-testid="teaser-save"
                disabled={busy !== '' || !dirty || !!problem} onClick={save}>
          {busy === 'save' ? 'Saving...' : 'Save'}
        </button>
        {st.rate > 0 && (
          <button className={BTN} data-testid="teaser-off" disabled={busy !== ''} onClick={turnOff}>
            {busy === 'off' ? '...' : 'Turn off'}
          </button>
        )}
        {dirty && (
          <button className={BTN} disabled={busy !== ''} onClick={() => { setEdit(null); setErr('') }}>Undo</button>
        )}
      </div>

      {problem && <p className="text-[11px] text-amber-300 mt-1.5" data-testid="teaser-problem">{problem}</p>}
      {err && <p className="text-[11px] text-red-300 mt-1.5" data-testid="teaser-error">{err}</p>}
      {msg && <p className="text-[11px] text-emerald-300 mt-1.5" data-testid="teaser-msg">{msg}</p>}

      <div className="mt-2.5 space-y-0.5 text-[11px] text-pb-dim" data-testid="teaser-progress">
        <p>
          <span className="text-pb-text font-semibold">{num(p.with_snapshot)}</span> of {num(p.targets)} clubs pulled
          {' · '}<span className="text-pb-text font-semibold">{num(p.due)}</span> due
          {' · '}{num(p.ok)} ok, {num(p.empty)} empty, {num(p.junior_only)} junior only, {num(p.error)} errors
        </p>
        <p data-testid="teaser-last-retrieved">
          Last club retrieved:{' '}
          {p.last_retrieved_at
            ? <><span className="text-pb-text font-semibold">{perthWhen(p.last_retrieved_at)}</span> Perth ({agoText(p.last_retrieved_at)})</>
            : 'none yet'}
          {p.next_due_at && p.due === 0 ? <> · next club due <span className="text-pb-text font-semibold">{perthWhen(p.next_due_at)}</span> Perth</> : null}
        </p>
        <p data-testid="teaser-worker">
          {st.worker?.last_cycle_at
            ? <>Crawler last looked for work {agoText(st.worker.last_cycle_at)} ({WORKER_SAID[st.worker.last_status] || st.worker.last_status}).</>
            : 'The crawler has not reported since the server last restarted.'}
        </p>
        <p>
          Last hour: {num(p.clubs_last_hour)} clubs, {num(p.calls_last_hour)} calls
          {achieved ? ` (${achieved} a second on average)` : ''}
          {p.avg_calls ? ` · ${p.avg_calls} calls a club on average` : ''}
        </p>
        {est ? (
          <p data-testid="teaser-estimate">
            The {num(p.due)} still due is about {num(est.calls)} calls: roughly {est.hours} hours at {st.rate} a second
            ({est.days} of a {est.window_hours} hour window).
            {' '}{est.rate_to_finish_in_one_window} a second would finish it inside one window.
          </p>
        ) : (st.rate > 0 && p.due > 0 ? <p>No estimate until at least one club has been pulled.</p> : null)}
        {img && (
          <div className="flex flex-wrap items-center gap-2 pt-1" data-testid="teaser-images">
            <p>
              Pictures for emails and ads: <span className="text-pb-text font-semibold" data-testid="teaser-images-ready">{num(img.ready)}</span> drawn
              {' · '}<span className="text-pb-text font-semibold" data-testid="teaser-images-pending">{num(img.pending)}</span> waiting
              {img.stale > 0 ? ` (${num(img.stale)} out of date)` : ''}
              {img.running ? ' · drawing now' : ''}
            </p>
            <button className={BTN} data-testid="teaser-draw"
                    disabled={busy !== '' || img.running || img.pending === 0} onClick={draw}>
              {busy === 'draw' ? '...' : (img.pending > 0 ? `Draw ${Math.min(img.pending, RENDER_BATCH)} pictures` : 'Draw pictures')}
            </button>
          </div>
        )}
        {img?.last && img.last.status === 'error' && (
          <p className="text-red-300" data-testid="teaser-images-error">
            The last batch could not run: {img.last.error || 'unknown error'}.
          </p>
        )}
        {img?.last && img.last.status === 'ok' && img.last.failed > 0 && (
          <p className="text-amber-300" data-testid="teaser-images-failed">
            {num(img.last.failed)} club{img.last.failed === 1 ? '' : 's'} could not be drawn in the last batch
            (usually a very long name that does not fit the card). They stay waiting.
          </p>
        )}
        {p.empty > 0 && p.with_snapshot > 0 && p.empty / p.with_snapshot > 0.2 && (
          <p className="text-amber-300" data-testid="teaser-empty-warn">
            A lot of clubs read as empty. If Cricket Australia is having trouble, that can look like empty clubs
            rather than errors. Press Stop crawling above and check before letting it carry on.
          </p>
        )}
      </div>
    </div>
  )
}
