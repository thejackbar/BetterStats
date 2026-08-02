import { useState } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'
import EntityManager, { reorderBySortOrder } from '../parts/EntityManager'
import AreaEditor from '../parts/AreaEditor'

// Areas & Roles — the configuration the other screens read from. Roles,
// Activities and Qualification types are backed by real club config. Operational
// Areas (the roster's own concept) is net-new and lands with the roster backend.

export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'roles'
  const [busy, setBusy] = useState(false)
  const [areaKey, setAreaKey] = useState(0)  // bump to remount AreaEditor after a reset

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

      {tab === 'areas' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '68rem' }}>
          <AreaEditor key={areaKey} />
          <div style={{ marginTop: 20, borderTop: `1px solid ${C.hair}`, paddingTop: 14 }}>
            <button disabled={busy} onClick={async () => { if (!window.confirm('Remove all operational areas, their patterns and every roster week for this club? (Testing reset — only this club; players/members/committee are untouched.)')) return; setBusy(true); await api.rosterClearConfig().catch(() => {}); setAreaKey(k => k + 1); setBusy(false) }}
              style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>Clear all areas (reset)</button>
          </div>
        </div>
      )}
    </div>
  )
}
