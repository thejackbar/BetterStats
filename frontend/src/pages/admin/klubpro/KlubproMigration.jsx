import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import AdminLayout from '../../../components/admin/AdminLayout'
import { PbSpinner, Card, Btn, TabBar, Label, Select } from '../../../lib/presskit'
import KlubproPlayers from './KlubproPlayers'
import KlubproSponsors from './KlubproSponsors'

const TABS = [
  { key: 'dashboard', label: 'DASHBOARD' },
  { key: 'players', label: 'PLAYERS' },
  { key: 'sponsors', label: 'SPONSORS' },
  { key: 'history', label: 'HISTORY' },
]

const num = n => Number(n || 0).toLocaleString()

export default function KlubproMigration() {
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [configured, setConfigured] = useState(true)
  const [dash, setDash] = useState(null)        // { summary, club_mappings }
  const [orgs, setOrgs] = useState([])          // all BetterStats organisations
  const [tab, setTab] = useState('dashboard')
  const [cmId, setCmId] = useState('')          // selected club_mapping id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const st = await api.kpStatus()
      setConfigured(st.configured)
      if (!st.configured) { setLoading(false); return }
      const [d, o] = await Promise.all([api.kpDashboard(), api.kpOrganisations()])
      setDash(d)
      setOrgs(o.organisations || [])
      // default to the first mapped club with a BetterStats org
      const firstMapped = (d.club_mappings || []).find(c => c.betterstats_organisation_id)
      setCmId(prev => prev || (firstMapped ? firstMapped.id : ''))
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const mappings = dash?.club_mappings || []
  const selected = useMemo(() => mappings.find(c => c.id === cmId) || null, [mappings, cmId])
  const orgId = selected?.betterstats_organisation_id || null

  if (loading) return <AdminLayout><PbSpinner message="Loading migration…" /></AdminLayout>

  if (!configured) {
    return (
      <AdminLayout>
        <div className="max-w-3xl">
          <Crumb />
          <h1 className="font-display font-bold text-2xl text-pb-text mt-2 mb-3">KlubPro migration</h1>
          <Card>
            <p className="text-pb-text text-sm mb-2">The KlubPro migration database is not configured on this server.</p>
            <p className="text-pb-faint text-[13px] leading-relaxed">
              Set <code className="text-pb-accent">KLUBPRO_DATABASE_URL</code> in the backend
              environment (e.g.{' '}
              <code className="text-pb-dim">postgresql+asyncpg://klubpro_admin:&lt;pw&gt;@klubpro-postgres:5432/klubpro</code>)
              and restart the backend. The backend container must share a Docker
              network with <code className="text-pb-dim">klubpro-postgres</code>.
            </p>
          </Card>
        </div>
      </AdminLayout>
    )
  }

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <Crumb />
        <div className="flex items-end justify-between flex-wrap gap-3 mt-2 mb-4">
          <h1 className="font-display font-bold text-2xl text-pb-text">KlubPro migration</h1>
          <div className="min-w-[280px]">
            <Label>Mapped club</Label>
            <Select value={cmId} onChange={e => setCmId(e.target.value)} className="mt-1">
              <option value="">select a club</option>
              {mappings.filter(c => c.betterstats_organisation_id).map(c => (
                <option key={c.id} value={c.id}>
                  {c.betterstats_organisation_name} ← {c.klubpro_club_name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <TabBar tabs={TABS} active={tab} onChange={setTab} />

        {tab === 'dashboard' && <Dashboard dash={dash} orgs={orgs} onReload={load} />}

        {tab === 'players' && (
          selected
            ? <KlubproPlayers key={cmId} clubMapping={selected} />
            : <NeedClub />
        )}

        {tab === 'sponsors' && (
          selected
            ? <KlubproSponsors key={cmId} clubMapping={selected} />
            : <NeedClub />
        )}

        {tab === 'history' && <History orgId={orgId} selected={selected} onChanged={load} />}
      </div>
    </AdminLayout>
  )
}

function Crumb() {
  return (
    <Link to="/admin" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← ADMIN</Link>
  )
}

function NeedClub() {
  return <Card><p className="text-pb-faint text-sm">Select a mapped club above to begin.</p></Card>
}

function Dashboard({ dash, orgs, onReload }) {
  const toast = useToast()
  const summary = dash?.summary || []
  const [busyId, setBusyId] = useState(null)

  const map = async (row, orgId, force = false) => {
    const org = orgs.find(o => o.id === orgId)
    if (!org) return
    if (!force && !window.confirm(
      `Map KlubPro club ${row.klubpro_club_name} to BetterStats organisation ${org.name}?`
    )) return
    setBusyId(row.klubpro_club_id)
    try {
      const res = await api.kpSetClubMapping({
        klubpro_club_id: row.klubpro_club_id,
        betterstats_organisation_id: orgId,
        force,
      })
      if (res.status === 'conflict') {
        setBusyId(null)
        if (window.confirm(res.message)) return map(row, orgId, true)
        return
      }
      toast.success(`Mapped ${row.klubpro_club_name} → ${org.name}`)
      await onReload()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Card title="Staging summary. All target clubs">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] uppercase tracking-wide2 text-left">
              <th className="py-1.5 pr-3">Club</th>
              <th className="py-1.5 pr-3 min-w-[220px]">Mapped to</th>
              <th className="py-1.5 pr-3 text-right">Players</th>
              <th className="py-1.5 pr-3 text-right">Complete</th>
              <th className="py-1.5 pr-3 text-right">w/ image</th>
              <th className="py-1.5 pr-3 text-right">Sponsors</th>
              <th className="py-1.5 pr-3 text-right">Logos</th>
              <th className="py-1.5 pr-3">Stage</th>
            </tr>
          </thead>
          <tbody>
            {summary.map(r => (
              <tr key={r.klubpro_club_id} className="pb-hairline-t">
                <td className="py-1.5 pr-3 text-pb-text">{r.klubpro_club_name}</td>
                <td className="py-1.5 pr-3">
                  <Select
                    value={r.betterstats_organisation_id || ''}
                    disabled={busyId === r.klubpro_club_id}
                    onChange={e => { if (e.target.value && e.target.value !== r.betterstats_organisation_id) map(r, e.target.value) }}
                    className={r.betterstats_organisation_id ? '' : 'text-pb-faint'}
                  >
                    <option value="">select BetterStats club</option>
                    {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </Select>
                </td>
                <td className="py-1.5 pr-3 text-right text-pb-dim">{num(r.staged_players)}</td>
                <td className="py-1.5 pr-3 text-right text-pb-dim">{num(r.players_with_all_required_data)}</td>
                <td className="py-1.5 pr-3 text-right text-pb-dim">{num(r.players_with_image)}</td>
                <td className="py-1.5 pr-3 text-right text-pb-dim">{num(r.staged_sponsors)}</td>
                <td className="py-1.5 pr-3 text-right text-pb-dim">{num(r.sponsors_with_logo)}</td>
                <td className="py-1.5 pr-3 font-mono text-[10px] text-pb-faint uppercase">{r.stage_status || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function History({ orgId, selected, onChanged }) {
  const toast = useToast()
  const [batches, setBatches] = useState(null)
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    try {
      const r = await api.kpBatches(orgId || undefined)
      setBatches(r.batches || [])
    } catch (e) { toast.error(e.message) }
  }, [orgId, toast])

  useEffect(() => { load() }, [load])

  const rollback = async (b) => {
    if (!window.confirm(`Roll back this ${b.kind} import? This restores the affected BetterStats rows.`)) return
    setBusy(b.id)
    try {
      const r = await api.kpRollback(b.id)
      toast.success(`Rolled back (${r.restored || 0} restored, ${r.deleted || 0} deleted)`)
      await load()
      onChanged && onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(null) }
  }

  if (batches === null) return <PbSpinner message="Loading history…" />
  if (!batches.length) return <Card><p className="text-pb-faint text-sm">No imports yet{selected ? ` for ${selected.betterstats_organisation_name}` : ''}.</p></Card>

  return (
    <Card title={`Import history${selected ? `. ${selected.betterstats_organisation_name}` : '. All clubs'}`}>
      <div className="space-y-2">
        {batches.map(b => (
          <div key={b.id} className="flex items-center justify-between gap-3 pb-hairline-t pt-2 first:pt-0 first:border-0">
            <div className="min-w-0">
              <div className="text-sm text-pb-text">
                <span className="font-mono text-[10px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border border-pb-hairline2 mr-2"
                  style={{ color: 'var(--pb-accent)' }}>{b.kind}</span>
                {b.kind === 'player'
                  ? `${num(b.counts?.updated)} updated, ${num(b.counts?.skipped)} skipped`
                  : `${num(b.counts?.inserted)} inserted, ${num(b.counts?.skipped)} skipped`}
              </div>
              <div className="text-pb-faint text-[11px] font-mono mt-0.5">
                {new Date(b.created_at).toLocaleString()} · {b.operator_name || 'operator'}
                {b.status === 'rolled_back' && <span className="text-pb-amber ml-2">ROLLED BACK</span>}
              </div>
            </div>
            {b.status !== 'rolled_back' && (
              <Btn danger sm onClick={() => rollback(b)} disabled={busy === b.id}>
                {busy === b.id ? 'Rolling back…' : 'Roll back'}
              </Btn>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
