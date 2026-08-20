// BetterSelect → Net Manager (overview). Three quiet tabs over the durable side
// of the feature: the list of net sessions (each opens the live runner), the
// per-player attendance report ("who turns up most"), and the club's default
// timer/rotation settings new sessions seed from. The pitch-side batting queue
// + timer lives in NetSession.jsx.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Icon, Btn, Segmented, Avatar, Empty, RoleChips } from './ui'

const NET_URL = '/admin/betterselect/nets/'

function fmtDate(d) {
  if (!d) return ''
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}
function fmtClock(total) {
  const s = Math.max(0, Math.round(total))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

/* ── Sessions tab ─────────────────────────────────────────────────────────── */
function SessionsTab({ canEdit, onOpen }) {
  const toast = useToast()
  const [sessions, setSessions] = useState(null)
  const [label, setLabel] = useState('')
  const [sdate, setSdate] = useState(() => new Date().toISOString().slice(0, 10))
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.nmListSessions().then((r) => setSessions(r.sessions || [])).catch((e) => { toast.error(e.message); setSessions([]) })
  }, [toast])
  useEffect(() => { load() }, [load])

  const start = async () => {
    setBusy(true)
    try {
      const s = await api.nmCreateSession({ session_date: sdate, label: label.trim() || null })
      onOpen(s.id)
    } catch (e) { toast.error(e.message); setBusy(false) }
  }
  const remove = async (id, e) => {
    e.stopPropagation()
    if (!confirm('Delete this net session and its attendance?')) return
    try { await api.nmDeleteSession(id); load() } catch (err) { toast.error(err.message) }
  }

  if (sessions === null) return <PbSpinner message="Loading sessions…" />

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <div className="pb-card px-4 py-3.5 flex flex-wrap items-end gap-3">
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1">Date</label>
            <input type="date" value={sdate} onChange={(e) => setSdate(e.target.value)}
              className="bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-sm text-pb-text focus:outline-none focus:border-pb-accent" />
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1">Label (optional)</label>
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Tuesday senior nets"
              className="w-full bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-sm text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-pb-accent" />
          </div>
          <Btn variant="primary" icon="play" onClick={start} disabled={busy}>{busy ? 'Starting…' : 'Start a session'}</Btn>
        </div>
      )}

      <div className="pb-card divide-y divide-pb-hairline">
        {sessions.length === 0
          ? <Empty className="px-4 py-10 text-center">No net sessions yet. Start one above to begin checking players in.</Empty>
          : sessions.map((s) => (
            // A div rather than a button: the row now holds a download link,
            // and a link inside a button is markup no browser agrees on.
            <div key={s.id} role="button" tabIndex={0} onClick={() => onOpen(s.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(s.id) } }}
              className="w-full flex items-center gap-3 px-4 py-3 text-left cursor-pointer hover:bg-pb-surface2/50 transition-colors">
              <span className="w-9 h-9 rounded-lg bg-pb-accent/12 text-pb-accent flex items-center justify-center shrink-0"><Icon name="nets" size={18} /></span>
              <div className="flex-1 min-w-0">
                <div className="font-display font-semibold text-[14.5px] truncate">{s.label || 'Net session'}</div>
                <div className="text-[12px] text-pb-faint">{fmtDate(s.session_date)}</div>
              </div>
              <div className="text-right shrink-0">
                <div className="font-display font-bold text-[15px] pb-num">{s.attendee_count}</div>
                <div className="text-[10px] text-pb-faint">attended</div>
              </div>
              {s.batted_count > 0 && (
                <div className="text-right shrink-0 hidden sm:block">
                  <div className="font-display font-bold text-[15px] pb-num text-pb-accent">{s.batted_count}</div>
                  <div className="text-[10px] text-pb-faint">batted</div>
                </div>
              )}
              {s.attendee_count > 0 && (
                <a href={api.nmSessionCsvUrl(s.id)} onClick={(e) => e.stopPropagation()}
                  className="text-pb-faint hover:text-pb-accent p-1.5 rounded-md" title="Download who attended this session">
                  <Icon name="download" size={15} />
                </a>
              )}
              {canEdit && <span onClick={(e) => remove(s.id, e)} className="text-pb-faint hover:text-pb-red p-1.5 rounded-md" title="Delete session"><Icon name="trash" size={15} /></span>}
              <Icon name="chevron" size={15} className="text-pb-faint shrink-0" />
            </div>
          ))}
      </div>
    </div>
  )
}

