import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'

// Areas & Roles — the configuration the other screens read from. Roles,
// Activities and Qualification types are backed by real club config. Operational
// Areas (the roster's own concept) is net-new and lands with the roster backend.

export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'roles'
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      api.raRoles().catch(() => ({ roles: [] })),
      api.raActivities().catch(() => ({ activities: [] })),
      api.qualListTypes().catch(() => ([])),
    ]).then(([rolesRes, actRes, qualRes]) => {
      if (!alive) return
      setData({
        roles: rolesRes?.roles || rolesRes || [],
        activities: actRes?.activities || actRes || [],
        quals: qualRes?.types || qualRes || [],
      })
    })
    return () => { alive = false }
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

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

      {!data && <div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading configuration…</div>}

      {data && tab === 'roles' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: '72rem' }}>
            <div>
              <div style={cap}>GENERAL ROLES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {data.roles.filter(r => !r.is_committee).map(r => (
                  <div key={r.id} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{r.title}</span>
                      {r.role_type_name && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.dim }}>{r.role_type_name}</span>}
                    </div>
                    {r.description && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 4 }}>{r.description}</div>}
                  </div>
                ))}
                {data.roles.filter(r => !r.is_committee).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No general roles set up yet.</div>}
              </div>
            </div>
            <div>
              <div style={cap}>COMMITTEE ROLES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {data.roles.filter(r => r.is_committee).map(r => (
                  <div key={r.id} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                    <span style={{ fontSize: 13, color: C.text }}>{r.title}</span>
                    {r.role_type_name && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{r.role_type_name}</span>}
                  </div>
                ))}
                {data.roles.filter(r => r.is_committee).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No committee roles set up yet.</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {data && tab === 'activities' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '44rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 16px', lineHeight: 1.55 }}>What logged volunteer hours are spent on. A completed roster shift books its hours against one of these.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.activities.map(a => (
              <div key={a.id} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                <span style={{ fontSize: 13, color: C.text }}>{a.title}</span>
                {a.activity_type_name && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{a.activity_type_name}</span>}
              </div>
            ))}
            {data.activities.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No activities set up yet.</div>}
          </div>
        </div>
      )}

      {data && tab === 'quals' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '48rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 16px', lineHeight: 1.55 }}>Qualification types the club tracks. A gating qualification will block rostering for the areas that require it, once the roster is live.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.quals.map(q => (
              <div key={q.id} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{q.name}</span>
                  {q.validity_months ? <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>valid {q.validity_months} months</span> : <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>no expiry</span>}
                </div>
                {q.description && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 4 }}>{q.description}</div>}
              </div>
            ))}
            {data.quals.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No qualification types set up yet.</div>}
          </div>
        </div>
      )}

      {tab === 'areas' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '46rem' }}>
          <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 22, fontSize: 13, color: C.dim, lineHeight: 1.6 }}>
            Operational areas — a slice of club work with its own weekly shift pattern, the role that covers it and the qualification that gates it — are part of the roster, which is being built next. Once it lands you'll define your areas here and the weekly roster generates from them.
          </div>
        </div>
      )}
    </div>
  )
}
