import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { PbSpinner, Card, Btn, Label, Select } from '../../../lib/presskit'
import { battingHandLabel, bowlingLabel, bowlingFromLabel, genderLabel, normalizeGender, bowls } from '../../../lib/playerAttributes'

const fmt = (v) => {
  if (v === null || v === undefined || v === '') return '—'
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}
const sameSet = (a, b) => {
  const A = new Set(a || []), B = new Set(b || [])
  return A.size === B.size && [...A].every(x => B.has(x))
}
// "gender · role · batting · bowling [· opener]" — empties dropped.
const summaryLine = (vals, opener) => {
  const parts = vals.filter(v => v !== null && v !== undefined && v !== '').map(String)
  if (opener === true) parts.push('opener')
  return parts.length ? parts.join(' · ') : '—'
}

// Name matching tolerant of double spaces (empty middle name), suffixes and word
// order — "Eadon-Clarke Jnr, Chas" should still find KlubPro's "Chas Eadon-Clarke".
const _SUFFIXES = new Set(['jnr', 'snr', 'jr', 'sr', 'ii', 'iii', 'iv'])
const normName = (s) => (s || '').toString().toLowerCase().replace(/[,]/g, ' ').replace(/\s+/g, ' ').trim()
const nameTokens = (s) => normName(s).split(' ').filter(t => t && !_SUFFIXES.has(t))

// KlubPro stages display labels; BetterStats stores codes. Normalise both to a
// comparable code so e.g. 'RIGHT' (stored) and "Right handed" (staged) match, and
// render BetterStats codes back to labels so the card reads cleanly.
const battingCode = (v) => {
  const s = (v == null ? '' : String(v)).trim().toLowerCase()
  if (['right', 'right handed', 'right-handed', 'rhb', 'r'].includes(s)) return 'RIGHT'
  if (['left', 'left handed', 'left-handed', 'lhb', 'l'].includes(s)) return 'LEFT'
  return null
}
const bowlingType = (v) => {
  if (v == null || v === '') return null
  const fromLabel = bowlingFromLabel(String(v).trim())
  if (fromLabel.bowling_type) return fromLabel.bowling_type
  const up = String(v).trim().toUpperCase().replace(/[ -]/g, '_')
  return ['FAST', 'FAST_MEDIUM', 'MEDIUM', 'MEDIUM_FAST', 'FINGER_SPIN', 'WRIST_SPIN'].includes(up) ? up : null
}
const roleCode = (v) => (v == null ? '' : String(v).trim().toLowerCase())
const bsBattingLabel = (bs) => battingHandLabel(bs.batting_hand) || bs.batting_hand || null
const bsBowlingLabel = (bs) => {
  const lbl = bowls(bs.bowling_action, bs.bowling_type) ? bowlingLabel(bs.bowling_action, bs.bowling_type) : null
  return (lbl && lbl !== '—') ? lbl : (bs.bowling_type || null)
}