/* ── Attendance report tab ──────────────────────────────────────────────────
 * Every player, the last night they were at nets and how many they have been
 * to. A tally opens into the dates behind it, so "12 sessions" can be checked
 * rather than taken on trust, and the whole thing downloads as a spreadsheet
 * for a coach or a selection meeting. */
const RANGES = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 180, label: '6 months' },
  { value: 365, label: '12 months' },
  { value: 0, label: 'All time' },
]
function ReportTab() {
  const toast = useToast()
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)
  const [openPlayer, setOpenPlayer] = useState(null)

  useEffect(() => {
    let alive = true
    setData(null)
    api.nmAttendanceReport(days).then((r) => { if (alive) setData(r) }).catch((e) => { toast.error(e.message); if (alive) setData({ players: [], session_count: 0 }) })
    return () => { alive = false }
  }, [days, toast])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <Segmented options={RANGES} value={days} onChange={setDays} sm />
        <div className="flex items-center gap-3">
          {data && <span className="text-[12.5px] text-pb-faint">{data.session_count} session{data.session_count === 1 ? '' : 's'} {days ? 'in range' : 'all time'}</span>}
          <Btn variant="ghost" sm icon="download" href={api.nmAttendanceReportCsvUrl(days)} disabled={!data || !data.players.length}>Download</Btn>
        </div>
      </div>
      {data === null ? <PbSpinner message="Loading report…" /> : data.players.length === 0 ? (
        <div className="pb-card"><Empty className="px-4 py-10 text-center">No attendance recorded in this window.</Empty></div>
      ) : (
        <div className="pb-card overflow-hidden">
          <div className="hidden sm:flex items-center gap-3 px-4 py-2.5 border-b pb-hairline font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">
            <span className="flex-1">Player</span>
            <span className="w-20 text-right">Attended</span>
            <span className="w-16 text-right">Batted</span>
            <span className="w-24 text-right">Rate</span>
            <span className="w-28 text-right">Last seen</span>
          </div>
          {data.players.map((p, i) => (
            <div key={p.player_id} className="flex items-center gap-3 px-4 py-2.5 border-b pb-hairline last:border-0">
              <span className="font-mono text-[11px] text-pb-faintest w-5 shrink-0">{i + 1}</span>
              <Avatar player={{ ...p, id: p.player_id }} size={30} />
              <div className="flex-1 min-w-0">
                <div className="font-display font-semibold text-[13.5px] truncate">{p.name}</div>
                <button type="button" onClick={() => setOpenPlayer(p)}
                  className="sm:hidden text-[11px] text-pb-faint underline decoration-dotted underline-offset-2">{p.attended} attended · {p.attendance_pct}%</button>
              </div>
              <RoleChips roles={(p.skill_positions || []).slice(0, 2)} muted />
              <button type="button" onClick={() => setOpenPlayer(p)} title={`Every session ${p.name} has been to`}
                className="hidden sm:block w-20 text-right font-display font-bold pb-num hover:text-pb-accent transition-colors">{p.attended}</button>
              <span className="hidden sm:block w-16 text-right pb-num text-pb-dim">{p.batted}</span>
              <span className="hidden sm:flex w-24 items-center justify-end gap-2">
                <span className="h-1.5 w-10 rounded-full bg-pb-surface2 overflow-hidden"><span className="block h-full bg-pb-accent" style={{ width: `${p.attendance_pct}%` }} /></span>
                <span className="font-mono text-[11px] text-pb-faint w-8 text-right">{p.attendance_pct}%</span>
              </span>
              <span className="hidden sm:block w-28 text-right text-[11.5px] text-pb-faint">{p.last_attended ? fmtDate(p.last_attended).replace(/^\w+ /, '') : '—'}</span>
            </div>
          ))}
        </div>
      )}
      {openPlayer && <PlayerSessionsModal player={openPlayer} onClose={() => setOpenPlayer(null)} />}
    </div>
  )
}

/* ── Every session one player has been to ────────────────────────────────────
 * What the tally opens into. Reads the player's whole net history, not just
 * the window the report is showing — a coach clicking a number is asking about
 * the person, not about the last 90 days. */
