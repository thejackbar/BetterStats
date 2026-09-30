import { useEffect, useMemo, useState } from 'react'
import QRCode from 'qrcode'
import { aflApi } from '../../../aflApi'
import { useToast } from '../../../../contexts/ToastContext'
import LoadingSpinner from '../../../../components/LoadingSpinner'
import { AVAIL, Btn, Card, INPUT, PageHead, shortDate } from './ui'

// Who can play on each match date. One answer covers every game that day.
// A tap cycles a player's answer; an injury or a holiday is entered once as a
// period and covers every date inside it, with an answer for a single date
// still winning over it. Players can answer for themselves through the link.

const CYCLE = ['NO_RESPONSE', 'AVAILABLE', 'MAYBE', 'UNAVAILABLE']

function SelfServicePanel() {
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [qr, setQr] = useState(null)
  const base = `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, '')}`
  const url = cfg?.path ? `${base}${cfg.path}` : null

  useEffect(() => { aflApi.selSelfService().then(setCfg).catch(() => {}) }, [])
  useEffect(() => { if (url) QRCode.toDataURL(url, { margin: 1, width: 180 }).then(setQr).catch(() => setQr(null)) }, [url])

  async function set(body) {
    try { setCfg(await aflApi.selSetSelfService(body)) } catch (e) { toast.error(e.message) }
  }
  if (!cfg) return null
  return (
    <Card className="p-4 mb-5" data-testid="self-service">
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex-1 min-w-[16rem]">
          <h2 className="font-semibold text-sm">Players answer for themselves</h2>
          <p className="text-xs text-pb-dim mt-1">
            One link for the whole club, for the group chat or a QR code on the clubroom wall. A player picks their
            name and, if you keep the PIN on, types the last four digits of their mobile.
          </p>
          <div className="flex flex-wrap gap-2 mt-3">
            <Btn small primary={!cfg.enabled} onClick={() => set({ enabled: !cfg.enabled })}>{cfg.enabled ? 'Turn the link off' : 'Turn the link on'}</Btn>
            {cfg.enabled && <Btn small onClick={() => set({ require_pin: !cfg.require_pin })}>{cfg.require_pin ? 'Stop asking for a PIN' : 'Ask for a PIN'}</Btn>}
            {cfg.enabled && url && <Btn small onClick={() => navigator.clipboard?.writeText(url).then(() => toast.success('Link copied'))}>Copy link</Btn>}
            {cfg.enabled && <Btn small onClick={async () => {
              if (!window.confirm('Make a new link? The old one and its QR code stop working straight away.')) return
              try { setCfg(await aflApi.selRegenSelfService()) } catch (e) { toast.error(e.message) }
            }}>New link</Btn>}
          </div>
          {cfg.enabled && url && <div className="mt-3 font-mono text-[11px] break-all text-pb-dim" data-testid="self-link">{url}</div>}
          {cfg.enabled && cfg.require_pin && (
            <p className="text-xs text-pb-faint mt-2">
              {cfg.phone_coverage.with_phone} of {cfg.phone_coverage.total} current players have a mobile number on file.
              A player without one can't use the PIN; you answer for them here.
            </p>
          )}
        </div>
        {cfg.enabled && qr && <img src={qr} alt="QR code for the availability link" className="w-36 h-36 rounded bg-white p-1" />}
      </div>
    </Card>
  )
}

