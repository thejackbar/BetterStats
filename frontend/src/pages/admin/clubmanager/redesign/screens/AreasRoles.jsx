import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'
import EntityManager, { reorderBySortOrder } from '../parts/EntityManager'
import AreaEditor from '../parts/AreaEditor'

// Areas & Roles — the configuration the other screens read from. Roles,
// Activities and Operational Areas each pair a primary list with a "type"
// catalogue (Role types / Activity types / Departments) that groups it. Each
// pairing is a top-level primary tab plus a secondary tab so the type catalogue
// is first-class and discoverable, not buried. A parent Starter Pack seeds its
// type catalogue too (see the services), so one click gives a grouped set.

// Role-type categories — a committee type feeds committee positions; an official
// type is a formal scorecard role (umpire/scorer); the rest are non-committee.
const ROLE_CAT_OPTS = [
  { value: 'committee', label: 'Committee' },
  { value: 'official', label: 'Official (umpire, scorer)' },
  { value: 'volunteer', label: 'Volunteer' },
  { value: 'paid', label: 'Paid worker' },
  { value: 'third_party', label: 'Third party' },
  { value: 'other', label: 'Other' },
]
const catLabel = (v) => (ROLE_CAT_OPTS.find(o => o.value === v) || {}).label || ''

// A compact secondary tab bar, sized to content (not full width).
function SubBar({ value, onChange, tabs }) {
  return <div style={{ display: 'flex', marginBottom: 16 }}><SegTabs value={value} onChange={onChange} tabs={tabs} /></div>
}

