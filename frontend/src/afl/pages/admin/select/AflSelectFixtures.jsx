import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi } from '../../../aflApi'
import { useToast } from '../../../../contexts/ToastContext'
import LoadingSpinner from '../../../../components/LoadingSpinner'
import { Btn, Card, INPUT, PageHead, shortDate } from './ui'

// The draw, from PlayHQ. Every game the sync finds for one of our sides
// becomes a fixture on its own; a practice match or a trial game PlayHQ
// doesn't list is added here by hand. A PlayHQ fixture only takes a side and
// a finals answer — its date, time and ground come back on the next sync.

const BLANK = { label: '', opponent_name: '', played_on: '', start_time: '', venue: '', team_id: '', home_away: '' }

export default function AflSelectFixtures() {
  const toast = useToast()
  const [when, setWhen] = useState('upcoming')
  const [team, setTeam] = useState('')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState(BLANK)

  async function load() {
    setData(await aflApi.selFixtures({ when, team_id: team }))
  }
  useEffect(() => { load().catch(e => toast.error(e.message)) }, [when, team])

  async function sync() {
    setBusy(true)
    try {
      const r = await aflApi.selSyncFixtures()
      toast.success(r.created ? `${r.created} new fixture${r.created === 1 ? '' : 's'} from PlayHQ` : 'The draw is up to date')
      await load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function add(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
      await aflApi.selCreateFixture(body)
      setForm(BLANK)
      setAdding(false)
      await load()
    } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }

  async function patch(fx, body) {
    try { await aflApi.selUpdateFixture(fx.id, body); await load() } catch (e) { toast.error(e.message) }
  }

  if (!data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const byDate = {}
  for (const f of data.fixtures) (byDate[f.played_on || ''] ||= []).push(f)

  return (
    <div>
      <PageHead title="Fixtures"
        caption="Every game on PlayHQ's draw for your sides, updated each sync. Pick a side for any of them, or add a game PlayHQ doesn't list."
        right={<>
          <Btn onClick={sync} disabled={busy}>Update from PlayHQ</Btn>
          <Btn primary onClick={() => setAdding(v => !v)}>{adding ? 'Close' : 'Add a game'}</Btn>
        </>} />

      {adding && (
        <Card className="p-4 mb-4">
          <form onSubmit={add} className="grid gap-2 sm:grid-cols-3" data-testid="fixture-form">
            <input className={INPUT} placeholder="Opponent" value={form.opponent_name} onChange={e => setForm({ ...form, opponent_name: e.target.value })} />
            <input className={INPUT} placeholder="Or a name, e.g. Practice match" value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} />
            <select className={INPUT} value={form.team_id} onChange={e => setForm({ ...form, team_id: e.target.value })} aria-label="Side">
              <option value="">Which side?</option>
              {data.teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <input className={INPUT} type="date" aria-label="Date" value={form.played_on} onChange={e => setForm({ ...form, played_on: e.target.value })} />
            <input className={INPUT} type="time" aria-label="Time" value={form.start_time} onChange={e => setForm({ ...form, start_time: e.target.value })} />
            <input className={INPUT} placeholder="Ground" value={form.venue} onChange={e => setForm({ ...form, venue: e.target.value })} />
            <div className="sm:col-span-3 flex justify-end">
              <Btn type="submit" primary disabled={busy || !form.played_on || !(form.opponent_name || form.label)}>Add game</Btn>
            </div>
          </form>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        {['upcoming', 'past'].map(w => (
          <button key={w} onClick={() => setWhen(w)} aria-pressed={when === w}
            className={`px-3 py-1.5 text-sm rounded border ${when === w ? 'border-[var(--pb-accent)] text-[var(--pb-accent)]' : 'border-pb-hairline text-pb-dim'}`}>
            {w === 'upcoming' ? 'Coming up' : 'Played'}
          </button>
        ))}
        <select className={INPUT} value={team} onChange={e => setTeam(e.target.value)} aria-label="Filter by side">
          <option value="">Every side</option>
          {data.teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>

      {data.fixtures.length === 0 && (
        <Card className="p-6 text-sm text-pb-dim">
          {when === 'upcoming'
            ? 'No games coming up. Run a sync, or press Update from PlayHQ, to bring in the draw.'
            : 'No games played in the last few weeks.'}
        </Card>
      )}

      {Object.entries(byDate).map(([day, list]) => (
        <div key={day} className="mb-4">
          <h2 className="font-mono text-xs uppercase tracking-wide3 text-pb-faint mb-2">{day ? shortDate(day) : 'No date'}</h2>
          <Card>
            {list.map(f => (
              <div key={f.id} className="flex flex-wrap items-center gap-3 px-4 py-3 pb-hairline-b last:border-0" data-testid="fixture-row">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">
                    {f.team_name || f.grade_name || 'No side set'}
                    <span className="text-pb-dim font-normal"> {f.home_away === 'AWAY' ? '@' : 'v'} {f.opponent_name || f.label || 'TBC'}</span>
                  </div>
                  <div className="font-mono text-[11px] text-pb-faint mt-0.5">
                    {[f.round, f.start_time, f.venue, f.source === 'manual' ? 'Added here' : null].filter(Boolean).join(' · ')}
                  </div>
                </div>
                {!f.team_id && data.teams.length > 0 && (
                  <select className={`${INPUT} !py-1 !text-xs`} value="" aria-label="Set side"
                    onChange={e => patch(f, { team_id: e.target.value })}>
                    <option value="">Set side…</option>
                    {data.teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                )}
                <label className="flex items-center gap-1 text-xs text-pb-dim">
                  <input type="checkbox" checked={!!f.is_final} onChange={e => patch(f, { is_final: e.target.checked })} />
                  Final
                </label>
                <span className="font-mono text-[11px] text-pb-dim" data-testid="picked">{f.picked ? `${f.picked} named` : 'No side named'}</span>
                <Link to={`/admin/select/selection?fixture=${f.id}`}
                  className="text-sm px-3 py-1.5 rounded border border-[var(--pb-accent)] text-[var(--pb-accent)]">
                  {f.picked ? 'Edit side' : 'Pick side'}
                </Link>
                {f.source === 'manual' && (
                  <Btn small danger onClick={async () => {
                    if (!window.confirm('Delete this game and any side picked for it?')) return
                    try { await aflApi.selDeleteFixture(f.id); await load() } catch (e) { toast.error(e.message) }
                  }}>Delete</Btn>
                )}
              </div>
            ))}
          </Card>
        </div>
      ))}
    </div>
  )
}
