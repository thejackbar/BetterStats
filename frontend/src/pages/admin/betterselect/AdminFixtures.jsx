import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Btn, Field, Input, Select } from '../../../lib/presskit'

const EMPTY = {
  label: '', opponent_name: '', home_away: 'HOME', team_id: '',
  played_on: '', end_on: '', start_time: '', venue: '', round: '', notes: '',
}

function FixtureModal({ fixture, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({ ...EMPTY, ...(fixture || {}), team_id: fixture?.team_id || '' }))
  const [saving, setSaving] = useState(false)
  const [teams, setTeams] = useState([])
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  useEffect(() => {
    api.bsListTeams().then(setTeams).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const payload = {
        label: form.label || null,
        opponent_name: form.opponent_name || null,
        home_away: form.home_away || null,
        team_id: form.team_id || null,
        played_on: form.played_on || null,
        end_on: form.end_on || null,
        start_time: form.start_time || null,
        venue: form.venue || null,
        round: form.round || null,
        notes: form.notes || null,
      }
      const saved = fixture
        ? await api.bsUpdateFixture(fixture.id, payload)
        : await api.bsCreateFixture(payload)
      toast.success(fixture ? 'Fixture updated' : 'Fixture added')
      onSaved(saved)
    } catch (e) {
      toast.error('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4" style={{ backdropFilter: 'blur(2px)' }}>
      <div className="bg-pb-surface pb-card max-w-lg w-full mt-12 mb-8 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline">
          <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">{fixture ? 'Edit fixture' : 'New manual fixture'}</h3>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text">✕</button>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Label (optional)"><Input value={form.label} onChange={set('label')} placeholder="e.g. Pre-season friendly" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Opponent"><Input value={form.opponent_name} onChange={set('opponent_name')} placeholder="Opposition club" /></Field>
            <Field label="Home / Away">
              <Select value={form.home_away} onChange={set('home_away')}>
                <option value="HOME">Home</option>
                <option value="AWAY">Away</option>
                <option value="BYE">Bye</option>
              </Select>
            </Field>
          </div>
          <Field label="Our team">
            <Select value={form.team_id || ''} onChange={set('team_id')}>
              <option value="">— No team assigned —</option>
              {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date"><Input type="date" value={form.played_on || ''} onChange={set('played_on')} /></Field>
            <Field label="End date (2-day, optional)"><Input type="date" value={form.end_on || ''} onChange={set('end_on')} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Start time"><Input value={form.start_time || ''} onChange={set('start_time')} placeholder="e.g. 13:00" /></Field>
            <Field label="Round"><Input value={form.round || ''} onChange={set('round')} placeholder="e.g. R6" /></Field>
          </div>
          <Field label="Venue"><Input value={form.venue || ''} onChange={set('venue')} /></Field>
          <Field label="Notes"><Input value={form.notes || ''} onChange={set('notes')} /></Field>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t pb-hairline">
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn primary onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>
        </div>
      </div>
    </div>
  )
}

function fmtDate(d) {
  if (!d) return '—'
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d }
}

// Week helpers — weeks run Monday→Sunday so Sat/Sun fixtures stay together.
function mondayOf(date) {
  const x = new Date(date); x.setHours(0, 0, 0, 0)
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7))
  return x
}
function addDays(date, n) { const x = new Date(date); x.setDate(x.getDate() + n); return x }
function isoLocal(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function weekLabel(start) {
  const end = addDays(start, 6)
  const opts = { day: 'numeric', month: 'short' }
  return `${start.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, opts)}`
}

export default function AdminFixtures() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canManage = hasCapability(CAP.MANAGE_FIXTURES)
  const [fixtures, setFixtures] = useState(null)
  const [view, setView] = useState('week') // 'upcoming' | 'week' | 'all' — default to this week
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()))
  const [editing, setEditing] = useState(undefined) // undefined=closed, null=new, obj=edit
  const [syncing, setSyncing] = useState(false)

  // 'upcoming' fetches only future; 'week'/'all' need the full set (week can be in the past).
  const load = useCallback(() => {
    setFixtures(null)
    api.bsListFixtures(view === 'upcoming').then(setFixtures).catch(e => { toast.error(e.message); setFixtures([]) })
  }, [view, toast])

  useEffect(() => { load() }, [load])

  // Fixtures actually shown — narrowed to the selected week when in week view.
  const displayed = useMemo(() => {
    if (!fixtures) return fixtures
    if (view !== 'week') return fixtures
    const lo = isoLocal(weekStart), hi = isoLocal(addDays(weekStart, 6))
    return fixtures.filter(f => f.played_on && f.played_on >= lo && f.played_on <= hi)
  }, [fixtures, view, weekStart])

  const thisWeek = isoLocal(weekStart) === isoLocal(mondayOf(new Date()))

  const sync = async () => {
    setSyncing(true)
    try {
      const r = await api.bsSyncFixtures()
      toast.success(r.detail || `Synced ${r.synced} fixtures`)
      load()
    } catch (e) { toast.error('Sync failed: ' + e.message) }
    finally { setSyncing(false) }
  }

  const del = async (f) => {
    if (!window.confirm(`Delete this fixture${f.opponent_name ? ' vs ' + f.opponent_name : ''}?`)) return
    try { await api.bsDeleteFixture(f.id); toast.success('Deleted'); load() }
    catch (e) { toast.error('Delete failed: ' + e.message) }
  }

  const actions = canManage && (
    <div className="flex gap-2">
      <Btn onClick={sync} disabled={syncing}>{syncing ? 'Syncing…' : '⟳ Sync PlayHQ'}</Btn>
      <Btn primary onClick={() => setEditing(null)}>+ Add fixture</Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Fixtures" actions={actions}>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Btn sm primary={view === 'week'} onClick={() => { setView('week'); setWeekStart(mondayOf(new Date())) }}>This week</Btn>
        <Btn sm primary={view === 'upcoming'} onClick={() => setView('upcoming')}>Upcoming</Btn>
        <Btn sm primary={view === 'all'} onClick={() => setView('all')}>All</Btn>

        {view === 'week' && (
          <div className="flex items-center gap-2 ml-auto">
            <Btn sm onClick={() => setWeekStart(s => addDays(s, -7))}>‹ Prev</Btn>
            <span className="font-mono text-xs text-pb-text min-w-[130px] text-center">
              {weekLabel(weekStart)}{thisWeek && <span className="text-pb-accent"> · this week</span>}
            </span>
            <Btn sm onClick={() => setWeekStart(s => addDays(s, 7))}>Next ›</Btn>
            {!thisWeek && <Btn sm onClick={() => setWeekStart(mondayOf(new Date()))}>Today</Btn>}
          </div>
        )}
      </div>

      {displayed === null ? <PbSpinner message="Loading fixtures…" /> : (
        <div className="pb-card overflow-hidden">
          {displayed.length === 0 && (
            <div className="px-5 py-10 text-center text-pb-faint text-sm">
              {view === 'week'
                ? `No fixtures for ${weekLabel(weekStart)}.`
                : <>No fixtures yet. {canManage && 'Sync from PlayHQ or add one manually.'}</>}
            </div>
          )}
          {displayed.map((f, i) => (
            <div key={f.id} className={`px-5 py-3 flex items-center justify-between gap-3 ${i > 0 ? 'border-t pb-hairline' : ''}`}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {f.team_name && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-text border pb-hairline" title="Our team">{f.team_short || f.team_name}</span>
                  )}
                  <span className="font-medium text-sm truncate">
                    {f.home_away === 'BYE' ? 'BYE' : `${f.home_away === 'AWAY' ? '@ ' : 'vs '}${f.opponent_name || f.label || 'TBC'}`}
                  </span>
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded ${f.source === 'playhq' ? 'bg-pb-accent/15 text-pb-accent' : 'bg-pb-surface2 text-pb-faint'}`}>
                    {f.source === 'playhq' ? 'PlayHQ' : 'Manual'}
                  </span>
                  {f.end_on && f.end_on !== f.played_on && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300">2-day</span>
                  )}
                  {f.lineup_count > 0 && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-pb-accent/15 text-pb-accent" title="Players selected">XI: {f.lineup_count}</span>
                  )}
                </div>
                <div className="text-pb-faint text-xs mt-0.5">
                  {fmtDate(f.played_on)}{f.end_on && f.end_on !== f.played_on ? ` → ${fmtDate(f.end_on)}` : ''}
                  {f.start_time ? ` · ${f.start_time}` : ''}{f.venue ? ` · ${f.venue}` : ''}{f.round ? ` · ${f.round}` : ''}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                {f.home_away !== 'BYE' && (
                  <Link to={`/admin/betterselect/select/${f.id}`}>
                    <Btn sm primary>Select</Btn>
                  </Link>
                )}
                {canManage && <>
                  <Btn sm onClick={() => setEditing(f)}>Edit</Btn>
                  <Btn sm danger onClick={() => del(f)}>Delete</Btn>
                </>}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing !== undefined && (
        <FixtureModal
          fixture={editing}
          onClose={() => setEditing(undefined)}
          onSaved={() => { setEditing(undefined); load() }}
        />
      )}
    </BetterSelectLayout>
  )
}