function PlayerSessionsModal({ player, onClose }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let alive = true
    api.nmPlayerAttendance(player.player_id)
      .then((r) => { if (alive) setData(r) })
      .catch(() => { if (alive) setData({ sessions: [] }) })
    return () => { alive = false }
  }, [player.player_id])

  const sessions = (data && data.sessions) || []
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-full sm:w-[420px] max-h-[85vh] bg-pb-surface sm:rounded-2xl rounded-t-2xl border border-pb-hairline2 overflow-hidden shadow-2xl flex flex-col">
        <div className="flex items-center gap-3 px-4 py-3.5 border-b pb-hairline">
          <Avatar player={{ ...player, id: player.player_id }} size={34} noLink />
          <div className="flex-1 min-w-0">
            <div className="font-display font-bold text-[15px] truncate">{player.name}</div>
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Net sessions attended</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        {data === null ? <PbSpinner message="Loading sessions…" /> : sessions.length === 0 ? (
          <Empty className="px-4 py-8 text-center">No sessions recorded.</Empty>
        ) : (
          <>
            <div className="px-4 py-2.5 border-b pb-hairline flex items-center gap-4 text-[12.5px] text-pb-faint">
              <span><b className="pb-num font-display font-bold text-pb-text">{data.attended}</b> attended</span>
              <span><b className="pb-num font-display font-bold text-pb-accent">{data.batted}</b> batted</span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {sessions.map((sess) => (
                <div key={sess.session_id} className="flex items-center gap-3 px-4 py-2.5 border-b pb-hairline last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] text-pb-text">{fmtDate(sess.session_date)}</div>
                    {sess.label && <div className="text-[11.5px] text-pb-faint truncate">{sess.label}</div>}
                  </div>
                  {sess.batted
                    ? <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-accent">Batted</span>
                    : <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">Attended</span>}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ── Settings tab ─────────────────────────────────────────────────────────── */
const TONES = [{ value: 'info', label: 'Notify' }, { value: 'amber', label: 'Warn' }, { value: 'red', label: 'Final' }]
function SettingsTab({ canEdit }) {
  const toast = useToast()
  const [s, setS] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => { api.nmGetSettings().then((r) => setS(r.settings)).catch((e) => toast.error(e.message)) }, [toast])

  const patch = (k, v) => setS((cur) => ({ ...cur, [k]: v }))
  const patchAlert = (i, k, v) => setS((cur) => ({ ...cur, alerts: cur.alerts.map((a, j) => j === i ? { ...a, [k]: v } : a) }))
  const addAlert = () => setS((cur) => ({ ...cur, alerts: [...(cur.alerts || []), { seconds_remaining: 60, label: 'Alert', tone: 'info' }] }))
  const removeAlert = (i) => setS((cur) => ({ ...cur, alerts: cur.alerts.filter((_, j) => j !== i) }))

  const save = async () => {
    setSaving(true)
    try {
      const r = await api.nmSetSettings(s)
      setS(r.settings)
      toast.success('Settings saved')
    } catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  if (!s) return <PbSpinner message="Loading settings…" />
  const mins = Math.floor(s.duration_seconds / 60)
  const secs = s.duration_seconds % 60

  return (
    <div className="flex flex-col gap-4 max-w-[640px]">
      <div className="pb-card px-5 py-4 flex flex-col gap-4">
        <div className="font-display font-bold text-[15px]">Batting turn</div>
        <div className="flex flex-wrap items-end gap-5">
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1.5">Length</label>
            <div className="flex items-center gap-1.5">
              <input type="number" min="0" max="120" value={mins} disabled={!canEdit}
                onChange={(e) => patch('duration_seconds', Math.max(30, (Number(e.target.value) || 0) * 60 + secs))}
                className="w-16 bg-pb-surface2 border border-pb-hairline rounded-lg px-2.5 h-[38px] text-sm text-pb-text text-center focus:outline-none focus:border-pb-accent" />
              <span className="text-pb-faint text-sm">min</span>
              <input type="number" min="0" max="59" value={secs} disabled={!canEdit}
                onChange={(e) => patch('duration_seconds', Math.max(30, mins * 60 + (Number(e.target.value) || 0)))}
                className="w-16 bg-pb-surface2 border border-pb-hairline rounded-lg px-2.5 h-[38px] text-sm text-pb-text text-center focus:outline-none focus:border-pb-accent" />
              <span className="text-pb-faint text-sm">sec</span>
            </div>
          </div>
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1.5">Nets / batters at once</label>
            <input type="number" min="1" max="8" value={s.nets} disabled={!canEdit}
              onChange={(e) => patch('nets', Math.max(1, Math.min(8, Number(e.target.value) || 1)))}
              className="w-16 bg-pb-surface2 border border-pb-hairline rounded-lg px-2.5 h-[38px] text-sm text-pb-text text-center focus:outline-none focus:border-pb-accent" />
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-6">
          <ToggleRow label="Auto-roll into next group" hint="When the turn ends, rotate and restart automatically" on={s.auto_roll} disabled={!canEdit} onChange={(v) => patch('auto_roll', v)} />
          <ToggleRow label="Sound on alerts" hint="Play a beep at each alert point" on={s.sound} disabled={!canEdit} onChange={(v) => patch('sound', v)} />
        </div>
      </div>

      <div className="pb-card px-5 py-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="font-display font-bold text-[15px]">Alerts</div>
          <span className="text-[12px] text-pb-faint">Time remaining when each fires</span>
        </div>
        {(s.alerts || []).map((a, i) => {
          const am = Math.floor(a.seconds_remaining / 60), as = a.seconds_remaining % 60
          return (
            <div key={i} className="flex flex-wrap items-center gap-2 py-1.5 border-b pb-hairline last:border-0">
              <div className="flex items-center gap-1">
                <input type="number" min="0" max="120" value={am} disabled={!canEdit}
                  onChange={(e) => patchAlert(i, 'seconds_remaining', (Number(e.target.value) || 0) * 60 + as)}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-[34px] text-sm text-center focus:outline-none focus:border-pb-accent" />
                <span className="text-pb-faint text-xs">:</span>
                <input type="number" min="0" max="59" value={String(as).padStart(2, '0')} disabled={!canEdit}
                  onChange={(e) => patchAlert(i, 'seconds_remaining', am * 60 + (Number(e.target.value) || 0))}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-[34px] text-sm text-center focus:outline-none focus:border-pb-accent" />
              </div>
              <input value={a.label} disabled={!canEdit} onChange={(e) => patchAlert(i, 'label', e.target.value)} placeholder="Alert message"
                className="flex-1 min-w-[140px] bg-pb-surface2 border border-pb-hairline rounded px-2.5 h-[34px] text-sm focus:outline-none focus:border-pb-accent" />
              <Segmented options={TONES} value={a.tone} onChange={(v) => canEdit && patchAlert(i, 'tone', v)} sm />
              {canEdit && <button onClick={() => removeAlert(i)} className="text-pb-faint hover:text-pb-red p-1" title="Remove"><Icon name="close" size={15} /></button>}
            </div>
          )
        })}
        {canEdit && (s.alerts || []).length < 6 && <Btn variant="ghost" sm icon="plus" onClick={addAlert} className="self-start">Add alert</Btn>}
      </div>

      {canEdit && (
        <div className="flex items-center gap-3">
          <Btn variant="primary" icon="check" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save settings'}</Btn>
          <span className="text-[12px] text-pb-faint">New sessions start from these defaults — you can tweak any session live.</span>
        </div>
      )}
    </div>
  )
}

function ToggleRow({ label, hint, on, onChange, disabled }) {
  return (
    <button type="button" disabled={disabled} onClick={() => onChange(!on)} className="flex items-start gap-2.5 text-left disabled:opacity-60">
      <span className={`mt-0.5 w-9 h-5 rounded-full shrink-0 transition-colors relative ${on ? 'bg-pb-accent' : 'bg-pb-surface2 border border-pb-hairline2'}`}>
        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
      </span>
      <span>
        <span className="block text-[13.5px] font-medium text-pb-text leading-tight">{label}</span>
        {hint && <span className="block text-[11.5px] text-pb-faint mt-0.5">{hint}</span>}
      </span>
    </button>
  )
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
const TABS = [
  { value: 'sessions', label: 'Sessions' },
  { value: 'report', label: 'Attendance' },
  { value: 'settings', label: 'Settings' },
]
export default function Nets() {
  const { hasCapability } = useAuth()
  const navigate = useNavigate()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const [tab, setTab] = useState('sessions')

  return (
    <BetterSelectLayout title="Net Manager" actions={<Segmented options={TABS} value={tab} onChange={setTab} sm />}>
      {tab === 'sessions' && <SessionsTab canEdit={canEdit} onOpen={(id) => navigate(NET_URL + id)} />}
      {tab === 'report' && <ReportTab />}
      {tab === 'settings' && <SettingsTab canEdit={canEdit} />}
    </BetterSelectLayout>
  )
}
