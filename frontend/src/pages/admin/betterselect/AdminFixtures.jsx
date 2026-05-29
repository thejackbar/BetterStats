import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Btn, Field, Input, Select } from '../../../lib/presskit'

const EMPTY = {
  label: '', opponent_name: '', home_away: 'HOME',
  played_on: '', end_on: '', start_time: '', venue: '', round: '', notes: '',
}

function FixtureModal({ fixture, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({ ...EMPTY, ...(fixture || {}) }))
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const save = async () => {
    setSaving(true)
    try {
      const payload = {
        label: form.label || null,
        opponent_name: form.opponent_name || null,
        home_away: form.home_away || null,
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

export default function AdminFixtures() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canManage = hasCapability(CAP.MANAGE_FIXTURES)
  const [fixtures, setFixtures] = useState(null)
  const [upcomingOnly, setUpcomingOnly] = useState(true)
  const [editing, setEditing] = useState(undefined) // undefined=closed, null=new, obj=edit
  const [syncing, setSyncing] = useState(false)

  const load = useCallback(() => {
    setFixtures(null)
    api.bsListFixtures(upcomingOnly).then(setFixtures).catch(e => { toast.error(e.message); setFixtures([]) })
  }, [upcomingOnly, toast])

  useEffect(() => { load() }, [load])

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
      <div className="flex items-center gap-2 mb-4">
        <Btn sm primary={upcomingOnly} onClick={() => setUpcomingOnly(true)}>Upcoming</Btn>
        <Btn sm primary={!upcomingOnly} onClick={() => setUpcomingOnly(false)}>All</Btn>
      </div>

      {fixtures === null ? <PbSpinner message="Loading fixtures…" /> : (
        <div className="pb-card overflow-hidden">
          {fixtures.length === 0 && (
            <div className="px-5 py-10 text-center text-pb-faint text-sm">
              No fixtures yet. {canManage && 'Sync from PlayHQ or add one manually.'}
            </div>
          )}
          {fixtures.map((f, i) => (
            <div key={f.id} className={`px-5 py-3 flex items-center justify-between gap-3 ${i > 0 ? 'border-t pb-hairline' : ''}`}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">
                    {f.home_away === 'BYE' ? 'BYE' : `${f.home_away === 'AWAY' ? '@ ' : 'vs '}${f.opponent_name || f.label || 'TBC'}`}
                  </span>
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded ${f.source === 'playhq' ? 'bg-pb-accent/15 text-pb-accent' : 'bg-pb-surface2 text-pb-faint'}`}>
                    {f.source === 'playhq' ? 'PlayHQ' : 'Manual'}
                  </span>
                  {f.end_on && f.end_on !== f.played_on && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300">2-day</span>
                  )}
                </div>
                <div className="text-pb-faint text-xs mt-0.5">
                  {fmtDate(f.played_on)}{f.end_on && f.end_on !== f.played_on ? ` → ${fmtDate(f.end_on)}` : ''}
                  {f.start_time ? ` · ${f.start_time}` : ''}{f.venue ? ` · ${f.venue}` : ''}{f.round ? ` · ${f.round}` : ''}
                </div>
              </div>
              {canManage && (
                <div className="flex gap-2 shrink-0">
                  <Btn sm onClick={() => setEditing(f)}>Edit</Btn>
                  <Btn sm danger onClick={() => del(f)}>Delete</Btn>
                </div>
              )}
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
