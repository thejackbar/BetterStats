import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import {
  Button, FilterPill, SearchInput, StatCard, StatReadout,
  Modal, Field, TextInput, Select, TextArea, Checkbox, Note, Badge,
} from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}
const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function StatusPill({ status }) {
  if (status === 'financial') return <Badge toneKey="ok">Financial</Badge>
  if (status === 'non_financial') return <Badge toneKey="warn">Owes</Badge>
  if (status === 'needs_tier') return <Badge>Needs tier</Badge>
  return null
}

function AddMemberModal({ seasonId, tiers, membershipTypes, onClose, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ full_name: '', email: '', mobile: '', fee_schedule_id: '', membership_type_id: '' })
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!form.full_name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      await api.feeCreateMember({
        season_id: seasonId, full_name: form.full_name.trim(),
        email: form.email.trim() || null, mobile: form.mobile.trim() || null,
        fee_schedule_id: form.fee_schedule_id || null,
        membership_type_id: form.membership_type_id || null,
      })
      toast.success('Member added'); onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal
      onClose={onClose}
      title="Add a person"
      subtitle="For non-playing members (life members, sponsors, ICL). Players who appear in a game are added automatically."
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={busy || !form.full_name.trim()}>
          {busy ? 'Adding…' : 'Add member'}
        </Button>
      </>}
    >
      <div className="grid gap-3">
        <Field label="Full name *">
          <TextInput autoFocus placeholder="Surname, First" value={form.full_name}
            onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Email">
            <TextInput value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </Field>
          <Field label="Mobile">
            <TextInput value={form.mobile} onChange={e => setForm(f => ({ ...f, mobile: e.target.value }))} />
          </Field>
        </div>
        <Field label="Tier">
          <Select value={form.fee_schedule_id} onChange={e => setForm(f => ({ ...f, fee_schedule_id: e.target.value }))}>
            <option value="">— Needs tier —</option>
            {tiers.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Membership type">
          <Select value={form.membership_type_id} onChange={e => setForm(f => ({ ...f, membership_type_id: e.target.value }))}>
            <option value="">— None —</option>
            {membershipTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
      </div>
    </Modal>
  )
}

