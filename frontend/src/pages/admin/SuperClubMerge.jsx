import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Standalone Super Admin tool for real-world club mergers — folds a source
// club's whole synced history (players, seasons, grades, games) into a
// target club, then archives the source. Deliberately its own page rather
// than a per-row action on All Clubs: this is a rare, high-stakes operation,
// not something that belongs cluttering every club's row.
//
// Typical use: sync a since-merged predecessor club as its own temporary
// club first (ordinary onboarding), then fold its history into the real,
// ongoing club here. See services/org_merge.py for the merge mechanics and
// its documented reversibility limits.

const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const SELECT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'

export default function SuperClubMerge() {
  const [clubs, setClubs] = useState([])
  const [loadingClubs, setLoadingClubs] = useState(true)
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [preview, setPreview] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const [repairId, setRepairId] = useState('')
  const [repairing, setRepairing] = useState(false)
  const [repairError, setRepairError] = useState('')
  const [repairResult, setRepairResult] = useState(null)

  useEffect(() => {
    api.superListClubs(false).then((cs) => {
      setClubs([...cs].sort((a, b) => a.name.localeCompare(b.name)))
    }).catch((e) => setError(e.message)).finally(() => setLoadingClubs(false))
  }, [])

  const sourceClub = clubs.find((c) => c.id === sourceId)
  const targetClub = clubs.find((c) => c.id === targetId)

  useEffect(() => {
    setPreview(null); setError(''); setConfirmText(''); setResult(null)
    if (!sourceId || !targetId || sourceId === targetId) return
    setLoadingPreview(true)
    api.superClubMergePreview(sourceId, targetId)
      .then(setPreview)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingPreview(false))
  }, [sourceId, targetId])

  const confirmPhrase = sourceClub ? `MERGE ${sourceClub.name.toUpperCase()}` : ''
  const canMerge = sourceId && targetId && sourceId !== targetId && confirmText.trim() === confirmPhrase && !merging

  const doMerge = async () => {
    setMerging(true); setError('')
    try {
      const r = await api.superClubMerge(sourceId, targetId)
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setMerging(false)
    }
  }

  const reset = () => {
    setSourceId(''); setTargetId(''); setPreview(null); setConfirmText(''); setResult(null); setError('')
  }

  const repairClub = clubs.find((c) => c.id === repairId)
  const doRepair = async () => {
    setRepairing(true); setRepairError(''); setRepairResult(null)
    try {
      const r = await api.superClubRepairMergeStats(repairId)
      setRepairResult(r)
    } catch (e) {
      setRepairError(e.message)
    } finally {
      setRepairing(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-2xl mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Merge clubs</h1>
          <p className="text-sm text-pb-dim mt-1 leading-relaxed">
            For real-world club mergers. Every player, season, grade and game currently synced under the
            source club is moved onto (or merged with, where the same real competition or player already
            exists on both sides) the target club, and the source club is then archived. Not fully reversible,
            see the notes on the tool before running it on a live club.
          </p>
        </div>

        {result ? (
          <div className="pb-card p-5">
            <p className="text-sm text-pb-text mb-3">
              Merged <span className="font-semibold">{sourceClub?.name}</span> into{' '}
              <span className="font-semibold">{targetClub?.name}</span>. {sourceClub?.name} has been archived.
            </p>
            <ul className="font-mono text-[11px] text-pb-dim space-y-0.5 mb-4">
              <li>Seasons: {result.seasons_moved} moved, {result.seasons_merged} merged</li>
              <li>Grades: {result.grades_moved} moved, {result.grades_merged} merged</li>
              <li>Games repointed: {result.games_repointed}</li>
              <li>Players: {result.players_moved} moved, {result.players_merged} merged</li>
            </ul>
            {result.skipped_player_conflicts?.length > 0 && (
              <p className="text-[12px] text-amber-400 mb-4">
                {result.skipped_player_conflicts.length} player(s) hit a data conflict and were left under the
                target club unmerged. Reconcile them manually via Merge Players.
              </p>
            )}
            <button onClick={reset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
              MERGE ANOTHER CLUB
            </button>
          </div>
        ) : (
          <div className="pb-card p-5">
            {loadingClubs ? (
              <p className="font-mono text-[10px] text-pb-faint">loading clubs…</p>
            ) : (
              <>
                <label className={LABEL_CLS}>Source club (its history moves out, then it's archived)</label>
                <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} className={`${SELECT_CLS} mb-4`}>
                  <option value="">. Select the source club, </option>
                  {clubs.map((c) => <option key={c.id} value={c.id} disabled={c.id === targetId}>{c.name}</option>)}
                </select>

                <label className={LABEL_CLS}>Target club (keeps its identity, receives the source's history)</label>
                <select value={targetId} onChange={(e) => setTargetId(e.target.value)} className={`${SELECT_CLS} mb-4`}>
                  <option value="">. Select the target club, </option>
                  {clubs.map((c) => <option key={c.id} value={c.id} disabled={c.id === sourceId}>{c.name}</option>)}
                </select>

                {loadingPreview && <p className="font-mono text-[10px] text-pb-faint mb-3">loading preview…</p>}
                {preview && (
                  <div className="rounded border pb-hairline p-3 mb-4 font-mono text-[11px] text-pb-dim space-y-0.5">
                    <div>{preview.seasons_total} seasons, {preview.grades_total} grades, {preview.games_total} games, {preview.players_total} players</div>
                    <div className="text-pb-faintest">will be reassigned from {sourceClub?.name} onto {targetClub?.name}.</div>
                  </div>
                )}
                {error && <p className="text-[12px] text-pb-red mb-4">{error}</p>}

                {preview && (
                  <>
                    <label className={LABEL_CLS}>
                      Type <span className="text-pb-text">{confirmPhrase}</span> to confirm
                    </label>
                    <input type="text" value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                      className={`${SELECT_CLS} mb-4`} />

                    <button onClick={doMerge} disabled={!canMerge}
                      className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40"
                      style={{ background: 'var(--pb-red, #e05555)' }}>
                      {merging ? 'MERGING…' : 'MERGE & ARCHIVE'}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        )}

        <div className="mt-8">
          <h2 className="text-base font-semibold text-pb-text">Repair a previous merge</h2>
          <p className="text-sm text-pb-dim mt-1 leading-relaxed">
            A merge run before player-season-stats repointing was added could leave some of a player's seasons
            still pointing at the archived predecessor club's copy of that season, they disappear from the
            player's summary while still turning up in raw/analysis views. Safe to run on any club, including one
            that's never been merged (does nothing), and safe to run more than once.
          </p>
          <div className="pb-card p-5 mt-3">
            {loadingClubs ? (
              <p className="font-mono text-[10px] text-pb-faint">loading clubs…</p>
            ) : (
              <>
                <label className={LABEL_CLS}>Club to repair (the target it was merged INTO)</label>
                <select value={repairId} onChange={(e) => { setRepairId(e.target.value); setRepairResult(null); setRepairError('') }}
                  className={`${SELECT_CLS} mb-4`}>
                  <option value="">. Select a club, </option>
                  {clubs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {repairError && <p className="text-[12px] text-pb-red mb-3">{repairError}</p>}
                {repairResult && (
                  <div className="rounded border pb-hairline p-3 mb-4 font-mono text-[11px] text-pb-dim space-y-0.5">
                    <div>Season stats: {repairResult.season_stats_repointed} repointed, {repairResult.season_stats_deduped} deduped</div>
                    <div>Grade stats: {repairResult.grade_stats_repointed} repointed, {repairResult.grade_stats_deduped} deduped</div>
                    {repairResult.unresolved?.length > 0 && (
                      <div className="text-amber-400">{repairResult.unresolved.length} row(s) had no matching season/grade in this club and were left as-is.</div>
                    )}
                  </div>
                )}
                <button onClick={doRepair} disabled={!repairId || repairing}
                  className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40"
                  style={{ background: 'var(--pb-accent)' }}>
                  {repairing ? 'REPAIRING…' : `REPAIR ${repairClub?.name?.toUpperCase() || 'CLUB'}`}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