export default function AreasRoles({ st, patch, narrow }) {
  const tab = st.setupTab || 'roles'
  const [sub, setSub] = useState('main')   // secondary tab within a section: 'main' | 'types'
  const [busy, setBusy] = useState(false)
  const [areaKey, setAreaKey] = useState(0)  // bump to remount AreaEditor after a reset
  const [roleTypes, setRoleTypes] = useState([])
  const [actTypes, setActTypes] = useState([])

  const reloadRoleTypes = () => api.raRoleTypes().then(r => setRoleTypes(r?.types || r || [])).catch(() => {})
  const reloadActTypes = () => api.raActivityTypes().then(r => setActTypes(r?.types || r || [])).catch(() => {})
  useEffect(() => {
    setSub('main')  // reset the secondary tab when switching sections
    if (tab === 'roles') reloadRoleTypes()
    if (tab === 'activities') reloadActTypes()
  }, [tab])

  const roleTypeOpts = roleTypes.map(t => ({ value: t.id, label: t.name }))
  const actTypeOpts = actTypes.map(t => ({ value: t.id, label: t.name }))
  const scroll = (max) => ({ flex: 1, overflowY: 'auto', padding: 20, maxWidth: max })

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
        <div className="pb-scroll" style={scroll('52rem')}>
          <SubBar value={sub} onChange={setSub} tabs={[{ key: 'main', label: 'Roles' }, { key: 'types', label: 'Role types' }]} />
          {sub === 'main' ? (
            <EntityManager key="roles"
              describe="General club roles a volunteer can hold — these name what people do and gate which operational areas they can be rostered onto. Each role sits under a type (Official, Volunteer, Paid…). Committee-type roles are managed as positions on the Committee screen and don't appear here."
              load={() => api.raRoles().then(r => (r?.roles || r || []).filter(x => !x.is_committee && x.role_type_category !== 'committee'))}
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
          ) : (
            <EntityManager key="role-types"
              describe="Role types classify your roles. A Committee type feeds committee positions (not the Roles list); an Official type is a formal scorecard role (umpire/scorer); Volunteer / Paid / Third party / Other are everyday roles. Pick a type when adding a role."
              load={() => api.raRoleTypes().then(r => r?.types || r || [])}
              fields={[
                { key: 'name', label: 'Type name', type: 'text', required: true, span: 2 },
                { key: 'category', label: 'Category', type: 'select', options: ROLE_CAT_OPTS, placeholder: 'Volunteer' },
                { key: 'description', label: 'Description', type: 'text' },
              ]}
              onCreate={v => api.raCreateRoleType(v)} onUpdate={(id, v) => api.raUpdateRoleType(id, v)} onDelete={id => api.raArchiveRoleType(id)}
              onReorder={reorderBySortOrder(api.raUpdateRoleType)} onChanged={reloadRoleTypes}
              seed={{ label: 'Add Role Types Starter Pack', fn: () => api.raSeedRoleTypes() }}
              primaryKey="name" subtitle={it => [catLabel(it.category), it.description].filter(Boolean).join(' · ')}
              addLabel="Add role type" emptyText="No role types yet." />
          )}
        </div>
      )}

      {tab === 'activities' && (
        <div className="pb-scroll" style={scroll('48rem')}>
          <SubBar value={sub} onChange={setSub} tabs={[{ key: 'main', label: 'Activities' }, { key: 'types', label: 'Activity types' }]} />
          {sub === 'main' ? (
            <EntityManager key="activities"
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
          ) : (
            <EntityManager key="activity-types"
              describe="Activity types group your activities (Committee & Administration, Ground & Equipment…). Pick one when adding an activity. The Activities Starter Pack seeds these for you."
              load={() => api.raActivityTypes().then(r => r?.types || r || [])}
              fields={[{ key: 'name', label: 'Type name', type: 'text', required: true, span: 2 }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
              onCreate={v => api.raCreateActivityType(v)} onUpdate={(id, v) => api.raUpdateActivityType(id, v)} onDelete={id => api.raArchiveActivityType(id)}
              onReorder={reorderBySortOrder(api.raUpdateActivityType)} onChanged={reloadActTypes}
              seed={{ label: 'Add Activity Types Starter Pack', fn: () => api.raSeedActivityTypes() }}
              primaryKey="name" subtitle={it => it.description || ''}
              addLabel="Add activity type" emptyText="No activity types yet." />
          )}
        </div>
      )}

      {tab === 'quals' && (
        <div className="pb-scroll" style={scroll('48rem')}>
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
        <div className="pb-scroll" style={scroll('68rem')}>
          <SubBar value={sub} onChange={setSub} tabs={[{ key: 'main', label: 'Operational areas' }, { key: 'types', label: 'Departments' }]} />
          {sub === 'main' ? (
            <>
              <AreaEditor key={areaKey} />
              <div style={{ marginTop: 20, borderTop: `1px solid ${C.hair}`, paddingTop: 14 }}>
                <button disabled={busy} onClick={async () => { if (!window.confirm('Remove all operational areas, their patterns and every roster week for this club? (Testing reset — only this club; players/members/committee are untouched.)')) return; setBusy(true); await api.rosterClearConfig().catch(() => {}); setAreaKey(k => k + 1); setBusy(false) }}
                  style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>Clear all areas (reset)</button>
              </div>
            </>
          ) : (
            <EntityManager key="departments"
              describe="Departments group your operational areas (Food & Beverage, Cricket Operations…). Pick one when adding an area. The Operational Areas Starter Pack seeds these for you."
              load={() => api.rosterDepartments().then(r => r?.departments || r || [])}
              fields={[{ key: 'name', label: 'Department name', type: 'text', required: true, span: 2 }]}
              onCreate={v => api.rosterCreateDepartment(v)} onUpdate={(id, v) => api.rosterUpdateDepartment(id, v)} onDelete={id => api.rosterDeleteDepartment(id)}
              onReorder={reorderBySortOrder(api.rosterUpdateDepartment)}
              seed={{ label: 'Add Departments Starter Pack', fn: () => api.rosterSeedDepartments() }}
              primaryKey="name" addLabel="Add department" emptyText="No departments yet." />
          )}
        </div>
      )}
    </div>
  )
}