// Per-field comparison for one matched pair (label display + normalised compare).
function compareFields(bs, cand) {
  const kpHasPhoto = !!(cand.profile_image_found || cand.thumbnail_image_found)
  const bsHasPhoto = !!bs.has_photo
  const out = []
  const row = (key, label, current, incoming, emptyIncoming, differ) =>
    out.push({ key, label, current, incoming, emptyIncoming, differ, recommended: !emptyIncoming })

  const gI = normalizeGender(cand.gender) || null, gC = normalizeGender(bs.gender) || null
  row('gender', 'Gender', genderLabel(bs.gender), cand.gender ? genderLabel(cand.gender) : null, !gI, gI !== gC)
  row('email', 'Email', bs.email, cand.email, !cand.email, (cand.email || '') !== (bs.email || ''))
  row('phone', 'Phone', bs.phone, cand.mobile, !cand.mobile, (cand.mobile || '') !== (bs.phone || ''))
  const rI = cand.betterstats_player_role
  row('player_role', 'Role', bs.player_role, rI, !rI, roleCode(rI) !== roleCode(bs.player_role))
  const bI = battingCode(cand.betterstats_batting_hand)
  row('batting_hand', 'Batting hand', bsBattingLabel(bs), cand.betterstats_batting_hand || null, !bI, bI !== battingCode(bs.batting_hand))
  const wI = bowlingType(cand.betterstats_bowling_type)
  row('bowling_type', 'Bowling type', bsBowlingLabel(bs), cand.betterstats_bowling_type || null, !wI, wI !== bowlingType(bs.bowling_type))
  const oI = cand.betterstats_is_opening_batsman
  out.push({ key: 'is_opening_batsman', label: 'Opening batter', current: bs.is_opening_batsman, incoming: oI, emptyIncoming: oI !== true, differ: oI !== bs.is_opening_batsman, recommended: oI === true })
  const sI = cand.betterstats_skill_positions
  out.push({ key: 'skill_positions', label: 'Skills', current: bs.skill_positions, incoming: sI, emptyIncoming: !(sI && sI.length), differ: !sameSet(sI, bs.skill_positions), recommended: !!(sI && sI.length) })
  // profile image: checked whenever KlubPro has one (untick to keep a newer BS photo)
  out.push({ key: 'profile_image', label: 'Profile image', photo: true, current: bsHasPhoto ? 'image' : null, incoming: kpHasPhoto ? 'image' : null, emptyIncoming: !kpHasPhoto, differ: kpHasPhoto !== bsHasPhoto, recommended: kpHasPhoto })
  return out
}
function recommendedMap(bs, cand) {
  const m = {}
  for (const c of compareFields(bs, cand)) m[c.key] = c.recommended
  return m
}