function Periods({ players, onChange }) {
  const toast = useToast()
  const [rows, setRows] = useState([])
  const [f, setF] = useState({ player_id: '', start_date: '', end_date: '', status: 'UNAVAILABLE', reason: '' })
  const names = useMemo(() => Object.fromEntries(players.map(p => [p.id, p.name])), [players])
  const load = () => aflApi.selPeriods().then(setRows).catch(() => {})
  useEffect(() => { load() }, [])

  async function add(e) {
    e.preventDefault()
    try {
      await aflApi.selCreatePeriod(Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')))
      setF({ ...f, player_id: '', start_date: '', end_date: '', reason: '' })
      await load(); onChange()
    } catch (err) { toast.error(err.message) }
  }
  return (
    <Card className="p-4 mt-5">
      <h2 className="font-semibold text-sm">Injuries and time away</h2>
      <p className="text-xs text-pb-dim mt-1 mb-3">Covers every match date in the range. Leave the end blank for "out until further notice".</p>
      <form onSubmit={add} className="grid gap-2 sm:grid-cols-6 mb-3">
        <select className={`${INPUT} sm:col-span-2`} value={f.player_id} onChange={e => setF({ ...f, player_id: e.target.value })} aria-label="Player">
          <option value="">Player…</option>
          {players.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input type="date" className={INPUT} aria-label="From" value={f.start_date} onChange={e => setF({ ...f, start_date: e.target.value })} />
        <input type="date" className={INPUT} aria-label="Until" value={f.end_date} onChange={e => setF({ ...f, end_date: e.target.value })} />
        <input className={INPUT} placeholder="Reason, e.g. Hamstring" value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} />
        <Btn type="submit" disabled={!f.player_id || !f.start_date}>Add</Btn>
      </form>
      {rows.length === 0 ? <p className="text-xs text-pb-faint">Nothing recorded.</p> : rows.map(r => (
        <div key={r.id} className="flex items-center gap-2 py-1 text-sm pb-hairline-b last:border-0">
          <span className="flex-1 min-w-0 truncate">{names[r.player_id] || 'Player'} · {AVAIL[r.status]?.label}{r.reason ? ` · ${r.reason}` : ''}</span>
          <span className="font-mono text-[11px] text-pb-faint">{shortDate(r.start_date)} – {r.end_date ? shortDate(r.end_date) : 'further notice'}</span>
          <Btn small danger onClick={async () => { await aflApi.selDeletePeriod(r.id); await load(); onChange() }}>Remove</Btn>
        </div>
      ))}
    </Card>
  )
}

export default function AflSelectAvailability() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [squad, setSquad] = useState('')
  const [q, setQ] = useState('')
  const [showLapsed, setShowLapsed] = useState(false)

  const load = () => aflApi.selAvailability().then(setData)
  useEffect(() => { load().catch(e => toast.error(e.message)) }, [])

  async function cycle(p, day) {
    const cur = data.availability[p.id]?.[day]?.status || 'NO_RESPONSE'
    const next = CYCLE[(CYCLE.indexOf(cur) + 1) % CYCLE.length]
    setData(d => ({ ...d, availability: { ...d.availability, [p.id]: { ...(d.availability[p.id] || {}), [day]: { status: next, source: 'admin' } } } }))
    try { await aflApi.selSetAvailability({ player_id: p.id, date: day, status: next }) }
    catch (e) { toast.error(e.message); load() }
  }

  if (!data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  const rows = data.players.filter(p => p.status !== 'inactive'
    && (showLapsed || !p.lapsed)
    && (!squad || (squad === 'none' ? !p.squad_id : p.squad_id === squad))
    && (!q || p.name.toLowerCase().includes(q.toLowerCase())))
  const teamName = Object.fromEntries(data.teams.map(t => [t.id, t.short_name || t.name]))

  return (
    <div>
      <PageHead title="Availability" caption="Who can play on each match date. Tap a box to change a player's answer." />
      <SelfServicePanel />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players" className={`${INPUT} w-56`} />
        <select className={INPUT} value={squad} onChange={e => setSquad(e.target.value)} aria-label="Squad">
          <option value="">Every squad</option>
          {data.teams.filter(t => t.is_active).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          <option value="none">Not in a squad</option>
        </select>
        <label className="flex items-center gap-1 text-xs text-pb-dim">
          <input type="checkbox" checked={showLapsed} onChange={e => setShowLapsed(e.target.checked)} />
          Include players who haven't played for {data.dormancy_months} months
        </label>
      </div>
      {data.dates.length === 0 ? (
        <Card className="p-6 text-sm text-pb-dim">No match dates coming up. The draw comes from PlayHQ with each sync, or add a game on Fixtures.</Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="text-sm min-w-full" data-testid="avail-matrix">
            <thead>
              <tr className="text-left">
                <th className="px-3 py-2 font-mono text-[10px] uppercase text-pb-faint sticky left-0 bg-pb-surface">Player</th>
                {data.dates.map(d => (
                  <th key={d.date} className="px-2 py-2 font-mono text-[10px] uppercase text-pb-faint whitespace-nowrap">
                    {shortDate(d.date)}
                    <div className="normal-case text-[10px] text-pb-faintest">{d.fixtures.length} game{d.fixtures.length === 1 ? '' : 's'}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(p => (
                <tr key={p.id} className="pb-hairline-t">
                  <td className="px-3 py-1.5 sticky left-0 bg-pb-surface whitespace-nowrap">
                    {p.name}
                    {p.squad_id && <span className="ml-2 font-mono text-[10px] text-pb-faint">{teamName[p.squad_id]}</span>}
                  </td>
                  {data.dates.map(d => {
                    const cell = data.availability[p.id]?.[d.date]
                    const a = AVAIL[cell?.status || 'NO_RESPONSE']
                    return (
                      <td key={d.date} className="px-2 py-1">
                        <button onClick={() => cycle(p, d.date)} data-testid="avail-cell"
                          title={`${a.label}${cell?.note ? ` · ${cell.note}` : ''}${cell?.source === 'period' ? ' (from a period)' : cell?.source === 'self' ? ' (the player answered)' : ''}`}
                          className="w-16 py-1 rounded border text-[11px] font-mono"
                          style={{ color: a.color, borderColor: `color-mix(in srgb, ${a.color} 40%, transparent)`,
                            borderStyle: cell?.source === 'period' ? 'dashed' : 'solid' }}>
                          {a.short}{cell?.source === 'self' ? ' •' : ''}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <Periods players={data.players.filter(p => p.status !== 'inactive')} onChange={load} />
    </div>
  )
}
