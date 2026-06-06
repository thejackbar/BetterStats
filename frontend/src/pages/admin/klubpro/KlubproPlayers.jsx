import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { PbSpinner, Card, Btn, Label } from '../../../lib/presskit'

const FIELD_LABELS = {
  gender: 'Gender', email: 'Email', phone: 'Phone', player_role: 'Role',
  batting_hand: 'Batting hand', bowling_type: 'Bowling type',
  is_opening_batsman: 'Opening batter', skill_positions: 'Skills', photo: 'Photo',
}

const fmt = (v) => {
  if (v === null || v === undefined || v === '') return '—'
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
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

function StatusBadge({ match }) {
  let label = 'NO MATCH', tone = 'text-pb-red/70 border-pb-red/30'
  if (match?.approved) { label = 'APPROVED'; tone = 'text-green-300 border-green-400/30' }
  else if (match?.match_status === 'reject') { label = 'REJECTED'; tone = 'text-pb-red/70 border-pb-red/30' }
  else if (match?.match_status === 'skip') { label = 'SKIPPED'; tone = 'text-pb-faint border-pb-faint/30' }
  else if (match?.klubpro_player_id) {
    const pct = match.match_score != null ? ` ${Math.round(match.match_score * 100)}%` : ''
    label = `SUGGESTED${pct}`; tone = 'text-pb-amber border-pb-amber/30'
  }
  return <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${tone}`}>{label}</span>
}

export default function KlubproPlayers({ clubMapping }) {
  const toast = useToast()
  const cm = clubMapping.id
  const [data, setData] = useState(null)
  const [matches, setMatches] = useState({})   // bsId -> match row
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')  // all | suggested | approved | unmatched
  const [picker, setPicker] = useState(null)   // bs player being (re)matched
  const [dry, setDry] = useState(null)
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    setData(null); setDry(null)
    try {
      const d = await api.kpPlayers(cm)
      setData(d)
      const map = {}
      for (const m of (d.matches || [])) if (m.betterstats_player_id) map[m.betterstats_player_id] = m
      setMatches(map)
    } catch (e) { toast.error(e.message) }
  }, [cm, toast])

  useEffect(() => { load() }, [load])

  const candidatesById = useMemo(() => {
    const m = {}
    for (const c of (data?.klubpro_candidates || [])) m[c.klubpro_player_id] = c
    return m
  }, [data])

  const decide = async (bs, decision, cand) => {
    try {
      await api.kpSetMatch(cm, {
        betterstats_player_id: bs.id,
        betterstats_player_name: bs.name,
        klubpro_player_id: cand?.klubpro_player_id || null,
        klubpro_player_firstname: cand?.firstname || null,
        klubpro_player_lastname: cand?.lastname || null,
        klubpro_player_nickname: cand?.nickname || null,
        decision,
      })
      setMatches(prev => ({
        ...prev,
        [bs.id]: {
          ...(prev[bs.id] || {}),
          betterstats_player_id: bs.id,
          klubpro_player_id: decision === 'approve' ? cand?.klubpro_player_id : (decision === 'reject' || decision === 'skip' ? null : prev[bs.id]?.klubpro_player_id),
          match_status: decision,
          approved: decision === 'approve',
          // keep suggested candidate visible after approve via candidatesById
          match_score: cand ? null : prev[bs.id]?.match_score,
        },
      }))
      setDry(null) // any decision invalidates a prior dry-run
    } catch (e) { toast.error(e.message) }
  }

  const counts = useMemo(() => {
    const bs = data?.betterstats_players || []
    let approved = 0, suggested = 0
    for (const p of bs) {
      const m = matches[p.id]
      if (m?.approved) approved++
      else if (m?.klubpro_player_id && m?.match_status !== 'reject' && m?.match_status !== 'skip') suggested++
    }
    return { total: bs.length, approved, suggested }
  }, [data, matches])

  const visible = useMemo(() => {
    const bs = data?.betterstats_players || []
    const term = q.trim().toLowerCase()
    return bs.filter(p => {
      if (term && !p.name?.toLowerCase().includes(term)) return false
      const m = matches[p.id]
      if (filter === 'approved') return !!m?.approved
      if (filter === 'suggested') return !m?.approved && !!m?.klubpro_player_id && m?.match_status !== 'reject' && m?.match_status !== 'skip'
      if (filter === 'unmatched') return !m?.klubpro_player_id || m?.match_status === 'reject'
      return true
    })
  }, [data, matches, q, filter])

  const runDryRun = async () => {
    try {
      const r = await api.kpPlayerDryRun(cm)
      setDry(r)
      if (!r.players_changing) toast.info('Nothing to change — approved matches already match the staged data.')
    } catch (e) { toast.error(e.message) }
  }

  const runImport = async () => {
    if (!window.confirm(`Import ${dry.players_changing} player update(s)? A backup is taken so this can be rolled back from History.`)) return
    setImporting(true)
    try {
      const r = await api.kpPlayerImport(cm)
      toast.success(`Imported — ${r.updated} updated, ${r.skipped} skipped`)
      await load()
    } catch (e) { toast.error(e.message) } finally { setImporting(false) }
  }

  if (!data) return <PbSpinner message="Loading players…" />

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-4 text-[13px]">
            <span className="text-pb-dim">{counts.total} BetterStats players</span>
            <span className="text-green-300">{counts.approved} approved</span>
            <span className="text-pb-amber">{counts.suggested} suggested</span>
          </div>
          <div className="flex gap-2">
            <Btn onClick={runDryRun}>Dry run</Btn>
            <Btn primary disabled={!dry || !dry.players_changing || importing} onClick={runImport}>
              {importing ? 'Importing…' : `Import${dry?.players_changing ? ` ${dry.players_changing}` : ''}`}
            </Btn>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players…"
            className="bg-pb-surface2 border border-pb-hairline2 rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
          {['all', 'suggested', 'approved', 'unmatched'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`font-mono text-[10px] uppercase tracking-wide2 px-2.5 py-1 rounded border ${
                filter === f ? 'border-pb-accent text-pb-text' : 'border-pb-hairline2 text-pb-faint hover:text-pb-dim'}`}
              style={filter === f ? { color: 'var(--pb-accent)' } : {}}>{f}</button>
          ))}
        </div>
      </Card>

      {dry && (
        <Card title={`Dry-run preview — ${dry.players_changing} changing, ${dry.field_writes} field writes`}>
          {dry.players_changing === 0 ? (
            <p className="text-pb-faint text-sm">No changes — approved matches already match the staged data.</p>
          ) : (
            <div className="space-y-3">
              {dry.previews.filter(p => p.error || p.row_changes > 0).map(p => (
                <div key={p.betterstats_player_id} className="pb-hairline-t pt-2 first:pt-0 first:border-0">
                  <div className="text-sm text-pb-text">{p.betterstats_player_name} {p.error && <span className="text-pb-red/70 text-[12px]">· {p.error}</span>}</div>
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
        {visible.map(bs => {
          const m = matches[bs.id]
          const cand = m?.klubpro_player_id ? candidatesById[m.klubpro_player_id] : null
          return (
            <PlayerRow key={bs.id} bs={bs} match={m} cand={cand}
              onApprove={() => cand && decide(bs, 'approve', cand)}
              onReject={() => decide(bs, 'reject')}
              onSkip={() => decide(bs, 'skip')}
              onChange={() => setPicker(bs)} />
          )
        })}
        {!visible.length && <Card><p className="text-pb-faint text-sm">No players match this filter.</p></Card>}
      </div>

      {picker && (
        <CandidatePicker bs={picker} candidates={data.klubpro_candidates}
          onPick={(c) => { decide(picker, 'approve', c); setPicker(null) }}
          onClose={() => setPicker(null)} />
      )}
    </div>
  )
}

function PlayerRow({ bs, match, cand, onApprove, onReject, onSkip, onChange }) {
  const approved = match?.approved
  return (
    <Card pad="p-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* BetterStats (left) */}
        <div className="flex gap-3">
          <Avatar url={bs.has_photo ? api.bsPlayerPhotoUrl(bs.id) : null} name={bs.name} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm text-pb-text font-medium">{bs.name}</span>
              <StatusBadge match={match} />
            </div>
            <div className="text-[11px] text-pb-faint mt-0.5 leading-snug">
              {fmt(bs.gender)} · {fmt(bs.player_role)} · {fmt(bs.batting_hand)} · {fmt(bs.bowling_type)}<br />
              {fmt(bs.email)} · {fmt(bs.phone)} · {bs.skill_positions?.length ? bs.skill_positions.join(', ') : 'no skills'}
            </div>
          </div>
        </div>
        {/* KlubPro (right) */}
        <div className="flex gap-3 md:border-l md:pl-3 border-pb-hairline2">
          {cand ? (
            <>
              <Avatar url={cand.thumbnail_image_found || cand.profile_image_found
                ? api.kpPlayerImageUrl(cand.klubpro_player_id, cand.thumbnail_image_found) : null}
                name={`${cand.firstname || ''} ${cand.lastname || ''}`} />
              <div className="min-w-0">
                <span className="text-sm text-pb-text">
                  {[cand.firstname, cand.lastname].filter(Boolean).join(' ')}
                  {cand.nickname ? <span className="text-pb-faint"> “{cand.nickname}”</span> : null}
                </span>
                <div className="text-[11px] text-pb-faint mt-0.5 leading-snug">
                  {fmt(cand.gender)} · {fmt(cand.betterstats_player_role)} · {fmt(cand.betterstats_batting_hand)} · {fmt(cand.betterstats_bowling_type)}
                  {cand.betterstats_is_opening_batsman ? ' · opener' : ''}<br />
                  {fmt(cand.email)} · {fmt(cand.mobile)} · {cand.betterstats_skill_positions?.length ? cand.betterstats_skill_positions.join(', ') : 'no skills'}
                </div>
              </div>
            </>
          ) : (
            <div className="text-pb-faintest text-[13px] self-center">No KlubPro match selected</div>
          )}
        </div>
      </div>
      <div className="flex gap-2 mt-2.5 justify-end">
        <Btn sm onClick={onChange}>{cand ? 'Change' : 'Find match'}</Btn>
        {cand && !approved && <Btn sm primary onClick={onApprove}>Approve</Btn>}
        {cand && <Btn sm onClick={onReject}>Reject</Btn>}
        <Btn sm onClick={onSkip}>Skip</Btn>
      </div>
    </Card>
  )
}

function CandidatePicker({ bs, candidates, onPick, onClose }) {
  const [q, setQ] = useState(() => (bs.name || '').replace(',', ' '))
  const term = q.trim().toLowerCase()
  const list = useMemo(() => {
    const arr = term
      ? candidates.filter(c => `${c.firstname || ''} ${c.lastname || ''} ${c.nickname || ''}`.toLowerCase().includes(term))
      : candidates
    return arr.slice(0, 60)
  }, [candidates, term])

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
              <Avatar url={c.thumbnail_image_found || c.profile_image_found
                ? api.kpPlayerImageUrl(c.klubpro_player_id, c.thumbnail_image_found) : null}
                name={`${c.firstname || ''} ${c.lastname || ''}`} />
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