function Avatar({ url, name }) {
  const [ok, setOk] = useState(true)
  const initials = (name || '?').split(/[\s,]+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase()
  if (!url || !ok) {
    return (
      <div className="w-12 h-12 rounded-full bg-pb-surface2 border border-pb-hairline2 flex items-center justify-center text-pb-faint font-mono text-[11px] shrink-0">
        {initials || '—'}
      </div>
    )
  }
  return <img src={url} alt={name} onError={() => setOk(false)}
    className="w-12 h-12 rounded-full object-cover border border-pb-hairline2 shrink-0" />
}

function StatusBadge({ status, score, imported }) {
  if (imported) {
    return <span className="font-mono text-[10px] px-1.5 py-0.5 rounded border text-green-300 border-green-400/30">IMPORTED ✓</span>
  }
  const map = {
    approved: ['APPROVED · NOT IMPORTED', 'text-blue-300 border-blue-400/30'],
    rejected: ['REJECTED', 'text-pb-red/70 border-pb-red/30'],
    skipped: ['SKIPPED', 'text-pb-faint border-pb-faint/30'],
  }
  let [label, tone] = map[status] || [null, '']
  if (!label) {
    label = score != null ? `SUGGESTED ${Math.round(score * 100)}%` : 'NO MATCH'
    tone = score != null ? 'text-pb-amber border-pb-amber/30' : 'text-pb-red/70 border-pb-red/30'
  }
  return <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${tone}`}>{label}</span>
}

export default function KlubproPlayers({ clubMapping }) {
  const toast = useToast()
  const cm = clubMapping.id
  const [data, setData] = useState(null)
  const [rows, setRows] = useState({})        // bsId -> { candId, fields, status, score }
  const [expanded, setExpanded] = useState(() => new Set())
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [picker, setPicker] = useState(null)
  const [dry, setDry] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setData(null); setDry(null)
    try {
      const d = await api.kpPlayers(cm)
      setData(d)
      const candById = {}
      for (const c of (d.klubpro_candidates || [])) candById[c.klubpro_player_id] = c
      const bsById = {}
      for (const p of (d.betterstats_players || [])) bsById[p.id] = p
      const r = {}
      for (const p of (d.betterstats_players || [])) {
        const m = (d.matches || []).find(x => x.betterstats_player_id === p.id)
        const candId = m?.klubpro_player_id || null
        const cand = candId ? candById[candId] : null
        let status = 'pending'
        if (m?.approved) status = 'approved'
        else if (m?.match_status === 'reject' || m?.match_status === 'rejected') status = 'rejected'
        else if (m?.match_status === 'skip' || m?.match_status === 'skipped') status = 'skipped'
        const hasStored = m?.migrate_fields && Object.keys(m.migrate_fields).length
        r[p.id] = {
          candId,
          score: m?.match_score ?? null,
          status,
          imported: !!m?.imported_at,
          fields: cand ? (hasStored ? { ...recommendedMap(p, cand), ...m.migrate_fields } : recommendedMap(p, cand)) : {},
        }
      }
      setRows(r)
    } catch (e) { toast.error(e.message) }
  }, [cm, toast])

  useEffect(() => { load() }, [load])

  const candById = useMemo(() => {
    const m = {}
    for (const c of (data?.klubpro_candidates || [])) m[c.klubpro_player_id] = c
    return m
  }, [data])
  const bsById = useMemo(() => {
    const m = {}
    for (const p of (data?.betterstats_players || [])) m[p.id] = p
    return m
  }, [data])

  const setRow = (bsId, patch) => setRows(prev => ({ ...prev, [bsId]: { ...prev[bsId], ...patch } }))
  const setField = (bsId, key, val) => {
    setDry(null)
    setRows(prev => ({ ...prev, [bsId]: { ...prev[bsId], fields: { ...prev[bsId].fields, [key]: val } } }))
  }
  const toggleExpand = (bsId) => setExpanded(prev => {
    const n = new Set(prev); n.has(bsId) ? n.delete(bsId) : n.add(bsId); return n
  })

  const checkAll = (bsId) => {
    const bs = bsById[bsId], cand = candById[rows[bsId]?.candId]
    if (!cand) return
    const f = {}
    for (const c of compareFields(bs, cand)) f[c.key] = !c.emptyIncoming
    setDry(null); setRow(bsId, { fields: f })
  }
  const uncheckAll = (bsId) => {
    const f = {}; for (const x of FIELDS) f[x.key] = false
    setDry(null); setRow(bsId, { fields: f })
  }
  const resetRec = (bsId) => {
    const bs = bsById[bsId], cand = candById[rows[bsId]?.candId]
    if (!cand) return
    setDry(null); setRow(bsId, { fields: recommendedMap(bs, cand) })
  }

  // Persist a decision for one player.
  const decide = async (bsId, decision) => {
    const bs = bsById[bsId], row = rows[bsId]
    const cand = decision === 'approve' ? candById[row?.candId] : null
    if (decision === 'approve' && !cand) { toast.error('No KlubPro player matched'); return }
    try {
      await api.kpSetMatch(cm, {
        betterstats_player_id: bsId,
        betterstats_player_name: bs.name,
        klubpro_player_id: cand?.klubpro_player_id || null,
        klubpro_player_firstname: cand?.firstname || null,
        klubpro_player_lastname: cand?.lastname || null,
        klubpro_player_nickname: cand?.nickname || null,
        decision,
        migrate_fields: decision === 'approve' ? row.fields : undefined,
      })
      setDry(null)
      setRow(bsId, { status: decision === 'approve' ? 'approved' : decision === 'reject' ? 'rejected' : 'skipped' })
    } catch (e) { toast.error(e.message) }
  }

  const pickCandidate = (bsId, cand) => {
    const bs = bsById[bsId]
    setDry(null)
    setRow(bsId, { candId: cand.klubpro_player_id, score: null, status: 'pending', fields: recommendedMap(bs, cand) })
    setExpanded(prev => new Set(prev).add(bsId))
    setPicker(null)
  }

  // ── derived sets ────────────────────────────────────────────────────────────
  const eligible = useMemo(() => // have a candidate and not rejected/skipped
    Object.entries(rows).filter(([, r]) => r.candId && r.status !== 'rejected' && r.status !== 'skipped'),
    [rows])

  const counts = useMemo(() => {
    const all = Object.values(rows)
    return {
      total: all.length,
      approved: all.filter(r => r.status === 'approved').length,
      imported: all.filter(r => r.imported).length,
      // approved decisions whose data hasn't been written to BetterStats yet
      toImport: all.filter(r => r.status === 'approved' && !r.imported).length,
      pending: all.filter(r => r.candId && r.status === 'pending').length,
      eligible: eligible.length,
    }
  }, [rows, eligible])

  const visible = useMemo(() => {
    const term = normName(q)
    return (data?.betterstats_players || []).filter(p => {
      if (term && !normName(p.name).includes(term)) return false
      const r = rows[p.id]; if (!r) return false
      const cand = r.candId ? candById[r.candId] : null
      switch (filter) {
        case 'unreviewed': return r.status === 'pending'
        case 'reviewed': return r.status !== 'pending'
        case 'approved': return r.status === 'approved'
        case 'rejected': return r.status === 'rejected'
        case 'skipped': return r.status === 'skipped'
        case 'image_on': return !!r.fields?.profile_image
        case 'image_off': return cand && (cand.profile_image_found || cand.thumbnail_image_found) && !r.fields?.profile_image
        case 'differences': return cand && compareFields(p, cand).some(c => c.differ)
        case 'missing': return cand && compareFields(p, cand).some(c => c.emptyIncoming)
        default: return true
      }
    })
  }, [data, rows, candById, q, filter])

  // ── bulk approve ─────────────────────────────────────────────────────────────
  const bulkSummary = useMemo(() => {
    let fieldsSel = 0, fieldsSkip = 0, imgOn = 0, imgOff = 0, warn = 0
    for (const [bsId, r] of eligible) {
      const cand = candById[r.candId]; if (!cand) continue
      const cmp = compareFields(bsById[bsId], cand)
      let rowDiff = false
      for (const c of cmp) {
        const sel = !!r.fields[c.key]
        if (sel && !c.emptyIncoming) fieldsSel++; else fieldsSkip++
        if (c.key === 'profile_image') { if (sel && !c.emptyIncoming) imgOn++; else if (!c.emptyIncoming) imgOff++ }
        if (c.differ) rowDiff = true
      }
      if (rowDiff) warn++
    }
    return { players: eligible.length, fieldsSel, fieldsSkip, imgOn, imgOff, warn }
  }, [eligible, candById, bsById])

  const bulkApprove = async () => {
    const s = bulkSummary
    if (!s.players) { toast.info('No eligible players to approve.'); return }
    if (!window.confirm(
      `Approve all reviewed player matches using the currently selected field-level migration settings?\n\n` +
      `Players: ${s.players}\nFields to migrate: ${s.fieldsSel}\nFields skipped: ${s.fieldsSkip}\n` +
      `Image replacements: ${s.imgOn} (skipped ${s.imgOff})\nPlayers with differences: ${s.warn}`
    )) return
    setBusy(true)
    try {
      const items = eligible.map(([bsId, r]) => {
        const c = candById[r.candId] || {}
        return {
          betterstats_player_id: bsId,
          betterstats_player_name: bsById[bsId]?.name,
          klubpro_player_id: r.candId,
          klubpro_player_firstname: c.firstname || null,
          klubpro_player_lastname: c.lastname || null,
          klubpro_player_nickname: c.nickname || null,
          migrate_fields: r.fields,
        }
      })
      const res = await api.kpBulkApprove(cm, items)
      toast.success(`Approved ${res.approved}${res.failed ? `, ${res.failed} failed` : ''}`)
      await load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const runDryRun = async () => {
    try {
      const r = await api.kpPlayerDryRun(cm)
      setDry(r)
      if (!r.players_changing) toast.info('Nothing to change — approved matches already match the selected data.')
    } catch (e) { toast.error(e.message) }
  }
  const runImport = async () => {
    // Approve only records the decision; this is the step that writes to BetterStats.
    const n = counts.toImport || dry?.players_changing || 0
    if (!window.confirm(`Import ${n} approved player${n === 1 ? '' : 's'} into BetterStats now? Only the ticked fields are written, a backup is taken, and you can roll back from History.`)) return
    setBusy(true)
    try {
      const r = await api.kpPlayerImport(cm)
      toast.success(`Imported — ${r.updated} updated, ${r.skipped} skipped`)
      await load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (!data) return <PbSpinner message="Loading players…" />

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-4 text-[13px] flex-wrap">
            <span className="text-pb-dim">{counts.total} players</span>
            <span className="text-blue-300">{counts.approved} approved</span>
            <span className="text-green-300">{counts.imported} imported</span>
            <span className="text-pb-amber">{counts.pending} pending</span>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Btn onClick={bulkApprove} disabled={!counts.eligible || busy}>Bulk approve ({counts.eligible})</Btn>
            <Btn onClick={runDryRun}>Dry run</Btn>
            <Btn primary disabled={!counts.toImport || busy} onClick={runImport}>
              {busy ? 'Working…' : `Import${counts.toImport ? ` ${counts.toImport}` : ''}`}
            </Btn>
          </div>
        </div>
        {counts.toImport > 0 && (
          <div className="mt-2 text-[12px] text-pb-amber">
            {counts.toImport} approved player{counts.toImport === 1 ? ' is' : 's are'} not written to BetterStats yet —
            approving only records your choices. Click <span className="font-semibold">Import</span> to apply them
            (run <span className="font-semibold">Dry run</span> first to preview).
          </div>
        )}
        <div className="flex flex-wrap gap-2 mt-3 items-center">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players…"
            className="bg-pb-surface2 border border-pb-hairline2 rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
          <Select value={filter} onChange={e => setFilter(e.target.value)} className="max-w-[240px]">
            <option value="all">All</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="reviewed">Reviewed</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="skipped">Skipped</option>
            <option value="image_on">Image replacement selected</option>
            <option value="image_off">Image replacement deselected</option>
            <option value="differences">Has field differences</option>
            <option value="missing">Has missing KlubPro values</option>
          </Select>
          <span className="text-pb-faint text-[12px]">{visible.length} shown</span>
        </div>
      </Card>

      {dry && (
        <Card title={`Dry-run — ${dry.players_changing} players changing · ${dry.field_writes} field writes · ${dry.images_replacing || 0} image replacements`}>
          {dry.players_changing === 0 ? (
            <p className="text-pb-faint text-sm">No changes — approved matches already match the selected data.</p>
          ) : (
            <div className="space-y-3">
              {dry.previews.filter(p => p.error || p.row_changes > 0).map(p => (
                <div key={p.betterstats_player_id} className="pb-hairline-t pt-2 first:pt-0 first:border-0">
                  <div className="text-sm text-pb-text">{p.betterstats_player_name}{p.error && <span className="text-pb-red/70 text-[12px]"> · {p.error}</span>}</div>
                  {!p.error && (
                    <div className="flex flex-wrap gap-x-5 gap-y-0.5 mt-1">
                      {p.diffs.filter(d => d.change).map(d => (
                        <span key={d.field} className="text-[12px] text-pb-faint">
                          <span className="text-pb-faintest">{d.label}:</span>{' '}
                          <span className="line-through opacity-50">{fmt(d.current)}</span>{' '}
                          <span style={{ color: 'var(--pb-accent)' }}>→ {fmt(d.incoming)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <div className="space-y-2">
        {visible.map(bs => (
          <PlayerRow key={bs.id} bs={bs} row={rows[bs.id]} cand={rows[bs.id]?.candId ? candById[rows[bs.id].candId] : null}
            expanded={expanded.has(bs.id)} onToggle={() => toggleExpand(bs.id)}
            onField={(k, v) => setField(bs.id, k, v)}
            onCheckAll={() => checkAll(bs.id)} onUncheckAll={() => uncheckAll(bs.id)} onReset={() => resetRec(bs.id)}
            onApprove={() => decide(bs.id, 'approve')} onReject={() => decide(bs.id, 'reject')}
            onSkip={() => decide(bs.id, 'skip')} onChange={() => setPicker(bs)} />
        ))}
        {!visible.length && <Card><p className="text-pb-faint text-sm">No players match this filter.</p></Card>}
      </div>

      {picker && (
        <CandidatePicker bs={picker} candidates={data.klubpro_candidates}
          onPick={(c) => pickCandidate(picker.id, c)} onClose={() => setPicker(null)} />
      )}
    </div>
  )
}

function FieldImage({ url }) {
  const [ok, setOk] = useState(true)
  if (!url || !ok) return <div className="w-10 h-10 rounded bg-pb-surface2 border border-pb-hairline2 flex items-center justify-center text-pb-faintest text-[9px]">none</div>
  return <img src={url} onError={() => setOk(false)} className="w-10 h-10 rounded object-cover border border-pb-hairline2" alt="" />
}

function PlayerRow({ bs, row, cand, expanded, onToggle, onField, onCheckAll, onUncheckAll, onReset, onApprove, onReject, onSkip, onChange }) {
  const cmp = useMemo(() => (cand ? compareFields(bs, cand) : []), [bs, cand])
  const selCount = cand ? cmp.filter(c => row?.fields?.[c.key] && !c.emptyIncoming).length : 0
  const imgSel = !!row?.fields?.profile_image && !!(cand && (cand.profile_image_found || cand.thumbnail_image_found))

  return (
    <Card pad="p-3">
      {/* Rich side-by-side summary — always visible (no need to open Fields) */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-3 items-start">
        {/* Left: BetterStats current */}
        <div className="flex gap-3 min-w-0">
          <Avatar url={bs.has_photo ? api.bsPlayerPhotoUrl(bs.id) : null} name={bs.name} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-pb-text font-medium">{bs.name}</span>
              <StatusBadge status={row?.status} score={row?.status === 'pending' ? row?.score : null} imported={row?.imported} />
            </div>
            <div className="text-[11px] text-pb-faint mt-0.5 leading-snug">
              {summaryLine([genderLabel(bs.gender), bs.player_role, bsBattingLabel(bs), bsBowlingLabel(bs)], bs.is_opening_batsman)}
            </div>
            <div className="text-[11px] text-pb-faint leading-snug">{fmt(bs.email)} · {fmt(bs.phone)}</div>
            <div className="text-[11px] text-pb-faint leading-snug">{bs.skill_positions?.length ? bs.skill_positions.join(', ') : 'no skills'}</div>
          </div>
        </div>
        {/* divider */}
        <div className="hidden md:flex items-center text-pb-faintest self-center">↔</div>
        {/* Right: KlubPro staged */}
        <div className="flex gap-3 min-w-0 pt-2 md:pt-0 border-t md:border-t-0 border-pb-hairline2">
          {cand ? (
            <>
              <Avatar url={(cand.profile_image_found || cand.thumbnail_image_found)
                ? api.kpPlayerImageUrl(cand.klubpro_player_id, cand.thumbnail_image_found) : null}
                name={`${cand.firstname || ''} ${cand.lastname || ''}`} />
              <div className="min-w-0">
                <span className="text-sm text-pb-text">
                  {[cand.firstname, cand.lastname].filter(Boolean).join(' ')}
                  {cand.nickname ? <span className="text-pb-faint"> “{cand.nickname}”</span> : null}
                </span>
                <div className="text-[11px] text-pb-faint mt-0.5 leading-snug">
                  {summaryLine([genderLabel(cand.gender), cand.betterstats_player_role, cand.betterstats_batting_hand, cand.betterstats_bowling_type], cand.betterstats_is_opening_batsman)}
                </div>
                <div className="text-[11px] text-pb-faint leading-snug">{fmt(cand.email)} · {fmt(cand.mobile)}</div>
                <div className="text-[11px] text-pb-faint leading-snug">{cand.betterstats_skill_positions?.length ? cand.betterstats_skill_positions.join(', ') : 'no skills'}</div>
              </div>
            </>
          ) : (
            <div className="text-pb-faintest text-[13px] self-center">No KlubPro match selected</div>
          )}
        </div>
      </div>

      {/* secondary detail + actions */}
      <div className="flex items-center justify-between gap-2 flex-wrap mt-2.5">
        <span className="text-[11px] text-pb-faintest">
          {cand ? `${selCount} field${selCount === 1 ? '' : 's'} selected${imgSel ? ' · image replace' : ''}` : ''}
        </span>
        <div className="flex gap-2 flex-wrap justify-end">
          {cand && <Btn sm onClick={onToggle}>{expanded ? 'Hide fields' : 'Fields'}</Btn>}
          <Btn sm onClick={onChange}>{cand ? 'Change' : 'Find match'}</Btn>
          {cand && <Btn sm primary onClick={onApprove}>{row?.status === 'approved' ? 'Re-approve' : 'Approve'}</Btn>}
          {cand && <Btn sm onClick={onReject}>Reject</Btn>}
          <Btn sm onClick={onSkip}>Skip</Btn>
        </div>
      </div>

      {cand && expanded && (
        <div className="mt-3 pt-3 pb-hairline-t">
          <div className="flex items-center justify-between mb-2">
            <div className="grid grid-cols-[1.4rem,8rem,1fr,1fr] gap-2 text-[10px] font-mono uppercase tracking-wide2 text-pb-faintest w-full max-w-2xl">
              <span></span><span>Field</span><span>BetterStats (current)</span><span>KlubPro (staged)</span>
            </div>
          </div>
          <div className="space-y-1 max-w-2xl">
            {cmp.map(c => {
              const checked = !!row.fields[c.key]
              const disabled = c.emptyIncoming
              return (
                <div key={c.key} className={`grid grid-cols-[1.4rem,8rem,1fr,1fr] gap-2 items-center py-0.5 ${c.differ ? 'rounded' : ''}`}>
                  <input type="checkbox" checked={checked && !disabled} disabled={disabled}
                    onChange={e => onField(c.key, e.target.checked)}
                    className="w-4 h-4 accent-[var(--pb-accent)]" />
                  <span className="text-[12px] text-pb-dim flex items-center gap-1">
                    {c.label}{c.differ && <span className="w-1.5 h-1.5 rounded-full bg-pb-amber inline-block" title="differs" />}
                  </span>
                  {c.photo ? (
                    <FieldImage url={bs.has_photo ? api.bsPlayerPhotoUrl(bs.id) : null} />
                  ) : (
                    <span className="text-[12px] text-pb-faint truncate">{fmt(c.current)}</span>
                  )}
                  {c.photo ? (
                    <FieldImage url={(cand.profile_image_found || cand.thumbnail_image_found) ? api.kpPlayerImageUrl(cand.klubpro_player_id, cand.thumbnail_image_found) : null} />
                  ) : (
                    <span className={`text-[12px] truncate ${disabled ? 'text-pb-faintest' : c.differ ? 'text-pb-text' : 'text-pb-faint'}`}
                      style={c.differ && !disabled ? { color: 'var(--pb-accent)' } : {}}>
                      {disabled ? '— no value —' : fmt(c.incoming)}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
          <div className="flex gap-2 mt-2">
            <Btn sm onClick={onCheckAll}>Check all</Btn>
            <Btn sm onClick={onUncheckAll}>Uncheck all</Btn>
            <Btn sm onClick={onReset}>Reset to recommended</Btn>
          </div>
        </div>
      )}
    </Card>
  )
}

function CandidatePicker({ bs, candidates, onPick, onClose }) {
  // Seed with the cleaned name (no comma, no suffix, single spaces).
  const [q, setQ] = useState(() => nameTokens(bs.name).join(' '))
  const list = useMemo(() => {
    const tokens = nameTokens(q)
    const arr = candidates.filter(c => {
      const hay = normName(`${c.firstname || ''} ${c.lastname || ''} ${c.nickname || ''}`)
      // every search token must appear — order/middle-name/double-space tolerant
      return tokens.every(t => hay.includes(t))
    })
    return arr.slice(0, 60)
  }, [candidates, q])

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="pb-card p-4 max-w-lg w-full mt-12" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <Label>Pick KlubPro player for {bs.name}</Label>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text text-lg leading-none">×</button>
        </div>
        <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search KlubPro players…"
          className="w-full bg-pb-surface2 border border-pb-hairline2 rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent mb-3" />
        <div className="space-y-1 max-h-[50vh] overflow-y-auto">
          {list.map(c => (
            <button key={c.klubpro_player_id} onClick={() => onPick(c)}
              className="w-full flex items-center gap-3 text-left px-2 py-1.5 rounded hover:bg-pb-surface2">
              <FieldImage url={(c.thumbnail_image_found || c.profile_image_found) ? api.kpPlayerImageUrl(c.klubpro_player_id, c.thumbnail_image_found) : null} />
              <span className="text-sm text-pb-text">
                {[c.firstname, c.lastname].filter(Boolean).join(' ')}
                {c.nickname ? <span className="text-pb-faint"> “{c.nickname}”</span> : null}
                <span className="text-pb-faintest text-[11px] block">{fmt(c.email)} · {fmt(c.mobile)}</span>
              </span>
            </button>
          ))}
          {!list.length && <p className="text-pb-faint text-sm px-2 py-3">No candidates found.</p>}
        </div>
      </div>
    </div>
  )
}
