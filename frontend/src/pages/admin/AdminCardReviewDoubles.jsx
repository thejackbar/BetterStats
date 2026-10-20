import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Note, SegGroup, SegItem } from '../../components/admin/ui'
import DoubleCard from '../../components/admin/cardReview/DoubleCard'
import DoublesBulkModal from '../../components/admin/cardReview/DoublesBulkModal'
import MatchFilters, { FindLink, HistoryLink, filterParams, useFilterParams } from '../../components/admin/cardReview/MatchFilters'

const PAGE = 25

// Step one of Card review: matches the record holds twice that nothing links, so they count twice.
export default function AdminCardReviewDoubles() {
  const [filters, setFilters] = useFilterParams()
  const [kind, setKind] = useState('')
  const [strength, setStrength] = useState('')
  const [shown, setShown] = useState('open')
  const [sort, setSort] = useState('strongest')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState(null)
  const [playerNote, setPlayerNote] = useState(null)
  // Which list the rows on screen belong to. The buttons follow the rows, not the tab just clicked,
  // so the open pairs never show "Put back" while the dismissed list is still loading.
  const [rowsAre, setRowsAre] = useState('open')
  const [bulk, setBulk] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const seq = useRef(0)
  const fresh = useRef(false)

  const load = useCallback((more = false, offset = 0) => {
    const mine = ++seq.current
    setLoading(true)
    api.cardReviewDoubles({
      kind, strength: shown === 'open' ? strength : '', shown, sort, limit: PAGE, offset,
      fresh: fresh.current ? 'true' : undefined, ...filterParams(filters),
    }).then(r => {
      if (mine !== seq.current) return
      fresh.current = false
      setRows(prev => (more ? [...prev, ...r.rows] : r.rows))
      setRowsAre(shown); setTotal(r.total); setCounts(r.counts); setPlayerNote(r.player_note || null); setError(null)
    }).catch(e => { if (mine === seq.current) setError(e.message) })
      .finally(() => { if (mine === seq.current) setLoading(false) })
  }, [kind, strength, shown, sort, filters])

  useEffect(() => { load(false, 0) }, [load])
  // After a change the server's saved scan is dropped for a link or a dismissal, but a copy removed
  // through Manual Entries is not seen by it, so the reload after any action asks for a fresh scan.
  const changed = () => { fresh.current = true; load(false, 0) }

  const by = counts?.by_strength || {}
  return (
    <BetterStatsLayout
      title="Possible doubles"
      caption={counts ? `${counts.total.toLocaleString()} to look at` : undefined}
      actions={
        <div className="flex flex-wrap gap-2">
          {(counts?.by_kind?.relink > 0 || counts?.by_kind?.ca > 0) && counts?.by_strength?.strong > 0 && (
            <Button size="sm" variant="primary" onClick={() => setBulk(true)} data-testid="bulk-fix">Fix the strong ones…</Button>
          )}
          <FindLink filters={filters} />
          <HistoryLink />
          <Button as={Link} to="/admin/card-review" size="sm">Back to Card review</Button>
        </div>
      }
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-4">
        These are matches the record holds twice with nothing linking the copies, so a batter's career, the match type tabs and the
        record boards count them twice. Each one is a club scorecard (imported, typed in or read from a photo) that is not linked to its Cricket
        Australia match, or is linked to the wrong one, or a second club scorecard of the same match. Link it, move the link to the
        right match, or remove the extra copy. If it is not a double, say so and it will not be offered again.
      </p>
      <MatchFilters value={filters} onApply={setFilters} playerNote={playerNote}
        hint="The same words narrow every step of Card review." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegGroup>
          <SegItem active={shown === 'open'} onClick={() => setShown('open')} data-testid="shown-open">
            To look at{counts ? ` (${counts.total})` : ''}
          </SegItem>
          <SegItem active={shown === 'dismissed'} onClick={() => setShown('dismissed')} data-testid="shown-dismissed">
            Marked as different{counts ? ` (${counts.dismissed})` : ''}
          </SegItem>
        </SegGroup>
        {shown === 'open' && (
          <>
            <SegGroup>
              <SegItem active={!strength} onClick={() => setStrength('')}>Any</SegItem>
              <SegItem active={strength === 'strong'} onClick={() => setStrength('strong')} data-testid="s-strong">Strong ({by.strong || 0})</SegItem>
              <SegItem active={strength === 'likely'} onClick={() => setStrength('likely')}>Likely ({by.likely || 0})</SegItem>
              <SegItem active={strength === 'possible'} onClick={() => setStrength('possible')}>Possible ({by.possible || 0})</SegItem>
            </SegGroup>
            <SegGroup>
              <SegItem active={!kind} onClick={() => setKind('')}>Both kinds</SegItem>
              <SegItem active={kind === 'relink'} onClick={() => setKind('relink')} data-testid="k-relink">Wrong link ({counts?.by_kind?.relink || 0})</SegItem>
              <SegItem active={kind === 'ca'} onClick={() => setKind('ca')} data-testid="k-ca">Not linked ({counts?.by_kind?.ca || 0})</SegItem>
              <SegItem active={kind === 'club'} onClick={() => setKind('club')} data-testid="k-club">Two club scorecards</SegItem>
            </SegGroup>
            <SegGroup>
              <SegItem active={sort === 'strongest'} onClick={() => setSort('strongest')}>Strongest first</SegItem>
              <SegItem active={sort === 'newest'} onClick={() => setSort('newest')}>Newest first</SegItem>
            </SegGroup>
          </>
        )}
      </div>
      {counts && counts.formats_differ > 0 && shown === 'open' && (
        <p className="mb-3 text-[12.5px] text-pb-dim" data-testid="formats-note">
          {counts.formats_differ.toLocaleString()} of these have the two copies filed under different match types, which is how a double shows up on a player's profile: once under Two Day and once under One Day.
        </p>
      )}
      {error && <Note toneKey="block">{error}</Note>}
      {loading && rows.length === 0 && <PbSpinner message="Looking for matches held twice…" />}
      {!loading && !error && rows.length === 0 && (
        <Note toneKey="calm">{shown === 'open' ? 'No possible doubles here.' : 'Nothing has been marked as different matches.'}</Note>
      )}
      <div className="space-y-3">
        {rows.map(r => <DoubleCard key={r.key} row={r} dismissed={rowsAre === 'dismissed'} onChanged={changed} />)}
      </div>
      {rows.length < total && (
        <div className="mt-4 text-center">
          <Button disabled={loading} onClick={() => load(true, rows.length)}>Show more ({total - rows.length} left)</Button>
        </div>
      )}
      {bulk && <DoublesBulkModal onClose={() => setBulk(false)} onDone={() => { setBulk(false); changed() }} />}
    </BetterStatsLayout>
  )
}
