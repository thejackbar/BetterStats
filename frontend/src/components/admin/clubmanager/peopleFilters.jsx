import { useState, useEffect, useMemo } from 'react'
import { api } from '../../../lib/api'
import { MenuButton, MenuItem, MenuHeading, MenuDivider, FilterChip, C } from '../../../pages/admin/clubmanager/redesign/ui'

// The Directory's People filters, reusable on any screen that lists the club's
// people by `member_id` — Accounts and Payments today.
//
// It reads `/club-admin/directory/people` and matches on the SEGMENTS that
// endpoint already computes, rather than re-deriving "who is a volunteer" or
// "who is a Senior Player" per screen. That is the whole point: the moment two
// screens work out a segment separately they start disagreeing, and the
// Directory is where those rules live (see services/directory.py).
//
// The caller gets a predicate over member ids, so each screen keeps its own
// data layer and its own rows; nothing about fees or payments moves.

const TYPE_PREFIX = 'type:'
const SQUAD_PREFIX = 'squad:'
const TIER_PREFIX = 'tier:'
const GENDER_PREFIX = 'gender:'
const GENDER_LABEL = { male: 'Male', female: 'Female', other: 'Other' }
const ROLE_SEGS = [
  { seg: 'Volunteer', label: 'Volunteers' },
  { seg: 'Committee', label: 'Committee' },
  { seg: 'Official', label: 'Officials' },
]

