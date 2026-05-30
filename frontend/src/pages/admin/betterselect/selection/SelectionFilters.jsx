import { FilterGroup, FilterCheck } from '../../../../lib/filters'
import { SKILL_LABELS, BAT_HANDS, BOWL_ACTIONS, BOWL_TYPES, AVAIL_META } from './shared'

// The Selection filter panel. The container owns the facet Sets and renders this
// only when expanded; here we just read `facets` and report toggles via
// onToggle(facetKey, value). facetKey ∈ squads|roles|avail|batHand|bowlAction|bowlType|activity.
export default function SelectionFilters({ squadOptions, filterCount, onClear, facets, onToggle }) {
  return (
    <div className="pb-card p-4 mb-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Filters</h3>
        {filterCount > 0 && <button onClick={onClear} className="text-xs text-pb-accent hover:underline">Clear settings</button>}
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        <FilterGroup title="Squads">
          {squadOptions.length === 0 && <p className="text-pb-faintest text-xs">No squads found.</p>}
          {squadOptions.map(sq => <FilterCheck key={sq} label={sq} checked={facets.squads.has(sq)} onChange={() => onToggle('squads', sq)} />)}
        </FilterGroup>
        <FilterGroup title="Specialist roles">
          {Object.entries(SKILL_LABELS).map(([code, label]) => <FilterCheck key={code} label={label} checked={facets.roles.has(code)} onChange={() => onToggle('roles', code)} />)}
        </FilterGroup>
        <FilterGroup title="Availability">
          {['AVAILABLE', 'MAYBE', 'NO_RESPONSE', 'UNAVAILABLE'].map(s => <FilterCheck key={s} label={AVAIL_META[s].label} checked={facets.avail.has(s)} onChange={() => onToggle('avail', s)} />)}
        </FilterGroup>
        <FilterGroup title="Batting">
          {Object.entries(BAT_HANDS).map(([v, l]) => <FilterCheck key={v} label={l} checked={facets.batHand.has(v)} onChange={() => onToggle('batHand', v)} />)}
        </FilterGroup>
        <FilterGroup title="Bowling — action">
          {Object.entries(BOWL_ACTIONS).map(([v, l]) => <FilterCheck key={v} label={l} checked={facets.bowlAction.has(v)} onChange={() => onToggle('bowlAction', v)} />)}
        </FilterGroup>
        <FilterGroup title="Bowling — type">
          {Object.entries(BOWL_TYPES).map(([v, l]) => <FilterCheck key={v} label={l} checked={facets.bowlType.has(v)} onChange={() => onToggle('bowlType', v)} />)}
        </FilterGroup>
        <FilterGroup title="Activity">
          <FilterCheck label="Active" checked={facets.activity.has('ACTIVE')} onChange={() => onToggle('activity', 'ACTIVE')} />
          <FilterCheck label="Dormant" checked={facets.activity.has('DORMANT')} onChange={() => onToggle('activity', 'DORMANT')} />
        </FilterGroup>
      </div>
    </div>
  )
}