function ImportMembersModal({ seasonId, onClose, onDone }) {
  const toast = useToast()
  const [text, setText] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)

  function onFile(file) { if (!file) return; const rd = new FileReader(); rd.onload = () => { setText(String(rd.result || '')); setPreview(null) }; rd.readAsText(file) }
  async function runPreview() { setBusy(true); try { setPreview(await api.feeMembersImportPreview(text)) } catch (e) { toast.error(e.message) } finally { setBusy(false) } }
  async function runImport() {
    setBusy(true)
    try {
      const r = await api.feeMembersImportCommit(text, seasonId)
      toast.success(`Imported — ${r.created} added, ${r.updated} updated, ${r.added_to_season} into this season`)
      onDone()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal
      onClose={onClose} width={560}
      title="Import members from CSV"
      subtitle={<>
        Non-playing members (parents, life members, sponsors…). Columns:{' '}
        <span className="font-mono text-[11px]">name, email, mobile, category, roles</span> (only{' '}
        <span className="font-mono text-[11px]">name</span> required). Matched to existing people by name, so a re-run
        tops up rather than duplicates. Each imported person is opened into this season as “needs tier”. Players are
        imported in Stats.
      </>}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        {!preview
          ? <Button variant="primary" onClick={runPreview} disabled={busy || !text.trim()}>{busy ? 'Reading…' : 'Preview'}</Button>
          : <Button variant="primary" onClick={runImport} disabled={busy || preview.total === 0}>{busy ? 'Importing…' : `Import ${preview.total}`}</Button>}
      </>}
    >
      <input type="file" accept=".csv,text/csv" onChange={e => onFile(e.target.files?.[0])}
        className="block text-pb-dim text-[12.5px] mb-2.5" />
      <TextArea value={text} onChange={e => { setText(e.target.value); setPreview(null) }} rows={5}
        placeholder={'name,email,mobile,category,roles\nJane Doe,jane@x.com,0400000000,parent,"Canteen Manager, First Aid Officer"'}
        className="font-mono !text-[11.5px] resize-y" />
      {preview && (
        <div className="mt-3 bg-pb-surface2 border border-pb-hairline2 rounded-lg p-3">
          <div className="text-pb-text text-[13px] mb-2">{preview.total} row{preview.total === 1 ? '' : 's'}: <b>{preview.new}</b> new, <b>{preview.existing}</b> existing.</div>
          <div className="max-h-40 overflow-y-auto pb-scroll space-y-1">
            {preview.rows.map((r, i) => (
              <div key={i} className="text-[12px] text-pb-dim flex gap-2 items-baseline">
                <span className={`font-mono text-[9px] w-12 shrink-0 ${r.existing ? 'text-pb-amber' : 'text-green-300'}`}>{r.existing ? 'UPDATE' : 'NEW'}</span>
                <span className="text-pb-text">{r.name}</span>
                {r.category && <span className="font-mono text-[9.5px] text-pb-faint">{r.category}</span>}
                {r.roles.length > 0 && <span className="font-mono text-[9.5px]" style={{ color: 'var(--pb-accent-ink)' }}>{r.roles.join(', ')}</span>}
                {r.unknown_roles.length > 0 && <span className="font-mono text-[9.5px] text-pb-amber" title="Not a known role — skipped">?{r.unknown_roles.join(', ')}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}

function BulkTierModal({ seasonId, memberIds, tiers, onClose, onSaved }) {
  const toast = useToast()
  const [tierId, setTierId] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit() {
    setBusy(true)
    try {
      const r = await api.feeBulkSetTier(seasonId, memberIds, tierId || null)
      toast.success(`Tier set on ${r.updated} member${r.updated === 1 ? '' : 's'}`)
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal
      onClose={onClose}
      title={`Set tier for ${memberIds.length} member${memberIds.length === 1 ? '' : 's'}`}
      subtitle="Updates each member's tier for this season, and carries the new tier forward as their default for next season's rollover."
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Apply'}</Button>
      </>}
    >
      <Field label="Tier">
        <Select autoFocus value={tierId} onChange={e => setTierId(e.target.value)}>
          <option value="">— Clear tier (needs review) —</option>
          {tiers.map(t => <option key={t.id} value={t.id}>{t.name} ({t.payment_type})</option>)}
        </Select>
      </Field>
    </Modal>
  )
}

function RolloverModal({ seasonId, fromSeason, onClose, onDone }) {
  const toast = useToast()
  const [includeLeft, setIncludeLeft] = useState(false)
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true)
    try {
      const r = await api.feeRollover(seasonId, fromSeason.id, includeLeft)
      toast.success(`Rolled over ${r.created} member${r.created === 1 ? '' : 's'} (${r.skipped_left_club} left-club skipped)`)
      onDone()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal
      onClose={onClose}
      title={`Roll over from ${fromSeason.name}`}
      subtitle={`Opens this season for every member that was in ${fromSeason.name}. Each member's tier is carried across, matched by name against this season's rate card, so seed or copy the rate card first.`}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={go} disabled={busy}>{busy ? 'Rolling over…' : 'Roll over'}</Button>
      </>}
    >
      <Checkbox checked={includeLeft} onChange={setIncludeLeft}>
        Include “Left club” tiers
        <span className="text-pb-faintest"> · skipped by default</span>
      </Checkbox>
      <Note toneKey="calm" className="mt-3.5">
        Members who already exist in this season are skipped. Payments stay with the original season.
      </Note>
    </Modal>
  )
}

export default function AdminFeesMembers() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [data, setData] = useState(null)
  const [tiers, setTiers] = useState([])
  const [membershipTypes, setMembershipTypes] = useState([])
  const [q, setQ] = useState('')
  const [needsTierOnly, setNeedsTierOnly] = useState(false)
  const [owesOnly, setOwesOnly] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [recomputing, setRecomputing] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [showBulkTier, setShowBulkTier] = useState(false)
  const [showRollover, setShowRollover] = useState(false)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
    api.feeListMembershipTypes().then(d => setMembershipTypes(d.types || [])).catch(() => {})
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setData(null)
    setSelected(new Set())
    api.feeListMembers(seasonId).then(setData).catch(e => { toast.error(e.message); setData({ members: [], summary: {} }) })
    api.feeListSchedule(seasonId).then(setTiers).catch(() => setTiers([]))
  }, [seasonId])
  useEffect(() => { load() }, [load])

  // The next-most-recent season is the rollover source when this one is empty.
  const previousSeason = useMemo(() => {
    const idx = seasons.findIndex(s => s.id === seasonId)
    return idx >= 0 && idx + 1 < seasons.length ? seasons[idx + 1] : null
  }, [seasons, seasonId])

  async function recompute() {
    setRecomputing(true)
    try {
      const r = await api.feeRecompute(seasonId)
      toast.success(`Match days rebuilt — ${r.members_created} new members, ${r.entries_upserted} entries`)
      load()
    } catch (e) { toast.error(e.message) } finally { setRecomputing(false) }
  }

  const filtered = useMemo(() => {
    if (!data?.members) return []
    const needle = q.trim().toLowerCase()
    return data.members.filter(m =>
      (!needsTierOnly || m.needs_tier) &&
      (!owesOnly || m.status === 'non_financial') &&
      (!needle || m.full_name.toLowerCase().includes(needle) || (m.tier || '').toLowerCase().includes(needle))
    )
  }, [data, q, needsTierOnly, owesOnly])

  const s = data?.summary || {}

  // Header slots: the title, its live count, the filters and the primary action
  // all belong to the shell's sticky header now, which is why the old page-level
  // heading block and the "Showing N of M" footer line are both gone.
  const header = {
    title: 'Accounts',
    caption: `One balance per person · ${filtered.length} of ${data?.members?.length ?? 0} shown`,
    filters: (
      <div className="flex items-center gap-2 flex-wrap">
        <SearchInput value={q} onChange={setQ} placeholder="Search name or tier…" />
        <FilterPill active={!needsTierOnly && !owesOnly} onClick={() => { setNeedsTierOnly(false); setOwesOnly(false) }}>
          Everyone
        </FilterPill>
        <FilterPill warn active={owesOnly} onClick={() => setOwesOnly(v => !v)} count={s.non_financial}>
          Owes money
        </FilterPill>
        <FilterPill active={needsTierOnly} onClick={() => setNeedsTierOnly(v => !v)} count={s.needs_tier}>
          Needs tier
        </FilterPill>
      </div>
    ),
    stats: (
      <>
        <StatReadout value={money(s.total_outstanding)} label="Outstanding"
          ink={(s.total_outstanding ?? 0) > 0 ? '#f5b542' : undefined} />
        <StatReadout value={s.total_members ?? 0} label="People" />
      </>
    ),
    actions: (
      <>
        <Select value={seasonId} onChange={e => setSeasonId(e.target.value)} className="!w-auto max-w-[190px]">
          {seasons.map(se => <option key={se.id} value={se.id}>{se.name}</option>)}
        </Select>
        {previousSeason && <Button size="sm" onClick={() => setShowRollover(true)} disabled={!seasonId}>Roll over</Button>}
        <Button size="sm" onClick={() => setShowImport(true)} disabled={!seasonId}>Import</Button>
        <Button variant="primary" onClick={() => setShowAdd(true)} disabled={!seasonId}>Add member</Button>
      </>
    ),
  }

  return (
    <BetterFeesLayout {...header}>
      <div className="max-w-5xl">
        {data === null ? (
          <PbSpinner message="Loading accounts…" />
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-5">
              <StatCard label="People" value={s.total_members ?? 0} ink="var(--pb-text)" />
              <StatCard label="Owe money" value={s.non_financial ?? 0}
                ink={(s.non_financial ?? 0) > 0 ? '#f5b542' : 'var(--pb-text)'} />
              <StatCard label="Billed" value={money(s.total_payable)} ink="var(--pb-text)" />
              <StatCard label="Taken" value={money(s.total_paid)} ink="var(--pb-text)" />
              <StatCard label="Outstanding" value={money(s.total_outstanding)} accent />
            </div>

            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Button size="sm" onClick={recompute} disabled={recomputing}>
                {recomputing ? 'Syncing…' : 'Sync match days'}
              </Button>
            </div>

            {filtered.length === 0 ? (
              data.members.length === 0 && previousSeason ? (
                // First view of a new season → offer to roll forward from the prior one.
                <div className="pb-card p-6">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Open Season</p>
                  <p className="text-pb-text text-sm mb-1">No members yet for this season.</p>
                  <p className="text-pb-dim text-sm mb-4 leading-relaxed">
                    Roll forward everyone from <span className="text-pb-text">{previousSeason.name}</span> — each member keeps their tier
                    (so you only bulk-edit the exceptions, e.g. graduating students). Payments stay behind, "Left Club" members are skipped.
                  </p>
                  <div className="flex gap-2 flex-wrap">
                    <Button variant="primary" onClick={() => setShowRollover(true)}>
                      Roll over from {previousSeason.name}
                    </Button>
                    <Button onClick={recompute} disabled={recomputing}>
                      {recomputing ? 'Syncing…' : 'Just sync match days'}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="pb-card p-6 text-center">
                  <p className="text-pb-dim text-sm mb-1">
                    {data.members.length === 0 ? 'No members yet for this season.' : 'No members match your filter.'}
                  </p>
                  {data.members.length === 0 && (
                    <p className="font-mono text-[11px] text-pb-faint">
                      Set up the <Link to="/admin/fees/schedule" className="text-pb-accent underline">Fee Schedule</Link>, then hit “Sync Match Days”.
                    </p>
                  )}
                </div>
              )
            ) : (
              <>
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-2">
                  Tip: tick rows to bulk-assign a tier (e.g. promote graduating students to Senior in one go).
                </p>
                <div className="pb-card overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                        <th className="font-medium py-2.5 pl-5 pr-2 w-8">
                          <input type="checkbox"
                            checked={filtered.length > 0 && filtered.every(m => selected.has(m.member_id))}
                            onChange={e => {
                              if (e.target.checked) setSelected(new Set(filtered.map(m => m.member_id)))
                              else setSelected(new Set())
                            }}
                            className="cursor-pointer align-middle" />
                        </th>
                        <th className="font-medium py-2.5 pr-3">NAME</th>
                        <th className="font-medium py-2.5 pr-3">TYPE</th>
                        <th className="font-medium py-2.5 pr-3">TIER</th>
                        <th className="font-medium py-2.5 pr-3 w-16 text-right">DAYS</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">PAYABLE</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">PAID</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">OWED</th>
                        <th className="font-medium py-2.5 pr-5 w-28 text-right">STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map(m => {
                        const isSelected = selected.has(m.member_id)
                        return (
                          <tr key={m.member_season_id}
                            className={`pb-hairline-t align-middle ${isSelected ? 'bg-pb-surface2/60' : 'hover:bg-pb-surface2/40'} transition-colors`}>
                            <td className="py-2.5 pl-5 pr-2">
                              <input type="checkbox" checked={isSelected}
                                onChange={e => setSelected(s => {
                                  const n = new Set(s)
                                  if (e.target.checked) n.add(m.member_id); else n.delete(m.member_id)
                                  return n
                                })}
                                className="cursor-pointer align-middle" />
                            </td>
                            <td className="py-2.5 pr-3">
                              <Link to={`/admin/fees/member/${m.member_id}?season=${seasonId}`}
                                className="text-pb-text text-sm hover:text-pb-accent transition-colors inline-flex items-center gap-1.5">
                                {m.full_name}
                                {!m.is_linked && <Badge>Manual</Badge>}
                              </Link>
                            </td>
                            <td className="py-2.5 pr-3">
                              <span className="text-pb-dim text-[12px]">
                                {membershipTypes.find(t => t.id === m.membership_type_id)?.name || '—'}
                              </span>
                              {m.is_life_member && <Badge toneKey="accent" className="ml-1.5">Life</Badge>}
                              {m.is_honorary && <Badge className="ml-1.5">Honorary</Badge>}
                            </td>
                            <td className="py-2.5 pr-3">
                              {m.needs_tier
                                ? <span className="font-mono text-[10px] text-pb-amber">⚠ needs tier</span>
                                : <span className="text-pb-dim text-sm">{m.tier}</span>}
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{m.match_days || 0}</td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(m.total_payable)}</td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(m.total_paid)}</td>
                            <td className={`py-2.5 pr-3 text-right font-mono text-[11px] tabular-nums ${m.total_outstanding > 0 ? 'text-pb-text' : 'text-pb-faintest'}`}>
                              {money(m.total_outstanding)}
                            </td>
                            <td className="py-2.5 pr-5 text-right whitespace-nowrap">
                              {m.in_credit && (
                                <span title="In credit toward future games" className="mr-1.5 inline-block">
                                  <Badge toneKey="ok">+{money(m.credit)}</Badge>
                                </span>
                              )}
                              <StatusPill status={m.status} />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* Sticky bulk-action bar — appears when any row is checked. */}
      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-pb-surface border pb-hairline rounded-lg shadow-2xl px-4 py-3 flex items-center gap-3"
          style={{ borderColor: 'var(--pb-accent)' }}>
          <span className="font-mono text-[11px] text-pb-text">{selected.size} selected</span>
          <Button size="sm" variant="primary" onClick={() => setShowBulkTier(true)}>Set tier</Button>
          <Button size="sm" variant="quiet" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}

      {showAdd && (
        <AddMemberModal seasonId={seasonId} tiers={tiers} membershipTypes={membershipTypes}
          onClose={() => setShowAdd(false)}
          onCreated={() => { setShowAdd(false); load() }} />
      )}
      {showImport && (
        <ImportMembersModal seasonId={seasonId}
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); load() }} />
      )}
      {showBulkTier && (
        <BulkTierModal seasonId={seasonId} memberIds={Array.from(selected)} tiers={tiers}
          onClose={() => setShowBulkTier(false)}
          onSaved={() => { setShowBulkTier(false); setSelected(new Set()); load() }} />
      )}
      {showRollover && previousSeason && (
        <RolloverModal seasonId={seasonId} fromSeason={previousSeason}
          onClose={() => setShowRollover(false)}
          onDone={() => { setShowRollover(false); load() }} />
      )}
    </BetterFeesLayout>
  )
}
