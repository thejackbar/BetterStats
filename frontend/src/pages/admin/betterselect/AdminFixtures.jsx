// BetterSelect → Fixtures. The whole club's weekend, grouped by round (design
// handoff bs-app.jsx FixturesScreen): each weekend is a card with a row per
// team's fixture, colour-coded by team, with a Pick/Select action. A grade
// filter narrows to one team. Manual add / PlayHQ sync / edit / delete are
// preserved from the previous screen.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Field, Input, Select } from '../../../lib/presskit'
import { Icon, Btn, Segmented, Empty } from './ui'

// Home/Away accent for the left edge of each row — fixed semantic colours
// (green = home, red = away), NOT the club's white-label accent.
function homeAwayColor(ha) {
  if (ha === 'HOME') return 'var(--pb-positive)'
  if (ha === 'AWAY') return 'var(--pb-red)'
  return 'var(--pb-faintest)' // BYE / unknown
}

const EMPTY = {
  label: '', opponent_name: '', home_away: 'HOME', team_id: '',
  played_on: '', end_on: '', start_time: '', venue: '', round: '', notes: '',
}

function FixtureModal({ fixture, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({ ...EMPTY, ...(fixture || {}), team_id: fixture?.team_id || '' }))
  const [saving, setSaving] = useState(false)
  const [teams, setTeams] = useState([])
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  useEffect(() => { api.bsListTeams().then(setTeams).catch(() => {}) }, [])

  const save = async () => {
    setSaving(true)
    try {
      const payload = {
        label: form.label || null, opponent_name: form.opponent_name || null,
        home_away: form.home_away || null, team_id: form.team_id || null,
        played_on: form.played_on || null, end_on: form.end_on || null,
        start_time: form.start_time || null, venue: form.venue || null,
        round: form.round || null, notes: form.notes || null,
      }
      const saved = fixture ? await api.bsUpdateFixture(fixture.id, payload) : await api.bsCreateFixture(payload)
      toast.success(fixture ? 'Fixture updated' : 'Fixture added')
      onSaved(saved)
    } catch (e) { toast.error('Save failed: ' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="bg-pb-surface pb-card max-w-lg w-full mt-12 mb-8 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline">
          <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">{fixture ? 'Edit fixture' : 'New manual fixture'}</h3>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text"><Icon name="close" size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Label (optional)"><Input value={form.label} onChange={set('label')} placeholder="e.g. Pre-season friendly" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Opponent"><Input value={form.opponent_name} onChange={set('opponent_name')} placeholder="Opposition club" /></Field>
            <Field label="Home / Away">
              <Select value={form.home_away} onChange={set('home_away')}>
                <option value="HOME">Home</option><option value="AWAY">Away</option><option value="BYE">Bye</option>
              </Select>
            </Field>
          </div>
          <Field label="Our team">
            <Select value={form.team_id || ''} onChange={set('team_id')}>
              <option value="">— No team assigned —</option>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
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
          <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" sm onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>
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
function mondayOf(date) { const x = new Date(date); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
function isoLocal(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }

export default function AdminFixtures() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const canManage = hasCapability(CAP.MANAGE_FIXTURES)
  const canSelect = hasCapability(CAP.MANAGE_SELECTIONS)
  const [fixtures, setFixtures] = useState(null)
  const [scope, setScope] = useState('upcoming') // 'upcoming' | 'past' | 'all'
  const [teamFilter, setTeamFilter] = useState('all')
  const [editing, setEditing] = useState(undefined)
  const [syncing, setSyncing] = useState(false)

  // Always fetch the full set; scope (upcoming/past/all) is a client-side cut so
  // switching tabs is instant and "past" needs no extra endpoint.
  const load = useCallback(() => {
    setFixtures(null)
    api.bsListFixtures(false).then(setFixtures).catch((e) => { toast.error(e.message); setFixtures([]) })
  }, [toast])
  useEffect(() => { load() }, [load])

  const teamOptions = useMemo(() => {
    const seen = new Map()
    ;(fixtures || []).forEach((f) => { if (f.team_name && !seen.has(f.team_name)) seen.set(f.team_name, f.team_sequence ?? 99) })
    const sorted = [...seen.entries()].sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))
    return [{ value: 'all', label: 'Whole club' }, ...sorted.map(([name]) => ({ value: name, label: name }))]
  }, [fixtures])

  // Group by weekend (Monday-anchored). Scope cuts to upcoming/past/all; past
  // shows most-recent first, upcoming/all soonest first.
  const groups = useMemo(() => {
    if (!fixtures) return null
    const todayIso = isoLocal(new Date())
    let filtered = teamFilter === 'all' ? fixtures : fixtures.filter((f) => f.team_name === teamFilter)
    if (scope === 'upcoming') filtered = filtered.filter((f) => !f.played_on || f.played_on >= todayIso)
    else if (scope === 'past') filtered = filtered.filter((f) => f.played_on && f.played_on < todayIso)
    const byWeek = new Map()
    filtered.forEach((f) => {
      const key = f.played_on ? isoLocal(mondayOf(new Date(f.played_on + 'T00:00:00'))) : 'undated'
      if (!byWeek.has(key)) byWeek.set(key, [])
      byWeek.get(key).push(f)
    })
    const thisMon = isoLocal(mondayOf(new Date()))
    const desc = scope === 'past'
    return [...byWeek.entries()]
      .sort((a, b) => {
        if (a[0] === 'undated') return 1
        if (b[0] === 'undated') return -1
        return desc ? b[0].localeCompare(a[0]) : a[0].localeCompare(b[0])
      })
      .map(([week, list]) => ({
        week,
        current: week === thisMon,
        games: list.slice().sort((a, b) =>
          (a.team_sequence ?? 99) - (b.team_sequence ?? 99)
          || (a.start_time || '').localeCompare(b.start_time || '')),
      }))
  }, [fixtures, teamFilter, scope])

  const sync = async () => {
    setSyncing(true)
    try { const r = await api.bsSyncFixtures(); toast.success(r.detail || `Synced ${r.synced} fixtures`); load() }
    catch (e) { toast.error('Sync failed: ' + e.message) }
    finally { setSyncing(false) }
  }
  const del = async (f) => {
    if (!window.confirm(`Delete this fixture${f.opponent_name ? ' vs ' + f.opponent_name : ''}?`)) return
    try { await api.bsDeleteFixture(f.id); toast.success('Deleted'); load() }
    catch (e) { toast.error('Delete failed: ' + e.message) }
  }

  const actions = (
    <div className="flex gap-2">
      {canManage && <Btn variant="ghost" sm icon="fixtures" onClick={() => setEditing(null)}>Add fixture</Btn>}
      {canManage && <Btn variant="soft" sm icon="bolt" onClick={sync} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync'}</Btn>}
    </div>
  )

  return (
    <BetterSelectLayout title="Fixtures" actions={actions}>
      <div className="flex flex-wrap items-center gap-3 mb-2">
        <Segmented value={teamFilter} onChange={setTeamFilter} options={teamOptions} />
        <div className="ml-auto flex items-center gap-2">
          <Segmented value={scope} onChange={setScope} sm options={[
            { value: 'upcoming', label: 'Upcoming' },
            { value: 'past', label: 'Past' },
            { value: 'all', label: 'All' },
          ]} />
        </div>
      </div>
      <div className="flex items-center gap-4 mb-4 font-mono text-[10px] text-pb-faint">
        <span className="inline-flex items-center gap-1.5"><span className="w-[3px] h-3 rounded-sm" style={{ background: 'var(--pb-positive)' }} /> Home</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-[3px] h-3 rounded-sm" style={{ background: 'var(--pb-red)' }} /> Away</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: 'color-mix(in srgb, var(--pb-positive) 25%, transparent)' }} /> XI named</span>
      </div>

      {groups === null ? <PbSpinner message="Loading fixtures…" /> : (
        groups.length === 0 ? (
          <div className="pb-card px-5 py-12 text-center">
            <Empty className="mb-4">{scope === 'upcoming' ? 'No upcoming fixtures.' : scope === 'past' ? 'No past fixtures.' : 'No fixtures yet.'}{canManage && scope !== 'past' && ' Sync from PlayHQ or add one manually.'}</Empty>
            {canManage && (
              <div className="flex gap-2 justify-center">
                <Btn variant="soft" sm icon="bolt" onClick={sync} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync PlayHQ'}</Btn>
                <Btn variant="primary" sm icon="fixtures" onClick={() => setEditing(null)}>Add fixture</Btn>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3.5">
            {groups.map(({ week, current, games }) => {
              const playable = games.filter((g) => g.home_away !== 'BYE')
              return (
                <div key={week} className="pb-card overflow-hidden" style={{ borderColor: current ? 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' : undefined }}>
                  <div className="flex items-center gap-3 px-[18px] py-3 border-b pb-hairline" style={{ background: current ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : 'var(--pb-surface2)' }}>
                    <span className="font-display font-bold text-[16px]">{week === 'undated' ? 'Undated' : fmtDate(games[0]?.played_on)}</span>
                    {games[0]?.round && <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Round {games[0].round}</span>}
                    {current && <span className="font-mono text-[9.5px] text-pb-accent bg-pb-accent/12 px-2 py-0.5 rounded-full">THIS WEEKEND</span>}
                    <span className="ml-auto font-mono text-[11px] text-pb-faint">{playable.length} game{playable.length === 1 ? '' : 's'}</span>
                  </div>
                  {games.map((g, gi) => {
                    const bye = g.home_away === 'BYE'
                    const named = (g.lineup_count || 0) > 0
                    const isCurrentTop = current && (g.team_sequence ?? 99) <= 1
                    return (
                      <div key={g.id}
                        className={`relative flex items-center gap-4 pl-[22px] pr-[18px] py-3 ${gi > 0 ? 'border-t pb-hairline' : ''}`}
                        style={{ background: named ? 'color-mix(in srgb, var(--pb-positive) 6%, transparent)' : 'transparent' }}>
                        {/* Home/away accent bar on the far left */}
                        <span className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: homeAwayColor(g.home_away) }}
                          title={g.home_away === 'HOME' ? 'Home' : g.home_away === 'AWAY' ? 'Away' : 'Bye'} />
                        <span className="font-display font-bold text-[13.5px] w-[64px] shrink-0 truncate text-pb-text">{g.team_short || g.team_name || '—'}</span>
                        {g.grade_name && <span className="font-mono text-[10px] text-pb-faint w-[60px] shrink-0 truncate">{g.grade_name}</span>}
                        <span className="w-px h-6 bg-pb-hairline shrink-0" />
                        <div className="flex-1 min-w-0">
                          {bye ? <span className="text-sm text-pb-faint italic">Bye</span> : (
                            <>
                              <span className="text-[14.5px] font-medium"><span className="text-pb-faint font-normal">{g.home_away === 'AWAY' ? '@ ' : 'vs '}</span>{g.opponent_name || g.label || 'TBC'}</span>
                              <span className="text-[12.5px] text-pb-faint ml-2.5">
                                {g.venue ? `${g.venue} (${g.home_away === 'AWAY' ? 'A' : 'H'})` : ''}{g.start_time ? ` · ${g.start_time}` : ''}
                              </span>
                            </>
                          )}
                        </div>
                        {named && <span className="font-mono text-[9px] text-pb-positive bg-pb-positive/12 px-1.5 py-0.5 rounded shrink-0">XI named</span>}
                        {!bye && canSelect && (
                          <Btn variant={isCurrentTop ? 'primary' : 'ghost'} sm onClick={() => navigate(`/admin/betterselect/select/${g.id}`)}>
                            {isCurrentTop ? 'Pick team' : 'Select'}
                          </Btn>
                        )}
                        {canManage && (
                          <div className="flex gap-1 shrink-0">
                            <button onClick={() => setEditing(g)} title="Edit" className="text-pb-faintest hover:text-pb-text p-1"><Icon name="filter" size={14} /></button>
                            <button onClick={() => del(g)} title="Delete" className="text-pb-faintest hover:text-pb-red p-1"><Icon name="close" size={14} /></button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )
      )}

      {editing !== undefined && (
        <FixtureModal fixture={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load() }} />
      )}
    </BetterSelectLayout>
  )
}
