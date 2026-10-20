// Admin "view as a team" bar. Shown across the top of the public Fantasy pages
// while an admin is looking at the game as one of the club's managers. Read-only:
// the server refuses every change. The select jumps to another team; Exit ends
// the view and goes back to the admin Fantasy pages.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP } from './ui'

const AMBER = '#f5a524'

export default function ViewAsBar({ token, viewAs, fail }) {
  const [teams, setTeams] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.fanViewAsManagers(token).then(d => setTeams(d.teams || [])).catch(() => setTeams([]))
  }, [token])

  const switchTo = async (id) => {
    if (!id || id === viewAs.manager_id) return
    setBusy(true)
    try { await api.fanViewAsSwitch(token, id); window.location.reload() }
    catch (e) { fail?.(e); setBusy(false) }
  }
  const exit = async () => {
    setBusy(true)
    try { await api.fanViewAsExit(token) } catch { /* the cookie expires on its own */ }
    window.location.assign('/admin/fantasy')
  }

  const label = (t) => `${t.team_name || 'No team yet'} · ${t.display_name}${t.total_points != null ? ` · ${t.total_points}` : ''}`

  return (
    <div role="status" style={{
      position: 'sticky', top: 0, zIndex: 50, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10,
      padding: '8px 12px', marginBottom: 10, borderRadius: 10,
      background: 'color-mix(in srgb, #f5a524 16%, var(--bg))', border: `1px solid ${AMBER}`, color: 'var(--text)',
    }}>
      <span style={{ font: `800 10px ${DISP}`, letterSpacing: '.14em', textTransform: 'uppercase', color: AMBER }}>Admin view</span>
      <span style={{ font: `600 12px 'Hanken Grotesk'`, minWidth: 0 }}>
        Viewing as <strong>{viewAs.display_name || 'a team'}</strong>. Read only: nothing you do here changes their team.
      </span>
      <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
        <select value={viewAs.manager_id || ''} disabled={busy || !teams?.length} onChange={e => switchTo(e.target.value)}
          aria-label="Switch team"
          style={{ maxWidth: 'min(280px, 52vw)', minWidth: 0, padding: '5px 8px', borderRadius: 8, border: '1px solid var(--hairline2)', background: 'var(--surface)', color: 'var(--text)', font: `600 12px 'Hanken Grotesk'` }}>
          {!viewAs.manager_id && <option value="">Pick a team…</option>}
          {(teams || []).map(t => <option key={t.manager_id} value={t.manager_id}>{label(t)}</option>)}
        </select>
        <button onClick={exit} disabled={busy} style={{
          padding: '5px 12px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${AMBER}`, background: 'transparent',
          color: 'var(--text)', font: `700 12px 'Hanken Grotesk'`,
        }}>Exit</button>
      </span>
    </div>
  )
}
