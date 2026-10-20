import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, Select } from '../../components/admin/ui'
import { SideBox, Evidence } from '../../components/admin/cardReview/DoubleCard'
import MatchFilters, { filterParams, hasFilters, useFilterParams } from '../../components/admin/cardReview/MatchFilters'
import { GROUPS, CHOICE_NAME, fmtDate } from '../../components/admin/cardReview/shared'

const PAGE = 25
const STATE = {
  linked: { label: 'Linked: one match, two copies', tone: 'ok' },
  club_only: { label: 'Club scorecard only', tone: 'warn' },
  ca_only: { label: 'Cricket Australia only', tone: 'accent' },
}

// Look a fixture up and see every copy of it, whether or not anything links them. Meant for a
// question about a card the site shows ("is that score right?"), and for finding a double the scan
// did not suggest: tick a club scorecard and a Cricket Australia match and link them by hand.
export default function AdminCardReviewFind() {
  const toast = useToast()
  const [filters, setFilters] = useFilterParams()
  const [season, setSeason] = useState('')
  const [opts, setOpts] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [capped, setCapped] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [picked, setPicked] = useState({})
  const [busy, setBusy] = useState(false)
  const seq = useRef(0)
  const searched = hasFilters(filters) || !!season

  useEffect(() => { api.cardReviewFindOptions().then(setOpts).catch(() => {}) }, [])

  const load = useCallback((more = false, offset = 0) => {
    if (!searched) { setRows([]); setTotal(0); return }
    const mine = ++seq.current
    setLoading(true)
    api.cardReviewFind({ ...filterParams(filters), season, limit: PAGE, offset })
      .then(r => {
        if (mine !== seq.current) return
        setRows(prev => (more ? [...prev, ...r.rows] : r.rows)); setTotal(r.total); setCapped(r.capped); setError(null)
      })
      .catch(e => { if (mine === seq.current) setError(e.message) })
      .finally(() => { if (mine === seq.current) setLoading(false) })
  }, [filters, season, searched])
  useEffect(() => { load(false, 0) }, [load])

  const chosen = rows.filter(r => picked[r.key])
  const club = chosen.filter(r => r.state === 'club_only')
  const ca = chosen.filter(r => r.state === 'ca_only')
  const canLink = chosen.length === 2 && club.length === 1 && ca.length === 1

  async function linkPicked() {
    setBusy(true)
    try {
      const res = await api.cardReviewDoubleLink(club[0].match_id, ca[0].game_id)
      toast.success(`Linked. The site now shows the ${res.shows === 'club' ? 'club scorecard' : 'Cricket Australia scorecard'}.`)
      setPicked({}); load(false, 0)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <BetterStatsLayout
      title="Find a match"
      caption={searched ? `${total.toLocaleString()} fixture${total === 1 ? '' : 's'}` : undefined}
      actions={<Button as={Link} to="/admin/card-review" size="sm">Back to Card review</Button>}
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-4">
        Look up a fixture and see every copy the record holds of it: the Cricket Australia match, the club scorecard, or both. Use it to
        check a figure someone has questioned, or to find two copies of one match that Card review did not suggest.
      </p>
      <MatchFilters value={filters} onApply={setFilters}
        extra={
          <label className="block min-w-0 text-[11.5px] text-pb-dim">Season
            <Select className="mt-1" value={season} onChange={e => setSeason(e.target.value)} data-testid="f-season">
              <option value="">Any season</option>
              {(opts?.seasons || []).map(s => <option key={s} value={s}>{s}</option>)}
            </Select>
          </label>
        } />
      {!searched && <Note toneKey="calm">Give at least one thing to look for: an opposition, a player, a grade, a competition, a season or a date.</Note>}
      {error && <Note toneKey="block">{error}</Note>}
      {capped && <div className="mb-3"><Note toneKey="warn">That matches more fixtures than can be listed. The newest are shown. Add a player, a grade or a date range to narrow it.</Note></div>}
      {loading && rows.length === 0 && <PbSpinner message="Looking…" />}
      {searched && !loading && !error && rows.length === 0 && <Note toneKey="calm">No fixture matches that.</Note>}

      {rows.length > 0 && (
        <div className="sticky top-0 z-10 mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-pb-hairline bg-pb-surface px-4 py-2.5" data-testid="link-bar">
          <span className="text-[12.5px] text-pb-dim">
            {canLink ? 'Ready: one club scorecard and one Cricket Australia match are ticked.'
              : 'Tick one club-only fixture and one Cricket Australia-only fixture to link them as the same match.'}
          </span>
          <Button className="ml-auto" size="sm" variant="primary" disabled={!canLink || busy} onClick={linkPicked} data-testid="link-picked">
            Same match: link the two
          </Button>
        </div>
      )}

      <div className="space-y-3">
        {rows.map(r => {
          const s = STATE[r.state]
          const selectable = r.state !== 'linked'
          const other = r.candidate && (r.candidate.a.id === r.match_id || r.candidate.a.id === r.game_id ? r.candidate.b : r.candidate.a)
          return (
            <div key={r.key} className="rounded-xl border border-pb-hairline bg-pb-surface p-4" data-testid="fixture" data-state={r.state}>
              <div className="flex flex-wrap items-center gap-2">
                {selectable && (
                  <input type="checkbox" checked={!!picked[r.key]} onChange={() => setPicked(p => ({ ...p, [r.key]: !p[r.key] }))}
                    aria-label="Select this fixture to link" data-testid="pick" />
                )}
                <Badge toneKey={s.tone}>{s.label}</Badge>
                <span className="font-mono text-[12px] text-pb-dim">{fmtDate(r.date)}</span>
                {r.review && (
                  <>
                    <Badge toneKey={GROUPS[r.review.group]?.tone || 'calm'}>{GROUPS[r.review.group]?.label}</Badge>
                    <span className="text-[12px] text-pb-dim">Site shows: {CHOICE_NAME[r.review.current]}{r.review.headline ? ` · ${r.review.headline}` : ''}</span>
                    <Button className="ml-auto" size="sm" as={Link} to={`/admin/card-review/match/${r.match_id}`} data-testid="open-compare">Compare side by side ›</Button>
                  </>
                )}
              </div>
              <div className={`mt-3 grid gap-3 ${r.copies.length > 1 ? 'md:grid-cols-2' : ''}`}>
                {r.copies.map(c => <SideBox key={c.id} side={c} />)}
              </div>
              {r.candidate && (
                <div className="mt-3 rounded-lg border border-pb-hairline bg-pb-bg p-3" data-testid="candidate">
                  <div className="mb-2 text-[12.5px] text-pb-text">This may be the same match as another copy:</div>
                  <Evidence row={r.candidate} />
                  <div className="mt-2 text-[12.5px] text-pb-dim">
                    {other.grade} v {other.opposition}, {fmtDate(other.date)}.{' '}
                    <Link className="underline" to="/admin/card-review/doubles" data-testid="to-doubles">Review it in Possible doubles</Link>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      {rows.length < total && (
        <div className="mt-4 text-center">
          <Button disabled={loading} onClick={() => load(true, rows.length)}>Show more ({total - rows.length} left)</Button>
        </div>
      )}
    </BetterStatsLayout>
  )
}