export function usePeopleFilters() {
  const [people, setPeople] = useState(null)
  const [failed, setFailed] = useState(false)
  const [opts, setOpts] = useState({ genders: [], squads: [], tiers: [], tier_season: null })
  const [types, setTypes] = useState([])
  const [f, setF] = useState({ membership: null, role: null, honour: null, gender: null, squad: null, tier: null })

  useEffect(() => {
    let dead = false
    api.dirPeople().then(res => {
      if (dead) return
      setPeople(res?.people || [])
      setTypes(res?.membership_types || [])
      setOpts({
        genders: res?.genders || [], squads: res?.squads || [],
        tiers: res?.tiers || [], tier_season: res?.tier_season || null,
      })
    }).catch(() => { if (!dead) { setPeople([]); setFailed(true) } })
    return () => { dead = true }
  }, [])

  const set = (k, v) => setF(s => ({ ...s, [k]: s[k] === v ? null : v }))
  const active = Object.entries(f).filter(([, v]) => v)
  const anyOn = active.length > 0

  // member_id -> segs, so matching is a set lookup per row rather than a scan.
  const segsById = useMemo(() => {
    const m = new Map()
    for (const p of people || []) if (p.member_id) m.set(p.member_id, p.segs || [])
    return m
  }, [people])

  // A person the Directory does not know about cannot satisfy a People filter,
  // so they drop out while any filter is on and are kept when none is.
  //
  // FAIL OPEN if the Directory could not be read at all. Filtering everything
  // out on a failed fetch turns one broken endpoint into an empty Accounts
  // page, which reads as "this club has no members" — exactly what a 500 in
  // GET /people did before. No menus are drawn in that state either, so the
  // screen simply carries on without People filters.
  const matches = (memberId) => {
    if (failed || !anyOn) return true
    const segs = segsById.get(memberId)
    if (!segs) return false
    return active.every(([, seg]) => segs.includes(seg))
  }

  const internal = types.filter(t => (t.scope || 'internal') !== 'external')
  const external = types.filter(t => (t.scope || 'internal') === 'external')
  const label = (seg, prefix) => (seg || '').slice(prefix.length)

  const menus = failed ? null : (
    <>
      <MenuButton label="Membership" width={260}
        value={f.membership ? (f.membership === 'Player' ? 'Players' : f.membership === 'External' ? 'Not members' : label(f.membership, TYPE_PREFIX)) : null}>
        {close => (
          <>
            <MenuItem on={!f.membership} onClick={() => { setF(s => ({ ...s, membership: null })); close() }}>Everyone</MenuItem>
            <MenuItem on={f.membership === 'Player'} onClick={() => { set('membership', 'Player'); close() }}>Players</MenuItem>
            {internal.length > 0 && <MenuHeading>MEMBERS</MenuHeading>}
            {internal.map(t => (
              <MenuItem key={t.id} on={f.membership === TYPE_PREFIX + t.name}
                onClick={() => { set('membership', TYPE_PREFIX + t.name); close() }}>{t.name}</MenuItem>
            ))}
            {external.length > 0 && <MenuHeading>NOT MEMBERS</MenuHeading>}
            {external.map(t => (
              <MenuItem key={t.id} on={f.membership === TYPE_PREFIX + t.name}
                onClick={() => { set('membership', TYPE_PREFIX + t.name); close() }}>{t.name}</MenuItem>
            ))}
            {external.length > 0 && (
              <MenuItem on={f.membership === 'External'} onClick={() => { set('membership', 'External'); close() }}>Anyone who is not a member</MenuItem>
            )}
          </>
        )}
      </MenuButton>

      <MenuButton label="Role" width={220}
        value={f.role ? (ROLE_SEGS.find(r => r.seg === f.role) || {}).label : null}>
        {close => (
          <>
            <MenuItem on={!f.role} onClick={() => { setF(s => ({ ...s, role: null })); close() }}>Any role</MenuItem>
            {ROLE_SEGS.map(r => (
              <MenuItem key={r.seg} on={f.role === r.seg} onClick={() => { set('role', r.seg); close() }}>{r.label}</MenuItem>
            ))}
          </>
        )}
      </MenuButton>

      <MenuButton label="More" width={240}
        value={active.filter(([k]) => !['membership', 'role'].includes(k)).length
          ? String(active.filter(([k]) => !['membership', 'role'].includes(k)).length) : null}>
        {close => (
          <>
            <MenuHeading>HONOURS</MenuHeading>
            <MenuItem on={f.honour === 'Life member'} onClick={() => { set('honour', 'Life member'); close() }}>Life members</MenuItem>
            {opts.genders.length > 0 && <MenuHeading>GENDER</MenuHeading>}
            {opts.genders.map(g => (
              <MenuItem key={g} on={f.gender === GENDER_PREFIX + g}
                onClick={() => { set('gender', GENDER_PREFIX + g); close() }}>{GENDER_LABEL[g] || g}</MenuItem>
            ))}
            {opts.squads.length > 0 && <MenuHeading>SQUAD</MenuHeading>}
            {opts.squads.map(t => (
              <MenuItem key={t.id} on={f.squad === SQUAD_PREFIX + t.name}
                onClick={() => { set('squad', SQUAD_PREFIX + t.name); close() }}>{t.name}</MenuItem>
            ))}
            {opts.tiers.length > 0 && (
              <>
                <MenuDivider />
                <MenuHeading>MEMBERSHIP TIER{opts.tier_season ? ' · ' + opts.tier_season.name : ''}</MenuHeading>
              </>
            )}
            {opts.tiers.map(t => (
              <MenuItem key={t.id} on={f.tier === TIER_PREFIX + t.name}
                onClick={() => { set('tier', TIER_PREFIX + t.name); close() }}>{t.name}</MenuItem>
            ))}
          </>
        )}
      </MenuButton>
    </>
  )

  const CHIP_LABEL = {
    membership: v => v === 'Player' ? 'Players' : v === 'External' ? 'Not members' : label(v, TYPE_PREFIX),
    role: v => (ROLE_SEGS.find(r => r.seg === v) || {}).label || v,
    honour: v => v + 's',
    gender: v => GENDER_LABEL[label(v, GENDER_PREFIX)] || label(v, GENDER_PREFIX),
    squad: v => 'Squad: ' + label(v, SQUAD_PREFIX),
    tier: v => 'Tier: ' + label(v, TIER_PREFIX),
  }
  const chips = anyOn ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {active.map(([k, v]) => (
        <FilterChip key={k} onClear={() => setF(s => ({ ...s, [k]: null }))}>{CHIP_LABEL[k](v)}</FilterChip>
      ))}
      <button onClick={() => setF({ membership: null, role: null, honour: null, gender: null, squad: null, tier: null })}
        style={{ padding: '5px 10px', borderRadius: 7, fontSize: 12, border: 'none', background: 'transparent', color: C.faint, cursor: 'pointer' }}>
        Clear all
      </button>
    </div>
  ) : null

  return { menus, chips, matches, anyOn, failed, loading: people === null }
}
