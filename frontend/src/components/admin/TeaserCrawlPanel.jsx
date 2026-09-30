import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'

// The club teaser crawl's rate and hours, with how far through the directory it
// is. It writes through the General Settings PATCH (the one place these two
// settings are validated) and reads back GET /marketing/teaser/status. The Stop
// switch above it on the Club Directory page also stops this crawl, so the panel
// says so rather than adding a second stop control that could disagree.

const POLL_MS = 15000

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

const INPUT = 'bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs text-pb-text w-20 focus:outline-none focus:border-pb-accent'
const BTN = 'px-3 py-1.5 rounded text-xs font-semibold border border-pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_ACCENT = 'px-3 py-1.5 rounded text-xs font-semibold bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 disabled:opacity-50'

const hh = (h) => `${String(h).padStart(2, '0')}:00`
const num = (n) => Number(n || 0).toLocaleString()

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

  useEffect(() => {
    load()
    const t = setInterval(() => { if (!document.hidden) load() }, POLL_MS)
    return () => clearInterval(t)
  }, [load])

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
