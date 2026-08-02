import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'
import EntityManager, { reorderBySortOrder } from '../parts/EntityManager'

// Areas & Roles — the configuration the other screens read from. Roles,
// Activities and Qualification types are backed by real club config. Operational
// Areas (the roster's own concept) is net-new and lands with the roster backend.

export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'roles'
  const [data, setData] = useState(null)

  const [busy, setBusy] = useState(false)
  // Roles / Activities / Qualifications self-load inside their EntityManager;
  // this only fetches the operational areas for that tab.
  const load = () => api.rosterAreas().then(r => setData({ areas: r?.areas || r || [] })).catch(() => setData({ areas: [] }))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const fmtHour = (h) => { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); if (hh === 24) return '12am'; let b = hh % 12; if (b === 0) b = 12; return b + (mm ? ':' + String(mm).padStart(2, '0') : '') + (hh >= 12 && hh < 24 ? 'pm' : 'am') }
  const DOWL = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Areas &amp; Roles</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>THE CONFIGURATION EVERY OTHER SCREEN READS FROM</Caption>
        </div>
        <SegTabs value={tab} onChange={k => patch({ setupTab: k })} tabs={[{ key: 'roles', label: 'Roles' }, { key: 'activities', label: 'Activities' }, { key: 'quals', label: 'Qualifications' }, { key: 'areas', label: 'Operational areas' }]} />
      </ScreenHeader>

      {tab === 'areas' && !data && <div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading configuration…</div>}

      {tab === 'roles' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '52rem' }}>
          <EntityManager
            describe="General club roles a volunteer can hold — these name what people do and gate which operational areas they can be rostered onto. Committee roles are managed on the Committee screen."
            load={() => api.raRoles().then(r => (r?.roles || r || []).filter(x => !x.is_committee))}
            fields={[{ key: 'title', label: 'Role name', type: 'text', required: true, span: 2 }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
            onCreate={v => api.raCreateRole(v)} onUpdate={(id, v) => api.raUpdateRole(id, v)} onDelete={id => api.raArchiveRole(id)}
            onReorder={reorderBySortOrder(api.raUpdateRole)}
            seed={{ label: 'Add Roles Starter Pack', fn: () => api.raSeedRoles(false) }}
            primaryKey="title" subtitle={it => [it.role_type_name, it.description].filter(Boolean).join(' · ')}
            addLabel="Add role" emptyText="No general roles yet." />
        </div>
      )}

      {tab === 'activities' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '46rem' }}>
          <EntityManager
            describe="What logged volunteer hours are spent on. A completed roster shift books its hours against one of these."
            load={() => api.raActivities().then(r => r?.activities || r || [])}
            fields={[{ key: 'title', label: 'Activity name', type: 'text', required: true, span: 2 }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
            onCreate={v => api.raCreateActivity(v)} onUpdate={(id, v) => api.raUpdateActivity(id, v)} onDelete={id => api.raArchiveActivity(id)}
            onReorder={reorderBySortOrder(api.raUpdateActivity)}
            seed={{ label: 'Add Activities Starter Pack', fn: () => api.raSeedActivities() }}
            primaryKey="title" subtitle={it => it.activity_type_name || ''}
            addLabel="Add activity" emptyText="No activities yet." />
        </div>
      )}

      {tab === 'quals' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '48rem' }}>
          <EntityManager
            describe="Qualification types the club tracks. A gating qualification blocks rostering for the operational areas that require it."
            load={() => api.qualListTypes().then(r => r?.types || r || [])}
            fields={[{ key: 'name', label: 'Qualification', type: 'text', required: true, span: 2 }, { key: 'validity_months', label: 'Valid for (months)', type: 'number' }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
            onCreate={v => api.qualCreateType(v)} onUpdate={(id, v) => api.qualUpdateType(id, v)} onDelete={id => api.qualArchiveType(id)}
            onReorder={reorderBySortOrder(api.qualUpdateType)}
            seed={{ label: 'Add Qualifications Starter Pack', fn: () => api.qualSeedStarterTypes() }}
            primaryKey="name" subtitle={it => it.validity_months ? 'valid ' + it.validity_months + ' months' : 'no expiry'}
            addLabel="Add qualification" emptyText="No qualification types yet." />
        </div>
      )}

      {data && tab === 'areas' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '68rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 18px', lineHeight: 1.55, maxWidth: '46rem' }}>An operational area is a slice of club work with its own weekly shift pattern, the role that can cover it, and the qualification that gates it. Change a pattern here and next week's roster is generated from it.</p>
          {data.areas.length === 0 ? (
            <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 22, fontSize: 13.5, color: C.dim, lineHeight: 1.6 }}>
              No operational areas yet. Add a starter set (Bar, Umpires, Groundsman…) — matched to your existing roles and qualifications where the names line up — and edit from there.
              <div style={{ marginTop: 14 }}>
                <button disabled={busy} onClick={async () => { setBusy(true); await api.rosterSeedStarter().catch(() => {}); await load(); setBusy(false) }} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>{busy ? 'Setting up…' : 'Add Operational Areas Starter Pack'}</button>
              </div>
            </div>
          ) : (
            <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
              {[...new Set(data.areas.map(a => a.department || 'Areas'))].map(dept => (
                <div key={dept}>
                  <div style={cap}>{dept}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {data.areas.filter(a => (a.department || 'Areas') === dept).map(a => {
                      const slots = (a.patterns || []).reduce((n, p) => n + (p.headcount || 1), 0)
                      return (
                        <div key={a.id} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: '13px 15px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ width: 9, height: 9, borderRadius: 3, background: a.color || '#6366F1', flexShrink: 0 }} />
                            <span style={{ fontSize: 14.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{a.name}</span>
                            <span style={{ fontFamily: MONO, fontSize: 10, color: C.dim, flexShrink: 0 }}>{slots} shift{slots === 1 ? '' : 's'} / week</span>
                          </div>
                          <div style={{ fontFamily: MONO, fontSize: 10, color: C.faint, margin: '6px 0 9px' }}>{[a.required_role_name, a.required_qualification_name ? 'must hold ' + a.required_qualification_name : null].filter(Boolean).join(' · ') || 'No role or qualification set'}</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                            {(a.patterns || []).map((p, i) => (
                              <span key={i} style={{ fontFamily: MONO, fontSize: 9.5, padding: '3px 7px', borderRadius: 5, background: `color-mix(in srgb, ${a.color || '#6366F1'} 12%, transparent)`, border: `1px solid color-mix(in srgb, ${a.color || '#6366F1'} 35%, transparent)`, color: a.color || '#6366F1' }}>{DOWL[p.day_of_week]} {fmtHour(p.start_time)}–{fmtHour(p.end_time)}{p.headcount > 1 ? ' ×' + p.headcount : ''}</span>
                            ))}
                            {(a.patterns || []).length === 0 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>No shift pattern set</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 20, borderTop: `1px solid ${C.hair}`, paddingTop: 14 }}>
              <button disabled={busy} onClick={async () => { if (!window.confirm('Remove all operational areas, their patterns and every roster week for this club? (Testing reset — only this club; players/members/committee are untouched.)')) return; setBusy(true); await api.rosterClearConfig().catch(() => {}); await load(); setBusy(false) }}
                style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>Clear all areas (reset)</button>
            </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
