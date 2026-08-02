import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'
import EntityManager, { reorderBySortOrder } from '../parts/EntityManager'
import AreaEditor from '../parts/AreaEditor'

// Areas & Roles — the configuration the other screens read from. Roles,
// Activities and Qualification types are backed by real club config; each of
// Roles/Activities also has a "type" catalogue (managed in a collapsible panel)
// that groups its items and feeds the type dropdown in its own CRUD form.
// Operational Areas (the roster's own concept) carries a Departments catalogue
// the same way — see AreaEditor.

// A collapsible panel for the secondary "type" catalogue managers, so the main
// list stays the focus and the type CRUD is one click away.
function ManagePanel({ title, hint, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginTop: 24, borderTop: `1px solid ${C.hair}`, paddingTop: 14 }}>
      <button onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 9, background: 'transparent', border: 'none', color: C.text, cursor: 'pointer', fontSize: 13.5, fontWeight: 600, padding: 0 }}>
        <span style={{ fontSize: 11, color: C.faint, width: 10 }}>{open ? '▾' : '▸'}</span>{title}
        {hint && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, fontWeight: 400 }}>{hint}</span>}
      </button>
      {open && <div style={{ marginTop: 14 }}>{children}</div>}
    </div>
  )
}

export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'roles'
  const [busy, setBusy] = useState(false)
  const [areaKey, setAreaKey] = useState(0)  // bump to remount AreaEditor after a reset
  const [roleTypes, setRoleTypes] = useState([])
  const [actTypes, setActTypes] = useState([])

  const reloadRoleTypes = () => api.raRoleTypes().then(r => setRoleTypes(r?.types || r || [])).catch(() => {})
  const reloadActTypes = () => api.raActivityTypes().then(r => setActTypes(r?.types || r || [])).catch(() => {})
  useEffect(() => {
    if (tab === 'roles') reloadRoleTypes()
    if (tab === 'activities') reloadActTypes()
  }, [tab])

  const roleTypeOpts = roleTypes.map(t => ({ value: t.id, label: t.name }))
  const actTypeOpts = actTypes.map(t => ({ value: t.id, label: t.name }))

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
            describe="General club roles a volunteer can hold — these name what people do and gate which operational areas they can be rostered onto. Each role can sit under an optional type (Coach, Ground Staff…); the Starter Pack sets up those types for you. Committee roles are managed on the Committee screen."
            load={() => api.raRoles().then(r => (r?.roles || r || []).filter(x => !x.is_committee))}
            fields={[
              { key: 'title', label: 'Role name', type: 'text', required: true, span: 2 },
              { key: 'role_type_id', label: 'Type', type: 'select', options: roleTypeOpts, placeholder: 'No type',
                allowNew: true, newLabel: 'New role type…', newPlaceholder: 'New role type name',
                onCreateNew: async (name) => { const t = await api.raCreateRoleType({ name }); await reloadRoleTypes(); return t } },
              { key: 'description', label: 'Description', type: 'text' },
            ]}
            onCreate={v => api.raCreateRole(v)} onUpdate={(id, v) => api.raUpdateRole(id, v)} onDelete={id => api.raArchiveRole(id)}
            onReorder={reorderBySortOrder(api.raUpdateRole)} onChanged={reloadRoleTypes}
            seed={{ label: 'Add Roles Starter Pack', fn: () => api.raSeedRoles(false) }}
            primaryKey="title" subtitle={it => [it.role_type_name, it.description].filter(Boolean).join(' · ')}
            addLabel="Add role" emptyText="No general roles yet." />

          <ManagePanel title="Manage role types" hint="COACH · GROUND STAFF · FOOD & BEVERAGE…">
            <EntityManager
              describe="Role types group your roles. Pick one when adding a role above."
              load={() => api.raRoleTypes().then(r => r?.types || r || [])}
              fields={[{ key: 'name', label: 'Type name', type: 'text', required: true, span: 2 }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
              onCreate={v => api.raCreateRoleType(v)} onUpdate={(id, v) => api.raUpdateRoleType(id, v)} onDelete={id => api.raArchiveRoleType(id)}
              onReorder={reorderBySortOrder(api.raUpdateRoleType)} onChanged={reloadRoleTypes}
              seed={{ label: 'Add Role Types Starter Pack', fn: () => api.raSeedRoleTypes() }}
              primaryKey="name" subtitle={it => it.description || ''}
              addLabel="Add role type" emptyText="No role types yet." />
          </ManagePanel>
        </div>
      )}

      {tab === 'activities' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '48rem' }}>
          <EntityManager
            describe="What logged volunteer hours are spent on. A completed roster shift books its hours against one of these. Each activity can sit under an optional type; the Starter Pack sets up those types for you."
            load={() => api.raActivities().then(r => r?.activities || r || [])}
            fields={[
              { key: 'title', label: 'Activity name', type: 'text', required: true, span: 2 },
              { key: 'activity_type_id', label: 'Type', type: 'select', options: actTypeOpts, placeholder: 'No type',
                allowNew: true, newLabel: 'New activity type…', newPlaceholder: 'New activity type name',
                onCreateNew: async (name) => { const t = await api.raCreateActivityType({ name }); await reloadActTypes(); return t } },
              { key: 'description', label: 'Description', type: 'text' },
            ]}
            onCreate={v => api.raCreateActivity(v)} onUpdate={(id, v) => api.raUpdateActivity(id, v)} onDelete={id => api.raArchiveActivity(id)}
            onReorder={reorderBySortOrder(api.raUpdateActivity)} onChanged={reloadActTypes}
            seed={{ label: 'Add Activities Starter Pack', fn: () => api.raSeedActivities() }}
            primaryKey="title" subtitle={it => it.activity_type_name || ''}
            addLabel="Add activity" emptyText="No activities yet." />

          <ManagePanel title="Manage activity types" hint="COMMITTEE & ADMINISTRATION · GROUND & EQUIPMENT…">
            <EntityManager
              describe="Activity types group your activities. Pick one when adding an activity above."
              load={() => api.raActivityTypes().then(r => r?.types || r || [])}
              fields={[{ key: 'name', label: 'Type name', type: 'text', required: true, span: 2 }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
              onCreate={v => api.raCreateActivityType(v)} onUpdate={(id, v) => api.raUpdateActivityType(id, v)} onDelete={id => api.raArchiveActivityType(id)}
              onReorder={reorderBySortOrder(api.raUpdateActivityType)} onChanged={reloadActTypes}
              seed={{ label: 'Add Activity Types Starter Pack', fn: () => api.raSeedActivityTypes() }}
              primaryKey="name" subtitle={it => it.description || ''}
              addLabel="Add activity type" emptyText="No activity types yet." />
          </ManagePanel>
        </div>
      )}

      {tab === 'quals' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '48rem' }}>
          <EntityManager
            describe="Qualification types the club tracks — these ARE the qualifications (there's no separate sub-type). A gating qualification blocks rostering for the operational areas that require it."
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
