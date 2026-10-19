import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, Select, SegGroup, SegItem } from '../../components/admin/ui'
import {
  GROUPS, ChoiceControl, DifferenceTable, SizeBar, SuggestionBadge, fmtDate, matchPageUrl,
} from '../../components/admin/cardReview/shared'

const PAGE = 50
export const QUEUE_KEY = 'card-review-queue'

// One match as one line. The line names the biggest difference; a caret opens every difference
// without leaving the page, so the list stays one uniform row per match.
function Line({ r, open, onToggle, selected, onSelect, onChoose, busy }) {
  return (
    <>
      <tr className={`border-t border-pb-hairline align-middle ${open ? 'bg-pb-surface2/40' : ''}`} data-testid="queue-row" data-match={r.match_id}>
        <td className="pl-4 pr-1 py-2.5">
          <input type="checkbox" checked={selected} onChange={onSelect} aria-label={`Select ${r.grade} v ${r.opposition}`} disabled={!r.suggested} />
        </td>
        <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap">{fmtDate(r.date)}</td>
        <td className="px-3 py-2.5 whitespace-nowrap">{r.grade}</td>
        <td className="px-3 py-2.5">{r.opposition}</td>
        <td className="px-3 py-2.5 min-w-[220px]">
          <Link to={`/admin/card-review/match/${r.match_id}`} className="text-pb-text hover:text-pb-accent-ink" data-testid="headline">
            {r.headline || 'Open'}
          </Link>
          {r.item_count > 1 && (
            <button
              type="button" onClick={onToggle} aria-expanded={open} data-testid="caret"
              className="ml-2 rounded border px-1.5 py-0.5 font-mono text-[10.5px]"
              style={{ borderColor: open ? 'rgba(245,181,66,.4)' : 'rgba(59,130,246,.4)', color: open ? '#f5b542' : '#7fb0ff',
                background: open ? 'rgba(245,181,66,.08)' : 'rgba(59,130,246,.08)' }}
            >
              {open ? '▾' : '▸'} +{r.item_count - 1} more
            </button>
          )}
        </td>
        <td className="px-3 py-2.5"><SizeBar size={r.size} /></td>
        <td className="px-3 py-2.5"><SuggestionBadge suggested={r.suggested} /></td>
        <td className="px-3 py-2.5">
          <div className="flex items-center gap-2">
            <ChoiceControl compact value={r.current} onChange={onChoose} disabled={busy} data-testid="choice" />
            {r.decided_by_hand && <span title="Chosen by hand: a bulk switch never changes this" className="font-mono text-[9px] uppercase text-pb-faint">hand</span>}
          </div>
        </td>
      </tr>
      {open && (
        <tr className="bg-pb-surface2/30" data-testid="queue-detail">
          <td />
          <td colSpan={7} className="px-3 pb-4 pt-1">
            <div className="rounded-lg border border-pb-hairline bg-pb-bg p-3.5">
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint mb-2">All {r.item_count} differences in this match</div>
              <DifferenceTable items={r.items} />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="text-[12px] text-pb-dim">
                  Cricket Australia also holds {Object.entries({ 'balls faced': r.ca_holds.balls, 'dismissal credits': r.ca_holds.credits, 'fall of wickets': r.ca_holds.fow, partnerships: r.ca_holds.partnerships })
                    .filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join(', ') || 'no extra detail for this match'}.
                </span>
                <Button size="sm" as={Link} to={`/admin/card-review/match/${r.match_id}`} className="ml-auto">Open side by side ›</Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// A match whose two cards do not look like the same game. The card says what each side holds
// and what the scorecards share; "Find a better match" asks for other games of the club close
// in date whose batters and scores really do match.
function PairingCard({ r, onChanged }) {
  const toast = useToast()
  const [cands, setCands] = useState(null)
  const [busy, setBusy] = useState(false)

  async function find() {
    setBusy(true)
    try { setCands((await api.cardReviewCandidates(r.match_id)).candidates) } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function act(fn, ok) {
    setBusy(true)
    try { await fn(); toast.success(ok); onChanged() } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="rounded-xl border border-pb-hairline bg-pb-surface p-4" data-testid="pairing-card" data-match={r.match_id}>
      <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">Club scorecard</div>
          <div className="mt-1 font-semibold text-pb-text">{r.grade} v {r.opposition}</div>
          <div className="font-mono text-[12px] text-pb-dim">{fmtDate(r.date)} · {r.club_batters} batters</div>
          <div className="mt-1 text-[12px] text-pb-faint">{r.source.label}{r.source.at ? ` · ${fmtDate(r.source.at)}` : ''}</div>
        </div>
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">Linked now to (Cricket Australia)</div>
          <div className="mt-1 font-mono text-[12px] text-pb-dim">{r.ca_batters} batters on its card</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge toneKey="block">{r.shared} of {Math.min(r.club_batters, r.ca_batters) || r.club_batters} batters in common</Badge>
          </div>
        </div>
      </div>
      {cands && (
        <div className="mt-3 rounded-lg border border-pb-hairline bg-pb-bg p-3" data-testid="candidates">
          {cands.length === 0 && <div className="text-[12.5px] text-pb-dim">No better match found. Open both cards to decide, or unlink if they are different games.</div>}
          {cands.map(c => (
            <div key={c.game_id} className="flex flex-wrap items-center gap-3 py-1.5">
              <div className="min-w-0 flex-1 text-[13px] text-pb-text">
                {c.grade} v {c.opposition} <span className="font-mono text-[12px] text-pb-dim">· {fmtDate(c.date)}</span>
                <span className="ml-2"><Badge toneKey="ok">{c.shared} of {c.club_batters} batters in common</Badge></span>
                {c.taken_by && <span className="ml-2"><Badge toneKey="warn">Already linked to another club scorecard</Badge></span>}
              </div>
              <Button size="sm" variant="primary" disabled={busy || !!c.taken_by}
                onClick={() => act(() => api.cardReviewRelink(r.match_id, c.game_id), 'Linked to the better match')}>
                Re-link to this match
              </Button>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!cands && <Button size="sm" variant="primary" disabled={busy} onClick={find}>Find a better match</Button>}
        <Button size="sm" disabled={busy} onClick={() => act(() => api.cardReviewPairOk(r.match_id), 'Marked as the same match')}>Looks right: keep the link</Button>
        <Button size="sm" disabled={busy} onClick={() => {
          if (confirm('Say these are two different matches? The club scorecard will stand alone and Cricket Australia\'s card will count as its own match. This can be undone.')) {
            act(() => api.cardReviewUnlink(r.match_id), 'Unlinked')
          }
        }}>Not the same match: unlink</Button>
        <Button size="sm" as={Link} to={`/admin/card-review/match/${r.match_id}`} className="ml-auto">Open side by side ›</Button>
      </div>
    </div>
  )
}

export default function AdminCardReviewList() {
  const { group } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const g = GROUPS[group]
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [sources, setSources] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState({})
  const [picked, setPicked] = useState({})
  const [filters, setFilters] = useState({ season: '', decided: 'no', recent: false, source_file: '' })
  const seq = useRef(0)

  const query = useCallback((offset) => ({
    group, limit: PAGE, offset, season: filters.season || undefined,
    decided: filters.decided === 'all' ? undefined : filters.decided,
    recent_seasons: filters.recent ? 3 : undefined, source_file: filters.source_file || undefined,
  }), [group, filters])

  const load = useCallback((more = false) => {
    const mine = ++seq.current
    setLoading(true)
    api.cardReviewMatches(query(more ? rows.length : 0))
      .then(r => {
        if (mine !== seq.current) return
        setRows(prev => (more ? [...prev, ...r.rows] : r.rows))
        setTotal(r.total)
        setSources(r.sources)
        setError(null)
      })
      .catch(e => { if (mine === seq.current) setError(e.message) })
      .finally(() => { if (mine === seq.current) setLoading(false) })
  }, [query, rows.length])

  useEffect(() => { load(false) }, [group, filters]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.cardReviewOverview().then(o => setSeasons(o.seasons.map(s => s.season))).catch(() => {}) }, [])
  // The compare page walks the same order with Previous and Next.
  useEffect(() => {
    try { sessionStorage.setItem(QUEUE_KEY, JSON.stringify({ group, ids: rows.map(r => r.match_id) })) } catch { /* private window */ }
  }, [rows, group])

  async function choose(r, key) {
    if (key === 'hybrid') { navigate(`/admin/card-review/match/${r.match_id}#hybrid`); return }
    if (key === r.current) return
    setBusy(true)
    try {
      await api.cardReviewChoose(r.match_id, key)
      toast.success(`${r.grade} v ${r.opposition} now shows ${key === 'ca' ? 'Cricket Australia' : 'the club scorecard'}`)
      setRows(prev => prev.map(x => (x.match_id === r.match_id ? { ...x, current: key, decided_by_hand: true } : x)))
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function accept() {
    const ids = Object.keys(picked).filter(k => picked[k])
    if (!ids.length) return
    setBusy(true)
    try {
      const r = await api.cardReviewAccept(ids)
      toast.success(`${r.switched} matches switched${r.skipped.length ? `, ${r.skipped.length} skipped` : ''}`)
      setPicked({})
      load(false)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (!g) return <BetterStatsLayout title="Card review"><Note toneKey="block">That group does not exist.</Note></BetterStatsLayout>
  const isPairing = group === 'pairing'
  const nPicked = Object.values(picked).filter(Boolean).length

  return (
    <BetterStatsLayout
      title={g.label}
      caption={`${total.toLocaleString()} match${total === 1 ? '' : 'es'}`}
      actions={<Button as={Link} to="/admin/card-review">Back to Card review</Button>}
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-4">
        {isPairing
          ? 'These club scorecards are linked to a Cricket Australia match, but the two do not look like the same game. Fix the link first. Once the pairing is right, the match moves into the normal review.'
          : 'Newest first, one line per match. The line shows the biggest difference. When there are more, a caret opens the full list without leaving the page.'}
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegGroup>
          <SegItem active={!filters.recent} onClick={() => setFilters(f => ({ ...f, recent: false }))}>All seasons</SegItem>
          <SegItem active={filters.recent} onClick={() => setFilters(f => ({ ...f, recent: true }))}>Last 3 seasons</SegItem>
        </SegGroup>
        <SegGroup>
          <SegItem active={filters.decided === 'no'} onClick={() => setFilters(f => ({ ...f, decided: 'no' }))}>Not decided</SegItem>
          <SegItem active={filters.decided === 'yes'} onClick={() => setFilters(f => ({ ...f, decided: 'yes' }))}>Decided</SegItem>
          <SegItem active={filters.decided === 'all'} onClick={() => setFilters(f => ({ ...f, decided: 'all' }))}>All</SegItem>
        </SegGroup>
        <Select className="!w-auto" value={filters.season} onChange={e => setFilters(f => ({ ...f, season: e.target.value }))} aria-label="Season">
          <option value="">Every season</option>
          {seasons.map(s => <option key={s} value={s}>{s}</option>)}
        </Select>
        {sources.length > 1 && (
          <Select className="!w-auto" value={filters.source_file} onChange={e => setFilters(f => ({ ...f, source_file: e.target.value }))} aria-label="Source file">
            <option value="">Every source</option>
            {sources.map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        )}
        {!isPairing && (
          <Button className="ml-auto" size="sm" disabled={busy || nPicked === 0} onClick={accept} data-testid="accept">
            Accept the suggestion for {nPicked} selected
          </Button>
        )}
      </div>

      {error && <Note toneKey="block">{error}</Note>}
      {loading && rows.length === 0 && <PbSpinner message="Loading matches…" />}
      {!loading && !error && rows.length === 0 && (
        <Note toneKey="calm">Nothing here{filters.decided === 'no' ? ' that is still undecided' : ''}.</Note>
      )}

      {isPairing ? (
        <div className="space-y-3">{rows.map(r => <PairingCard key={r.match_id} r={r} onChanged={() => load(false)} />)}</div>
      ) : rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-pb-hairline bg-pb-surface">
          <table className="w-full text-[13px]" data-testid="queue">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-[0.1em] text-pb-faint">
                <th className="w-7 pl-4" />
                <th className="px-3 py-2.5 font-normal">Date</th>
                <th className="px-3 py-2.5 font-normal">Grade</th>
                <th className="px-3 py-2.5 font-normal">Opposition</th>
                <th className="px-3 py-2.5 font-normal">Biggest difference</th>
                <th className="px-3 py-2.5 font-normal">Size</th>
                <th className="px-3 py-2.5 font-normal">Suggested</th>
                <th className="px-3 py-2.5 font-normal">Showing now</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <Line
                  key={r.match_id} r={r} busy={busy}
                  open={!!open[r.match_id]} onToggle={() => setOpen(o => ({ ...o, [r.match_id]: !o[r.match_id] }))}
                  selected={!!picked[r.match_id]} onSelect={() => setPicked(p => ({ ...p, [r.match_id]: !p[r.match_id] }))}
                  onChoose={key => choose(r, key)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length < total && (
        <div className="mt-4 text-center">
          <Button disabled={loading} onClick={() => load(true)}>Show more ({total - rows.length} left)</Button>
        </div>
      )}
      <p className="mt-4 text-[12px] text-pb-faint">
        The size bar counts how much differs, not just how many items. A different total or winner is never suggested for a switch.
        The combined choice opens the match, because it needs a preview first.
      </p>
    </BetterStatsLayout>
  )
}
